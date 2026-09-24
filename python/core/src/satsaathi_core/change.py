"""Classical change detection and SAR water masks.

These are the measurements under the model-backed steps. The boxes a user sees
for "what changed?" come from here, not from the vision-language model: the
optical adapter's change yes/no is good (0.92 held-out), but its boxes are not
trained on change masks, so it *explains* regions measured here instead of
inventing them.

  * optical: change-vector analysis — per-pixel Euclidean distance between the
    two dates, after both are stretched to 0-1 with one shared range per band;
  * SAR: log-ratio of backscatter, which turns multiplicative speckle into
    additive noise and treats a doubling the same way at any brightness.

Both are thresholded with Otsu and cleaned with a morphological opening;
connected regions become boxes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy import ndimage as ndi

from .boxes import pixels_to_relative


def otsu_threshold(values: np.ndarray, bins: int = 256) -> tuple[float, float]:
    """Otsu's threshold over finite values, and the separability η in [0, 1].

    η is between-class variance over total variance. Near 1 the histogram is
    genuinely two populations; near 0 a split was forced on one.
    """
    v = values[np.isfinite(values)].astype(np.float64)
    if v.size == 0 or v.max() == v.min():
        return float(v.max()) if v.size else 0.0, 0.0
    hist, edges = np.histogram(v, bins=bins)
    centres = (edges[:-1] + edges[1:]) / 2
    weight = hist.astype(np.float64) / hist.sum()
    w0 = np.cumsum(weight)
    w1 = 1 - w0
    mu = np.cumsum(weight * centres)
    mu_t = mu[-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        between = (mu_t * w0 - mu) ** 2 / (w0 * w1)
    between = np.nan_to_num(between)
    k = int(np.argmax(between))
    total = float(np.sum(weight * (centres - mu_t) ** 2))
    eta = float(between[k] / total) if total > 0 else 0.0
    return float(centres[k]), eta


def _joint_stretch(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Stretch each band of both dates with one shared 2-98 percentile range.

    Shared, not per date: a large new bright roof moves the after-date's own
    percentiles, and a per-date stretch would then rescale every unchanged
    pixel and report the whole scene as changed.
    """
    out_a = np.empty(a.shape, np.float64)
    out_b = np.empty(b.shape, np.float64)
    for c in range(a.shape[-1]):
        both = np.concatenate([a[..., c].ravel(), b[..., c].ravel()]).astype(np.float64)
        finite = both[np.isfinite(both)]
        if finite.size == 0:
            out_a[..., c] = np.nan
            out_b[..., c] = np.nan
            continue
        lo, hi = np.percentile(finite, [2, 98])
        span = max(hi - lo, 1e-6)
        out_a[..., c] = np.clip((a[..., c] - lo) / span, 0, 1)
        out_b[..., c] = np.clip((b[..., c] - lo) / span, 0, 1)
    return out_a, out_b


def _match_shape(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Resample `b` onto `a`'s grid when co-registration left them unequal."""
    if a.shape[:2] == b.shape[:2]:
        return b
    factors = (a.shape[0] / b.shape[0], a.shape[1] / b.shape[1]) + (1,) * (b.ndim - 2)
    return np.asarray(ndi.zoom(b, factors, order=1))


def cva_magnitude(before: np.ndarray, after: np.ndarray) -> np.ndarray:
    """Change-vector magnitude for H x W x C optical arrays."""
    after = _match_shape(before, after)
    channels = min(before.shape[-1], after.shape[-1])
    a, b = _joint_stretch(before[..., :channels], after[..., :channels])
    return np.asarray(np.sqrt(np.sum((b - a) ** 2, axis=-1)), dtype=np.float64)


def log_ratio(before: np.ndarray, after: np.ndarray) -> np.ndarray:
    """|log(after / before)| for linear SAR, or |Δ dB| when already in dB."""
    after = _match_shape(before, after)
    finite = np.isfinite(before) & np.isfinite(after)
    in_db = finite.any() and (np.nanmin(before[finite]) < 0 or np.nanmin(after[finite]) < 0)
    if in_db:
        return np.asarray(np.abs(after - before))
    eps = 1e-6
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.asarray(np.abs(np.log((after + eps) / (before + eps))))


@dataclass
class MaskResult:
    method: str
    threshold: float
    separability: float
    fraction_pct: float
    #: Each box: {"bbox_px": [x1,y1,x2,y2], "bbox_2d": [0-1000], "area_px": n}
    boxes: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def regions(
    mask: np.ndarray,
    label: str,
    *,
    scale_to: tuple[int, int] | None = None,
    k: int = 10,
    min_frac: float = 0.002,
) -> list[dict[str, Any]]:
    """Connected regions of a mask as boxes, largest first.

    `scale_to` is the (width, height) of the scene as uploaded; the mask may
    have been computed on a decimated copy, and pixel boxes must refer to the
    original.
    """
    h, w = mask.shape
    sx = (scale_to[0] / w) if scale_to else 1.0
    sy = (scale_to[1] / h) if scale_to else 1.0
    labelled, _n = ndi.label(mask)  # pyright: ignore[reportGeneralTypeIssues]
    found = []
    for i, sl in enumerate(ndi.find_objects(labelled), 1):
        if sl is None:
            continue
        area = int((labelled[sl] == i).sum())
        if area < min_frac * h * w:
            continue
        y0, y1, x0, x1 = sl[0].start, sl[0].stop, sl[1].start, sl[1].stop
        px = [round(x0 * sx, 1), round(y0 * sy, 1), round(x1 * sx, 1), round(y1 * sy, 1)]
        found.append(
            {
                "label": label,
                "bbox_px": px,
                "bbox_2d": pixels_to_relative([x0, y0, x1, y1], w, h),
                "area_px": int(round(area * sx * sy)),
            }
        )
    found.sort(key=lambda r: -r["area_px"])
    return found[:k]


def _clean(mask: np.ndarray) -> np.ndarray:
    if min(mask.shape) < 16:
        return mask
    return ndi.binary_opening(mask, iterations=1)


def detect_change(
    before: np.ndarray,
    after: np.ndarray,
    *,
    sensor: str,
    scale_to: tuple[int, int] | None = None,
) -> MaskResult:
    """Classical change map between two co-registered dates."""
    if sensor == "sar":
        magnitude, method = log_ratio(before, after), "log_ratio"
    else:
        magnitude, method = cva_magnitude(before, after), "cva"
    threshold, eta = otsu_threshold(magnitude)
    notes: list[str] = []
    finite = np.isfinite(magnitude)
    if eta == 0.0 or not finite.any():
        return MaskResult(method, threshold, eta, 0.0, [], ["change.no_signal"])
    mask = _clean(finite & (magnitude > threshold))
    if eta < 0.5:
        # Otsu always splits; a weak split means "changed" is mostly noise.
        notes.append("change.weak_separation")
    fraction = 100.0 * float(mask.sum()) / float(finite.sum())
    return MaskResult(
        method,
        round(threshold, 4),
        round(eta, 3),
        round(fraction, 2),
        regions(mask, "change", scale_to=scale_to),
        notes,
    )


def sar_water_mask(
    backscatter: np.ndarray, *, scale_to: tuple[int, int] | None = None
) -> MaskResult:
    """Open water in SAR: dark, smooth returns below an Otsu split in dB."""
    from .imaging import to_db

    db = to_db(backscatter)
    threshold, eta = otsu_threshold(db)
    finite = np.isfinite(db)
    if eta == 0.0 or not finite.any():
        return MaskResult("otsu_db", threshold, eta, 0.0, [], ["sar_water.no_signal"])
    water = finite & (db < threshold)
    if min(water.shape) >= 16:
        water = ndi.binary_closing(ndi.binary_opening(water, iterations=1), iterations=1)
    notes = [] if eta >= 0.5 else ["sar_water.not_bimodal"]
    fraction = 100.0 * float(water.sum()) / float(finite.sum())
    return MaskResult(
        "otsu_db",
        round(threshold, 3),
        round(eta, 3),
        round(fraction, 2),
        regions(water, "water", scale_to=scale_to),
        notes,
    )


def sar_bright_targets(
    backscatter: np.ndarray,
    *,
    k_sigma: float = 3.0,
    scale_to: tuple[int, int] | None = None,
    max_targets: int = 20,
) -> MaskResult:
    """Strong point scatterers (ships, vehicles, structures) against clutter.

    A global CFAR: pixels more than `k_sigma` robust deviations above the
    scene's median, in dB. Crude on purpose — its job is to corroborate or
    fail to corroborate a SAR grounding box, never to be shown on its own.
    Works on 8-bit chips too, since a monotonic stretch keeps bright bright.
    """
    from .imaging import to_db

    arr = np.asarray(backscatter, dtype=np.float64)
    finite = np.isfinite(arr)
    values = to_db(arr) if (finite.any() and np.nanmax(arr) > 255) else arr
    v = values[np.isfinite(values)]
    if v.size == 0:
        return MaskResult("cfar", 0.0, 0.0, 0.0, [], ["sar_targets.no_signal"])
    median = float(np.median(v))
    mad = float(np.median(np.abs(v - median))) * 1.4826
    if mad == 0:
        return MaskResult("cfar", median, 0.0, 0.0, [], ["sar_targets.no_signal"])
    threshold = median + k_sigma * mad
    mask = np.isfinite(values) & (values > threshold)
    fraction = 100.0 * float(mask.sum()) / float(v.size)
    boxes = regions(mask, "bright_target", scale_to=scale_to, k=max_targets, min_frac=0.0002)
    return MaskResult("cfar", round(threshold, 3), 0.0, round(fraction, 3), boxes, [])
