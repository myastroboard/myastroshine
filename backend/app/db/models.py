"""SQLAlchemy ORM models.

Tables (see docs/ARCHITECTURE): sessions, jobs, presets, astrodex_links,
webhook_tokens, stacks.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.types import JsonDict


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class SessionRecord(Base):
    """A single upload/edit session with its working files."""

    __tablename__ = "sessions"

    session_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    image_path: Mapped[str] = mapped_column(String(512))
    original_filename: Mapped[str | None] = mapped_column(String(255))
    parameters: Mapped[JsonDict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    astrodex_link: Mapped[AstroDexLink | None] = relationship(
        back_populates="session", cascade="all, delete-orphan", uselist=False
    )


class JobRecord(Base):
    """An async processing job (direct or Celery-backed)."""

    __tablename__ = "jobs"

    job_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str | None] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(16), default="queued")
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    current_step: Mapped[str | None] = mapped_column(String(32))
    error: Mapped[str | None] = mapped_column(Text)
    client_ip: Mapped[str | None] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class PresetRecord(Base):
    """A named set of processing parameters."""

    __tablename__ = "presets"

    preset_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    category: Mapped[str] = mapped_column(String(64), default="astronomy")
    description: Mapped[str | None] = mapped_column(Text)
    parameters: Mapped[JsonDict] = mapped_column(JSON)
    author: Mapped[str] = mapped_column(String(64), default="user")
    is_favorite: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AstroDexLink(Base):
    """Links a local session to an AstroDex gallery image."""

    __tablename__ = "astrodex_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.session_id"), unique=True)
    astrodex_image_id: Mapped[str] = mapped_column(String(64))
    callback_url: Mapped[str] = mapped_column(String(512))
    callback_token: Mapped[str | None] = mapped_column(String(512))
    webhook_status: Mapped[str] = mapped_column(String(16), default="pending")
    webhook_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    session: Mapped[SessionRecord] = relationship(back_populates="astrodex_link")


class StackRecord(Base):
    """A multi-frame stacking session (linear rebuild).

    See ``initial_plan/12_STACKING_REBUILD.md``.
    """

    __tablename__ = "stacks"

    stack_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    frame_count: Mapped[int] = mapped_column(Integer)
    received_frames: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(24), default="waiting_for_frames")
    combination_method: Mapped[str] = mapped_column(String(16), default="average")
    result: Mapped[JsonDict | None] = mapped_column(JSON)
    session_id: Mapped[str | None] = mapped_column(String(36))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    registration_transform: Mapped[str] = mapped_column(String(16), default="similarity")
    rejection_algo: Mapped[str] = mapped_column(String(24), default="winsorized_sigma")
    rejection_params: Mapped[JsonDict | None] = mapped_column(JSON)
    weighting: Mapped[str] = mapped_column(String(12), default="noise")
    #: replace hot/dead pixels (from the master dark/flat) with a neighbour median.
    cosmetic_correction: Mapped[bool] = mapped_column(default=True)
    #: auto-reject strength for per-frame quality (off/lenient/moderate/strict).
    quality_filter: Mapped[str] = mapped_column(String(12), default="moderate")
    #: post-stack cleanup on the composite (crop the rotation wedge, remove the
    #: background gradient, neutralise + balance the colour) before the editor.
    post_process: Mapped[bool] = mapped_column(default=True)
    #: frame indices the user has manually excluded (a trail, a cloud, ...).
    excluded_frames: Mapped[list[int]] = mapped_column(JSON, default=list)
    #: frame indices the user has manually rescued from the quality auto-reject.
    included_frames: Mapped[list[int]] = mapped_column(JSON, default=list)
    #: reference frame, per-frame quality metrics, registration residuals.
    quality_report: Mapped[JsonDict | None] = mapped_column(JSON)
    #: "upload" (the UI) or "watch" (the folder-watch ingest task).
    source: Mapped[str] = mapped_column(String(12), default="upload")
    #: drizzle output scale: 1 = off, 2 or 3 = variable-pixel super-resolution.
    drizzle_factor: Mapped[int] = mapped_column(Integer, default=1)
    #: last time a frame was added - drives the watch-folder idle timeout.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class WebhookToken(Base):
    """A long-lived bearer token that authenticates AstroDex to this instance.

    Created and revoked from the UI. The raw value is shown once; only its hash
    is stored. ``signing_secret`` is used to HMAC-sign outbound webhooks.
    """

    __tablename__ = "webhook_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    token_prefix: Mapped[str] = mapped_column(String(16), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    signing_secret: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(default=False)
