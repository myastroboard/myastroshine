"""SessionService lifecycle."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.db.models import SessionRecord
from app.exceptions import SessionExpiredError, SessionNotFoundError
from app.services.session import SessionService


def test_create_and_get_session(db_session) -> None:
    """A created session round-trips by id."""
    service = SessionService(db_session)
    record = service.create_session(image_path="/x/original.jpg", original_filename="m31.jpg")

    loaded = service.get_session(record.session_id)
    assert loaded.session_id == record.session_id
    assert loaded.original_filename == "m31.jpg"


def test_get_missing_session_raises(db_session) -> None:
    """An unknown id raises SessionNotFoundError."""
    service = SessionService(db_session)
    with pytest.raises(SessionNotFoundError):
        service.get_session("11111111-1111-1111-1111-111111111111")


def test_get_expired_session_raises(db_session) -> None:
    """A session past its expiry raises SessionExpiredError."""
    service = SessionService(db_session)
    record = service.create_session(image_path="/x")
    record.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db_session.commit()

    with pytest.raises(SessionExpiredError):
        service.get_session(record.session_id)


def test_update_parameters_persists(db_session) -> None:
    """update_parameters stores the dict on the row."""
    service = SessionService(db_session)
    record = service.create_session(image_path="/x")
    service.update_parameters(record.session_id, {"contrast": 1.5})

    assert service.get_session(record.session_id).parameters == {"contrast": 1.5}


def test_cleanup_removes_expired(db_session) -> None:
    """cleanup_old_sessions deletes only the expired rows and returns the count."""
    service = SessionService(db_session)
    live = service.create_session(image_path="/live")
    dead = service.create_session(image_path="/dead")
    dead.expires_at = datetime.now(UTC) - timedelta(hours=1)
    db_session.commit()

    removed = service.cleanup_old_sessions()

    assert removed == 1
    assert db_session.get(SessionRecord, live.session_id) is not None
    assert db_session.get(SessionRecord, dead.session_id) is None
