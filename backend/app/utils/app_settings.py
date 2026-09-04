"""Product configuration - runtime-tunable settings, persisted as JSON.

PASSATION section 1: ``docker compose up`` needs no ``.env`` editing. The session
secret is auto-generated once and kept in the data volume; everything else a user
tunes lives in ``DATA_DIR/app_settings.json`` and is edited from Settings in the
UI, never from an environment variable.

Loading: hard-coded defaults (the field defaults below), merged with the on-disk
file, cached in memory. Call :func:`reload_app_settings` after an external write
and :func:`save_app_settings` to change values.
"""

from __future__ import annotations

import contextlib
import json
import secrets
import threading
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import get_settings
from app.logging_config import get_logger

logger = get_logger(__name__)

_lock = threading.Lock()


class _Cache:
    """Process-wide memo, held on an instance so helpers never need ``global``."""

    settings: AppSettings | None = None
    secret_key: str | None = None


_cache = _Cache()


class AppSettings(BaseModel):
    """Runtime-tunable configuration. The field defaults are the shipped defaults."""

    model_config = ConfigDict(extra="ignore")

    # API
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # Rate limiting (per IP, across upload/process/stack - API spec "Rate Limiting").
    # 120/min, not the spec's original 10: the editor re-processes on every slider
    # change (500ms debounce - see docs/API.md "Rate Limiting" for the numbers).
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = Field(default=120, ge=1, le=1000)
    max_concurrent_jobs_per_ip: int = Field(default=5, ge=1, le=100)

    # Uploads and sessions
    max_image_size_mb: int = Field(default=100, ge=1, le=1024)
    session_expiry_hours: int = Field(default=24, ge=1, le=8760)
    preview_max_size: int = Field(default=512, ge=64, le=4096)

    # AstroDex integration
    astrodex_callback_urls: list[str] = Field(default_factory=list)
    astrodex_max_retries: int = Field(default=3, ge=1, le=10)
    astrodex_retry_delay_seconds: float = Field(default=5.0, ge=0, le=60)

    # Processing
    denoise_enable_ml: bool = False
    depth_detection_method: str = "gradient"  # gradient | ml

    # Stacking (v1.1+)
    stacking_enabled: bool = True
    stacking_max_frames: int = Field(default=100, ge=2, le=1000)
    stacking_detector: str = "orb"  # orb | sift
    stacking_combination_default: str = "median"  # median | mean | sigma_clip
    stacking_cosmic_ray_threshold: float = Field(default=3.0, ge=0.5, le=10.0)

    # Logging - file level and console level (changeable at runtime, see #4)
    log_level: str = "info"
    console_log_level: str = "warning"

    @field_validator("cors_origins", "astrodex_callback_urls", mode="after")
    @classmethod
    def _clean_url_list(cls, value: list[str]) -> list[str]:
        """Trim entries and drop blanks - an empty prefix would match every URL."""
        return [item.strip() for item in value if item and item.strip()]


def load_or_generate_secret_key() -> str:
    """Return the session secret, generating and persisting it on first run.

    Written once to ``DATA_DIR/secret_key.txt`` (``secrets.token_hex(32)``), never
    regenerated, survives rebuilds. There is no ``SECRET_KEY`` environment
    variable to set.
    """
    if _cache.secret_key is not None:
        return _cache.secret_key
    with _lock:
        if _cache.secret_key is not None:
            return _cache.secret_key
        path = get_settings().secret_key_file
        if path.exists():
            key = path.read_text(encoding="utf-8").strip()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            key = secrets.token_hex(32)
            path.write_text(key, encoding="utf-8")
            with contextlib.suppress(OSError):  # chmod is a no-op on Windows
                path.chmod(0o600)
            logger.info("generated session secret key", path=str(path))
        _cache.secret_key = key
        return key


def _load_from_disk() -> AppSettings:
    path = get_settings().app_settings_file
    if not path.exists():
        return AppSettings()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        logger.exception("could not read app settings; falling back to defaults", path=str(path))
        return AppSettings()
    return AppSettings.model_validate(data)


def get_app_settings() -> AppSettings:
    """Return the cached product settings, loading them from disk on first use."""
    if _cache.settings is None:
        with _lock:
            if _cache.settings is None:
                _cache.settings = _load_from_disk()
    return _cache.settings


def reload_app_settings() -> AppSettings:
    """Drop the cache and re-read the file (use after an external write)."""
    with _lock:
        _cache.settings = _load_from_disk()
    return _cache.settings


def save_app_settings(patch: dict[str, Any]) -> AppSettings:
    """Merge ``patch`` into the current settings, persist, and refresh the cache.

    Unknown keys are ignored; values are validated against :class:`AppSettings`.
    """
    with _lock:
        current = _cache.settings or _load_from_disk()
        merged = AppSettings.model_validate({**current.model_dump(), **patch})
        path = get_settings().app_settings_file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(merged.model_dump_json(indent=2), encoding="utf-8")
        _cache.settings = merged
    applied = sorted(k for k in patch if k in AppSettings.model_fields)
    logger.info("app settings updated", keys=applied)
    return merged
