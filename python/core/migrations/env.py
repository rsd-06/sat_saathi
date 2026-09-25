"""Alembic environment.

Runs migrations on asyncpg, the driver the app itself uses, through
run_sync. psycopg was simpler here but its compiled extension can be blocked
by Windows Application Control, which stopped migrations dead.

GeoAlchemy2's alembic_helpers keep autogenerate from trying to re-create the
spatial indexes and geometry columns PostGIS manages itself.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from geoalchemy2 import alembic_helpers
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from satsaathi_core.models import Base
from satsaathi_core.settings import get_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


#: PostGIS installs its own tables (topology, layer, and the whole tiger
#: geocoder) into the same database. Autogenerate sees them as tables the
#: models no longer declare and will happily emit DROP statements that break
#: the extension, so comparison is restricted to the tables we define.
_OURS = frozenset(Base.metadata.tables)
_FOREIGN_SCHEMAS = {"tiger", "tiger_data", "topology"}


def _include_object(obj, name, type_, reflected, compare_to):
    schema = getattr(obj, "schema", None)
    if schema in _FOREIGN_SCHEMAS:
        return False
    if type_ == "table":
        # Only our own tables participate; anything reflected that we do not
        # declare is somebody else's and is left strictly alone.
        return name in _OURS
    parent = getattr(obj, "table", None)
    if parent is not None and parent.name not in _OURS:
        return False
    return alembic_helpers.include_object(obj, name, type_, reflected, compare_to)


def _sync_url() -> str:
    # The app runs on asyncpg; migrations run synchronously on psycopg.
    return get_settings().sync_database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_sync_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=_include_object,
        process_revision_directives=alembic_helpers.writer,
        render_item=alembic_helpers.render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_sync(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=_include_object,
        process_revision_directives=alembic_helpers.writer,
        render_item=alembic_helpers.render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async() -> None:
    settings = get_settings()
    engine = create_async_engine(
        settings.effective_database_url,
        poolclass=pool.NullPool,
        connect_args=settings.asyncpg_connect_args(),
    )
    async with engine.connect() as connection:
        await connection.run_sync(_run_sync)
    await engine.dispose()


def run_migrations_online() -> None:
    # asyncpg, the same driver the app uses. Migrations used to run on psycopg,
    # whose compiled extension Windows Application Control can block outright;
    # one driver for everything means one thing that has to load.
    asyncio.run(_run_async())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
