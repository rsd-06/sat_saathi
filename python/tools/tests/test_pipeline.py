from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest
import rasterio
from jsonschema import Draft202012Validator
from rasterio.transform import from_origin

from satsaathi_tools import pipeline
from satsaathi_tools.builtin import build_default_registry
from satsaathi_tools.protocol import BaseTool, NoParams, ToolContext, ToolResult
from satsaathi_tools.registry import PlannedStep, plan
from satsaathi_tools.vlm import VlmParams

SCHEMA = json.loads(
    (Path(pipeline.__file__).parent / "trace_schema.json").read_text("utf-8")
)
VALIDATOR = Draft202012Validator(SCHEMA)


@dataclass
class Settings:
    max_index_pixels: int = 4096 * 4096


@pytest.fixture
def ctx():
    return ToolContext(job_id="job-1", storage=None, settings=Settings())


@pytest.fixture
def registry():
    return build_default_registry()


@pytest.fixture
def scene(tmp_path: Path) -> Path:
    path = tmp_path / "scene.tif"
    with rasterio.open(
        path, "w", driver="GTiff", height=4, width=4, count=4, dtype="float32",
        crs="EPSG:32645", transform=from_origin(500000, 2700000, 10, 10),
    ) as dst:
        for i, v in enumerate((0.05, 0.12, 0.10, 0.50), start=1):
            dst.write(np.full((4, 4), v, dtype="float32"), i)
    return path


def base_inputs(scene: Path) -> dict:
    return {
        "question": "how much crop is there",
        "path": scene,
        "band_map": {"blue": 1, "green": 2, "red": 3, "nir": 4},
        "planned_index": "ndvi",
    }


def run_pipeline(registry, ctx, scene, *, intent="vegetation", emit=None):
    return pipeline.run(
        job_id="job-1",
        plan=plan(intent, "single", available_indices=["ndvi", "ndwi"]),
        registry=registry,
        ctx=ctx,
        inputs=base_inputs(scene),
        query={"text": "how much crop is there", "lang": "en", "ui_lang": "en"},
        input_set={"mode": "single", "assets": [{"role": "single"}]},
        emit=emit,
    )


def test_runs_all_eight_steps_in_order(registry, ctx, scene):
    trace = run_pipeline(registry, ctx, scene)

    assert [s.step_key for s in trace.steps] == [
        "ask", "imagery", "understand", "preprocess",
        "compute", "vision_language", "verify", "answer",
    ]
    assert [s.ordinal for s in trace.steps] == list(range(8))


def test_no_step_is_left_pending(registry, ctx, scene):
    trace = run_pipeline(registry, ctx, scene)

    assert all(s.status != "pending" for s in trace.steps)
    assert all(s.duration_ms is not None for s in trace.steps)


def test_records_which_steps_measured_and_which_were_fixture(registry, ctx, scene):
    trace = run_pipeline(registry, ctx, scene)
    by_key = {s.step_key: s for s in trace.steps}

    assert by_key["compute"].is_stub is False
    assert by_key["imagery"].is_stub is False
    assert by_key["vision_language"].is_stub is True
    assert by_key["answer"].is_stub is True


def test_compute_step_carries_real_measurements(registry, ctx, scene):
    trace = run_pipeline(registry, ctx, scene)
    compute = next(s for s in trace.steps if s.step_key == "compute")

    assert compute.output_summary["index"] == "ndvi"
    assert compute.output_summary["above_threshold_pct"] == pytest.approx(100.0)
    assert compute.output_summary["area_ha"] == pytest.approx(0.16)


def test_emits_a_snapshot_on_every_transition(registry, ctx, scene):
    seen: list[dict] = []
    run_pipeline(registry, ctx, scene, emit=seen.append)

    # One before the run, then running + settled per step, then a final one.
    assert len(seen) >= 17
    assert seen[0]["steps"][0]["status"] == "pending"
    assert seen[-1]["status"] in {"succeeded", "needs_review"}
    # Every emission is a complete, valid trace, not a delta.
    for snapshot in seen:
        VALIDATOR.validate(snapshot)


def test_exported_trace_validates_against_the_schema(registry, ctx, scene):
    trace = run_pipeline(registry, ctx, scene)
    VALIDATOR.validate(trace.to_dict())


def test_a_failing_step_is_recorded_and_the_rest_are_skipped(registry, ctx, scene):
    class Exploding(BaseTool):
        name = "vlm.vqa"  # replaces the registered one below
        version = "0.1.0"
        params_schema = VlmParams
        is_stub = True

        def run(self, inputs, params, ctx):
            raise RuntimeError("model unavailable")

    registry._tools["vlm.vqa"] = Exploding()
    trace = run_pipeline(registry, ctx, scene, intent="vqa")

    by_key = {s.step_key: s for s in trace.steps}
    assert by_key["vision_language"].status == "failed"
    assert by_key["vision_language"].error["key"] == "tool.failed"
    assert "model unavailable" in by_key["vision_language"].error["params"]["detail"]
    # Later steps are recorded as skipped, not left pending or dropped.
    assert by_key["verify"].status == "skipped"
    assert by_key["answer"].status == "skipped"
    assert trace.status == "failed"
    # And the trace is still a whole, valid document.
    VALIDATOR.validate(trace.to_dict())


def test_errors_are_message_keys_not_sentences(registry, ctx, scene):
    class Exploding(BaseTool):
        name = "vlm.vqa"
        version = "0.1.0"
        params_schema = VlmParams

        def run(self, inputs, params, ctx):
            raise RuntimeError("boom")

    registry._tools["vlm.vqa"] = Exploding()
    trace = run_pipeline(registry, ctx, scene, intent="vqa")
    error = next(s for s in trace.steps if s.status == "failed").error

    assert error["key"].startswith("tool.")
    assert " " not in error["key"]


def test_a_low_confidence_run_is_held_for_review(registry, ctx, scene):
    class LowConfidence(BaseTool):
        name = "verify.crosscheck"
        version = "0.1.0"
        params_schema = NoParams
        is_stub = False

        def run(self, inputs, params, ctx):
            return ToolResult(
                output_summary={"confidence": 0.3, "verdict": "held_for_review"},
                confidence=0.3,
            )

    registry._tools["verify.crosscheck"] = LowConfidence()
    trace = run_pipeline(registry, ctx, scene)

    assert trace.confidence == 0.3
    assert trace.status == "needs_review"
    assert next(s for s in trace.steps if s.step_key == "verify").status == "needs_review"


def test_a_rejected_parameter_fails_the_step_not_the_process(registry, ctx, scene):
    bad_plan = [
        PlannedStep("ask", "intake.text", {}),
        PlannedStep("imagery", "imagery.inspect", {}),
        PlannedStep("understand", "intent.keyword", {}),
        PlannedStep("preprocess", "preprocess.noop", {}),
        # threshold is out of the permitted range.
        PlannedStep("compute", "indices.compute", {"index": "ndvi", "threshold": 12}),
        PlannedStep("vision_language", "vlm.vqa", {}),
        PlannedStep("verify", "verify.crosscheck", {}),
        PlannedStep("answer", "answer.template", {}),
    ]
    trace = pipeline.run(
        job_id="job-2",
        plan=bad_plan,
        registry=registry,
        ctx=ctx,
        inputs=base_inputs(scene),
        query={"text": "q", "lang": "en"},
        input_set={"mode": "single", "assets": []},
    )

    compute = next(s for s in trace.steps if s.step_key == "compute")
    assert compute.status == "failed"
    assert compute.error["key"] == "tool.params_rejected"
    VALIDATOR.validate(trace.to_dict())


def test_the_answer_only_reports_what_compute_measured(registry, ctx, scene):
    trace = run_pipeline(registry, ctx, scene)

    assert trace.answer is not None
    # 100% above threshold over 0.16 ha, both taken from the compute step.
    assert "100.0" in trace.answer["text"]
    assert "0.16" in trace.answer["text"]
