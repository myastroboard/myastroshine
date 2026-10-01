"""Upload handling that never holds more than one file in memory.

Starlette spools every multipart file to a temporary file as it parses the
request, so an ``UploadFile`` is already on disk when a route runs. What blew up
memory was reading it back whole (``await upload.read()``) - an archive or a
20-frame batch at once. The helpers here keep it on disk:

- :func:`check_upload` rejects an oversized or unsupported file from its spooled
  size and name, before a byte of it is read;
- :func:`upload_reader` hands the services a reader they call when they get to
  that file (``StackingService.add_frames`` reads, decodes and writes one frame
  at a time);
- :func:`request_body_limit` is the per-route ceiling the app middleware checks
  against ``Content-Length``, so an oversized request is refused before
  Starlette spools it to disk at all.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from fastapi import UploadFile

from app.constants import (
    ENGINE_ARCHIVE_MAX_BYTES,
    MULTIPART_OVERHEAD_BYTES,
    UPLOAD_BATCH_MAX_FILES,
)
from app.exceptions import InvalidParameterError
from app.utils.app_settings import get_app_settings
from app.utils.validators import validate_image_extension, validate_upload_size

_MIB = 1024 * 1024

#: Upload routes that carry exactly one file (image, frame or archive).
_SINGLE_FILE_ROUTES = re.compile(r"^/api/(upload|stack/[^/]+/(upload-frame|upload-archive))$")
#: Upload routes that carry a batch of up to ``UPLOAD_BATCH_MAX_FILES`` files.
_BATCH_ROUTES = re.compile(r"^/api/stack/[^/]+/(upload-frames|calibration/[^/]+/frames)$")
#: An engine package (StarNet2 / DeepSNR CLI archive) - much larger than an image.
_ENGINE_ROUTE = re.compile(r"^/api/admin/engines/[^/]+/stage$")


def check_upload(upload: UploadFile, *, check_extension: bool = True) -> None:
    """Reject ``upload`` on its spooled size and its name, without reading it.

    ``upload.size`` is set by Starlette while it spools the part; when a client
    sends a part it could not size, :func:`upload_reader` checks after reading.
    """
    if upload.size is not None:
        validate_upload_size(upload.size)
    if check_extension and upload.filename:
        validate_image_extension(upload.filename)


def check_batch(uploads: list[UploadFile]) -> None:
    """:func:`check_upload` every file of a batch, and cap the batch size."""
    if len(uploads) > UPLOAD_BATCH_MAX_FILES:
        raise InvalidParameterError(f"Too many files in one request (max {UPLOAD_BATCH_MAX_FILES})")
    for upload in uploads:
        check_upload(upload)


def upload_reader(upload: UploadFile) -> Callable[[], bytes]:
    """A reader returning the whole spooled file, called when the file's turn comes.

    Sync (``upload.file``), so it runs on whichever worker thread decodes it.
    """

    def read() -> bytes:
        upload.file.seek(0)
        data = upload.file.read()
        validate_upload_size(len(data))
        return data

    return read


def request_body_limit(method: str, path: str) -> int | None:
    """The largest request body an upload route accepts, or ``None`` for any
    other request (left to the route's own validation)."""
    if method != "POST":
        return None
    file_cap = get_app_settings().max_image_size_mb * _MIB
    if _SINGLE_FILE_ROUTES.match(path):
        return file_cap + MULTIPART_OVERHEAD_BYTES
    if _BATCH_ROUTES.match(path):
        return file_cap * UPLOAD_BATCH_MAX_FILES + MULTIPART_OVERHEAD_BYTES
    if _ENGINE_ROUTE.match(path):
        return ENGINE_ARCHIVE_MAX_BYTES + MULTIPART_OVERHEAD_BYTES
    return None
