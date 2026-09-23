"""Shared request dependencies and error helpers."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from satsaathi_core.db import get_session
from satsaathi_core.settings import Settings, get_settings
from satsaathi_core.storage import Storage, build_storage
from satsaathi_tools.builtin import build_default_registry
from satsaathi_tools.registry import Registry

Session = Annotated[AsyncSession, Depends(get_session)]


def settings_dep() -> Settings:
    return get_settings()


SettingsDep = Annotated[Settings, Depends(settings_dep)]

_registry: Registry | None = None


def registry_dep() -> Registry:
    global _registry
    if _registry is None:
        _registry = build_default_registry()
    return _registry


RegistryDep = Annotated[Registry, Depends(registry_dep)]

_storage: Storage | None = None


def storage_dep(settings: SettingsDep) -> Storage:
    global _storage
    if _storage is None:
        _storage = build_storage(
            settings.storage_backend,
            local_root=settings.storage_dir,
            bucket=settings.s3_bucket,
            offline=settings.is_offline,
        )
    return _storage


StorageDep = Annotated[Storage, Depends(storage_dep)]


def api_error(
    status: int, key: str, **params: Any
) -> HTTPException:
    """Errors travel as a message key plus params; the frontend localises."""
    return HTTPException(
        status_code=status, detail={"error": {"key": key, "params": params}}
    )
