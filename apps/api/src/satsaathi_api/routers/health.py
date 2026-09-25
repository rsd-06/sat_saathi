from __future__ import annotations

import asyncio
from typing import Literal

import httpx
import redis.asyncio as redis_asyncio
from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from satsaathi_core.db import get_engine
from satsaathi_core.settings import Settings, get_settings

router = APIRouter()


class CheckResult(BaseModel):
    #: "skipped" is for a dependency this deployment does not use. It is not a
    #: failure, and does not make the service degraded.
    status: Literal["ok", "error", "skipped"]
    detail: str | None = None


class HealthResponse(BaseModel):
    mode: str
    status: Literal["ok", "degraded"]
    checks: dict[str, CheckResult]


async def check_database(settings: Settings) -> CheckResult:
    """Ask the pool, not a fresh connection.

    A new connection to a hosted database is TCP, then TLS, then SCRAM — one
    to five seconds from here. The health check runs on every page that shows
    the connectivity badge, and opening a connection each time made it the
    slowest thing on the page while also spending the free tier's connection
    limit. The pool answers the question that matters: can the app reach its
    database right now.
    """
    try:
        async with get_engine().connect() as conn:
            await asyncio.wait_for(conn.execute(text("SELECT 1")), timeout=5)
        return CheckResult(status="ok")
    except Exception as exc:
        return CheckResult(status="error", detail=str(exc))


async def check_redis(settings: Settings) -> CheckResult:
    """Redis is optional: without it, jobs run inline and events stay in-process.

    The client used to be built before the try, so an unset URL raised out of
    the health endpoint and took the connectivity badge and the settings page
    down with it.
    """
    if not settings.redis_url:
        return CheckResult(status="skipped", detail="not configured")
    try:
        client = redis_asyncio.from_url(settings.redis_url, socket_connect_timeout=2)
    except Exception as exc:
        return CheckResult(status="error", detail=str(exc))
    try:
        await client.ping()
        return CheckResult(status="ok")
    except Exception as exc:
        return CheckResult(status="error", detail=str(exc))
    finally:
        await client.aclose()


async def check_storage(settings: Settings) -> CheckResult:
    try:
        settings.storage_dir.mkdir(parents=True, exist_ok=True)
        probe = settings.storage_dir / ".health-probe"
        probe.write_text("ok")
        probe.unlink()
        return CheckResult(status="ok")
    except Exception as exc:
        return CheckResult(status="error", detail=str(exc))


async def check_tiler(settings: Settings) -> CheckResult:
    if not settings.tiler_url:
        return CheckResult(status="skipped", detail="not configured")
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            response = await client.get(settings.tiler_url)
        if response.status_code < 500:
            return CheckResult(status="ok")
        return CheckResult(status="error", detail=f"HTTP {response.status_code}")
    except Exception as exc:
        return CheckResult(status="error", detail=str(exc))


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    names = ("database", "redis", "storage", "tiler")
    checkers = (check_database, check_redis, check_storage, check_tiler)
    results = await asyncio.gather(*(checker(settings) for checker in checkers))
    checks: dict[str, CheckResult] = dict(zip(names, results))
    overall: Literal["ok", "degraded"] = (
        "ok" if all(c.status != "error" for c in checks.values()) else "degraded"
    )
    return HealthResponse(mode=settings.mode, status=overall, checks=checks)


# -- liveness and readiness ---------------------------------------------------


class LiveResponse(BaseModel):
    status: Literal["live"] = "live"


class ReadyCheck(BaseModel):
    ok: bool
    #: Message key naming what is wrong; None when ok.
    key: str | None = None
    params: dict = {}


class ReadyResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    failing: list[str]
    checks: dict[str, ReadyCheck]


@router.get("/health/live", response_model=LiveResponse)
async def live() -> LiveResponse:
    """The process is up. No dependency is touched, so it is always fast."""
    return LiveResponse()


def _migrations_head() -> str | None:
    from pathlib import Path

    from alembic.script import ScriptDirectory

    import satsaathi_core

    folder = Path(satsaathi_core.__file__).resolve().parents[2] / "migrations"
    if not folder.is_dir():
        return None
    return ScriptDirectory(str(folder)).get_current_head()


async def ready_database(settings: Settings) -> ReadyCheck:
    try:
        conn = await asyncpg.connect(dsn=settings.database_url_asyncpg_dsn, timeout=2)
    except Exception as exc:  # noqa: BLE001
        return ReadyCheck(ok=False, key="health.database_unreachable", params={"detail": str(exc)})
    try:
        try:
            current = await conn.fetchval("SELECT version_num FROM alembic_version")
        except Exception:  # noqa: BLE001 - no table means never migrated
            current = None
    finally:
        await conn.close()
    head = _migrations_head()
    if head is None:
        return ReadyCheck(ok=False, key="health.migrations_unknown")
    if current != head:
        return ReadyCheck(
            ok=False, key="health.migrations_behind", params={"current": current, "head": head}
        )
    return ReadyCheck(ok=True)


async def ready_redis(settings: Settings) -> ReadyCheck:
    result = await check_redis(settings)
    if result.status == "ok":
        return ReadyCheck(ok=True)
    return ReadyCheck(ok=False, key="health.redis_unreachable", params={"detail": result.detail})


def required_queues(settings: Settings) -> list[str]:
    """Queues that must have a live consumer for jobs to finish.

    With inline dispatch the API runs jobs itself and needs no worker. With
    Celery, the CPU queue always needs one, and the GPU queue does as soon as
    any GPU model is usable here — otherwise its jobs would wait for ever.
    """
    if settings.job_dispatch != "celery":
        return []
    from satsaathi_models import ModelCatalog

    queues = ["cpu"]
    catalog = ModelCatalog(settings.models_dir)
    if any(s.available and s.spec.queue == "gpu" for s in catalog.all_status()):
        queues.append("gpu")
    return queues


async def ready_queues(settings: Settings) -> dict[str, ReadyCheck]:
    from ..heartbeat import queue_consumers

    wanted = required_queues(settings)
    if not wanted:
        return {}
    alive = await queue_consumers(settings.redis_url, wanted)
    return {
        f"queue_{q}": (
            ReadyCheck(ok=True)
            if alive[q]
            else ReadyCheck(ok=False, key=f"health.{q}_worker_missing")
        )
        for q in wanted
    }


@router.get(
    "/health/ready",
    response_model=ReadyResponse,
    responses={503: {"model": ReadyResponse}},
)
async def ready():
    """Ready to take a job end to end: 200, or 503 naming what is not."""
    from fastapi.responses import JSONResponse

    settings = get_settings()
    database, redis_check, queues = await asyncio.gather(
        ready_database(settings), ready_redis(settings), ready_queues(settings)
    )
    checks: dict[str, ReadyCheck] = {"database": database, "redis": redis_check, **queues}
    failing = [c.key for c in checks.values() if not c.ok and c.key]
    body = ReadyResponse(
        status="not_ready" if failing else "ready", failing=failing, checks=checks
    )
    return JSONResponse(body.model_dump(), status_code=503 if failing else 200)


class PublicConfig(BaseModel):
    """Server settings the interface must not guess at."""

    mode: str
    #: Answers below this confidence are held for review, as a percentage.
    review_threshold_pct: int
    max_upload_mb: int
    google_sign_in: bool


@router.get("/config", response_model=PublicConfig)
async def public_config() -> PublicConfig:
    settings = get_settings()
    return PublicConfig(
        mode=settings.mode,
        review_threshold_pct=round(settings.confidence_threshold * 100),
        max_upload_mb=settings.max_upload_mb,
        google_sign_in=settings.google_sign_in_enabled,
    )
