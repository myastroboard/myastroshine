"""EnhancementService orchestration (sync mode)."""

from __future__ import annotations

import numpy as np
import pytest

from app.exceptions import SessionNotFoundError, UnsupportedImageError
from app.models import ProcessingParameters
from app.services.enhancement import EnhancementService
from app.services.image_processing import ImageProcessingService
from app.services.job import JobService
from app.services.session import SessionService
from app.services.storage import StorageService


@pytest.fixture
def enhancement(db_session) -> EnhancementService:
    storage = StorageService()
    return EnhancementService(
        SessionService(db_session, storage),
        storage,
        ImageProcessingService(),
        JobService(db_session),
    )


def test_dispatch_runs_inline_and_completes(
    enhancement: EnhancementService, sample_image: np.ndarray
) -> None:
    """dispatch() writes processed.jpg and returns a completed job."""
    record = enhancement.sessions.create_session(image_path="")
    enhancement.storage.save_original(record.session_id, sample_image)

    response = enhancement.dispatch(record.session_id, ProcessingParameters(contrast=2.0))

    assert response.status == "completed"
    assert response.session_id == record.session_id
    assert response.ws_status_url == f"/ws/processing-status/{response.job_id}"
    processed = enhancement.storage.load_processed(record.session_id)
    assert not np.array_equal(processed, sample_image)


def test_run_tracks_progress_on_the_job(
    enhancement: EnhancementService, sample_image: np.ndarray
) -> None:
    """run() moves the job queued -> processing -> completed at 100%."""
    record = enhancement.sessions.create_session(image_path="")
    enhancement.storage.save_original(record.session_id, sample_image)
    job = enhancement.jobs.create(record.session_id)

    enhancement.run(record.session_id, ProcessingParameters(denoise=20), job.job_id)

    done = enhancement.jobs.get(job.job_id)
    assert done.status == "completed"
    assert done.progress_percent == 100
    assert done.current_step == "done"


def test_dispatch_unknown_session_raises(enhancement: EnhancementService) -> None:
    with pytest.raises(SessionNotFoundError):
        enhancement.dispatch("11111111-1111-1111-1111-111111111111", ProcessingParameters())


def test_run_marks_job_failed_on_missing_image(
    enhancement: EnhancementService,
) -> None:
    """If the original image is gone, the job ends 'failed' and the error raises."""
    record = enhancement.sessions.create_session(image_path="")
    job = enhancement.jobs.create(record.session_id)

    with pytest.raises(UnsupportedImageError):
        enhancement.run(record.session_id, ProcessingParameters(), job.job_id)

    assert enhancement.jobs.get(job.job_id).status == "failed"
