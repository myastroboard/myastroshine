"""Admin authentication request/response models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.constants import ADMIN_PASSWORD_MAX_LENGTH, ADMIN_PASSWORD_MIN_LENGTH


class AuthStatusResponse(BaseModel):
    """Body of ``GET /api/auth/status`` - what the Settings page should show."""

    #: ``False``: the structural ``ADMIN_ENABLED`` switch turned the admin API off.
    admin_enabled: bool
    #: ``False``: no admin password yet - show the setup form.
    configured: bool
    #: This browser holds a live admin session.
    authenticated: bool


class SetupRequest(BaseModel):
    """Body of ``POST /api/auth/setup``."""

    password: str = Field(
        min_length=ADMIN_PASSWORD_MIN_LENGTH, max_length=ADMIN_PASSWORD_MAX_LENGTH
    )


class LoginRequest(BaseModel):
    """Body of ``POST /api/auth/login``. No minimum length: that would hint the policy."""

    password: str = Field(min_length=1, max_length=ADMIN_PASSWORD_MAX_LENGTH)


class ChangePasswordRequest(BaseModel):
    """Body of ``POST /api/auth/password``."""

    current_password: str = Field(min_length=1, max_length=ADMIN_PASSWORD_MAX_LENGTH)
    new_password: str = Field(
        min_length=ADMIN_PASSWORD_MIN_LENGTH, max_length=ADMIN_PASSWORD_MAX_LENGTH
    )


class AdminSessionOut(BaseModel):
    """One logged-in browser in ``GET /api/auth/sessions``."""

    id: str
    client_ip: str | None = None
    user_agent: str | None = None
    created_at: datetime
    last_seen_at: datetime
    #: The session making this request.
    current: bool = False


class AdminSessionListResponse(BaseModel):
    sessions: list[AdminSessionOut]
