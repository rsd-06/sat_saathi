from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import numpy as np
import pytest

from satsaathi_core.raster import inspect, is_tiff


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


def test_a_file_with_no_crs_reports_no_pixel_size(tmp_path):
    """Regression: an ungeoreferenced image claimed one-metre pixels.

    rasterio hands back the identity transform when there is no coordinate
    system, and passing its 1.0 straight through reads as a real ground
    measurement. There is no ground size to report, so None is the answer.
    """
    import numpy as np
    import rasterio

    from satsaathi_core.raster import inspect

    path = tmp_path / "plain.tif"
    with rasterio.open(
        path, "w", driver="GTiff", height=4, width=4, count=3, dtype="uint8"
    ) as dst:
        dst.write(np.zeros((3, 4, 4), dtype="uint8"))

    meta = inspect(path)

    assert meta.is_georeferenced is False
    assert meta.pixel_size is None


class TestGreyscaleChips:
    """8-bit greyscale is what the SAR adapter trained on; colour is optical."""

    def _png(self, path, arr):
        from PIL import Image

        Image.fromarray(arr).save(path)
        return path

    def test_a_grey_png_is_inferred_as_sar_and_says_so(self, tmp_path):
        import numpy as np

        grey = (np.arange(128 * 128) % 251).astype("uint8").reshape(128, 128)
        meta = inspect(self._png(tmp_path / "chip.png", grey))

        assert meta.sensor_type == "sar"
        assert "sensor.inferred_sar_from_greyscale" in meta.warnings
        assert "sensor.unknown_choose_preset" not in meta.warnings

    def test_grey_stored_as_rgb_is_still_grey(self, tmp_path):
        import numpy as np

        grey = (np.arange(64 * 64) % 200).astype("uint8").reshape(64, 64)
        meta = inspect(self._png(tmp_path / "chip.png", np.stack([grey] * 3, -1)))

        assert meta.sensor_type == "sar"

    def test_a_colour_png_stays_optical(self, tmp_path):
        import numpy as np

        rng = np.random.default_rng(0)
        rgb = rng.integers(0, 255, (64, 64, 3), dtype="uint8")
        meta = inspect(self._png(tmp_path / "scene.png", rgb))

        assert meta.sensor_type == "optical"
        assert "sensor.inferred_sar_from_greyscale" not in meta.warnings


class TestIsTiff:
    """The upload gate trusts these bytes, not the filename."""

    def test_a_real_geotiff_is_recognised(self, optical: Path):
        assert is_tiff(optical.read_bytes()[:4])

    @pytest.mark.parametrize(
        "magic",
        ["49492a00", "4d4d002a", "49492b00", "4d4d002b"],
        ids=["le", "be", "big-le", "big-be"],
    )
    def test_every_tiff_flavour_is_recognised(self, magic: str):
        assert is_tiff(bytes.fromhex(magic) + bytes(4))

    @pytest.mark.parametrize(
        "head",
        [
            bytes.fromhex("ffd8ffe0"),  # JPEG
            bytes.fromhex("89504e470d0a1a0a"),  # PNG
            bytes.fromhex("52494646") + bytes(4) + b"WEBP",
            b"GIF89a",
            b"%PDF-1.7",
            bytes.fromhex("49492a"),  # truncated: three bytes is not a header
            b"",
        ],
        ids=["jpeg", "png", "webp", "gif", "pdf", "truncated", "empty"],
    )
    def test_everything_else_is_refused(self, head: bytes):
        assert not is_tiff(head)
