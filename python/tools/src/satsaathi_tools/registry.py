"""Tool lookup, and the rule-based planner that orders them.

The planner is deliberately dumb: a table from (intent, input mode) to an
ordered list of tool names. Nothing here reasons. The agentic controller that
eventually replaces it plugs in behind `plan`, and the eight fixed step keys
stay the same either way so the trace shape never changes.
"""

from __future__ import annotations

from dataclasses import dataclass

from .protocol import BaseTool

STEP_KEYS = (
    "ask",
    "imagery",
    "understand",
    "preprocess",
    "compute",
    "vision_language",
    "verify",
    "answer",
)

Intent = str
InputMode = str


class UnknownToolError(KeyError):
    pass


class Registry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> BaseTool:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool
        return tool

    def get(self, name: str) -> BaseTool:
        if name not in self._tools:
            raise UnknownToolError(name)
        return self._tools[name]

    def all(self) -> list[BaseTool]:
        return sorted(self._tools.values(), key=lambda t: t.name)

    def for_task(self, task: str) -> list[BaseTool]:
        return [t for t in self.all() if t.task == task]

    def describe(self) -> list[dict]:
        return [t.describe() for t in self.all()]

    def __contains__(self, name: object) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)


@dataclass(frozen=True)
class PlannedStep:
    step_key: str
    tool_name: str
    params: dict


#: Which vision-language tool answers which intent.
_VLM_BY_INTENT: dict[Intent, str] = {
    "vqa": "vlm.vqa.stub",
    "caption": "vlm.caption.stub",
    "grounding": "vlm.grounding.stub",
    "change": "vlm.change.stub",
    "fusion": "vlm.fusion.stub",
}

#: Which index a given intent wants computed, when one is computable at all.
_INDEX_BY_INTENT: dict[Intent, str] = {
    "water": "ndwi",
    "vegetation": "ndvi",
    "moisture": "lswi",
}


def plan(
    intent: Intent,
    mode: InputMode,
    *,
    available_indices: list[str] | None = None,
) -> list[PlannedStep]:
    """Map (intent, mode) to an ordered plan over the eight fixed steps.

    `available_indices` is what the band mapping actually supports. An index
    the input cannot support is never planned, so the pipeline does not
    discover the problem halfway through and improvise.
    """
    supported = set(available_indices or [])
    steps: list[PlannedStep] = [
        PlannedStep("ask", "intake.text", {}),
        PlannedStep("imagery", "imagery.inspect", {}),
        PlannedStep("understand", "intent.keyword", {}),
    ]

    if mode in ("fusion", "change"):
        steps.append(PlannedStep("preprocess", "preprocess.coregister.stub", {}))
    else:
        steps.append(PlannedStep("preprocess", "preprocess.noop", {}))

    wanted = _INDEX_BY_INTENT.get(intent)
    if wanted and wanted in supported:
        steps.append(PlannedStep("compute", "indices.compute", {"index": wanted}))
    elif supported:
        # Compute something the input genuinely supports rather than nothing.
        steps.append(
            PlannedStep("compute", "indices.compute", {"index": sorted(supported)[0]})
        )
    else:
        steps.append(PlannedStep("compute", "indices.unavailable", {}))

    vlm = _VLM_BY_INTENT.get(intent)
    if vlm is None:
        vlm = "vlm.change.stub" if mode == "change" else "vlm.vqa.stub"
    steps.append(PlannedStep("vision_language", vlm, {}))

    steps.append(PlannedStep("verify", "verify.crosscheck", {}))
    steps.append(PlannedStep("answer", "answer.template", {}))
    return steps


def plan_is_complete(steps: list[PlannedStep]) -> bool:
    """A plan must cover every step key exactly once, in the fixed order."""
    return tuple(s.step_key for s in steps) == STEP_KEYS
