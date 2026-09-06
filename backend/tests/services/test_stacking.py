"""StackingService: the initiate -> upload -> process lifecycle."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from app.db.models import StackRecord
from app.exceptions import InvalidParameterError, ResourceNotFoundError
from app.models import InitiateStackRequest
from app.services.session import SessionService
from app.services.stacking import StackingService
from app.services.storage import StorageService
from tests.support import translate


@pytest.fixture
def stacking(db_session) -> StackingService:
    storage = StorageService()
    return StackingService(db_session, SessionService(db_session, storage), storage)


def _shifted_set(star_field: np.ndarray, n: int) -> list[np.ndarray]:
    return [star_field, *(translate(star_field, i, -i) for i in range(1, n))]


def test_initiate_then_upload_marks_ready(
    stacking: StackingService, star_field: np.ndarray
) -> None:
    record = stacking.initiate(InitiateStackRequest(frame_count=3))
    assert record.status == "waiting_for_frames"

    for i in range(3):
        record = stacking.add_frame(record.stack_id, i, star_field)
    assert record.received_frames == 3
    assert record.status == "ready"


def test_cleanup_removes_expired_stacks_and_their_frames(
    stacking: StackingService, star_field: np.ndarray
) -> None:
    """cleanup_old_stacks drops only expired rows and their frame PNGs."""
    live = stacking.initiate(InitiateStackRequest(frame_count=2))
    dead = stacking.initiate(InitiateStackRequest(frame_count=2))
    stacking.add_frame(dead.stack_id, 0, star_field)
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
    record = stacking.initiate(InitiateStackRequest(frame_count=4, combination_method="median"))
    for i, frame in enumerate(_shifted_set(star_field, 4)):
        stacking.add_frame(record.stack_id, i, frame)

    done = stacking.process(record.stack_id)

    assert done.status == "completed"
    assert done.session_id is not None
    assert stacking.storage.has_session(done.session_id)
    assert done.result is not None
    assert done.result["frames_stacked"] == 4
    assert done.result["snr_improvement"] == pytest.approx(2.0)


def test_upload_rejects_out_of_range_index(
    stacking: StackingService, star_field: np.ndarray
) -> None:
    record = stacking.initiate(InitiateStackRequest(frame_count=2))
    with pytest.raises(InvalidParameterError):
        stacking.add_frame(record.stack_id, 5, star_field)


def test_process_needs_two_frames(stacking: StackingService, star_field: np.ndarray) -> None:
    record = stacking.initiate(InitiateStackRequest(frame_count=2))
    stacking.add_frame(record.stack_id, 0, star_field)
    with pytest.raises(InvalidParameterError, match="2 frames"):
        stacking.process(record.stack_id)


def test_process_rejects_mismatched_dimensions(
    stacking: StackingService, star_field: np.ndarray
) -> None:
    record = stacking.initiate(InitiateStackRequest(frame_count=2))
    stacking.add_frame(record.stack_id, 0, star_field)
    stacking.add_frame(record.stack_id, 1, star_field[:, :100])
    with pytest.raises(InvalidParameterError, match="dimensions"):
        stacking.process(record.stack_id)


def test_unknown_stack_raises(stacking: StackingService) -> None:
    with pytest.raises(ResourceNotFoundError):
        stacking.process("no-such-stack")
