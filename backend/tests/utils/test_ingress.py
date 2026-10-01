"""Home Assistant ingress: Supervisor headers are trusted from the Supervisor only."""

from __future__ import annotations

import ipaddress
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.utils.ingress import IngressMiddleware, client_from_forwarded_for, parse_ip

SUPERVISOR = "172.30.32.2"
PREFIX = "/api/hassio_ingress/abc_DEF-123"
PASSWORD = "a long enough password"


@pytest.fixture
def on_home_assistant(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPERVISOR_TOKEN", "supervisor-token")
    get_settings.cache_clear()


class _Recorder:
    """The inner ASGI app: keeps the scope it was called with."""

    def __init__(self) -> None:
        self.scope: dict[str, Any] = {}

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        self.scope = dict(scope)


async def _through(peer: str | None, headers: dict[str, str], kind: str = "http") -> dict[str, Any]:
    recorder = _Recorder()
    scope: dict[str, Any] = {
        "type": kind,
        "scheme": "ws" if kind == "websocket" else "http",
        "path": "/api/health",
        "root_path": "",
        "headers": [(k.encode(), v.encode()) for k, v in headers.items()],
        "client": (peer, 40000) if peer else None,
    }
    await IngressMiddleware(recorder)(scope, None, None)  # type: ignore[arg-type]
    return recorder.scope


def _ingress_headers(**extra: str) -> dict[str, str]:
    return {
        "x-ingress-path": PREFIX,
        "x-forwarded-for": "192.168.1.50, 172.30.32.1",
        "x-forwarded-proto": "https",
        "x-remote-user-id": "ha-user-1",
        **extra,
    }


def _header_names(scope: dict[str, Any]) -> set[bytes]:
    return {key for key, _ in scope["headers"]}


# --- address parsing ------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("172.30.32.2", "172.30.32.2"),
        ("::ffff:172.30.32.2", "172.30.32.2"),
        (" 2001:db8::1 ", "2001:db8::1"),
        ("None", None),
        ("", None),
        ("not-an-ip", None),
    ],
)
def test_parse_ip_unwraps_ipv4_mapped_addresses(raw: str, expected: str | None) -> None:
    """A dual-stack socket reports IPv4 peers as ``::ffff:a.b.c.d``: they must
    compare equal to the plain IPv4 address."""
    parsed = parse_ip(raw)
    assert parsed == (ipaddress.ip_address(expected) if expected else None)


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("192.168.1.50, 172.30.32.1", "192.168.1.50"),
        ("None, 192.168.1.50, 172.30.32.1", "192.168.1.50"),
        ("6.6.6.6, 192.168.1.50, 172.30.32.1, 172.30.32.2", "192.168.1.50"),
        ("::ffff:192.168.1.50, ::ffff:172.30.33.9", "192.168.1.50"),
        ("2001:db8::7, 172.30.32.1", "2001:db8::7"),
        ("172.30.32.1", None),
        ("None", None),
        ("", None),
    ],
)
def test_client_is_the_rightmost_hop_outside_the_hassio_network(
    header: str, expected: str | None
) -> None:
    """Hops left of the client came from the browser and are not believed."""
    found = client_from_forwarded_for(header)
    assert found == (ipaddress.ip_address(expected) if expected else None)


# --- trusted Supervisor ---------------------------------------------------------


@pytest.mark.parametrize("peer", [SUPERVISOR, f"::ffff:{SUPERVISOR}"])
async def test_supervisor_request_gets_client_prefix_and_scheme(
    on_home_assistant: None, peer: str
) -> None:
    """From the Supervisor, plain or IPv4-mapped, the browser's address, the
    ingress prefix and the HTTPS scheme are restored."""
    scope = await _through(peer, _ingress_headers())

    assert scope["client"] == ("192.168.1.50", 40000)
    assert scope["root_path"] == PREFIX
    assert scope["scheme"] == "https"
    assert b"x-remote-user-id" in _header_names(scope)


async def test_supervisor_websocket_gets_a_secure_websocket_scheme(on_home_assistant: None) -> None:
    scope = await _through(SUPERVISOR, _ingress_headers(), kind="websocket")

    assert scope["scheme"] == "wss"
    assert scope["client"] == ("192.168.1.50", 40000)


async def test_supervisor_request_without_a_client_hop_keeps_the_peer(
    on_home_assistant: None,
) -> None:
    scope = await _through(SUPERVISOR, {"x-forwarded-for": "172.30.32.1"})

    assert scope["client"] == (SUPERVISOR, 40000)
    assert scope["root_path"] == ""
    assert scope["scheme"] == "http"


@pytest.mark.parametrize(
    "prefix", ["/api/hassio_ingress/a b", "relative/path", "/api/x/../y?z", "/api/<script>"]
)
async def test_malformed_ingress_prefix_is_ignored(on_home_assistant: None, prefix: str) -> None:
    """The prefix becomes a cookie path: anything but plain segments is refused."""
    scope = await _through(SUPERVISOR, _ingress_headers(**{"x-ingress-path": prefix}))

    assert scope["root_path"] == ""


async def test_unknown_forwarded_proto_keeps_the_scheme(on_home_assistant: None) -> None:
    scope = await _through(SUPERVISOR, _ingress_headers(**{"x-forwarded-proto": "gopher"}))

    assert scope["scheme"] == "http"


async def test_proxy_address_override_is_honoured(
    on_home_assistant: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The e2e fake Supervisor runs on loopback and sets INGRESS_PROXY_IP."""
    monkeypatch.setenv("INGRESS_PROXY_IP", "127.0.0.1")
    get_settings.cache_clear()

    scope = await _through("::ffff:127.0.0.1", _ingress_headers())

    assert scope["root_path"] == PREFIX


# --- untrusted peers --------------------------------------------------------------


async def test_other_peer_cannot_spoof_the_supervisor_headers(on_home_assistant: None) -> None:
    """On the direct port anyone can send these headers: they are removed and
    nothing they say is applied."""
    scope = await _through("192.168.1.66", _ingress_headers())

    assert scope["client"] == ("192.168.1.66", 40000)
    assert scope["root_path"] == ""
    assert scope["scheme"] == "http"
    assert b"x-ingress-path" not in _header_names(scope)
    assert b"x-remote-user-id" not in _header_names(scope)
    assert b"x-forwarded-for" in _header_names(scope)


async def test_supervisor_address_is_not_trusted_outside_home_assistant() -> None:
    """A plain Docker install never trusts the headers, whatever the peer."""
    scope = await _through(SUPERVISOR, _ingress_headers())

    assert scope["client"] == (SUPERVISOR, 40000)
    assert scope["root_path"] == ""
    assert b"x-ingress-path" not in _header_names(scope)


async def test_request_without_a_peer_is_left_alone(on_home_assistant: None) -> None:
    scope = await _through(None, {"accept": "*/*"})

    assert scope["client"] is None
    assert scope["root_path"] == ""


async def test_lifespan_scope_passes_through() -> None:
    recorder = _Recorder()
    await IngressMiddleware(recorder)({"type": "lifespan"}, None, None)  # type: ignore[arg-type]

    assert recorder.scope == {"type": "lifespan"}


# --- through the real app ---------------------------------------------------------


def test_admin_cookie_is_scoped_to_the_ingress_prefix(
    client: TestClient, on_home_assistant: None
) -> None:
    """Every ingress app shares the HA origin: the admin cookie must be path
    scoped to this app's prefix, and Secure when HA is reached over HTTPS."""
    behind_ha = TestClient(client.app, client=(f"::ffff:{SUPERVISOR}", 40000))

    response = behind_ha.post(
        "/api/auth/setup", json={"password": PASSWORD}, headers=_ingress_headers()
    )

    assert response.status_code == 204
    cookie = response.headers["set-cookie"]
    assert f"Path={PREFIX}/" in cookie
    assert "Secure" in cookie


def test_login_throttle_counts_each_ha_user_apart(
    client: TestClient, on_home_assistant: None
) -> None:
    """Behind the Supervisor every request shares its address; the throttle must
    key on the browser's, or one user locks every other one out."""
    behind_ha = TestClient(client.app, client=(SUPERVISOR, 40000))
    assert behind_ha.post("/api/auth/setup", json={"password": PASSWORD}).status_code == 204

    def _login(user_ip: str, password: str) -> int:
        headers = _ingress_headers(**{"x-forwarded-for": f"{user_ip}, 172.30.32.1"})
        return behind_ha.post(
            "/api/auth/login", json={"password": password}, headers=headers
        ).status_code

    statuses = [_login("192.168.1.66", "wrong password!!") for _ in range(6)]
    assert statuses[-1] == 429
    assert _login("192.168.1.50", PASSWORD) == 204
