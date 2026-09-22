from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from satsaathi_tools.builtin import build_default_registry
from satsaathi_tools.protocol import ToolContext


@dataclass
class Settings:
    max_index_pixels: int = 4096 * 4096


@pytest.fixture
def ctx(tmp_path: Path):
    return ToolContext(job_id="job-1", storage=None, settings=Settings())


@pytest.fixture
def registry():
    return build_default_registry()


@pytest.fixture
def scene(tmp_path: Path) -> Path:
    """4x4 optical scene: Blue, Green, Red, NIR."""
    path = tmp_path / "scene.tif"
    bands = [
        np.full((4, 4), 0.05, dtype="float32"),
        np.full((4, 4), 0.12, dtype="float32"),
        np.full((4, 4), 0.10, dtype="float32"),
        np.full((4, 4), 0.50, dtype="float32"),
    ]
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=4,
        width=4,
        count=4,
        dtype="float32",
        crs="EPSG:32645",
        transform=from_origin(500000, 2700000, 10, 10),
    ) as dst:
        for i, band in enumerate(bands, start=1):
            dst.write(band, i)
    return path


BANDS = {"blue": 1, "green": 2, "red": 3, "nir": 4}


def run(registry, name, inputs, params, ctx):
    tool = registry.get(name)
    return tool.run(inputs, tool.validate_params(params), ctx)


def test_imagery_inspect_reports_real_header_values(registry, scene, ctx):
    result = run(registry, "imagery.inspect", {"path": scene}, {}, ctx)

    assert result.output_summary["bands"] == 4
    assert result.output_summary["width"] == 4
    assert result.output_summary["georeferenced"] is True
    assert "32645" in result.output_summary["crs"]


def test_imagery_inspect_notes_a_missing_crs(registry, tmp_path, ctx):
    path = tmp_path / "plain.tif"
    with rasterio.open(
        path, "w", driver="GTiff", height=2, width=2, count=3, dtype="float32"
    ) as dst:
        dst.write(np.zeros((3, 2, 2), dtype="float32"))

    result = run(registry, "imagery.inspect", {"path": path}, {}, ctx)

    assert result.output_summary["georeferenced"] is False
    assert result.note == "raster.not_georeferenced"


def test_indices_compute_returns_measured_numbers(registry, scene, ctx):
    result = run(
        registry,
        "indices.compute",
        {"path": scene, "band_map": BANDS},
        {"index": "ndvi", "threshold": 0.2},
        ctx,
    )

    # NIR 0.50 / Red 0.10 -> 0.6667 across every pixel.
    assert result.output_summary["index"] == "ndvi"
    assert result.output_summary["above_threshold_pct"] == pytest.approx(100.0)
    assert result.output_summary["mean"] == pytest.approx(0.6667, abs=1e-3)
    # 16 pixels of 100 m2 -> 0.16 ha.
    assert result.output_summary["area_ha"] == pytest.approx(0.16)


def test_indices_compute_reports_no_area_without_a_crs(registry, tmp_path, ctx):
    path = tmp_path / "nocrs.tif"
    with rasterio.open(
        path, "w", driver="GTiff", height=2, width=2, count=4, dtype="float32"
    ) as dst:
        for i, v in enumerate((0.05, 0.12, 0.10, 0.50), start=1):
            dst.write(np.full((2, 2), v, dtype="float32"), i)

    result = run(
        registry,
        "indices.compute",
        {"path": path, "band_map": BANDS},
        {"index": "ndvi"},
        ctx,
    )

    assert result.output_summary["area_ha"] is None
    assert result.note == "area.requires_crs"


def test_indices_unavailable_lists_the_missing_bands(registry, ctx):
    result = run(
        registry, "indices.unavailable", {"band_map": {"red": 3}}, {}, ctx
    )

    assert "nir" in result.output_summary["ndvi"]
    assert result.note == "indices.none_available"


def test_intent_keyword_matches_whole_tokens_only(registry, ctx):
    water = run(
        registry, "intent.keyword", {"question": "where is the flooding"}, {}, ctx
    )
    assert water.output_summary["intent"] == "water"

    # A keyword buried inside an unrelated word must not fire.
    none = run(
        registry, "intent.keyword", {"question": "describe this afternoon"}, {}, ctx
    )
    assert none.output_summary["intent"] == "land_cover"
    assert none.note == "intent.defaulted"


def test_verify_holds_an_answer_that_claims_area_without_a_crs(registry, ctx):
    result = run(
        registry,
        "verify.crosscheck",
        {
            "measured": {"index": "ndvi", "area_ha": None},
            "claims": {"mentions_area": True},
        },
        {"threshold": 0.75},
        ctx,
    )

    assert result.output_summary["verdict"] == "held_for_review"
    assert "area_claimed_without_crs" in result.output_summary["reasons"]


def test_verify_releases_a_supported_answer(registry, ctx):
    result = run(
        registry,
        "verify.crosscheck",
        {"measured": {"index": "ndvi", "area_ha": 1.5}, "claims": {"index": "ndvi"}},
        {},
        ctx,
    )

    assert result.output_summary["verdict"] == "released"
    assert result.confidence is not None and result.confidence >= 0.75


def test_verify_penalises_a_claim_about_an_index_that_was_not_computed(registry, ctx):
    result = run(
        registry,
        "verify.crosscheck",
        {"measured": {"index": "ndvi"}, "claims": {"index": "ndwi"}},
        {},
        ctx,
    )

    assert "index_mismatch" in result.output_summary["reasons"]


def test_answer_template_only_states_measured_figures(registry, ctx):
    result = run(
        registry,
        "answer.template",
        {"measured": {"index": "ndwi", "above_threshold_pct": 31.7, "area_ha": 142.4}},
        {"target_lang": "ta"},
        ctx,
    )

    text = result.evidence["text"]
    assert "31.7" in text and "142.4" in text
    assert result.output_summary["target_lang"] == "ta"


def test_answer_template_says_nothing_when_nothing_was_measured(registry, ctx):
    result = run(registry, "answer.template", {"measured": {}}, {}, ctx)

    assert result.evidence["text"] == "No measurement was available."


def test_stub_vlms_declare_their_output_as_fixture(registry, ctx):
    for name in ("vlm.vqa.stub", "vlm.change.stub", "vlm.fusion.stub"):
        result = run(registry, name, {}, {}, ctx)
        assert result.output_summary["source"] == "fixture"
        assert registry.get(name).is_stub is True
