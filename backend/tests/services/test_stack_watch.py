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


def test_seen_path_resolves_under_the_data_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    """The real _seen_path (every other test monkeypatches it into tmp_path)."""
    from app.config import get_settings

    monkeypatch.undo()  # revert this test's autouse _isolate_seen patch
    assert stack_watch._seen_path() == get_settings().data_dir / "stacking_watch_seen.json"


def test_a_corrupt_seen_file_is_treated_as_empty(db_session, watch_dir, tmp_path) -> None:
    (tmp_path / "seen.json").write_text("not json{", encoding="utf-8")
    _drop_frame(watch_dir, "a.png", 1)

    result = run_watch_tick(db_session, StorageService())

    assert result["status"] == "ingested"  # the corrupt store didn't block ingest


def test_watch_dir_that_does_not_exist_reports_no_dir(db_session) -> None:
    app_settings.save_app_settings({"stacking_watch_dir": "/nonexistent/watch/dir/xyz"})
    try:
        result = run_watch_tick(db_session, StorageService())
        assert result["status"] == "no_dir"
    finally:
        app_settings.save_app_settings({"stacking_watch_dir": ""})


def test_no_files_and_no_stack_is_idle(db_session, watch_dir) -> None:
    result = run_watch_tick(db_session, StorageService())
    assert result["status"] == "idle"


def test_an_unreadable_file_is_skipped_and_marked_seen(db_session, watch_dir) -> None:
    """A file that decodes to nothing must not wedge the watch - it's logged
    and marked seen so it isn't retried forever, and the tick still succeeds
    with zero frames added."""
    (watch_dir / "corrupt.png").write_bytes(b"not actually a png")

    result = run_watch_tick(db_session, StorageService())

    assert result == {"status": "ingested", "count": 0, "stack_id": result["stack_id"]}
    # marked seen -> a second tick does not try it again as "new"
    assert run_watch_tick(db_session, StorageService())["status"] == "idle"


def test_files_past_the_frame_cap_are_marked_seen_as_overflow(
    db_session, watch_dir, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_settings.save_app_settings({"stacking_max_frames": 2})
    _drop_frame(watch_dir, "a.png", 1)
    _drop_frame(watch_dir, "b.png", 2)
    _drop_frame(watch_dir, "c.png", 3)  # will not fit under the cap

    result = run_watch_tick(db_session, StorageService())

    assert result["count"] == 2
    record = db_session.scalars(select(StackRecord)).one()
    assert record.received_frames == 2
    # the overflow file was still marked seen, not left to be rescanned forever
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
