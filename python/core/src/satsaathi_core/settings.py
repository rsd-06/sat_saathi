from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: python/core/src/satsaathi_core/settings.py -> the repository root. The same
#: depth holds inside the Docker images, which copy the tree as-is.
REPO_ROOT = Path(__file__).resolve().parents[4]

#: Hosts that mean "the Postgres on this machine or in this compose stack".
#: Anything else is treated as remote and gets TLS.
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "postgres", ""}


class Settings(BaseSettings):
    # One secrets file for the whole repository, at its root, read by absolute
    # path so it does not depend on which directory a process started in.
    # Real environment variables still win, which is what lets the test suite
    # and the compose stack point somewhere else without editing the file.
    # `.env` is deliberately not read: it holds compose's container hostnames,
    # which do not resolve from a process running on the host.
    model_config = SettingsConfigDict(
        extra="ignore",
        env_file=REPO_ROOT / ".env.local",
        env_file_encoding="utf-8",
    )

    mode: Literal["online", "offline"] = Field(
        default="online", validation_alias="SATSAATHI_MODE"
    )
    #: The Postgres from infra/compose. Always there when Docker is, and the
    #: only database offline mode will use.
    local_database_url: str = (
        "postgresql+asyncpg://satsaathi:satsaathi_dev_password@localhost:5432/satsaathi"
    )
    #: A hosted database, such as Supabase. Empty means use the local one.
    database_url: str = ""
    redis_url: str = "redis://localhost:6379/0"
    storage_dir: Path = Path("./.data/storage")
    #: Where model weights live. Kept out of storage: rasters are user
    #: data and get backed up and cleared, weights are part of the build.
    models_dir: Path = Path("./.data/models")
    tiler_url: str = "http://localhost:8001"

    storage_backend: Literal["local", "s3"] = "local"
    s3_bucket: str | None = None

    #: Answers scoring below this are held for a specialist instead of shown.
    confidence_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    max_upload_mb: int = Field(default=512, gt=0)
    #: Rasters larger than this are not index-computed inline.
    max_index_pixels: int = Field(default=4096 * 4096, gt=0)
    pair_min_overlap_pct: float = Field(default=90.0, ge=0.0, le=100.0)
    #: Artificial delay per stub step, so the live trace can be watched.
    stub_delay_ms: int = Field(default=0, ge=0)

    #: Where a job runs. "inline" needs no broker and is the default so a
    #: checkout runs with one command; "celery" hands the job to a worker.
    job_dispatch: Literal["inline", "celery"] = "inline"

    translation_provider: Literal["passthrough", "indictrans2", "bhashini"] = (
        "passthrough"
    )
    llm_provider: Literal["stub", "ollama"] = "stub"

    #: Google OAuth. The API needs only the client id, as the audience it will
    #: accept in an ID token; the secret belongs to whoever exchanges codes.
    #: Empty means Google sign-in is off, and the API refuses such tokens
    #: rather than skipping the audience check.
    google_client_id: str = ""

    @property
    def google_sign_in_enabled(self) -> bool:
        return bool(self.google_client_id)

    @property
    def is_offline(self) -> bool:
        return self.mode == "offline"

    @field_validator("database_url", "local_database_url")
    @classmethod
    def _asyncpg_driver(cls, value: str) -> str:
        """Accept a URL as the provider prints it, and name our driver.

        Supabase and most hosts hand out `postgresql://` or `postgres://`.
        SQLAlchemy would pick psycopg for those; the app runs on asyncpg.
        """
        value = value.strip()
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+asyncpg://" + value[len(prefix) :]
        return value

    @property
    def effective_database_url(self) -> str:
        """The database this process actually uses.

        Offline mode always uses the local one, whatever else is configured:
        offline means no network, and a hosted database is the network.
        """
        if self.is_offline or not self.database_url:
            return self.local_database_url
        return self.database_url

    @property
    def database_host(self) -> str:
        return urlsplit(self.effective_database_url).hostname or ""

    @property
    def database_is_remote(self) -> bool:
        return self.database_host not in _LOCAL_HOSTS

    @property
    def _uses_transaction_pooler(self) -> bool:
        # Supabase's transaction-mode pooler listens on 6543. It hands each
        # statement to whichever backend is free, so a prepared statement made
        # on one connection is gone on the next.
        return urlsplit(self.effective_database_url).port == 6543

    def asyncpg_connect_args(self) -> dict[str, Any]:
        """Driver options for asyncpg, used by the app and the health check."""
        args: dict[str, Any] = {
            # asyncpg waits 60s for a connection by default. A database that
            # cannot be reached should say so in seconds, not leave someone
            # watching a sign-in button for a minute.
            "timeout": 10,
            # And no single statement should hold a request longer than this.
            "command_timeout": 30,
        }
        if self.database_is_remote:
            # A hosted database must not be spoken to in the clear.
            args["ssl"] = "require"
        if self._uses_transaction_pooler:
            args["statement_cache_size"] = 0
        return args

    def psycopg_connect_args(self) -> dict[str, Any]:
        """The same intent, spelled the way psycopg wants, for migrations."""
        args: dict[str, Any] = {}
        if self.database_is_remote:
            args["sslmode"] = "require"
        if self._uses_transaction_pooler:
            args["prepare_threshold"] = None
        return args

    @property
    def sync_database_url(self) -> str:
        """For Alembic, which runs synchronously on psycopg."""
        return self.effective_database_url.replace("+asyncpg", "+psycopg", 1)

    @property
    def database_url_asyncpg_dsn(self) -> str:
        return self.effective_database_url.replace(
            "postgresql+asyncpg://", "postgresql://", 1
        )

    def assert_provider_allowed(self, provider: str) -> None:
        """Offline mode must not reach the network, so online-only providers
        are refused at startup rather than failing mid-job."""
        online_only = {"bhashini"}
        if self.is_offline and provider in online_only:
            raise ValueError(
                f"provider {provider!r} needs a network connection and "
                f"SATSAATHI_MODE is offline"
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
