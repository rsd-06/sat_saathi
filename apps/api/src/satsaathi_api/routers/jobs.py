"""Asking a question, watching it run, and taking the result away."""

from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from satsaathi_core.db import session_scope
from satsaathi_core.models import InputSet, Job, JobStatus
from satsaathi_jobs import service as jobs_service
from satsaathi_jobs.runner import event_bus

from ..deps import Session, SettingsDep, StorageDep, api_error
from ..dispatch import dispatch_job
from ..schemas import ErrorBody, JobIn, JobOut, JobPage, JobSummary, StepOut
from .auth import CurrentUser, current_user

# Everything here is somebody's own work, so all of it needs an account.
router = APIRouter(prefix="/jobs", tags=["jobs"], dependencies=[Depends(current_user)])


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
    user: CurrentUser,
    settings: SettingsDep,
    storage: StorageDep,
    body: JobIn,
    background: BackgroundTasks,
) -> JobOut:
    input_set = await session.get(InputSet, body.input_set_id)
    if input_set is None or input_set.user_id != user.id:
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
        user_id=user.id,
    )
    # Plan before dispatching. The interface can then show the whole route
    # immediately, and the dispatcher knows which hardware the job needs.
    _planned, queue = await jobs_service.plan_job(session, job, storage=storage, settings=settings)
    job_id = job.id
    await session.commit()

    dispatch_job(job_id, settings, background, queue=queue)

    reloaded = await jobs_service.load_job(session, job_id)
    return _to_out(reloaded or job)


@router.get("", response_model=JobPage)
async def list_jobs(
    session: Session,
    user: CurrentUser,
    limit: int = Query(default=20, le=100, ge=1),
    offset: int = Query(default=0, ge=0),
    job_status: str | None = Query(default=None, alias="status"),
) -> JobPage:
    stmt = select(Job, InputSet.mode).join(InputSet, Job.input_set_id == InputSet.id)
    stmt = stmt.where(Job.user_id == user.id)
    count_stmt = select(func.count()).select_from(Job).where(Job.user_id == user.id)
    if job_status:
        stmt = stmt.where(Job.status == JobStatus(job_status))
        count_stmt = count_stmt.where(Job.status == JobStatus(job_status))

    total = (await session.scalars(count_stmt)).one()
    rows = (
        await session.execute(stmt.order_by(Job.created_at.desc()).limit(limit).offset(offset))
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
async def get_job(session: Session, user: CurrentUser, job_id: uuid.UUID) -> JobOut:
    job = await jobs_service.load_job(session, job_id)
    # Someone else's job is reported exactly like a missing one, so ids
    # cannot be probed to learn what other accounts have run.
    if job is None or job.user_id != user.id:
        raise api_error(status.HTTP_404_NOT_FOUND, "job.not_found", id=str(job_id))
    return _to_out(job)


#: How long the stream waits on the broker before checking the database
#: instead. See `job_events` for why it cannot only wait.
POLL_SECONDS = 2.0

TERMINAL = {"succeeded", "failed", "needs_review"}


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


async def _current(job_id: uuid.UUID) -> dict | None:
    """Re-read the job on its own session, outside the request's."""
    async with session_scope() as session:
        job = await jobs_service.load_job(session, job_id)
        return _to_out(job).model_dump(mode="json") if job else None


@router.get("/{job_id}/events")
async def job_events(
    session: Session, user: CurrentUser, settings: SettingsDep, job_id: uuid.UUID
) -> StreamingResponse:
    """Server-sent events carrying a full trace snapshot per message.

    A snapshot rather than a delta, so a browser that reconnects mid-job
    recovers on the next message with nothing to replay.

    Redis pub/sub has no replay, which makes the broker alone unsafe to wait
    on: a job that finishes between this handler reading the row and the
    subscription being established publishes every one of its frames into an
    empty channel, and the browser then waits for a message that never comes.
    A worker that finishes a job in under a second loses that race routinely.
    So the stream falls back to re-reading the row whenever the broker goes
    quiet, which doubles as the keep-alive that proxies want to see.
    """
    job = await jobs_service.load_job(session, job_id)
    # Someone else's job is reported exactly like a missing one, so ids
    # cannot be probed to learn what other accounts have run.
    if job is None or job.user_id != user.id:
        raise api_error(status.HTTP_404_NOT_FOUND, "job.not_found", id=str(job_id))

    initial = _to_out(job).model_dump(mode="json")
    bus, _cross_process = event_bus(settings)

    async def stream():
        yield _sse("snapshot", initial)
        if initial["status"] in TERMINAL:
            yield _sse("done", {})
            return

        frames = bus.subscribe(str(job_id))
        try:
            while True:
                try:
                    snapshot = await asyncio.wait_for(frames.__anext__(), timeout=POLL_SECONDS)
                except TimeoutError:
                    settled = await _current(job_id)
                    if settled and settled["status"] in TERMINAL:
                        yield _sse("snapshot", settled)
                        yield _sse("done", {})
                        return
                    # A comment line keeps the connection open without the
                    # client mistaking it for a frame.
                    yield ": waiting\n\n"
                    continue
                except StopAsyncIteration:
                    break

                yield _sse("snapshot", snapshot)
                if snapshot.get("status") in TERMINAL:
                    yield _sse("done", {})
                    return
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            yield _sse(
                "error",
                {"key": "events.stream_failed", "params": {"detail": str(exc)}},
            )
        finally:
            await frames.aclose()

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
async def job_trace(session: Session, user: CurrentUser, job_id: uuid.UUID) -> Response:
    job = await jobs_service.load_job(session, job_id)
    # Someone else's job is reported exactly like a missing one, so ids
    # cannot be probed to learn what other accounts have run.
    if job is None or job.user_id != user.id:
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
        "steps": [{**s, "artifacts": []} for s in jobs_service.step_records(job)],
    }
    return JSONResponse(
        document,
        headers={"Content-Disposition": f'attachment; filename="trace-{job.id}.json"'},
    )


@router.get("/{job_id}/result.geojson")
async def job_geojson(
    session: Session, user: CurrentUser, storage: StorageDep, job_id: uuid.UUID
) -> Response:
    """Vector outputs as a FeatureCollection.

    Only geometry that was actually produced appears here; an input with no
    coordinate system yields an empty collection rather than invented shapes.
    """
    job = await jobs_service.load_job(session, job_id)
    # Someone else's job is reported exactly like a missing one, so ids
    # cannot be probed to learn what other accounts have run.
    if job is None or job.user_id != user.id:
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

    # Boxes and regions the steps produced, already in WGS84. A SAR box keeps
    # its `status` ("unverified" unless corroborated) all the way to the map.
    from satsaathi_core.models import Artifact, ArtifactKind

    artifacts = await session.scalars(
        select(Artifact).where(
            Artifact.job_id == job.id, Artifact.kind == ArtifactKind.geojson
        )
    )
    for artifact in artifacts:
        try:
            collection = json.loads(storage.get(artifact.storage_key))
        except Exception:  # noqa: BLE001 - a missing file drops its features, not the map
            continue
        for feature in collection.get("features", []):
            feature.setdefault("properties", {})["step"] = (
                artifact.step_key.value if artifact.step_key else None
            )
            features.append(feature)

    return JSONResponse(
        {"type": "FeatureCollection", "features": features},
        headers={"Content-Disposition": f'attachment; filename="result-{job.id}.geojson"'},
    )
