"""The models this system knows about, and whether this machine has them.

The catalog is a declaration checked into the repository, not a scan of a
directory. That way a deployment missing its weights reports a *named* model
as unavailable rather than silently having fewer capabilities, and the
settings screen can say which one to install.

Adding a real model is: add a spec here, put the weights under the models
directory, install the runtime extra, restart the worker. Nothing else in the
pipeline changes, because the tools ask the catalog rather than importing
anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .spec import ModelSpec

#: The first live scope is SAR and optical imagery, so these are the models
#: the pipeline is built around. Each stays unavailable — and its tool stays
#: honestly marked as fixture output — until its weights are on disk.
CATALOG: tuple[ModelSpec, ...] = (
    ModelSpec(
        name="vqa-optical",
        task="vqa",
        revision="v0",
        queue="gpu",
        vram_mb=6000,
        note="Answers a question about a single optical scene.",
    ),
    ModelSpec(
        name="vqa-sar",
        task="vqa",
        revision="v0",
        queue="gpu",
        vram_mb=6000,
        note="Answers a question about a SAR scene, where optical models mislead.",
    ),
    ModelSpec(
        name="fusion-optical-sar",
        task="optical_sar_fusion",
        revision="v0",
        queue="gpu",
        vram_mb=8000,
        note="Reads an optical and a SAR scene of the same ground together.",
    ),
    ModelSpec(
        name="change-detection",
        task="change_detection",
        revision="v0",
        queue="gpu",
        vram_mb=6000,
        note="Marks what differs between two dates over the same ground.",
    ),
    ModelSpec(
        name="sar-water-mask",
        task="sar_water_mask",
        revision="v0",
        queue="gpu",
        vram_mb=4000,
        note="Segments open water in SAR, where an optical index cannot see through cloud.",
    ),
    ModelSpec(
        name="translate-indic",
        task="translate",
        revision="v0",
        runtime="torch",
        queue="lang",
        vram_mb=2000,
        note="Translates the answer into the language the question was asked in.",
    ),
)


@dataclass(frozen=True)
class ModelStatus:
    spec: ModelSpec
    available: bool
    path: str
    fingerprint: str | None


class ModelCatalog:
    """The catalog resolved against one machine's models directory."""

    def __init__(self, root: Path | str, specs: tuple[ModelSpec, ...] = CATALOG):
        self.root = Path(root)
        self._specs = {spec.name: spec for spec in specs}

    def __contains__(self, name: object) -> bool:
        return name in self._specs

    def get(self, name: str) -> ModelSpec | None:
        return self._specs.get(name)

    def status(self, name: str) -> ModelStatus | None:
        spec = self._specs.get(name)
        if spec is None:
            return None
        available = spec.is_available(self.root)
        return ModelStatus(
            spec=spec,
            available=available,
            path=str(spec.directory(self.root)),
            fingerprint=spec.fingerprint(self.root) if available else None,
        )

    def is_available(self, name: str) -> bool:
        spec = self._specs.get(name)
        return bool(spec and spec.is_available(self.root))

    def available_names(self) -> set[str]:
        return {name for name in self._specs if self.is_available(name)}

    def all_status(self) -> list[ModelStatus]:
        rows = [self.status(name) for name in sorted(self._specs)]
        return [row for row in rows if row is not None]
