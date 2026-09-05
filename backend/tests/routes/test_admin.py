"""Admin routes: runtime settings read/write and the log endpoints."""

from __future__ import annotations

import io
import zipfile

import pytest

from app.config import get_settings
from app.utils.app_settings import get_app_settings


def test_get_app_settings_returns_current_values(client) -> None:
    response = client.get("/api/admin/app-settings")

    assert response.status_code == 200
    body = response.json()
    assert body["stacking_detector"] == "orb"
    # conftest allow-lists this host
    assert body["astrodex_callback_urls"] == ["http://astrodex.test/api/webhooks/enhanced-images"]


def test_post_app_settings_persists_and_is_readable(client) -> None:
    current = client.get("/api/admin/app-settings").json()
    current["max_image_size_mb"] = 300
    current["stacking_enabled"] = False

    response = client.post("/api/admin/app-settings", json=current)

    assert response.status_code == 200
    assert response.json()["max_image_size_mb"] == 300
    assert client.get("/api/admin/app-settings").json()["stacking_enabled"] is False
    assert get_app_settings().max_image_size_mb == 300


def test_post_app_settings_validates_bounds(client) -> None:
    current = client.get("/api/admin/app-settings").json()
    current["max_image_size_mb"] = 0  # below the ge=1 bound

    response = client.post("/api/admin/app-settings", json=current)

    assert response.status_code == 400


def test_post_app_settings_403_when_admin_disabled(client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_ENABLED", "false")
    get_settings.cache_clear()
    body = client.get("/api/admin/app-settings").json()

    response = client.post("/api/admin/app-settings", json=body)

    assert response.status_code == 403
    get_settings.cache_clear()


def test_post_app_settings_rejects_cors_wildcard(client) -> None:
    current = client.get("/api/admin/app-settings").json()
    current["cors_origins"] = ["*"]

    response = client.post("/api/admin/app-settings", json=current)

    assert response.status_code == 400


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/admin/app-settings"),
        ("GET", "/api/admin/logs"),
        ("GET", "/api/admin/logs/level"),
        ("GET", "/api/admin/logs/export"),
    ],
)
def test_reads_403_when_admin_disabled(
    client, monkeypatch: pytest.MonkeyPatch, method: str, path: str
) -> None:
    """Reads used to be reachable regardless of ADMIN_ENABLED - they must be
    gated the same as the sibling write routes."""
    monkeypatch.setenv("ADMIN_ENABLED", "false")
    get_settings.cache_clear()

    response = client.request(method, path)

    assert response.status_code == 403
    get_settings.cache_clear()


# --- logs ---------------------------------------------------------------


def test_tail_logs_empty_when_no_file(client) -> None:
    response = client.get("/api/admin/logs")

    assert response.status_code == 200
    assert response.json() == {"lines": [], "returned": 0, "filtered_level": None}


def test_tail_logs_newest_first_with_level_filter(client) -> None:
    get_settings().log_file.write_text(
        "2026-09-04 10:00:00,000 +0000 - app.a - INFO [f:1] - first\n"
        "2026-09-04 10:00:01,000 +0000 - app.b - ERROR [g:2] - boom\n"
        "2026-09-04 10:00:02,000 +0000 - app.c - INFO [h:3] - third\n",
        encoding="utf-8",
        newline="",
    )

    all_lines = client.get("/api/admin/logs").json()["lines"]
    assert all_lines[0].endswith("third")  # newest first

    errors = client.get("/api/admin/logs", params={"level": "error"}).json()
    assert errors["returned"] == 1
    assert "boom" in errors["lines"][0]


def test_log_level_roundtrip_persists_and_applies(client) -> None:
    assert client.get("/api/admin/logs/level").json() == {"file": "info", "console": "warning"}

    response = client.post("/api/admin/logs/level", json={"file": "debug"})

    assert response.status_code == 200
    assert response.json()["file"] == "debug"
    assert get_app_settings().log_level == "debug"


def test_log_level_rejects_unknown_level(client) -> None:
    assert client.post("/api/admin/logs/level", json={"console": "loud"}).status_code == 400


def test_clear_logs_truncates_the_file(client) -> None:
    get_settings().log_file.write_text("noise\n", encoding="utf-8", newline="")

    assert client.post("/api/admin/logs/clear").status_code == 204
    assert get_settings().log_file.read_text(encoding="utf-8") == ""


def test_export_logs_returns_a_zip_of_the_present_files(client) -> None:
    get_settings().log_file.write_bytes(b"main log\n")
    (get_settings().log_file.parent / "myastroshine.log.1").write_bytes(b"older\n")

    response = client.get("/api/admin/logs/export")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert set(archive.namelist()) == {"myastroshine.log", "myastroshine.log.1"}
        assert archive.read("myastroshine.log") == b"main log\n"
