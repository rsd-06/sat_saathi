# The block below is verbatim training code; its PIL constants and scipy
# tuple unpacking run fine but upset the type stubs.
# pyright: reportAttributeAccessIssue=false, reportGeneralTypeIssues=false
"""The spectral-index contract the index adapters were trained on.

The block between the SHARED CONTRACT rules is copied unchanged from
`satquery_ndvi_train.py` (it is identical in `satquery_ndwi_train.py`). The
adapters learned to read images rendered by exactly these functions and
statistics phrased by exactly this text; a "cleaner" re-implementation that
rounds differently or interpolates colours another way would show the model
inputs it never saw. `tests/test_index_contract.py` holds this to fixtures
produced by the training script itself.

Do not edit inside the block. Everything this system adds — mapping band
*roles* onto the Sentinel-2 names the contract uses, and refusing when a band
is missing — lives below it.
"""

from __future__ import annotations

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

# ==============================================================================================
# SHARED CONTRACT (copy into the backend's index module unchanged)
# ==============================================================================================
SIDE = 256  # both images rendered at 256x256 -> 64 visual tokens each
EUROSAT_BANDS = ["B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08", "B09", "B10", "B11", "B12", "B8A"]
S2_L1C_BANDS = ["B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B09", "B10", "B11", "B12"]

# NDVI classes (common agronomic breakpoints)
NDVI_BINS = [(-1.01, 0.0, "water or non-vegetated (NDVI < 0)"), (0.0, 0.2, "bare soil or built-up (0-0.2)"),
             (0.2, 0.4, "sparse vegetation (0.2-0.4)"), (0.4, 0.6, "moderate vegetation (0.4-0.6)"),
             (0.6, 1.01, "dense vegetation (> 0.6)")]
# colour map anchors (value, RGB): brown -> yellow -> light green -> dark green; blue for water
NDVI_LUT = [(-1.0, (40, 70, 160)), (0.0, (165, 120, 80)), (0.2, (230, 210, 120)),
            (0.4, (170, 210, 100)), (0.6, (60, 160, 60)), (1.0, (0, 80, 20))]
# NDWI (McFeeters) classes: > 0 is the standard open-water threshold
NDWI_BINS = [(-1.01, -0.3, "dry land or vegetation (< -0.3)"), (-0.3, 0.0, "moist soil or other non-water (-0.3-0)"),
             (0.0, 0.2, "shallow, turbid water or wet surfaces (0-0.2)"), (0.2, 1.01, "open water (> 0.2)")]
NDWI_LUT = [(-1.0, (120, 80, 40)), (-0.3, (215, 195, 150)), (0.0, (240, 240, 240)),
            (0.2, (120, 180, 230)), (1.0, (10, 40, 140))]

SYSTEM = (
    "You are SatQuery-Spectral, an expert in multispectral satellite analysis. You receive a true-colour "
    "image, an index map, and index statistics computed exactly from the satellite bands. Quote numbers only "
    "from the provided statistics. When asked to locate regions, answer with JSON: "
    '[{"bbox_2d": [x1, y1, x2, y2], "label": "<class>"}] using coordinates normalised to 0-1000.'
)
GRID = [["top-left", "top", "top-right"], ["left", "center", "right"], ["bottom-left", "bottom", "bottom-right"]]


def nd(a, b):
    a = a.astype(np.float32)
    b = b.astype(np.float32)
    den = a + b
    out = np.full(a.shape, np.nan, np.float32)
    ok = np.abs(den) > 1e-6
    out[ok] = (a[ok] - b[ok]) / den[ok]
    return np.clip(out, -1, 1)


def bands_of(arr_hwc: np.ndarray, order: list[str]) -> dict:
    return {name: arr_hwc[..., i] for i, name in enumerate(order)}


def compute_index(name: str, b: dict) -> np.ndarray:
    if name == "NDVI":
        return nd(b["B08"], b["B04"])
    if name == "NDWI":   # McFeeters 1996: green vs NIR
        return nd(b["B03"], b["B08"])
    if name == "MNDWI":  # Xu 2006: green vs SWIR1 (better in built-up areas)
        return nd(b["B03"], b["B11"])
    if name == "NDBI":
        return nd(b["B11"], b["B08"])
    raise KeyError(name)


def true_colour(b: dict, side=SIDE) -> Image.Image:
    rgb = np.stack([b["B04"], b["B03"], b["B02"]], -1).astype(np.float32)
    lo, hi = np.nanpercentile(rgb, [2, 98])
    rgb = np.clip((rgb - lo) / max(hi - lo, 1e-6), 0, 1)
    return Image.fromarray((rgb * 255).astype(np.uint8)).resize((side, side), Image.BICUBIC)


def render_index(x: np.ndarray, lut=NDVI_LUT, side=SIDE) -> Image.Image:
    v = np.nan_to_num(x, nan=-1.0)
    xs = np.array([p[0] for p in lut])
    cols = np.array([p[1] for p in lut], np.float32)
    rgb = np.stack([np.interp(v, xs, cols[:, c]) for c in range(3)], -1)
    return Image.fromarray(rgb.astype(np.uint8)).resize((side, side), Image.NEAREST)


def region_means(x: np.ndarray):
    h, w = x.shape
    out = {}
    for r in range(3):
        for c in range(3):
            cell = x[r * h // 3:(r + 1) * h // 3, c * w // 3:(c + 1) * w // 3]
            out[GRID[r][c]] = float(np.nanmean(cell)) if np.isfinite(cell).any() else float("nan")
    return out


def index_stats(name: str, x: np.ndarray, bins=NDVI_BINS) -> dict:
    v = x[np.isfinite(x)]
    s = {"index": name, "mean": round(float(v.mean()), 3), "median": round(float(np.median(v)), 3),
         "p10": round(float(np.percentile(v, 10)), 3), "p90": round(float(np.percentile(v, 90)), 3),
         "classes": {lab: round(100 * float(((v >= lo) & (v < hi)).mean()), 1) for lo, hi, lab in bins}}
    rm = region_means(x)
    s["highest_region"] = max(rm, key=lambda k: rm[k])
    s["lowest_region"] = min(rm, key=lambda k: rm[k])
    return s


def stats_text(s: dict) -> str:
    cls = "; ".join(f"{k}: {v}%" for k, v in s["classes"].items())
    return (f"{s['index']} statistics (computed from the bands): mean {s['mean']}, median {s['median']}, "
            f"10th-90th percentile {s['p10']} to {s['p90']}. Cover: {cls}. "
            f"Highest in the {s['highest_region']}, lowest in the {s['lowest_region']}.")


def mask_boxes(mask: np.ndarray, label: str, k=3, min_frac=0.015):
    lab, n = ndi.label(ndi.binary_opening(mask, iterations=1) if mask.shape[0] >= 32 else mask)
    h, w = mask.shape
    boxes = []
    for i, sl in enumerate(ndi.find_objects(lab), 1):
        if sl is None:
            continue
        area = int((lab[sl] == i).sum())
        if area < min_frac * h * w:
            continue
        y0, y1, x0, x1 = sl[0].start, sl[0].stop, sl[1].start, sl[1].stop
        boxes.append((area, {"bbox_2d": [round(x0 / w * 1000), round(y0 / h * 1000),
                                         round(x1 / w * 1000), round(y1 / h * 1000)], "label": label}))
    boxes.sort(key=lambda t: -t[0])
    return [b for _, b in boxes[:k]]


def build_prompt(question: str, s: dict) -> str:
    return f"Image 1: true colour. Image 2: {s['index']} map. {stats_text(s)}\nQuestion: {question}"
# ==============================================================================================
# SatSaathi side of the contract
# ==============================================================================================

#: Band role (as mapped by the officer) -> the Sentinel-2 name the contract
#: keys on. The adapters were trained on Sentinel-2; a role is a physical
#: wavelength range, so this is a rename, never a substitution.
ROLE_TO_S2: dict[str, str] = {
    "blue": "B02",
    "green": "B03",
    "red": "B04",
    "nir": "B08",
    "swir1": "B11",
}

#: What each adapter needs to see its training inputs, by role.
INDEX_ROLES: dict[str, tuple[str, ...]] = {
    # true colour (red, green, blue) + NDVI (nir, red)
    "NDVI": ("red", "green", "blue", "nir"),
    # true colour + NDWI (green, nir) + the MNDWI fraction (green, swir1)
    "NDWI": ("red", "green", "blue", "nir", "swir1"),
}


class MissingRolesError(ValueError):
    def __init__(self, index: str, missing: list[str]):
        self.index = index
        self.missing = missing
        super().__init__(f"{index} contract needs {', '.join(missing)}")


def bands_from_roles(arrays_by_role: dict[str, np.ndarray]) -> dict:
    """Rename role-keyed arrays to the contract's Sentinel-2 keys."""
    return {ROLE_TO_S2[role]: arr for role, arr in arrays_by_role.items() if role in ROLE_TO_S2}


def missing_roles(index: str, roles: set[str] | list[str]) -> list[str]:
    return [role for role in INDEX_ROLES[index] if role not in set(roles)]


def true_colour_safe(b: dict) -> dict:
    """Zero-fill nodata before `true_colour`.

    Casting NaN to uint8 inside the contract is undefined behaviour, so the
    same pixels could render differently per platform. The training data had
    no nodata, so no trained behaviour depends on it; indices keep their NaN.
    """
    return {k: np.nan_to_num(v, nan=0.0) for k, v in b.items()}


def mndwi_water_fraction(b: dict) -> float:
    """Percentage of MNDWI > 0 pixels, exactly as the NDWI script phrases it."""
    m = compute_index("MNDWI", b)
    return round(100 * float(np.nanmean(m > 0)), 1)


def ndwi_prompt(question: str, s: dict, mndwi_water: float) -> str:
    """`prompt_for` from satquery_ndwi_train.py."""
    return build_prompt(question, s) + f"\n(MNDWI water fraction: {mndwi_water}%.)"


def prepare(index: str, arrays_by_role: dict[str, np.ndarray], question: str):
    """Everything the adapter is shown, from real bands only.

    Returns (true_colour image, index map image, stats dict, prompt text).
    Raises MissingRolesError rather than approximating an absent band.
    """
    missing = missing_roles(index, list(arrays_by_role))
    if missing:
        raise MissingRolesError(index, missing)
    b = bands_from_roles(arrays_by_role)
    x = compute_index(index, b)
    if index == "NDVI":
        s = index_stats("NDVI", x, NDVI_BINS)
        prompt = build_prompt(question, s)
        lut = NDVI_LUT
    else:
        s = index_stats("NDWI", x, NDWI_BINS)
        prompt = ndwi_prompt(question, s, mndwi_water_fraction(b))
        lut = NDWI_LUT
    return true_colour(true_colour_safe(b)), render_index(x, lut), s, prompt
