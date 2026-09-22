from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from satsaathi_core.indices import (
    MissingBandError,
    available_indices,
    compute,
    normalised_difference,
)

# Blue=1, Green=2, Red=3, NIR=4 in the `optical` fixture.
BANDS = {"blue": 1, "green": 2, "red": 3, "nir": 4}


def test_normalised_difference_matches_hand_calculation():
    a = np.array([[0.5, 0.2]])
    b = np.array([[0.1, 0.2]])
    # (0.5-0.1)/(0.5+0.1) = 0.6667 ; (0.2-0.2)/(0.4) = 0.0
    assert normalised_difference(a, b).ravel() == pytest.approx([2 / 3, 0.0])


def test_zero_denominator_is_nan_not_infinity():
    out = normalised_difference(np.array([0.0]), np.array([0.0]))
    assert np.isnan(out).all()
    assert not np.isinf(out).any()


def test_ndvi_over_a_known_raster(optical: Path):
    result = compute(optical, "ndvi", BANDS, threshold=0.2)

    # 15 pixels are NIR 0.50 / Red 0.10 -> 0.6667. One water pixel is
    # NIR 0.02 / Red 0.10 -> -0.6667.
    assert result.valid_pixels == 16
    assert result.maximum == pytest.approx(2 / 3, abs=1e-6)
    assert result.minimum == pytest.approx(-2 / 3, abs=1e-6)
    assert result.above_threshold_pixels == 15
    assert result.above_threshold_pct == pytest.approx(93.75)


def test_ndwi_finds_the_water_pixel(optical: Path):
    # NDWI = (green - nir) / (green + nir); only the water pixel is positive.
    result = compute(optical, "ndwi", BANDS, threshold=0.0)

    assert result.above_threshold_pixels == 1
    assert result.maximum == pytest.approx((0.20 - 0.02) / (0.20 + 0.02), abs=1e-6)


def test_area_uses_true_pixel_size_in_a_projected_crs(optical: Path):
    # 10 m pixels -> 100 m2 each. 15 pixels above threshold -> 1500 m2 -> 0.15 ha.
    result = compute(optical, "ndvi", BANDS, threshold=0.2)

    assert result.pixel_area_m2 == pytest.approx(100.0)
    assert result.area_above_threshold_ha == pytest.approx(0.15)


def test_area_is_none_without_a_crs(tmp_path: Path, make_raster):
    path = make_raster(
        tmp_path / "nocrs.tif",
        [np.full((2, 2), v, dtype="float32") for v in (0.1, 0.2, 0.1, 0.5)],
        crs=None,
    )
    result = compute(path, "ndvi", BANDS)

    assert result.pixel_area_m2 is None
    assert result.area_above_threshold_ha is None
    # The index itself is still perfectly computable.
    assert result.valid_pixels == 4


def test_geographic_crs_area_is_measured_on_the_ellipsoid(
    tmp_path: Path, make_raster
):
    # A degree is not a length; naive width*height would give nonsense.
    path = make_raster(
        tmp_path / "geo.tif",
        [np.full((10, 10), v, dtype="float32") for v in (0.1, 0.2, 0.1, 0.5)],
        crs="EPSG:4326",
        pixel_size=0.001,
        origin=(88.0, 23.0),
    )
    result = compute(path, "ndvi", BANDS, threshold=0.0)

    assert result.pixel_area_m2 is not None
    # 0.001 degrees near 23 degrees N is roughly 111 m by 102 m.
    assert 9_000 < result.pixel_area_m2 < 13_000


def test_nodata_pixels_are_excluded_not_counted_as_zero(
    tmp_path: Path, make_raster
):
    nir = np.full((2, 2), 0.5, dtype="float32")
    nir[0, 0] = -9999.0
    red = np.full((2, 2), 0.1, dtype="float32")
    red[0, 0] = -9999.0
    path = make_raster(
        tmp_path / "nodata.tif",
        [np.zeros((2, 2), dtype="float32"), np.zeros((2, 2), dtype="float32"), red, nir],
        nodata=-9999.0,
    )
    result = compute(path, "ndvi", BANDS)

    assert result.valid_pixels == 3
    assert result.mean == pytest.approx(2 / 3, abs=1e-6)


def test_refuses_an_index_whose_band_is_missing(optical: Path):
    # No SWIR band was mapped, so LSWI is not computable.
    with pytest.raises(MissingBandError) as excinfo:
        compute(optical, "lswi", BANDS)

    assert excinfo.value.missing == ["swir1"]


def test_available_indices_reports_what_is_missing():
    unavailable = available_indices({"red": 3, "nir": 4})

    assert "ndvi" not in unavailable
    assert unavailable["ndwi"] == ["green"]
    assert unavailable["lswi"] == ["swir1"]


def test_refuses_a_raster_over_the_pixel_cap(optical: Path):
    with pytest.raises(ValueError, match="cap"):
        compute(optical, "ndvi", BANDS, max_pixels=4)
