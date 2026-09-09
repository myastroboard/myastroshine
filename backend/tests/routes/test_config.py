"""Public client-config route."""

from __future__ import annotations


def test_config_reports_the_upload_and_stacking_limits(client) -> None:
    response = client.get("/api/config")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "max_image_size_mb": 100,
        "stacking_enabled": True,
        "stacking_max_frames": 2000,
        "starless_engines": ["classic"],
        "denoise_engines": ["classic"],
    }


def test_config_tracks_a_settings_change(client) -> None:
    current = client.get("/api/admin/app-settings").json()
    current["max_image_size_mb"] = 250
    client.post("/api/admin/app-settings", json=current)

    assert client.get("/api/config").json()["max_image_size_mb"] == 250


def test_config_needs_no_admin(client, monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_ENABLED", "false")

    assert client.get("/api/config").status_code == 200


def test_config_lists_an_external_engine_only_when_it_is_available(client, monkeypatch) -> None:
    from app.models.engines import EngineStatus
    from app.routes import config as config_route

    monkeypatch.setattr(
        config_route,
        "get_engine_statuses",
        lambda: {
            "starnet2": EngineStatus(
                configured=True, found=True, version="2.6.1", known_good=True, detail="ok"
            ),
            "deepsnr": EngineStatus(configured=False, found=False, detail="No path configured"),
        },
    )

    body = client.get("/api/config").json()
    assert body["starless_engines"] == ["classic", "starnet2"]
    assert body["denoise_engines"] == ["classic"]
