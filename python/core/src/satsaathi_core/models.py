"""Persistent shape of a job and everything it touches.

PostGIS holds footprints, AOIs and vector results. Rasters never go in the
database — they live in storage and are referenced by key.

The step_key enum is fixed and shared with the frontend, the i18n catalogs and
the exported trace. Renaming a member is a breaking change to all four.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> uuid.UUID:
    return uuid.uuid4()


#: JSONB on Postgres, plain JSON elsewhere so tests can run on SQLite.
JsonType = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class StepKey(enum.StrEnum):
    ask = "ask"
    imagery = "imagery"
    understand = "understand"
    preprocess = "preprocess"
    compute = "compute"
    vision_language = "vision_language"
    verify = "verify"
    answer = "answer"


class StepStatus(enum.StrEnum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    skipped = "skipped"
    failed = "failed"
    needs_review = "needs_review"


class JobStatus(enum.StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    needs_review = "needs_review"


class InputMode(enum.StrEnum):
    single = "single"
    fusion = "fusion"
    change = "change"


class AssetRole(enum.StrEnum):
    single = "single"
    optical = "optical"
    sar = "sar"
    before = "before"
    after = "after"


class ArtifactKind(enum.StrEnum):
    cog = "cog"
    geojson = "geojson"
    pdf = "pdf"
    png = "png"
    trace = "trace"


class ReviewStatus(enum.StrEnum):
    pending = "pending"
    approved = "approved"
    edited = "edited"
    rejected = "rejected"


class User(Base):
    """A person who signs in.

    Email is stored lowercased and unique. Department and district are the
    context an officer works in and appear on reports, so they are part of
    the account rather than a profile bolted on later.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_id
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    #: Argon2id, or None for an account that only ever signs in through a
    #: provider. Absent is not the same as empty: `authenticate` must refuse
    #: a password sign-in outright rather than compare against nothing.
    password_hash: Mapped[str | None] = mapped_column(String(512), nullable=True)
    full_name: Mapped[str] = mapped_column(String(200))
    department: Mapped[str | None] = mapped_column(String(200), nullable=True)
    district: Mapped[str | None] = mapped_column(String(200), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    #: The officer's post, e.g. "District Collector", shown with their name.
    designation: Mapped[str | None] = mapped_column(String(200), nullable=True)
    #: The locale to open the app in, so a Tamil speaker is not shown English
    #: once before their preference loads.
    preferred_locale: Mapped[str] = mapped_column(String(8), default="en")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    sessions: Mapped[list[UserSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    identities: Mapped[list[AuthIdentity]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class AuthIdentity(Base):
    """An account at an outside provider, linked to a local user.

    Separate from `users` so one person can hold several — Google today, a
    department single sign-on later — without the user row growing a column
    per provider.

    The provider's subject is the identity, not the email. An email address
    can be reassigned or changed at the provider; the subject never is, so
    matching on it is what keeps a returning user the same user.
    """

    __tablename__ = "auth_identities"
    __table_args__ = (UniqueConstraint("provider", "subject", name="uq_identity"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_id
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(32))
    #: The provider's stable identifier for this person ("sub" in OIDC).
    subject: Mapped[str] = mapped_column(String(255))
    #: What the provider said the address was at link time, kept for support
    #: questions. Never used to find a user — the subject does that.
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped[User] = relationship(back_populates="identities")


class UserSession(Base):
    """One sign-in, revocable on its own.

    Only a hash of the token is stored, so a copy of this table does not let
    anyone sign in as anybody. Rows are kept after revocation rather than
    deleted: "when did this account last sign out" is a question worth being
    able to answer.
    """

    __tablename__ = "user_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_id
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped[User] = relationship(back_populates="sessions")


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_id
    )
    #: The account this belongs to. Nullable only for rows made before
    #: accounts existed; nothing new is created without one.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    storage_key: Mapped[str] = mapped_column(String(512))
    cog_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    filename: Mapped[str] = mapped_column(String(512))
    sensor_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sensor_preset: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bands: Mapped[list | None] = mapped_column(JsonType, nullable=True)
    band_map: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    crs: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pixel_size: Mapped[float | None] = mapped_column(Float, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    acquired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    footprint = mapped_column(
        Geometry("POLYGON", srid=4326, spatial_index=True), nullable=True
    )
    warnings: Mapped[list | None] = mapped_column(JsonType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class InputSet(Base):
    __tablename__ = "input_sets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_id
    )
    #: The account this belongs to. Nullable only for rows made before
    #: accounts existed; nothing new is created without one.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    mode: Mapped[InputMode] = mapped_column(Enum(InputMode, name="input_mode"))
    checks: Mapped[list | None] = mapped_column(JsonType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    assets: Mapped[list[InputSetAsset]] = relationship(
        back_populates="input_set", cascade="all, delete-orphan"
    )


class InputSetAsset(Base):
    __tablename__ = "input_set_assets"
    __table_args__ = (UniqueConstraint("input_set_id", "role"),)

    input_set_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("input_sets.id", ondelete="CASCADE"),
        primary_key=True,
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id"), primary_key=True
    )
    role: Mapped[AssetRole] = mapped_column(Enum(AssetRole, name="asset_role"))

    input_set: Mapped[InputSet] = relationship(back_populates="assets")
    asset: Mapped[Asset] = relationship()


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_id
    )
    #: The account this belongs to. Nullable only for rows made before
    #: accounts existed; nothing new is created without one.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    input_set_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("input_sets.id")
    )
    query_text: Mapped[str] = mapped_column(Text)
    query_lang: Mapped[str] = mapped_column(String(8))
    ui_lang: Mapped[str] = mapped_column(String(8))
    query_text_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    intent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    plan: Mapped[list | None] = mapped_column(JsonType, nullable=True)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status"), default=JobStatus.queued
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    answer: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    error: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    steps: Mapped[list[JobStep]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="JobStep.ordinal",
    )
    input_set: Mapped[InputSet] = relationship()


class JobStep(Base):
    __tablename__ = "job_steps"
    __table_args__ = (UniqueConstraint("job_id", "step_key"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_id
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE")
    )
    step_key: Mapped[StepKey] = mapped_column(Enum(StepKey, name="step_key"))
    ordinal: Mapped[int] = mapped_column(Integer)
    status: Mapped[StepStatus] = mapped_column(
        Enum(StepStatus, name="step_status"), default=StepStatus.pending
    )
    tool_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tool_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_stub: Mapped[bool | None] = mapped_column(nullable=True)
    params: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    output_summary: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    note: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    job: Mapped[Job] = relationship(back_populates="steps")


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_id
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE")
    )
    step_key: Mapped[StepKey | None] = mapped_column(
        Enum(StepKey, name="step_key"), nullable=True
    )
    kind: Mapped[ArtifactKind] = mapped_column(Enum(ArtifactKind, name="artifact_kind"))
    name: Mapped[str] = mapped_column(String(256))
    storage_key: Mapped[str] = mapped_column(String(512))
    geometry = mapped_column(Geometry(srid=4326), nullable=True)
    meta: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class ReviewItem(Base):
    __tablename__ = "review_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_id
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE")
    )
    reason: Mapped[str] = mapped_column(String(128))
    status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus, name="review_status"), default=ReviewStatus.pending
    )
    reviewer_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    edited_answer: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Analysis(Base):
    """A change-detection or cross-modal run, kept so history is real.

    These run in the browser today, as pixel heuristics, so the server keeps
    what was shown rather than recomputing it: the summary, the numbers and
    which images (by name and date) went in. `method` records how it was made
    so a later model-backed run is never confused with one of these.
    """

    __tablename__ = "analyses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_id
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20))
    variant: Mapped[str | None] = mapped_column(String(20), nullable=True)
    method: Mapped[str] = mapped_column(String(40), default="browser-heuristic")
    title: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(Text)
    stats: Mapped[dict] = mapped_column(JsonType, default=dict)
    frames: Mapped[list] = mapped_column(JsonType, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
