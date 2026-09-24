"""Boxes: reading them out of model text, and putting them on the ground.

The adapters answer in the format they were trained on:

    ```json
    [{"bbox_2d": [x1, y1, x2, y2], "label": "ship"}]
    ```

with coordinates relative to the image, 0-1000. Generation is capped, so the
closing fence, bracket or brace is sometimes cut off; the parser takes every
complete `bbox_2d` it can find rather than all-or-nothing JSON.

Coordinates move through three frames: relative (0-1000, what the model
says), pixels (of the scene as uploaded, not the resized copy the model saw),
and map (only when the scene has a CRS — a pixel box from an ungeoreferenced
image is never presented as a place on the ground).
"""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE = re.compile(r"```(?:json)?\s*(.*?)(?:```|$)", re.S)
_NUM = r"-?\d+(?:\.\d+)?"
_BOX = re.compile(
    r'"bbox_2d"\s*:\s*\[\s*(' + _NUM + r")\s*,\s*(" + _NUM + r")\s*,\s*("
    + _NUM + r")\s*,\s*(" + _NUM + r")\s*\]"
)
_LABEL_AFTER = re.compile(r'^[^{}\[]*?"label"\s*:\s*"([^"]*)"')
_LABEL_BEFORE = re.compile(r'"label"\s*:\s*"([^"]*)"[^{}\]]*$')


def _clamp(v: float) -> int:
    return int(round(min(max(v, 0.0), 1000.0)))


def _normalise(coords: list[float], label: Any) -> dict[str, Any] | None:
    x1, y1, x2, y2 = (_clamp(v) for v in coords)
    x1, x2 = sorted((x1, x2))
    y1, y2 = sorted((y1, y2))
    if x2 <= x1 or y2 <= y1:
        return None
    return {"bbox_2d": [x1, y1, x2, y2], "label": str(label) if label else "object"}


def _from_json(text: str) -> list[dict[str, Any]] | None:
    candidates = [m.group(1) for m in _FENCE.finditer(text)] + [text]
    for chunk in candidates:
        chunk = chunk.strip()
        start = chunk.find("[")
        if start < 0:
            continue
        try:
            data = json.loads(chunk[start : chunk.rfind("]") + 1])
        except ValueError:
            continue
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            continue
        out = []
        for item in data:
            if isinstance(item, dict) and isinstance(item.get("bbox_2d"), list):
                coords = item["bbox_2d"]
                if len(coords) == 4 and all(isinstance(v, (int, float)) for v in coords):
                    box = _normalise([float(v) for v in coords], item.get("label"))
                    if box:
                        out.append(box)
        if out:
            return out
    return None


def parse_boxes(text: str) -> list[dict[str, Any]]:
    """Every box the text states, relative 0-1000, in order.

    Clean JSON first; otherwise a regex over each `"bbox_2d": [...]`, picking
    up a label beside it when one survived truncation.
    """
    parsed = _from_json(text)
    if parsed is not None:
        return parsed
    out = []
    for match in _BOX.finditer(text):
        after = _LABEL_AFTER.match(text[match.end() :])
        before = _LABEL_BEFORE.search(text[: match.start()])
        found = after or before
        label = found.group(1) if found else None
        box = _normalise([float(g) for g in match.groups()], label)
        if box:
            out.append(box)
    return out


def looks_like_boxes(text: str) -> bool:
    """Whether the model tried to answer with boxes at all."""
    return "bbox_2d" in text


def relative_to_pixels(box: list[int], width: int, height: int) -> list[float]:
    x1, y1, x2, y2 = box
    return [
        round(x1 / 1000 * width, 2),
        round(y1 / 1000 * height, 2),
        round(x2 / 1000 * width, 2),
        round(y2 / 1000 * height, 2),
    ]


def pixels_to_relative(box: list[float], width: int, height: int) -> list[int]:
    x1, y1, x2, y2 = box
    return [
        _clamp(x1 / width * 1000),
        _clamp(y1 / height * 1000),
        _clamp(x2 / width * 1000),
        _clamp(y2 / height * 1000),
    ]


def pixels_to_map(
    box: list[float],
    transform: tuple[float, float, float, float, float, float] | None,
    crs: str | None,
) -> list[float] | None:
    """[minx, miny, maxx, maxy] in the scene's CRS, or None without one.

    The honesty rule: no CRS, no map coordinates — never a guess.
    """
    if transform is None or not crs:
        return None
    a, b, c, d, e, f = transform
    corners = [
        (a * x + b * y + c, d * x + e * y + f)
        for x, y in ((box[0], box[1]), (box[2], box[1]), (box[0], box[3]), (box[2], box[3]))
    ]
    xs = [p[0] for p in corners]
    ys = [p[1] for p in corners]
    return [min(xs), min(ys), max(xs), max(ys)]


def iou(a: list[float], b: list[float]) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def box_f1(pred: list[list[float]], ref: list[list[float]], threshold: float = 0.5) -> float:
    """F1 of greedy one-to-one matches at an IoU threshold.

    Two empty sets agree perfectly; one empty and one not share nothing.
    """
    if not pred and not ref:
        return 1.0
    if not pred or not ref:
        return 0.0
    pairs = sorted(
        ((iou(p, r), i, j) for i, p in enumerate(pred) for j, r in enumerate(ref)),
        reverse=True,
    )
    used_p: set[int] = set()
    used_r: set[int] = set()
    matched = 0
    for score, i, j in pairs:
        if score < threshold:
            break
        if i in used_p or j in used_r:
            continue
        used_p.add(i)
        used_r.add(j)
        matched += 1
    precision = matched / len(pred)
    recall = matched / len(ref)
    return 0.0 if matched == 0 else 2 * precision * recall / (precision + recall)


def best_overlap(box: list[float], others: list[list[float]]) -> float:
    return max((iou(box, o) for o in others), default=0.0)
