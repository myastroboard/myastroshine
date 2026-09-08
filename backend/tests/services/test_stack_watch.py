"""Folder-watch ingest for stacking (Phase 5)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import cv2
import numpy as np
import pytest
from sqlalchemy import select

from app.db.models import StackRecord
from app.services import stack_watch
from app.services.stack_watch import run_watch_tick
from app.services.storage import StorageService
from app.utils import app_settings


@pytest.fixture(autouse=True)
def _isolate_seen(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Keep the seen-file store inside the test's tmp dir."""
    monkeypatch.setattr(stack_watch, "_seen_path", lambda: tmp_path / "seen.json")


def _drop_frame(folder, name: str, seed: int) -> None:
    rng = np.random.default_rng(seed)
    img = rng.integers(0, 60, (48, 64, 3), dtype=np.uint8)
    img[10:14, 20:24] = 240  # a "star"
    ok, buf = cv2.imencode(".png", img)
    assert ok
    (folder / name).write_bytes(buf.tobytes())


@pytest.fixture
def watch_dir(tmp_path):
    folder = tmp_path / "incoming"
    folder.mkdir()
    app_settings.save_app_settings({"stacking_watch_dir": str(folder)})
    yield folder
    app_settings.save_app_settings({"stacking_watch_dir": ""})


def test_watch_is_a_no_op_when_unconfigured(db_session) -> None:
    app_settings.save_app_settings({"stacking_watch_dir": ""})
    assert run_watch_tick(db_session, StorageService())["status"] == "disabled"


def test_new_files_are_ingested_into_a_watch_stack(db_session, watch_dir) -> None:
    _drop_frame(watch_dir, "a.png", 1)
    _drop_frame(watch_dir, "b.png", 2)

    result = run_watch_tick(db_session, StorageService())

    assert result == {"status": "ingested", "count": 2, "stack_id": result["stack_id"]}
    record = db_session.scalars(select(StackRecord)).one()
    assert record.source == "watch"
    assert record.received_frames == 2


def test_a_second_batch_appends_to_the_same_stack(db_session, watch_dir) -> None:
    _drop_frame(watch_dir, "a.png", 1)
    first = run_watch_tick(db_session, StorageService())

    _drop_frame(watch_dir, "b.png", 2)
    _drop_frame(watch_dir, "c.png", 3)
    second = run_watch_tick(db_session, StorageService())

    assert second["stack_id"] == first["stack_id"]
    assert db_session.get(StackRecord, first["stack_id"]).received_frames == 3


def test_seen_files_are_not_re_ingested(db_session, watch_dir) -> None:
    _drop_frame(watch_dir, "a.png", 1)
    _drop_frame(watch_dir, "b.png", 2)
    run_watch_tick(db_session, StorageService())

    assert run_watch_tick(db_session, StorageService())["status"] == "waiting"


def test_an_idle_folder_auto_processes(
    db_session, watch_dir, monkeypatch: pytest.MonkeyPatch
) -> None:
    _drop_frame(watch_dir, "a.png", 1)
    _drop_frame(watch_dir, "b.png", 2)
    run_watch_tick(db_session, StorageService())
    app_settings.save_app_settings({"stacking_watch_idle_minutes": 5})

    record = db_session.scalars(select(StackRecord)).one()
    record.updated_at = datetime.now(UTC) - timedelta(minutes=10)
    db_session.commit()

    dispatched: list[str] = []
    monkeypatch.setattr(
        "app.services.stacking.StackingService.dispatch",
        lambda self, stack_id, jobs, **kw: dispatched.append(stack_id),
    )
    result = run_watch_tick(db_session, StorageService())

    assert result["status"] == "processing"
    assert dispatched == [record.stack_id]
