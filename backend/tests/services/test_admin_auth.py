"""AdminAuthService: password hashing, setup, login, sessions, password changes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.db.models import AdminCredential, AdminSession
from app.exceptions import (
    AdminAlreadyConfiguredError,
    AdminLoginRequiredError,
    AdminSetupRequiredError,
    InvalidCredentialsError,
    ResourceNotFoundError,
)
from app.services import admin_auth
from app.services.admin_auth import (
    AdminAuthService,
    hash_password,
    needs_rehash,
    verify_password,
)
from app.utils.app_settings import save_app_settings

PASSWORD = "a long enough password"


@pytest.fixture
def auth(db_session) -> AdminAuthService:
    return AdminAuthService(db_session)


def _only_session(db_session) -> AdminSession:
    sessions = db_session.query(AdminSession).all()
    assert len(sessions) == 1
    return sessions[0]


# --- hashing ------------------------------------------------------------------


def test_hash_round_trips_and_rejects_a_wrong_password() -> None:
    """A hash verifies its own password and nothing else."""
    encoded = hash_password(PASSWORD)

    assert verify_password(PASSWORD, encoded)
    assert not verify_password(PASSWORD + "x", encoded)


def test_hash_is_salted_and_carries_its_parameters() -> None:
    """Two hashes of one password differ, and each records the scrypt cost it used,
    so a later cost increase does not break existing hashes."""
    first, second = hash_password(PASSWORD), hash_password(PASSWORD)

    assert first != second
    scheme, n, r, p, _salt, _key = first.split("$")
    assert (scheme, int(n), int(r), int(p)) == (
        "scrypt",
        admin_auth.SCRYPT.n,
        admin_auth.SCRYPT.r,
        admin_auth.SCRYPT.p,
    )


def test_hash_made_with_other_parameters_still_verifies(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verification reads the cost from the stored hash, not the current default."""
    encoded = hash_password(PASSWORD)
    monkeypatch.setattr(admin_auth, "SCRYPT", admin_auth.ScryptParams(n=2**5, r=8, p=1))

    assert verify_password(PASSWORD, encoded)


def test_shipped_cost_meets_the_owasp_scrypt_minimum() -> None:
    """OWASP Password Storage Cheat Sheet: N=2^17, r=8, p=1 or an equivalent,
    i.e. N x p of at least 2^17 at r=8 - without eating a small host's memory."""
    shipped = admin_auth.ScryptParams()  # the conftest swaps a cheap cost into SCRYPT

    assert shipped.r >= 8
    assert shipped.n * shipped.p >= 2**17 - 2**15  # N=2^15, p=3 is OWASP's equivalent
    assert 128 * shipped.n * shipped.r <= 64 * 1024 * 1024


def test_needs_rehash_spots_another_cost_or_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    current = hash_password(PASSWORD)
    assert not needs_rehash(current)

    monkeypatch.setattr(admin_auth, "SCRYPT", admin_auth.ScryptParams(n=2**5, r=8, p=1))
    assert needs_rehash(current)
    assert needs_rehash("bcrypt$16$8$1$c2FsdA$a2V5")
    assert needs_rehash("")


def test_login_upgrades_a_hash_made_with_an_older_cost(
    auth, db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stored hash moves to the current cost at the next good login; the
    password, its version and the open sessions are unchanged."""
    first = auth.setup(PASSWORD, None, None)
    old_hash = db_session.get(AdminCredential, 1).password_hash
    monkeypatch.setattr(admin_auth, "SCRYPT", admin_auth.ScryptParams(n=2**5, r=8, p=2))

    auth.login(PASSWORD, None, None)

    credential = db_session.get(AdminCredential, 1)
    assert credential.password_hash != old_hash
    assert credential.password_hash.startswith("scrypt$32$8$2$")
    assert credential.password_version == 1
    assert auth.authenticate(first)
    auth.login(PASSWORD, None, None)  # current cost: no rewrite
    assert db_session.get(AdminCredential, 1).password_hash == credential.password_hash


@pytest.mark.parametrize(
    "encoded",
    ["", "bcrypt$16$8$1$c2FsdA$a2V5", "scrypt$notanumber$8$1$c2FsdA$a2V5", "scrypt$16$8$1"],
)
def test_malformed_hash_never_verifies(encoded: str) -> None:
    """A corrupt or foreign hash is a failed login, not a crash."""
    assert not verify_password(PASSWORD, encoded)


# --- setup and login ----------------------------------------------------------


def test_setup_stores_a_hash_and_opens_a_session(auth, db_session) -> None:
    """Setup keeps only a hash of the password and logs the caller in."""
    raw = auth.setup(PASSWORD, "10.0.0.2", "Firefox")

    credential = db_session.get(AdminCredential, 1)
    assert credential is not None
    assert PASSWORD not in credential.password_hash
    session = auth.authenticate(raw)
    assert (session.client_ip, session.user_agent) == ("10.0.0.2", "Firefox")
    assert raw not in session.token_hash


def test_setup_twice_is_refused(auth) -> None:
    """Once a password exists, setup can never replace it."""
    auth.setup(PASSWORD, None, None)

    with pytest.raises(AdminAlreadyConfiguredError):
        auth.setup("another long password", None, None)


def test_setup_losing_a_race_is_refused(auth, monkeypatch: pytest.MonkeyPatch) -> None:
    """Two concurrent setups: the insert that loses on the fixed primary key gets a 409."""
    monkeypatch.setattr(auth, "is_configured", lambda: False)

    def _conflict() -> None:
        raise IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed"))

    monkeypatch.setattr(auth.db, "commit", _conflict)

    with pytest.raises(AdminAlreadyConfiguredError):
        auth.setup(PASSWORD, None, None)


def test_long_user_agent_is_truncated(auth) -> None:
    """The stored user agent fits its column."""
    raw = auth.setup(PASSWORD, None, "x" * 1000)

    assert len(auth.authenticate(raw).user_agent or "") == 255


def test_login_before_setup_asks_for_setup(auth) -> None:
    with pytest.raises(AdminSetupRequiredError):
        auth.login(PASSWORD, None, None)


def test_login_with_the_right_password_opens_a_new_session(auth, db_session) -> None:
    """Each login is its own session; the setup one stays valid."""
    first = auth.setup(PASSWORD, None, None)
    second = auth.login(PASSWORD, "10.0.0.3", None)

    assert first != second
    assert auth.authenticate(first).id != auth.authenticate(second).id
    assert db_session.query(AdminSession).count() == 2


def test_login_with_a_wrong_password_is_refused(auth) -> None:
    auth.setup(PASSWORD, None, None)

    with pytest.raises(InvalidCredentialsError):
        auth.login("wrong password!", None, None)


# --- session checks -----------------------------------------------------------


@pytest.mark.parametrize("raw", [None, "", "not-a-session-token"])
def test_authenticate_refuses_a_missing_or_unknown_token(auth, raw: str | None) -> None:
    auth.setup(PASSWORD, None, None)

    with pytest.raises(AdminLoginRequiredError):
        auth.authenticate(raw)


def test_session_past_its_hard_expiry_is_refused_and_deleted(auth, db_session) -> None:
    """The absolute ceiling holds even for a session in constant use."""
    raw = auth.setup(PASSWORD, None, None)
    session = _only_session(db_session)
    session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()

    with pytest.raises(AdminLoginRequiredError, match="expired"):
        auth.authenticate(raw)
    assert db_session.query(AdminSession).count() == 0


def test_session_idle_longer_than_the_setting_is_refused(auth, db_session) -> None:
    """A session unused for more than ``admin_session_idle_days`` is over."""
    save_app_settings({"admin_session_idle_days": 2})
    raw = auth.setup(PASSWORD, None, None)
    session = _only_session(db_session)
    session.last_seen_at = datetime.now(UTC) - timedelta(days=3)
    db_session.commit()

    with pytest.raises(AdminLoginRequiredError):
        auth.authenticate(raw)


def test_authenticate_slides_last_seen_only_after_the_touch_interval(auth, db_session) -> None:
    """Recent activity is not rewritten on every call; older activity is refreshed."""
    raw = auth.setup(PASSWORD, None, None)
    session = _only_session(db_session)
    recent = datetime.now(UTC) - timedelta(seconds=10)
    session.last_seen_at = recent
    db_session.commit()

    auth.authenticate(raw)
    assert abs(_aware(session.last_seen_at) - recent) < timedelta(seconds=1)

    session.last_seen_at = datetime.now(UTC) - timedelta(hours=1)
    db_session.commit()
    auth.authenticate(raw)
    assert datetime.now(UTC) - _aware(session.last_seen_at) < timedelta(seconds=5)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def test_logout_ends_only_that_session(auth) -> None:
    first = auth.setup(PASSWORD, None, None)
    second = auth.login(PASSWORD, None, None)

    auth.logout(first)

    with pytest.raises(AdminLoginRequiredError):
        auth.authenticate(first)
    assert auth.authenticate(second)


def test_logout_without_a_token_is_a_no_op(auth) -> None:
    auth.setup(PASSWORD, None, None)

    auth.logout(None)

    assert len(auth.list_sessions()) == 1


# --- password change, revoke, reset, prune ------------------------------------


def test_change_password_keeps_the_caller_and_closes_the_others(auth) -> None:
    """After a change: new password works, old one does not, only the caller stays logged in."""
    mine = auth.setup(PASSWORD, None, None)
    other = auth.login(PASSWORD, None, None)
    new_password = "a brand new password"

    auth.change_password(auth.authenticate(mine), PASSWORD, new_password)

    assert auth.authenticate(mine)
    with pytest.raises(AdminLoginRequiredError):
        auth.authenticate(other)
    with pytest.raises(InvalidCredentialsError):
        auth.login(PASSWORD, None, None)
    assert auth.login(new_password, None, None)


def test_change_password_needs_the_current_one(auth) -> None:
    raw = auth.setup(PASSWORD, None, None)

    with pytest.raises(InvalidCredentialsError):
        auth.change_password(auth.authenticate(raw), "not the password", "a brand new password")


def test_change_password_without_a_credential_asks_for_setup(auth, db_session) -> None:
    raw = auth.setup(PASSWORD, None, None)
    session = auth.authenticate(raw)
    db_session.query(AdminCredential).delete()
    db_session.commit()

    with pytest.raises(AdminSetupRequiredError):
        auth.change_password(session, PASSWORD, "a brand new password")


def test_session_minted_under_an_older_password_version_is_refused(auth, db_session) -> None:
    raw = auth.setup(PASSWORD, None, None)
    db_session.get(AdminCredential, 1).password_version = 7
    db_session.commit()

    with pytest.raises(AdminLoginRequiredError):
        auth.authenticate(raw)


def test_revoke_session_and_unknown_session(auth) -> None:
    raw = auth.setup(PASSWORD, None, None)
    session_id = auth.authenticate(raw).id

    auth.revoke_session(session_id)

    with pytest.raises(AdminLoginRequiredError):
        auth.authenticate(raw)
    with pytest.raises(ResourceNotFoundError):
        auth.revoke_session(session_id)


def test_reset_forgets_the_password_and_every_session(auth) -> None:
    raw = auth.setup(PASSWORD, None, None)

    auth.reset()

    assert not auth.is_configured()
    assert auth.list_sessions() == []
    assert auth.setup("the new first password", None, None) != raw


def test_reset_marker_clears_the_password_once_and_is_consumed(auth, tmp_path) -> None:
    """A marker file present at startup resets the admin and is deleted, so the
    next start keeps the new password."""
    auth.setup(PASSWORD, None, None)
    marker = tmp_path / "reset-admin"
    marker.touch()

    assert auth.reset_if_requested([tmp_path / "absent", marker]) is True

    assert not auth.is_configured()
    assert not marker.exists()
    auth.setup("the new first password", None, None)
    assert auth.reset_if_requested([marker]) is False
    assert auth.is_configured()


def test_reset_without_a_marker_keeps_the_password(auth, tmp_path) -> None:
    auth.setup(PASSWORD, None, None)

    assert auth.reset_if_requested([tmp_path / "reset-admin"]) is False
    assert auth.is_configured()


def test_reset_marker_that_cannot_be_removed_keeps_the_password(
    auth, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A marker that would survive the restart must not wipe the password at
    every start: it is reported and nothing is reset."""
    auth.setup(PASSWORD, None, None)
    marker = tmp_path / "reset-admin"
    marker.touch()

    def _read_only(self: object, missing_ok: bool = False) -> None:
        raise PermissionError("read-only file system")

    monkeypatch.setattr(type(marker), "unlink", _read_only)

    assert auth.reset_if_requested([marker]) is False
    assert auth.is_configured()


def test_prune_removes_only_expired_or_idle_sessions(auth, db_session) -> None:
    """Hard-expired and idle sessions go; a live one stays."""
    auth.setup(PASSWORD, None, None)
    auth.login(PASSWORD, None, None)
    auth.login(PASSWORD, None, None)
    expired, idle, live = auth.list_sessions()
    expired.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    idle.last_seen_at = datetime.now(UTC) - timedelta(days=30)
    db_session.commit()

    assert auth.prune_expired_sessions() == 2
    assert [s.id for s in auth.list_sessions()] == [live.id]
    assert auth.prune_expired_sessions() == 0
