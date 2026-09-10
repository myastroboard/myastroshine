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
    # 600/min, well above a busy session: the editor re-processes on every slider
    # change (500ms debounce, ~120/min alone) and a stacking upload adds a burst on
    # top. It is an abuse guard for a public instance, not a fairness knob - a
    # single user doing real work should never hit it. See docs/API.md.
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = Field(default=600, ge=1, le=6000)
    max_concurrent_jobs_per_ip: int = Field(default=5, ge=1, le=100)

    # Uploads and sessions
    max_image_size_mb: int = Field(default=100, ge=1, le=1024)
    session_expiry_hours: int = Field(default=24, ge=1, le=8760)
    preview_max_size: int = Field(default=512, ge=64, le=4096)

    # AstroDex integration
    astrodex_callback_urls: list[str] = Field(default_factory=list)
    astrodex_max_retries: int = Field(default=3, ge=1, le=10)
    astrodex_retry_delay_seconds: float = Field(default=5.0, ge=0, le=60)

    # Stacking (linear rebuild - see initial_plan/12_STACKING_REBUILD.md).
    # Default sized for a real imaging night: a smart telescope at 10 s subs over
    # ~5-6 h of darkness produces ~2000 frames.
    stacking_enabled: bool = True
    stacking_max_frames: int = Field(default=2000, ge=2, le=5000)
    #: Threads for the per-frame register / align passes. 0 = auto (CPU count,
    #: capped at 4); 1 = sequential. The Celery worker itself runs 1-2 stacks.
    stacking_workers: int = Field(default=0, ge=0, le=16)
    # How long a stack's uploaded frames + working files are kept. They are much
    # heavier than a normal session (thousands of full-res frames) and are only
    # needed to review and re-stack; the composite a run produces is a normal
    # session and lives session_expiry_hours. Default 12 h.
    stacking_retention_hours: int = Field(default=12, ge=1, le=168)
    #: Watch-folder ingest: a directory the worker polls (empty = off). New image
    #: files are ingested into a rolling "watch" stack; once the folder is quiet
    #: for stacking_watch_idle_minutes the stack is processed (if auto-process is
    #: on) and the next file starts a fresh one.
    stacking_watch_dir: str = ""
    stacking_watch_idle_minutes: int = Field(default=10, ge=1, le=1440)
    stacking_watch_auto_process: bool = True

    # External ML engines - optional, operator-installed StarNet2 / DeepSNR, invoked
    # as a subprocess (docs/DEPLOYMENT.md "External ML engines"). Nothing is bundled:
    # the operator downloads the binary from starnetastro.com, mounts it into the
    # container, and points these at it. Empty (the default) = that engine is off and
    # the classical path is the only star-removal / denoise engine. Both the API and
    # the worker need the binary reachable at the same path.
    starnet2_path: str = ""
    deepsnr_path: str = ""
    #: -s/--stride for each tool; both require an even value in 2-512. 0 (the
    #: default) omits the flag so the tool uses its own default (StarNet2 256,
    #: DeepSNR 480) - forward-compatible if a future version changes that.
    starnet2_stride: int = Field(default=0, ge=0, le=512)
    deepsnr_stride: int = Field(default=0, ge=0, le=512)

    # Logging - file level and console level (changeable at runtime, see #4)
    log_level: str = "info"
    console_log_level: str = "warning"

    @field_validator("starnet2_stride", "deepsnr_stride", mode="after")
    @classmethod
    def _stride_even(cls, value: int) -> int:
        """StarNet2 / DeepSNR reject an odd stride outright - fail here, not at run time."""
        if value and value % 2:
            raise ValueError("stride must be even (or 0 to use the tool default)")
        return value

    @field_validator("cors_origins", "astrodex_callback_urls", mode="after")
    @classmethod
    def _clean_url_list(cls, value: list[str]) -> list[str]:
        """Trim whitespace and any trailing slash, and drop blank entries.

        A trailing slash is the usual copy-paste artefact and never what is meant
        here: a CORS ``Origin`` header carries none, and the AstroDex allowlist is
        matched against a slash-stripped ``callback_base`` (see
        ``is_allowed_callback_url``), so ``https://host/`` would silently match
        nothing. An empty entry is dropped - an empty prefix would match every URL.
        """
        cleaned = (item.strip().rstrip("/") for item in value)
        return [item for item in cleaned if item]

    @field_validator("cors_origins", mode="after")
    @classmethod
    def _reject_cors_wildcard(cls, value: list[str]) -> list[str]:
        """The CORS middleware always sets allow_credentials=True (main.py) - a
        literal "*" origin paired with credentials is a real hole, not just a
        combination browsers happen to reject."""
        if "*" in value:
            raise ValueError('cors_origins cannot contain "*" (credentials are always allowed)')
        return value


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


def _invalidate_derived_caches() -> None:
    """Drop caches keyed on settings values (use after any settings change)."""
    from app.services.engine_probe import clear_engine_probe_cache  # noqa: PLC0415 - import cycle

    clear_engine_probe_cache()


def reload_app_settings() -> AppSettings:
    """Drop the cache and re-read the file (use after an external write)."""
    with _lock:
        _cache.settings = _load_from_disk()
    _invalidate_derived_caches()
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
    _invalidate_derived_caches()
    applied = sorted(k for k in patch if k in AppSettings.model_fields)
    logger.info("app settings updated", keys=applied)
    return merged
