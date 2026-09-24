"""Put pretend weights on disk, for tests in any package.

Real weights are gigabytes; availability is a stat() and a JSON read, so a
few bytes in the right file names exercise every branch the catalog has.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .catalog import CATALOG
from .spec import ModelSpec


def _spec(name_or_spec: str | ModelSpec, specs: tuple[ModelSpec, ...]) -> ModelSpec:
    if isinstance(name_or_spec, ModelSpec):
        return name_or_spec
    return next(s for s in specs if s.name == name_or_spec)


def install_fake(
    root: Path,
    name_or_spec: str | ModelSpec,
    *,
    specs: tuple[ModelSpec, ...] = CATALOG,
    base_repo: str | None = None,
    eval_doc: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
    with_base: bool = True,
    weights: bytes = b"pretend weights",
) -> ModelSpec:
    """Create every required file for a spec, and its base or dependencies.

    `base_repo` overrides what an adapter claims it was trained on, which is
    how the mismatch path is tested.
    """
    spec = _spec(name_or_spec, specs)
    directory = spec.directory(root)
    directory.mkdir(parents=True, exist_ok=True)

    by_name = {s.name: s for s in specs}
    if spec.kind == "lora_adapter":
        base = by_name.get(spec.base or "")
        claimed = base_repo or (base.hf_repo if base else "unknown/base")
        for name in spec.required_files:
            path = directory / name
            if name == "adapter_config.json":
                path.write_text(json.dumps({"base_model_name_or_path": claimed}))
            elif name == spec.meta_file:
                path.write_text(
                    json.dumps(
                        meta
                        or {
                            "base_model": claimed,
                            "system_prompt": f"system prompt for {spec.name}",
                            "change_prompt": "BEFORE then AFTER. {q}",
                            "max_side_px": 512,
                            "box_format": "bbox_2d x1,y1,x2,y2 relative 0-1000",
                        }
                    )
                )
            else:
                path.write_bytes(weights)
        if with_base and base is not None:
            install_fake(root, base, specs=specs)
    elif spec.kind == "composite":
        if with_base:
            for dependency in spec.uses:
                install_fake(root, dependency, specs=specs)
    else:
        for name in spec.required_files:
            (directory / name).write_bytes(weights)

    if eval_doc is not None:
        (directory / "eval.json").write_text(json.dumps(eval_doc))
    return spec
