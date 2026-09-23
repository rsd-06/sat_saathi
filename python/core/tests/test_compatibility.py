from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from satsaathi_core.compatibility import (
    blocked,
    check_change,
    check_fusion,
    check_single,
    overlap_pct,
)
from satsaathi_core.raster import inspect


def by_key(checks, key):
    return next(c for c in checks if c.key == key)


def test_identical_footprints_overlap_fully(optical: Path, sar: Path):
    assert overlap_pct(inspect(optical), inspect(sar)) == pytest.approx(100.0, abs=0.1)


def test_fusion_passes_for_an_aligned_optical_sar_pair(optical: Path, sar: Path):
    checks = check_fusion(inspect(optical), inspect(sar))

    assert not blocked(checks)
    assert by_key(checks, "checks.sensorRoles").status == "pass"
    assert by_key(checks, "checks.overlap").status == "pass"


def test_fusion_fails_when_both_images_are_optical(optical: Path):
    meta = inspect(optical)
    checks = check_fusion(meta, meta)

    assert blocked(checks)
    assert by_key(checks, "checks.sensorRoles").status == "fail"


def test_fusion_fails_when_footprints_barely_overlap(
    tmp_path: Path, make_raster, optical: Path
):
    far = make_raster(
        tmp_path / "far.tif",
        [np.full((4, 4), 0.1, dtype="float32")] * 2,
        descriptions=["VV", "VH"],
        origin=(900000.0, 2700000.0),  # ~400 km east
    )
    checks = check_fusion(inspect(optical), inspect(far))

    overlap = by_key(checks, "checks.overlap")
    assert overlap.status == "fail"
    assert overlap.params["pct"] == 0.0
    assert blocked(checks)


def test_differing_crs_warns_rather_than_blocks(
    tmp_path: Path, make_raster, optical: Path
):
    # A reprojection is routine, so this must not stop the analysis.
    other = make_raster(
        tmp_path / "utm44.tif",
        [np.full((4, 4), 0.1, dtype="float32")] * 2,
        descriptions=["VV", "VH"],
        crs="EPSG:32644",
    )
    check = by_key(check_fusion(inspect(optical), inspect(other)), "checks.crs")

    assert check.status == "warn"
    assert "32645" in str(check.params["a"])
    assert "32644" in str(check.params["b"])


def test_change_pair_must_be_in_date_order(optical: Path, sar: Path):
    before, after = inspect(sar), inspect(optical)  # 09-04 then 09-12
    assert by_key(check_change(before, after), "checks.dates").status == "pass"

    # Reversed, the same pair is rejected.
    reversed_checks = check_change(after, before)
    assert by_key(reversed_checks, "checks.dates").status == "fail"
    assert blocked(reversed_checks)


def test_change_fails_when_a_date_is_unknown(
    tmp_path: Path, make_raster, optical: Path
):
    undated = make_raster(
        tmp_path / "undated.tif",
        [np.full((4, 4), 0.1, dtype="float32")] * 4,
    )
    checks = check_change(inspect(optical), inspect(undated))

    dates = by_key(checks, "checks.dates")
    assert dates.status == "fail"
    assert dates.params["reason"] == "unknown_date"


def test_resolution_mismatch_warns_within_reason(
    tmp_path: Path, make_raster, optical: Path
):
    coarse = make_raster(
        tmp_path / "coarse.tif",
        [np.full((4, 4), 0.1, dtype="float32")] * 2,
        descriptions=["VV", "VH"],
        pixel_size=60.0,
    )
    check = by_key(
        check_fusion(inspect(optical), inspect(coarse)), "checks.resolution"
    )

    assert check.status == "warn"
    assert check.params["ratio"] == pytest.approx(6.0)


def test_single_image_without_a_crs_warns_but_is_not_blocked(
    tmp_path: Path, make_raster, optical: Path
):
    assert not blocked(check_single(inspect(optical)))

    plain = make_raster(
        tmp_path / "plain.tif",
        [np.zeros((2, 2), dtype="float32")] * 3,
        crs=None,
    )
    checks = check_single(inspect(plain))

    # Indices remain computable; only ground area is lost, and that is
    # reported as unavailable rather than guessed.
    assert not blocked(checks)
    assert by_key(checks, "checks.georeferenced").status == "warn"


def test_checks_carry_keys_and_params_not_sentences(optical: Path, sar: Path):
    # The API must never ship user-facing English; the frontend localises.
    for check in check_fusion(inspect(optical), inspect(sar)):
        assert check.key.startswith("checks.")
        assert isinstance(check.params, dict)
        assert " " not in check.key
