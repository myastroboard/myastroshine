"""Checks GitHub for a newer myastroshine release.

Cached in-memory with a long TTL so a busy frontend can't hammer GitHub's API
(see ALIGNMENT.md #3). No disk-shared cache is needed the way
``app/utils/rate_limit.py`` would need one across replicas: the ``worker``
process never serves HTTP and so never calls this, and ``api`` itself is a
single process.
"""

from __future__ import annotations

import time

import httpx
from packaging.version import InvalidVersion, Version

from app import __version__
from app.constants import GITHUB_RELEASES_URL, VERSION_CHECK_CACHE_TTL_SECONDS
from app.logging_config import get_logger
from app.types import JsonDict

logger = get_logger(__name__)

# A failed lookup (timeout, transient network error, malformed body) is cached
# only briefly - long enough to absorb a burst of requests, short enough that a
# passing outage doesn't suppress the update notice for the full success TTL.
# A GitHub 403 rate-limit is the exception: retrying soon would just be rate
# limited again, so it keeps the full TTL.
_ERROR_CACHE_TTL_SECONDS = 5 * 60


def _is_newer(latest: str, current: str) -> bool:
    """True if ``latest`` parses as a strictly newer version than ``current``."""
    try:
        return Version(latest) > Version(current)
    except InvalidVersion:
        return False


class VersionCheckService:
    """Fetches, and caches, the latest GitHub release for this repository."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport
        self._cached_result: JsonDict | None = None
        self._cached_at = 0.0

    async def check_for_updates(self) -> JsonDict:
        """Return the cached result if still fresh, else query GitHub and cache it.

        Every failure path (timeout, rate limit, malformed response, ...) is
        caught and turned into a plain dict with a non-``None`` ``error`` -
        this never raises, so a GitHub outage can't break the editor.
        """
        now = time.monotonic()
        cache_age = now - self._cached_at
        if self._cached_result is not None and cache_age < self._cache_ttl(self._cached_result):
            return self._cached_result

        result = await self._fetch_latest_release()
        self._cached_result = result
        self._cached_at = now
        return result

    @staticmethod
    def _cache_ttl(result: JsonDict) -> float:
        """How long ``result`` stays cached: full TTL for a success (or a GitHub
        rate-limit, where retrying soon is pointless), a short retry window for
        any other transient failure."""
        error = result.get("error")
        if error is None or error == "Rate limit exceeded":
            return VERSION_CHECK_CACHE_TTL_SECONDS
        return _ERROR_CACHE_TTL_SECONDS

    async def _fetch_latest_release(self) -> JsonDict:
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=10.0) as client:
                response = await client.get(
                    GITHUB_RELEASES_URL, headers={"Accept": "application/vnd.github+json"}
                )
        except httpx.TimeoutException:
            logger.warning("version check timed out")
            return self._error_result("Request timed out")
        except httpx.RequestError as exc:
            logger.warning("version check request failed", error=str(exc))
            return self._error_result("Request failed")

        status_error = self._status_error(response)
        if status_error is not None:
            return self._error_result(status_error)

        try:
            payload = response.json()
            latest_version = str(payload["tag_name"]).lstrip("v")
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("version check response malformed", error=str(exc))
            return self._error_result("Malformed response")

        return {
            "current_version": __version__,
            "latest_version": latest_version,
            "update_available": _is_newer(latest_version, __version__),
            "release_url": payload.get("html_url"),
            "release_name": payload.get("name") or latest_version,
            "release_notes": payload.get("body") or "",
            "published_at": payload.get("published_at"),
            "error": None,
        }

    def _status_error(self, response: httpx.Response) -> str | None:
        """Return an error message for a non-2xx GitHub response, else ``None``."""
        if response.status_code == httpx.codes.NOT_FOUND:
            return "Repository not found"
        if response.status_code == httpx.codes.FORBIDDEN:
            logger.warning("version check rate limited by GitHub")
            return "Rate limit exceeded"
        if not response.is_success:
            logger.warning("version check unexpected status", status=response.status_code)
            return "Request failed"
        return None

    def _error_result(self, message: str) -> JsonDict:
        return {
            "current_version": __version__,
            "latest_version": None,
            "update_available": False,
            "release_url": None,
            "release_name": None,
            "release_notes": None,
            "published_at": None,
            "error": message,
        }
