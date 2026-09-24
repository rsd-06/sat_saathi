"""Reading what a GeoTIFF actually says about itself.

Header-only: nothing here loads a full raster into memory, because the
inspection runs synchronously inside the upload request. Band *data* is only
touched by the index computation in `indices.py`, which has its own size cap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Literal

import rasterio
from rasterio.warp import transform_geom
from shapely.geometry import box, mapping, shape
from shapely.geometry.base import BaseGeometry

SensorType = Literal["optical", "sar", "unknown"]

# Tag keys different providers use for the acquisition instant.
_DATE_TAGS = (
    "ACQUISITIONDATETIME",
    "ACQUISITION_DATE",
    "DATE_ACQUIRED",
    "TIFFTAG_DATETIME",
    "SENSING_TIME",
    "PRODUCT_SCENE_RASTER_START_TIME",
)

_SAR_POL = {"VV", "VH", "HH", "HV"}


@dataclass(frozen=True)
class BandInfo:
    index: int
    description: str | None
    dtype: str
    nodata: float | None
    """Role is assigned later by a sensor preset or by hand; never guessed."""
    role: str | None = None


@dataclass(frozen=True)
class RasterMetadata:
    driver: str
    width: int
    height: int
    band_count: int
    dtype: str
    crs: str | None
    #: Ground size of one pixel, or None when the file has no coordinate
    #: system. Without one, rasterio reports the identity transform, and
    #: passing that on as 1.0 would read as one-metre pixels.
    pixel_size: tuple[float, float] | None
    bands: list[BandInfo]
    sensor_type: SensorType
    acquired_at: datetime | date | None
    footprint: dict | None
    """Footprint in EPSG:4326, as GeoJSON, or None when not georeferenced."""
    warnings: list[str] = field(default_factory=list)

    @property
    def is_georeferenced(self) -> bool:
        return self.crs is not None and self.footprint is not None


def _parse_date(raw: str) -> datetime | date | None:
    text = raw.strip().replace("Z", "+00:00")
    for fmt in (
        "%Y:%m:%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%Y%m%d",
    ):
        try:
            return datetime.strptime(text[: len(fmt) + 6], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _acquired_at(tags: dict[str, str]) -> datetime | date | None:
    upper = {k.upper(): v for k, v in tags.items()}
    for key in _DATE_TAGS:
        if key in upper and upper[key]:
            parsed = _parse_date(upper[key])
            if parsed:
                return parsed
    return None


def _detect_sensor(
    band_count: int, descriptions: list[str | None], dtype: str
) -> tuple[SensorType, list[str]]:
    """Heuristic only. When it cannot tell, it says so rather than guessing."""
    warnings: list[str] = []
    labels = {(d or "").strip().upper() for d in descriptions}

    if labels & _SAR_POL:
        return "sar", warnings
    if band_count <= 2 and (dtype.startswith("float") or dtype.startswith("complex")):
        warnings.append("sensor.inferred_sar_from_dtype")
        return "sar", warnings
    if 3 <= band_count <= 13:
        return "optical", warnings

    warnings.append("sensor.unknown_choose_preset")
    return "unknown", warnings


def _footprint_4326(src: rasterio.DatasetReader) -> dict | None:
    if src.crs is None:
        return None
    geom = mapping(box(*src.bounds))
    if src.crs.to_epsg() == 4326:
        return geom
    return transform_geom(src.crs, "EPSG:4326", geom, precision=8)


def inspect(path: str | Path) -> RasterMetadata:
    """Read headers only. Raises rasterio.RasterioIOError on an unreadable file."""
    with rasterio.open(path) as src:
        descriptions = list(src.descriptions)
        dtype = src.dtypes[0] if src.dtypes else "unknown"
        sensor, warnings = _detect_sensor(src.count, descriptions, dtype)

        bands = [
            BandInfo(
                index=i,
                description=descriptions[i - 1],
                dtype=src.dtypes[i - 1],
                nodata=src.nodatavals[i - 1],
            )
            for i in range(1, src.count + 1)
        ]

        crs = src.crs.to_string() if src.crs else None
        if crs is None:
            warnings.append("raster.not_georeferenced")

        transform = src.transform
        pixel_size = (
            (abs(transform.a), abs(transform.e)) if crs is not None else None
        )

        return RasterMetadata(
            driver=src.driver,
            width=src.width,
            height=src.height,
            band_count=src.count,
            dtype=dtype,
            crs=crs,
            pixel_size=pixel_size,
            bands=bands,
            sensor_type=sensor,
            acquired_at=_acquired_at(src.tags()),
            footprint=_footprint_4326(src),
            warnings=warnings,
        )


def footprint_geometry(meta: RasterMetadata) -> BaseGeometry | None:
    return shape(meta.footprint) if meta.footprint else None
