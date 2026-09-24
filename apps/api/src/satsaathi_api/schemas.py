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

from pydantic import BaseModel, EmailStr, Field

Mode = Literal["single", "fusion", "change"]
Role = Literal["single", "optical", "sar", "before", "after"]


class ErrorBody(BaseModel):
    key: str
    params: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorBody


class RegisterIn(BaseModel):
    email: EmailStr
    #: Length is the only rule worth enforcing. Composition rules push people
    #: towards "Password1!" and NIST stopped recommending them years ago.
    password: str = Field(min_length=12, max_length=256)
    full_name: str = Field(min_length=1, max_length=200)
    department: str | None = Field(default=None, max_length=200)
    district: str | None = Field(default=None, max_length=200)
    preferred_locale: Literal["en", "hi", "ta", "bn"] = "en"


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class GoogleTokenIn(BaseModel):
    """A Google ID token, to be verified here rather than trusted."""

    id_token: str = Field(min_length=1, max_length=8192)
    preferred_locale: Literal["en", "hi", "ta", "bn"] = "en"


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    department: str | None = None
    district: str | None = None
    preferred_locale: str
    created_at: datetime


class SessionOut(BaseModel):
    """The token is returned once and never again; only its holder has it."""

    token: str
    expires_at: datetime
    user: UserOut
    #: True when this sign-in created the account, so the interface can
    #: welcome a new person rather than greeting them back.
    created: bool = False


class ModelOut(BaseModel):
    """One model, and whether this machine actually has it."""

    name: str
    task: str
    revision: str
    runtime: str
    queue: str
    #: Usable right now: own files, base or dependencies, and a matching base.
    available: bool
    path: str
    #: Digest of the weights on disk; None when they are absent.
    fingerprint: str | None = None
    vram_mb: int | None = None
    #: Operator-facing detail, not interface chrome, so it is prose.
    note: str = ""
    #: hf_base | lora_adapter | composite | classical | stub
    kind: str = "hf_base"
    #: This model's own files are present, whatever the state of its base.
    installed: bool = False
    missing_files: list[str] = Field(default_factory=list)
    #: The base an adapter attaches to, or the models a composite runs.
    base: str | None = None
    uses: list[str] = Field(default_factory=list)
    #: Whether an adapter was trained on the declared base; None if n/a.
    compatible: bool | None = None
    #: Why it is unavailable, as a message key plus params. None if available.
    reason: ErrorBody | None = None
    #: Held-out metrics from the adapter's eval.json ("base", "finetuned").
    eval: dict[str, Any] | None = None
    #: Resident on the GPU worker right now (from its heartbeat). None when
    #: no GPU worker is alive to say.
    loaded: bool | None = None
    #: Its tools would return fixture output here. A declared stub always is.
    is_stub: bool = True


class ModelsOut(BaseModel):
    models: list[ModelOut]
    models_dir: str
    available_count: int
    #: How many tools would return fixture output rather than a measurement.
    stub_tool_count: int
    tool_count: int
    #: Whether a GPU worker heartbeat was seen within its TTL.
    gpu_worker: bool = False


class RuntimeOut(BaseModel):
    """The GPU worker's last heartbeat, or `no_gpu_worker`."""

    status: Literal["up", "no_gpu_worker"]
    worker_id: str | None = None
    base_loaded: bool | None = None
    adapters_loaded: list[str] = Field(default_factory=list)
    vram_allocated_mb: float | None = None
    vram_reserved_mb: float | None = None
    vram_peak_mb: float | None = None
    gpu_name: str | None = None
    torch: str | None = None
    transformers: str | None = None
    peft: str | None = None
    bitsandbytes: str | None = None
    load_seconds: float | None = None
    last_inference_ms: int | None = None
    inferences_total: int | None = None
    last_error_key: str | None = None
    idle_seconds: float | None = None


class SelftestStarted(BaseModel):
    task_id: str
    model: str


class SelftestCheck(BaseModel):
    sample: str | None = None
    check: str
    passed: bool
    detail: str = ""


class SelftestOut(BaseModel):
    task_id: str
    state: Literal["pending", "done", "failed"]
    model: str | None = None
    passed: bool | None = None
    checks: list[SelftestCheck] = Field(default_factory=list)
    latency_ms: int | None = None
    vram_peak_mb: float | None = None
    output_excerpt: str = ""


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


class ToolModelOut(BaseModel):
    """The model a tool would use, if this machine has it."""

    name: str
    available: bool
    revision: str | None = None
    fingerprint: str | None = None


class ToolOut(BaseModel):
    name: str
    version: str
    task: str
    required_modalities: list[str]
    params_schema: dict[str, Any]
    is_stub: bool
    #: Which worker queue can run this, given what is installed here.
    queue: str = "cpu"
    #: Absent for tools that never involved a model, such as index maths.
    model: ToolModelOut | None = None


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
