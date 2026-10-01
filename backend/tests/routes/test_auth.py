"""Admin authentication routes and the admin gate on the admin surface."""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.constants import ADMIN_COOKIE_NAME, LOGIN_MAX_FAILURES
from tests.conftest import ADMIN_TEST_PASSWORD

#: One representative route per admin router.
ADMIN_ROUTES = [
    ("get", "/api/admin/app-settings"),
    ("get", "/api/admin/logs"),
    ("get", "/api/admin/jobs"),
    ("get", "/api/admin/engine-status"),
    ("get", "/api/tokens"),
    ("post", "/api/tokens"),
    ("get", "/api/auth/sessions"),
]


def _set_cookie_header(response) -> str:
    return response.headers.get("set-cookie", "")


# --- status -------------------------------------------------------------------


def test_status_before_setup(client) -> None:
    """A fresh install: admin on, no password yet, nobody logged in."""
    assert client.get("/api/auth/status").json() == {
        "admin_enabled": True,
        "configured": False,
        "authenticated": False,
    }


def test_status_after_setup_and_after_logout(admin_client) -> None:
    assert admin_client.get("/api/auth/status").json()["authenticated"] is True

    assert admin_client.post("/api/auth/logout").status_code == 204

    body = admin_client.get("/api/auth/status").json()
    assert (body["configured"], body["authenticated"]) == (True, False)


def test_status_reports_admin_disabled(client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_ENABLED", "false")
    get_settings.cache_clear()

    assert client.get("/api/auth/status").json()["admin_enabled"] is False
    get_settings.cache_clear()


# --- the admin gate -----------------------------------------------------------


@pytest.mark.parametrize(("method", "path"), ADMIN_ROUTES)
def test_admin_routes_are_locked_until_setup(client, method: str, path: str) -> None:
    """Before any password exists the admin surface is closed, never open."""
    response = getattr(client, method)(
        path, **({"json": {"name": "x"}} if method == "post" else {})
    )

    assert response.status_code == 403
    assert response.json()["error_code"] == "ADMIN_SETUP_REQUIRED"


@pytest.mark.parametrize(("method", "path"), ADMIN_ROUTES)
def test_admin_routes_need_a_login(admin_client, method: str, path: str) -> None:
    """With a password set, an anonymous caller gets 401 on every admin route."""
    admin_client.cookies.clear()

    response = getattr(admin_client, method)(
        path, **({"json": {"name": "x"}} if method == "post" else {})
    )

    assert response.status_code == 401
    assert response.json()["error_code"] == "ADMIN_LOGIN_REQUIRED"


def test_admin_routes_answer_a_logged_in_admin(admin_client) -> None:
    assert admin_client.get("/api/admin/app-settings").status_code == 200


def test_processing_routes_stay_open_without_login(admin_client, sample_jpeg: bytes) -> None:
    """Using the app never needs the admin: upload and presets answer anonymously."""
    admin_client.cookies.clear()

    upload = admin_client.post(
        "/api/upload", files={"file": ("m42.jpg", sample_jpeg, "image/jpeg")}
    )

    assert upload.status_code == 200
    assert admin_client.get("/api/presets").status_code == 200
    assert admin_client.get("/api/config").status_code == 200


# --- setup --------------------------------------------------------------------


def test_setup_sets_a_hardened_cookie(client) -> None:
    """The session cookie is HttpOnly, SameSite=Strict, scoped to the app root, and
    not Secure over plain http."""
    response = client.post("/api/auth/setup", json={"password": ADMIN_TEST_PASSWORD})

    assert response.status_code == 204
    cookie = _set_cookie_header(response)
    assert cookie.startswith(f"{ADMIN_COOKIE_NAME}=")
    lowered = cookie.lower()
    assert "httponly" in lowered
    assert "samesite=strict" in lowered
    assert "path=/;" in lowered or lowered.endswith("path=/")
    assert "secure" not in lowered.replace("samesite", "")


def test_cookie_is_secure_behind_an_https_proxy(client) -> None:
    response = client.post(
        "/api/auth/setup",
        json={"password": ADMIN_TEST_PASSWORD},
        headers={"X-Forwarded-Proto": "https"},
    )

    assert "; secure" in _set_cookie_header(response).lower()


def test_cookie_path_follows_the_root_path() -> None:
    """Served under a path prefix, the cookie is scoped to that prefix only."""
    from types import SimpleNamespace

    from app.routes.auth import cookie_path

    prefixed = SimpleNamespace(scope={"root_path": "/api/hassio_ingress/abc123"})
    assert cookie_path(prefixed) == "/api/hassio_ingress/abc123/"  # type: ignore[arg-type]
    assert cookie_path(SimpleNamespace(scope={})) == "/"  # type: ignore[arg-type]


def test_setup_twice_is_a_409(admin_client) -> None:
    response = admin_client.post("/api/auth/setup", json={"password": "another long one"})

    assert response.status_code == 409
    assert response.json()["error_code"] == "ADMIN_ALREADY_CONFIGURED"


def test_setup_rejects_a_short_password(client) -> None:
    assert client.post("/api/auth/setup", json={"password": "short"}).status_code == 400
    assert client.get("/api/auth/status").json()["configured"] is False


@pytest.mark.parametrize("path", ["/api/auth/setup", "/api/auth/login"])
def test_setup_and_login_403_when_admin_disabled(
    client, monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    monkeypatch.setenv("ADMIN_ENABLED", "false")
    get_settings.cache_clear()

    assert client.post(path, json={"password": ADMIN_TEST_PASSWORD}).status_code == 403
    get_settings.cache_clear()


# --- login / logout -----------------------------------------------------------


def test_login_with_the_right_password(admin_client) -> None:
    admin_client.cookies.clear()

    response = admin_client.post("/api/auth/login", json={"password": ADMIN_TEST_PASSWORD})

    assert response.status_code == 204
    assert admin_client.get("/api/admin/app-settings").status_code == 200


def test_login_with_a_wrong_password(admin_client) -> None:
    admin_client.cookies.clear()

    response = admin_client.post("/api/auth/login", json={"password": "nope"})

    assert response.status_code == 401
    assert response.json()["error_code"] == "INVALID_CREDENTIALS"
    assert ADMIN_COOKIE_NAME not in _set_cookie_header(response)


def test_login_before_setup(client) -> None:
    response = client.post("/api/auth/login", json={"password": ADMIN_TEST_PASSWORD})

    assert response.status_code == 403
    assert response.json()["error_code"] == "ADMIN_SETUP_REQUIRED"


def test_repeated_failures_lock_the_ip_out_even_for_the_right_password(admin_client) -> None:
    """After the failure budget, the IP is locked out; a right password does not
    get through until the lockout ends."""
    admin_client.cookies.clear()
    for _ in range(LOGIN_MAX_FAILURES):
        admin_client.post("/api/auth/login", json={"password": "wrong password"})

    response = admin_client.post("/api/auth/login", json={"password": ADMIN_TEST_PASSWORD})

    assert response.status_code == 429
    assert response.json()["details"]["retry_after_seconds"] > 0


def test_logout_clears_the_cookie_and_the_session(admin_client) -> None:
    response = admin_client.post("/api/auth/logout")

    assert response.status_code == 204
    assert f'{ADMIN_COOKIE_NAME}=""' in _set_cookie_header(response)
    admin_client.cookies.clear()
    assert admin_client.get("/api/admin/app-settings").status_code == 401


# --- password change and sessions ---------------------------------------------


def test_change_password(admin_client) -> None:
    new_password = "a completely new password"

    response = admin_client.post(
        "/api/auth/password",
        json={"current_password": ADMIN_TEST_PASSWORD, "new_password": new_password},
    )

    assert response.status_code == 204
    assert admin_client.get("/api/admin/app-settings").status_code == 200
    admin_client.cookies.clear()
    assert (
        admin_client.post("/api/auth/login", json={"password": ADMIN_TEST_PASSWORD}).status_code
        == 401
    )
    assert admin_client.post("/api/auth/login", json={"password": new_password}).status_code == 204


def test_change_password_with_a_wrong_current_one(admin_client) -> None:
    response = admin_client.post(
        "/api/auth/password",
        json={"current_password": "not it at all", "new_password": "a completely new password"},
    )

    assert response.status_code == 401
    assert response.json()["error_code"] == "INVALID_CREDENTIALS"


def test_list_sessions_flags_the_current_one(admin_client) -> None:
    """Two logins: both listed, only the caller's flagged ``current``; no secret leaks."""
    from fastapi.testclient import TestClient

    import app.main as main_module

    other = TestClient(main_module.app)
    assert other.post("/api/auth/login", json={"password": ADMIN_TEST_PASSWORD}).status_code == 204

    sessions = admin_client.get("/api/auth/sessions").json()["sessions"]

    assert len(sessions) == 2
    assert [s["current"] for s in sessions].count(True) == 1
    assert all("token_hash" not in s for s in sessions)


def test_revoke_another_session_keeps_mine(admin_client) -> None:
    from fastapi.testclient import TestClient

    import app.main as main_module

    other = TestClient(main_module.app)
    other.post("/api/auth/login", json={"password": ADMIN_TEST_PASSWORD})
    sessions = admin_client.get("/api/auth/sessions").json()["sessions"]
    other_id = next(s["id"] for s in sessions if not s["current"])

    response = admin_client.delete(f"/api/auth/sessions/{other_id}")

    assert response.status_code == 204
    assert ADMIN_COOKIE_NAME not in _set_cookie_header(response)
    assert other.get("/api/admin/app-settings").status_code == 401
    assert admin_client.get("/api/admin/app-settings").status_code == 200


def test_revoke_my_own_session_logs_me_out(admin_client) -> None:
    mine = admin_client.get("/api/auth/sessions").json()["sessions"][0]["id"]

    response = admin_client.delete(f"/api/auth/sessions/{mine}")

    assert response.status_code == 204
    assert f'{ADMIN_COOKIE_NAME}=""' in _set_cookie_header(response)


def test_revoke_unknown_session_is_404(admin_client) -> None:
    assert admin_client.delete("/api/auth/sessions/does-not-exist").status_code == 404


# --- cross-origin guard -------------------------------------------------------


def test_cross_origin_login_is_refused(admin_client) -> None:
    """A page on another origin (even the same host, another port) cannot log in
    or change settings with the admin cookie."""
    admin_client.cookies.clear()

    response = admin_client.post(
        "/api/auth/login",
        json={"password": ADMIN_TEST_PASSWORD},
        headers={"Origin": "http://evil.example:8123"},
    )

    assert response.status_code == 403


def test_cross_origin_admin_write_is_refused(admin_client) -> None:
    body = admin_client.get("/api/admin/app-settings").json()

    response = admin_client.post(
        "/api/admin/app-settings", json=body, headers={"Origin": "http://testserver:9999"}
    )

    assert response.status_code == 403


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "http://testserver"},
        {"Origin": "http://localhost:3000"},  # in cors_origins by default
        {"Origin": "https://ha.example", "X-Forwarded-Host": "ha.example"},
        {},
    ],
)
def test_same_origin_writes_are_accepted(admin_client, headers: dict[str, str]) -> None:
    """Own host, a configured CORS origin, the proxy's forwarded host, or no Origin."""
    body = admin_client.get("/api/admin/app-settings").json()

    response = admin_client.post("/api/admin/app-settings", json=body, headers=headers)

    assert response.status_code == 200


def test_cross_origin_reads_are_not_blocked_by_the_origin_guard(admin_client) -> None:
    """GETs never change state; the guard only applies to writes."""
    response = admin_client.get(
        "/api/admin/app-settings", headers={"Origin": "http://evil.example"}
    )

    assert response.status_code == 200
