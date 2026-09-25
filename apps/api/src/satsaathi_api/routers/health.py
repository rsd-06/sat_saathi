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
