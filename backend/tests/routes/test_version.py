"""Version and update-check routes."""

from __future__ import annotations

import httpx

import app.main as main_module
from app import __version__
from app.dependencies import get_version_check_service
from app.services.version_check import VersionCheckService


def _override_version_check(handler) -> None:
    main_module.app.dependency_overrides[get_version_check_service] = lambda: VersionCheckService(
        transport=httpx.MockTransport(handler)
    )


def test_read_version_reports_the_running_version(client) -> None:
    response = client.get("/api/version")

    assert response.status_code == 200
    assert response.json() == {"version": __version__}


def test_check_updates_reports_an_available_update(client) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "tag_name": "v999.0.0",
                "html_url": "https://github.com/myastroboard/myastroshine/releases/tag/v999.0.0",
                "name": "Release v999.0.0",
                "body": "### Added\n- Something new.",
                "published_at": "2026-09-05T00:00:00Z",
            },
        )

    _override_version_check(handler)

    response = client.get("/api/version/check-updates")

    assert response.status_code == 200
    body = response.json()
    assert body["current_version"] == __version__
    assert body["latest_version"] == "999.0.0"
    assert body["update_available"] is True
    assert body["release_notes"] == "### Added\n- Something new."


def test_check_updates_never_5xxs_on_a_github_outage(client) -> None:
    _override_version_check(lambda _r: httpx.Response(503))

    response = client.get("/api/version/check-updates")

    assert response.status_code == 200
    body = response.json()
    assert body["update_available"] is False
    assert body["error"] == "Request failed"
