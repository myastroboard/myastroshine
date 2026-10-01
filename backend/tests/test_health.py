"""Health endpoint contract."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.routes.health import _database_status


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


def test_health_has_no_redis_field(client) -> None:
    """Jobs run in-process: there is no queue backend to report on."""
    assert "redis" not in client.get("/api/health").json()


def test_database_status_reports_unreachable_when_the_query_raises() -> None:
    db = MagicMock()
    db.execute.side_effect = RuntimeError("connection refused")
    assert _database_status(db) == "unreachable"
