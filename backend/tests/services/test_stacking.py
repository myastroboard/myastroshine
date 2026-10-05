"""StackingService: the initiate -> upload -> process lifecycle (linear rebuild)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import cv2
import numpy as np
import pytest

from app.db.models import StackRecord
from app.exceptions import InvalidParameterError, ResourceNotFoundError
from app.models import InitiateStackRequest, ProcessStackRequest
from app.services.integration import IntegrationResult
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


def _png_source(array: np.ndarray, name: str = "f.png") -> tuple[Callable[[], bytes], str]:
    """A frame source (reader + file name) over an encoded PNG, as an upload gives."""
    data = cv2.imencode(".png", array)[1].tobytes()
    return (lambda: data), name


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


def test_initiate_rejects_too_many_frames(stacking: StackingService) -> None:
    from app.utils import app_settings

    app_settings.save_app_settings({"stacking_max_frames": 5})
    with pytest.raises(InvalidParameterError, match="Too many frames"):
        stacking.initiate(InitiateStackRequest(frame_count=6))


def test_add_frame_rejects_once_the_stack_is_no_longer_accepting_frames(
    stacking: StackingService, star_field: np.ndarray
) -> None:
    record = stacking.initiate(InitiateStackRequest(frame_count=2))
    stacking.add_frame(record.stack_id, 0, _frame(star_field))
    stacking.add_frame(record.stack_id, 1, _frame(star_field))
    stacking.process(record.stack_id)  # -> status "completed"

    with pytest.raises(InvalidParameterError, match="not accepting"):
        stacking.add_frame(record.stack_id, 2, _frame(star_field))


def test_re_uploading_the_same_frame_index_does_not_double_count(
    stacking: StackingService, star_field: np.ndarray
) -> None:
    record = stacking.initiate(InitiateStackRequest(frame_count=3))
    record = stacking.add_frame(record.stack_id, 0, _frame(star_field))
    assert record.received_frames == 1
    record = stacking.add_frame(record.stack_id, 0, _frame(star_field))  # same index again
    assert record.received_frames == 1


def test_add_frames_batch_rejects_once_the_stack_is_no_longer_accepting_frames(
    stacking: StackingService, star_field: np.ndarray
) -> None:
    record = stacking.initiate(InitiateStackRequest(frame_count=2))
    stacking.add_frame(record.stack_id, 0, _frame(star_field))
    stacking.add_frame(record.stack_id, 1, _frame(star_field))
    stacking.process(record.stack_id)

    with pytest.raises(InvalidParameterError, match="not accepting"):
        stacking.add_frames(record.stack_id, 2, [_png_source(star_field)])


def test_add_frames_batch_rejects_an_index_past_the_instance_cap(
    stacking: StackingService, star_field: np.ndarray
) -> None:
    from app.utils import app_settings

    app_settings.save_app_settings({"stacking_max_frames": 3})
    record = stacking.initiate(InitiateStackRequest(frame_count=2))
    with pytest.raises(InvalidParameterError, match="frame_index"):
        stacking.add_frames(record.stack_id, 5, [_png_source(star_field)])


def test_add_frames_batch_does_not_double_count_an_existing_index(
    stacking: StackingService, star_field: np.ndarray
) -> None:
    record = stacking.initiate(InitiateStackRequest(frame_count=3))
    record = stacking.add_frame(record.stack_id, 0, _frame(star_field))
    assert record.received_frames == 1

    record, added = stacking.add_frames(record.stack_id, 0, [_png_source(star_field)])  # again
    assert record.received_frames == 1
    assert added == 1


def test_add_frames_ingests_a_batch_across_workers_in_index_order(
    stacking: StackingService, star_field: np.ndarray
) -> None:
    """Each frame lands at its own index, whatever order the workers finish in,
    and the batch is committed once."""
    record = stacking.initiate(InitiateStackRequest(frame_count=5))
    sources = [_png_source(translate(star_field, i, 0), f"f{i}.png") for i in range(5)]

    record, added = stacking.add_frames(record.stack_id, 0, sources)

    assert added == 5
    assert (record.received_frames, record.frame_count, record.status) == (5, 5, "ready")
    assert stacking.storage.stack_frame_indices(record.stack_id) == [0, 1, 2, 3, 4]


def test_add_frames_reads_each_source_only_when_its_turn_comes(
    stacking: StackingService, star_field: np.ndarray, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With one worker, a source is read only after the previous frame was written -
    a batch is never held in memory at once."""
    from app.services import stacking as stacking_module

    monkeypatch.setattr(stacking_module, "UPLOAD_INGEST_WORKERS", 1)
    record = stacking.initiate(InitiateStackRequest(frame_count=3))
    events: list[str] = []
    data = cv2.imencode(".png", star_field)[1].tobytes()

    def source(i: int) -> tuple[Callable[[], bytes], str]:
        def read() -> bytes:
            events.append(f"read {i}")
            return data

        return read, f"f{i}.png"

    original_write = stacking.storage.write_linear_frame

    def write(stack_id: str, index: int, prepared: object) -> None:
        events.append(f"write {index}")
        original_write(stack_id, index, prepared)  # type: ignore[arg-type]

    monkeypatch.setattr(stacking.storage, "write_linear_frame", write)

    stacking.add_frames(record.stack_id, 0, [source(i) for i in range(3)])

    assert events == ["read 0", "write 0", "read 1", "write 1", "read 2", "write 2"]


def test_add_frames_fails_the_batch_on_an_unreadable_frame(
    stacking: StackingService, star_field: np.ndarray
) -> None:
    record = stacking.initiate(InitiateStackRequest(frame_count=2))

    with pytest.raises(Exception):  # noqa: B017 - whatever the decoder raises for junk
        stacking.add_frames(
            record.stack_id, 0, [_png_source(star_field), ((lambda: b"junk"), "bad.png")]
        )


def test_add_frames_can_skip_unreadable_frames_on_consecutive_indices(
    stacking: StackingService, star_field: np.ndarray
) -> None:
    """The folder watch mode: a broken file is skipped and leaves no gap."""
    record = stacking.initiate(InitiateStackRequest(frame_count=2))
    sources = [_png_source(star_field, "a.png"), ((lambda: b"junk"), "bad.png")]
    sources.append(_png_source(translate(star_field, 2, 2), "b.png"))

    record, added = stacking.add_frames(record.stack_id, 0, sources, skip_unreadable=True)

    assert added == 2
    assert stacking.storage.stack_frame_indices(record.stack_id) == [0, 1]
    assert record.received_frames == 2


def test_add_frames_with_an_empty_batch_changes_nothing(stacking: StackingService) -> None:
    record = stacking.initiate(InitiateStackRequest(frame_count=2))

    record, added = stacking.add_frames(record.stack_id, 0, [])

    assert added == 0
    assert record.received_frames == 0


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


def test_cleanup_removes_abandoned_uploads(
    stacking: StackingService, star_field: np.ndarray
) -> None:
    """A stack with frames uploaded but never processed is swept early (a night
    of frames is many GB - it must not wait for the full retention window)."""
    from app.constants import ABANDONED_STACK_SECONDS

    stale = stacking.initiate(InitiateStackRequest(frame_count=2))
    stacking.add_frame(stale.stack_id, 0, _frame(star_field))
    stacking.add_frame(stale.stack_id, 1, _frame(star_field))
    assert stale.status == "ready"
    stale.created_at = datetime.now(UTC) - timedelta(seconds=ABANDONED_STACK_SECONDS + 60)
    fresh = stacking.initiate(InitiateStackRequest(frame_count=2))
    stacking.add_frame(fresh.stack_id, 0, _frame(star_field))
    stacking.db.commit()

    removed = stacking.cleanup_old_stacks()

    assert removed == 1
    assert stacking.db.get(StackRecord, stale.stack_id) is None
    assert not stacking.storage.stack_dir(stale.stack_id).exists()
    assert stacking.db.get(StackRecord, fresh.stack_id) is not None


def test_cleanup_sweeps_a_stale_align_memmap(
    stacking: StackingService, star_field: np.ndarray
) -> None:
    """A dead 'processing' run leaves a multi-GB align-memmap; cleanup nukes it
    and marks the stack failed."""
    import os

    from app.constants import STALE_STACK_WORK_SECONDS

    record = stacking.initiate(InitiateStackRequest(frame_count=2))
    stacking.add_frame(record.stack_id, 0, _frame(star_field))
    record.status = "processing"
    stacking.db.commit()
    accum = stacking.storage.stack_accum_dir(record.stack_id, create=True)
    memmap = accum / "aligned.npy"
    memmap.write_bytes(b"x" * 1024)
    old = datetime.now().timestamp() - STALE_STACK_WORK_SECONDS - 60
    os.utime(memmap, (old, old))

    removed = stacking.cleanup_old_stacks()

    assert removed == 1
    assert not accum.exists()
    assert stacking.storage.stack_frames_dir(record.stack_id).exists()  # frames kept
    refreshed = stacking.db.get(StackRecord, record.stack_id)
    assert refreshed is not None and refreshed.status == "failed"


def test_cleanup_removes_a_directory_with_no_record(stacking: StackingService) -> None:
    orphan = stacking.storage.stack_frames_dir("ghost-stack", create=True)
    assert orphan.exists()

    stacking.cleanup_old_stacks()

    assert not stacking.storage.stack_dir("ghost-stack").exists()


def test_cleanup_sweeps_a_stale_memmap_without_relabeling_a_finished_stack(
    stacking: StackingService, star_field: np.ndarray
) -> None:
    """The align-memmap is reclaimed regardless, but only a genuinely-stuck
    'processing' stack gets relabeled 'failed' - a finished one is left alone."""
    import os

    from app.constants import STALE_STACK_WORK_SECONDS

    record = stacking.initiate(InitiateStackRequest(frame_count=2))
    stacking.add_frame(record.stack_id, 0, _frame(star_field))
    record.status = "completed"  # a leftover accum dir from an earlier run, stack is done
    stacking.db.commit()
    accum = stacking.storage.stack_accum_dir(record.stack_id, create=True)
    memmap = accum / "aligned.npy"
    memmap.write_bytes(b"x" * 1024)
    old = datetime.now().timestamp() - STALE_STACK_WORK_SECONDS - 60
    os.utime(memmap, (old, old))

    removed = stacking.cleanup_old_stacks()

    assert removed == 1
    assert not accum.exists()
    refreshed = stacking.db.get(StackRecord, record.stack_id)
    assert refreshed is not None and refreshed.status == "completed"


def test_cleanup_is_a_noop_with_nothing_to_clean(stacking: StackingService) -> None:
    assert stacking.cleanup_old_stacks() == 0


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
    assert done.result["snr_improvement"] == pytest.approx(2.0, abs=0.4)


def test_process_summarizes_capture_info_from_the_kept_frames(
    stacking: StackingService, star_field: np.ndarray
) -> None:
    """Each sub's FITS metadata sidecar rolls up into the stack's capture info -
    the editor's info panel reads this off the completed StackRecord."""
    record = stacking.initiate(InitiateStackRequest(frame_count=4))
    for i, frame in enumerate(_shifted_frames(star_field, 4)):
        with_meta = LinearFrame(
            data=frame.data,
            already_stretched=frame.already_stretched,
            source_bit_depth=frame.source_bit_depth,
            metadata={"object": "NGC 7000", "filter": "LP", "exposure_s": "10.0"},
        )
        stacking.add_frame(record.stack_id, i, with_meta)
    stacking.set_frame_excluded(record.stack_id, 3, excluded=True)  # kept: 3 of 4

    done = stacking.process(record.stack_id)

    assert done.capture_info == {
        "object_name": "NGC 7000",
        "filter": "LP",
        "frame_count": 3,
        "exposure_s": 10.0,
        "total_exposure_s": 30.0,
    }


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


def test_quality_filter_auto_rejects_a_cloudy_frame(
    stacking: StackingService, star_field: np.ndarray
) -> None:
    """A dim, star-poor sub is dropped by the moderate quality filter and the
    per-frame report explains why."""
    record = stacking.initiate(InitiateStackRequest(frame_count=5, quality_filter="moderate"))
    for i, frame in enumerate(_shifted_frames(star_field, 5)):
        stacking.add_frame(record.stack_id, i, frame)
    stacking.add_frame(record.stack_id, 5, _frame(cv2.GaussianBlur(star_field, (0, 0), 3)))

    done = stacking.process(record.stack_id)

    assert done.result is not None
    assert done.result["frames_auto_rejected"] == 1
    assert done.result["frames_stacked"] == 5
    report = done.quality_report["frames"]
    rejected = [f for f in report if not f["accepted"]]
    assert [f["index"] for f in rejected] == [5]
    assert rejected[0]["reject_reason"] in {"clouds", "soft", "bright_sky"}


def test_rescued_frame_survives_the_next_run(
    stacking: StackingService, star_field: np.ndarray
) -> None:
    record = stacking.initiate(InitiateStackRequest(frame_count=5, quality_filter="moderate"))
    for i, frame in enumerate(_shifted_frames(star_field, 5)):
        stacking.add_frame(record.stack_id, i, frame)
    # a hazy sub: bright sky, but the stars are still sharp enough to register
    hazy = cv2.addWeighted(star_field, 0.6, np.full_like(star_field, 90), 0.4, 0)
    stacking.add_frame(record.stack_id, 5, _frame(hazy))
    first = stacking.process(record.stack_id)
    assert first.result["frames_auto_rejected"] == 1

    stacking.set_frame_excluded(record.stack_id, 5, excluded=False)  # rescue it
    assert stacking._get(record.stack_id).included_frames == [5]

    done = stacking.process(record.stack_id)
    assert done.result is not None
    assert done.result["frames_auto_rejected"] == 0
    assert done.result["frames_stacked"] == 6


def test_quality_filter_off_keeps_every_frame(
    stacking: StackingService, star_field: np.ndarray
) -> None:
    record = stacking.initiate(InitiateStackRequest(frame_count=5, quality_filter="off"))
    for i, frame in enumerate(_shifted_frames(star_field, 5)):
        stacking.add_frame(record.stack_id, i, frame)
    stacking.add_frame(record.stack_id, 5, _frame(cv2.GaussianBlur(star_field, (0, 0), 3)))

    done = stacking.process(record.stack_id)
    assert done.result is not None
    assert done.result["frames_auto_rejected"] == 0
    assert all("score" in f for f in done.quality_report["frames"])  # still scored


def test_process_calibrates_when_darks_and_flats_are_present(
    stacking: StackingService, star_field: np.ndarray
) -> None:
    """Uploaded calibration frames build masters and mark the result calibrated."""
    record = stacking.initiate(InitiateStackRequest(frame_count=4))
    for i, frame in enumerate(_shifted_frames(star_field, 4)):
        stacking.add_frame(record.stack_id, i, frame)

    dark = np.full_like(star_field, 6)
    flat = np.full_like(star_field, 180)
    stacking.add_calibration_frames(record.stack_id, "dark", [_png_source(dark)] * 3)
    stacking.add_calibration_frames(record.stack_id, "flat", [_png_source(flat)] * 3)

    done = stacking.process(record.stack_id)

    assert done.status == "completed"
    assert done.result is not None
    assert done.result["calibrated"] is True
    assert done.result["frames_stacked"] == 4
    assert stacking.storage.master_path(record.stack_id, "dark").exists()


def test_process_without_calibration_frames_is_not_calibrated(
    stacking: StackingService, star_field: np.ndarray
) -> None:
    record = stacking.initiate(InitiateStackRequest(frame_count=3))
    for i, frame in enumerate(_shifted_frames(star_field, 3)):
        stacking.add_frame(record.stack_id, i, frame)

    done = stacking.process(record.stack_id)

    assert done.result is not None
    assert done.result["calibrated"] is False


def test_add_calibration_frames_rejects_an_unknown_kind(stacking: StackingService) -> None:
    record = stacking.initiate(InitiateStackRequest(frame_count=2))
    with pytest.raises(InvalidParameterError, match="kind"):
        stacking.add_calibration_frames(record.stack_id, "sky", [])


def test_add_calibration_frames_rejects_more_than_the_instance_cap(
    stacking: StackingService, star_field: np.ndarray, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = stacking.initiate(InitiateStackRequest(frame_count=2))
    monkeypatch.setattr(stacking.storage, "cal_frame_indices", lambda *_a, **_k: list(range(256)))

    with pytest.raises(InvalidParameterError, match="Too many"):
        stacking.add_calibration_frames(record.stack_id, "dark", [_png_source(star_field)])


def test_clear_calibration_rejects_an_unknown_kind(stacking: StackingService) -> None:
    record = stacking.initiate(InitiateStackRequest(frame_count=2))
    with pytest.raises(InvalidParameterError, match="kind"):
        stacking.clear_calibration(record.stack_id, "sky")


def test_clear_calibration_drops_the_subs_and_master(
    stacking: StackingService, star_field: np.ndarray
) -> None:
    record = stacking.initiate(InitiateStackRequest(frame_count=2))
    stacking.add_calibration_frames(
        record.stack_id, "bias", [_png_source(np.full_like(star_field, 3))] * 2
    )
    assert stacking.storage.cal_frame_counts(record.stack_id)["bias"] == 2

    stacking.clear_calibration(record.stack_id, "bias")
    assert stacking.storage.cal_frame_counts(record.stack_id)["bias"] == 0


def test_dispatch_drives_the_job_to_a_terminal_state(
    stacking: StackingService, star_field: np.ndarray, job_db
) -> None:
    """A stack job must end with its JobRecord completed, or it counts against
    the per-IP concurrency limit forever."""
    jobs = JobService(stacking.db)
    record = stacking.initiate(InitiateStackRequest(frame_count=3))
    for i, frame in enumerate(_shifted_frames(star_field, 3)):
        stacking.add_frame(record.stack_id, i, frame)

    _done, job_id = stacking.dispatch(record.stack_id, jobs, client_ip="1.2.3.4")

    stacking.db.expire_all()  # the job committed through its own session
    assert jobs.get(job_id).status == "completed"
    assert jobs.count_active_for_ip("1.2.3.4") == 0


def test_dispatch_with_an_all_default_overrides_body_skips_the_extra_commit(
    stacking: StackingService, star_field: np.ndarray, job_db
) -> None:
    """overrides is not None, but every field is unset - nothing to change."""
    jobs = JobService(stacking.db)
    record = stacking.initiate(InitiateStackRequest(frame_count=3))
    for i, frame in enumerate(_shifted_frames(star_field, 3)):
        stacking.add_frame(record.stack_id, i, frame)

    _done, job_id = stacking.dispatch(record.stack_id, jobs, overrides=ProcessStackRequest())

    stacking.db.expire_all()
    assert jobs.get(job_id).status == "completed"


def test_dispatch_marks_the_job_failed_when_processing_raises(
    stacking: StackingService, star_field: np.ndarray, monkeypatch: pytest.MonkeyPatch, job_db
) -> None:
    """The failure happens after dispatch answered: it must land on the job row."""
    jobs = JobService(stacking.db)
    record = stacking.initiate(InitiateStackRequest(frame_count=3))
    for i, frame in enumerate(_shifted_frames(star_field, 3)):
        stacking.add_frame(record.stack_id, i, frame)

    def _explode(*_a: object, **_k: object) -> None:
        raise RuntimeError("integration exploded")

    monkeypatch.setattr(StackingService, "process", _explode)

    _record, job_id = stacking.dispatch(record.stack_id, jobs)

    stacking.db.expire_all()
    failed = jobs.get(job_id)
    assert failed.status == "failed"
    assert failed.error == "integration exploded"


def _fake_integration_result(reference_noise: float, composite: np.ndarray) -> IntegrationResult:
    return IntegrationResult(
        composite=composite,
        coverage=np.ones(composite.shape[:2], dtype=np.int32),
        frames_stacked=2,
        registration_failures=0,
        reference_index=0,
        rejected_samples=0,
        registration_rms=0.1,
        reference_noise=reference_noise,
        aligned=True,
        quality_rejected=0,
        frame_quality=[],
        weights=[1.0, 1.0],
    )


def test_process_skips_noise_measurement_when_the_reference_had_none(
    stacking: StackingService, star_field: np.ndarray, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = stacking.initiate(InitiateStackRequest(frame_count=2))
    for i, frame in enumerate(_shifted_frames(star_field, 2)):
        stacking.add_frame(record.stack_id, i, frame)
    composite = np.random.default_rng(1).random((*star_field.shape[:2], 3)).astype(np.float32)
    monkeypatch.setattr(
        stacking._integration,
        "integrate",
        lambda *_a, **_k: _fake_integration_result(0.0, composite),
    )

    done = stacking.process(record.stack_id)

    assert done.result["measured_noise_reduction"] is None


def test_process_skips_noise_measurement_when_the_composite_is_perfectly_flat(
    stacking: StackingService, star_field: np.ndarray, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A flat (zero-variance) composite has zero measured noise - dividing by
    it would be meaningless, so the ratio is skipped rather than computed."""
    record = stacking.initiate(InitiateStackRequest(frame_count=2))
    for i, frame in enumerate(_shifted_frames(star_field, 2)):
        stacking.add_frame(record.stack_id, i, frame)
    flat = np.full((*star_field.shape[:2], 3), 0.5, dtype=np.float32)
    monkeypatch.setattr(
        stacking._integration, "integrate", lambda *_a, **_k: _fake_integration_result(5.0, flat)
    )

    done = stacking.process(record.stack_id)

    assert done.result["measured_noise_reduction"] is None


def test_process_stops_at_its_next_step_when_the_server_shuts_down(
    stacking: StackingService, star_field: np.ndarray
) -> None:
    """A shutdown mid-stack stops the integration and leaves the stack failed."""
    from app.services import job_runner
    from app.services.job_runner import JobInterruptedError

    record = stacking.initiate(InitiateStackRequest(frame_count=3))
    for i, frame in enumerate(_shifted_frames(star_field, 3)):
        stacking.add_frame(record.stack_id, i, frame)
    job_runner.get_job_runner().stopping.set()

    with pytest.raises(JobInterruptedError):
        stacking.process(record.stack_id, "job-interrupted")

    assert stacking.get_result(record.stack_id).status == "failed"


def _matte(height: int, width: int, landscape_rows: int) -> np.ndarray:
    """A quarter-size sky matte (255 = sky) with landscape along the bottom."""
    matte = np.full((height // 4, width // 4), 255, dtype=np.uint8)
    matte[matte.shape[0] - landscape_rows // 4 :] = 0
    return matte


def test_a_stack_inherits_the_reference_frames_sky_matte(
    stacking: StackingService, star_field: np.ndarray
) -> None:
    """Frames are aligned onto the reference, so its matte marks the composite's
    sky: it is stored at the composite's size and the default render uses it."""
    record = stacking.initiate(InitiateStackRequest(frame_count=3))
    matte = _matte(120, 160, landscape_rows=32)
    for i, frame in enumerate(_shifted_frames(star_field, 3)):
        stacking.add_frame(record.stack_id, i, replace(frame, sky_matte=matte))

    done = stacking.process(record.stack_id)

    mask = stacking.storage.load_stack_sky_mask(record.stack_id)
    assert mask is not None
    composite = stacking.storage.load_stack_composite(record.stack_id)
    assert mask.shape == composite.shape[:2]
    assert mask[:40].min() == 255
    assert mask[-10:].max() == 0
    assert done.quality_report is not None


def test_a_stack_without_mattes_has_no_sky_mask(
    stacking: StackingService, star_field: np.ndarray
) -> None:
    """Deep-sky frames (no matte) leave the composite maskless."""
    record = stacking.initiate(InitiateStackRequest(frame_count=2))
    for i, frame in enumerate(_shifted_frames(star_field, 2)):
        stacking.add_frame(record.stack_id, i, frame)
    stacking.process(record.stack_id)
    assert stacking.storage.load_stack_sky_mask(record.stack_id) is None


def test_re_uploading_a_frame_without_a_matte_drops_the_old_one(
    stacking: StackingService, star_field: np.ndarray
) -> None:
    """A replaced frame never keeps the previous file's matte."""
    record = stacking.initiate(InitiateStackRequest(frame_count=2))
    with_matte = replace(_frame(star_field), sky_matte=_matte(120, 160, landscape_rows=32))
    stacking.add_frame(record.stack_id, 0, with_matte)
    assert stacking.storage.load_frame_sky_matte(record.stack_id, 0) is not None

    stacking.add_frame(record.stack_id, 0, _frame(star_field))
    assert stacking.storage.load_frame_sky_matte(record.stack_id, 0) is None


_PHONE_METADATA = {"camera_processed": "1", "focal_35mm": "24"}


def test_a_phone_stack_uses_equal_weights_and_records_its_render_hints(
    stacking: StackingService, star_field: np.ndarray
) -> None:
    """The phone denoises each frame by its own amount, so noise weighting is
    replaced by equal weights; the composite's render hints are stored."""
    record = stacking.initiate(InitiateStackRequest(frame_count=3))
    for i, frame in enumerate(_shifted_frames(star_field, 3)):
        stacking.add_frame(record.stack_id, i, replace(frame, metadata=_PHONE_METADATA))

    done = stacking.process(record.stack_id)

    assert done.quality_report is not None
    assert done.quality_report["weighting"] == "none"
    assert stacking.storage.load_stack_render_hints(record.stack_id) == {
        "camera_processed": True,
        "wide_field": True,
    }


def test_a_camera_stack_keeps_noise_weighting(
    stacking: StackingService, star_field: np.ndarray
) -> None:
    """Frames that are not camera-processed keep the requested weighting."""
    record = stacking.initiate(InitiateStackRequest(frame_count=2))
    for i, frame in enumerate(_shifted_frames(star_field, 2)):
        stacking.add_frame(record.stack_id, i, frame)
    done = stacking.process(record.stack_id)
    assert done.quality_report is not None
    assert done.quality_report["weighting"] == "noise"
