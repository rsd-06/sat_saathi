"""What a model is, before anything has been loaded.

A spec is a declaration, not a loaded model: it says which weights a task
wants, which revision, what hardware it needs and how to run it. Resolving one
touches the filesystem and nothing else, so the API can answer "is the real
vision-language model available?" without importing a deep-learning stack.

Revisions are part of the identity on purpose. A trace records the version of
every tool that ran, and "the VQA model" is not a version — `vqa-remoteclip`
at `v1.2` is. Swapping weights without changing the revision would make two
different answers look like they came from the same system.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Runtime = Literal["torch", "onnx", "external"]
Queue = Literal["cpu", "gpu", "lang"]


@dataclass(frozen=True)
class ModelSpec:
    """A model this system knows how to run, if its weights are present."""

    #: Stable identifier, used in tool versions and on the trace.
    name: str
    #: The tool task this serves, matching `satsaathi_tools.protocol.TASKS`.
    task: str
    #: Weights revision. Changing weights without changing this is a bug.
    revision: str
    #: Runtime needed to execute it.
    runtime: Runtime = "torch"
    #: Which worker queue can run it. GPU models must not land on a CPU box.
    queue: Queue = "gpu"
    #: File that must exist for the model to count as available. Relative to
    #: the model's own directory.
    entrypoint: str = "model.safetensors"
    #: Rough VRAM need in MB, so a scheduler can refuse rather than OOM.
    vram_mb: int | None = None
    #: Human-facing note for the settings screen. Not user-facing chrome —
    #: this is operator detail, shown as-is.
    note: str = ""

    @property
    def slug(self) -> str:
        """Directory name for this exact revision."""
        return f"{self.name}@{self.revision}"

    def directory(self, root: Path) -> Path:
        return Path(root) / self.name / self.revision

    def weights_path(self, root: Path) -> Path:
        return self.directory(root) / self.entrypoint

    def is_available(self, root: Path) -> bool:
        """Whether the weights are actually on this machine.

        Presence of the entrypoint file is the whole test. Verifying that the
        file is a loadable model is the runtime's job, and doing it here would
        mean loading every model to answer a status question.
        """
        try:
            return self.weights_path(root).is_file()
        except OSError:
            # An unreadable or missing mount is a missing model, not a crash.
            return False

    def fingerprint(self, root: Path) -> str | None:
        """A short digest of the weights, or None when they are absent.

        Recorded alongside a real prediction so a trace can be tied to the
        exact bytes that produced it. Only the first and last megabyte are
        hashed: enough to catch a swapped or truncated file, cheap enough to
        run at worker startup rather than never.
        """
        path = self.weights_path(root)
        try:
            size = path.stat().st_size
            digest = hashlib.sha256()
            digest.update(str(size).encode())
            with path.open("rb") as handle:
                digest.update(handle.read(1 << 20))
                if size > (2 << 20):
                    handle.seek(-(1 << 20), 2)
                    digest.update(handle.read(1 << 20))
            return digest.hexdigest()[:16]
        except OSError:
            return None
