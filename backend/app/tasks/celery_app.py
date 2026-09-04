"""Celery application.

Used when ``PROCESSING_MODE=queue``. A worker runs alongside the API:

    celery -A app.tasks.celery_app worker --loglevel=info

In tests (``APP_ENV=test``) tasks run eagerly (inline), so no broker is needed.
"""

from __future__ import annotations

from typing import Any

from celery import Celery
from celery.signals import setup_logging

from app.config import get_settings
from app.logging_config import apply_runtime_log_levels, configure_logging

_settings = get_settings()


@setup_logging.connect
def _configure_worker_logging(**_kwargs: Any) -> None:
    """Use the app's logging (rotating worker.log + console), not Celery's."""
    configure_logging(role="worker", force=True)
    apply_runtime_log_levels()


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
