"""The work that runs off the request: processing jobs and periodic maintenance.

Every function here opens its own DB session (``database.SessionLocal``): it runs
on a background thread (``app.services.job_runner``) or from the in-process
scheduler (``app.services.scheduler``), long after the request that started it
has returned and closed its own session.
"""

from __future__ import annotations

from app.db import database
from app.logging_config import get_logger
from app.models import ProcessingParameters
from app.services.admin_auth import AdminAuthService
from app.services.engine_install import EngineInstallService
from app.services.enhancement import EnhancementService
from app.services.image_processing import ImageProcessingService
from app.services.job import JobService
from app.services.session import SessionService
from app.services.stack_watch import run_watch_tick
from app.services.stacking import StackingService
from app.services.storage import StorageService
from app.utils.app_settings import get_app_settings

logger = get_logger(__name__)


def run_image_job(session_id: str, parameters: ProcessingParameters, job_id: str) -> None:
    """Run the enhancement pipeline for a session, tracking ``job_id``."""
    with database.SessionLocal() as db:
        storage = StorageService()
        enhancement = EnhancementService(
            SessionService(db, storage), storage, ImageProcessingService(), JobService(db)
        )
        enhancement.run(session_id, parameters, job_id)


def run_stack_job(stack_id: str, job_id: str) -> None:
    """Register, normalise, reject outliers and combine a frame stack."""
    with database.SessionLocal() as db:
        storage = StorageService()
        jobs = JobService(db)
        stacking = StackingService(db, SessionService(db, storage), storage)
        jobs.update(job_id, status="processing", progress_percent=5)
        try:
            stacking.process(stack_id, job_id)
        except Exception as exc:
            jobs.update(job_id, status="failed", error=str(exc))
            raise
        jobs.update(job_id, status="completed", progress_percent=100)


def cleanup_expired() -> int:
    """Delete expired sessions and stacks (and their files), fail stale jobs,
    prune old *terminal* job history past ``job_history_retention_hours``, and
    drop expired admin logins and abandoned engine uploads. Returns how many
    records were removed / repaired."""
    storage = StorageService()
    with database.SessionLocal() as db:
        sessions = SessionService(db, storage)
        jobs = JobService(db)
        removed = sessions.cleanup_old_sessions()
        removed += StackingService(db, sessions, storage).cleanup_old_stacks()
        removed += jobs.cleanup_stale_jobs()
        removed += jobs.prune_old_jobs(get_app_settings().job_history_retention_hours)
        removed += AdminAuthService(db).prune_expired_sessions()
    return removed + EngineInstallService().prune_stale_staging()


def watch_stacking_folder() -> str:
    """Poll ``stacking_watch_dir`` for new frames (no-op unless configured)."""
    with database.SessionLocal() as db:
        result = run_watch_tick(db, StorageService())
    return str(result.get("status", "?"))


def fail_interrupted_jobs() -> int:
    """At startup: every job still queued or running belongs to a previous run of
    this process, which is gone - mark them failed so the UI and the per-IP
    concurrency limit stop waiting for them."""
    with database.SessionLocal() as db:
        return JobService(db).fail_unfinished("interrupted by a restart")
