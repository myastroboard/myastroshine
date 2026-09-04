"""Celery application.

Used when ``PROCESSING_MODE=queue``. A worker runs alongside the API:

    celery -A app.tasks.celery_app worker --loglevel=info

In tests (``APP_ENV=test``) tasks run eagerly (inline), so no broker is needed.

The compose ``worker`` service runs with ``-B`` (embedded beat): one worker
replica is the deployment target for now (mono-poste, see ALIGNMENT.md #1), so
there is no separate ``beat`` service. Scaling ``worker`` beyond one replica
would run the schedule multiple times - move beat to its own service first.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from celery import Celery
from celery.signals import setup_logging

from app.config import get_settings
from app.constants import SESSION_CLEANUP_INTERVAL_SECONDS
from app.logging_config import apply_runtime_log_levels, configure_logging

_settings = get_settings()
_settings.data_dir.mkdir(parents=True, exist_ok=True)  # beat needs it for the schedule file


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
    beat_schedule_filename=str(_settings.data_dir / "celerybeat-schedule"),
    beat_schedule={
        "cleanup-expired-sessions": {
            "task": "myastroshine.cleanup_sessions",
            "schedule": timedelta(seconds=SESSION_CLEANUP_INTERVAL_SECONDS),
        },
    },
)
