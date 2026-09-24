"""What this deployment can actually run.

The settings screen needs a straight answer to "is this thing measuring or
guessing?", and so does anyone reading a trace. This reports every model the
system knows about and whether its weights are on the machine serving the
request — never a capability list that assumes the happy case.

Which models are *resident* is the GPU worker's to say. It publishes a
heartbeat to Redis; this router reads it and never imports torch.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, status

from ..deps import CatalogDep, RegistryDep, SettingsDep, api_error
from ..heartbeat import gpu_heartbeat
from ..routers.auth import CurrentUser
from ..schemas import (
    ErrorBody,
    ModelOut,
    ModelsOut,
    RuntimeOut,
    SelftestCheck,
    SelftestOut,
    SelftestStarted,
)

router = APIRouter(prefix="/models", tags=["models"])

SELFTEST_TASK = "satsaathi.model_selftest"


def _loaded(status_row: Any, beat: dict[str, Any] | None, all_rows: dict[str, Any]) -> bool | None:
    if beat is None:
        return None
    spec = status_row.spec
    adapters = set(beat.get("adapters_loaded") or [])
    base_loaded = bool(beat.get("base_loaded"))
    if spec.kind == "hf_base":
        return base_loaded
    if spec.kind == "lora_adapter":
        return base_loaded and spec.name in adapters
    if spec.kind == "composite":
        return all(
            _loaded(all_rows[u], beat, all_rows) for u in spec.uses if u in all_rows
        )
    if spec.kind == "classical":
        return True
    return False


@router.get("", response_model=ModelsOut)
async def list_models(
    catalog: CatalogDep, registry: RegistryDep, settings: SettingsDep
) -> ModelsOut:
    beat = await gpu_heartbeat(settings.redis_url)
    statuses = catalog.all_status()
    by_name = {s.spec.name: s for s in statuses}
    rows = [
        ModelOut(
            name=s.spec.name,
            task=s.spec.task,
            revision=s.spec.revision,
            runtime=s.spec.runtime,
            queue=s.spec.queue,
            available=s.available,
            path=s.path,
            fingerprint=s.fingerprint,
            vram_mb=s.spec.vram_mb,
            note=s.spec.note,
            kind=s.spec.kind,
            installed=s.installed,
            missing_files=s.missing_files,
            base=s.spec.base,
            uses=list(s.spec.uses),
            compatible=s.compatible,
            reason=ErrorBody(key=s.reason_key, params=s.reason_params) if s.reason_key else None,
            eval=s.eval,
            loaded=_loaded(s, beat, by_name),
            is_stub=not s.available,
        )
        for s in statuses
    ]

    # Counted from the tools rather than the catalog: what matters to a reader
    # is how many steps would measure something, not how many files exist.
    tools = registry.all()
    return ModelsOut(
        models=rows,
        models_dir=str(catalog.root),
        available_count=sum(1 for row in rows if row.available),
        stub_tool_count=sum(1 for tool in tools if tool.is_stub),
        tool_count=len(tools),
        gpu_worker=beat is not None,
    )


@router.get("/runtime", response_model=RuntimeOut, response_model_exclude_none=True)
async def runtime(settings: SettingsDep) -> RuntimeOut:
    """The GPU worker's heartbeat: what is loaded, VRAM, versions, last error."""
    beat = await gpu_heartbeat(settings.redis_url)
    if beat is None:
        return RuntimeOut(status="no_gpu_worker")
    fields = set(RuntimeOut.model_fields) - {"status"}
    return RuntimeOut(status="up", **{k: v for k, v in beat.items() if k in fields})


def _celery(settings):
    from celery import Celery

    return Celery(broker=settings.redis_url, backend=settings.redis_url)


@router.post(
    "/{name}/selftest",
    response_model=SelftestStarted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_selftest(
    name: str, user: CurrentUser, catalog: CatalogDep, settings: SettingsDep
) -> SelftestStarted:
    """Run a model's golden fixtures on the GPU worker. Operators only.

    Enabled by SATSAATHI_DEBUG=1: a self-test occupies the one GPU for
    seconds, which is not something every signed-in user should trigger.
    """
    if not settings.debug:
        raise api_error(status.HTTP_404_NOT_FOUND, "selftest.disabled")
    if name not in catalog:
        raise api_error(status.HTTP_404_NOT_FOUND, "model.unknown", name=name)
    result = _celery(settings).send_task(SELFTEST_TASK, args=[name], queue="gpu")
    return SelftestStarted(task_id=str(result.id), model=name)


@router.get("/selftest/{task_id}", response_model=SelftestOut)
async def selftest_result(task_id: str, user: CurrentUser, settings: SettingsDep) -> SelftestOut:
    if not settings.debug:
        raise api_error(status.HTTP_404_NOT_FOUND, "selftest.disabled")
    from celery.result import AsyncResult

    result = AsyncResult(task_id, app=_celery(settings))
    state = result.state
    if state in ("PENDING", "RECEIVED", "STARTED", "RETRY"):
        return SelftestOut(task_id=task_id, state="pending")
    if state != "SUCCESS":
        return SelftestOut(
            task_id=task_id,
            state="failed",
            passed=False,
            checks=[
                SelftestCheck(check="selftest.crashed", passed=False, detail=str(result.result))
            ],
        )
    body = result.result or {}
    return SelftestOut(task_id=task_id, state="done", **body)
