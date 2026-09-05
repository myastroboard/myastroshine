"""VersionCheckService: cached, never-raising GitHub release lookups."""

from __future__ import annotations

import httpx
import pytest

from app import __version__
from app.services.version_check import VersionCheckService, _is_newer


def _release_response(tag: str, **overrides: object) -> httpx.Response:
    body = {
        "tag_name": tag,
        "html_url": f"https://github.com/myastroboard/myastroshine/releases/tag/{tag}",
        "name": f"Release {tag}",
        "body": "### Added\n- Something new.",
        "published_at": "2026-09-05T00:00:00Z",
        **overrides,
    }
    return httpx.Response(200, json=body)


def test_is_newer_compares_semantic_versions() -> None:
    assert _is_newer("1.2.0", "1.1.9")
    assert not _is_newer("1.1.0", "1.1.0")
    assert not _is_newer("1.0.9", "1.1.0")


def test_is_newer_ignores_a_leading_v() -> None:
    assert _is_newer("v2.0.0", "1.0.0")


def test_is_newer_returns_false_for_unparseable_input() -> None:
    assert not _is_newer("not-a-version", "1.0.0")


@pytest.mark.asyncio
async def test_check_for_updates_reports_available_update() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["accept"] == "application/vnd.github+json"
        return _release_response("v999.0.0")

    service = VersionCheckService(transport=httpx.MockTransport(handler))
    result = await service.check_for_updates()

    assert result == {
        "current_version": __version__,
        "latest_version": "999.0.0",
        "update_available": True,
        "release_url": "https://github.com/myastroboard/myastroshine/releases/tag/v999.0.0",
        "release_name": "Release v999.0.0",
        "release_notes": "### Added\n- Something new.",
        "published_at": "2026-09-05T00:00:00Z",
        "error": None,
    }


@pytest.mark.asyncio
async def test_check_for_updates_reports_no_update_when_already_current() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return _release_response(f"v{__version__}")

    service = VersionCheckService(transport=httpx.MockTransport(handler))
    result = await service.check_for_updates()

    assert result["update_available"] is False


@pytest.mark.asyncio
async def test_check_for_updates_caches_and_does_not_refetch() -> None:
    """A second call within the TTL never hits the transport again."""
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return _release_response("v999.0.0")

    service = VersionCheckService(transport=httpx.MockTransport(handler))
    first = await service.check_for_updates()
    second = await service.check_for_updates()

    assert calls["n"] == 1
    assert first == second


@pytest.mark.asyncio
async def test_check_for_updates_handles_404() -> None:
    service = VersionCheckService(transport=httpx.MockTransport(lambda _r: httpx.Response(404)))
    result = await service.check_for_updates()

    assert result["update_available"] is False
    assert result["error"] == "Repository not found"


@pytest.mark.asyncio
async def test_check_for_updates_handles_github_rate_limit() -> None:
    service = VersionCheckService(transport=httpx.MockTransport(lambda _r: httpx.Response(403)))
    result = await service.check_for_updates()

    assert result["update_available"] is False
    assert result["error"] == "Rate limit exceeded"


@pytest.mark.asyncio
async def test_check_for_updates_handles_timeout() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out")

    service = VersionCheckService(transport=httpx.MockTransport(handler))
    result = await service.check_for_updates()

    assert result["update_available"] is False
    assert result["error"] == "Request timed out"


@pytest.mark.asyncio
async def test_check_for_updates_handles_a_connection_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    service = VersionCheckService(transport=httpx.MockTransport(handler))
    result = await service.check_for_updates()

    assert result["update_available"] is False
    assert result["error"] == "Request failed"


@pytest.mark.asyncio
async def test_a_transient_failure_is_only_cached_briefly() -> None:
    """A timeout doesn't suppress the check for the full success TTL - the next
    call after the short error window retries and can then succeed."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.TimeoutException("timed out")
        return _release_response("v999.0.0")

    service = VersionCheckService(transport=httpx.MockTransport(handler))
    first = await service.check_for_updates()
    assert first["error"] == "Request timed out"

    # jump past the short error TTL but well within the success TTL
    service._cached_at -= 10 * 60
    second = await service.check_for_updates()

    assert calls["n"] == 2
    assert second["error"] is None
    assert second["update_available"] is True


@pytest.mark.asyncio
async def test_check_for_updates_handles_malformed_response() -> None:
    service = VersionCheckService(
        transport=httpx.MockTransport(lambda _r: httpx.Response(200, json={"unexpected": True}))
    )
    result = await service.check_for_updates()

    assert result["update_available"] is False
    assert result["error"] == "Malformed response"
