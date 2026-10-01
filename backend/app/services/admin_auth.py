"""AdminAuthService - the one admin password and the browsers logged in with it.

MyAstroShine is open to anyone who reaches it for *using* it (upload, edit,
stack, download); only the administration surface (``/api/admin/*``,
``/api/tokens``) needs a login. Mono-poste: one password, no usernames, no
roles.

- The password is stored as a salted scrypt hash (stdlib ``hashlib.scrypt``, no
  extra dependency). The cost parameters are encoded in the hash itself, so they
  can be raised later without invalidating existing hashes.
- A login mints a random session token. The browser holds it in an ``HttpOnly``
  cookie; the DB keeps only its SHA-256 hash (like webhook tokens).
- Sessions slide (``admin_session_idle_days`` without use) under a hard ceiling
  (``ADMIN_SESSION_MAX_DAYS``), and die with the password: each one records the
  ``password_version`` it was minted under.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.constants import ADMIN_SESSION_MAX_DAYS, ADMIN_SESSION_TOUCH_SECONDS
from app.db.models import AdminCredential, AdminSession
from app.exceptions import (
    AdminAlreadyConfiguredError,
    AdminLoginRequiredError,
    AdminSetupRequiredError,
    InvalidCredentialsError,
    ResourceNotFoundError,
)
from app.logging_config import get_logger
from app.utils.app_settings import get_app_settings

logger = get_logger(__name__)

_CREDENTIAL_ID = 1
_USER_AGENT_MAX = 255


@dataclass(frozen=True)
class ScryptParams:
    """scrypt cost. The defaults are the shipped cost (see :data:`SCRYPT`)."""

    n: int = 2**15
    r: int = 8
    p: int = 3


#: OWASP Password Storage Cheat Sheet: scrypt at N=2^17, r=8, p=1, or an
#: equivalent trading memory for CPU - N=2^15, r=8, p=3 is one. 32 MiB per hash
#: (kind to a Raspberry Pi), a few tenths of a second; a login is rare, and a
#: brute force is throttled per IP on top. A stored hash with weaker parameters
#: is upgraded at the next successful login (:func:`needs_rehash`).
SCRYPT = ScryptParams()
_SALT_BYTES = 16
_KEY_BYTES = 32


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _derive(password: str, salt: bytes, params: ScryptParams) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=params.n,
        r=params.r,
        p=params.p,
        maxmem=256 * params.n * params.r + 1024 * 1024,
        dklen=_KEY_BYTES,
    )


def hash_password(password: str) -> str:
    """``scrypt$n$r$p$salt$key`` with a fresh random salt."""
    params = SCRYPT
    salt = secrets.token_bytes(_SALT_BYTES)
    key = _derive(password, salt, params)
    return f"scrypt${params.n}${params.r}${params.p}${_b64(salt)}${_b64(key)}"


def verify_password(password: str, encoded: str) -> bool:
    """Constant-time check of ``password`` against a :func:`hash_password` value."""
    try:
        scheme, n, r, p, salt, key = encoded.split("$")
        if scheme != "scrypt":
            return False
        params = ScryptParams(n=int(n), r=int(r), p=int(p))
        expected = _unb64(key)
        actual = _derive(password, _unb64(salt), params)
    except ValueError:
        logger.error("admin password hash is malformed")
        return False
    return hmac.compare_digest(actual, expected)


def needs_rehash(encoded: str) -> bool:
    """True when ``encoded`` was made with parameters other than :data:`SCRYPT`."""
    scheme, *fields = encoded.split("$")
    return scheme != "scrypt" or fields[:3] != [str(SCRYPT.n), str(SCRYPT.r), str(SCRYPT.p)]


def _token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _aware(value: datetime) -> datetime:
    """SQLite hands timezone-aware columns back naive; they are stored as UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class AdminAuthService:
    """Setup, login, session checks and password changes for the admin."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # --- credential ---------------------------------------------------------

    def _credential(self) -> AdminCredential | None:
        return self.db.get(AdminCredential, _CREDENTIAL_ID)

    def is_configured(self) -> bool:
        return self._credential() is not None

    def setup(self, password: str, client_ip: str | None, user_agent: str | None) -> str:
        """Set the first admin password and log this browser in.

        Only while no password exists: the row has a fixed primary key, so two
        concurrent setups cannot both win - the loser gets a 409.
        """
        if self.is_configured():
            raise AdminAlreadyConfiguredError("The admin password is already set")
        self.db.add(
            AdminCredential(
                id=_CREDENTIAL_ID, password_hash=hash_password(password), password_version=1
            )
        )
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise AdminAlreadyConfiguredError("The admin password is already set") from exc
        logger.info("admin password set up", client_ip=client_ip)
        return self._open_session(1, client_ip, user_agent)

    def login(self, password: str, client_ip: str | None, user_agent: str | None) -> str:
        """Check the password and open a session; returns the raw session token."""
        credential = self._credential()
        if credential is None:
            raise AdminSetupRequiredError("No admin password has been set yet")
        if not verify_password(password, credential.password_hash):
            raise InvalidCredentialsError("Wrong password")
        if needs_rehash(credential.password_hash):
            # Same password, current cost: sessions and password_version untouched.
            credential.password_hash = hash_password(password)
            self.db.commit()
            logger.info("admin password hash upgraded to the current cost")
        logger.info("admin logged in", client_ip=client_ip)
        return self._open_session(credential.password_version, client_ip, user_agent)

    def change_password(self, session: AdminSession, current: str, new: str) -> None:
        """Replace the password. Every other session is closed; this one survives."""
        credential = self._credential()
        if credential is None:
            raise AdminSetupRequiredError("No admin password has been set yet")
        if not verify_password(current, credential.password_hash):
            raise InvalidCredentialsError("Wrong current password")
        credential.password_hash = hash_password(new)
        credential.password_version += 1
        session.password_version = credential.password_version
        self.db.execute(delete(AdminSession).where(AdminSession.id != session.id))
        self.db.commit()
        logger.info("admin password changed", session_id=session.id)

    def reset(self) -> None:
        """Forget the password and every session; the next visit shows setup again.

        Reached from the ``reset-admin`` CLI (``python -m app.cli``) - the way back
        in for an operator who lost the password.
        """
        self.db.execute(delete(AdminSession))
        self.db.execute(delete(AdminCredential))
        self.db.commit()
        logger.warning("admin password reset")

    # --- sessions -----------------------------------------------------------

    def _open_session(self, version: int, client_ip: str | None, user_agent: str | None) -> str:
        raw = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        self.db.add(
            AdminSession(
                id=str(uuid.uuid4()),
                token_hash=_token_hash(raw),
                password_version=version,
                client_ip=client_ip,
                user_agent=(user_agent or "")[:_USER_AGENT_MAX] or None,
                created_at=now,
                last_seen_at=now,
                expires_at=now + timedelta(days=ADMIN_SESSION_MAX_DAYS),
            )
        )
        self.db.commit()
        return raw

    def authenticate(self, raw_token: str | None) -> AdminSession:
        """The live session behind a cookie value, or :class:`AdminLoginRequiredError`."""
        if not raw_token:
            raise AdminLoginRequiredError("Admin login required")
        session = self.db.scalar(
            select(AdminSession).where(AdminSession.token_hash == _token_hash(raw_token))
        )
        if session is None or not hmac.compare_digest(session.token_hash, _token_hash(raw_token)):
            raise AdminLoginRequiredError("Admin login required")
        credential = self._credential()
        now = datetime.now(UTC)
        idle_limit = timedelta(days=get_app_settings().admin_session_idle_days)
        if (
            credential is None
            or session.password_version != credential.password_version
            or _aware(session.expires_at) <= now
            or now - _aware(session.last_seen_at) > idle_limit
        ):
            self.db.delete(session)
            self.db.commit()
            raise AdminLoginRequiredError("Admin session expired, log in again")
        if (now - _aware(session.last_seen_at)).total_seconds() > ADMIN_SESSION_TOUCH_SECONDS:
            session.last_seen_at = now
            self.db.commit()
        return session

    def logout(self, raw_token: str | None) -> None:
        if not raw_token:
            return
        self.db.execute(
            delete(AdminSession).where(AdminSession.token_hash == _token_hash(raw_token))
        )
        self.db.commit()

    def list_sessions(self) -> list[AdminSession]:
        return list(
            self.db.scalars(select(AdminSession).order_by(AdminSession.last_seen_at.desc())).all()
        )

    def revoke_session(self, session_id: str) -> None:
        session = self.db.get(AdminSession, session_id)
        if session is None:
            raise ResourceNotFoundError(f"Admin session {session_id} not found")
        self.db.delete(session)
        self.db.commit()
        logger.info("admin session revoked", session_id=session_id)

    def prune_expired_sessions(self) -> int:
        """Delete sessions past their hard expiry or idle limit. Returns the count."""
        now = datetime.now(UTC)
        idle_cutoff = now - timedelta(days=get_app_settings().admin_session_idle_days)
        result = self.db.execute(
            delete(AdminSession)
            .where((AdminSession.expires_at <= now) | (AdminSession.last_seen_at < idle_cutoff))
            # SQLite hands the columns back naive; let the DB do the comparison
            # instead of SQLAlchemy re-evaluating it in Python on loaded objects.
            .execution_options(synchronize_session="fetch")
        )
        self.db.commit()
        removed = int(getattr(result, "rowcount", 0) or 0)
        if removed:
            logger.info("expired admin sessions pruned", count=removed)
        return removed
