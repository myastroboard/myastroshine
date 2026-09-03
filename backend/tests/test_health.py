"""Health endpoint contract."""

from __future__ import annotations


def test_health_returns_ok(client) -> None:
    """GET /api/health reports a healthy status and the app version."""
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["version"]
    assert "timestamp" in body
