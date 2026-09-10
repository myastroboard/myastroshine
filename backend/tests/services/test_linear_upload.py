"""LinearUploadService: a single stacked FITS / 16-bit export opens as a composite."""

from __future__ import annotations

import io

import cv2
import numpy as np
import pytest
from astropy.io import fits

from app.db.models import StackRecord
from app.models import ProcessingParameters, StackParameters
from app.services.enhancement import EnhancementService
from app.services.image_processing import ImageProcessingService
from app.services.job import JobService
from app.services.linear_upload import LinearUploadService, is_linear_stack_upload
from app.services.session import SessionService
from app.services.storage import StorageService


@pytest.fixture
def linear_upload(db_session, tmp_path) -> LinearUploadService:
    storage = StorageService(root=tmp_path)
    return LinearUploadService(SessionService(db_session, storage), storage)


def _fits_cube(seed: int = 3, dead_corner: bool = False) -> bytes:
    """A faint linear RGB stack: sky + a bright central blob, optionally with a
    collapsed top-right corner (the Seestar field-rotation footprint)."""
    rng = np.random.default_rng(seed)
    h, w = 240, 180
    sky = 10_000 + rng.normal(0, 40, (h, w, 3)).astype(np.float32)
    yy, xx = np.mgrid[0:h, 0:w]
    blob = np.exp(-(((yy - h / 2) / 22) ** 2 + ((xx - w / 2) / 22) ** 2)).astype(np.float32)
    sky += blob[:, :, None] * np.array([1400.0, 400.0, 300.0], dtype=np.float32)
    if dead_corner:
        sky[: h // 6, -w // 4 :, 1:] -= 900.0  # G and B collapse in the corner
    cube = np.moveaxis(np.clip(sky, 0, None), -1, 0).astype(np.uint16)  # (3, H, W)
    buffer = io.BytesIO()
    fits.PrimaryHDU(data=cube).writeto(buffer)
    return buffer.getvalue()


def _png16(seed: int = 1) -> bytes:
    rng = np.random.default_rng(seed)
    img = (rng.random((80, 100, 3)) * 4000 + 8000).astype(np.uint16)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


def test_is_linear_stack_upload_classifies_sources() -> None:
    assert is_linear_stack_upload(b"", "stack.fits") is True
    assert is_linear_stack_upload(b"", "stack.FIT") is True
    assert is_linear_stack_upload(_png16(), "stack.png") is True
    _, jpeg = cv2.imencode(".jpg", np.zeros((10, 10, 3), np.uint8))
    assert is_linear_stack_upload(jpeg.tobytes(), "photo.jpg") is False
    _, png8 = cv2.imencode(".png", np.zeros((10, 10, 3), np.uint8))
    assert is_linear_stack_upload(png8.tobytes(), "photo.png") is False


def test_ingest_opens_a_composite_backed_session(
    linear_upload: LinearUploadService, db_session
) -> None:
    session, composite = linear_upload.ingest(_fits_cube(), "Stacked_NGC.fits")

    assert composite.ndim == 3 and composite.shape[2] == 3
    assert composite.dtype == np.float32
    # a StackRecord links the session so the enhancement pipeline runs the
    # linear "Stack" pre-stage on composite.npy
    record = db_session.query(StackRecord).filter_by(session_id=session.session_id).one()
    assert record.status == "completed"
    assert record.source == "single"
    assert linear_upload.storage.stack_composite_path(record.stack_id).exists()
    # before/after images are seeded with the default Stack render
    assert linear_upload.storage.processed_path(session.session_id).exists()


def _crop_box(service: LinearUploadService, db, session_id: str):
    record = db.query(StackRecord).filter_by(session_id=session_id).one()
    return record.quality_report["border_crop"]


def test_ingest_bakes_the_border_crop_only_when_a_border_is_dead(
    linear_upload: LinearUploadService, db_session
) -> None:
    clean_session, clean = linear_upload.ingest(_fits_cube(dead_corner=False), "clean.fits")
    dirty_session, dirty = linear_upload.ingest(_fits_cube(dead_corner=True), "dirty.fits")

    assert _crop_box(linear_upload, db_session, clean_session.session_id) is None
    assert clean.shape[:2] == (240, 180)

    dirty_box = _crop_box(linear_upload, db_session, dirty_session.session_id)
    assert dirty_box is not None
    top, _left, height, width = dirty_box
    assert top > 0 or width < 180  # the collapsed corner was trimmed off
    assert dirty.shape[:2] == (height, width)


def test_composite_session_runs_the_linear_stack_step(
    linear_upload: LinearUploadService, db_session
) -> None:
    """End to end: the editor's Stack controls drive a render off the 32-bit composite."""
    session, _ = linear_upload.ingest(_fits_cube(dead_corner=True), "Stacked_NGC.fits")

    jobs = JobService(db_session)
    enhancement = EnhancementService(
        linear_upload.sessions, linear_upload.storage, ImageProcessingService(), jobs
    )
    job = jobs.create(session.session_id)
    enhancement.run(
        session.session_id,
        ProcessingParameters(stack=StackParameters(stretch=0.2, background_extraction=100)),
        job.job_id,
    )

    assert jobs.get(job.job_id).status == "completed"
    result = cv2.imread(str(linear_upload.storage.processed_path(session.session_id)))
    assert result is not None
    # a low stretch target keeps the sky dark, not lifted to a milky grey
    assert int(np.median(result)) < 60
