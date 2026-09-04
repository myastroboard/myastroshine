"""Celery app config: the beat schedule that drives session cleanup.

``celery_app`` binds ``DATA_DIR`` at first import (module-level, like the
SQLAlchemy engine in ``app.db.database``), so these only check its *shape* -
not an exact path against the current test's isolated ``DATA_DIR``, which may
differ from whichever test triggered the first import.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from app.constants import SESSION_CLEANUP_INTERVAL_SECONDS
from app.tasks.celery_app import celery_app


def test_cleanup_sessions_task_is_scheduled() -> None:
    entry = celery_app.conf.beat_schedule["cleanup-expired-sessions"]
    assert entry["task"] == "myastroshine.cleanup_sessions"
    assert entry["schedule"] == timedelta(seconds=SESSION_CLEANUP_INTERVAL_SECONDS)


def test_beat_schedule_file_lives_under_a_data_dir() -> None:
    assert Path(celery_app.conf.beat_schedule_filename).name == "celerybeat-schedule"
