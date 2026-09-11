"""Backup / restore of the operator's own configuration - settings + user
presets, for moving to a new machine or sharing a preset library.

Deliberately **not** sessions or images: a session is transient by design
(``session_expiry_hours``), the actual deliverable is the downloaded image,
and the whole data volume is already the backup unit for everything else
(``docs/ARCHITECTURE.md`` "Storage layout"). This is for the one thing that
isn't - your tuned settings and your own presets - without dragging along the
old instance's secrets, images, or transient job/session rows. Built-in
presets are never included: every instance seeds them itself.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.models.processing import ProcessingParameters
from app.utils.app_settings import AppSettings

CONFIG_EXPORT_FORMAT_VERSION = 1


class ConfigExportPreset(BaseModel):
    """One user preset, export/import shape (no ``preset_id`` - a fresh one is
    minted on import)."""

    name: str
    description: str | None = None
    category: str = "astronomy"
    parameters: ProcessingParameters


class ConfigExportResponse(BaseModel):
    """Body of ``GET /api/admin/config-export``."""

    format_version: int = CONFIG_EXPORT_FORMAT_VERSION
    app_version: str
    exported_at: datetime
    settings: AppSettings
    presets: list[ConfigExportPreset]


class ConfigImportRequest(BaseModel):
    """Body of ``POST /api/admin/config-import`` - the export's own shape."""

    format_version: int
    settings: AppSettings
    presets: list[ConfigExportPreset] = []


class ConfigImportResponse(BaseModel):
    """Body of ``POST /api/admin/config-import``."""

    presets_imported: int
    #: names skipped because a preset with that name already exists - never
    #: overwritten, never renamed.
    presets_skipped: list[str]
