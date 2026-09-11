"""Admin routes - runtime configuration, logs, and job history.

Settings:
    GET  /api/admin/app-settings     - the live runtime settings
    POST /api/admin/app-settings     - replace them (writes app_settings.json)
    GET  /api/admin/engine-status    - probe the configured StarNet2 / DeepSNR paths

Logs (see app/logging_config.py):
    GET  /api/admin/logs             - tail the rotating log file (newest first)
    GET  /api/admin/logs/level       - the two sink levels
    POST /api/admin/logs/level       - change them at runtime (persisted)
    POST /api/admin/logs/clear       - empty myastroshine.log
    GET  /api/admin/logs/export      - ZIP: myastroshine.log + rotations + worker.log

Operations:
    GET  /api/admin/jobs             - recent processing jobs, newest first
    GET  /api/admin/disk-usage       - the data volume, broken down by what put bytes there

Every route here is gated by ``ADMIN_ENABLED`` (on by default for single-user
local deployments) and rate-limited. Changing ``cors_origins`` takes effect on
the next restart (the CORS middleware reads it once at startup); every other
setting applies immediately.
"""

from __future__ import annotations

import io
import zipfile
from collections import deque
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Query, Response

from app.config import get_settings
from app.dependencies import JobServiceDep, RequireAdmin, RequireRateLimit
from app.logging_config import apply_runtime_log_levels, get_logger, truncate_main_log
from app.models import (
    AppSettingsResponse,
    AppSettingsUpdate,
    DiskUsageResponse,
    EngineStatusResponse,
    JobListResponse,
    JobSummary,
    LogLevels,
    LogLevelUpdate,
    LogTailResponse,
)
from app.services.engine_probe import get_engine_statuses
from app.utils import disk_usage
from app.utils.app_settings import get_app_settings, save_app_settings

logger = get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

_TAIL_SCAN_LIMIT = 20_000  # lines held in memory while filtering


# --- runtime settings ------------------------------------------------------


@router.get("/app-settings", response_model=AppSettingsResponse)
async def read_app_settings(
    _admin: RequireAdmin, _rate_limit: RequireRateLimit
) -> AppSettingsResponse:
    """Return the current runtime settings."""
    return AppSettingsResponse.model_validate(get_app_settings().model_dump())


@router.post("/app-settings", response_model=AppSettingsResponse)
async def update_app_settings(
    body: AppSettingsUpdate, _admin: RequireAdmin, _rate_limit: RequireRateLimit
) -> AppSettingsResponse:
    """Persist the posted settings and refresh the in-memory cache."""
    updated = save_app_settings(body.model_dump())
    apply_runtime_log_levels()
    logger.info("app settings replaced via API")
    return AppSettingsResponse.model_validate(updated.model_dump())


@router.get("/engine-status", response_model=EngineStatusResponse)
async def read_engine_status(
    _admin: RequireAdmin, _rate_limit: RequireRateLimit
) -> EngineStatusResponse:
    """Probe the configured external ML engine paths (StarNet2 / DeepSNR).

    Drives the "engine detected / not found / untested version" line in Settings.
    Memoised until the next settings change; a no-op for an engine with no path.
    """
    statuses = get_engine_statuses()
    return EngineStatusResponse(starnet2=statuses["starnet2"], deepsnr=statuses["deepsnr"])


# --- logs ----------------------------------------------------------------


def _tail(path: Path, limit: int, offset: int, level: str | None) -> list[str]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        lines = [line.rstrip("\n") for line in deque(handle, maxlen=_TAIL_SCAN_LIMIT)]
    if level:
        needle = f" - {level.upper()} "  # `- app.x - INFO [f:1] -` / `- app.x - INFO -`
        lines = [line for line in lines if needle in line]
    lines.reverse()  # newest first
    return lines[offset : offset + limit]


@router.get("/logs", response_model=LogTailResponse)
async def tail_logs(
    _admin: RequireAdmin,
    _rate_limit: RequireRateLimit,
    limit: int = Query(200, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    level: str | None = Query(None, description="only lines at this level"),
) -> LogTailResponse:
    """Return the most recent log lines, newest first."""
    lines = _tail(get_settings().log_file, limit, offset, level)
    return LogTailResponse(lines=lines, returned=len(lines), filtered_level=level)


@router.get("/logs/level", response_model=LogLevels)
async def read_log_levels(_admin: RequireAdmin, _rate_limit: RequireRateLimit) -> LogLevels:
    """Return the file and console log levels."""
    settings = get_app_settings()
    return LogLevels(file=settings.log_level, console=settings.console_log_level)


@router.post("/logs/level", response_model=LogLevels)
async def update_log_levels(
    body: LogLevelUpdate, _admin: RequireAdmin, _rate_limit: RequireRateLimit
) -> LogLevels:
    """Change one or both sink levels immediately and persist the choice."""
    patch: dict[str, str] = {}
    if body.file is not None:
        patch["log_level"] = body.file
    if body.console is not None:
        patch["console_log_level"] = body.console
    if patch:
        save_app_settings(patch)
        apply_runtime_log_levels()
        logger.info("log levels changed", **patch)
    settings = get_app_settings()
    return LogLevels(file=settings.log_level, console=settings.console_log_level)


@router.post("/logs/clear", status_code=204)
async def clear_logs(_admin: RequireAdmin, _rate_limit: RequireRateLimit) -> None:
    """Empty the main log file (rotations are left in place)."""
    truncate_main_log()
    logger.info("main log cleared via API")


@router.get("/logs/export")
async def export_logs(_admin: RequireAdmin, _rate_limit: RequireRateLimit) -> Response:
    """Bundle the main and worker logs (with rotations) into a ZIP."""
    settings = get_settings()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for base in (settings.log_file, settings.worker_log_file):
            rotations = sorted(base.parent.glob(f"{base.name}.*"))
            for candidate in (base, *rotations):
                if candidate.exists():
                    archive.write(candidate, candidate.name)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="myastroshine-logs-{stamp}.zip"'},
    )


# --- operations ------------------------------------------------------------


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(
    jobs: JobServiceDep,
    _admin: RequireAdmin,
    _rate_limit: RequireRateLimit,
    status: str | None = Query(None, description="e.g. failed, processing, superseded"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> JobListResponse:
    """Recent processing jobs, newest first.

    With no ``status`` filter, ``superseded`` rows are hidden by default - one
    is created for every debounced slider edit that got pre-empted by the
    next, so an unfiltered view is mostly noise.
    """
    rows, total = jobs.list_recent(status=status, limit=limit, offset=offset)
    return JobListResponse(
        jobs=[
            JobSummary(
                job_id=row.job_id,
                session_id=row.session_id,
                status=row.status,
                progress_percent=row.progress_percent,
                current_step=row.current_step,
                error=row.error,
                client_ip=row.client_ip,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/disk-usage", response_model=DiskUsageResponse)
async def read_disk_usage(_admin: RequireAdmin, _rate_limit: RequireRateLimit) -> DiskUsageResponse:
    """The data volume's filesystem total/used/free, plus how ``DATA_DIR``'s
    own bytes split across images, stacks, the database, and log files - the
    folder-watch stacking mode runs unattended, so this should be visible in
    Settings before a filling disk becomes an outage."""
    return DiskUsageResponse(**disk_usage.volume_usage(), **disk_usage.data_breakdown())
