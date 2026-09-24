"""Declaring, finding and loading the models behind the pipeline.

Importing this package pulls in no deep-learning runtime. Everything here is
about *whether* a model exists and *how* it would be loaded; actually loading
one happens in `loader.load`, which imports its runtime at that moment.
"""

from .catalog import BASE_NAME, CATALOG, ModelCatalog, ModelStatus, prior_from_eval
from .loader import (
    ModelOOMError,
    ModelOutputUnparseableError,
    ModelUnavailableError,
    clear_loaders,
    has_loader,
    load,
    loaded_names,
    register_loader,
    unload_all,
)
from .spec import Kind, ModelSpec, Queue, Runtime

__all__ = [
    "BASE_NAME",
    "CATALOG",
    "Kind",
    "ModelOOMError",
    "ModelOutputUnparseableError",
    "prior_from_eval",
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
