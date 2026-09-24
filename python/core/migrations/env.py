"""Alembic environment.

Runs migrations synchronously against a psycopg-style URL derived from the
async one in settings: migrations are a one-shot operation and gain nothing
from an async driver, while asyncpg would force a run_sync dance here.

GeoAlchemy2's alembic_helpers keep autogenerate from trying to re-create the
spatial indexes and geometry columns PostGIS manages itself.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from geoalchemy2 import alembic_helpers
from sqlalchemy import engine_from_config, pool

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


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _sync_url()

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        # TLS for a hosted database, spelled the way psycopg wants it.
        connect_args=get_settings().psycopg_connect_args(),
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=_include_object,
            process_revision_directives=alembic_helpers.writer,
            render_item=alembic_helpers.render_item,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
