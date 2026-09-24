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


#: Which index a given intent wants computed, when one is computable at all.
_INDEX_BY_INTENT: dict[Intent, str] = {
    "water": "ndwi",
    "vegetation": "ndvi",
    "moisture": "lswi",
}

#: Index -> the vision-language tool that reads its rendered map.
_INDEX_VLM: dict[str, str] = {"ndvi": "vlm.index.ndvi", "ndwi": "vlm.index.ndwi"}

_SAR_ROLES = {"vv", "vh", "hh", "hv"}
_OPTICAL_ROLES = {"blue", "green", "red", "nir", "swir1"}


def effective_sensor(sensor_type: str | None, band_map: dict | None) -> str:
    """What the upload is, for routing: "sar", "optical" or "unknown".

    The officer's band mapping wins over the file's headers — choosing the
    Sentinel-1 preset is a statement that the scene is SAR — and headers win
    over nothing. Inspection already inferred SAR from 8-bit greyscale.
    """
    roles = set((band_map or {}).keys())
    if roles & _SAR_ROLES:
        return "sar"
    if roles & _OPTICAL_ROLES:
        return "optical"
    if sensor_type in ("sar", "optical"):
        return sensor_type
    return "unknown"


def plan(
    intent: Intent,
    mode: InputMode,
    *,
    available_indices: list[str] | None = None,
    sensor: str | None = None,
    vlm_indices: list[str] | None = None,
) -> list[PlannedStep]:
    """Map (intent, mode, sensor) to an ordered plan over the eight fixed steps.

    `available_indices` is what the band mapping actually supports. An index
    the input cannot support is never planned, so the pipeline does not
    discover the problem halfway through and improvise.

    `sensor` routes the vision-language step to the adapter trained on that
    kind of image — SAR to the SAR adapter, optical to the optical one. An
    optical model reading backscatter as brightness is confidently wrong.

    `vlm_indices` are indices whose reading adapter is installed *and* whose
    training inputs the bands can reproduce; a water or vegetation question
    over such bands is answered by that adapter.
    """
    supported = set(available_indices or [])
    readable = set(vlm_indices or [])
    is_sar = mode == "sar" or (mode == "single" and sensor == "sar")
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
    if is_sar and intent == "water":
        # SAR has no spectral index; its water measurement is backscatter.
        steps.append(PlannedStep("compute", "sar.water_mask", {}))
    elif wanted and wanted in supported:
        steps.append(PlannedStep("compute", "indices.compute", {"index": wanted}))
    elif supported:
        # Compute something the input genuinely supports rather than nothing.
        steps.append(
            PlannedStep("compute", "indices.compute", {"index": sorted(supported)[0]})
        )
    else:
        steps.append(PlannedStep("compute", "indices.unavailable", {}))

    if mode == "change":
        vlm = "vlm.change"
    elif mode == "fusion":
        vlm = "vlm.fusion"
    elif is_sar:
        vlm = "vlm.sar"
    elif intent == "caption":
        vlm = "vlm.caption"
    elif intent == "grounding":
        vlm = "vlm.grounding"
    elif wanted in _INDEX_VLM and wanted in readable and wanted in supported:
        vlm = _INDEX_VLM[wanted]
    else:
        vlm = "vlm.vqa"
    steps.append(PlannedStep("vision_language", vlm, {}))

    steps.append(PlannedStep("verify", "verify.crosscheck", {}))
    steps.append(PlannedStep("answer", "answer.template", {}))
    return steps


def plan_is_complete(steps: list[PlannedStep]) -> bool:
    """A plan must cover every step key exactly once, in the fixed order."""
    return tuple(s.step_key for s in steps) == STEP_KEYS


#: Queue precedence. A plan runs as one task, so it needs the scarcest queue
#: any of its steps asks for — a job with one GPU step must not be handed to a
#: CPU worker that would fail at that step.
_QUEUE_RANK = {"cpu": 0, "lang": 1, "gpu": 2}


def queue_for(steps: list[PlannedStep], registry: Registry) -> str:
    """The queue a whole plan must run on.

    Unknown tools are ignored rather than raising: a plan is validated when it
    executes, and refusing to route it here would turn a bad plan into a
    dispatch crash instead of a recorded step failure.
    """
    queue = "cpu"
    for step in steps:
        try:
            tool = registry.get(step.tool_name)
        except UnknownToolError:
            continue
        candidate = getattr(tool, "queue", "cpu")
        if _QUEUE_RANK.get(candidate, 0) > _QUEUE_RANK.get(queue, 0):
            queue = candidate
    return queue
