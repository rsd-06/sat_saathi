"""The index adapters must see exactly what training rendered.

Fixtures in infra/fixtures/golden/indices were produced by executing the
SHARED CONTRACT block cut from satquery_ndvi_train.py / satquery_ndwi_train.py
(see make_fixtures.py there). Same bands in, identical pixels and identical
text out — anything less and the adapter is reading images it never saw.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from satsaathi_core import index_contract as ic

GOLDEN = Path(__file__).resolve().parents[3] / "infra" / "fixtures" / "golden" / "indices"
CASES = sorted(p for p in GOLDEN.glob("seed*") if p.is_dir())


def _pixels(img: Image.Image) -> bytes:
    return img.convert("RGB").tobytes()


def _golden_pixels(path: Path) -> bytes:
    with Image.open(path) as img:
        return img.convert("RGB").tobytes()


@pytest.fixture(params=CASES, ids=[c.name for c in CASES])
def case(request):
    folder: Path = request.param
    roles = dict(np.load(folder / "bands.npz"))
    expected = json.loads((folder / "expected.json").read_text(encoding="utf-8"))
    return folder, roles, expected


def test_there_are_golden_cases():
    assert len(CASES) >= 2


def test_ndvi_renders_are_pixel_identical(case):
    folder, roles, expected = case

    tc, idx, stats, prompt = ic.prepare("NDVI", roles, expected["ndvi_question"])

    assert tc.size == idx.size == (ic.SIDE, ic.SIDE)
    assert _pixels(tc) == _golden_pixels(folder / "true_colour.png")
    assert _pixels(idx) == _golden_pixels(folder / "ndvi_map.png")


def test_ndvi_stats_and_prompt_are_identical(case):
    folder, roles, expected = case

    _tc, _idx, stats, prompt = ic.prepare("NDVI", roles, expected["ndvi_question"])

    assert stats == expected["ndvi_stats"]
    assert ic.stats_text(stats) == expected["ndvi_stats_text"]
    assert prompt == (folder / "ndvi_prompt.txt").read_text(encoding="utf-8")


def test_ndwi_render_stats_and_mndwi_suffix_are_identical(case):
    folder, roles, expected = case

    _tc, idx, stats, prompt = ic.prepare("NDWI", roles, expected["ndwi_question"])

    assert _pixels(idx) == _golden_pixels(folder / "ndwi_map.png")
    assert stats == expected["ndwi_stats"]
    assert prompt == (folder / "ndwi_prompt.txt").read_text(encoding="utf-8")
    assert prompt.endswith(f"(MNDWI water fraction: {expected['mndwi_water_pct']}%.)")


def test_mask_boxes_match(case):
    _folder, roles, expected = case
    x = ic.compute_index("NDVI", ic.bands_from_roles(roles))

    boxes = ic.mask_boxes(x > 0.6, "dense vegetation")

    assert boxes == expected["ndvi_dense_boxes"]


def test_a_missing_band_is_refused_not_substituted():
    roles = {"red": np.ones((8, 8)), "green": np.ones((8, 8)), "nir": np.ones((8, 8))}

    # No blue: the true-colour image the adapter was trained with cannot be
    # made, and borrowing another band would show it a false-colour scene.
    with pytest.raises(ic.MissingRolesError) as err:
        ic.prepare("NDVI", roles, "q")
    assert err.value.missing == ["blue"]


def test_ndwi_needs_swir_for_the_mndwi_line():
    roles = {r: np.ones((8, 8)) for r in ("red", "green", "blue", "nir")}

    with pytest.raises(ic.MissingRolesError) as err:
        ic.prepare("NDWI", roles, "q")
    assert err.value.missing == ["swir1"]


def test_the_contract_block_is_marked_verbatim():
    source = Path(ic.__file__).read_text(encoding="utf-8")

    assert "# SHARED CONTRACT (copy into the backend's index module unchanged)" in source
