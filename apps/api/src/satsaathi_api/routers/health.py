from __future__ import annotations

import asyncio
from typing import Literal

import asyncpg
import httpx
import redis.asyncio as redis_asyncio
from fastapi import APIRouter
from pydantic import BaseModel

from satsaathi_core.settings import Settings, get_settings

router = APIRouter()


class CheckResult(BaseModel):
    status: Literal["ok", "error"]
    detail: str | None = None


class HealthResponse(BaseModel):
    mode: str
    status: Literal["ok", "degraded"]
    checks: dict[str, CheckResult]


async def check_database(settings: Settings) -> CheckResult:
    try:
        conn = await asyncpg.connect(dsn=settings.database_url_asyncpg_dsn, timeout=2)
        try:
            await conn.fetchval("SELECT 1")
        finally:
            await conn.close()
        return CheckResult(status="ok")
    except Exception as exc:
        return CheckResult(status="error", detail=str(exc))


async def check_redis(settings: Settings) -> CheckResult:
    client = redis_asyncio.from_url(settings.redis_url, socket_connect_timeout=2)
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
    checks = dict(zip(names, results))
    overall: Literal["ok", "degraded"] = (
        "ok" if all(c.status == "ok" for c in checks.values()) else "degraded"
    )
    return HealthResponse(mode=settings.mode, status=overall, checks=checks)
