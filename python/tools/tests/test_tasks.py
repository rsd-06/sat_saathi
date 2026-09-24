"""Task selection, checked against the problem statement's representative queries."""

from __future__ import annotations

import pytest

from satsaathi_tools.registry import plan
from satsaathi_tools.tasks import classify_task


@pytest.mark.parametrize(
    ("question", "mode", "task"),
    [
        # The five representative queries in the problem statement.
        ("Describe the land-cover and major objects visible in this image.", "single", "caption"),
        ("Highlight the water body referred to in the query.", "single", "grounding"),
        ("What changed between these two dates, and where did the change occur?",
         "change", "change"),
        ("Use the optical and SAR images together to identify built-up and water-covered "
         "regions.", "fusion", "fusion"),
        ("Has the built-up area increased, decreased, or remained unchanged?", "change", "change"),
        # Single-image VQA stays the default.
        # RSVQA counting questions want a number, not boxes.
        ("How many ships are there?", "single", "vqa"),
        ("Is there a road in this image?", "single", "vqa"),
        # The interface languages.
        ("जहाज़ कहाँ है?", "single", "grounding"),
        ("கப்பல் எங்கே உள்ளது?", "single", "grounding"),
        ("এই ছবির বর্ণনা দিন", "single", "caption"),
    ],
)
def test_classify_task(question, mode, task):
    assert classify_task(question, mode) == task


class TestRoutingByTask:
    def test_caption_goes_to_the_caption_tool_and_records_the_task(self):
        step = plan("land_cover", "single", sensor="optical", task="caption")[5]

        assert step.tool_name == "vlm.caption"
        assert step.params == {"task": "caption"}

    def test_grounding_goes_to_the_grounding_tool(self):
        step = plan("land_cover", "single", sensor="optical", task="grounding")[5]

        assert step.tool_name == "vlm.grounding"

    def test_sar_grounding_stays_on_the_sar_adapter(self):
        step = plan("land_cover", "single", sensor="sar", task="grounding")[5]

        assert (step.tool_name, step.params) == ("vlm.sar", {"task": "grounding"})

    def test_water_grounding_over_readable_bands_uses_the_ndwi_adapter(self):
        step = plan("water", "single", sensor="optical", task="grounding",
                    available_indices=["ndwi"], vlm_indices=["ndwi"])[5]

        assert (step.tool_name, step.params) == ("vlm.index.ndwi", {"task": "grounding"})

    def test_pair_modes_record_their_task(self):
        assert plan("change", "change", task="vqa")[5].params == {"task": "change"}
        assert plan("water", "fusion")[5].params == {"task": "fusion"}

    def test_every_planned_task_is_a_permitted_parameter(self):
        from satsaathi_tools.builtin import build_default_registry

        registry = build_default_registry()
        for mode in ("single", "change", "fusion"):
            for task in ("vqa", "caption", "grounding"):
                for sensor in ("optical", "sar"):
                    step = plan("land_cover", mode, sensor=sensor, task=task)[5]
                    tool = registry.get(step.tool_name)
                    tool.validate_params(step.params)  # raises if not permitted
