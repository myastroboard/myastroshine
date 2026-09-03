"""Celery tasks for heavy processing (phase 2+)."""

from __future__ import annotations

from app.logging_config import get_logger
from app.tasks.celery_app import celery_app
from app.types import JsonDict

logger = get_logger(__name__)


@celery_app.task(name="myastroshine.process_image")
def task_process_image(session_id: str, parameters: JsonDict) -> JsonDict:
    """Run the full enhancement pipeline for a session."""
    raise NotImplementedError


@celery_app.task(name="myastroshine.generate_depth_map")
def task_generate_depth_map(session_id: str, num_layers: int = 7) -> JsonDict:
    """Generate the depth map and parallax layers for a session."""
    raise NotImplementedError


@celery_app.task(name="myastroshine.process_stack")
def task_process_stack(stack_id: str) -> JsonDict:
    """Register, normalize, reject cosmic rays, and combine a frame stack."""
    raise NotImplementedError


@celery_app.task(name="myastroshine.cleanup_sessions")
def task_cleanup_sessions() -> int:
    """Delete expired sessions and their files."""
    raise NotImplementedError
