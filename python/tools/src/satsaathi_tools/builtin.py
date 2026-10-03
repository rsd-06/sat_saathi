"""The tools that exist today.

Two kinds live here, and the difference is recorded on every one of them:

- Real tools measure something. `imagery.inspect` reads GeoTIFF headers and
  `indices.compute` computes an index from mapped bands. Their numbers can be
  checked against the file.
- Stub tools return fixture output. They exist so the eight-step pipeline runs
  end to end before any model exists, and every one is marked `is_stub=True`
  so the trace never implies a measurement that did not happen.

Replacing a stub means writing a tool with the same name, task and parameter
schema and registering it instead. Nothing above this module changes.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from satsaathi_core import indices as index_maths
from satsaathi_core.raster import inspect as inspect_raster

from .protocol import Artifact, BaseTool, NoParams, ToolContext, ToolResult
from .vlm import (
    SarWaterMask,
    VlmCaption,
    VlmChange,
    VlmFusion,
    VlmGrounding,
    VlmIndexNdvi,
    VlmIndexNdwi,
    VlmSar,
    VlmVqa,
)

# --------------------------------------------------------------------------
# Real tools
# --------------------------------------------------------------------------


class IntakeParams(BaseModel):
    model_config = {"extra": "forbid"}

    query_lang: str = "en"
    ui_lang: str = "en"


class IntakeText(BaseTool):
    name = "intake.text"
    version = "0.1.0"
    task = "vqa"
    required_modalities: list[str] = []
    params_schema = IntakeParams
    is_stub = False

    def run(self, inputs, params: IntakeParams, ctx: ToolContext) -> ToolResult:
        question = str(inputs.get("question", ""))
        return ToolResult(
            output_summary={
                "chars": len(question),
                "query_lang": params.query_lang,
                "ui_lang": params.ui_lang,
            }
        )


class ImageryInspect(BaseTool):
    name = "imagery.inspect"
    version = "0.1.0"
    task = "index_compute"
    required_modalities = ["raster"]
    params_schema = NoParams
    is_stub = False

    def run(self, inputs, params, ctx: ToolContext) -> ToolResult:
        path = Path(inputs["path"])
        meta = inspect_raster(path)
        return ToolResult(
            output_summary={
                "driver": meta.driver,
                "width": meta.width,
                "height": meta.height,
                "bands": meta.band_count,
                "crs": meta.crs or "none",
                "pixel_size": meta.pixel_size[0] if meta.pixel_size else None,
                "sensor_type": meta.sensor_type,
                "georeferenced": meta.is_georeferenced,
            },
            evidence={"footprint": meta.footprint, "warnings": meta.warnings},
            note=None if meta.is_georeferenced else "raster.not_georeferenced",
        )


class IndexParams(BaseModel):
    model_config = {"extra": "forbid"}

    index: Literal["ndvi", "ndwi", "lswi"] = "ndvi"
    threshold: float = Field(default=0.0, ge=-1.0, le=1.0)


class IndicesCompute(BaseTool):
    name = "indices.compute"
    version = "0.1.0"
    task = "index_compute"
    required_modalities = ["raster"]
    params_schema = IndexParams
    is_stub = False

    def run(self, inputs, params: IndexParams, ctx: ToolContext) -> ToolResult:
        result = index_maths.compute(
            inputs["path"],
            params.index,
            inputs["band_map"],
            threshold=params.threshold,
            max_pixels=getattr(ctx.settings, "max_index_pixels", 4096 * 4096),
        )
        summary: dict[str, Any] = {
            "index": result.name,
            "mean": round(result.mean, 4),
            "min": round(result.minimum, 4),
            "max": round(result.maximum, 4),
            "valid_pixels": result.valid_pixels,
            "above_threshold_pct": round(result.above_threshold_pct, 2),
        }
        if result.area_above_threshold_ha is None:
            summary["area_ha"] = None
        else:
            summary["area_ha"] = round(result.area_above_threshold_ha, 3)

        return ToolResult(
            output_summary=summary,
            note=None if result.pixel_area_m2 else "area.requires_crs",
        )


class IndicesUnavailable(BaseTool):
    """Records, in the trace, that no index was computable and why."""

    name = "indices.unavailable"
    version = "0.1.0"
    task = "index_compute"
    required_modalities = ["raster"]
    params_schema = NoParams
    is_stub = False

    def run(self, inputs, params, ctx: ToolContext) -> ToolResult:
        missing = index_maths.available_indices(inputs.get("band_map", {}))
        return ToolResult(
            output_summary={
                name: "needs " + ", ".join(roles) for name, roles in missing.items()
            },
            note="indices.none_available",
        )


class VerifyParams(BaseModel):
    model_config = {"extra": "forbid"}

    threshold: float = Field(default=0.75, ge=0.0, le=1.0)


class VerifyCrosscheck(BaseTool):
    """Scores agreement between what was described and what was measured.

    Real arithmetic over real inputs, but a blunt rule: it penalises a claim
    the measurement cannot support. A learned verifier replaces it later.
    """

    name = "verify.crosscheck"
    version = "0.1.0"
    task = "verify"
    required_modalities: list[str] = []
    params_schema = VerifyParams
    is_stub = False

    @staticmethod
    def _has_measurement(measured: dict[str, Any]) -> bool:
        """A dict of reasons is not a measurement.

        `indices.unavailable` reports why each index could not be computed, so
        the summary is non-empty while nothing was actually measured. Truthiness
        would read that as success and release a fully confident answer backed
        by no numbers at all.
        """
        return isinstance(measured.get("above_threshold_pct"), (int, float))

    def run(self, inputs, params: VerifyParams, ctx: ToolContext) -> ToolResult:
        measured: dict[str, Any] = inputs.get("measured") or {}
        claims: dict[str, Any] = inputs.get("claims") or {}
        vision: dict[str, Any] = inputs.get("vision") or {}

        if vision.get("source") == "model" and isinstance(vision.get("confidence"), float):
            return self._model_answer(vision, measured, claims, ctx)
        if vision.get("source") == "classical":
            # A classical map with no model answer: its numbers are measured,
            # so it is judged like any measured-only step.
            measured = {**measured, **{"above_threshold_pct": vision.get("changed_pct")}}

        confidence = 0.9
        reasons: list[str] = []

        if not self._has_measurement(measured):
            confidence -= 0.4
            reasons.append("no_measurement")
        if measured.get("area_ha") is None and claims.get("mentions_area"):
            confidence -= 0.3
            reasons.append("area_claimed_without_crs")
        if claims.get("index") and claims["index"] not in str(measured.get("index")):
            confidence -= 0.25
            reasons.append("index_mismatch")

        confidence = max(0.0, min(1.0, confidence))
        return ToolResult(
            output_summary={
                "confidence": round(confidence, 2),
                "verdict": (
                    "released" if confidence >= params.threshold else "held_for_review"
                ),
                "reasons": ",".join(reasons) or "none",
            },
            confidence=confidence,
        )

    def _model_answer(
        self, vision: dict[str, Any], measured: dict[str, Any], claims: dict[str, Any],
        ctx: ToolContext,
    ) -> ToolResult:
        """A model answer carries a calibrated confidence; verify checks it.

        The confidence already folds in the held-out prior, so it is judged
        against the model thresholds (`confidence_low` / `_high`), not the
        0.75 used for measured-only answers — against which even the best
        adapter here (optical VQA, 0.60 held-out) could never pass.
        """
        from .confidence import band, thresholds

        high, low = thresholds(ctx.settings)
        confidence = float(vision["confidence"])
        reasons: list[str] = ["model_confidence"]
        if measured.get("area_ha") is None and claims.get("mentions_area"):
            confidence *= 0.7
            reasons.append("area_claimed_without_crs")
        if vision.get("box_status") and "unverified" in str(vision.get("box_status")):
            reasons.append("sar_boxes_unverified")
        if vision.get("note"):
            reasons.append(str(vision["note"]))
        level = band(confidence, high, low)
        held = level == "low" or bool(vision.get("needs_review"))
        return ToolResult(
            output_summary={
                "confidence": round(confidence, 3),
                "confidence_band": level,
                "verdict": "held_for_review" if held else "released",
                "reasons": ",".join(reasons),
                "threshold_low": low,
                "threshold_high": high,
            },
            confidence=confidence,
            needs_review=held,
        )


class PreprocessNoop(BaseTool):
    name = "preprocess.noop"
    version = "0.1.0"
    task = "index_compute"
    required_modalities = ["raster"]
    params_schema = NoParams
    is_stub = False

    def run(self, inputs, params, ctx: ToolContext) -> ToolResult:
        return ToolResult(
            output_summary={"reason": "single raster; nothing to co-register"},
            note="preprocess.skipped",
        )


# --------------------------------------------------------------------------
# Stub tools — fixture output, plainly marked
# --------------------------------------------------------------------------


class IntentParams(BaseModel):
    model_config = {"extra": "forbid"}

    classifier: Literal["keyword"] = "keyword"


class IntentKeyword(BaseTool):
    """Keyword intent classification. The real classifier replaces this."""

    name = "intent.keyword"
    version = "0.1.0"
    task = "llm_explain"
    required_modalities: list[str] = []
    params_schema = IntentParams
    is_stub = True

    #: Matching is token-anchored, never substring-anywhere: "பின்" (after)
    #: once matched inside "பின்வருமாறு" (as follows) and routed an unrelated
    #: sentence to change detection. Bare positional words are excluded for
    #: the same reason — they carry no intent and hide inside compounds.
    KEYWORDS: dict[str, tuple[str, ...]] = {
        "water": (
            "water", "flood", "flooded", "flooding", "inundated", "inundation",
            "submerged", "river", "lake", "waterlogged",
            "पानी", "बाढ़", "जलमग्न", "नदी", "झील",
            "நீர", "வெள்ள", "மூழ்க", "ஆறு", "ஏரி",
            "জল", "বন্যা", "জলমগ্ন", "নদী", "প্লাবিত",
        ),
        "vegetation": (
            "crop", "crops", "paddy", "rice", "vegetation", "farm", "farmland",
            "field", "fields", "harvest", "yield", "canopy", "greenery",
            "फसल", "धान", "खेत", "हरियाली", "वनस्पति",
            "பயிர்", "நெல்", "வயல்", "தாவர", "பசுமை",
            "ফসল", "ধান", "ক্ষেত", "সবুজ", "গাছপালা",
        ),
        "change": (
            "change", "changed", "changes", "difference", "differences",
            "compare", "comparison",
            "बदल", "परिवर्तन", "अंतर", "तुलना",
            "மாற்ற", "மாறி", "மாறு", "வேறுபாடு", "ஒப்பிட",
            "পরিবর্তন", "বদল", "পার্থক্য", "তুলনা",
        ),
        "built_up": (
            "built", "urban", "building", "buildings", "settlement",
            "city", "town", "road", "roads", "infrastructure",
            "निर्मित", "शहर", "इमारत", "बस्ती", "सड़क",
            "கட்டிட", "நகர", "குடியிருப்", "சாலை",
            "নির্মিত", "শহর", "বাড়ি", "বসতি", "রাস্তা",
        ),
    }

    _SPLIT = re.compile(r"[\s.,;:!?'\"()\[\]{}/\\|<>@#$%^&*+=~`_—–-]+")

    def run(self, inputs, params: IntentParams, ctx: ToolContext) -> ToolResult:
        question = str(inputs.get("question", "")).lower()
        tokens = [t for t in self._SPLIT.split(question) if t]

        best, matched, best_score = "land_cover", [], 0
        for intent, words in self.KEYWORDS.items():
            hits = [
                w
                for w in words
                # Anchored to a token start, which tolerates the suffixes
                # Tamil, Hindi and Bengali attach without matching mid-word.
                if any(t == w or t.startswith(w) for t in tokens)
            ]
            # Longer terms are more specific, so weight by length.
            score = sum(len(w) for w in hits)
            if score > best_score:
                best, matched, best_score = intent, hits, score

        return ToolResult(
            output_summary={
                "intent": best,
                "matched": ",".join(matched) or "(none)",
                "score": best_score,
            },
            note=None if matched else "intent.defaulted",
        )


class PreprocessCoregister(BaseTool):
    name = "preprocess.coregister.stub"
    version = "0.1.0"
    task = "index_compute"
    required_modalities = ["raster"]
    params_schema = NoParams
    is_stub = True

    def run(self, inputs, params, ctx: ToolContext) -> ToolResult:
        return ToolResult(
            output_summary={
                "status": "skipped",
                "reason": "inputs assumed already co-registered",
            }
        )


class AnswerParams(BaseModel):
    model_config = {"extra": "forbid"}

    target_lang: str = "en"


class AnswerTemplate(BaseTool):
    """Templated phrasing. The LLM provider replaces this."""

    name = "answer.template"
    version = "0.1.0"
    task = "llm_explain"
    required_modalities: list[str] = []
    params_schema = AnswerParams
    is_stub = True

    def run(self, inputs, params: AnswerParams, ctx: ToolContext) -> ToolResult:
        measured = inputs.get("measured") or {}
        vision = inputs.get("vision") or {}
        pieces: list[str] = []
        if vision.get("source") in ("model", "classical") and vision.get("answer"):
            said = str(vision.get("text") or vision["answer"]).strip()
            boxes = [b for b in str(vision.get("boxes_2d") or "").split(";") if b.strip()]
            if boxes and (said.startswith("`") or said.startswith("[")):
                # A grounding answer is JSON; the officer reads it as a sentence.
                labels = [b.split("[")[0].strip() or "object" for b in boxes]
                noun = labels[0] if len(set(labels)) == 1 else "object"
                said = (
                    f"Found {len(boxes)} {noun}{'s' if len(boxes) > 1 else ''}, "
                    f"marked on the image ({vision.get('box_status', 'model')})"
                )
            pieces.append(said)
            if "unverified" in str(vision.get("box_status", "")):
                pieces.append(
                    "The SAR locations are unverified: no independent detection "
                    "confirms them."
                )
        if measured.get("above_threshold_pct") is not None:
            pieces.append(
                f"{measured['above_threshold_pct']}% of valid pixels exceed the "
                f"{measured.get('index', 'index')} threshold"
            )
        if measured.get("area_ha") is not None:
            pieces.append(f"covering {measured['area_ha']} ha")
        if measured.get("water_pct") is not None:
            pieces.append(f"SAR backscatter marks {measured['water_pct']}% of the scene as water")
        # The model's own words go out verbatim: no added punctuation, which
        # once turned a Hindi "।" into "।.". Only our own sentences get a stop.
        model_spoke = vision.get("source") in ("model", "classical") and vision.get("answer")
        said_verbatim = pieces[:1] if model_spoke else []
        rest = [p if p.endswith(".") else p + "." for p in pieces[len(said_verbatim):]]
        text = " ".join(said_verbatim + rest) if pieces else "No measurement was available."

        return ToolResult(
            output_summary={"chars": len(text), "target_lang": params.target_lang},
            evidence={"text": text},
        )


def build_default_registry(catalog=None):
    """Every tool the system currently has, in one place.

    `catalog` decides whether the model-backed tools have anything to run.
    Passing None is the same as a machine with no weights installed: every
    such tool reports itself as fixture output, which is the truth.
    """
    from .registry import Registry

    registry = Registry()
    for tool in (
        IntakeText(),
        ImageryInspect(),
        IntentKeyword(),
        PreprocessNoop(),
        PreprocessCoregister(),
        IndicesCompute(),
        IndicesUnavailable(),
        SarWaterMask(catalog),
        VlmVqa(catalog),
        VlmSar(catalog),
        VlmCaption(catalog),
        VlmGrounding(catalog),
        VlmChange(catalog),
        VlmFusion(catalog),
        VlmIndexNdvi(catalog),
        VlmIndexNdwi(catalog),
        VerifyCrosscheck(),
        AnswerTemplate(),
    ):
        registry.register(tool)
    return registry


__all__ = ["build_default_registry", "Artifact"]
