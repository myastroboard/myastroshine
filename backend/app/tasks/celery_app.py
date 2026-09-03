"""Celery application instance.

Only used when the job queue is enabled (phase 2+). The API falls back to
in-process processing when Celery/Redis are not configured.
"""

from __future__ import annotations

from celery import Celery

from app.config import get_settings

_settings = get_settings()

celery_app = Celery(
    "myastroshine",
    broker=_settings.celery_broker_url,
    backend=_settings.redis_url,
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
)
