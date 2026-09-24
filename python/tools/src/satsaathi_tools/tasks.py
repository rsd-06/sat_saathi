"""Which task a query asks for, decided before any model runs.

The problem statement scores "correct task and specialist-model/tool
selection" from the execution trace, so the task is an explicit, recorded
decision: the planner writes it into the vision-language step's permitted
parameters, and the tool runs that task rather than guessing again.

    vqa        answer a question about one image (mandatory baseline)
    caption    describe the scene
    grounding  locate what the query refers to (boxes)
    change     a bi-temporal pair: what changed, and where
    fusion     a co-registered optical + SAR pair, read together

Input mode decides pair tasks; wording decides single-image ones. Matching
is token-anchored and covers the four interface languages, like intent.
"""

from __future__ import annotations

import re
from typing import Literal

Task = Literal["vqa", "caption", "grounding", "change", "fusion"]
TASKS: tuple[str, ...] = ("vqa", "caption", "grounding", "change", "fusion")

_GROUNDING = re.compile(
    r"\b(where|locate|location|highlight|mark|find|point\s+out|outline|bounding|"
    r"box(?:es)?|detect|show\s+me|show\s+where)\b"
    r"|कहाँ|कहां|चिह्नित|दिखाइए|दिखाओ|எங்கே|எங்கு|குறி|காட்டு|কোথায়|চিহ্নিত|দেখাও",
    re.IGNORECASE,
)
_CAPTION = re.compile(
    r"\b(describe|description|caption|summari[sz]e|overview|what\s+does\s+(?:this|the)\s+"
    r"(?:image|scene|picture)\s+show|what\s+is\s+(?:in|shown\s+in)\s+(?:this|the)\s+"
    r"(?:image|scene))\b"
    r"|वर्णन|विवरण|விவரி|விவரிக்க|বর্ণনা",
    re.IGNORECASE,
)


def wants_boxes(question: str) -> bool:
    return bool(_GROUNDING.search(question or ""))


def classify_task(question: str, mode: str) -> Task:
    if mode == "change":
        return "change"
    if mode == "fusion":
        return "fusion"
    if wants_boxes(question):
        return "grounding"
    if _CAPTION.search(question or ""):
        return "caption"
    return "vqa"
