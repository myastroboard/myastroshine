"""Domain exceptions.

Services raise these; ``app.main`` translates them into the API error envelope
documented in docs/API.md. Routes should not build error responses by hand.
"""

from __future__ import annotations

from app.types import JsonDict


class AppError(Exception):
    """Base class for expected, client-facing errors."""

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, *, details: JsonDict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class SessionNotFoundError(AppError):
    status_code = 404
    error_code = "SESSION_NOT_FOUND"


class SessionExpiredError(AppError):
    status_code = 410
    error_code = "SESSION_EXPIRED"


class UnsupportedImageError(AppError):
    status_code = 415
    error_code = "UNSUPPORTED_FORMAT"


class InvalidParameterError(AppError):
    status_code = 400
    error_code = "INVALID_PARAMETER"


class PayloadTooLargeError(AppError):
    status_code = 400
    error_code = "PAYLOAD_TOO_LARGE"


class ImageProcessingError(AppError):
    status_code = 500
    error_code = "PROCESSING_FAILED"
