"""Input validation helpers."""

from __future__ import annotations

import uuid

import pytest

from app.exceptions import PayloadTooLargeError, UnsupportedImageError
from app.utils.app_settings import save_app_settings
from app.utils.validators import (
    is_allowed_callback_url,
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


@pytest.mark.parametrize(
    "filename",
    ["frame.fits", "frame.FIT", "frame.fts", "photo.cr2", "photo.NEF", "photo.dng"],
)
def test_validate_image_extension_allows_fits_and_raw(filename: str) -> None:
    """FITS and camera RAW extensions are accepted (see image_utils.decode_image)."""
    validate_image_extension(filename)


def test_validate_upload_size_enforces_limit() -> None:
    """An oversized upload raises PayloadTooLargeError."""
    with pytest.raises(PayloadTooLargeError, match="exceeds"):
        validate_upload_size(500 * 1024 * 1024)


def test_is_allowed_callback_url_fails_closed_when_allowlist_empty() -> None:
    """An empty allowlist allows nothing - it must be configured explicitly."""
    save_app_settings({"astrodex_callback_urls": []})
    assert not is_allowed_callback_url("http://anything.test/webhook")


def test_is_allowed_callback_url_matches_configured_prefix() -> None:
    save_app_settings({"astrodex_callback_urls": ["http://astrodex.test/"]})
    assert is_allowed_callback_url("http://astrodex.test/api/webhooks/enhanced-images")
    assert not is_allowed_callback_url("http://evil.test/x")
