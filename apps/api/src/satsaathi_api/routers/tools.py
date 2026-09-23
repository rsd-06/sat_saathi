"""What the system can do, and which parts of it are real."""

from __future__ import annotations

from fastapi import APIRouter, status

from satsaathi_tools.presets import SENSOR_PRESETS

from ..deps import RegistryDep, api_error
from ..schemas import ToolOut

router = APIRouter(tags=["tools"])


@router.get("/tools", response_model=list[ToolOut])
async def list_tools(registry: RegistryDep) -> list[ToolOut]:
    """Every tool, its permitted parameters, and whether it is a stub.

    Exposed deliberately: the stub flag is how a reviewer can tell which
    numbers were measured and which are fixture output.
    """
    return [ToolOut(**described) for described in registry.describe()]


@router.get("/sensor-presets")
async def list_presets() -> dict[str, dict[str, int]]:
    """Band layouts by sensor. Labels are localised by the frontend."""
    return SENSOR_PRESETS


@router.post("/voice/transcribe", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def transcribe() -> None:
    raise api_error(status.HTTP_501_NOT_IMPLEMENTED, "voice.not_available")
