"""Celery application.

Used when ``PROCESSING_MODE=queue``. A worker runs alongside the API:

    celery -A app.tasks.celery_app worker --loglevel=info

In tests (``APP_ENV=test``) tasks run eagerly (inline), so no broker is needed.
"""

from __future__ import annotations

from celery import Celery

from app.config import get_settings

_settings = get_settings()

celery_app = Celery(
    "myastroshine",
    broker=_settings.celery_broker_url,
    backend=_settings.redis_url,
    include=["app.tasks.processing"],
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_always_eager=_settings.app_env == "test",
    task_eager_propagates=True,
)
