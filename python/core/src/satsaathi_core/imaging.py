"""Turning an uploaded scene into the image a vision-language adapter saw in training.

The optical and SAR adapters were trained on RGB images whose longest side was
at most 512 px, shrunk with bicubic resampling and never enlarged (`fit` in
both training scripts). A different resize, or a SAR chip scaled another way,
is an input the adapter never learned from, so this lives in core and the
tools call it rather than each doing their own thing.

SAR arrives two ways:

  * an 8-bit chip (PNG/JPEG, or a uint8 GeoTIFF), which is what the training
    data was, and passes through untouched apart from grey -> 3 channels;
  * a raw GeoTIFF of backscatter (float or 16-bit), which is converted to dB,
    stretched between its 2nd and 98th percentiles, and quantised to uint8.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

MAX_SIDE = 512
#: Rasters larger than this are decimated on read, then fitted. Reading a
#: 10k x 10k scene whole to end up with 512 px would cost gigabytes of RAM.
READ_MAX_SIDE = 2048

_RASTER_SUFFIXES = {".tif", ".tiff", ".geotiff", ".vrt", ".img", ".jp2"}


def fit(img: Image.Image) -> Image.Image:
    """`fit` from the training scripts, unchanged."""
    img = img.convert("RGB")
    w, h = img.size
    s = MAX_SIDE / max(w, h)
    if s < 1:
        img = img.resize((max(32, round(w * s)), max(32, round(h * s))), Image.BICUBIC)  # pyright: ignore[reportAttributeAccessIssue]
    return img


@dataclass
class PreparedImage:
    image: Image.Image
    #: Size of the scene as uploaded, (width, height). Boxes are relative to
    #: the fitted image, so converting them back needs this, not image.size.
    original_size: tuple[int, int]
    crs: str | None = None
    #: Affine transform as (a, b, c, d, e, f), when the scene has one.
    transform: tuple[float, float, float, float, float, float] | None = None
    notes: list[str] = field(default_factory=list)


def stretch_to_uint8(arr: np.ndarray, lo_pct: float = 2, hi_pct: float = 98) -> np.ndarray:
    """Percentile stretch to 0-255, with nodata going to 0."""
    arr = arr.astype(np.float64)
    finite = np.isfinite(arr)
    if not finite.any():
        return np.zeros(arr.shape, np.uint8)
    lo, hi = np.percentile(arr[finite], [lo_pct, hi_pct])
    scaled = np.clip((arr - lo) / max(hi - lo, 1e-6), 0, 1)
    scaled[~finite] = 0
    return (scaled * 255).astype(np.uint8)


def to_db(arr: np.ndarray) -> np.ndarray:
    """Linear backscatter to decibels. Values already in dB pass through.

    A product holding negative values cannot be linear power, so it is taken
    to be dB already; converting it again would produce NaNs everywhere.
    """
    arr = arr.astype(np.float64)
    finite = np.isfinite(arr)
    if finite.any() and np.nanmin(arr[finite]) < 0:
        return arr
    with np.errstate(divide="ignore", invalid="ignore"):
        out = 10 * np.log10(np.where(arr > 0, arr, np.nan))
    return out


def _read_raster(path: Path, bands: list[int] | None) -> tuple[np.ndarray, Any, Any, str]:
    import rasterio
    from rasterio.enums import Resampling

    with rasterio.open(path) as src:
        indexes = bands or list(range(1, min(src.count, 3) + 1))
        scale = min(1.0, READ_MAX_SIDE / max(src.width, src.height))
        out_shape = (
            len(indexes),
            max(1, round(src.height * scale)),
            max(1, round(src.width * scale)),
        )
        data = src.read(
            indexes,
            out_shape=out_shape,
            masked=True,
            resampling=Resampling.average if scale < 1 else Resampling.nearest,
        )
        if data.dtype == np.uint8:
            # 8-bit imagery is already display-ready; nodata goes to black.
            arr = data.filled(0)
        else:
            arr = data.astype("float64").filled(np.nan)
        crs = src.crs.to_string() if src.crs else None
        return arr, crs, src.transform, str(src.dtypes[0])


def _original_size(path: Path) -> tuple[int, int]:
    if path.suffix.lower() in _RASTER_SUFFIXES:
        import rasterio

        with rasterio.open(path) as src:
            return src.width, src.height
    with Image.open(path) as img:
        return img.size


def _transform_tuple(transform: Any, crs: str | None) -> tuple | None:
    if crs is None or transform is None:
        return None
    return (transform.a, transform.b, transform.c, transform.d, transform.e, transform.f)


def load_optical(path: str | Path, band_map: dict[str, int] | None = None) -> PreparedImage:
    """An optical scene as the optical adapter expects it."""
    path = Path(path)
    size = _original_size(path)
    if path.suffix.lower() not in _RASTER_SUFFIXES:
        with Image.open(path) as img:
            return PreparedImage(fit(img), size)

    band_map = band_map or {}
    rgb_roles = [band_map.get(r) for r in ("red", "green", "blue")]
    notes: list[str] = []
    bands = [b for b in rgb_roles if b] if all(rgb_roles) else None
    if bands is None:
        notes.append("imaging.rgb_from_first_bands")
    arr, crs, transform, dtype = _read_raster(path, bands)
    # Already display-ready 8-bit imagery passes through; anything else is
    # stretched the way true colour is rendered for the index adapters.
    if dtype == "uint8":
        chw = np.nan_to_num(arr).astype(np.uint8)
    else:
        chw = np.stack([stretch_to_uint8(band) for band in arr])
    if chw.shape[0] == 1:
        chw = np.repeat(chw, 3, axis=0)
    image = Image.fromarray(np.moveaxis(chw[:3], 0, -1))
    # Undo the read-time decimation's effect on size bookkeeping: boxes
    # convert against the scene as uploaded, not the decimated array.
    return PreparedImage(fit(image), size, crs, _transform_tuple(transform, crs), notes)


def load_sar(path: str | Path, band_map: dict[str, int] | None = None) -> PreparedImage:
    """A SAR scene as the SAR adapter expects it."""
    path = Path(path)
    size = _original_size(path)
    if path.suffix.lower() not in _RASTER_SUFFIXES:
        with Image.open(path) as img:
            return PreparedImage(fit(img.convert("L")), size, notes=["imaging.sar_8bit_chip"])

    band_map = band_map or {}
    band = band_map.get("vv") or band_map.get("vh") or 1
    arr, crs, transform, dtype = _read_raster(path, [band])
    grey = arr[0]
    if dtype == "uint8":
        img = Image.fromarray(np.nan_to_num(grey).astype(np.uint8))
        notes = ["imaging.sar_8bit_chip"]
    else:
        img = Image.fromarray(stretch_to_uint8(to_db(grey)))
        notes = ["imaging.sar_db_stretch"]
    return PreparedImage(fit(img), size, crs, _transform_tuple(transform, crs), notes)


def read_band_arrays(
    path: str | Path, band_map: dict[str, int], roles: tuple[str, ...], max_pixels: int
) -> dict[str, np.ndarray]:
    """Role -> float32 array (NaN for nodata), for the roles that are mapped.

    Never fills in a missing role: callers check what came back.
    """
    import rasterio
    from rasterio.enums import Resampling

    out: dict[str, np.ndarray] = {}
    with rasterio.open(path) as src:
        scale = min(1.0, (max_pixels / (src.width * src.height)) ** 0.5)
        shape = (max(1, round(src.height * scale)), max(1, round(src.width * scale)))
        for role in roles:
            index = band_map.get(role)
            if not index:
                continue
            data = src.read(
                index,
                out_shape=shape,
                masked=True,
                resampling=Resampling.average if scale < 1 else Resampling.nearest,
            )
            out[role] = data.astype("float32").filled(np.nan)
    return out


def read_single_band(path: str | Path, band: int = 1, max_side: int = READ_MAX_SIDE) -> np.ndarray:
    """One band as float64 with NaN nodata, decimated to at most `max_side`."""
    path = Path(path)
    if path.suffix.lower() not in _RASTER_SUFFIXES:
        with Image.open(path) as img:
            grey = img.convert("L")
            s = min(1.0, max_side / max(grey.size))
            if s < 1:
                size = (round(grey.width * s), round(grey.height * s))
                grey = grey.resize(size, Image.Resampling.BILINEAR)
            return np.asarray(grey, dtype=np.float64)
    arr, _crs, _t, _dtype = _read_raster(path, [band])
    return arr[0].astype(np.float64)


def read_rgb_array(path: str | Path, band_map: dict[str, int] | None = None) -> np.ndarray:
    """H x W x C float64, for change-vector analysis. Decimated like above."""
    path = Path(path)
    if path.suffix.lower() not in _RASTER_SUFFIXES:
        with Image.open(path) as img:
            rgb = img.convert("RGB")
            s = min(1.0, READ_MAX_SIDE / max(rgb.size))
            if s < 1:
                size = (round(rgb.width * s), round(rgb.height * s))
                rgb = rgb.resize(size, Image.Resampling.BILINEAR)
            return np.asarray(rgb, dtype=np.float64)
    band_map = band_map or {}
    roles = [band_map.get(r) for r in ("red", "green", "blue", "nir")]
    bands = [b for b in roles if b] or None
    arr, _crs, _t, _dtype = _read_raster(path, bands)
    return np.moveaxis(arr.astype(np.float64), 0, -1)
