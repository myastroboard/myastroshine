"""SQLAlchemy ORM models.

Tables (see docs/ARCHITECTURE): sessions, jobs, presets, astrodex_links.
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

    jobs: Mapped[list[JobRecord]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    astrodex_link: Mapped[AstroDexLink | None] = relationship(
        back_populates="session", cascade="all, delete-orphan", uselist=False
    )


class JobRecord(Base):
    """An async processing job (direct or Celery-backed)."""

    __tablename__ = "jobs"

    job_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.session_id"))
    status: Mapped[str] = mapped_column(String(16), default="queued")
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    current_step: Mapped[str | None] = mapped_column(String(32))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    session: Mapped[SessionRecord] = relationship(back_populates="jobs")


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
    webhook_status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    session: Mapped[SessionRecord] = relationship(back_populates="astrodex_link")
