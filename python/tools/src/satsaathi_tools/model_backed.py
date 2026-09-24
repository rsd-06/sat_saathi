"""The seam where a fixture becomes a real prediction.

One tool, two behaviours. When the weights for its model are on the machine it
runs them; when they are not it produces the fixture its stub always produced.
What it must never do is blur the two, so the switch is visible in three
places the trace records:

  * `is_stub` flips to False only when a model (or a classical measurement)
    actually ran,
  * `version` carries the model revision, so two answers from different
    weights are not recorded as the same system,
  * `output_summary["source"]` says "model", "classical" or "fixture" in words.

This is the whole reason the trace is worth showing. A system that quietly
degraded to a plausible-looking fixture, and reported the same confidence
either way, would be worse than one that had no model at all.

Failures map onto that rule:

  * load failure, missing GPU stack  -> fixture, note `model.not_loadable`
  * out of GPU memory                -> fixture, note `model.oom`
  * the model answered, unparseably  -> model (it did run), note
    `model.output_unparseable`, and the step is held for review — decided
    inside `predict`, which knows what shape it wanted.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .protocol import BaseTool, ToolContext, ToolResult

SOURCES = ("model", "classical", "fixture")


class ModelBackedTool(BaseTool):
    """A tool that prefers a model and falls back to a fixture.

    Subclasses implement `predict` for the real path. `fixture` is the
    behaviour when no weights are present, and is where the existing stub
    logic lives unchanged.
    """

    #: Name in the model catalog. Not a path and not a runtime.
    model_name: str = ""
    #: Version of the tool's own logic, before the model revision is appended.
    base_version: str = "0.1.0"

    def __init__(self, catalog: Any = None):
        # The catalog is injected so tests can point at a temporary directory
        # and so a process with no models configured still constructs.
        self._catalog = catalog

    # -- availability -----------------------------------------------------

    def _status(self) -> Any:
        if self._catalog is None:
            return None
        return self._catalog.status(self.model_name)

    @property
    def model_available(self) -> bool:
        status = self._status()
        return bool(status and status.available)

    @property
    def is_stub(self) -> bool:  # type: ignore[override]
        return not self.model_available

    @property
    def version(self) -> str:  # type: ignore[override]
        """Includes the weights revision whenever a model would be used.

        `0.1.0` and `0.1.0+vqa-optical@v1` are different systems, and a trace
        that called them both `0.1.0` would be lying by omission.
        """
        status = self._status()
        if status and status.available:
            return f"{self.base_version}+{status.spec.slug}"
        return self.base_version

    @property
    def queue(self) -> str:  # type: ignore[override]
        """Where this tool must run.

        A model-backed tool needs its model's hardware only when the weights
        are present; with none installed it is a dictionary lookup and belongs
        on the CPU queue like anything else. Routing a fixture to a GPU worker
        would idle the scarcest machine in the deployment.
        """
        status = self._status()
        if status and status.available:
            return status.spec.queue
        return "cpu"

    def describe(self) -> dict[str, Any]:
        described = super().describe()
        status = self._status()
        described.update(
            {
                "version": self.version,
                "is_stub": self.is_stub,
                "queue": self.queue,
                "model": {
                    "name": self.model_name,
                    "available": bool(status and status.available),
                    "revision": status.spec.revision if status else None,
                    "fingerprint": status.fingerprint if status else None,
                },
            }
        )
        return described

    # -- execution --------------------------------------------------------

    def run(
        self, inputs: dict[str, Any], params: BaseModel, ctx: ToolContext
    ) -> ToolResult:
        status = self._status()
        if status is None or not status.available:
            return self._tagged(self.fixture(inputs, params, ctx), "fixture", None)

        from satsaathi_models import (
            ModelOOMError,
            ModelUnavailableError,
            load,
        )

        model: Any = None
        if status.spec.kind != "classical":
            try:
                model = load(status.spec, Path(self._catalog.root))
            except ModelUnavailableError:
                # Declared and present but not loadable — a missing runtime,
                # most often. Answering with a fixture is fine; pretending it
                # came from the model is not, so this takes the fixture path
                # in full.
                return self._fallback(inputs, params, ctx, "model.not_loadable")

        try:
            result = self.predict(model, inputs, params, ctx)
        except ModelOOMError:
            return self._fallback(inputs, params, ctx, "model.oom")
        except ModelUnavailableError:
            # The runtime loads its weights on first use, so a broken install
            # surfaces here rather than at `load`. Same rule: fixture, said so.
            return self._fallback(inputs, params, ctx, "model.not_loadable")

        source = result.output_summary.get("source") or (
            "classical" if status.spec.kind == "classical" else "model"
        )
        return self._tagged(result, source, None)

    def _fallback(
        self, inputs: dict[str, Any], params: BaseModel, ctx: ToolContext, note: str
    ) -> ToolResult:
        return self._tagged(self.fixture(inputs, params, ctx), "fixture", note)

    def _tagged(self, result: ToolResult, source: str, note: str | None) -> ToolResult:
        """Stamp the result with what actually ran.

        `source` is for a reader; `is_stub` and `tool_version` are for the
        trace. All three have to agree, and they only can if they are set from
        the same branch that produced the output.
        """
        assert source in SOURCES, source
        ran = source != "fixture"
        result.output_summary = {**result.output_summary, "source": source}
        result.is_stub = not ran
        result.tool_version = self.version if ran else self.base_version
        if note and not result.note:
            result.note = note
        if not ran:
            # A fixture carries no confidence of its own; whatever the stub
            # hard-coded must not reach verify as if it were measured.
            result.confidence = None
        return result

    def fixture(
        self, inputs: dict[str, Any], params: BaseModel, ctx: ToolContext
    ) -> ToolResult:  # pragma: no cover - subclasses implement
        raise NotImplementedError

    def predict(
        self, model: Any, inputs: dict[str, Any], params: BaseModel, ctx: ToolContext
    ) -> ToolResult:  # pragma: no cover - subclasses implement
        raise NotImplementedError
