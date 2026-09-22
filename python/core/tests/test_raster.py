from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import numpy as np
import pytest

from satsaathi_core.raster import inspect


def test_reads_shape_and_bands(optical: Path):
    meta = inspect(optical)

    assert (meta.width, meta.height) == (4, 4)
    assert meta.band_count == 4
    assert meta.driver == "GTiff"
    assert [b.description for b in meta.bands] == ["Blue", "Green", "Red", "NIR"]
    assert [b.index for b in meta.bands] == [1, 2, 3, 4]


def test_reads_crs_and_pixel_size(optical: Path):
    meta = inspect(optical)

    assert meta.crs is not None and "32645" in meta.crs
    assert meta.pixel_size == pytest.approx((10.0, 10.0))


def test_reprojects_footprint_to_wgs84(optical: Path):
    meta = inspect(optical)

    assert meta.footprint is not None
    assert meta.footprint["type"] == "Polygon"
    lons = [c[0] for c in meta.footprint["coordinates"][0]]
    lats = [c[1] for c in meta.footprint["coordinates"][0]]
    # UTM 45N easting 500000 is the zone's central meridian: 87°E.
    assert all(86 < lon < 88 for lon in lons)
    assert all(23 < lat < 25 for lat in lats)
    assert meta.is_georeferenced


def test_detects_optical_and_sar(optical: Path, sar: Path):
    assert inspect(optical).sensor_type == "optical"
    assert inspect(sar).sensor_type == "sar"


def test_reads_acquisition_date(optical: Path):
    meta = inspect(optical)
    acquired = meta.acquired_at
    assert acquired is not None
    as_date = acquired.date() if isinstance(acquired, datetime) else acquired
    assert as_date == date(2026, 9, 12)


def test_flags_a_raster_with_no_crs(tmp_path: Path, make_raster):
    path = make_raster(
        tmp_path / "plain.tif",
        [np.zeros((2, 2), dtype="float32")] * 3,
        crs=None,
    )
    meta = inspect(path)

    assert meta.crs is None
    assert meta.footprint is None
    assert meta.is_georeferenced is False
    assert "raster.not_georeferenced" in meta.warnings


def test_says_unknown_rather_than_guessing_an_odd_band_count(tmp_path: Path, make_raster):
    path = make_raster(
        tmp_path / "odd.tif",
        [np.zeros((2, 2), dtype="uint8")] * 20,
        dtype="uint8",
    )
    meta = inspect(path)

    assert meta.sensor_type == "unknown"
    assert "sensor.unknown_choose_preset" in meta.warnings


def test_bands_carry_no_role_until_one_is_assigned(optical: Path):
    # Band roles decide which indices are computable, so they are never
    # inferred from position — a preset or the officer assigns them.
    assert all(b.role is None for b in inspect(optical).bands)
