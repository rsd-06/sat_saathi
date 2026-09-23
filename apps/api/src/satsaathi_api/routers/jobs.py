"""Asking a question, watching it run, and taking the result away."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Query, Response, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from satsaathi_core.db import session_scope
from satsaathi_core.events import InProcessEventBus, RedisEventBus
from satsaathi_core.models import InputSet, Job, JobStatus

from .. import jobs_service
from ..deps import Session, SettingsDep, StorageDep, api_error
from ..schemas import ErrorBody, JobIn, JobOut, JobPage, JobSummary, StepOut

router = APIRouter(prefix="/jobs", tags=["jobs"])

#: Falls back to an in-process bus when Redis is unreachable, so a developer
#: without a broker still gets a live trace — from this process only.
_fallback_bus = InProcessEventBus()
_redis_bus: RedisEventBus | None = None


def _bus(settings) -> tuple[Any, bool]:
    global _redis_bus
    if settings.redis_url:
        if _redis_bus is None:
            _redis_bus = RedisEventBus(settings.redis_url)
        return _redis_bus, True
    return _fallback_bus, False


def _to_out(job: Job) -> JobOut:
    return JobOut(
        id=job.id,
        input_set_id=job.input_set_id,
        query_text=job.query_text,
        query_lang=job.query_lang,
        ui_lang=job.ui_lang,
        intent=job.intent,
        status=job.status.value,
        confidence=job.confidence,
        answer=job.answer,
        error=ErrorBody(**job.error) if job.error else None,
        steps=[StepOut(**s) for s in jobs_service.step_records(job)],
        artifacts=[],
        created_at=job.created_at,
        finished_at=job.finished_at,
    )


@router.post("", response_model=JobOut, status_code=status.HTTP_201_CREATED)
async def create_job(
    session: Session,
    settings: SettingsDep,
    storage: StorageDep,
    body: JobIn,
    background: BackgroundTasks,
) -> JobOut:
    input_set = await session.get(InputSet, body.input_set_id)
    if input_set is None:
        raise api_error(
            status.HTTP_404_NOT_FOUND,
            "inputSet.not_found",
            id=str(body.input_set_id),
        )

    blocked = [c for c in (input_set.checks or []) if c.get("status") == "fail"]
    if blocked:
        raise api_error(
            status.HTTP_409_CONFLICT,
            "job.error.inputSetBlocked",
            checks=[c["key"] for c in blocked],
        )

    job = await jobs_service.create_job(
        session,
        input_set_id=body.input_set_id,
        query_text=body.query_text,
        query_lang=body.query_lang,
        ui_lang=body.ui_lang,
    )
    job_id = job.id
    await session.commit()

    background.add_task(run_job_task, job_id)

    reloaded = await jobs_service.load_job(session, job_id)
    return _to_out(reloaded or job)


async def run_job_task(job_id: uuid.UUID) -> None:
    """Execute the job and publish each snapshot as it happens."""
    from satsaathi_core.settings import get_settings
    from satsaathi_core.storage import build_storage

    settings = get_settings()
    storage = build_storage(
        settings.storage_backend,
        local_root=settings.storage_dir,
        bucket=settings.s3_bucket,
        offline=settings.is_offline,
    )
    bus, _ = _bus(settings)
    queue: asyncio.Queue = asyncio.Queue()

    def publish(snapshot: dict[str, Any]) -> None:
        queue.put_nowait(snapshot)

    async def drain() -> None:
        while True:
            snapshot = await queue.get()
            if snapshot is None:
                return
            try:
                await bus.publish(str(job_id), snapshot)
            except Exception:
                # A dead broker must not fail the job; the trace is persisted.
                pass

    drainer = asyncio.create_task(drain())
    try:
        async with session_scope() as session:
            job = await jobs_service.load_job(session, job_id)
            if job is None:
                return
            try:
                await jobs_service.execute(
                    session,
                    job,
                    storage=storage,
                    settings=settings,
                    # Every frame leaves in the job shape, so the client never
                    # has to tell a trace document from a job document.
                    publish=lambda snap: publish(
                        jobs_service.snapshot_for_stream(job, snap)
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                job.status = JobStatus.failed
                job.error = {"key": "job.failed", "params": {"detail": str(exc)}}
    finally:
        queue.put_nowait(None)
        await drainer


@router.get("", response_model=JobPage)
async def list_jobs(
    session: Session,
    limit: int = Query(default=20, le=100, ge=1),
    offset: int = Query(default=0, ge=0),
    job_status: str | None = Query(default=None, alias="status"),
) -> JobPage:
    stmt = select(Job, InputSet.mode).join(InputSet, Job.input_set_id == InputSet.id)
    count_stmt = select(func.count()).select_from(Job)
    if job_status:
        stmt = stmt.where(Job.status == JobStatus(job_status))
        count_stmt = count_stmt.where(Job.status == JobStatus(job_status))

    total = (await session.scalars(count_stmt)).one()
    rows = (
        await session.execute(
            stmt.order_by(Job.created_at.desc()).limit(limit).offset(offset)
        )
    ).all()

    return JobPage(
        items=[
            JobSummary(
                id=job.id,
                query_text=job.query_text,
                query_lang=job.query_lang,
                mode=mode.value,
                status=job.status.value,
                confidence=job.confidence,
                created_at=job.created_at,
            )
            for job, mode in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{job_id}", response_model=JobOut)
async def get_job(session: Session, job_id: uuid.UUID) -> JobOut:
    job = await jobs_service.load_job(session, job_id)
    if job is None:
        raise api_error(status.HTTP_404_NOT_FOUND, "job.not_found", id=str(job_id))
    return _to_out(job)


@router.get("/{job_id}/events")
async def job_events(
    session: Session, settings: SettingsDep, job_id: uuid.UUID
) -> StreamingResponse:
    """Server-sent events carrying a full trace snapshot per message.

    A snapshot rather than a delta, so a browser that reconnects mid-job
    recovers on the next message with nothing to replay.
    """
    job = await jobs_service.load_job(session, job_id)
    if job is None:
        raise api_error(status.HTTP_404_NOT_FOUND, "job.not_found", id=str(job_id))

    initial = _to_out(job).model_dump(mode="json")
    bus, cross_process = _bus(settings)
    terminal = {"succeeded", "failed", "needs_review"}

    async def stream():
        yield f"event: snapshot\ndata: {json.dumps(initial)}\n\n"
        if initial["status"] in terminal:
            yield "event: done\ndata: {}\n\n"
            return
        try:
            async for snapshot in bus.subscribe(str(job_id)):
                yield f"event: snapshot\ndata: {json.dumps(snapshot)}\n\n"
                if snapshot.get("status") in terminal:
                    yield "event: done\ndata: {}\n\n"
                    return
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            payload = json.dumps(
                {"error": {"key": "events.stream_failed", "params": {"detail": str(exc)}}}
            )
            yield f"event: error\ndata: {payload}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{job_id}/trace")
async def job_trace(session: Session, job_id: uuid.UUID) -> Response:
    job = await jobs_service.load_job(session, job_id)
    if job is None:
        raise api_error(status.HTTP_404_NOT_FOUND, "job.not_found", id=str(job_id))

    result = await session.scalars(
        select(InputSet)
        .where(InputSet.id == job.input_set_id)
        .options(selectinload(InputSet.assets))
    )
    input_set = result.first()

    document = {
        "trace_version": 1,
        "job_id": str(job.id),
        "created_at": job.created_at.isoformat(),
        "status": job.status.value,
        "confidence": job.confidence,
        "answer": job.answer,
        "query": {
            "text": job.query_text,
            "lang": job.query_lang,
            "ui_lang": job.ui_lang,
            "intent": job.intent,
        },
        "input_set": {
            "mode": input_set.mode.value if input_set else "single",
            "assets": [{"role": a.role.value} for a in (input_set.assets if input_set else [])],
        },
        "plan": job.plan or [],
        "steps": [
            {**s, "artifacts": []} for s in jobs_service.step_records(job)
        ],
    }
    return JSONResponse(
        document,
        headers={
            "Content-Disposition": f'attachment; filename="trace-{job.id}.json"'
        },
    )


@router.get("/{job_id}/result.geojson")
async def job_geojson(session: Session, job_id: uuid.UUID) -> Response:
    """Vector outputs as a FeatureCollection.

    Only geometry that was actually produced appears here; an input with no
    coordinate system yields an empty collection rather than invented shapes.
    """
    job = await jobs_service.load_job(session, job_id)
    if job is None:
        raise api_error(status.HTTP_404_NOT_FOUND, "job.not_found", id=str(job_id))

    from geoalchemy2.shape import to_shape
    from shapely.geometry import mapping

    from satsaathi_core.models import InputSetAsset

    rows = await session.scalars(
        select(InputSetAsset)
        .where(InputSetAsset.input_set_id == job.input_set_id)
        .options(selectinload(InputSetAsset.asset))
    )

    features = []
    for row in rows:
        asset = row.asset
        if asset.footprint is None:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": mapping(to_shape(asset.footprint)),
                "properties": {
                    "role": row.role.value,
                    "filename": asset.filename,
                    "crs": asset.crs,
                    "kind": "footprint",
                },
            }
        )

    return JSONResponse(
        {"type": "FeatureCollection", "features": features},
        headers={
            "Content-Disposition": f'attachment; filename="result-{job.id}.geojson"'
        },
    )
