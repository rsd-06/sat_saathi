"""The contract every step-executing tool implements.

A tool declares what it needs and what parameters it will accept, and nothing
else may be passed to it — the problem statement requires that only permitted
task parameters be configurable, so `params_schema` is the enforcement point,
not a suggestion.

`is_stub` is part of the contract rather than a comment: the execution trace
shows which steps measured something and which returned fixture output, and
that distinction is the reason the trace is worth showing at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ValidationError

Task = str

TASKS: frozenset[Task] = frozenset(
    {
        "vqa",
        "caption",
        "grounding",
        "change_detection",
        "change_vqa",
        "optical_sar_fusion",
        "index_compute",
        "sar_water_mask",
        "translate",
        "asr",
        "tts",
        "llm_explain",
        "verify",
    }
)


class RejectedParamsError(ValueError):
    """Raised when a caller passes a parameter a tool does not permit."""

    def __init__(self, tool: str, errors: str):
        self.tool = tool
        super().__init__(f"{tool} rejected the given parameters: {errors}")


@dataclass
class Artifact:
    name: str
    kind: str  # cog | geojson | pdf | png | trace
    storage_key: str
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    output_summary: dict[str, Any]
    artifacts: list[Artifact] = field(default_factory=list)
    confidence: float | None = None
    evidence: dict[str, Any] | None = None
    """Set when a tool declines to produce a figure it cannot support."""
    note: str | None = None

    #: What actually happened, when it differs from what the tool expected.
    #:
    #: A model-backed tool reports `is_stub = False` while its weights are
    #: installed, but a load can still fail at the moment of use and send it
    #: down the fixture path. The trace must record the run that happened, not
    #: the one that was planned, so a result may correct both of these and the
    #: pipeline prefers them over the tool's own properties.
    is_stub: bool | None = None
    tool_version: str | None = None
    #: A tool's own verdict on whether its output must be held for a person.
    #: None leaves it to the pipeline's confidence threshold, which is right
    #: for a measured-only step and wrong for a model answer whose confidence
    #: is calibrated against held-out accuracy (see `confidence.py`).
    needs_review: bool | None = None


@dataclass
class ToolContext:
    """Everything a tool may touch. Nothing reaches out beyond this."""

    job_id: str
    storage: Any
    settings: Any
    inputs: dict[str, Any] = field(default_factory=dict)


class NoParams(BaseModel):
    model_config = {"extra": "forbid"}


@runtime_checkable
class Tool(Protocol):
    name: str
    version: str
    task: Task
    required_modalities: list[str]
    params_schema: type[BaseModel]
    is_stub: bool
    #: Which worker queue can run this. A tool that needs a GPU says so here
    #: rather than discovering it has no device halfway through a job.
    queue: str

    def run(
        self, inputs: dict[str, Any], params: BaseModel, ctx: ToolContext
    ) -> ToolResult: ...


class BaseTool:
    """Shared plumbing: parameter validation and self-description."""

    name: str = "unnamed"
    version: str = "0.0.0"
    task: Task = "vqa"
    required_modalities: list[str] = []
    params_schema: type[BaseModel] = NoParams
    is_stub: bool = True
    queue: str = "cpu"

    def validate_params(self, params: dict[str, Any] | None) -> BaseModel:
        try:
            return self.params_schema.model_validate(params or {})
        except ValidationError as exc:
            raise RejectedParamsError(self.name, exc.json(indent=None)) from exc

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "task": self.task,
            "required_modalities": list(self.required_modalities),
            "params_schema": self.params_schema.model_json_schema(),
            "is_stub": self.is_stub,
            "queue": self.queue,
        }

    def run(
        self, inputs: dict[str, Any], params: BaseModel, ctx: ToolContext
    ) -> ToolResult:  # pragma: no cover - subclasses implement
        raise NotImplementedError
