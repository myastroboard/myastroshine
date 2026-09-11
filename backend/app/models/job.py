"""Admin job-history endpoint models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class JobSummary(BaseModel):
    """One row of ``GET /api/admin/jobs``."""

    job_id: str
    session_id: str | None
    status: str
    progress_percent: int
    current_step: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime


class JobListResponse(BaseModel):
    """Body of ``GET /api/admin/jobs`` - newest first."""

    jobs: list[JobSummary]
    total: int
    limit: int
    offset: int


class DiskUsageResponse(BaseModel):
    """Body of ``GET /api/admin/disk-usage``."""

    total_bytes: int
    used_bytes: int
    free_bytes: int
    images_bytes: int
    stacks_bytes: int
    db_bytes: int
    logs_bytes: int
