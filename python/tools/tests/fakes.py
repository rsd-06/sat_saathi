"""A stand-in for the GPU runtime handle, with the same three methods.

`generate`, `meta` and `prior` are all a tool may call; scripting them lets
every branch of every tool run in CI without torch.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from satsaathi_core import vlm_prompts


@dataclass
class FakeGeneration:
    text: str
    token_logprobs: list[float] = field(default_factory=lambda: [math.log(0.9)] * 4)
    latency_ms: int = 12
    input_tokens: int = 300
    output_tokens: int = 4
    adapter: str | None = None

    @property
    def mean_token_prob(self) -> float | None:
        if not self.token_logprobs:
            return None
        return math.exp(sum(self.token_logprobs) / len(self.token_logprobs))


class FakeModel:
    """Answers from a script: a string, a list consumed in order, or a dict by adapter."""

    def __init__(self, catalog, script: Any = "ok", *, raises: Exception | None = None):
        self.catalog = catalog
        self.script = script
        self.raises = raises
        self.calls: list[dict[str, Any]] = []

    def generate(self, adapter, images, prompt, **kwargs):
        self.calls.append(
            {"adapter": adapter, "images": len(images), "prompt": prompt, **kwargs}
        )
        if self.raises is not None:
            raise self.raises
        if isinstance(self.script, dict):
            text = self.script[adapter]
        elif isinstance(self.script, list):
            text = self.script.pop(0)
        else:
            text = self.script
        return FakeGeneration(text=text, adapter=adapter)

    def meta(self, adapter=None):
        spec = self.catalog.get(adapter)
        return vlm_prompts.load_meta(spec.directory(self.catalog.root) / spec.meta_file)

    def prior(self, adapter, task):
        return self.catalog.prior(adapter, task)
