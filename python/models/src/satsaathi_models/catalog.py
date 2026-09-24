"""The models this system knows about, and whether this machine has them.

The catalog is a declaration checked into the repository, not a scan of a
directory. That way a deployment missing its weights reports a *named* model
as unavailable rather than silently having fewer capabilities, and the
settings screen can say which one to install.

Everything here is stdlib: `stat()` for presence, `json` for the adapter's
declared base and its eval numbers. The API resolves the whole catalog without
importing torch.

Every adapter is a LoRA on one resident base (Qwen3-VL-2B-Instruct, 4-bit),
so installing an adapter means nothing until that base is installed too — and
an adapter trained on a different base is refused outright, never loaded.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .spec import ModelSpec

BASE_NAME = "qwen3-vl-2b-instruct"
BASE_REPO = "Qwen/Qwen3-VL-2B-Instruct"
#: Pinned upstream commit. `revision` is its short form, so the trace reads
#: `qwen3-vl-2b-instruct@89644892e4d8` and `pull` still fetches exact bytes.
BASE_COMMIT = "89644892e4d85e24eaac8bacfd4f463576704203"

#: The first live scope is SAR and optical imagery, so these are the models
#: the pipeline is built around. Each stays unavailable — and its tool stays
#: honestly marked as fixture output — until its weights are on disk.
CATALOG: tuple[ModelSpec, ...] = (
    ModelSpec(
        name=BASE_NAME,
        task="llm_explain",
        revision=BASE_COMMIT[:12],
        kind="hf_base",
        hf_repo=BASE_REPO,
        hf_revision=BASE_COMMIT,
        vram_mb=2600,
        note="Resident 4-bit base. Every adapter below attaches to it; with "
        "adapters disabled it adjudicates fusion disagreements.",
    ),
    ModelSpec(
        name="vqa-optical",
        task="vqa",
        revision="v1",
        kind="lora_adapter",
        base=BASE_NAME,
        meta_file="satquery_optical_meta.json",
        eval_metrics={
            "grounding": "ground_acc@0.5",
            "vqa": "vqa_acc",
            "caption": "vqa_acc",
            "change": "change_flag_acc",
        },
        vram_mb=2800,
        note="LoRA on the base: answers, captions and locates in one optical scene.",
    ),
    ModelSpec(
        name="vqa-sar",
        task="vqa",
        revision="v1",
        kind="lora_adapter",
        base=BASE_NAME,
        meta_file="satquery_sar_meta.json",
        # Scene accuracy is the closest held-out measure of a free-form SAR
        # answer. Grounding is weak (0.20) and is kept separate on purpose.
        eval_metrics={
            "grounding": "ground_acc@0.5",
            "vqa": "scene_acc",
            "caption": "scene_acc",
        },
        vram_mb=2800,
        note="LoRA on the base for SAR backscatter, where optical models mislead.",
    ),
    ModelSpec(
        name="index-ndvi",
        task="index_compute",
        revision="v1",
        kind="lora_adapter",
        base=BASE_NAME,
        meta_file="satquery_index_meta.json",
        eval_metrics={"vqa": "vqa_acc"},
        vram_mb=2800,
        note="LoRA that reads a rendered NDVI map next to its computed statistics.",
    ),
    ModelSpec(
        name="index-ndwi",
        task="index_compute",
        revision="v1",
        kind="lora_adapter",
        base=BASE_NAME,
        meta_file="satquery_index_meta.json",
        eval_metrics={"vqa": "vqa_acc"},
        vram_mb=2800,
        note="LoRA that reads a rendered NDWI map next to its computed statistics.",
    ),
    ModelSpec(
        name="fusion-optical-sar",
        task="optical_sar_fusion",
        revision="v1",
        kind="composite",
        uses=("vqa-optical", "vqa-sar", BASE_NAME),
        vram_mb=2800,
        note="Asks both adapters the same question, measures agreement, and "
        "has the base decide which sensor to trust.",
    ),
    ModelSpec(
        name="change-detection",
        task="change_detection",
        revision="v1",
        kind="composite",
        uses=("vqa-optical",),
        vram_mb=2800,
        note="Classical change map for the boxes; the optical adapter explains them.",
    ),
    ModelSpec(
        name="sar-water-mask",
        task="sar_water_mask",
        revision="v1",
        kind="classical",
        runtime="numpy",
        queue="cpu",
        note="dB threshold (Otsu) and morphology. No learned weights.",
    ),
    ModelSpec(
        name="translate-indic",
        task="translate",
        revision="v0",
        kind="stub",
        queue="lang",
        vram_mb=2000,
        note="Declared, not implemented: answers are not translated yet.",
    ),
)


@dataclass(frozen=True)
class ModelStatus:
    spec: ModelSpec
    #: Usable right now: own files present, base or dependencies usable, and
    #: an adapter's declared base matches. This is what a tool checks.
    available: bool
    path: str
    fingerprint: str | None
    #: This spec's own files are present, whatever the state of its base.
    installed: bool = False
    missing_files: list[str] = field(default_factory=list)
    #: Whether an adapter was trained on the base declared here. None when
    #: the question does not apply or cannot be answered yet.
    compatible: bool | None = None
    #: Why it is not available, as an i18n key. None when it is.
    reason_key: str | None = None
    reason_params: dict[str, Any] = field(default_factory=dict)
    #: Held-out metrics from eval.json, when installed alongside the weights.
    eval: dict[str, Any] | None = None
    #: manifest.json written by `satsaathi-models install`, when present.
    manifest: dict[str, Any] | None = None

    @property
    def is_stub(self) -> bool:
        return self.spec.kind == "stub"


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def prior_from_eval(spec: ModelSpec, eval_doc: dict[str, Any] | None, task: str) -> float | None:
    """The fine-tuned held-out metric behind one kind of answer, or None."""
    if not eval_doc:
        return None
    key = spec.eval_metrics.get(task)
    value = (eval_doc.get("finetuned") or {}).get(key) if key else None
    return float(value) if isinstance(value, (int, float)) else None


class ModelCatalog:
    """The catalog resolved against one machine's models directory."""

    def __init__(self, root: Path | str, specs: tuple[ModelSpec, ...] = CATALOG):
        self.root = Path(root)
        self._specs = {spec.name: spec for spec in specs}

    def __contains__(self, name: object) -> bool:
        return name in self._specs

    def get(self, name: str) -> ModelSpec | None:
        return self._specs.get(name)

    def specs(self) -> list[ModelSpec]:
        return [self._specs[name] for name in sorted(self._specs)]

    def status(self, name: str) -> ModelStatus | None:
        return self._resolve(name, frozenset())

    def _resolve(self, name: str, seen: frozenset[str]) -> ModelStatus | None:
        spec = self._specs.get(name)
        if spec is None:
            return None
        directory = spec.directory(self.root)
        missing = spec.missing_files(self.root)
        installed = spec.kind != "stub" and not missing
        eval_doc = _read_json(directory / "eval.json") if installed else None
        manifest = _read_json(directory / "manifest.json") if installed else None

        reason: str | None = None
        params: dict[str, Any] = {}
        compatible: bool | None = None

        if spec.kind == "stub":
            reason = "model.stub"
        elif missing:
            reason, params = "model.not_installed", {"missing": missing}
        elif spec.kind == "lora_adapter":
            reason, params, compatible = self._check_adapter(spec, directory, seen)
        elif spec.kind == "composite":
            for dependency in spec.uses:
                dep = self._resolve(dependency, seen | {name}) if dependency not in seen else None
                if dep is None or not dep.available:
                    reason, params = "model.dependency_missing", {"model": dependency}
                    break

        available = reason is None
        return ModelStatus(
            spec=spec,
            available=available,
            path=str(directory),
            fingerprint=spec.fingerprint(self.root) if installed else None,
            installed=installed,
            missing_files=missing,
            compatible=compatible,
            reason_key=reason,
            reason_params=params,
            eval=eval_doc,
            manifest=manifest,
        )

    def _check_adapter(
        self, spec: ModelSpec, directory: Path, seen: frozenset[str]
    ) -> tuple[str | None, dict[str, Any], bool | None]:
        """Refuse an adapter whose base is absent or is not the one declared.

        A LoRA applied to the wrong base still produces text, which is exactly
        why it is refused here: nothing downstream could tell it was garbage.
        """
        base = self._specs.get(spec.base or "")
        if base is None:
            return "model.base_missing", {"base": spec.base}, None

        config = _read_json(directory / "adapter_config.json")
        declared = (config or {}).get("base_model_name_or_path")
        if not isinstance(declared, str):
            return "model.adapter_config_unreadable", {}, None
        if declared != base.hf_repo:
            return (
                "model.base_mismatch",
                {"expected": base.hf_repo, "found": declared},
                False,
            )

        base_status = self._resolve(base.name, seen | {spec.name})
        if base_status is None or not base_status.available:
            return "model.base_missing", {"base": base.name}, True
        return None, {}, True

    def is_available(self, name: str) -> bool:
        status = self.status(name)
        return bool(status and status.available)

    def available_names(self) -> set[str]:
        return {name for name in self._specs if self.is_available(name)}

    def all_status(self) -> list[ModelStatus]:
        rows = [self.status(name) for name in sorted(self._specs)]
        return [row for row in rows if row is not None]

    def prior(self, name: str, task: str) -> float | None:
        status = self.status(name)
        if status is None:
            return None
        return prior_from_eval(status.spec, status.eval, task)
