"""What this deployment can actually run.

The settings screen needs a straight answer to "is this thing measuring or
guessing?", and so does anyone reading a trace. This reports every model the
system knows about and whether its weights are on the machine serving the
request — never a capability list that assumes the happy case.
"""

from __future__ import annotations

from fastapi import APIRouter

from ..deps import CatalogDep, RegistryDep
from ..schemas import ModelOut, ModelsOut

router = APIRouter(prefix="/models", tags=["models"])


@router.get("", response_model=ModelsOut)
async def list_models(catalog: CatalogDep, registry: RegistryDep) -> ModelsOut:
    rows = [
        ModelOut(
            name=status.spec.name,
            task=status.spec.task,
            revision=status.spec.revision,
            runtime=status.spec.runtime,
            queue=status.spec.queue,
            available=status.available,
            path=status.path,
            fingerprint=status.fingerprint,
            vram_mb=status.spec.vram_mb,
            note=status.spec.note,
        )
        for status in catalog.all_status()
    ]

    # Counted from the tools rather than the catalog: what matters to a reader
    # is how many steps would measure something, not how many files exist.
    tools = registry.all()
    return ModelsOut(
        models=rows,
        models_dir=str(catalog.root),
        available_count=sum(1 for row in rows if row.available),
        stub_tool_count=sum(1 for tool in tools if tool.is_stub),
        tool_count=len(tools),
    )
