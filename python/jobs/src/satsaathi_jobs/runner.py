"""Executing one job and broadcasting its progress.

This is the seam between the two deployments. The API can run a job in its
own process with `BackgroundTasks`, and a Celery worker can run it on another
machine entirely; both call `run_job`, so the resulting trace is the same
document either way.

Snapshots leave through an event bus rather than being written to the stream
directly, because the process serving a browser's `/events` connection is
often not the process running the job.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from satsaathi_core.db import session_scope
from satsaathi_core.events import EventBus, InProcessEventBus, RedisEventBus
from satsaathi_core.models import JobStatus
from satsaathi_core.settings import Settings, get_settings
from satsaathi_core.storage import Storage, build_storage

from . import service

#: Used when no broker is configured, so a developer without Redis still sees
#: a live trace. It only carries events within one process, and `event_bus`
#: says so in its second return value rather than pretending otherwise.
_fallback_bus = InProcessEventBus()
_redis_bus: RedisEventBus | None = None


def event_bus(settings: Settings) -> tuple[EventBus, bool]:
    """Return the bus to use and whether it reaches other processes."""
    global _redis_bus
    if settings.redis_url:
        if _redis_bus is None:
            _redis_bus = RedisEventBus(settings.redis_url)
        return _redis_bus, True
    return _fallback_bus, False


def build_job_storage(settings: Settings) -> Storage:
    return build_storage(
        settings.storage_backend,
        local_root=settings.storage_dir,
        bucket=settings.s3_bucket,
        offline=settings.is_offline,
    )


async def run_job(
    job_id: uuid.UUID,
    *,
    settings: Settings | None = None,
    storage: Storage | None = None,
) -> None:
    """Run the job to completion, publishing a snapshot after every step.

    Publishing happens on a separate task draining a queue, so a slow or dead
    broker delays nothing and fails nothing: the trace is persisted regardless,
    and a browser that missed frames recovers by re-reading the job.
    """
    settings = settings or get_settings()
    storage = storage or build_job_storage(settings)
    bus, _ = event_bus(settings)

    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def drain() -> None:
        while True:
            snapshot = await queue.get()
            if snapshot is None:
                return
            try:
                await bus.publish(str(job_id), snapshot)
            except Exception:  # noqa: BLE001
                # A dead broker must not fail the job; the trace is persisted.
                pass

    drainer = asyncio.create_task(drain())
    try:
        async with session_scope() as session:
            job = await service.load_job(session, job_id)
            if job is None:
                return
            try:
                await service.execute(
                    session,
                    job,
                    storage=storage,
                    settings=settings,
                    # Every frame leaves in the job shape, so the client never
                    # has to tell a trace document from a job document.
                    publish=lambda snap: queue.put_nowait(
                        service.snapshot_for_stream(job, snap)
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                job.status = JobStatus.failed
                job.error = {"key": "job.failed", "params": {"detail": str(exc)}}
    finally:
        queue.put_nowait(None)
        await drainer


#: One event loop per process, reused for every job that process runs.
_loop: asyncio.AbstractEventLoop | None = None


def worker_loop() -> asyncio.AbstractEventLoop:
    """The process's long-lived loop.

    `asyncio.run` per task looks tidier and is wrong here: the SQLAlchemy
    engine is cached per process and its asyncpg connections are bound to the
    loop that opened them. Closing that loop after the first job leaves the
    pool holding sockets attached to nothing, and the second job dies inside
    the driver with `'NoneType' object has no attribute 'send'`.

    This assumes one loop per process, which holds for Celery's solo and
    prefork pools. A threaded pool would need a loop per thread.
    """
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop


def close_worker_loop() -> None:
    """Dispose the engine and close the loop, at process shutdown."""
    global _loop
    if _loop is None or _loop.is_closed():
        return
    from satsaathi_core.db import dispose_engine

    try:
        _loop.run_until_complete(dispose_engine())
    finally:
        _loop.close()
        _loop = None


def run_job_blocking(job_id: str | uuid.UUID) -> None:
    """Synchronous entry point, for callers with no event loop of their own.

    Celery tasks are ordinary functions; this gives them one to call.
    """
    worker_loop().run_until_complete(run_job(uuid.UUID(str(job_id))))
