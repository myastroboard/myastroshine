"""Admin authentication routes.

GET    /api/auth/status          - admin enabled / password set / this browser logged in
POST   /api/auth/setup           - set the first admin password (only while none exists)
POST   /api/auth/login           - log in with the admin password
POST   /api/auth/logout          - end this browser's admin session
POST   /api/auth/password        - change the password (closes every other session)
GET    /api/auth/sessions        - list logged-in browsers
DELETE /api/auth/sessions/{id}   - log one of them out

Only the administration surface needs this; using the app (upload, edit, stack,
download) stays open. The session lives in an ``HttpOnly`` cookie whose path is
derived from the ASGI ``root_path``, so it stays scoped to this app when served
under a path prefix (a Home Assistant ingress).
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from app.config import get_settings
from app.constants import ADMIN_COOKIE_NAME, ADMIN_SESSION_MAX_DAYS
from app.dependencies import (
    AdminAuthServiceDep,
    RequireAdmin,
    RequireRateLimit,
    RequireTrustedOrigin,
)
from app.exceptions import AdminLoginRequiredError, ForbiddenError, InvalidCredentialsError
from app.logging_config import get_logger
from app.models import (
    AdminSessionListResponse,
    AdminSessionOut,
    AuthStatusResponse,
    ChangePasswordRequest,
    LoginRequest,
    SetupRequest,
)
from app.utils.rate_limit import get_client_ip, login_throttle

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def cookie_path(request: Request) -> str:
    """``/`` when served at the root, ``<prefix>/`` under a path prefix."""
    return str(request.scope.get("root_path") or "").rstrip("/") + "/"


def _is_https(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"


def _set_cookie(response: Response, request: Request, raw_token: str) -> None:
    response.set_cookie(
        ADMIN_COOKIE_NAME,
        raw_token,
        max_age=ADMIN_SESSION_MAX_DAYS * 24 * 60 * 60,
        path=cookie_path(request),
        httponly=True,
        samesite="strict",
        secure=_is_https(request),
    )


def _clear_cookie(response: Response, request: Request) -> None:
    response.delete_cookie(
        ADMIN_COOKIE_NAME,
        path=cookie_path(request),
        httponly=True,
        samesite="strict",
        secure=_is_https(request),
    )


def _require_admin_enabled() -> None:
    if not get_settings().admin_enabled:
        raise ForbiddenError("Admin API is disabled (ADMIN_ENABLED=false)")


def _throttle_key(request: Request) -> str:
    return get_client_ip(request) or "unknown"


@router.get("/status", response_model=AuthStatusResponse)
def auth_status(request: Request, auth: AdminAuthServiceDep) -> AuthStatusResponse:
    """What the Settings page should show: setup form, login form, or the panels."""
    configured = auth.is_configured()
    authenticated = False
    if configured:
        try:
            auth.authenticate(request.cookies.get(ADMIN_COOKIE_NAME))
            authenticated = True
        except AdminLoginRequiredError:
            authenticated = False
    return AuthStatusResponse(
        admin_enabled=get_settings().admin_enabled,
        configured=configured,
        authenticated=authenticated,
    )


@router.post("/setup", status_code=status.HTTP_204_NO_CONTENT)
def setup_admin(
    body: SetupRequest,
    request: Request,
    response: Response,
    auth: AdminAuthServiceDep,
    _origin: RequireTrustedOrigin,
    _rate_limit: RequireRateLimit,
) -> None:
    """Set the first admin password and log this browser in (409 once one exists)."""
    _require_admin_enabled()
    raw = auth.setup(body.password, get_client_ip(request), request.headers.get("user-agent"))
    _set_cookie(response, request, raw)


@router.post("/login", status_code=status.HTTP_204_NO_CONTENT)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    auth: AdminAuthServiceDep,
    _origin: RequireTrustedOrigin,
    _rate_limit: RequireRateLimit,
) -> None:
    """Log in with the admin password. Failures are throttled per client IP."""
    _require_admin_enabled()
    key = _throttle_key(request)
    login_throttle.check(key)
    try:
        raw = auth.login(body.password, get_client_ip(request), request.headers.get("user-agent"))
    except InvalidCredentialsError:
        locked = login_throttle.record_failure(key)
        logger.warning("admin login failed", client_ip=key, locked_out=locked)
        raise
    login_throttle.record_success(key)
    _set_cookie(response, request, raw)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    auth: AdminAuthServiceDep,
    _origin: RequireTrustedOrigin,
) -> None:
    """End this browser's session. Always succeeds, logged in or not."""
    auth.logout(request.cookies.get(ADMIN_COOKIE_NAME))
    _clear_cookie(response, request)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: ChangePasswordRequest,
    request: Request,
    admin: RequireAdmin,
    auth: AdminAuthServiceDep,
    _rate_limit: RequireRateLimit,
) -> None:
    """Change the admin password. Every other logged-in browser is logged out."""
    key = _throttle_key(request)
    login_throttle.check(key)
    try:
        auth.change_password(admin, body.current_password, body.new_password)
    except InvalidCredentialsError:
        login_throttle.record_failure(key)
        raise


@router.get("/sessions", response_model=AdminSessionListResponse)
def list_sessions(
    admin: RequireAdmin, auth: AdminAuthServiceDep, _rate_limit: RequireRateLimit
) -> AdminSessionListResponse:
    """Every logged-in admin browser, most recently active first."""
    return AdminSessionListResponse(
        sessions=[
            AdminSessionOut(
                **AdminSessionOut.model_validate(record, from_attributes=True).model_dump(
                    exclude={"current"}
                ),
                current=record.id == admin.id,
            )
            for record in auth.list_sessions()
        ]
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_session(
    session_id: str,
    request: Request,
    response: Response,
    admin: RequireAdmin,
    auth: AdminAuthServiceDep,
    _rate_limit: RequireRateLimit,
) -> None:
    """Log one browser out (revoking the current one is a logout)."""
    auth.revoke_session(session_id)
    if session_id == admin.id:
        _clear_cookie(response, request)
