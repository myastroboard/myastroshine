"""Health endpoint contract."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.routes.health import _database_status, _redis_status


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


def test_database_status_reports_unreachable_when_the_query_raises() -> None:
    db = MagicMock()
    db.execute.side_effect = RuntimeError("connection refused")
    assert _database_status(db) == "unreachable"


def test_redis_status_reports_connected_when_the_ping_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROCESSING_MODE", "queue")
    from app.config import get_settings

    get_settings.cache_clear()
    fake_client = MagicMock()
    fake_client.ping.return_value = True
    monkeypatch.setattr("app.routes.health.redis.Redis.from_url", lambda *a, **k: fake_client)
    try:
        assert _redis_status() == "connected"
    finally:
        get_settings.cache_clear()
