"""Whether a set of images can actually be analysed together.

Every check returns a message key and parameters, never a sentence: the API
does not send user-facing English, the frontend localises. A check is `fail`
only when the analysis genuinely cannot proceed; anything the officer should
look at but which does not block is `warn`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from shapely.geometry import shape
from shapely.ops import unary_union

from .raster import RasterMetadata

CheckStatus = Literal["pass", "warn", "fail"]
InputMode = Literal["single", "fusion", "change"]


@dataclass(frozen=True)
class Check:
    key: str
    status: CheckStatus
    params: dict[str, object]


def _as_date(value: datetime | date | None) -> date | None:
    if value is None:
        return None
    return value.date() if isinstance(value, datetime) else value


def overlap_pct(a: RasterMetadata, b: RasterMetadata) -> float | None:
    """Intersection as a percentage of the smaller footprint."""
    if not (a.footprint and b.footprint):
        return None
    ga, gb = shape(a.footprint), shape(b.footprint)
    if ga.is_empty or gb.is_empty:
        return None
    intersection = ga.intersection(gb).area
    smaller = min(ga.area, gb.area)
    if smaller == 0:
        return None
    return 100.0 * intersection / smaller


def _crs_check(a: RasterMetadata, b: RasterMetadata) -> Check:
    if a.crs is None or b.crs is None:
        return Check("checks.crs", "fail", {"a": a.crs, "b": b.crs})
    if a.crs == b.crs:
        return Check("checks.crs", "pass", {"crs": a.crs})
    # Different CRSs are reprojectable, so this warns rather than blocks.
    return Check("checks.crs", "warn", {"a": a.crs, "b": b.crs})


def _overlap_check(a: RasterMetadata, b: RasterMetadata, minimum: float) -> Check:
    pct = overlap_pct(a, b)
    if pct is None:
        return Check("checks.overlap", "fail", {"reason": "no_footprint"})
    status: CheckStatus = "pass" if pct >= minimum else "fail"
    return Check(
        "checks.overlap", status, {"pct": round(pct, 1), "minimum": minimum}
    )


def _resolution_check(
    a: RasterMetadata, b: RasterMetadata, tolerance: float
) -> Check:
    # A file with no coordinate system has no ground resolution to compare,
    # so this warns rather than inventing a ratio from pixel counts.
    if a.pixel_size is None or b.pixel_size is None:
        return Check("checks.resolution", "warn", {})
    ax, bx = a.pixel_size[0], b.pixel_size[0]
    if ax == 0 or bx == 0:
        return Check("checks.resolution", "warn", {"a": ax, "b": bx})
    ratio = max(ax, bx) / min(ax, bx)
    # Differing resolutions are resampled, not rejected.
    status: CheckStatus = "pass" if ratio <= tolerance else "warn"
    return Check(
        "checks.resolution",
        status,
        {"a": ax, "b": bx, "ratio": round(ratio, 2), "tolerance": tolerance},
    )


def check_fusion(
    optical: RasterMetadata,
    sar: RasterMetadata,
    *,
    min_overlap_pct: float = 90.0,
    resolution_tolerance: float = 4.0,
) -> list[Check]:
    checks: list[Check] = []

    if optical.sensor_type != "optical" or sar.sensor_type != "sar":
        checks.append(
            Check(
                "checks.sensorRoles",
                "fail",
                {"optical": optical.sensor_type, "sar": sar.sensor_type},
            )
        )
    else:
        checks.append(Check("checks.sensorRoles", "pass", {}))

    checks.append(_crs_check(optical, sar))
    checks.append(_overlap_check(optical, sar, min_overlap_pct))
    checks.append(_resolution_check(optical, sar, resolution_tolerance))
    return checks


def check_change(
    before: RasterMetadata,
    after: RasterMetadata,
    *,
    min_overlap_pct: float = 90.0,
    resolution_tolerance: float = 4.0,
) -> list[Check]:
    checks: list[Check] = []

    if before.sensor_type != after.sensor_type:
        checks.append(
            Check(
                "checks.sensorFamily",
                "warn",
                {"before": before.sensor_type, "after": after.sensor_type},
            )
        )
    else:
        checks.append(
            Check("checks.sensorFamily", "pass", {"sensor": before.sensor_type})
        )

    b_date, a_date = _as_date(before.acquired_at), _as_date(after.acquired_at)
    if b_date is None or a_date is None:
        checks.append(Check("checks.dates", "fail", {"reason": "unknown_date"}))
    elif b_date >= a_date:
        checks.append(
            Check(
                "checks.dates",
                "fail",
                {"before": b_date.isoformat(), "after": a_date.isoformat()},
            )
        )
    else:
        checks.append(
            Check(
                "checks.dates",
                "pass",
                {"before": b_date.isoformat(), "after": a_date.isoformat()},
            )
        )

    checks.append(_crs_check(before, after))
    checks.append(_overlap_check(before, after, min_overlap_pct))
    checks.append(_resolution_check(before, after, resolution_tolerance))
    return checks


def check_single(asset: RasterMetadata) -> list[Check]:
    """A single image is analysable unless it cannot be read at all.

    A missing coordinate system warns rather than blocks: indices are still
    computable from the pixels, and the only casualty is ground area, which is
    reported as unavailable rather than guessed. Blocking here would reject
    the PNG and JPEG benchmark datasets the problem statement allows.
    """
    if not asset.is_georeferenced:
        return [Check("checks.georeferenced", "warn", {})]
    return [Check("checks.georeferenced", "pass", {"crs": asset.crs})]


def blocked(checks: list[Check]) -> bool:
    return any(c.status == "fail" for c in checks)


def union_footprint(metas: list[RasterMetadata]) -> dict | None:
    geoms = [shape(m.footprint) for m in metas if m.footprint]
    if not geoms:
        return None
    from shapely.geometry import mapping

    return mapping(unary_union(geoms))
