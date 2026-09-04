"""Webhook token routes."""

from __future__ import annotations


def test_create_lists_and_revoke(client) -> None:
    """A created token appears in the listing and can be revoked."""
    created = client.post("/api/tokens", json={"name": "AstroDex prod"})
    assert created.status_code == 201
    body = created.json()
    assert body["token"].startswith("mas_")
    assert body["signing_secret"]
    token_id = body["id"]

    listing = client.get("/api/tokens").json()
    assert listing["total"] == 1
    entry = listing["tokens"][0]
    assert entry["name"] == "AstroDex prod"
    assert "token" not in entry  # secret material is never listed
    assert "signing_secret" not in entry

    assert client.delete(f"/api/tokens/{token_id}").status_code == 204
    assert client.get("/api/tokens").json()["tokens"][0]["revoked"] is True


def test_create_rejects_blank_name(client) -> None:
    assert client.post("/api/tokens", json={"name": ""}).status_code == 400


def test_revoke_unknown_is_404(client) -> None:
    assert client.delete("/api/tokens/does-not-exist").status_code == 404


def test_expiry_is_returned(client) -> None:
    created = client.post("/api/tokens", json={"name": "temp", "expires_in_days": 30}).json()
    assert created["expires_at"] is not None
