"""Input validation helpers."""

from __future__ import annotations

import uuid

import pytest

from app.exceptions import PayloadTooLargeError, UnsupportedImageError
from app.utils.validators import (
    is_valid_session_id,
    validate_image_extension,
    validate_upload_size,
)


def test_valid_session_id_accepts_uuid() -> None:
    """A canonical UUID string is accepted."""
    assert is_valid_session_id(str(uuid.uuid4()))


@pytest.mark.parametrize("bad", ["", "not-a-uuid", "../etc/passwd", "1234"])
def test_valid_session_id_rejects_junk(bad: str) -> None:
    """Malformed or path-like ids are rejected."""
    assert not is_valid_session_id(bad)


def test_validate_image_extension_rejects_unsupported() -> None:
    """A .bmp upload is rejected; a .jpg upload returns its extension."""
    assert validate_image_extension("photo.JPG") == ".jpg"
    with pytest.raises(UnsupportedImageError, match="not supported"):
        validate_image_extension("photo.bmp")


def test_validate_image_extension_allows_missing_extension() -> None:
    """A filename with no extension is allowed (content is sniffed on decode)."""
    assert validate_image_extension("clipboard") == ""


def test_validate_upload_size_enforces_limit() -> None:
    """An oversized upload raises PayloadTooLargeError."""
    with pytest.raises(PayloadTooLargeError, match="exceeds"):
        validate_upload_size(500 * 1024 * 1024)
