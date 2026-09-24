"""Creating a job, running it, and persisting the trace.

The runner is the same one the tests exercise; this module only adds
persistence and event publishing around it. Running inline versus on a Celery
worker is a deployment choice, not a behavioural one — both call `execute`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from satsaathi_core.indices import available_indices
from satsaathi_core.models import (
    Artifact,
    ArtifactKind,
    Asset,
    InputSet,
    InputSetAsset,
    Job,
    JobStatus,
    JobStep,
    ReviewItem,
    StepKey,
    StepStatus,
)
from satsaathi_core.settings import Settings
from satsaathi_core.storage import Storage
from satsaathi_tools import pipeline
from satsaathi_tools.builtin import build_default_registry
from satsaathi_tools.protocol import ToolContext
from satsaathi_tools.registry import (
    STEP_KEYS,
    PlannedStep,
    effective_sensor,
    plan,
    queue_for,
)

STEP_ORDER = {key: i for i, key in enumerate(STEP_KEYS)}


def build_registry(settings: Settings):
    """The tool registry for this machine, models and all.

    Built fresh per call rather than cached, because the API and the worker
    both use it and a worker that has just had weights installed should see
    them on its next job rather than its next restart.
    """
    from satsaathi_models import ModelCatalog

    return build_default_registry(ModelCatalog(settings.models_dir))


async def plan_job(
    session: AsyncSession, job: Job, *, storage: Storage, settings: Settings
) -> tuple[list, str]:
    """Classify the question and choose a plan, before anything is dispatched.

    Planning at creation rather than inside the worker buys two things: the
    interface can show the whole plan the moment a job exists, and the
    dispatcher knows which queue the job needs — a plan with a GPU step must
    not be handed to a CPU worker that would only discover that at the step.

    Returns the plan and the queue it must run on.
    """
    registry = build_registry(settings)
    inputs, _summary, mode = await _gather_inputs(session, job, storage)

    unavailable = available_indices(inputs.get("band_map") or {})
    available = [n for n in ("ndvi", "ndwi", "lswi") if n not in unavailable]

    ctx = ToolContext(
        job_id=str(job.id), storage=storage, settings=settings, inputs=inputs
    )
    intent_tool = registry.get("intent.keyword")
    intent = intent_tool.run(
        {"question": job.query_text}, intent_tool.validate_params({}), ctx
    ).output_summary["intent"]

    planned = plan(
        intent,
        mode,
        available_indices=available,
        sensor=inputs.get("sensor_type"),
        vlm_indices=_readable_indices(registry, inputs.get("band_map") or {}),
    )
    job.intent = intent
    job.plan = [
        {"step_key": s.step_key, "tool": s.tool_name, "params": s.params}
        for s in planned
    ]
    await session.flush()
    return planned, queue_for(planned, registry)


def _readable_indices(registry, band_map: dict[str, int]) -> list[str]:
    """Indices whose reading adapter is installed and can see its training inputs.

    The index adapters were trained on a true-colour image next to the index
    map, so they need blue, green and red besides the index's own bands (and
    SWIR for NDWI's MNDWI line). Bands are never substituted: without them,
    the question goes to the optical adapter instead.
    """
    from satsaathi_core.index_contract import INDEX_ROLES

    out = []
    for index, tool_name in (("ndvi", "vlm.index.ndvi"), ("ndwi", "vlm.index.ndwi")):
        if tool_name not in registry or registry.get(tool_name).is_stub:
            continue
        if all(role in band_map for role in INDEX_ROLES[index.upper()]):
            out.append(index)
    return out


async def create_job(
    session: AsyncSession,
    *,
    input_set_id: uuid.UUID,
    query_text: str,
    query_lang: str,
    ui_lang: str,
) -> Job:
    """Create the job and its eight pending steps in one transaction.

    The steps exist before anything runs so the UI can render the whole
    sequence immediately, greyed out, rather than growing it a row at a time.
    """
    job = Job(
        input_set_id=input_set_id,
        query_text=query_text,
        query_lang=query_lang,
        ui_lang=ui_lang,
        status=JobStatus.queued,
    )
    session.add(job)
    await session.flush()

    for ordinal, key in enumerate(STEP_KEYS):
        session.add(
            JobStep(
                job_id=job.id,
                step_key=StepKey(key),
                ordinal=ordinal,
                status=StepStatus.pending,
            )
        )
    await session.flush()
    return job


async def load_job(session: AsyncSession, job_id: uuid.UUID) -> Job | None:
    result = await session.scalars(
        select(Job).where(Job.id == job_id).options(selectinload(Job.steps))
    )
    return result.first()


async def _gather_inputs(
    session: AsyncSession, job: Job, storage: Storage
) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Assemble what the tools need, plus the trace's input-set summary."""
    result = await session.scalars(
        select(InputSet)
        .where(InputSet.id == job.input_set_id)
        .options(selectinload(InputSet.assets).selectinload(InputSetAsset.asset))
    )
    input_set = result.first()
    if input_set is None:
        raise ValueError("input set missing")

    by_role: dict[str, Asset] = {a.role.value: a.asset for a in input_set.assets}
    primary = (
        by_role.get("single")
        or by_role.get("optical")
        or by_role.get("after")
        or next(iter(by_role.values()))
    )

    inputs: dict[str, Any] = {
        "question": job.query_text,
        "path": storage.local_path(primary.storage_key),
        "band_map": primary.band_map or {},
        "sensor_type": effective_sensor(primary.sensor_type, primary.band_map),
        # Every image by role, so a pair step reads both dates or both
        # sensors rather than only the primary one.
        "assets": {
            role: {
                "path": storage.local_path(asset.storage_key),
                "band_map": asset.band_map or {},
                "sensor_type": effective_sensor(asset.sensor_type, asset.band_map),
                "crs": asset.crs,
                "width": asset.width,
                "height": asset.height,
            }
            for role, asset in by_role.items()
        },
    }
    summary = {
        "mode": input_set.mode.value,
        "assets": [
            {
                "role": role,
                "filename": asset.filename,
                "crs": asset.crs,
                "width": asset.width,
                "height": asset.height,
                "bands": len(asset.bands or []),
                "sensor_type": asset.sensor_type,
                "acquired_at": (
                    asset.acquired_at.isoformat() if asset.acquired_at else None
                ),
            }
            for role, asset in by_role.items()
        ],
    }
    return inputs, summary, input_set.mode.value


def _intent_of(trace: pipeline.Trace) -> str | None:
    for step in trace.steps:
        if step.step_key == "understand":
            return step.output_summary.get("intent")
    return None


async def execute(
    session: AsyncSession,
    job: Job,
    *,
    storage: Storage,
    settings: Settings,
    publish=None,
) -> pipeline.Trace:
    """Run the job's plan and write every step back as it settles.

    The plan was chosen when the job was created, so the worker executes a
    decision rather than making one. Re-planning here could pick a different
    route than the one the interface already showed, and than the one the
    queue was chosen for.
    """
    registry = build_registry(settings)
    inputs, input_summary, _mode = await _gather_inputs(session, job, storage)

    ctx = ToolContext(
        job_id=str(job.id), storage=storage, settings=settings, inputs=inputs
    )

    if job.plan:
        planned = [
            PlannedStep(row["step_key"], row["tool"], row.get("params") or {})
            for row in job.plan
        ]
        intent = job.intent or "land_cover"
    else:
        # A job created before plans were stored, or by a caller that skipped
        # planning. Plan it now rather than refusing to run it.
        planned, _queue = await plan_job(
            session, job, storage=storage, settings=settings
        )
        intent = job.intent or "land_cover"

    job.status = JobStatus.running
    await session.flush()

    emitted: list[dict[str, Any]] = []

    def emit(snapshot: dict[str, Any]) -> None:
        emitted.append(snapshot)
        if publish is not None:
            publish(snapshot)

    trace = pipeline.run(
        job_id=str(job.id),
        plan=planned,
        registry=registry,
        ctx=ctx,
        inputs={**inputs, "planned_index": next(
            (s.params.get("index") for s in planned if s.step_key == "compute"), None
        )},
        query={
            "text": job.query_text,
            "lang": job.query_lang,
            "ui_lang": job.ui_lang,
            "intent": intent,
        },
        input_set=input_summary,
        emit=emit,
        confidence_threshold=settings.confidence_threshold,
        stub_delay_ms=settings.stub_delay_ms,
    )

    await _persist(session, job, trace, settings)
    return trace


async def _persist(
    session: AsyncSession, job: Job, trace: pipeline.Trace, settings: Settings
) -> None:
    rows = await session.scalars(select(JobStep).where(JobStep.job_id == job.id))
    by_key = {row.step_key.value: row for row in rows}

    for record in trace.steps:
        row = by_key.get(record.step_key)
        if row is None:
            continue
        row.status = StepStatus(record.status)
        row.tool_name = record.tool_name
        row.tool_version = record.tool_version
        row.is_stub = record.is_stub
        row.params = record.params
        row.output_summary = record.output_summary
        row.note = record.note
        row.error = record.error
        row.duration_ms = record.duration_ms
        if record.started_at:
            row.started_at = datetime.fromisoformat(record.started_at)
        if record.finished_at:
            row.finished_at = datetime.fromisoformat(record.finished_at)

    # Files a step wrote (box GeoJSON, for one) are recorded once per job, so
    # a re-run rewrites them rather than piling up duplicates.
    old = await session.scalars(select(Artifact).where(Artifact.job_id == job.id))
    for artifact in old:
        await session.delete(artifact)
    for record in trace.steps:
        for art in record.artifacts:
            session.add(
                Artifact(
                    job_id=job.id,
                    step_key=StepKey(record.step_key),
                    kind=ArtifactKind(art["kind"]),
                    name=art["name"],
                    storage_key=art["storage_key"],
                    meta=art.get("meta") or {},
                )
            )

    job.confidence = trace.confidence
    job.answer = trace.answer
    job.status = JobStatus(trace.status)
    job.finished_at = datetime.now(UTC)

    failed = next((s for s in trace.steps if s.status == "failed"), None)
    job.error = failed.error if failed else None

    if trace.status == JobStatus.needs_review.value:
        existing = await session.scalars(
            select(ReviewItem).where(ReviewItem.job_id == job.id)
        )
        if existing.first() is None:
            session.add(
                ReviewItem(
                    job_id=job.id,
                    reason="confidence.below_threshold",
                )
            )

    await session.flush()


def trace_to_dict(trace: pipeline.Trace) -> dict[str, Any]:
    return trace.to_dict()


def snapshot_for_stream(job: Job, snapshot: dict[str, Any]) -> dict[str, Any]:
    """Reshape a pipeline snapshot into the job shape the API otherwise serves.

    The stream would otherwise carry two different documents — a job for the
    first frame and a raw trace for every later one — leaving the client to
    guess which identifier field it has. One shape, always.
    """
    return {
        "id": str(job.id),
        "input_set_id": str(job.input_set_id),
        "query_text": job.query_text,
        "query_lang": job.query_lang,
        "ui_lang": job.ui_lang,
        "intent": snapshot.get("query", {}).get("intent"),
        "status": snapshot.get("status"),
        "confidence": snapshot.get("confidence"),
        "answer": snapshot.get("answer"),
        "error": None,
        "steps": snapshot.get("steps", []),
        "artifacts": [],
        "created_at": job.created_at.isoformat(),
        "finished_at": None,
    }


def step_records(job: Job) -> list[dict[str, Any]]:
    """Step rows as plain JSON.

    Timestamps leave as ISO strings: this feeds both the trace export, which
    is serialised straight to JSON, and the response model, which parses them
    back into datetimes.
    """

    def iso(value: datetime | None) -> str | None:
        return value.isoformat() if value else None

    return [
        {
            "step_key": s.step_key.value,
            "ordinal": s.ordinal,
            "status": s.status.value,
            "tool_name": s.tool_name,
            "tool_version": s.tool_version,
            "is_stub": s.is_stub,
            "params": s.params or {},
            "output_summary": s.output_summary or {},
            "note": s.note,
            "error": s.error,
            "started_at": iso(s.started_at),
            "finished_at": iso(s.finished_at),
            "duration_ms": s.duration_ms,
        }
        for s in sorted(job.steps, key=lambda s: s.ordinal)
    ]
