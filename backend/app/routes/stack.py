"""Stacking routes (linear rebuild).

POST   /api/stack/initiate                       - open a stack session
POST   /api/stack/{id}/upload-frame              - upload one frame
POST   /api/stack/{id}/upload-frames             - upload a batch of frames in one request
POST   /api/stack/{id}/upload-archive            - upload a .zip of frames in one request
POST   /api/stack/{id}/frame/{index}/exclude     - include/exclude a frame
GET    /api/stack/{id}/frame/{index}/thumb       - a frame's thumbnail
POST   /api/stack/{id}/calibration/{kind}/frames - upload dark/flat/bias/dark_flat subs
DELETE /api/stack/{id}/calibration/{kind}        - drop every sub of one kind
POST   /api/stack/{id}/process                   - integrate the frames
GET    /api/stack/{id}                           - stack result, statistics, frame list

Processing runs inline (``PROCESSING_MODE=sync``) or on the Celery queue
(``PROCESSING_MODE=queue``); progress streams over ``/ws/stack-status/{job_id}``.
"""

from __future__ import annotations

import asyncio
import io
import zipfile

from fastapi import APIRouter, File, Form, Request, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from app.db.models import StackRecord
from app.dependencies import JobServiceDep, RequireRateLimit, StackingServiceDep, StorageDep
from app.exceptions import InvalidParameterError, ResourceNotFoundError, UnsupportedImageError
from app.logging_config import get_logger
from app.models import (
    CalibrationFrameCounts,
    CalibrationSummary,
    ExcludeFrameRequest,
    FrameQualityInfo,
    InitiateStackRequest,
    ProcessStackRequest,
    StackFrameInfo,
    StackResultResponse,
    StackSessionResponse,
    StackStatistics,
    UploadFrameResponse,
)
from app.services.calibration import CALIBRATION_KINDS
from app.services.storage import StorageService
from app.utils.app_settings import get_app_settings
from app.utils.linear_ingest import ingest_frame
from app.utils.rate_limit import get_client_ip
from app.utils.validators import validate_image_extension, validate_upload_size

logger = get_logger(__name__)

router = APIRouter(prefix="/stack", tags=["stacking"])

_ARCHIVE_MEMBER_CAP = 5000  # zip-bomb guard: refuse an archive claiming more members than this


_QUALITY_FIELDS = (
    "star_count",
    "fwhm",
    "roundness",
    "background",
    "snr",
    "score",
    "weight",
    "accepted",
    "reject_reason",
)


def _frame_infos(record: StackRecord, storage: StorageService) -> list[StackFrameInfo]:
    excluded = set(record.excluded_frames or [])
    rescued = set(record.included_frames or [])
    quality_by_index = {
        f["index"]: f for f in (record.quality_report or {}).get("frames", [])
    }
    infos: list[StackFrameInfo] = []
    for index in storage.stack_frame_indices(record.stack_id):
        raw = quality_by_index.get(index)
        quality = (
            FrameQualityInfo(**{k: raw[k] for k in _QUALITY_FIELDS}) if raw is not None else None
        )
        auto_rejected = quality is not None and not quality.accepted and index not in rescued
        infos.append(
            StackFrameInfo(
                index=index,
                thumb_url=f"/api/stack/{record.stack_id}/frame/{index}/thumb",
                excluded=index in excluded or auto_rejected,
                quality=quality,
            )
        )
    return infos


def _calibration_summary(record: StackRecord, storage: StorageService) -> CalibrationSummary:
    return CalibrationSummary(
        frames=CalibrationFrameCounts(**storage.cal_frame_counts(record.stack_id)),
        cosmetic_correction=record.cosmetic_correction,
    )


def _result(
    record: StackRecord, storage: StorageService, job_id: str | None = None
) -> StackResultResponse:
    session_id = record.session_id
    return StackResultResponse(
        stack_id=record.stack_id,
        status=record.status,
        job_id=job_id,
        ws_status_url=f"/ws/stack-status/{job_id}" if job_id else None,
        session_id=session_id,
        stacked_image_url=f"/api/preview/{session_id}?full=true" if session_id else None,
        statistics=StackStatistics(**record.result) if record.result else None,
        frames=_frame_infos(record, storage),
        calibration=_calibration_summary(record, storage),
        error=record.error,
    )


@router.post("/initiate", status_code=status.HTTP_202_ACCEPTED, response_model=StackSessionResponse)
async def initiate_stack(
    request: InitiateStackRequest, stacking: StackingServiceDep, _rate_limit: RequireRateLimit
) -> StackSessionResponse:
    """Open a stacking session and wait for frames."""
    record = stacking.initiate(request)
    return StackSessionResponse(
        stack_id=record.stack_id,
        status=record.status,
        frame_count=record.frame_count,
        received_frames=record.received_frames,
    )


@router.post(
    "/{stack_id}/upload-frame",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=UploadFrameResponse,
)
async def upload_frame(
    stack_id: str,
    stacking: StackingServiceDep,
    _rate_limit: RequireRateLimit,
    frame_index: int = Form(...),
    file: UploadFile = File(...),
) -> UploadFrameResponse:
    """Upload a single frame into an open stacking session."""
    data = await file.read()
    validate_upload_size(len(data))
    if file.filename:
        validate_image_extension(file.filename)
    frame = ingest_frame(data, file.filename)

    record = stacking.add_frame(stack_id, frame_index, frame)
    return UploadFrameResponse(
        frame_index=frame_index,
        received_frames=record.received_frames,
        frame_count=record.frame_count,
        status=record.status,
    )


@router.post(
    "/{stack_id}/upload-frames",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=StackSessionResponse,
)
async def upload_frames(
    stack_id: str,
    stacking: StackingServiceDep,
    _rate_limit: RequireRateLimit,
    start_index: int = Form(...),
    files: list[UploadFile] = File(...),
) -> StackSessionResponse:
    """Upload a batch of frames in one request, indexed ``start_index`` upward.

    The frontend sends frames in batches of a few dozen so a thousand-frame
    session is tens of requests, not a thousand. Decoding + thumbnailing the
    batch (the slow part - a FITS thumbnail is ~30 ms) runs across the
    threadpool; the disk writes and the single DB commit are serial.
    """
    stacking.get_result(stack_id)  # 404 before any work
    payloads: list[tuple[bytes, str | None]] = []
    for upload in files:
        data = await upload.read()
        validate_upload_size(len(data))
        if upload.filename:
            validate_image_extension(upload.filename)
        payloads.append((data, upload.filename))

    prepared = await asyncio.gather(
        *(run_in_threadpool(stacking.prepare_frame, data, name) for data, name in payloads)
    )
    record = await run_in_threadpool(
        stacking.add_frames, stack_id, start_index, list(prepared)
    )
    return StackSessionResponse(
        stack_id=record.stack_id,
        status=record.status,
        frame_count=record.frame_count,
        received_frames=record.received_frames,
    )


@router.post(
    "/{stack_id}/upload-archive",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=StackSessionResponse,
)
async def upload_archive(
    stack_id: str,
    stacking: StackingServiceDep,
    _rate_limit: RequireRateLimit,
    file: UploadFile = File(...),
) -> StackSessionResponse:
    """Upload many frames as one ``.zip`` - avoids one HTTP request per frame.

    Image members are ingested in filename order and assigned frame indices from
    the current ``received_frames`` upward, up to the session's ``frame_count``.
    """
    data = await file.read()
    validate_upload_size(len(data))
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise UnsupportedImageError("Not a valid zip archive") from exc

    members = [m for m in archive.infolist() if not m.is_dir()]
    if len(members) > _ARCHIVE_MEMBER_CAP:
        raise InvalidParameterError(f"Archive has too many members (max {_ARCHIVE_MEMBER_CAP})")

    image_members = sorted(
        (m for m in members if _is_supported_image(m.filename)),
        key=lambda m: m.filename,
    )
    if not image_members:
        raise UnsupportedImageError("Archive contains no supported image files")

    record = stacking.get_result(stack_id)  # 404 before any work
    ceiling = get_app_settings().stacking_max_frames
    next_index = record.received_frames
    added = 0
    for member in image_members:
        if next_index >= ceiling:
            break
        member_bytes = archive.read(member)
        validate_upload_size(len(member_bytes))
        record = stacking.add_frame(
            stack_id, next_index, ingest_frame(member_bytes, member.filename)
        )
        next_index += 1
        added += 1

    logger.info("stack archive uploaded", stack_id=stack_id, added=added)
    return StackSessionResponse(
        stack_id=record.stack_id,
        status=record.status,
        frame_count=record.frame_count,
        received_frames=record.received_frames,
    )


@router.post("/{stack_id}/frame/{index}/exclude", response_model=StackFrameInfo)
async def exclude_frame(
    stack_id: str,
    index: int,
    request: ExcludeFrameRequest,
    stacking: StackingServiceDep,
    _rate_limit: RequireRateLimit,
) -> StackFrameInfo:
    """Include or exclude one frame from the stack (spotted a trail, a cloud...)."""
    record = stacking.set_frame_excluded(stack_id, index, request.excluded)
    return StackFrameInfo(
        index=index,
        thumb_url=f"/api/stack/{record.stack_id}/frame/{index}/thumb",
        excluded=index in set(record.excluded_frames or []),
    )


@router.get("/{stack_id}/frame/{index}/thumb")
async def get_frame_thumb(
    stack_id: str, index: int, stacking: StackingServiceDep, storage: StorageDep
) -> FileResponse:
    """A frame's ~256 px auto-stretched thumbnail for the frame grid.

    Not rate-limited: the frame grid fetches one of these per tile (same
    reasoning as ``GET /api/preview`` and ``GET /api/config``).
    """
    stacking.get_result(stack_id)  # 404 for an unknown stack
    path = storage.stack_thumb_path(stack_id, index)
    if not path.exists():
        raise ResourceNotFoundError(f"Frame {index} not found for stack {stack_id}")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-cache"})


@router.post(
    "/{stack_id}/calibration/{kind}/frames",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=CalibrationSummary,
)
async def upload_calibration_frames(
    stack_id: str,
    kind: str,
    stacking: StackingServiceDep,
    storage: StorageDep,
    _rate_limit: RequireRateLimit,
    files: list[UploadFile] = File(...),
) -> CalibrationSummary:
    """Upload a batch of ``dark`` / ``flat`` / ``bias`` / ``dark_flat`` subs.

    Masters are built (per-pixel median) and cached when the stack runs; adding
    more subs later rebuilds them.
    """
    if kind not in CALIBRATION_KINDS:
        raise InvalidParameterError(f"Unknown calibration frame kind {kind!r}")
    frames = []
    for upload in files:
        data = await upload.read()
        validate_upload_size(len(data))
        if upload.filename:
            validate_image_extension(upload.filename)
        frames.append(ingest_frame(data, upload.filename))

    record = stacking.add_calibration_frames(stack_id, kind, frames)
    return _calibration_summary(record, storage)


@router.delete("/{stack_id}/calibration/{kind}", response_model=CalibrationSummary)
async def clear_calibration(
    stack_id: str,
    kind: str,
    stacking: StackingServiceDep,
    storage: StorageDep,
    _rate_limit: RequireRateLimit,
) -> CalibrationSummary:
    """Drop every sub of one calibration kind and any master derived from it."""
    record = stacking.clear_calibration(stack_id, kind)
    return _calibration_summary(record, storage)


@router.post("/{stack_id}/process", response_model=StackResultResponse)
def process_stack(
    stack_id: str,
    stacking: StackingServiceDep,
    storage: StorageDep,
    jobs: JobServiceDep,
    http_request: Request,
    _rate_limit: RequireRateLimit,
    overrides: ProcessStackRequest | None = None,
) -> StackResultResponse:
    """Integrate the frames into a composite.

    An optional body re-stacks with a changed setting (no re-upload). Defined
    ``def`` (not ``async``) so ``PROCESSING_MODE=sync`` runs the integration in a
    worker thread rather than blocking the event loop for the whole stack.
    """
    record, job_id = stacking.dispatch(stack_id, jobs, get_client_ip(http_request), overrides)
    return _result(record, storage, job_id)


@router.get("/{stack_id}", response_model=StackResultResponse)
async def get_stack(
    stack_id: str, stacking: StackingServiceDep, storage: StorageDep
) -> StackResultResponse:
    """Return the stack result, statistics, and the frame list."""
    return _result(stacking.get_result(stack_id), storage)


def _is_supported_image(filename: str) -> bool:
    try:
        return bool(validate_image_extension(filename))
    except UnsupportedImageError:
        return False
