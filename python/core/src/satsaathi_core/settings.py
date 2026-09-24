from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    mode: Literal["online", "offline"] = Field(
        default="online", validation_alias="SATSAATHI_MODE"
    )
    database_url: str = "postgresql+asyncpg://satsaathi:satsaathi@localhost:5432/satsaathi"
    redis_url: str = "redis://localhost:6379/0"
    storage_dir: Path = Path("./.data/storage")
    #: Where model weights live. Kept out of storage: rasters are user
    #: data and get backed up and cleared, weights are part of the build.
    models_dir: Path = Path("./.data/models")
    tiler_url: str = "http://localhost:8001"

    storage_backend: Literal["local", "s3"] = "local"
    s3_bucket: str | None = None

    #: Answers scoring below this are held for a specialist instead of shown.
    #: Applies to measured-only answers; model answers use the pair below.
    confidence_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    #: Model answers: confidence = held-out prior x token-probability signal
    #: (x agreement, for fusion). At or above `high` is shown as confident;
    #: below `low` is held for review; between is shown as medium.
    confidence_high: float = Field(default=0.6, ge=0.0, le=1.0)
    confidence_low: float = Field(default=0.35, ge=0.0, le=1.0)
    #: Re-sample twice at temperature 0.7 for a consistency signal. Triples
    #: GPU time per answer, so off unless asked for.
    vlm_resample: bool = Field(default=False, validation_alias="SATSAATHI_VLM_RESAMPLE")
    vlm_max_new_tokens: int = Field(default=256, gt=0, le=2048)

    #: GPU worker: load the model at worker start instead of on first use.
    preload_models: bool = Field(default=False, validation_alias="SATSAATHI_PRELOAD")
    #: Free the GPU and RAM after this many idle minutes; 0 keeps it resident.
    model_idle_unload_min: float = Field(
        default=20, ge=0, validation_alias="SATSAATHI_MODEL_IDLE_UNLOAD_MIN"
    )
    #: Enables operator-only endpoints such as model self-tests.
    debug: bool = Field(default=False, validation_alias="SATSAATHI_DEBUG")
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

    @property
    def is_offline(self) -> bool:
        return self.mode == "offline"

    @property
    def database_url_asyncpg_dsn(self) -> str:
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)

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
