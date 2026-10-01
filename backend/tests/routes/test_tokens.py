"""Webhook token routes."""

from __future__ import annotations

import pytest

from app.config import get_settings


def test_create_lists_and_revoke(admin_client) -> None:
    """A created token appears in the listing and can be revoked."""
    created = admin_client.post("/api/tokens", json={"name": "AstroDex prod"})
    assert created.status_code == 201
    body = created.json()
    assert body["token"].startswith("mas_")
    assert body["signing_secret"]
    token_id = body["id"]

    listing = admin_client.get("/api/tokens").json()
    assert listing["total"] == 1
    entry = listing["tokens"][0]
    assert entry["name"] == "AstroDex prod"
    assert "token" not in entry  # secret material is never listed
    assert "signing_secret" not in entry

    assert admin_client.delete(f"/api/tokens/{token_id}").status_code == 204
    assert admin_client.get("/api/tokens").json()["tokens"][0]["revoked"] is True


def test_create_rejects_blank_name(admin_client) -> None:
    assert admin_client.post("/api/tokens", json={"name": ""}).status_code == 400


def test_revoke_unknown_is_404(admin_client) -> None:
    assert admin_client.delete("/api/tokens/does-not-exist").status_code == 404


def test_expiry_is_returned(admin_client) -> None:
    created = admin_client.post("/api/tokens", json={"name": "temp", "expires_in_days": 30}).json()
    assert created["expires_at"] is not None


def test_all_routes_403_when_admin_disabled(admin_client, monkeypatch: pytest.MonkeyPatch) -> None:
    """Minting/listing/revoking a webhook token is an admin action, same as
    the app-settings routes - it must respect ADMIN_ENABLED too."""
    created = admin_client.post("/api/tokens", json={"name": "before disabling"}).json()

    monkeypatch.setenv("ADMIN_ENABLED", "false")
    get_settings.cache_clear()

    assert admin_client.get("/api/tokens").status_code == 403
    assert admin_client.post("/api/tokens", json={"name": "should fail"}).status_code == 403
    assert admin_client.delete(f"/api/tokens/{created['id']}").status_code == 403

    get_settings.cache_clear()
