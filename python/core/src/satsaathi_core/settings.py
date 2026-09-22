from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    mode: str = Field(default="online", validation_alias="SATSAATHI_MODE")
    database_url: str = "postgresql+asyncpg://satsaathi:satsaathi@localhost:5432/satsaathi"
    redis_url: str = "redis://localhost:6379/0"
    storage_dir: Path = Path("./.data/storage")
    tiler_url: str = "http://localhost:8001"

    @property
    def database_url_asyncpg_dsn(self) -> str:
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
