"""Declaring, finding and loading the models behind the pipeline.

Importing this package pulls in no deep-learning runtime. Everything here is
about *whether* a model exists and *how* it would be loaded; actually loading
one happens in `loader.load`, which imports its runtime at that moment.
"""

from .catalog import CATALOG, ModelCatalog, ModelStatus
from .loader import (
    ModelUnavailableError,
    clear_loaders,
    has_loader,
    load,
    loaded_names,
    register_loader,
    unload_all,
)
from .spec import ModelSpec, Queue, Runtime

__all__ = [
    "CATALOG",
    "ModelCatalog",
    "ModelSpec",
    "ModelStatus",
    "ModelUnavailableError",
    "clear_loaders",
    "Queue",
    "Runtime",
    "has_loader",
    "load",
    "loaded_names",
    "register_loader",
    "unload_all",
]
