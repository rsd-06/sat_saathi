"""Async engine and session handling.

One engine per process, created lazily so importing this module never opens a
connection — the API's health check and the test suite both import it without
a database being up.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .settings import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        settings.effective_database_url,
        connect_args=settings.asyncpg_connect_args(),
        pool_pre_ping=True,
        # A hosted free tier caps connections well below what a local Postgres
        # allows. Five per process plus a small burst keeps the API and a
        # worker inside it together.
        pool_size=5,
        max_overflow=5,
        # Hosted poolers drop idle connections. Recycling first means a quiet
        # evening does not end in a burst of connection-reset errors.
        pool_recycle=300,
        future=True,
    )


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        get_engine(), expire_on_commit=False, class_=AsyncSession
    )


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """A transaction that commits on success and rolls back on failure."""
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency. Commits when the request handler returns."""
    async with session_scope() as session:
        yield session


async def dispose_engine() -> None:
    engine = get_engine()
    await engine.dispose()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
