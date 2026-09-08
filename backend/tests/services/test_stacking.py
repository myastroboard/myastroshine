"""StackingService: the initiate -> upload -> process lifecycle (linear rebuild)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from app.db.models import StackRecord
from app.exceptions import InvalidParameterError, ResourceNotFoundError
from app.models import InitiateStackRequest
from app.services.job import JobService
from app.services.session import SessionService
from app.services.stacking import StackingService
from app.services.storage import StorageService
from app.utils.linear_ingest import LinearFrame
from tests.support import translate


@pytest.fixture
def stacking(db_session) -> StackingService:
    storage = StorageService()
    return StackingService(db_session, SessionService(db_session, storage), storage)


def _frame(array: np.ndarray) -> LinearFrame:
    """Wrap a BGR uint8 test image as a linear, already-stretched frame."""
    return LinearFrame(
        data=(array.astype(np.float32) / 255.0), already_stretched=True, source_bit_depth=8
    )


def _shifted_frames(star_field: np.ndarray, n: int) -> list[LinearFrame]:
    return [_frame(star_field), *(_frame(translate(star_field, i, -i)) for i in range(1, n))]


def test_initiate_then_upload_marks_ready(
    stacking: StackingService, star_field: np.ndarray
) -> None:
    record = stacking.initiate(InitiateStackRequest(frame_count=3))
    assert record.status == "waiting_for_frames"

    for i in range(3):
        record = stacking.add_frame(record.stack_id, i, _frame(star_field))
    assert record.received_frames == 3
    assert record.status == "ready"


def test_uploading_a_frame_writes_the_npy_plus_a_thumbnail(
    stacking: StackingService, star_field: np.ndarray
) -> None:
    record = stacking.initiate(InitiateStackRequest(frame_count=2))
    stacking.add_frame(record.stack_id, 0, _frame(star_field))

    assert stacking.storage.linear_frame_path(record.stack_id, 0).exists()
    assert stacking.storage.stack_thumb_path(record.stack_id, 0).exists()


def test_cleanup_removes_expired_stacks_and_their_frames(
    stacking: StackingService, star_field: np.ndarray
) -> None:
    live = stacking.initiate(InitiateStackRequest(frame_count=2))
    dead = stacking.initiate(InitiateStackRequest(frame_count=2))
    stacking.add_frame(dead.stack_id, 0, _frame(star_field))
    assert stacking.storage.stack_dir(dead.stack_id).exists()
    dead.expires_at = datetime.now(UTC) - timedelta(hours=1)
    stacking.db.commit()

    removed = stacking.cleanup_old_stacks()

    assert removed == 1
    assert stacking.db.get(StackRecord, live.stack_id) is not None
    assert stacking.db.get(StackRecord, dead.stack_id) is None
    assert not stacking.storage.stack_dir(dead.stack_id).exists()


def test_process_produces_an_enhanceable_session(
    stacking: StackingService, star_field: np.ndarray
) -> None:
    """A processed stack yields a composite exposed as a normal session."""
    record = stacking.initiate(InitiateStackRequest(frame_count=4))
    for i, frame in enumerate(_shifted_frames(star_field, 4)):
        stacking.add_frame(record.stack_id, i, frame)

    done = stacking.process(record.stack_id)

    assert done.status == "completed"
    assert done.session_id is not None
    assert stacking.storage.has_session(done.session_id)
    assert stacking.storage.stack_composite_path(record.stack_id).exists()
    assert done.result is not None
    assert done.result["frames_stacked"] == 4
    assert done.result["frames_excluded"] == 0
    assert done.result["snr_improvement"] == pytest.approx(2.0)


def test_excluded_frames_are_left_out_of_the_composite(
    stacking: StackingService, star_field: np.ndarray
) -> None:
    record = stacking.initiate(InitiateStackRequest(frame_count=4))
    for i, frame in enumerate(_shifted_frames(star_field, 4)):
        stacking.add_frame(record.stack_id, i, frame)
    stacking.set_frame_excluded(record.stack_id, 2, excluded=True)

    done = stacking.process(record.stack_id)

    assert done.result is not None
    assert done.result["frames_stacked"] == 3
    assert done.result["frames_excluded"] == 1


def test_excluding_an_unknown_frame_raises(stacking: StackingService) -> None:
    record = stacking.initiate(InitiateStackRequest(frame_count=2))
    with pytest.raises(ResourceNotFoundError):
        stacking.set_frame_excluded(record.stack_id, 0, excluded=True)


def test_upload_rejects_an_index_past_the_instance_cap(
    stacking: StackingService, star_field: np.ndarray
) -> None:
    from app.utils import app_settings

    app_settings.save_app_settings({"stacking_max_frames": 3})
    record = stacking.initiate(InitiateStackRequest(frame_count=2))
    with pytest.raises(InvalidParameterError):
        stacking.add_frame(record.stack_id, 5, _frame(star_field))


def test_adding_frames_past_the_initial_count_grows_the_stack(
    stacking: StackingService, star_field: np.ndarray
) -> None:
    """Uploading more frames than `initiate` estimated just grows `frame_count`."""
    record = stacking.initiate(InitiateStackRequest(frame_count=2))
    for i in range(4):
        record = stacking.add_frame(record.stack_id, i, _frame(star_field))
    assert record.received_frames == 4
    assert record.frame_count == 4


def test_process_needs_two_frames(stacking: StackingService, star_field: np.ndarray) -> None:
    record = stacking.initiate(InitiateStackRequest(frame_count=2))
    stacking.add_frame(record.stack_id, 0, _frame(star_field))
    with pytest.raises(InvalidParameterError, match="2 frames"):
        stacking.process(record.stack_id)


def test_process_rejects_mismatched_dimensions(
    stacking: StackingService, star_field: np.ndarray
) -> None:
    record = stacking.initiate(InitiateStackRequest(frame_count=2))
    stacking.add_frame(record.stack_id, 0, _frame(star_field))
    stacking.add_frame(record.stack_id, 1, _frame(star_field[:, :100]))
    with pytest.raises(InvalidParameterError, match="dimensions"):
        stacking.process(record.stack_id)


def test_unknown_stack_raises(stacking: StackingService) -> None:
    with pytest.raises(ResourceNotFoundError):
        stacking.process("no-such-stack")


def test_dispatch_drives_the_job_to_a_terminal_state_in_sync_mode(
    stacking: StackingService, star_field: np.ndarray
) -> None:
    """A sync-mode stack must mark its JobRecord completed, or it counts against
    the per-IP concurrency limit forever."""
    jobs = JobService(stacking.db)
    record = stacking.initiate(InitiateStackRequest(frame_count=3))
    for i, frame in enumerate(_shifted_frames(star_field, 3)):
        stacking.add_frame(record.stack_id, i, frame)

    _done, job_id = stacking.dispatch(record.stack_id, jobs, client_ip="1.2.3.4")

    assert jobs.get(job_id).status == "completed"
    assert jobs.count_active_for_ip("1.2.3.4") == 0
