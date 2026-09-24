"""Plugging the runtime into the existing model seam.

`satsaathi_models.load(spec, root)` asks a registered loader for a model. For
every torch-backed spec — base, adapter or composite — the answer is a handle
onto the one shared `VLMRuntime`; the handle is cheap, and the weights load
on its first call. A missing GPU stack is refused here, at load time, so the
tool takes its fixture path with `model.not_loadable` rather than failing
half-way through a prediction.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from satsaathi_models import ModelCatalog, ModelSpec, ModelUnavailableError, register_loader

from .runtime import Generation, VLMRuntime, get_runtime


class ModelHandle:
    """What a tool's `predict` receives: the runtime, seen from one spec."""

    def __init__(self, runtime: VLMRuntime, spec: ModelSpec):
        self.runtime = runtime
        self.spec = spec

    @property
    def catalog(self) -> ModelCatalog:
        return self.runtime.catalog

    def meta(self, adapter: str | None = None) -> dict[str, Any]:
        return self.runtime.meta(adapter or self.spec.name)

    def generate(self, adapter: str | None, images: list[Any], prompt: str, **kwargs) -> Generation:
        return self.runtime.generate(adapter, images, prompt, **kwargs)

    def prior(self, adapter: str, task: str) -> float | None:
        return self.catalog.prior(adapter, task)


def _gpu_stack_present() -> list[str]:
    missing = []
    for module in ("torch", "transformers", "peft", "bitsandbytes"):
        if importlib.util.find_spec(module) is None:
            missing.append(module)
    return missing


def register(catalog: ModelCatalog) -> None:
    """Teach this process to run torch models from `catalog`'s directory."""

    def loader(spec: ModelSpec, _directory: Path) -> ModelHandle:
        missing = _gpu_stack_present()
        if missing:
            raise ModelUnavailableError(f"GPU runtime not installed: {', '.join(missing)}")
        return ModelHandle(get_runtime(catalog), spec)

    register_loader("torch", loader)
