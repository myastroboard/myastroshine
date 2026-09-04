"""Per-IP rate limiting: the in-memory window counter and its FastAPI dependency."""

from __future__ import annotations

from typing import cast

import pytest
from fastapi import Request

from app.exceptions import RateLimitedError
from app.utils import app_settings
from app.utils.rate_limit import (
    InMemoryRateLimiter,
    _request_limiter,
    enforce_request_rate_limit,
    get_client_ip,
)


class _FakeClient:
    def __init__(self, host: str | None) -> None:
        self.host = host


class _FakeRequest:
    def __init__(self, host: str | None) -> None:
        self.client = _FakeClient(host) if host is not None else None


def _fake_request(host: str | None) -> Request:
    """A minimal stand-in for Starlette's ``Request`` - the code under test only
    reads ``.client.host``, so a full ASGI scope isn't needed."""
    return cast(Request, _FakeRequest(host))


class _NotTestEnv:
    """Stands in for ``get_settings()`` with ``is_test=False`` (real enforcement)."""

    is_test = False


def test_get_client_ip_reads_the_connecting_socket() -> None:
    assert get_client_ip(_fake_request("203.0.113.5")) == "203.0.113.5"


def test_get_client_ip_handles_missing_client() -> None:
    assert get_client_ip(_fake_request(None)) is None


def test_limiter_allows_up_to_the_limit() -> None:
    limiter = InMemoryRateLimiter()
    for _ in range(10):
        limiter.check("1.2.3.4", limit=10)  # must not raise


def test_limiter_raises_once_the_limit_is_exceeded() -> None:
    limiter = InMemoryRateLimiter()
    for _ in range(10):
        limiter.check("1.2.3.4", limit=10)
    with pytest.raises(RateLimitedError):
        limiter.check("1.2.3.4", limit=10)


def test_limiter_tracks_keys_independently() -> None:
    limiter = InMemoryRateLimiter()
    for _ in range(10):
        limiter.check("1.2.3.4", limit=10)
    limiter.check("5.6.7.8", limit=10)  # a different IP has its own budget


def test_limiter_resets_after_the_window_elapses(monkeypatch: pytest.MonkeyPatch) -> None:
    limiter = InMemoryRateLimiter(window_seconds=60)
    clock = [1_000_000.0]
    monkeypatch.setattr("app.utils.rate_limit.time.time", lambda: clock[0])

    for _ in range(10):
        limiter.check("1.2.3.4", limit=10)
    with pytest.raises(RateLimitedError):
        limiter.check("1.2.3.4", limit=10)

    clock[0] += 61  # next window
    limiter.check("1.2.3.4", limit=10)  # must not raise


def test_enforce_dependency_is_a_noop_under_app_env_test() -> None:
    """The default test env bypasses enforcement so the suite doesn't need to
    special-case every route that hits a rate-limited endpoint."""
    app_settings.save_app_settings({"rate_limit_per_minute": 1})
    request = _fake_request("1.2.3.4")
    for _ in range(5):
        enforce_request_rate_limit(request)  # must not raise


def test_enforce_dependency_respects_the_disabled_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.utils.rate_limit.get_settings", _NotTestEnv)
    app_settings.save_app_settings({"rate_limit_enabled": False, "rate_limit_per_minute": 1})
    request = _fake_request("1.2.3.4")
    for _ in range(5):
        enforce_request_rate_limit(request)  # must not raise


def test_enforce_dependency_raises_once_over_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.utils.rate_limit.get_settings", _NotTestEnv)
    app_settings.save_app_settings({"rate_limit_enabled": True, "rate_limit_per_minute": 2})
    request = _fake_request("9.9.9.9")
    _request_limiter._counts.pop("9.9.9.9", None)  # the limiter is a module-wide singleton

    try:
        enforce_request_rate_limit(request)
        enforce_request_rate_limit(request)
        with pytest.raises(RateLimitedError):
            enforce_request_rate_limit(request)
    finally:
        _request_limiter._counts.pop("9.9.9.9", None)
