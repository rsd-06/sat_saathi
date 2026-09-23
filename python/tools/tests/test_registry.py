from __future__ import annotations

import pytest

from satsaathi_tools.builtin import build_default_registry
from satsaathi_tools.protocol import RejectedParamsError, Tool
from satsaathi_tools.registry import (
    STEP_KEYS,
    Registry,
    UnknownToolError,
    plan,
    plan_is_complete,
)


@pytest.fixture
def registry():
    return build_default_registry()


def test_every_registered_tool_satisfies_the_protocol(registry: Registry):
    for tool in registry.all():
        assert isinstance(tool, Tool)
        assert tool.name and tool.version
        assert isinstance(tool.is_stub, bool)


def test_registry_rejects_a_duplicate_name(registry: Registry):
    existing = registry.get("intake.text")
    with pytest.raises(ValueError, match="already registered"):
        registry.register(existing)


def test_unknown_tool_raises(registry: Registry):
    with pytest.raises(UnknownToolError):
        registry.get("nope")


def test_describe_exposes_the_permitted_parameter_schema(registry: Registry):
    described = {d["name"]: d for d in registry.describe()}
    compute = described["indices.compute"]

    assert compute["is_stub"] is False
    assert set(compute["params_schema"]["properties"]) == {"index", "threshold"}


def test_tools_declare_whether_they_are_stubs(registry: Registry):
    by_name = {t.name: t.is_stub for t in registry.all()}

    # The distinction is the reason the trace is worth showing.
    assert by_name["indices.compute"] is False
    assert by_name["imagery.inspect"] is False
    assert by_name["vlm.vqa"] is True
    assert by_name["answer.template"] is True


def test_a_tool_refuses_a_parameter_it_does_not_permit(registry: Registry):
    tool = registry.get("indices.compute")

    with pytest.raises(RejectedParamsError):
        tool.validate_params({"index": "ndvi", "sneaky": True})


def test_a_tool_refuses_an_out_of_range_parameter(registry: Registry):
    tool = registry.get("indices.compute")

    with pytest.raises(RejectedParamsError):
        tool.validate_params({"index": "ndvi", "threshold": 9.0})


def test_a_tool_refuses_an_index_it_does_not_implement(registry: Registry):
    tool = registry.get("indices.compute")

    with pytest.raises(RejectedParamsError):
        tool.validate_params({"index": "evi"})


def test_valid_params_are_accepted_and_defaulted(registry: Registry):
    params = registry.get("indices.compute").validate_params({"index": "ndwi"})

    assert params.index == "ndwi"
    assert params.threshold == 0.0


class TestPlanner:
    def test_plan_covers_every_step_in_the_fixed_order(self):
        steps = plan("water", "single", available_indices=["ndwi"])

        assert tuple(s.step_key for s in steps) == STEP_KEYS
        assert plan_is_complete(steps)

    def test_plan_names_only_registered_tools(self, registry: Registry):
        for intent in ("water", "vegetation", "change", "built_up", "land_cover"):
            for mode in ("single", "fusion", "change"):
                for step in plan(intent, mode, available_indices=["ndvi", "ndwi"]):
                    assert step.tool_name in registry

    def test_water_intent_plans_ndwi(self):
        steps = plan("water", "single", available_indices=["ndvi", "ndwi"])
        compute = next(s for s in steps if s.step_key == "compute")

        assert compute.params["index"] == "ndwi"

    def test_never_plans_an_index_the_input_cannot_support(self):
        # Only NDVI is computable, so a water question must not plan NDWI.
        steps = plan("water", "single", available_indices=["ndvi"])
        compute = next(s for s in steps if s.step_key == "compute")

        assert compute.tool_name == "indices.compute"
        assert compute.params["index"] == "ndvi"

    def test_records_unavailability_when_no_index_is_computable(self):
        steps = plan("water", "single", available_indices=[])
        compute = next(s for s in steps if s.step_key == "compute")

        assert compute.tool_name == "indices.unavailable"
        assert "index" not in compute.params

    def test_pairs_get_a_coregistration_step(self):
        for mode in ("fusion", "change"):
            steps = plan("change", mode, available_indices=["ndvi"])
            pre = next(s for s in steps if s.step_key == "preprocess")
            assert pre.tool_name == "preprocess.coregister.stub"

    def test_a_single_image_skips_coregistration(self):
        steps = plan("vegetation", "single", available_indices=["ndvi"])
        pre = next(s for s in steps if s.step_key == "preprocess")

        assert pre.tool_name == "preprocess.noop"

    def test_fusion_mode_picks_the_fusion_vlm(self):
        steps = plan("fusion", "fusion", available_indices=["ndvi"])
        vlm = next(s for s in steps if s.step_key == "vision_language")

        assert vlm.tool_name == "vlm.fusion"

    def test_an_unknown_intent_still_produces_a_complete_plan(self):
        steps = plan("something_new", "single", available_indices=["ndvi"])

        assert plan_is_complete(steps)
