"""What the vision-language adapters are told, exactly as in training.

System prompts are never written here. Each adapter's meta JSON (saved by its
training script next to the weights) carries the prompt it was trained with,
and that file is the only source: an adapter asked under a paraphrased system
prompt is an adapter out of distribution.

The message layout — system, then one user turn holding every image followed
by the text — is `to_messages` from the training scripts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REQUIRED_META_KEYS = ("system_prompt",)


class MetaError(ValueError):
    """The adapter's meta JSON is missing or does not say what it must."""


def load_meta(path: str | Path) -> dict[str, Any]:
    try:
        meta = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MetaError(f"cannot read {path}: {exc}") from exc
    if not isinstance(meta, dict) or any(not meta.get(k) for k in REQUIRED_META_KEYS):
        raise MetaError(f"{path} has no system_prompt")
    return meta


def messages(system_prompt: str, n_images: int, text: str) -> list[dict[str, Any]]:
    """`to_messages(sample, with_answer=False)` from the training scripts."""
    content: list[dict[str, Any]] = [{"type": "image"} for _ in range(n_images)]
    content.append({"type": "text", "text": text})
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": content},
    ]


def change_text(meta: dict[str, Any], question: str) -> str:
    """The optical adapter's before/after framing, from its meta."""
    template = meta.get("change_prompt")
    if not template:
        raise MetaError("optical meta has no change_prompt")
    return str(template).format(q=question)


def change_explain_text(meta: dict[str, Any], question: str, regions: list[dict]) -> str:
    """Change question plus the regions the classical step measured.

    The adapter was trained on the bare change prompt; the region list is
    appended after it, so the part it learned from is unchanged and the boxes
    shown to the user stay the measured ones.
    """
    base = change_text(meta, question)
    if not regions:
        return base + "\nA pixel-level comparison found no significant changed regions."
    listed = "; ".join(
        f"region {i + 1} at {r['bbox_2d']}" for i, r in enumerate(regions[:5])
    )
    return (
        base
        + f"\nA pixel-level comparison marked these changed regions "
        f"(coordinates 0-1000): {listed}. Explain what changed in them."
    )


FUSION_JUDGE_SYSTEM = (
    "You combine two expert readings of the same ground: one from an optical image, "
    "one from a SAR image. Optical is reliable in clear weather and for colour and "
    "texture; SAR sees through cloud and at night, and shows water and metal clearly "
    "but not colour. Answer the question in two or three sentences. If the readings "
    "disagree, say which sensor to trust here and why."
)


def fusion_judge_text(question: str, optical: str, sar: str, agreement: float) -> str:
    return (
        f"Question: {question}\n"
        f"Optical reading: {optical.strip()}\n"
        f"SAR reading: {sar.strip()}\n"
        f"Agreement between the readings: {agreement:.2f} (0 = none, 1 = full)."
    )
