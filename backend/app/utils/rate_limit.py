"""Per-IP request rate limiting (release-hardening backlog item #2).

A single ``api`` process is the deployment target for now (mono-poste, see
ALIGNMENT.md #1), so a plain in-memory fixed-window counter is enough - no
Redis or other shared store needed. If ``api`` is ever scaled to multiple
replicas this has to move to a shared backend, since each replica would
otherwise track its own count.

The companion "5 concurrent processing jobs per IP" limit (also in the API
spec) is not handled here: it is a concurrency check, not a request-rate
check, and lives in ``JobService.assert_under_concurrency_limit`` where it can
query the shared ``jobs`` table (correct across the sync and Celery-queue
processing modes, and across multiple ``api`` replicas, without any extra
bookkeeping).
"""

from __future__ import annotations

import threading
import time

from fastapi import Request

from app.config import get_settings
from app.exceptions import RateLimitedError
from app.utils.app_settings import get_app_settings

_WINDOW_SECONDS = 60


class InMemoryRateLimiter:
    """Fixed-window request counter keyed by an arbitrary string (typically an IP)."""

    def __init__(self, window_seconds: int = _WINDOW_SECONDS) -> None:
        self._window_seconds = window_seconds
        self._lock = threading.Lock()
        self._counts: dict[str, tuple[int, int]] = {}  # key -> (window_index, count)

    def check(self, key: str, limit: int) -> None:
        """Raise :class:`RateLimitedError` once ``key`` exceeds ``limit`` in the current window."""
        window = int(time.time() // self._window_seconds)
        with self._lock:
            self._prune(window)
            window_index, count = self._counts.get(key, (window, 0))
            if window_index != window:
                window_index, count = window, 0
            count += 1
            self._counts[key] = (window_index, count)
            if count > limit:
                raise RateLimitedError(
                    "Too many requests, please slow down",
                    details={"limit_per_minute": limit},
                )

    def _prune(self, current_window: int) -> None:
        """Drop entries from past windows so memory does not grow unbounded."""
        stale = [
            key
            for key, (window_index, _count) in self._counts.items()
            if window_index < current_window
        ]
        for key in stale:
            del self._counts[key]


_request_limiter = InMemoryRateLimiter()


def get_client_ip(request: Request) -> str | None:
    """The connecting socket's address; ``None`` if the ASGI server didn't set one."""
    return request.client.host if request.client else None


def enforce_request_rate_limit(request: Request) -> None:
    """FastAPI dependency: 429s once an IP exceeds the configured per-minute limit.

    Wired onto the upload/process/stack routes (see docs/API.md "Rate
    Limiting"). A no-op under ``APP_ENV=test`` so the test suite - which
    routinely fires far more than the default 10 req/min from one client -
    doesn't need to special-case every route it exercises.
    """
    if get_settings().is_test:
        return
    settings = get_app_settings()
    if not settings.rate_limit_enabled:
        return
    ip = get_client_ip(request)
    if ip is None:
        return
    _request_limiter.check(ip, settings.rate_limit_per_minute)
