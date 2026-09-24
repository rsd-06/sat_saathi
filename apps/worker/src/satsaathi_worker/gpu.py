"""The GPU worker's side jobs: register the runtime, say it is alive, let go of memory.

One process holds the model. Celery must run it with `--pool=solo
--concurrency=1`: CUDA state does not survive fork, and a second process
would load a second copy of the base anyway.

Every worker, GPU or not, publishes a short-lived presence key per queue it
consumes (`workers:<queue>:heartbeat`), so the API's readiness check can tell
"no GPU worker" from "GPU worker busy" without importing Celery's inspect
machinery. The GPU worker also publishes `models:gpu:heartbeat`, the runtime
snapshot `/models/runtime` returns; the API reads it and never needs torch.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import sys
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

GPU_HEARTBEAT_KEY = "models:gpu:heartbeat"
QUEUE_HEARTBEAT_KEY = "workers:{queue}:heartbeat"
INTERVAL_S = 5
TTL_S = 15

_stop = threading.Event()
_thread: threading.Thread | None = None


def worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def register_runtime(settings: Any) -> bool:
    """Make torch models loadable in this process. False without the package."""
    try:
        from satsaathi_inference import register
    except ImportError:
        logger.warning("satsaathi-inference not installed; model steps will be fixtures")
        return False
    from satsaathi_models import ModelCatalog

    register(ModelCatalog(settings.models_dir))
    return True


def runtime():
    """The process's runtime, if one was ever created. Never creates one."""
    mod = sys.modules.get("satsaathi_inference.runtime")
    return mod.current_runtime() if mod is not None else None


def ensure_runtime(settings: Any):
    from satsaathi_inference.runtime import get_runtime
    from satsaathi_models import ModelCatalog

    return get_runtime(ModelCatalog(settings.models_dir))


def gpu_payload(settings: Any) -> dict[str, Any]:
    """The heartbeat body. Built without loading anything.

    VRAM is read only when torch is already imported: importing it just to
    report zero would cost the idle worker hundreds of megabytes.
    """
    rt = runtime()
    if rt is not None:
        snap = rt.snapshot() if "torch" in sys.modules else _cold_snapshot(rt)
    else:
        snap = _cold_snapshot(None)
    return {"worker_id": worker_id(), "at": time.time(), **snap}


def _cold_snapshot(rt) -> dict[str, Any]:
    from importlib import metadata

    def version(name: str) -> str | None:
        try:
            return metadata.version(name)
        except metadata.PackageNotFoundError:
            return None

    stats = rt.stats if rt is not None else None
    return {
        "base_loaded": bool(stats and stats.base_loaded),
        "adapters_loaded": list(stats.adapters_loaded) if stats else [],
        "vram_allocated_mb": None,
        "vram_reserved_mb": None,
        "vram_peak_mb": None,
        "gpu_name": None,
        "torch": version("torch"),
        "transformers": version("transformers"),
        "peft": version("peft"),
        "bitsandbytes": version("bitsandbytes"),
        "load_seconds": stats.load_seconds if stats else None,
        "last_inference_ms": stats.last_inference_ms if stats else None,
        "inferences_total": stats.inferences_total if stats else 0,
        "last_error_key": stats.last_error_key if stats else None,
        "idle_seconds": None,
    }


def beat_once(client: Any, settings: Any, queues: list[str]) -> None:
    for queue in queues:
        client.set(
            QUEUE_HEARTBEAT_KEY.format(queue=queue),
            json.dumps({"worker_id": worker_id(), "at": time.time()}),
            ex=TTL_S,
        )
    if "gpu" in queues:
        client.set(GPU_HEARTBEAT_KEY, json.dumps(gpu_payload(settings)), ex=TTL_S)
        rt = runtime()
        if rt is not None and rt.unload_if_idle(float(settings.model_idle_unload_min)):
            logger.info(
                "model unloaded after %s idle minutes", settings.model_idle_unload_min
            )


def start(settings: Any, queues: list[str]) -> None:
    """Start the heartbeat thread. Idempotent."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    import redis

    client = redis.Redis.from_url(settings.redis_url, socket_timeout=2)
    _stop.clear()

    def loop() -> None:
        while not _stop.is_set():
            try:
                beat_once(client, settings, queues)
            except Exception:  # noqa: BLE001 - a missed beat must not kill the worker
                logger.debug("heartbeat failed", exc_info=True)
            _stop.wait(INTERVAL_S)

    _thread = threading.Thread(target=loop, name="satsaathi-heartbeat", daemon=True)
    _thread.start()


def stop() -> None:
    _stop.set()


def on_worker_ready(settings: Any, queues: list[str]) -> None:
    """Called once when a worker comes up."""
    if "gpu" in queues:
        if register_runtime(settings) and settings.preload_models:
            try:
                ensure_runtime(settings).load()
            except Exception:  # noqa: BLE001 - the heartbeat reports last_error_key
                logger.exception("preload failed; will retry on first gpu task")
    start(settings, queues)
