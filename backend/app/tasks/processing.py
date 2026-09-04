"""Celery tasks.

Each task opens its own DB session and drives the same service code the sync
path uses. Progress is published to Redis by ``EnhancementService`` /
``StackingService`` as they run.
"""

from __future__ import annotations

from app.db import database
from app.logging_config import get_logger
from app.models import ProcessingParameters
from app.services.enhancement import EnhancementService
from app.services.image_processing import ImageProcessingService
from app.services.job import JobService
from app.services.session import SessionService
from app.services.stacking import StackingService
from app.services.storage import StorageService
from app.tasks.celery_app import celery_app
from app.types import JsonDict

logger = get_logger(__name__)


@celery_app.task(name="myastroshine.process_image")
def task_process_image(session_id: str, parameters: JsonDict, job_id: str) -> str:
    """Run the enhancement pipeline for a session and return the job id."""
    with database.SessionLocal() as db:
        storage = StorageService()
        enhancement = EnhancementService(
            SessionService(db, storage), storage, ImageProcessingService(), JobService(db)
        )
        enhancement.run(session_id, ProcessingParameters(**parameters), job_id)
    return job_id


@celery_app.task(name="myastroshine.process_stack")
def task_process_stack(stack_id: str, job_id: str) -> str:
    """Register, normalise, reject cosmic rays, and combine a frame stack."""
    with database.SessionLocal() as db:
        storage = StorageService()
        stacking = StackingService(db, SessionService(db, storage), storage)
        JobService(db).update(job_id, status="processing", progress_percent=5)
        try:
            stacking.process(stack_id, job_id)
        except Exception as exc:
            JobService(db).update(job_id, status="failed", error=str(exc))
            raise
        JobService(db).update(job_id, status="completed", progress_percent=100)
    return stack_id


@celery_app.task(name="myastroshine.cleanup_sessions")
def task_cleanup_sessions() -> int:
    """Delete expired sessions and their files."""
    with database.SessionLocal() as db:
        return SessionService(db, StorageService()).cleanup_old_sessions()
