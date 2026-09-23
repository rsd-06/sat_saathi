"""Running a plan and recording what happened.

Deliberately free of Celery, Redis and the database: this takes a plan, a
registry and an emitter, and returns a trace. The worker wraps it; the tests
call it directly. That separation is what makes the pipeline testable without
standing up a broker.

The trace is the product, not a by-product. Every step is recorded whether it
succeeded, was skipped or failed, with the tool that ran, the parameters it was
permitted, how long it took, and whether its output was measured or fixture.
"""

from __future__ import annotations

import time
import traceback
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from .protocol import RejectedParamsError, ToolContext, ToolResult
from .registry import PlannedStep, Registry

TRACE_VERSION = 1

Emitter = Callable[[dict[str, Any]], None]


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class StepRecord:
    step_key: str
    ordinal: int
    status: str = "pending"
    tool_name: str | None = None
    tool_version: str | None = None
    is_stub: bool | None = None
    params: dict[str, Any] = field(default_factory=dict)
    output_summary: dict[str, Any] = field(default_factory=dict)
    note: str | None = None
    error: dict[str, Any] | None = None
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int | None = None
    artifacts: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Trace:
    trace_version: int
    job_id: str
    created_at: str
    query: dict[str, Any]
    input_set: dict[str, Any]
    plan: list[dict[str, Any]]
    steps: list[StepRecord]
    status: str = "running"
    confidence: float | None = None
    answer: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_version": self.trace_version,
            "job_id": self.job_id,
            "created_at": self.created_at,
            "status": self.status,
            "query": self.query,
            "input_set": self.input_set,
            "plan": self.plan,
            "steps": [asdict(s) for s in self.steps],
            "confidence": self.confidence,
            "answer": self.answer,
        }


class PipelineError(RuntimeError):
    def __init__(self, step_key: str, message: str):
        self.step_key = step_key
        super().__init__(message)


def _step_inputs(
    step: PlannedStep, base: dict[str, Any], results: dict[str, ToolResult]
) -> dict[str, Any]:
    """What a step can see: the job inputs plus earlier steps' summaries.

    Passing whole result objects forward would let a step reach into another's
    internals; only the summary and evidence cross the boundary.
    """
    inputs = dict(base)
    compute = results.get("compute")
    if compute is not None:
        inputs["measured"] = compute.output_summary
    vlm = results.get("vision_language")
    if vlm is not None:
        inputs["claims"] = {
            "caption": vlm.output_summary.get("caption"),
            "index": base.get("planned_index"),
            "mentions_area": "area_ha" in (compute.output_summary if compute else {}),
        }
    understand = results.get("understand")
    if understand is not None:
        inputs["intent"] = understand.output_summary.get("intent")
    return inputs


def run(
    *,
    job_id: str,
    plan: Iterable[PlannedStep],
    registry: Registry,
    ctx: ToolContext,
    inputs: dict[str, Any],
    query: dict[str, Any],
    input_set: dict[str, Any],
    emit: Emitter | None = None,
    confidence_threshold: float = 0.75,
    stub_delay_ms: int = 0,
) -> Trace:
    """Execute a plan end to end, emitting the trace as it changes.

    A step that raises does not abort silently: it is recorded as failed with
    the exception's message, the remaining steps are recorded as skipped, and
    the trace still comes back whole.
    """
    plan_list = list(plan)
    trace = Trace(
        trace_version=TRACE_VERSION,
        job_id=job_id,
        created_at=_now().isoformat(),
        query=query,
        input_set=input_set,
        plan=[
            {"step_key": s.step_key, "tool": s.tool_name, "params": s.params}
            for s in plan_list
        ],
        steps=[
            StepRecord(step_key=s.step_key, ordinal=i)
            for i, s in enumerate(plan_list)
        ],
    )

    def publish() -> None:
        if emit is not None:
            emit(trace.to_dict())

    publish()

    results: dict[str, ToolResult] = {}
    failed = False

    for index, planned in enumerate(plan_list):
        record = trace.steps[index]

        if failed:
            record.status = "skipped"
            record.note = "pipeline.aborted_earlier"
            publish()
            continue

        record.status = "running"
        record.started_at = _now().isoformat()
        publish()

        started = time.perf_counter()
        try:
            tool = registry.get(planned.tool_name)
            params = tool.validate_params(planned.params)

            # Real steps are fast enough that the trace would flash past. A
            # configurable pause on stub steps only lets the sequence be
            # watched, and never inflates a measured step's timing.
            if stub_delay_ms and tool.is_stub:
                time.sleep(stub_delay_ms / 1000)

            record.tool_name = tool.name
            record.tool_version = tool.version
            record.is_stub = tool.is_stub
            record.params = params.model_dump()

            result = tool.run(
                _step_inputs(planned, inputs, results), params, ctx
            )
            results[planned.step_key] = result

            # A tool that expected to run a model but fell back to a fixture
            # says so here, and that correction wins: a trace claiming a model
            # ran when one did not is the exact failure this product exists to
            # prevent.
            if result.is_stub is not None:
                record.is_stub = result.is_stub
            if result.tool_version is not None:
                record.tool_version = result.tool_version

            record.output_summary = result.output_summary
            record.note = result.note
            record.artifacts = [asdict(a) for a in result.artifacts]
            # A tool may declare its own terminal status through its note.
            record.status = (
                "skipped" if (result.note or "").endswith("skipped") else "succeeded"
            )
            if result.confidence is not None:
                trace.confidence = result.confidence
                if result.confidence < confidence_threshold:
                    record.status = "needs_review"

        except RejectedParamsError as exc:
            failed = True
            record.status = "failed"
            record.error = {"key": "tool.params_rejected", "params": {"detail": str(exc)}}
        except Exception as exc:  # noqa: BLE001 - the trace must record anything
            failed = True
            record.status = "failed"
            record.error = {
                "key": "tool.failed",
                "params": {
                    "tool": planned.tool_name,
                    "detail": str(exc),
                    "type": type(exc).__name__,
                },
            }
            record.output_summary = {"traceback": traceback.format_exc(limit=3)}
        finally:
            record.finished_at = _now().isoformat()
            record.duration_ms = int((time.perf_counter() - started) * 1000)
            publish()

    answer_result = results.get("answer")
    if answer_result is not None and answer_result.evidence:
        trace.answer = {"text": answer_result.evidence.get("text")}

    if failed:
        trace.status = "failed"
    elif trace.confidence is not None and trace.confidence < confidence_threshold:
        trace.status = "needs_review"
    else:
        trace.status = "succeeded"

    publish()
    return trace
