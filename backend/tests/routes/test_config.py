"""Public client-config route."""

from __future__ import annotations


def test_config_reports_the_upload_and_stacking_limits(client) -> None:
    response = client.get("/api/config")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "max_image_size_mb": 100,
        "stacking_enabled": True,
        "stacking_max_frames": 500,
    }


def test_config_tracks_a_settings_change(client) -> None:
    current = client.get("/api/admin/app-settings").json()
    current["max_image_size_mb"] = 250
    client.post("/api/admin/app-settings", json=current)

    assert client.get("/api/config").json()["max_image_size_mb"] == 250


def test_config_needs_no_admin(client, monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_ENABLED", "false")

    assert client.get("/api/config").status_code == 200
