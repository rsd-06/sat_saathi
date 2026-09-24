"""Classical change maps and SAR water masks."""

from __future__ import annotations

import numpy as np

from satsaathi_core.change import detect_change, otsu_threshold, sar_water_mask


def _scene(seed=0, side=128):
    rng = np.random.default_rng(seed)
    return rng.uniform(0.2, 0.4, (side, side, 3))


def test_otsu_splits_two_populations():
    values = np.concatenate([np.full(500, 1.0), np.full(500, 9.0)])

    threshold, eta = otsu_threshold(values)

    assert 1.0 < threshold < 9.0
    assert eta > 0.9


def test_a_flat_image_has_no_signal():
    _t, eta = otsu_threshold(np.ones(100))

    assert eta == 0.0


def test_optical_change_finds_the_new_block():
    before = _scene()
    after = before.copy()
    after[30:60, 70:110] = 0.95  # a new bright roof

    result = detect_change(before, after, sensor="optical")

    assert result.method == "cva"
    assert result.boxes, result
    x1, y1, x2, y2 = result.boxes[0]["bbox_px"]
    assert 65 <= x1 <= 75 and 105 <= x2 <= 115
    assert 25 <= y1 <= 35 and 55 <= y2 <= 65
    assert 5 < result.fraction_pct < 15


def test_boxes_are_reported_on_the_uploaded_scene():
    before = _scene()
    after = before.copy()
    after[0:64, 0:64] = 0.95

    result = detect_change(before, after, sensor="optical", scale_to=(1280, 1280))

    # Computed on a 128 px copy of a 1280 px upload: ten times larger.
    assert result.boxes[0]["bbox_px"][2] >= 600


def test_identical_dates_report_no_change():
    before = _scene()

    result = detect_change(before, before.copy(), sensor="optical")

    assert result.fraction_pct == 0.0
    assert result.boxes == []
    assert "change.no_signal" in result.notes


def test_sar_uses_log_ratio():
    rng = np.random.default_rng(1)
    before = rng.gamma(4, 0.05, (128, 128))
    after = before.copy()
    after[10:40, 10:40] *= 20  # a new strong scatterer

    result = detect_change(before, after, sensor="sar")

    assert result.method == "log_ratio"
    assert result.boxes[0]["bbox_px"][:2] == [10.0, 10.0]


def test_sar_water_is_the_dark_part():
    rng = np.random.default_rng(2)
    land = rng.gamma(4, 0.05, (128, 128))  # ~ -7 dB
    land[64:, :] = rng.gamma(4, 0.001, (64, 128))  # calm water, ~ -24 dB

    result = sar_water_mask(land)

    assert 45 < result.fraction_pct < 55
    assert result.boxes[0]["label"] == "water"
    assert result.boxes[0]["bbox_px"][1] >= 60
    assert result.notes == []


def test_bright_targets_find_a_ship_on_dark_sea():
    from satsaathi_core.change import sar_bright_targets

    rng = np.random.default_rng(3)
    sea = rng.normal(30, 4, (256, 256)).clip(0, 255)
    sea[100:112, 150:170] = 240  # a vessel

    result = sar_bright_targets(sea)

    assert result.boxes
    x1, y1, x2, y2 = result.boxes[0]["bbox_px"]
    assert (x1, y1, x2, y2) == (150.0, 100.0, 170.0, 112.0)
