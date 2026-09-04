"""Admin settings request/response models.

The wire shape is :class:`app.utils.app_settings.AppSettings` itself: the UI reads
the whole object with ``GET`` and writes the whole object back with ``POST``.
"""

from __future__ import annotations

from app.utils.app_settings import AppSettings


class AppSettingsResponse(AppSettings):
    """Body of ``GET /api/admin/app-settings`` - the live runtime settings."""


class AppSettingsUpdate(AppSettings):
    """Body of ``POST /api/admin/app-settings`` - the full desired settings."""
