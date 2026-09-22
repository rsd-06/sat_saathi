"""Tiny real GeoTIFFs, written per-test.

Synthetic rather than checked-in binaries: the maths under test is exact, so
the inputs need to be exact too, and a four-pixel raster with known values
makes an index assertion something you can verify by hand.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin


def write_raster(
    path: Path,
    bands: list[np.ndarray],
    *,
    crs: str | None = "EPSG:32645",
    pixel_size: float = 10.0,
    origin: tuple[float, float] = (500000.0, 2700000.0),
    descriptions: list[str] | None = None,
    dtype: str = "float32",
    nodata: float | None = None,
    tags: dict[str, str] | None = None,
) -> Path:
    height, width = bands[0].shape
    transform = from_origin(origin[0], origin[1], pixel_size, pixel_size)

    profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": len(bands),
        "dtype": dtype,
        "transform": transform,
    }
    if crs is not None:
        profile["crs"] = crs
    if nodata is not None:
        profile["nodata"] = nodata

    with rasterio.open(path, "w", **profile) as dst:
        for i, band in enumerate(bands, start=1):
            dst.write(band.astype(dtype), i)
            if descriptions:
                dst.set_band_description(i, descriptions[i - 1])
        if tags:
            dst.update_tags(**tags)
    return path


@pytest.fixture
def make_raster():
    """Hands tests the writer above, so they can build odd cases inline."""
    return write_raster


@pytest.fixture
def optical(tmp_path: Path) -> Path:
    """4x4 optical scene, bands ordered Blue, Green, Red, NIR."""
    blue = np.full((4, 4), 0.05, dtype="float32")
    green = np.full((4, 4), 0.12, dtype="float32")
    red = np.full((4, 4), 0.10, dtype="float32")
    nir = np.full((4, 4), 0.50, dtype="float32")
    # One pixel is water: high green, low NIR.
    green[0, 0], nir[0, 0] = 0.20, 0.02
    return write_raster(
        tmp_path / "optical.tif",
        [blue, green, red, nir],
        descriptions=["Blue", "Green", "Red", "NIR"],
        tags={"ACQUISITION_DATE": "2026-09-12"},
    )


@pytest.fixture
def sar(tmp_path: Path) -> Path:
    vv = np.full((4, 4), -12.0, dtype="float32")
    vh = np.full((4, 4), -18.0, dtype="float32")
    return write_raster(
        tmp_path / "sar.tif",
        [vv, vh],
        descriptions=["VV", "VH"],
        tags={"ACQUISITION_DATE": "2026-09-04"},
    )
