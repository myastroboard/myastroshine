"""Open a single already-stacked linear frame as a composite session.

A Seestar / ASIAIR / DeepSkyStacker-style stacked FITS (or a 16-bit stack TIFF /
PNG export) is one frame of linear, full-bit-depth data - the same kind of
pixels the multi-frame stacker's composite is. Routing it through a composite
session, instead of :func:`app.utils.image_utils.decode_image`'s one-shot 8-bit
auto-stretch, unlocks the editor's linear "Stack" step - background extraction,
colour calibration and a tunable deep stretch, all recomputed from the 32-bit
composite on every render - and keeps the faint signal in float through the
whole tone chain rather than quantising it to 256 levels on the way in.

``decode_image`` still handles ordinary 8-bit photos and camera RAW.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import cv2
import numpy as np

from app.db.models import SessionRecord, StackRecord
from app.logging_config import get_logger
from app.models import StackParameters
from app.services.post_stack import crop_low_signal_border, render_stack_base
from app.services.session import SessionService
from app.services.storage import StorageService
from app.utils.app_settings import get_app_settings
from app.utils.image_utils import FITS_FORMATS, extension_of
from app.utils.linear_ingest import LinearFrame, debayer_rgb, ingest_frame

logger = get_logger(__name__)

#: TIFF / PNG carry both linear stack exports and ordinary photos - only a
#: >8-bit one is treated as linear stack data (see :func:`is_linear_stack_upload`).
_LINEAR_STANDARD_FORMATS = {".tif", ".tiff", ".png"}
_COLOR_NDIM = 3


def is_linear_stack_upload(data: bytes, filename: str | None) -> bool:
    """True when the upload is linear, full-bit-depth stack data.

    FITS always is (scientific linear data by convention); a TIFF / PNG only
    when it is stored deeper than 8-bit (a linear stack export, not a JPEG-grade
    preview). Everything else - JPEG, an 8-bit PNG, camera RAW - is left to
    :func:`app.utils.image_utils.decode_image`.
    """
    ext = extension_of(filename)
    if ext in FITS_FORMATS:
        return True
    if ext in _LINEAR_STANDARD_FORMATS:
        decoded = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        return decoded is not None and decoded.dtype != np.uint8
    return False


def _to_linear_composite(frame: LinearFrame) -> np.ndarray:
    """A :class:`LinearFrame` -> the ``(H, W, 3)`` / ``(H, W)`` linear composite.

    A CFA (Bayer) frame is debayered to RGB; a colour cube is used as-is; a mono
    stack is left 2D (``render_stack_base`` replicates it to three planes).
    """
    if frame.is_cfa and frame.bayer_pattern:
        frame = debayer_rgb(frame)
    return np.ascontiguousarray(frame.data.astype(np.float32))


class LinearUploadService:
    """Turns one linear stack upload into a composite-backed editing session."""

    def __init__(self, sessions: SessionService, storage: StorageService) -> None:
        self.sessions = sessions
        self.storage = storage

    def ingest(self, data: bytes, filename: str | None) -> tuple[SessionRecord, np.ndarray]:
        """Ingest ``data`` as a composite session; returns ``(session, composite)``.

        Bakes the border crop into ``composite.npy`` (like the multi-frame
        wedge crop), seeds the editor's before/after images with the default
        "Stack" render, and links a ``StackRecord`` so
        ``EnhancementService`` picks up the linear pre-stage.
        """
        frame = ingest_frame(data, filename)
        composite = _to_linear_composite(frame)
        composite, border_crop = crop_low_signal_border(composite)

        stack_id = str(uuid.uuid4())
        self.storage.save_stack_composite(stack_id, composite)

        session = self.sessions.create_session(image_path="", original_filename=filename)
        display = np.clip(render_stack_base(composite, StackParameters()) * 255.0, 0, 255).astype(
            np.uint8
        )
        self.storage.save_original(session.session_id, display)
        session.image_path = str(self.storage.original_path(session.session_id))

        db = self.sessions.db
        db.add(
            StackRecord(
                stack_id=stack_id,
                frame_count=1,
                received_frames=1,
                status="completed",
                source="single",
                session_id=session.session_id,
                post_process=False,
                cosmetic_correction=False,
                excluded_frames=[],
                included_frames=[],
                quality_report={"border_crop": list(border_crop) if border_crop else None},
                # One .npy, no heavy per-frame files to reclaim early - keep it
                # for the whole session lifetime so the linear editor stays live.
                expires_at=datetime.now(UTC)
                + timedelta(hours=get_app_settings().session_expiry_hours),
            )
        )
        db.commit()
        db.refresh(session)

        logger.info(
            "linear upload opened as composite session",
            session_id=session.session_id,
            stack_id=stack_id,
            shape=[int(n) for n in composite.shape],
            border_crop=list(border_crop) if border_crop else None,
        )
        return session, composite
