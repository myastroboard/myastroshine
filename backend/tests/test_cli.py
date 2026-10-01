"""The operator CLI (``python -m app.cli``)."""

from __future__ import annotations

import pytest

from app import cli
from app.db import database
from app.services.admin_auth import AdminAuthService


def test_reset_admin_clears_the_password_and_sessions(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``reset-admin`` brings the install back to the setup screen."""
    # The client fixture already built the schema on the test engine and points
    # SessionLocal at it; the real init_db would open the module-level engine.
    monkeypatch.setattr(cli, "init_db", lambda: None)
    assert (
        client.post("/api/auth/setup", json={"password": "a long enough password"}).status_code
        == 204
    )

    assert cli.main(["reset-admin"]) == 0

    with database.SessionLocal() as db:
        auth = AdminAuthService(db)
        assert not auth.is_configured()
        assert auth.list_sessions() == []
    assert client.get("/api/auth/status").json()["configured"] is False


def test_cli_without_a_command_exits_with_usage() -> None:
    with pytest.raises(SystemExit) as info:
        cli.main([])

    assert info.value.code == 2
