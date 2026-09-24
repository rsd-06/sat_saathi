"""Getting a model into memory, once per process, only when it is needed.

Loading is deferred as far as it can be. Importing this module costs nothing;
importing a runtime happens inside `load`, so an API process that only ever
asks whether a model exists never pays for torch, and a CPU worker never
imports CUDA.

Loaded models are cached per process and never evicted. A worker runs one job
at a time and reuses the same weights for the next one, and unloading between
jobs would spend seconds of GPU transfer to save memory nobody else wants.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .spec import ModelSpec

logger = logging.getLogger(__name__)

#: Runtime name -> callable that turns a spec and a directory into a model.
#: Registering a loader is how a deployment supports a runtime; nothing here
#: imports torch, so a machine without it still starts.
LoaderFn = Callable[[ModelSpec, Path], Any]

_loaders: dict[str, LoaderFn] = {}
_cache: dict[str, Any] = {}
_lock = threading.Lock()


class ModelUnavailableError(RuntimeError):
    """The weights are not on this machine, or no runtime can load them."""


class ModelOOMError(RuntimeError):
    """The device ran out of memory mid-call. The model did not answer."""


class ModelOutputUnparseableError(ValueError):
    """The model answered, but not in the shape the task needs.

    Distinct from the two above on purpose: here a model *did* run, so the
    trace records it as a model step that produced nothing usable, not as a
    fixture.
    """

    def __init__(self, message: str, raw_text: str = ""):
        super().__init__(message)
        self.raw_text = raw_text


def register_loader(runtime: str, fn: LoaderFn) -> None:
    """Teach the process how to load one runtime's models."""
    _loaders[runtime] = fn


def has_loader(runtime: str) -> bool:
    return runtime in _loaders


def load(spec: ModelSpec, root: Path) -> Any:
    """The loaded model for this spec, loading it on first use.

    Raises rather than returning a placeholder: a caller that wanted a real
    prediction must not be handed something that quietly is not one. Callers
    that can fall back to fixture output check availability first.
    """
    if not spec.is_available(root):
        raise ModelUnavailableError(
            f"{spec.slug}: missing {', '.join(spec.missing_files(root)) or 'weights'}"
            f" under {spec.directory(root)}"
        )

    loader = _loaders.get(spec.runtime)
    if loader is None:
        raise ModelUnavailableError(
            f"{spec.slug}: no loader registered for runtime {spec.runtime!r}"
        )

    key = spec.slug
    # Double-checked so the common path does not take the lock, while two
    # threads racing on first use still load the weights only once.
    if key in _cache:
        return _cache[key]
    with _lock:
        if key not in _cache:
            logger.info("loading model %s from %s", key, spec.directory(root))
            _cache[key] = loader(spec, spec.directory(root))
    return _cache[key]


def unload_all() -> None:
    """Drop every cached model. For tests and for a clean worker shutdown."""
    with _lock:
        _cache.clear()


def clear_loaders() -> None:
    """Forget every registered runtime, along with anything it loaded.

    Registering a loader is process-global, so a test that installs one would
    otherwise change how every later test behaves.
    """
    with _lock:
        _loaders.clear()
        _cache.clear()


def loaded_names() -> set[str]:
    return set(_cache)
