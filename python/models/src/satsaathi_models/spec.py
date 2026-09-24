"""What a model is, before anything has been loaded.

A spec is a declaration, not a loaded model: it says which weights a task
wants, which revision, what hardware it needs and how to run it. Resolving one
touches the filesystem and nothing else, so the API can answer "is the real
vision-language model available?" without importing a deep-learning stack.

Revisions are part of the identity on purpose. A trace records the version of
every tool that ran, and "the VQA model" is not a version — `vqa-sar` at `v1`
is. Swapping weights without changing the revision would make two different
answers look like they came from the same system.

Five kinds exist, because "is it installed?" means something different for
each:

  * `hf_base`       a full checkpoint; every file a loader opens must exist.
  * `lora_adapter`  small weights on top of a base. Useless without the base,
                    and harmful on the wrong one, so both are checked.
  * `composite`     no weights of its own; runs other models together
                    (fusion reads with two adapters). Installed when they are.
  * `classical`     code only — thresholds and morphology. Always installed.
  * `stub`          declared so the settings screen can name it, but nothing
                    here can run it. Never available, and says so.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

Runtime = Literal["torch", "onnx", "numpy", "external"]
Queue = Literal["cpu", "gpu", "lang"]
Kind = Literal["hf_base", "lora_adapter", "composite", "classical", "stub"]

#: Files a loader opens for a full checkpoint. Checked with stat() only.
HF_BASE_FILES: tuple[str, ...] = (
    "config.json",
    "model.safetensors",
    "tokenizer.json",
    "preprocessor_config.json",
    "chat_template.json",
)
#: Files every adapter needs besides its meta JSON.
ADAPTER_FILES: tuple[str, ...] = ("adapter_config.json", "adapter_model.safetensors")


@dataclass(frozen=True)
class ModelSpec:
    """A model this system knows how to run, if its weights are present."""

    #: Stable identifier, used in tool versions and on the trace.
    name: str
    #: The tool task this serves, matching `satsaathi_tools.protocol.TASKS`.
    task: str
    #: Weights revision. Changing weights without changing this is a bug.
    revision: str
    kind: Kind = "hf_base"
    #: Runtime needed to execute it.
    runtime: Runtime = "torch"
    #: Which worker queue can run it. GPU models must not land on a CPU box.
    queue: Queue = "gpu"
    #: For an adapter: the catalog name of the base it was trained on.
    base: str | None = None
    #: For a composite: the catalog names it runs.
    uses: tuple[str, ...] = ()
    #: For an adapter: the JSON holding its exact system prompt and image rule.
    meta_file: str | None = None
    #: For a base: the upstream repository and the exact commit to fetch.
    #: An adapter's `adapter_config.json` must name the same repository.
    hf_repo: str | None = None
    hf_revision: str | None = None
    #: Eval metric that backs each kind of answer, as keys into eval.json's
    #: "finetuned" block. The confidence prior for a grounding answer is the
    #: held-out grounding accuracy, not a number anyone chose.
    eval_metrics: dict[str, str] = field(default_factory=dict)
    #: Rough VRAM need in MB, so a scheduler can refuse rather than OOM.
    vram_mb: int | None = None
    #: Operator-facing note for the settings screen, shown as-is.
    note: str = ""

    @property
    def slug(self) -> str:
        """Directory name for this exact revision."""
        return f"{self.name}@{self.revision}"

    def directory(self, root: Path) -> Path:
        return Path(root) / self.name / self.revision

    @property
    def required_files(self) -> tuple[str, ...]:
        if self.kind == "hf_base":
            return HF_BASE_FILES
        if self.kind == "lora_adapter":
            return ADAPTER_FILES + ((self.meta_file,) if self.meta_file else ())
        return ()

    @property
    def entrypoint(self) -> str | None:
        """The one file whose bytes identify these weights."""
        if self.kind == "hf_base":
            return "model.safetensors"
        if self.kind == "lora_adapter":
            return "adapter_model.safetensors"
        return None

    def weights_path(self, root: Path) -> Path | None:
        entry = self.entrypoint
        return self.directory(root) / entry if entry else None

    def missing_files(self, root: Path) -> list[str]:
        """Required files that are not on disk, by name.

        Presence is the whole test. Verifying that a file is a loadable model
        is the runtime's job; doing it here would mean loading every model to
        answer a status question.
        """
        directory = self.directory(root)
        missing: list[str] = []
        for name in self.required_files:
            try:
                if not (directory / name).is_file():
                    missing.append(name)
            except OSError:
                # An unreadable or missing mount is a missing file, not a crash.
                missing.append(name)
        return missing

    def is_available(self, root: Path) -> bool:
        """Whether this spec's *own* files are on the machine.

        Says nothing about a base or the models a composite uses; the catalog
        resolves those, because only it knows the other specs.
        """
        if self.kind == "stub":
            return False
        return not self.missing_files(root)

    def fingerprint(self, root: Path) -> str | None:
        """A short digest of the weights, or None when they are absent.

        Recorded alongside a real prediction so a trace can be tied to the
        exact bytes that produced it. Only the first and last megabyte are
        hashed: enough to catch a swapped or truncated file, cheap enough to
        run at worker startup rather than never.
        """
        path = self.weights_path(root)
        if path is None:
            return None
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
