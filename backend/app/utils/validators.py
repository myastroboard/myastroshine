"""Input validation and sanitization.

All external input (uploads, form fields, callback URLs, session ids) must pass
through here before it is used in a file path or a response.
"""

from __future__ import annotations

import re
import uuid

from app.exceptions import PayloadTooLargeError, UnsupportedImageError
from app.utils.app_settings import get_app_settings
from app.utils.image_utils import SUPPORTED_FORMATS

_SESSION_ID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")


def is_valid_session_id(session_id: str) -> bool:
    """True if ``session_id`` is a well-formed UUID string."""
    if not _SESSION_ID_RE.match(session_id):
        return False
    try:
        uuid.UUID(session_id)
    except ValueError:
        return False
    return True


def validate_upload_size(size_bytes: int) -> None:
    """Raise :class:`PayloadTooLargeError` if the upload exceeds the configured limit."""
    max_mb = get_app_settings().max_image_size_mb
    if size_bytes > max_mb * 1024 * 1024:
        raise PayloadTooLargeError(f"File size exceeds {max_mb}MB limit")


def validate_image_extension(filename: str) -> str:
    """Return the lowercased extension if supported, else raise :class:`UnsupportedImageError`.

    An empty extension is allowed (the content is sniffed on decode instead).
    """
    ext = filename[filename.rfind(".") :].lower() if "." in filename else ""
    if ext and ext not in SUPPORTED_FORMATS:
        raise UnsupportedImageError(f"Format {ext} not supported")
    return ext


def is_allowed_callback_url(url: str) -> bool:
    """True if ``url`` is on the AstroDex callback allowlist.

    An empty allowlist allows nothing (fail closed) - configure at least one
    entry in Settings before enabling AstroDex webhook delivery.
    """
    allowlist = get_app_settings().astrodex_callback_urls
    return bool(allowlist) and any(url.startswith(allowed) for allowed in allowlist)
