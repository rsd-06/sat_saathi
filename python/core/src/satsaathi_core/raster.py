"""Reading what a GeoTIFF actually says about itself.

Header-only, apart from one 64 x 64 sample of 8-bit imagery to tell a
greyscale (SAR) chip from colour: nothing here loads a full raster into
memory, because the inspection runs synchronously inside the upload request. Band *data* is only
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


#: The first four bytes of every TIFF: byte order ("II" little-endian, "MM"
#: big-endian), then the magic number 42 (classic) or 43 (BigTIFF). A GeoTIFF
#: is a TIFF with extra tags, so it starts the same way.
TIFF_MAGIC = tuple(
    bytes.fromhex(h) for h in ("49492a00", "4d4d002a", "49492b00", "4d4d002b")
)


def is_tiff(head: bytes) -> bool:
    """Whether these leading bytes belong to a TIFF.

    The filename is only a claim. A JPEG renamed to ``scene.tif`` has the right
    extension and the wrong bytes, and this is what tells them apart without
    handing the file to a decoder first.
    """
    return bytes(head[:4]) in TIFF_MAGIC


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


def _looks_greyscale(src: rasterio.DatasetReader) -> bool:
    """One 8-bit band, or three identical ones, on a small decimated read.

    The only data read during inspection, capped at 64 x 64 pixels.
    """
    if src.count == 1:
        return True
    side = 64
    shape = (3, min(side, src.height), min(side, src.width))
    try:
        sample = src.read([1, 2, 3], out_shape=shape)
    except Exception:  # noqa: BLE001 - an unreadable sample is not greyscale
        return False
    return bool((sample[0] == sample[1]).all() and (sample[1] == sample[2]).all())


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
        if dtype == "uint8" and src.count in (1, 3) and _looks_greyscale(src):
            # An 8-bit greyscale chip is what the SAR adapter was trained on,
            # and in this product's scope (SAR and optical) far more likely
            # SAR than panchromatic. Said out loud, so a wrong guess is
            # visible and a band preset overrides it.
            sensor = "sar"
            warnings = [w for w in warnings if w != "sensor.unknown_choose_preset"]
            warnings.append("sensor.inferred_sar_from_greyscale")

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
