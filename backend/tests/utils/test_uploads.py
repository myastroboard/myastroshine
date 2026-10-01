"""Upload helpers (``app.utils.uploads``) and the request-size guard in front of them."""

from __future__ import annotations

import io
import zipfile

import numpy as np
import pytest
from fastapi import UploadFile

from app.constants import MULTIPART_OVERHEAD_BYTES, UPLOAD_BATCH_MAX_FILES
from app.exceptions import InvalidParameterError, PayloadTooLargeError, UnsupportedImageError
from app.utils.app_settings import save_app_settings
from app.utils.uploads import check_batch, check_upload, request_body_limit, upload_reader
from tests.support import png_bytes

MIB = 1024 * 1024


def _upload(data: bytes, name: str | None = "m42.png", *, size: int | None = -1) -> UploadFile:
    return UploadFile(io.BytesIO(data), filename=name, size=len(data) if size == -1 else size)


# --- check_upload / check_batch -----------------------------------------------


def test_check_upload_refuses_an_oversized_file_from_its_spooled_size() -> None:
    """The cap applies before reading: a declared size over it is refused."""
    save_app_settings({"max_image_size_mb": 1})

    with pytest.raises(PayloadTooLargeError):
        check_upload(_upload(b"x", size=2 * MIB))


def test_check_upload_refuses_an_unsupported_extension_unless_told_not_to() -> None:
    with pytest.raises(UnsupportedImageError):
        check_upload(_upload(b"x", "notes.txt"))

    check_upload(_upload(b"x", "frames.zip"), check_extension=False)


def test_check_upload_accepts_a_file_without_a_known_size_or_a_name() -> None:
    check_upload(_upload(b"x", None, size=None))


def test_check_batch_caps_the_number_of_files() -> None:
    with pytest.raises(InvalidParameterError, match="Too many files"):
        check_batch([_upload(b"x") for _ in range(UPLOAD_BATCH_MAX_FILES + 1)])

    check_batch([_upload(b"x") for _ in range(UPLOAD_BATCH_MAX_FILES)])


# --- upload_reader ------------------------------------------------------------


def test_upload_reader_returns_the_whole_file_from_the_start_every_time() -> None:
    upload = _upload(b"abcdef")
    read = upload_reader(upload)
    upload.file.read(3)  # someone moved the cursor

    assert read() == b"abcdef"
    assert read() == b"abcdef"


def test_upload_reader_enforces_the_cap_when_the_size_was_unknown() -> None:
    save_app_settings({"max_image_size_mb": 1})
    read = upload_reader(_upload(b"x" * (MIB + 1), size=None))

    with pytest.raises(PayloadTooLargeError):
        read()


# --- request_body_limit -------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    ["/api/upload", "/api/stack/abc/upload-frame", "/api/stack/abc/upload-archive"],
)
def test_single_file_routes_allow_one_file_plus_the_multipart_framing(path: str) -> None:
    save_app_settings({"max_image_size_mb": 10})

    assert request_body_limit("POST", path) == 10 * MIB + MULTIPART_OVERHEAD_BYTES


@pytest.mark.parametrize(
    "path", ["/api/stack/abc/upload-frames", "/api/stack/abc/calibration/dark/frames"]
)
def test_batch_routes_allow_a_full_batch(path: str) -> None:
    save_app_settings({"max_image_size_mb": 10})

    assert (
        request_body_limit("POST", path)
        == 10 * MIB * UPLOAD_BATCH_MAX_FILES + MULTIPART_OVERHEAD_BYTES
    )


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/upload"),
        ("POST", "/api/process/abc"),
        ("POST", "/api/stack/abc/upload-frames/extra"),
        ("POST", "/api/admin/config-import"),
    ],
)
def test_other_requests_have_no_upload_limit(method: str, path: str) -> None:
    assert request_body_limit(method, path) is None


# --- the middleware and the routes --------------------------------------------


def test_an_upload_declared_over_the_cap_is_refused_before_it_is_read(client) -> None:
    """The app answers 413 from the Content-Length alone, in the usual envelope."""
    save_app_settings({"max_image_size_mb": 1})

    response = client.post(
        "/api/upload",
        content=b"x" * (MIB + MULTIPART_OVERHEAD_BYTES + 1),
        headers={"Content-Type": "multipart/form-data; boundary=x"},
    )

    assert response.status_code == 413
    assert response.json()["error_code"] == "PAYLOAD_TOO_LARGE"


def test_a_batch_over_the_file_count_is_refused(client, star_field: np.ndarray) -> None:
    stack_id = client.post("/api/stack/initiate", json={"frame_count": 2}).json()["stack_id"]
    frame = png_bytes(star_field)
    files = [
        ("files", (f"f{i}.png", frame, "image/png")) for i in range(UPLOAD_BATCH_MAX_FILES + 1)
    ]

    response = client.post(
        f"/api/stack/{stack_id}/upload-frames", data={"start_index": "0"}, files=files
    )

    assert response.status_code == 400


def test_an_archive_member_declared_over_the_cap_is_refused_unread(
    client, star_field: np.ndarray
) -> None:
    """A compressed archive can hide a huge member: its declared size is checked first."""
    stack_id = client.post("/api/stack/initiate", json={"frame_count": 2}).json()["stack_id"]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("bomb.png", b"\0" * (2 * MIB))  # compresses to a few KB
    save_app_settings({"max_image_size_mb": 1})

    response = client.post(
        f"/api/stack/{stack_id}/upload-archive",
        files={"file": ("frames.zip", buffer.getvalue(), "application/zip")},
    )

    assert response.status_code == 413
