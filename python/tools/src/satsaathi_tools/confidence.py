"""How sure a model answer is, built from numbers someone can check.

    confidence = prior(model, task) x signal [x consistency] [x agreement]

  * prior       the adapter's fine-tuned held-out metric for this kind of
                answer, from its eval.json. SAR grounding is 0.20 and stays
                0.20: a fluent box from a weak grounder is still a weak box.
  * signal      geometric-mean probability of the generated tokens — how
                peaked the model's own distribution was.
  * consistency agreement across two temperature-0.7 re-samples (optional).
  * agreement   for fusion, how far the SAR and optical readings agree.

Every factor, and the product, is recorded on the step so a reader can see
why an answer was held.
"""

from __future__ import annotations

import re
import string
from dataclasses import dataclass
from typing import Any

from satsaathi_core.boxes import box_f1

#: Used when an installed adapter shipped without eval.json. Recorded as
#: such, never presented as a measured prior.
DEFAULT_PRIOR = 0.5

_WORDS = re.compile(r"\w+", re.UNICODE)
_PUNCT = str.maketrans("", "", string.punctuation)


@dataclass
class Confidence:
    value: float
    band: str
    prior: float
    prior_metric: str | None
    prior_measured: bool
    signal: float | None
    consistency: float | None = None
    agreement: float | None = None

    @property
    def needs_review(self) -> bool:
        return self.band == "low"

    def summary(self) -> dict[str, Any]:
        """Flat and JSON-safe, for the trace step's output_summary."""
        out: dict[str, Any] = {
            "confidence": round(self.value, 3),
            "confidence_band": self.band,
            "prior": round(self.prior, 4),
            "prior_metric": self.prior_metric or "default",
            "prior_measured": self.prior_measured,
        }
        for key in ("signal", "consistency", "agreement"):
            value = getattr(self, key)
            if value is not None:
                out[key] = round(value, 3)
        return out


def thresholds(settings: Any) -> tuple[float, float]:
    high = float(getattr(settings, "confidence_high", 0.6))
    low = float(getattr(settings, "confidence_low", 0.35))
    return high, low


def band(value: float, high: float, low: float) -> str:
    if value >= high:
        return "high"
    if value < low:
        return "low"
    return "medium"


def combine(
    *,
    prior: float | None,
    prior_metric: str | None,
    signal: float | None,
    settings: Any,
    consistency: float | None = None,
    agreement: float | None = None,
) -> Confidence:
    measured = prior is not None
    p = prior if prior is not None else DEFAULT_PRIOR
    value = p
    for factor in (signal, consistency, agreement):
        if factor is not None:
            value *= max(0.0, min(1.0, factor))
    high, low = thresholds(settings)
    return Confidence(
        value=value,
        band=band(value, high, low),
        prior=p,
        prior_metric=prior_metric if measured else None,
        prior_measured=measured,
        signal=signal,
        consistency=consistency,
        agreement=agreement,
    )


def normalise(text: str) -> str:
    return " ".join(text.lower().translate(_PUNCT).split())


def _polarity(text: str) -> str | None:
    head = normalise(text).split(" ", 1)[0] if text.strip() else ""
    return head if head in ("yes", "no") else None


def text_agreement(a: str, b: str) -> float:
    """1 for the same answer after normalisation, else token overlap.

    Yes/no answers agree when their polarity does, whatever follows.
    """
    pa, pb = _polarity(a), _polarity(b)
    if pa and pb:
        return 1.0 if pa == pb else 0.0
    na, nb = normalise(a), normalise(b)
    if na == nb:
        return 1.0
    ta, tb = set(_WORDS.findall(na)), set(_WORDS.findall(nb))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def box_agreement(a: list[list[float]], b: list[list[float]]) -> float:
    return box_f1(a, b, 0.5)
