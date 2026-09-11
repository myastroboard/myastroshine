"""Direct unit tests for the app.dependencies factory functions.

Most routes exercise these factories indirectly through FastAPI's real
dependency injection via the `client` fixture, but a couple are always
overridden in their own route tests (e.g. get_astrodex_handoff_service in
tests/routes/test_astrodex.py, to inject a fake service) so their actual
bodies never run - these call them directly instead.
"""

from __future__ import annotations

import pytest

from app.dependencies import (
    get_astrodex_handoff_service,
    get_version_check_service,
    require_token,
)
from app.exceptions import UnauthorizedError
from app.services.astrodex_handoff import AstroDexHandoffService
from app.services.session import SessionService
from app.services.storage import StorageService
from app.services.version_check import VersionCheckService


def test_require_token_without_credentials_is_unauthorized() -> None:
    with pytest.raises(UnauthorizedError, match="Missing webhook token"):
        require_token(tokens=None, credentials=None)  # type: ignore[arg-type]


def test_get_astrodex_handoff_service_builds_a_real_service(db_session: object) -> None:
    storage = StorageService()
    sessions = SessionService(db_session, storage)  # type: ignore[arg-type]

    service = get_astrodex_handoff_service(db_session, sessions, storage)  # type: ignore[arg-type]

    assert isinstance(service, AstroDexHandoffService)


def test_get_version_check_service_returns_the_shared_singleton() -> None:
    first = get_version_check_service()
    second = get_version_check_service()

    assert isinstance(first, VersionCheckService)
    assert first is second
