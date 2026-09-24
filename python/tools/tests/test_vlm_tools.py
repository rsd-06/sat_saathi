"""The vision-language tools: routing, confidence, honesty under failure.

A scripted stand-in replaces the GPU runtime (see fakes.py), so every branch
runs without torch. What is asserted is what the trace will say.
"""

from __future__ import annotations

import json
import math
from types import SimpleNamespace

import numpy as np
import pytest
import rasterio
from PIL import Image
from rasterio.transform import from_origin

from satsaathi_models import (
    ModelCatalog,
    ModelOOMError,
    ModelUnavailableError,
    clear_loaders,
    register_loader,
)
from satsaathi_models.testing import install_fake
from satsaathi_tools import pipeline
from satsaathi_tools.builtin import build_default_registry
from satsaathi_tools.protocol import ToolContext
from satsaathi_tools.registry import PlannedStep, effective_sensor, plan

from .fakes import FakeModel

SAR_EVAL = {"finetuned": {"ground_acc@0.5": 0.2, "scene_acc": 0.8833}}
OPT_EVAL = {
    "finetuned": {"ground_acc@0.5": 0.6, "vqa_acc": 0.6, "change_flag_acc": 0.9167}
}
SETTINGS = SimpleNamespace(
    confidence_high=0.6, confidence_low=0.35, vlm_resample=False,
    vlm_max_new_tokens=64, max_index_pixels=4096 * 4096,
)


@pytest.fixture(autouse=True)
def clean():
    clear_loaders()
    yield
    clear_loaders()


@pytest.fixture
def ctx():
    return ToolContext(job_id="job-1", storage=None, settings=SETTINGS)


def sar_chip(path, ship=(100, 112, 150, 170)):
    """A dark sea with one bright vessel, as an 8-bit chip."""
    rng = np.random.default_rng(3)
    sea = rng.normal(30, 4, (256, 256)).clip(0, 255)
    y0, y1, x0, x1 = ship
    sea[y0:y1, x0:x1] = 240
    Image.fromarray(sea.astype("uint8")).save(path)
    return str(path)


def setup(tmp_path, *names, script="ok", raises=None, evals=None):
    for name in names:
        install_fake(tmp_path, name, eval_doc=(evals or {}).get(name))
    catalog = ModelCatalog(tmp_path)
    model = FakeModel(catalog, script, raises=raises)
    register_loader("torch", lambda spec, directory: model)
    return build_default_registry(catalog), model


def run(tool, inputs, ctx):
    return tool.run(inputs, tool.validate_params({}), ctx)


# -- routing ------------------------------------------------------------------


class TestRouting:
    def test_a_sar_scene_goes_to_the_sar_adapter(self):
        steps = plan("land_cover", "single", sensor="sar")

        assert steps[5].tool_name == "vlm.sar"

    def test_an_optical_scene_goes_to_the_optical_adapter(self):
        steps = plan("land_cover", "single", sensor="optical")

        assert steps[5].tool_name == "vlm.vqa"

    def test_an_unknown_sensor_is_not_sent_to_the_sar_adapter(self):
        assert plan("land_cover", "single", sensor="unknown")[5].tool_name == "vlm.vqa"

    def test_a_water_question_on_sar_measures_backscatter(self):
        steps = plan("water", "single", sensor="sar", available_indices=[])

        assert steps[4].tool_name == "sar.water_mask"
        assert steps[5].tool_name == "vlm.sar"

    def test_an_index_question_with_readable_bands_goes_to_the_index_adapter(self):
        steps = plan(
            "water", "single", sensor="optical",
            available_indices=["ndvi", "ndwi"], vlm_indices=["ndwi"],
        )

        assert steps[4].params == {"index": "ndwi"}
        assert steps[5].tool_name == "vlm.index.ndwi"

    def test_without_the_index_adapter_the_optical_adapter_answers(self):
        steps = plan("vegetation", "single", sensor="optical",
                     available_indices=["ndvi"], vlm_indices=["ndwi"])

        assert steps[5].tool_name == "vlm.vqa"

    def test_pairs_go_to_change_and_fusion(self):
        assert plan("land_cover", "change")[5].tool_name == "vlm.change"
        assert plan("land_cover", "fusion")[5].tool_name == "vlm.fusion"

    def test_the_band_mapping_decides_the_sensor(self):
        # Choosing the Sentinel-1 preset says "this is SAR", whatever the
        # headers guessed.
        assert effective_sensor("optical", {"vv": 1, "vh": 2}) == "sar"
        assert effective_sensor("unknown", {"red": 1, "green": 2}) == "optical"
        assert effective_sensor("sar", None) == "sar"
        assert effective_sensor(None, {}) == "unknown"


# -- SAR ------------------------------------------------------------------------


class TestSar:
    def test_where_is_the_ship_runs_the_sar_adapter_with_its_prior(self, tmp_path, ctx):
        registry, model = setup(
            tmp_path, "vqa-sar", evals={"vqa-sar": SAR_EVAL},
            script='```json\n[{"bbox_2d": [100, 100, 200, 200], "label": "ship"}]\n```',
        )
        tool = registry.get("vlm.sar")

        result = run(tool, {"question": "Where is the ship?",
                            "path": sar_chip(tmp_path / "chip.png")}, ctx)

        summary = result.output_summary
        assert model.calls[0]["adapter"] == "vqa-sar"
        assert result.is_stub is False
        assert result.tool_version == "0.2.0+vqa-sar@v1"
        assert summary["source"] == "model"
        assert summary["task"] == "grounding"
        # SAR grounding is weak (0.20) and every confidence built on it says so.
        assert summary["prior"] == 0.2
        assert summary["prior_metric"] == "ground_acc@0.5"
        assert summary["signal"] == pytest.approx(0.9, abs=1e-3)
        assert summary["confidence"] == pytest.approx(0.18, abs=1e-3)
        assert summary["confidence_band"] == "low"
        assert result.needs_review is True

    def test_an_uncorroborated_sar_box_is_unverified(self, tmp_path, ctx):
        # The vessel is at x 150-170, y 100-112 of 256; the model says top-left.
        registry, _ = setup(
            tmp_path, "vqa-sar",
            script='[{"bbox_2d": [0, 0, 100, 100], "label": "ship"}]',
        )

        result = run(registry.get("vlm.sar"), {
            "question": "Where is the ship?", "path": sar_chip(tmp_path / "chip.png")}, ctx)

        assert result.output_summary["box_status"] == "unverified"
        assert result.evidence["boxes"][0]["status"] == "unverified"

    def test_a_box_over_a_classical_detection_is_corroborated(self, tmp_path, ctx):
        # 150/256*1000 = 586, 170/256 = 664, 100/256 = 391, 112/256 = 438.
        registry, _ = setup(
            tmp_path, "vqa-sar",
            script='[{"bbox_2d": [584, 388, 666, 440], "label": "ship"}]',
        )

        result = run(registry.get("vlm.sar"), {
            "question": "Where is the ship?", "path": sar_chip(tmp_path / "chip.png")}, ctx)

        assert result.output_summary["box_status"] == "corroborated"

    def test_boxes_convert_to_pixels_of_the_upload_but_not_to_a_map_without_crs(
        self, tmp_path, ctx
    ):
        registry, _ = setup(
            tmp_path, "vqa-sar", script='[{"bbox_2d": [0, 0, 500, 250], "label": "ship"}]'
        )

        result = run(registry.get("vlm.sar"), {
            "question": "Where is the ship?", "path": sar_chip(tmp_path / "chip.png")}, ctx)

        box = result.evidence["boxes"][0]
        assert box["bbox_px"] == [0, 0, 128, 64]
        assert box["bbox_map"] is None
        assert result.artifacts == []

    def test_a_scene_question_uses_the_scene_prior(self, tmp_path, ctx):
        registry, _ = setup(tmp_path, "vqa-sar", evals={"vqa-sar": SAR_EVAL},
                            script="This SAR image shows ships at sea.")

        result = run(registry.get("vlm.sar"), {
            "question": "What type of scene is this?",
            "path": sar_chip(tmp_path / "chip.png")}, ctx)

        assert result.output_summary["prior"] == 0.8833
        assert result.output_summary["confidence_band"] == "high"
        assert result.needs_review is False


# -- failure honesty ------------------------------------------------------------


class TestFailures:
    def test_oom_takes_the_fixture_path_and_says_so(self, tmp_path, ctx):
        registry, _ = setup(tmp_path, "vqa-sar", raises=ModelOOMError("CUDA out of memory"))
        tool = registry.get("vlm.sar")

        result = run(tool, {"question": "q", "path": sar_chip(tmp_path / "c.png")}, ctx)

        assert result.is_stub is True
        assert result.output_summary["source"] == "fixture"
        assert result.tool_version == "0.2.0"
        assert result.note == "model.oom"
        assert result.confidence is None

    def test_missing_weights_at_load_time_take_the_fixture_path(self, tmp_path, ctx):
        registry, _ = setup(
            tmp_path, "vqa-sar", raises=ModelUnavailableError("model.safetensors missing")
        )

        result = run(registry.get("vlm.sar"),
                     {"question": "q", "path": sar_chip(tmp_path / "c.png")}, ctx)

        assert result.is_stub is True
        assert result.output_summary["source"] == "fixture"
        assert result.note == "model.not_loadable"

    def test_unparseable_boxes_are_a_model_run_held_for_review(self, tmp_path, ctx):
        registry, _ = setup(tmp_path, "vqa-sar", script='```json\n[{"bbox_2d": [12, 4')

        result = run(registry.get("vlm.sar"),
                     {"question": "Where is the ship?",
                      "path": sar_chip(tmp_path / "c.png")}, ctx)

        # The model did run; it just said nothing usable.
        assert result.is_stub is False
        assert result.output_summary["source"] == "model"
        assert result.note == "model.output_unparseable"
        assert result.needs_review is True

    def test_the_trace_records_a_broken_runtime_as_fixture(self, tmp_path):
        """Regression: weights present, runtime broken, trace claimed a model ran."""
        registry, _ = setup(
            tmp_path, "vqa-sar", raises=ModelUnavailableError("CUDA is not available")
        )

        trace = pipeline.run(
            job_id="job-1",
            plan=[PlannedStep("vision_language", "vlm.sar", {})],
            registry=registry,
            ctx=ToolContext(job_id="job-1", storage=None, settings=SETTINGS),
            inputs={"question": "Where is the ship?", "path": sar_chip(tmp_path / "c.png")},
            query={"text": "q", "lang": "en"},
            input_set={"mode": "single", "assets": []},
        )

        step = trace.steps[0]
        assert step.is_stub is True
        assert step.tool_version == "0.2.0"
        assert step.output_summary["source"] == "fixture"
        assert step.note == "model.not_loadable"


# -- the whole pipeline, SAR ship question -------------------------------------------


def test_a_sar_ship_question_end_to_end(tmp_path):
    registry, _ = setup(
        tmp_path, "vqa-sar", evals={"vqa-sar": SAR_EVAL},
        script='[{"bbox_2d": [0, 0, 100, 100], "label": "ship"}]',
    )
    path = sar_chip(tmp_path / "chip.png")
    steps = plan("land_cover", "single", sensor="sar")

    trace = pipeline.run(
        job_id="job-1",
        plan=[s for s in steps if s.step_key in ("vision_language", "verify", "answer")],
        registry=registry,
        ctx=ToolContext(job_id="job-1", storage=None, settings=SETTINGS),
        inputs={"question": "Where is the ship?", "path": path},
        query={"text": "Where is the ship?", "lang": "en"},
        input_set={"mode": "single", "assets": []},
    )

    vl, verify, answer = trace.steps
    assert vl.tool_version == "0.2.0+vqa-sar@v1"
    assert vl.is_stub is False
    assert vl.output_summary["box_status"] == "unverified"
    assert {"prior", "signal", "confidence"} <= set(vl.output_summary)
    assert vl.status == "needs_review"
    assert verify.output_summary["verdict"] == "held_for_review"
    assert "sar_boxes_unverified" in verify.output_summary["reasons"]
    assert trace.status == "needs_review"
    assert "unverified" in trace.answer["text"]


# -- change ---------------------------------------------------------------------


def _pair(tmp_path):
    rng = np.random.default_rng(0)
    before = rng.integers(60, 90, (128, 128, 3), dtype="uint8")
    after = before.copy()
    after[30:60, 70:110] = 250
    Image.fromarray(before).save(tmp_path / "before.png")
    Image.fromarray(after).save(tmp_path / "after.png")
    return {
        "before": {"path": str(tmp_path / "before.png"), "sensor_type": "optical"},
        "after": {"path": str(tmp_path / "after.png"), "sensor_type": "optical"},
    }


class TestChange:
    def test_boxes_come_from_the_classical_map_and_the_adapter_explains(self, tmp_path, ctx):
        registry, model = setup(
            tmp_path, "change-detection", evals={"vqa-optical": OPT_EVAL},
            script='A new building was constructed. [{"bbox_2d": [1, 1, 5, 5]}]',
        )
        install_fake(tmp_path, "vqa-optical", eval_doc=OPT_EVAL)

        result = run(registry.get("vlm.change"),
                     {"question": "What changed?", "assets": _pair(tmp_path)}, ctx)

        call = model.calls[0]
        assert call["adapter"] == "vqa-optical"
        assert call["images"] == 2
        assert call["prompt"].startswith("BEFORE then AFTER. What changed?")
        boxes = result.evidence["boxes"]
        assert boxes and all(b["status"] == "measured" for b in boxes)
        # The model's own box [1,1,5,5] is not what is shown.
        assert all(b["bbox_2d"] != [1, 1, 5, 5] for b in boxes)
        assert result.output_summary["method"] == "cva"
        assert result.output_summary["agreement"] == 1.0
        assert result.output_summary["prior"] == 0.9167

    def test_a_model_saying_no_change_over_a_changed_map_is_flagged(self, tmp_path, ctx):
        registry, _ = setup(tmp_path, "change-detection", script="There is no change.")

        result = run(registry.get("vlm.change"),
                     {"question": "What changed?", "assets": _pair(tmp_path)}, ctx)

        assert result.output_summary["agreement"] == 0.0
        assert result.note == "change.model_disagrees_with_map"
        assert result.needs_review is True

    def test_a_sar_pair_is_classical_only(self, tmp_path, ctx):
        registry, model = setup(tmp_path, "change-detection")
        pair = _pair(tmp_path)
        for role in pair.values():
            role["sensor_type"] = "sar"

        result = run(registry.get("vlm.change"), {"question": "q", "assets": pair}, ctx)

        assert model.calls == []
        assert result.output_summary["source"] == "classical"
        assert result.is_stub is False
        assert result.note == "change.sar_classical_only"


# -- fusion ---------------------------------------------------------------------


class TestFusion:
    def test_both_adapters_then_the_base_decides(self, tmp_path, ctx):
        box = '[{"bbox_2d": [100, 100, 300, 300], "label": "ship"}]'
        registry, model = setup(
            tmp_path, "fusion-optical-sar",
            script={"vqa-optical": box, "vqa-sar": box, None: "Both sensors agree."},
        )
        Image.new("RGB", (64, 64), (20, 60, 120)).save(tmp_path / "opt.png")
        assets = {
            "optical": {"path": str(tmp_path / "opt.png"), "sensor_type": "optical"},
            "sar": {"path": sar_chip(tmp_path / "sar.png"), "sensor_type": "sar"},
        }

        result = run(registry.get("vlm.fusion"),
                     {"question": "Where is the ship?", "assets": assets}, ctx)

        assert [c["adapter"] for c in model.calls] == ["vqa-optical", "vqa-sar", None]
        judge = model.calls[2]
        assert judge["system"] and "optical" in judge["system"]
        assert result.output_summary["agreement"] == 1.0
        assert result.output_summary["agreement_kind"] == "box_f1@0.5"
        assert result.output_summary["answer"] == "Both sensors agree."
        sar_boxes = [b for b in result.evidence["boxes"] if b["label"].startswith("sar:")]
        assert sar_boxes[0]["status"] == "corroborated"

    def test_disagreement_is_multiplied_in(self, tmp_path, ctx):
        registry, _ = setup(
            tmp_path, "fusion-optical-sar",
            script={"vqa-optical": "Yes, it is flooded.", "vqa-sar": "No flooding.",
                    None: "Trust SAR: cloud hides the ground in the optical image."},
        )
        Image.new("RGB", (64, 64)).save(tmp_path / "opt.png")
        assets = {"optical": {"path": str(tmp_path / "opt.png")},
                  "sar": {"path": sar_chip(tmp_path / "sar.png")}}

        result = run(registry.get("vlm.fusion"),
                     {"question": "Is the field flooded?", "assets": assets}, ctx)

        assert result.output_summary["agreement"] == 0.0
        assert result.output_summary["confidence"] == 0.0
        assert result.needs_review is True


# -- index ----------------------------------------------------------------------


def _bands_tif(tmp_path):
    rng = np.random.default_rng(1)
    data = rng.uniform(500, 3000, (5, 64, 64)).astype("float32")
    path = tmp_path / "s2.tif"
    with rasterio.open(path, "w", driver="GTiff", width=64, height=64, count=5,
                       dtype="float32", crs="EPSG:32643",
                       transform=from_origin(500000, 4000000, 10, 10)) as dst:
        dst.write(data)
    return str(path), {"blue": 1, "green": 2, "red": 3, "nir": 4, "swir1": 5}


class TestIndex:
    def test_the_adapter_reads_two_rendered_images_and_the_stats(self, tmp_path, ctx):
        registry, model = setup(tmp_path, "index-ndwi", script="Open water is absent.")
        path, band_map = _bands_tif(tmp_path)

        result = run(registry.get("vlm.index.ndwi"),
                     {"question": "Is there water?", "path": path, "band_map": band_map}, ctx)

        call = model.calls[0]
        assert call["adapter"] == "index-ndwi"
        assert call["images"] == 2
        assert call["prompt"].startswith("Image 1: true colour. Image 2: NDWI map.")
        assert "(MNDWI water fraction:" in call["prompt"]
        assert result.output_summary["numbers_quoted_ok"] is True

    def test_a_number_not_in_the_stats_is_held(self, tmp_path, ctx):
        registry, _ = setup(tmp_path, "index-ndwi", script="About 73.9% is water.")
        path, band_map = _bands_tif(tmp_path)

        result = run(registry.get("vlm.index.ndwi"),
                     {"question": "How much water?", "path": path, "band_map": band_map}, ctx)

        assert result.output_summary["numbers_quoted_ok"] is False
        assert result.output_summary["numbers_unquoted"] == "73.9"
        assert result.note == "index.unquoted_numbers"
        assert result.needs_review is True

    def test_quoted_numbers_pass(self, tmp_path, ctx):
        path, band_map = _bands_tif(tmp_path)
        from satsaathi_core import imaging, index_contract

        roles = imaging.read_band_arrays(path, band_map, ("red", "green", "blue", "nir", "swir1"),
                                         4096 * 4096)
        _tc, _i, stats, _p = index_contract.prepare("NDWI", roles, "q")
        registry, _ = setup(tmp_path, "index-ndwi",
                            script=f"The mean NDWI is {stats['mean']}.")

        result = run(registry.get("vlm.index.ndwi"),
                     {"question": "q", "path": path, "band_map": band_map}, ctx)

        assert result.output_summary["numbers_quoted_ok"] is True


# -- classical water ----------------------------------------------------------


def test_sar_water_mask_is_a_measurement_not_a_stub(tmp_path, ctx):
    rng = np.random.default_rng(2)
    img = rng.normal(140, 10, (128, 128))
    img[64:] = rng.normal(20, 4, (64, 128))
    Image.fromarray(img.clip(0, 255).astype("uint8")).save(tmp_path / "s1.png")
    registry = build_default_registry(ModelCatalog(tmp_path))
    tool = registry.get("sar.water_mask")

    result = run(tool, {"path": str(tmp_path / "s1.png")}, ctx)

    assert tool.is_stub is False
    assert tool.queue == "cpu"
    assert result.output_summary["source"] == "classical"
    assert 45 < result.output_summary["water_pct"] < 55


def test_confidence_is_the_product_of_prior_and_signal():
    from satsaathi_tools.confidence import combine

    c = combine(prior=0.6, prior_metric="vqa_acc", signal=math.exp(math.log(0.8)),
                settings=SETTINGS)

    assert c.value == pytest.approx(0.48)
    assert c.band == "medium"
    assert json.dumps(c.summary())
