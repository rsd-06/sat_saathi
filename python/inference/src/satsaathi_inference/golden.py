"""Golden fixtures: a few held-out samples per model, and what a pass looks like.

Layout, one folder per sample:

    infra/fixtures/golden/<model>/<sample>/
        fixture.json      {"question", "images": [...], "checks": [...], "source"}
        <image files>     or bands.npz for the index adapters

Checks are deliberately coarse — "the answer parses as boxes", "IoU >= 0.5
with the expected box", "the answer starts with Yes". They catch a broken
runtime, a mis-attached adapter or a wrong prompt, which is their job; they
are not an accuracy benchmark (eval.json is).

`run_sample` is shared by the CLI load test and the API self-test, so both
mean the same thing by "passed".
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from satsaathi_core import boxes as box_maths
from satsaathi_core import index_contract, vlm_prompts
from satsaathi_core.imaging import fit

from .runtime import Generation, VLMRuntime

#: Repository location; overridable for a deployment that ships fixtures
#: elsewhere.
DEFAULT_ROOT = Path(__file__).resolve().parents[4] / "infra" / "fixtures" / "golden"

NO_CHANGE_WORDS = (
    "no change", "no difference", "identical", "same as before",
    "nothing has changed", "unchanged",
)


@dataclass
class Sample:
    model: str
    name: str
    folder: Path
    question: str
    images: list[str]
    checks: list[dict[str, Any]]
    kind: str = "vqa"  # vqa | change | index
    index: str | None = None
    source: str = ""


@dataclass
class CheckResult:
    check: str
    passed: bool
    detail: str = ""


@dataclass
class SampleResult:
    model: str
    sample: str
    passed: bool
    checks: list[CheckResult]
    latency_ms: int
    parsed: bool
    output_excerpt: str
    text: str = field(repr=False, default="")

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out.pop("text")
        return out


def discover(model: str, root: Path = DEFAULT_ROOT) -> list[Sample]:
    folder = root / model
    samples = []
    for sub in sorted(p for p in folder.glob("*") if (p / "fixture.json").is_file()):
        data = json.loads((sub / "fixture.json").read_text(encoding="utf-8"))
        samples.append(
            Sample(
                model=model,
                name=sub.name,
                folder=sub,
                question=data["question"],
                images=list(data.get("images", [])),
                checks=list(data.get("checks", [])),
                kind=data.get("kind", "vqa"),
                index=data.get("index"),
                source=data.get("source", ""),
            )
        )
    return samples


def _open_images(sample: Sample) -> list[Any]:
    from PIL import Image

    out = []
    for name in sample.images:
        with Image.open(sample.folder / name) as img:
            out.append(fit(img.copy()))
    return out


def build_inputs(runtime: VLMRuntime, sample: Sample) -> tuple[list[Any], str, dict[str, Any]]:
    """Images, prompt text and any computed context for one sample."""
    context: dict[str, Any] = {}
    if sample.kind == "index":
        import numpy as np

        roles = dict(np.load(sample.folder / "bands.npz"))
        tc, idx, stats, prompt = index_contract.prepare(
            sample.index or "NDWI", roles, sample.question
        )
        context["stats"] = stats
        context["stats_text"] = index_contract.stats_text(stats)
        return [tc, idx], prompt, context
    images = _open_images(sample)
    if sample.kind == "change":
        return images, vlm_prompts.change_text(runtime.meta(sample.model), sample.question), context
    return images, sample.question, context


def _numbers(text: str) -> list[str]:
    return re.findall(r"-?\d+(?:\.\d+)?", text)


def evaluate(check: dict[str, Any], text: str, context: dict[str, Any]) -> CheckResult:
    kind = check["type"]
    parsed = box_maths.parse_boxes(text)
    if kind == "parses_boxes":
        return CheckResult(kind, bool(parsed), f"{len(parsed)} boxes")
    if kind == "iou_at_least":
        best = box_maths.best_overlap(check["box"], [b["bbox_2d"] for b in parsed])
        ok = best >= float(check.get("threshold", 0.5))
        return CheckResult(f"iou>={check.get('threshold', 0.5)}", ok, f"best {best:.2f}")
    if kind == "starts_with":
        ok = text.strip().lower().startswith(str(check["text"]).lower())
        return CheckResult(f"starts_with {check['text']!r}", ok, text[:40])
    if kind == "contains":
        ok = str(check["text"]).lower() in text.lower()
        return CheckResult(f"contains {check['text']!r}", ok)
    if kind == "change_flag":
        said_same = any(w in text.lower() for w in NO_CHANGE_WORDS)
        flag = "unchanged" if said_same else "changed"
        return CheckResult(f"change flag = {check['expected']}", flag == check["expected"], flag)
    if kind == "stats_numbers_match":
        # Every number quoted must appear in the computed statistics. The
        # adapter was trained to quote, never to estimate.
        allowed = set(_numbers(context.get("stats_text", "")))
        allowed |= set(_numbers(json.dumps(context.get("stats", {}))))
        quoted = [n for n in _numbers(text) if n not in {"0", "1000"}]
        stray = [n for n in quoted if n not in allowed and not _is_box_coordinate(n, text)]
        return CheckResult(
            "stats numbers quoted match the computed stats", not stray,
            f"stray {stray}" if stray else f"{len(quoted)} quoted",
        )
    return CheckResult(kind, False, "unknown check")


def _is_box_coordinate(number: str, text: str) -> bool:
    return any(number in map(str, b["bbox_2d"]) for b in box_maths.parse_boxes(text))


def run_sample(
    runtime: VLMRuntime, sample: Sample, *, adapter: str | None = None, max_new_tokens: int = 192
) -> SampleResult:
    images, prompt, context = build_inputs(runtime, sample)
    name = adapter if adapter is not None else sample.model
    started = time.perf_counter()
    gen: Generation = runtime.generate(
        name, images, prompt, max_new_tokens=max_new_tokens, want_logprobs=False
    )
    latency = int((time.perf_counter() - started) * 1000)
    results = [evaluate(c, gen.text, context) for c in sample.checks]
    expects_boxes = any(c["type"] in ("parses_boxes", "iou_at_least") for c in sample.checks)
    parsed = bool(box_maths.parse_boxes(gen.text)) if expects_boxes else bool(gen.text.strip())
    return SampleResult(
        model=sample.model,
        sample=sample.name,
        passed=all(r.passed for r in results),
        checks=results,
        latency_ms=latency,
        parsed=parsed,
        output_excerpt=gen.text.strip()[:240],
        text=gen.text,
    )
