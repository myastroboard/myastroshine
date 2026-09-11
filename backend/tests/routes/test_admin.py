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
    assert body["stacking_max_frames"] == 2000
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


def test_post_app_settings_rejects_an_odd_starnet2_stride(client) -> None:
    current = client.get("/api/admin/app-settings").json()
    current["starnet2_stride"] = 7

    assert client.post("/api/admin/app-settings", json=current).status_code == 400


def test_engine_status_reports_nothing_configured_by_default(client) -> None:
    response = client.get("/api/admin/engine-status")

    assert response.status_code == 200
    body = response.json()
    assert body["starnet2"] == {
        "configured": False,
        "found": False,
        "version": None,
        "known_good": False,
        "detail": "No path configured",
    }
    assert body["deepsnr"]["configured"] is False


def test_engine_status_probes_a_configured_path(client) -> None:
    current = client.get("/api/admin/app-settings").json()
    current["starnet2_path"] = "/nonexistent/starnet2"
    client.post("/api/admin/app-settings", json=current)

    body = client.get("/api/admin/engine-status").json()

    assert body["starnet2"]["configured"] is True
    assert body["starnet2"]["found"] is False
    assert "not found" in body["starnet2"]["detail"].lower()


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/admin/app-settings"),
        ("GET", "/api/admin/engine-status"),
        ("GET", "/api/admin/logs"),
        ("GET", "/api/admin/logs/level"),
        ("GET", "/api/admin/logs/export"),
        ("GET", "/api/admin/jobs"),
        ("GET", "/api/admin/disk-usage"),
        ("GET", "/api/admin/config-export"),
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


# --- operations -----------------------------------------------------------


def test_list_jobs_hides_superseded_by_default(client, db_session) -> None:
    from app.services.job import JobService

    jobs = JobService(db_session)
    kept = jobs.create("sess-1")
    superseded = jobs.create("sess-1")
    jobs.update(superseded.job_id, status="superseded")

    response = client.get("/api/admin/jobs")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert [j["job_id"] for j in body["jobs"]] == [kept.job_id]
    assert body["limit"] == 50
    assert body["offset"] == 0


def test_list_jobs_filters_by_status(client, db_session) -> None:
    from app.services.job import JobService

    jobs = JobService(db_session)
    failed = jobs.create("sess-1")
    jobs.update(failed.job_id, status="failed", error="boom")
    jobs.create("sess-2")

    response = client.get("/api/admin/jobs", params={"status": "failed"})

    body = response.json()
    assert body["total"] == 1
    assert body["jobs"][0]["error"] == "boom"


def test_disk_usage_reports_bytes(client) -> None:
    response = client.get("/api/admin/disk-usage")

    assert response.status_code == 200
    body = response.json()
    assert body["total_bytes"] > 0
    for key in ("images_bytes", "stacks_bytes", "db_bytes", "logs_bytes"):
        assert body[key] >= 0


# --- backup / restore -------------------------------------------------------


def test_config_export_includes_user_presets_but_not_builtins(client) -> None:
    client.post("/api/presets", json={"name": "My Andromeda", "parameters": {"contrast": 1.4}})

    response = client.get("/api/admin/config-export")

    assert response.status_code == 200
    body = response.json()
    assert body["format_version"] == 1
    names = {p["name"] for p in body["presets"]}
    assert names == {"My Andromeda"}  # the 5 built-ins are never included
    assert body["settings"]["stacking_max_frames"] == 2000


def test_config_import_applies_settings_and_creates_presets(client) -> None:
    exported = client.get("/api/admin/config-export").json()
    exported["settings"]["max_image_size_mb"] = 321
    exported["presets"] = [
        {"name": "Imported One", "category": "astronomy", "parameters": {"contrast": 1.2}}
    ]

    response = client.post("/api/admin/config-import", json=exported)

    assert response.status_code == 200
    body = response.json()
    assert body == {"presets_imported": 1, "presets_skipped": []}
    assert client.get("/api/admin/app-settings").json()["max_image_size_mb"] == 321
    names = {p["name"] for p in client.get("/api/presets").json()["presets"]}
    assert "Imported One" in names


def test_config_import_skips_presets_with_a_colliding_name(client) -> None:
    client.post("/api/presets", json={"name": "Mine", "parameters": {"contrast": 1.1}})
    exported = client.get("/api/admin/config-export").json()
    exported["presets"] = [{"name": "Mine", "parameters": {"contrast": 1.9}}]

    response = client.post("/api/admin/config-import", json=exported)

    assert response.status_code == 200
    assert response.json() == {"presets_imported": 0, "presets_skipped": ["Mine"]}
    # the existing preset is untouched, not overwritten
    listing = client.get("/api/presets").json()["presets"]
    mine = next(p for p in listing if p["name"] == "Mine")
    assert mine["parameters"]["contrast"] == 1.1


def test_config_import_rejects_a_future_format_version(client) -> None:
    exported = client.get("/api/admin/config-export").json()
    exported["format_version"] = 99

    response = client.post("/api/admin/config-import", json=exported)

    assert response.status_code == 400


def test_config_import_403_when_admin_disabled(client, monkeypatch: pytest.MonkeyPatch) -> None:
    exported = client.get("/api/admin/config-export").json()
    monkeypatch.setenv("ADMIN_ENABLED", "false")
    get_settings.cache_clear()

    response = client.post("/api/admin/config-import", json=exported)

    assert response.status_code == 403
    get_settings.cache_clear()
