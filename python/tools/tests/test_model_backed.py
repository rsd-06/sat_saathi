"""The seam between a fixture and a real prediction.

These are the tests that keep the product's central claim honest: a step that
did not run a model must never look like one that did.
"""

from __future__ import annotations

import pytest

from satsaathi_models import ModelCatalog, clear_loaders, register_loader
from satsaathi_tools.builtin import build_default_registry
from satsaathi_tools.protocol import ToolContext, ToolResult
from satsaathi_tools.registry import plan, queue_for


@pytest.fixture(autouse=True)
def clean_cache():
    clear_loaders()
    yield
    clear_loaders()


@pytest.fixture
def ctx():
    return ToolContext(job_id="job-1", storage=None, settings=None)


def install(root, name: str) -> None:
    from satsaathi_models.testing import install_fake

    install_fake(root, name)


class TestWithoutWeights:
    def test_a_vision_language_tool_says_it_is_fixture_output(self, tmp_path, ctx):
        registry = build_default_registry(ModelCatalog(tmp_path))
        tool = registry.get("vlm.vqa")

        result = tool.run({}, tool.validate_params({}), ctx)

        assert tool.is_stub is True
        assert result.output_summary["source"] == "fixture"

    def test_the_version_carries_no_model_revision(self, tmp_path):
        registry = build_default_registry(ModelCatalog(tmp_path))

        assert registry.get("vlm.vqa").version == "0.1.0"

    def test_it_stays_on_the_cpu_queue(self, tmp_path):
        # A fixture is a dictionary lookup. Routing it to a GPU worker would
        # idle the scarcest machine in the deployment.
        registry = build_default_registry(ModelCatalog(tmp_path))

        assert registry.get("vlm.vqa").queue == "cpu"

    def test_a_registry_with_no_catalog_at_all_still_works(self, ctx):
        registry = build_default_registry()
        tool = registry.get("vlm.vqa")

        result = tool.run({}, tool.validate_params({}), ctx)

        assert tool.is_stub is True
        assert result.output_summary["source"] == "fixture"


class TestWithWeights:
    def test_the_tool_stops_calling_itself_a_stub(self, tmp_path):
        install(tmp_path, "vqa-optical")
        registry = build_default_registry(ModelCatalog(tmp_path))

        assert registry.get("vlm.vqa").is_stub is False

    def test_the_version_records_which_weights_would_run(self, tmp_path):
        install(tmp_path, "vqa-optical")
        registry = build_default_registry(ModelCatalog(tmp_path))

        # Two answers from different weights must not be recorded as the same
        # system, so the revision is part of the version the trace stores.
        assert registry.get("vlm.vqa").version == "0.1.0+vqa-optical@v1"

    def test_it_moves_to_the_queue_its_model_needs(self, tmp_path):
        install(tmp_path, "vqa-optical")
        registry = build_default_registry(ModelCatalog(tmp_path))

        assert registry.get("vlm.vqa").queue == "gpu"

    def test_installing_one_model_does_not_promote_another(self, tmp_path):
        install(tmp_path, "vqa-optical")
        registry = build_default_registry(ModelCatalog(tmp_path))

        assert registry.get("vlm.fusion").is_stub is True
        assert registry.get("vlm.fusion").queue == "cpu"

    def test_present_weights_with_no_runtime_fall_back_and_say_so(self, tmp_path, ctx):
        """Declared, installed, but unloadable — most often a missing runtime.

        Answering with the fixture is fine. Presenting it as a model result
        is not, so this takes the fixture path in full and leaves a note.
        """
        install(tmp_path, "vqa-optical")
        registry = build_default_registry(ModelCatalog(tmp_path))
        tool = registry.get("vlm.vqa")

        result = tool.run({}, tool.validate_params({}), ctx)

        assert result.output_summary["source"] == "fixture"
        assert result.note == "model.not_loadable"

    def test_a_failed_load_is_recorded_as_a_fixture_run(self, tmp_path, ctx):
        """Regression: the trace claimed a model ran when the load had failed.

        The tool reports `is_stub = False` while its weights are installed,
        because it expects to use them. A load that fails at the moment of use
        sends it down the fixture path anyway, and a trace that still said
        `is_stub=False` with the model revision in its version was describing
        a run that never happened — the exact failure the trace exists to
        catch. The result now corrects both.
        """
        install(tmp_path, "vqa-optical")
        registry = build_default_registry(ModelCatalog(tmp_path))
        tool = registry.get("vlm.vqa")

        # What the tool expects, before it tries.
        assert tool.is_stub is False
        assert tool.version == "0.1.0+vqa-optical@v1"

        result = tool.run({}, tool.validate_params({}), ctx)

        # What actually happened.
        assert result.is_stub is True
        assert result.tool_version == "0.1.0"
        assert result.output_summary["source"] == "fixture"

    def test_a_loadable_model_is_used_and_marked_as_a_model(self, tmp_path, ctx):
        install(tmp_path, "vqa-optical")
        register_loader("torch", lambda spec, directory: {"name": spec.name})
        registry = build_default_registry(ModelCatalog(tmp_path))
        tool = registry.get("vlm.vqa")

        # The shipped tools have no inference path yet, so a real load reaches
        # a deliberate NotImplementedError rather than inventing an answer.
        with pytest.raises(NotImplementedError):
            tool.run({}, tool.validate_params({}), ctx)


class TestQueueRouting:
    def test_an_all_fixture_plan_runs_on_cpu(self, tmp_path):
        registry = build_default_registry(ModelCatalog(tmp_path))
        steps = plan("water", "single", available_indices=["ndwi"])

        assert queue_for(steps, registry) == "cpu"

    def test_one_gpu_step_sends_the_whole_plan_to_the_gpu_queue(self, tmp_path):
        # A plan runs as one task, so it needs the scarcest queue any of its
        # steps asks for.
        install(tmp_path, "vqa-optical")
        registry = build_default_registry(ModelCatalog(tmp_path))
        steps = plan("water", "single", available_indices=["ndwi"])

        assert queue_for(steps, registry) == "gpu"

    def test_an_unknown_tool_does_not_break_routing(self, tmp_path):
        from satsaathi_tools.registry import PlannedStep

        registry = build_default_registry(ModelCatalog(tmp_path))
        steps = [PlannedStep("compute", "tool.that.does.not.exist", {})]

        assert queue_for(steps, registry) == "cpu"


class TestDescription:
    def test_a_tool_reports_its_model_and_whether_it_is_there(self, tmp_path):
        registry = build_default_registry(ModelCatalog(tmp_path))

        described = registry.get("vlm.vqa").describe()

        assert described["model"]["name"] == "vqa-optical"
        assert described["model"]["available"] is False
        assert described["is_stub"] is True
        assert described["queue"] == "cpu"

    def test_a_measuring_tool_is_not_marked_as_a_stub(self, tmp_path):
        registry = build_default_registry(ModelCatalog(tmp_path))

        # indices.compute reads real pixels and always has; nothing about the
        # model layer should have changed that.
        assert registry.get("indices.compute").is_stub is False


def test_the_fixture_result_still_carries_its_evidence(tmp_path, ctx):
    registry = build_default_registry(ModelCatalog(tmp_path))
    tool = registry.get("vlm.grounding")

    result: ToolResult = tool.run({}, tool.validate_params({}), ctx)

    assert result.output_summary["boxes"] == 2
    assert len(result.evidence["boxes"]) == 2


def test_the_trace_records_the_run_that_happened(tmp_path):
    """End to end through the pipeline, not just the tool.

    The pipeline reads `is_stub` and `version` off the tool before running it,
    which is right for every tool that cannot change its mind. A model-backed
    one can, so the result's correction has to survive all the way into the
    step record.
    """
    from satsaathi_tools import pipeline
    from satsaathi_tools.registry import PlannedStep

    install(tmp_path, "vqa-optical")
    registry = build_default_registry(ModelCatalog(tmp_path))

    trace = pipeline.run(
        job_id="job-1",
        plan=[PlannedStep("vision_language", "vlm.vqa", {})],
        registry=registry,
        ctx=ToolContext(job_id="job-1", storage=None, settings=None),
        inputs={},
        query={"text": "q", "lang": "en", "ui_lang": "en", "intent": "vqa"},
        input_set={"mode": "single", "assets": []},
    )

    step = next(s for s in trace.steps if s.step_key == "vision_language")
    assert step.is_stub is True
    assert step.tool_version == "0.1.0"
    assert step.output_summary["source"] == "fixture"
    assert step.note == "model.not_loadable"
