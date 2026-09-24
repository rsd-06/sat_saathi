"""The vision-language steps, and the classical measurements under them.

Which of these runs is decided by the planner from what was uploaded (see
`registry.plan`): SAR goes to the SAR adapter, optical to the optical one,
index questions over real bands to an index adapter, a before/after pair to
change detection, an optical+SAR pair to fusion. Each tool here only runs the
model it was routed to.

Every tool keeps its fixture: on a machine without the weights the step says
it is fixture output, and on a machine where the runtime breaks mid-job it
says so too (`ModelBackedTool.run`).

Nothing here imports torch. `model` is a handle onto the GPU runtime
(`satsaathi_inference.loader.ModelHandle`) with `generate`, `meta` and
`prior`; the tests pass a fake with the same three methods.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from satsaathi_core import boxes as box_maths
from satsaathi_core import imaging, index_contract, vlm_prompts
from satsaathi_core.change import detect_change, sar_bright_targets, sar_water_mask

from . import confidence as conf
from .model_backed import ModelBackedTool
from .protocol import Artifact, NoParams, ToolContext, ToolResult

#: Words that make a question a request for a location. English plus the
#: three Indian languages the interface ships; a match is token-anchored.
_WHERE = re.compile(
    r"\b(where|locate|location|find|mark|show|point|box|bounding|detect|count|how many)\b"
    r"|कहाँ|कहां|कहा|दिखा|எங்கே|எங்கு|কোথায়|দেখা",
    re.IGNORECASE,
)
#: A SAR box counts as corroborated at this overlap with independent evidence.
CORROBORATION_IOU = 0.3
ANSWER_EXCERPT = 280


def wants_boxes(question: str, intent: str | None = None) -> bool:
    return intent == "grounding" or bool(_WHERE.search(question or ""))


def _settings_value(ctx: ToolContext, name: str, default: Any) -> Any:
    return getattr(ctx.settings, name, default) if ctx.settings is not None else default


def _asset(inputs: dict[str, Any], role: str) -> dict[str, Any]:
    """One uploaded asset by role; a single upload answers to any role."""
    assets = inputs.get("assets") or {}
    if role in assets:
        return assets[role]
    if "single" in assets:
        return assets["single"]
    if inputs.get("path"):
        return {
            "path": inputs["path"],
            "band_map": inputs.get("band_map") or {},
            "sensor_type": inputs.get("sensor_type"),
        }
    raise ValueError(f"no {role} image in this job's inputs")


def _flat(boxes: list[dict[str, Any]]) -> str:
    """Boxes as one readable string: the trace shows summaries as k=v text."""
    return "; ".join(
        f"{b.get('label', 'object')}{b['bbox_2d']}:{b.get('status', 'model')}" for b in boxes
    )


def _place_boxes(
    parsed: list[dict[str, Any]], prepared: imaging.PreparedImage, status: str
) -> list[dict[str, Any]]:
    """Relative boxes -> pixels of the upload -> map, when there is a CRS."""
    width, height = prepared.original_size
    out = []
    for b in parsed:
        px = box_maths.relative_to_pixels(b["bbox_2d"], width, height)
        out.append(
            {
                "label": b["label"],
                "bbox_2d": b["bbox_2d"],
                "bbox_px": px,
                "bbox_map": box_maths.pixels_to_map(px, prepared.transform, prepared.crs),
                "status": status,
            }
        )
    return out


def _geojson_artifact(
    ctx: ToolContext, name: str, boxes: list[dict[str, Any]], crs: str | None
) -> list[Artifact]:
    """Boxes on the ground, as WGS84 GeoJSON. Nothing without a CRS."""
    placed = [b for b in boxes if b.get("bbox_map")]
    if not placed or not crs or ctx.storage is None:
        return []
    from rasterio.warp import transform_geom
    from shapely.geometry import box, mapping

    features = []
    for b in placed:
        geom = mapping(box(*b["bbox_map"]))
        if crs.upper() not in ("EPSG:4326", "OGC:CRS84"):
            geom = transform_geom(crs, "EPSG:4326", geom, precision=8)
        features.append(
            {
                "type": "Feature",
                "geometry": geom,
                "properties": {
                    "label": b["label"],
                    "status": b["status"],
                    "kind": name,
                },
            }
        )
    key = f"jobs/{ctx.job_id}/{name}.geojson"
    ctx.storage.put(key, json.dumps({"type": "FeatureCollection", "features": features}).encode())
    return [Artifact(name=f"{name}.geojson", kind="geojson", storage_key=key,
                     meta={"features": len(features), "crs": crs})]


@dataclass
class _Answer:
    text: str
    gen: Any
    boxes: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Shared behaviour
# ---------------------------------------------------------------------------


class _VisionLanguage(ModelBackedTool):
    """A vision-language step: a real model when its weights are here.

    The fixture is not a placeholder to be deleted later. It is what this step
    does on a machine without the weights, and the trace says so every time,
    so an installation with no models is honest rather than broken.
    """

    required_modalities = ["raster"]
    params_schema = NoParams
    base_version = "0.2.0"
    caption = "fixture caption"
    boxes: list[dict] = []
    #: Which adapter answers, and which eval metric backs an ordinary answer.
    adapter = "vqa-optical"
    sensor = "optical"
    default_task = "vqa"

    def fixture(self, inputs, params, ctx: ToolContext) -> ToolResult:
        return ToolResult(
            output_summary={"caption": self.caption, "boxes": len(self.boxes)},
            evidence={"boxes": self.boxes},
        )

    # -- pieces --------------------------------------------------------

    def _ask(
        self, model: Any, adapter: str | None, images: list[Any], prompt: str,
        ctx: ToolContext, *, system: str | None = None,
    ) -> _Answer:
        gen = model.generate(
            adapter, images, prompt, system=system,
            max_new_tokens=int(_settings_value(ctx, "vlm_max_new_tokens", 256)),
            want_logprobs=True,
        )
        return _Answer(gen.text, gen, box_maths.parse_boxes(gen.text))

    def _consistency(
        self, model: Any, adapter: str | None, images: list[Any], prompt: str,
        first: _Answer, grounding: bool, ctx: ToolContext,
    ) -> float | None:
        if not _settings_value(ctx, "vlm_resample", False):
            return None
        scores = []
        for _ in range(2):
            gen = model.generate(
                adapter, images, prompt, sample=True, temperature=0.7,
                max_new_tokens=int(_settings_value(ctx, "vlm_max_new_tokens", 256)),
                want_logprobs=False,
            )
            if grounding:
                other = [b["bbox_2d"] for b in box_maths.parse_boxes(gen.text)]
                scores.append(conf.box_agreement([b["bbox_2d"] for b in first.boxes], other))
            else:
                scores.append(conf.text_agreement(first.text, gen.text))
        return sum(scores) / len(scores)

    def _result(
        self,
        *,
        answer: _Answer,
        adapter: str | None,
        task: str,
        confidence: conf.Confidence,
        placed: list[dict[str, Any]],
        extra: dict[str, Any] | None = None,
        evidence: dict[str, Any] | None = None,
        artifacts: list[Artifact] | None = None,
        note: str | None = None,
        force_review: bool = False,
    ) -> ToolResult:
        grounding = task == "grounding"
        unparseable = grounding and box_maths.looks_like_boxes(answer.text) and not answer.boxes
        if grounding and not answer.boxes and not unparseable:
            # Asked where, answered in prose: not a failure of the runtime,
            # but not a box either.
            note = note or "vlm.no_boxes"
        if unparseable:
            note = "model.output_unparseable"
        needs_review = confidence.needs_review or unparseable or force_review
        summary: dict[str, Any] = {
            "adapter": adapter or "base",
            "task": task,
            "answer": answer.text.strip()[:ANSWER_EXCERPT],
            "boxes": len(placed),
            **confidence.summary(),
            "latency_ms": answer.gen.latency_ms,
            "input_tokens": answer.gen.input_tokens,
            "output_tokens": answer.gen.output_tokens,
            "needs_review": needs_review,
        }
        if placed:
            summary["boxes_2d"] = _flat(placed)
            statuses = sorted({b["status"] for b in placed})
            summary["box_status"] = ",".join(statuses)
        summary.update(extra or {})
        return ToolResult(
            output_summary=summary,
            evidence={"text": answer.text, "boxes": placed, **(evidence or {})},
            artifacts=artifacts or [],
            confidence=confidence.value,
            note=note,
            needs_review=needs_review,
        )

    # -- the common single-image path ------------------------------------

    def _single_image(self, model: Any, inputs: dict, ctx: ToolContext) -> ToolResult:
        question = str(inputs.get("question", ""))
        grounding = wants_boxes(question, inputs.get("intent"))
        task = "grounding" if grounding else self.default_task
        asset = _asset(inputs, self.sensor)
        loader = imaging.load_sar if self.sensor == "sar" else imaging.load_optical
        prepared = loader(asset["path"], asset.get("band_map"))

        answer = self._ask(model, self.adapter, [prepared.image], question, ctx)
        consistency = self._consistency(
            model, self.adapter, [prepared.image], question, answer, grounding, ctx
        )
        spec = model.catalog.get(self.adapter)
        prior_metric = spec.eval_metrics.get(task) if spec else None
        confidence = conf.combine(
            prior=model.prior(self.adapter, task),
            prior_metric=prior_metric,
            signal=answer.gen.mean_token_prob,
            consistency=consistency,
            settings=ctx.settings,
        )
        placed, extra = self._statuses(answer, prepared, asset, grounding)
        return self._result(
            answer=answer,
            adapter=self.adapter,
            task=task,
            confidence=confidence,
            placed=placed,
            extra=extra,
            artifacts=_geojson_artifact(ctx, f"{self.adapter}-boxes", placed, prepared.crs),
            note=(prepared.notes or [None])[0],
        )

    def _statuses(self, answer, prepared, asset, grounding):
        return _place_boxes(answer.boxes, prepared, "model"), {}

    def predict(self, model, inputs, params, ctx: ToolContext) -> ToolResult:
        return self._single_image(model, inputs, ctx)


# ---------------------------------------------------------------------------
# Optical and SAR
# ---------------------------------------------------------------------------


class VlmVqa(_VisionLanguage):
    name = "vlm.vqa"
    task = "vqa"
    model_name = "vqa-optical"
    caption = "A river channel crosses cultivated parcels."
    boxes = [{"label": "water", "bbox": [12, 40, 210, 96], "score": 0.81}]


class VlmCaption(_VisionLanguage):
    name = "vlm.caption"
    task = "caption"
    model_name = "vqa-optical"
    default_task = "caption"
    caption = "Agricultural land bisected by a watercourse."


class VlmGrounding(_VisionLanguage):
    name = "vlm.grounding"
    task = "grounding"
    model_name = "vqa-optical"
    default_task = "grounding"
    caption = "Two water bodies located."
    boxes = [
        {"label": "water", "bbox": [12, 40, 210, 96], "score": 0.81},
        {"label": "water", "bbox": [150, 120, 190, 150], "score": 0.64},
    ]


class VlmSar(_VisionLanguage):
    """The SAR adapter. Its boxes are never confirmed on its own word.

    Held-out SAR grounding is 0.20 at IoU 0.5. A box is shown as `unverified`
    unless an independent classical detection overlaps it (IoU >= 0.3).
    """

    name = "vlm.sar"
    task = "vqa"
    model_name = "vqa-sar"
    adapter = "vqa-sar"
    sensor = "sar"
    required_modalities = ["sar"]
    caption = "Backscatter is low over the inundated parcels."

    def _statuses(self, answer, prepared, asset, grounding):
        if not answer.boxes:
            return [], {}
        width, height = prepared.original_size
        grey = imaging.read_single_band(asset["path"], (asset.get("band_map") or {}).get("vv") or 1)
        targets = sar_bright_targets(grey, scale_to=(width, height))
        classical = [t["bbox_2d"] for t in targets.boxes]
        placed = []
        for b in _place_boxes(answer.boxes, prepared, "unverified"):
            overlap = box_maths.best_overlap(b["bbox_2d"], classical)
            b["status"] = "corroborated" if overlap >= CORROBORATION_IOU else "unverified"
            b["corroboration_iou"] = round(overlap, 3)
            placed.append(b)
        return placed, {"classical_targets": len(classical)}


# ---------------------------------------------------------------------------
# Index adapters
# ---------------------------------------------------------------------------


_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def unquoted_numbers(
    text: str, stats: dict[str, Any], extra: list[str] | None = None
) -> list[str]:
    """Numbers in an answer that do not come from the computed statistics.

    Box coordinates are exempt; everything else must be a quote.
    """
    allowed = set(_NUMBER.findall(index_contract.stats_text(stats)))
    allowed |= set(_NUMBER.findall(json.dumps(stats)))
    allowed |= set(extra or [])
    coords = {str(v) for b in box_maths.parse_boxes(text) for v in b["bbox_2d"]}
    return [n for n in _NUMBER.findall(text) if n not in allowed and n not in coords]


class _VlmIndex(_VisionLanguage):
    """An index adapter reading a rendered index map next to its statistics.

    The numbers are computed here, from the mapped bands, with the training
    contract's own functions; the adapter only reads them. An answer quoting
    a number the statistics do not contain is held for review.
    """

    index = "NDVI"
    required_modalities = ["raster"]
    default_task = "vqa"

    def predict(self, model, inputs, params, ctx: ToolContext) -> ToolResult:
        question = str(inputs.get("question", ""))
        grounding = wants_boxes(question, inputs.get("intent"))
        task = "grounding" if grounding else "vqa"
        asset = _asset(inputs, "optical")
        band_map = asset.get("band_map") or {}
        roles = imaging.read_band_arrays(
            asset["path"], band_map, index_contract.INDEX_ROLES[self.index],
            int(_settings_value(ctx, "max_index_pixels", 4096 * 4096)),
        )
        tc, idx_img, stats, prompt = index_contract.prepare(self.index, roles, question)
        answer = self._ask(model, self.model_name, [tc, idx_img], prompt, ctx)

        extra_numbers = []
        if self.index == "NDWI":
            extra_numbers = _NUMBER.findall(prompt.rsplit("(", 1)[-1])
        stray = unquoted_numbers(answer.text, stats, extra_numbers)

        spec = model.catalog.get(self.model_name)
        confidence = conf.combine(
            prior=model.prior(self.model_name, task),
            prior_metric=spec.eval_metrics.get(task) if spec else None,
            signal=answer.gen.mean_token_prob,
            settings=ctx.settings,
        )
        prepared = imaging.PreparedImage(tc, _original_size(asset["path"]))
        prepared.crs, prepared.transform = _georef(asset["path"])
        placed = _place_boxes(answer.boxes, prepared, "model")
        return self._result(
            answer=answer,
            adapter=self.model_name,
            task=task,
            confidence=confidence,
            placed=placed,
            extra={
                "index": self.index.lower(),
                "index_mean": stats["mean"],
                "numbers_quoted_ok": not stray,
                **({"numbers_unquoted": ",".join(stray)} if stray else {}),
            },
            evidence={"stats": stats, "prompt": prompt},
            artifacts=_geojson_artifact(ctx, f"{self.model_name}-boxes", placed, prepared.crs),
            note="index.unquoted_numbers" if stray else None,
            force_review=bool(stray),
        )


def _original_size(path: str) -> tuple[int, int]:
    import rasterio

    with rasterio.open(path) as src:
        return src.width, src.height


def _georef(path: str):
    import rasterio

    with rasterio.open(path) as src:
        if src.crs is None:
            return None, None
        t = src.transform
        return src.crs.to_string(), (t.a, t.b, t.c, t.d, t.e, t.f)


class VlmIndexNdvi(_VlmIndex):
    name = "vlm.index.ndvi"
    task = "index_compute"
    model_name = "index-ndvi"
    index = "NDVI"
    caption = "Vegetation is densest in the north-west parcels."


class VlmIndexNdwi(_VlmIndex):
    name = "vlm.index.ndwi"
    task = "index_compute"
    model_name = "index-ndwi"
    index = "NDWI"
    caption = "Open water lies along the western edge."


# ---------------------------------------------------------------------------
# Change: classical boxes, explained by the optical adapter
# ---------------------------------------------------------------------------


def _pair_sensor(inputs: dict[str, Any]) -> str:
    assets = inputs.get("assets") or {}
    kinds = {(assets.get(r) or {}).get("sensor_type") for r in ("before", "after")}
    return "sar" if kinds == {"sar"} else "optical"


class VlmChange(_VisionLanguage):
    """Boxes come from the classical change map, never from the model.

    The optical adapter's change yes/no is strong (0.92 held-out), its boxes
    were never trained on change masks. So the measured regions are shown,
    and the adapter is asked to explain them. A SAR pair gets the classical
    map only: neither adapter was trained on SAR pairs.
    """

    name = "vlm.change"
    task = "change_vqa"
    model_name = "change-detection"
    caption = "Inundation has expanded along the eastern bank."

    def predict(self, model, inputs, params, ctx: ToolContext) -> ToolResult:
        question = str(inputs.get("question", "")) or "What changed between the two images?"
        before, after = _asset(inputs, "before"), _asset(inputs, "after")
        sensor = _pair_sensor(inputs)
        size = _size_any(before["path"])

        if sensor == "sar":
            a = imaging.read_single_band(before["path"])
            b = imaging.read_single_band(after["path"])
        else:
            a = imaging.read_rgb_array(before["path"], before.get("band_map"))
            b = imaging.read_rgb_array(after["path"], after.get("band_map"))
        measured = detect_change(a, b, sensor=sensor, scale_to=size)
        regions = [
            {**r, "status": "measured",
             "bbox_map": None}
            for r in measured.boxes
        ]
        crs, transform = _georef_any(before["path"])
        for r in regions:
            r["bbox_map"] = box_maths.pixels_to_map(r["bbox_px"], transform, crs)
        classical_summary = {
            "method": measured.method,
            "changed_pct": measured.fraction_pct,
            "regions": len(regions),
            "separability": measured.separability,
        }
        if regions:
            classical_summary["boxes_2d"] = _flat(regions)
        artifacts = _geojson_artifact(ctx, "change-regions", regions, crs)

        if sensor == "sar":
            return ToolResult(
                output_summary={
                    "source": "classical",
                    "adapter": "none",
                    "answer": (
                        f"{measured.fraction_pct}% of the scene changed "
                        f"({len(regions)} regions, log-ratio)."
                    ),
                    **classical_summary,
                },
                evidence={"boxes": regions, "text": ""},
                artifacts=artifacts,
                note="change.sar_classical_only",
            )

        prep_a = imaging.load_optical(before["path"], before.get("band_map"))
        prep_b = imaging.load_optical(after["path"], after.get("band_map"))
        meta = model.meta("vqa-optical")
        prompt = vlm_prompts.change_explain_text(meta, question, regions)
        answer = self._ask(model, "vqa-optical", [prep_a.image, prep_b.image], prompt, ctx)

        # The adapter's own changed/unchanged call, checked against the map.
        said_same = any(w in answer.text.lower() for w in _NO_CHANGE)
        measured_changed = measured.fraction_pct >= 0.5 and bool(regions)
        agreement = 1.0 if said_same != measured_changed else 0.0
        confidence = conf.combine(
            prior=model.prior("vqa-optical", "change"),
            prior_metric="change_flag_acc",
            signal=answer.gen.mean_token_prob,
            agreement=agreement,
            settings=ctx.settings,
        )
        answer.boxes = []  # the model's boxes, if any, are not shown
        return self._result(
            answer=answer,
            adapter="vqa-optical",
            task="change",
            confidence=confidence,
            placed=regions,
            extra={
                **classical_summary,
                "model_says_changed": not said_same,
            },
            artifacts=artifacts,
            note=None if agreement else "change.model_disagrees_with_map",
        )


_NO_CHANGE = (
    "no change", "no difference", "identical", "same as before",
    "nothing has changed", "unchanged",
)


def _size_any(path: str) -> tuple[int, int]:
    try:
        return _original_size(path)
    except Exception:  # noqa: BLE001 - a PNG is not a raster rasterio always opens
        from PIL import Image

        with Image.open(path) as img:
            return img.size


def _georef_any(path: str):
    try:
        return _georef(path)
    except Exception:  # noqa: BLE001
        return None, None


# ---------------------------------------------------------------------------
# Fusion: both adapters, then the base decides
# ---------------------------------------------------------------------------


class VlmFusion(_VisionLanguage):
    """The same question to the optical and the SAR adapter, then the base.

    Agreement is box F1 at IoU 0.5 when the question asks where, otherwise
    the two answers compared after normalisation. The base model, with every
    adapter disabled, writes the final answer and, when the readings
    disagree, which sensor to trust and why.
    """

    name = "vlm.fusion"
    task = "optical_sar_fusion"
    model_name = "fusion-optical-sar"
    required_modalities = ["optical", "sar"]
    caption = "SAR shows standing water beneath cloud in the optical scene."

    def predict(self, model, inputs, params, ctx: ToolContext) -> ToolResult:
        question = str(inputs.get("question", ""))
        grounding = wants_boxes(question, inputs.get("intent"))
        task = "grounding" if grounding else "vqa"
        opt_asset, sar_asset = _asset(inputs, "optical"), _asset(inputs, "sar")
        opt = imaging.load_optical(opt_asset["path"], opt_asset.get("band_map"))
        sar = imaging.load_sar(sar_asset["path"], sar_asset.get("band_map"))

        opt_ans = self._ask(model, "vqa-optical", [opt.image], question, ctx)
        sar_ans = self._ask(model, "vqa-sar", [sar.image], question, ctx)
        if grounding:
            agreement = conf.box_agreement(
                [b["bbox_2d"] for b in opt_ans.boxes], [b["bbox_2d"] for b in sar_ans.boxes]
            )
        else:
            agreement = conf.text_agreement(opt_ans.text, sar_ans.text)

        judge = self._ask(
            model, None, [opt.image, sar.image],
            vlm_prompts.fusion_judge_text(question, opt_ans.text, sar_ans.text, agreement),
            ctx, system=vlm_prompts.FUSION_JUDGE_SYSTEM,
        )

        priors = [p for p in (model.prior("vqa-optical", task), model.prior("vqa-sar", task))
                  if p is not None]
        confidence = conf.combine(
            prior=sum(priors) / len(priors) if priors else None,
            prior_metric=f"mean({task})" if priors else None,
            signal=judge.gen.mean_token_prob,
            agreement=agreement,
            settings=ctx.settings,
        )

        optical_boxes = [b["bbox_2d"] for b in opt_ans.boxes]
        placed = _place_boxes(opt_ans.boxes, opt, "model")
        for b in _place_boxes(sar_ans.boxes, sar, "unverified"):
            overlap = box_maths.best_overlap(b["bbox_2d"], optical_boxes)
            b["status"] = "corroborated" if overlap >= CORROBORATION_IOU else "unverified"
            b["label"] = f"sar:{b['label']}"
            placed.append(b)

        judge.boxes = []
        return self._result(
            answer=judge,
            adapter="base",
            task=task,
            confidence=confidence,
            placed=placed,
            extra={
                "optical_answer": opt_ans.text.strip()[:160],
                "sar_answer": sar_ans.text.strip()[:160],
                "agreement_kind": "box_f1@0.5" if grounding else "answer_match",
            },
            evidence={"optical_text": opt_ans.text, "sar_text": sar_ans.text},
            artifacts=_geojson_artifact(ctx, "fusion-boxes", placed, opt.crs),
        )


# ---------------------------------------------------------------------------
# Classical SAR water
# ---------------------------------------------------------------------------


class SarWaterMask(ModelBackedTool):
    """Open water in SAR by dB threshold (Otsu) and morphology. No model."""

    name = "sar.water_mask"
    task = "sar_water_mask"
    model_name = "sar-water-mask"
    base_version = "0.1.0"
    required_modalities = ["sar"]
    params_schema = NoParams

    def fixture(self, inputs, params, ctx: ToolContext) -> ToolResult:
        return ToolResult(output_summary={"water_pct": 12.5}, note="sar_water.fixture")

    def predict(self, model, inputs, params: BaseModel, ctx: ToolContext) -> ToolResult:
        asset = _asset(inputs, "sar")
        band = (asset.get("band_map") or {}).get("vv") or 1
        values = imaging.read_single_band(asset["path"], band)
        size = _size_any(asset["path"])
        result = sar_water_mask(values, scale_to=size)
        crs, transform = _georef_any(asset["path"])
        regions = [{**r, "status": "measured"} for r in result.boxes]
        for r in regions:
            r["bbox_map"] = box_maths.pixels_to_map(r["bbox_px"], transform, crs)
        return ToolResult(
            output_summary={
                "source": "classical",
                "method": result.method,
                "threshold_db": result.threshold,
                "separability": result.separability,
                "water_pct": result.fraction_pct,
                "regions": len(regions),
            },
            evidence={"boxes": regions},
            artifacts=_geojson_artifact(ctx, "sar-water", regions, crs),
            note=(result.notes or [None])[0],
        )
