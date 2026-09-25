"""Spectral indices, computed from the bands the officer mapped.

Three rules hold throughout:

1. A band is never substituted. If the mapping lacks a band an index needs,
   the index is unavailable and says which band is missing — it is not
   approximated from whatever else is present.
2. Nodata and divide-by-zero produce NaN, which is excluded from statistics
   rather than silently counted as zero.
3. Area is measured on the ground, not in pixels. A geographic CRS has no
   constant pixel area, so it is reprojected to an equal-area projection
   before any hectare figure is produced.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import rasterio
from rasterio.warp import transform_bounds

IndexName = Literal["ndvi", "ndwi", "lswi"]

#: index -> the band roles it requires, in formula order (positive, negative).
INDEX_BANDS: dict[IndexName, tuple[str, str]] = {
    "ndvi": ("nir", "red"),
    "ndwi": ("green", "nir"),
    "lswi": ("nir", "swir1"),
}

_HECTARE_M2 = 10_000.0


class MissingBandError(ValueError):
    def __init__(self, index: IndexName, missing: list[str]):
        self.index = index
        self.missing = missing
        super().__init__(f"{index} needs {', '.join(missing)}")


@dataclass(frozen=True)
class IndexResult:
    name: IndexName
    mean: float
    minimum: float
    maximum: float
    valid_pixels: int
    threshold: float
    above_threshold_pixels: int
    above_threshold_pct: float
    area_above_threshold_ha: float | None
    """None when the raster carries no CRS, since ground area is unknowable."""
    pixel_area_m2: float | None


def available_indices(band_map: dict[str, int]) -> dict[IndexName, list[str]]:
    """Which indices are computable, and for the rest, what is missing."""
    unavailable: dict[IndexName, list[str]] = {}
    for index, needed in INDEX_BANDS.items():
        missing = [role for role in needed if role not in band_map]
        if missing:
            unavailable[index] = missing
    return unavailable


def normalised_difference(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """(a - b) / (a + b), with a zero denominator yielding NaN, not inf."""
    a = a.astype("float64")
    b = b.astype("float64")
    denominator = a + b
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(denominator == 0, np.nan, (a - b) / denominator)
    return out


def _pixel_area_m2(src: rasterio.DatasetReader) -> float | None:
    """Ground area of one pixel, via an equal-area CRS when needed."""
    if src.crs is None:
        return None
    try:
        # Imported here: a host that refuses pyproj's native module (Windows
        # Smart App Control has) still runs everything but ground area.
        from pyproj import CRS, Geod
    except ImportError:
        return None

    crs = CRS.from_user_input(src.crs)
    width_deg, height_deg = abs(src.transform.a), abs(src.transform.e)

    if not crs.is_geographic:
        # Projected CRS: linear units, so pixel area is a direct product.
        factor = crs.axis_info[0].unit_conversion_factor if crs.axis_info else 1.0
        return width_deg * height_deg * factor * factor

    # Geographic CRS: degrees are not a length. Measure the actual footprint
    # on the ellipsoid and divide by the pixel count.
    west, south, east, north = transform_bounds(src.crs, "EPSG:4326", *src.bounds)
    geod = Geod(ellps="WGS84")
    area_m2, _ = geod.polygon_area_perimeter(
        [west, east, east, west], [south, south, north, north]
    )
    return abs(area_m2) / (src.width * src.height)


def compute(
    path: str | Path,
    index: IndexName,
    band_map: dict[str, int],
    *,
    threshold: float = 0.0,
    max_pixels: int = 4096 * 4096,
) -> IndexResult:
    """Compute one index over a whole raster.

    `band_map` maps a role ("nir") to a 1-based band number. Raises
    MissingBandError when the mapping cannot support the index, and
    ValueError when the raster exceeds `max_pixels`.
    """
    positive_role, negative_role = INDEX_BANDS[index]
    missing = [r for r in (positive_role, negative_role) if r not in band_map]
    if missing:
        raise MissingBandError(index, missing)

    with rasterio.open(path) as src:
        if src.width * src.height > max_pixels:
            raise ValueError(
                f"raster has {src.width * src.height} pixels, over the "
                f"{max_pixels} cap"
            )

        positive = src.read(band_map[positive_role], masked=True)
        negative = src.read(band_map[negative_role], masked=True)
        pixel_area = _pixel_area_m2(src)

    values = normalised_difference(
        positive.filled(np.nan), negative.filled(np.nan)
    )

    valid = np.isfinite(values)
    valid_count = int(valid.sum())
    if valid_count == 0:
        return IndexResult(
            name=index,
            mean=float("nan"),
            minimum=float("nan"),
            maximum=float("nan"),
            valid_pixels=0,
            threshold=threshold,
            above_threshold_pixels=0,
            above_threshold_pct=0.0,
            area_above_threshold_ha=0.0 if pixel_area else None,
            pixel_area_m2=pixel_area,
        )

    above = int((values[valid] > threshold).sum())
    area_ha = (
        (above * pixel_area) / _HECTARE_M2 if pixel_area is not None else None
    )

    return IndexResult(
        name=index,
        mean=float(np.nanmean(values)),
        minimum=float(np.nanmin(values)),
        maximum=float(np.nanmax(values)),
        valid_pixels=valid_count,
        threshold=threshold,
        above_threshold_pixels=above,
        above_threshold_pct=100.0 * above / valid_count,
        area_above_threshold_ha=area_ha,
        pixel_area_m2=pixel_area,
    )
