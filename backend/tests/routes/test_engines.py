"""Engine package routes: stage, install, discard, remove - and the admin gate."""

from __future__ import annotations

import pytest

from app.models.engines import EngineStatus
from app.services import engine_install, engine_probe
from tests.services.test_engine_install import LICENSE, X86_64, package_files, zip_archive


@pytest.fixture(autouse=True)
def _fake_host_and_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    status = EngineStatus(
        configured=True, found=True, version="2.6.1", known_good=True, detail="StarNet2 2.6.1"
    )
    monkeypatch.setattr(engine_install, "host_elf_machine", lambda: X86_64)
    monkeypatch.setattr(engine_install, "probe_engine", lambda *_a, **_k: status)
    monkeypatch.setattr(
        engine_probe,
        "probe_engine",
        lambda path, *_a, **_k: (
            status if path else EngineStatus(configured=False, found=False, detail="No path")
        ),
    )
    engine_probe.clear_engine_probe_cache()


def _stage(client, engine: str = "starnet2"):
    return client.post(
        f"/api/admin/engines/{engine}/stage",
        files={
            "file": (
                "starnet2-linux.zip",
                zip_archive(package_files()).getvalue(),
                "application/zip",
            )
        },
    )


def test_stage_then_install_then_status_then_remove(admin_client) -> None:
    staged = _stage(admin_client)
    assert staged.status_code == 201
    body = staged.json()
    assert body["license_text"] == LICENSE
    assert body["status"]["version"] == "2.6.1"

    installed = admin_client.post(
        "/api/admin/engines/starnet2/install",
        json={"staging_id": body["staging_id"], "accept_license": True},
    )
    assert installed.status_code == 200
    assert installed.json()["installed"]["archive_name"] == "starnet2-linux.zip"

    status = admin_client.get("/api/admin/engine-status").json()
    assert status["starnet2"]["installed"]["version"] == "2.6.1"
    assert status["deepsnr"]["installed"] is None
    assert admin_client.get("/api/config").json()["starless_engines"] == ["classic", "starnet2"]

    assert admin_client.delete("/api/admin/engines/starnet2").status_code == 204
    assert admin_client.get("/api/admin/engine-status").json()["starnet2"]["installed"] is None


def test_install_without_accepting_the_licence_is_refused(admin_client) -> None:
    staging_id = _stage(admin_client).json()["staging_id"]

    response = admin_client.post(
        "/api/admin/engines/starnet2/install", json={"staging_id": staging_id}
    )

    assert response.status_code == 400


def test_discard_a_staged_package(admin_client) -> None:
    staging_id = _stage(admin_client).json()["staging_id"]

    assert admin_client.delete(f"/api/admin/engines/starnet2/stage/{staging_id}").status_code == 204
    response = admin_client.post(
        "/api/admin/engines/starnet2/install",
        json={"staging_id": staging_id, "accept_license": True},
    )
    assert response.status_code == 404


def test_a_bad_archive_is_a_400_with_its_reason(admin_client) -> None:
    response = admin_client.post(
        "/api/admin/engines/starnet2/stage",
        files={"file": ("x.zip", b"not an archive", "application/zip")},
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "INVALID_ENGINE_ARCHIVE"


def test_an_archive_over_the_cap_is_refused(admin_client, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.routes import engines as engines_route

    monkeypatch.setattr(engines_route, "ENGINE_ARCHIVE_MAX_BYTES", 10)

    assert _stage(admin_client).status_code == 413


def test_unknown_engine_is_404(admin_client) -> None:
    assert _stage(admin_client, "photoshop").status_code == 404
    assert admin_client.delete("/api/admin/engines/photoshop").status_code == 404


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api/admin/engines/starnet2/stage"),
        ("post", "/api/admin/engines/starnet2/install"),
        ("delete", "/api/admin/engines/starnet2"),
        ("delete", "/api/admin/engines/starnet2/stage/abc"),
    ],
)
def test_engine_routes_need_the_admin(admin_client, method: str, path: str) -> None:
    """Installing an engine runs a binary on the server: never without the admin."""
    admin_client.cookies.clear()

    response = getattr(admin_client, method)(path)

    assert response.status_code == 401
