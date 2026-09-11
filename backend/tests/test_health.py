"""Health endpoint contract."""

from __future__ import annotations

import pytest


def test_health_returns_ok(client) -> None:
    """GET /api/health reports a healthy status, DB connectivity, and disk usage."""
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["version"]
    assert body["database"] == "connected"
    assert "timestamp" in body
    assert body["disk"]["total_bytes"] > 0
    assert body["disk"]["free_bytes"] >= 0


def test_health_reports_redis_not_applicable_in_sync_mode(client) -> None:
    """sync mode (the default, and what tests use) never touches Redis at all."""
    response = client.get("/api/health")
    assert response.json()["redis"] == "not_applicable"


def test_health_reports_redis_unreachable_in_queue_mode(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PROCESSING_MODE", "queue")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")  # nothing listens here
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        response = client.get("/api/health")
        assert response.json()["redis"] == "unreachable"
    finally:
        get_settings.cache_clear()
