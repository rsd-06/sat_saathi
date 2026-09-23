"""Request and response shapes.

The API never sends user-facing English for interface chrome. Anything the
officer reads is a message key plus params, localised by the frontend. Only
free-text model output — the answer itself — is prose, and that is translated
by the language layer rather than assembled here.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Mode = Literal["single", "fusion", "change"]
Role = Literal["single", "optical", "sar", "before", "after"]


class ErrorBody(BaseModel):
    key: str
    params: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorBody


class BandOut(BaseModel):
    index: int
    description: str | None = None
    dtype: str
    nodata: float | None = None
    role: str | None = None


class AssetOut(BaseModel):
    id: uuid.UUID
    filename: str
    storage_key: str
    sensor_type: str | None
    sensor_preset: str | None
    crs: str | None
    pixel_size: float | None
    width: int | None
    height: int | None
    band_count: int
    bands: list[BandOut]
    band_map: dict[str, int] | None
    acquired_at: datetime | None
    footprint: dict | None
    warnings: list[str]
    available_indices: list[str]
    unavailable_indices: dict[str, list[str]]
    tile_url: str | None = None
    created_at: datetime


class BandMappingIn(BaseModel):
    """Either a named sensor preset or an explicit role -> band number map."""

    preset: str | None = None
    band_map: dict[str, int] | None = None


class CheckOut(BaseModel):
    key: str
    status: Literal["pass", "warn", "fail"]
    params: dict[str, Any] = Field(default_factory=dict)


class InputSetIn(BaseModel):
    mode: Mode
    assets: dict[Role, uuid.UUID]


class InputSetOut(BaseModel):
    id: uuid.UUID
    mode: Mode
    assets: dict[str, uuid.UUID]
    checks: list[CheckOut]
    blocked: bool
    created_at: datetime


class JobIn(BaseModel):
    input_set_id: uuid.UUID
    query_text: str = Field(min_length=1, max_length=2000)
    query_lang: str = Field(default="en", max_length=8)
    ui_lang: str = Field(default="en", max_length=8)


class StepOut(BaseModel):
    step_key: str
    ordinal: int
    status: str
    tool_name: str | None = None
    tool_version: str | None = None
    is_stub: bool | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    output_summary: dict[str, Any] = Field(default_factory=dict)
    note: str | None = None
    error: ErrorBody | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None


class ArtifactOut(BaseModel):
    id: uuid.UUID
    kind: str
    name: str
    step_key: str | None = None
    url: str


class JobOut(BaseModel):
    id: uuid.UUID
    input_set_id: uuid.UUID
    query_text: str
    query_lang: str
    ui_lang: str
    intent: str | None
    status: str
    confidence: float | None
    answer: dict[str, Any] | None
    error: ErrorBody | None
    steps: list[StepOut]
    artifacts: list[ArtifactOut]
    created_at: datetime
    finished_at: datetime | None


class JobSummary(BaseModel):
    id: uuid.UUID
    query_text: str
    query_lang: str
    mode: Mode
    status: str
    confidence: float | None
    created_at: datetime


class JobPage(BaseModel):
    items: list[JobSummary]
    total: int
    limit: int
    offset: int


class ToolOut(BaseModel):
    name: str
    version: str
    task: str
    required_modalities: list[str]
    params_schema: dict[str, Any]
    is_stub: bool


class ReviewOut(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    reason: str
    status: str
    reviewer_note: str | None
    edited_answer: dict[str, Any] | None
    confidence: float | None
    query_text: str
    created_at: datetime
    resolved_at: datetime | None


class ReviewDecisionIn(BaseModel):
    decision: Literal["approve", "edit", "reject"]
    note: str | None = Field(default=None, max_length=2000)
    edited_answer: dict[str, Any] | None = None


class PresignOut(BaseModel):
    """Where to send the bytes, and the key to register afterwards."""

    upload_url: str
    method: Literal["PUT", "POST"]
    storage_key: str
    headers: dict[str, str] = Field(default_factory=dict)
