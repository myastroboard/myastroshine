"""Home Assistant ingress: trust the Supervisor's proxy headers, and only those.

As a Home Assistant app the UI is reached through the HA frontend at
``/api/hassio_ingress/<token>/``. The Supervisor strips that prefix, proxies to
the app and adds ``X-Ingress-Path`` (the prefix), ``X-Forwarded-For`` (HA core
and the Supervisor append their own hops), ``X-Forwarded-Proto`` and the HA user
(``X-Remote-User-Id`` / ``-Name`` / ``-Display-Name``).

Every request then comes from the Supervisor's address, so without this the
per-IP rate limit, login throttle and concurrent-job cap would be shared by
every HA user. :class:`IngressMiddleware` restores the browser's address, the
scheme and the prefix (``root_path``, which scopes the admin cookie) - but only
for a request that really comes from the Supervisor of an HA app:

* the app runs under Home Assistant (``SUPERVISOR_TOKEN``, injected by the
  Supervisor into every app container - a plain Docker install never has it);
* the TCP peer is the Supervisor (``172.30.32.2``). The dual-stack socket
  reports it as ``::ffff:172.30.32.2``: addresses are parsed and IPv4-mapped
  ones unwrapped, never compared as strings.

Any other request has the ingress and remote-user headers removed, so nothing
downstream can be fooled by a client that sends them on the direct port.
"""

from __future__ import annotations

import ipaddress
import re

from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import get_settings
from app.logging_config import get_logger

logger = get_logger(__name__)

#: The hassio network's proxies (HA core 172.30.32.1, the Supervisor
#: 172.30.32.2): hops they appended to X-Forwarded-For are not the client.
SUPERVISOR_NETWORK = ipaddress.ip_network("172.30.32.0/23")

#: The prefix ends up in a cookie path: plain path segments only.
_PREFIX_RE = re.compile(r"^(/[A-Za-z0-9._~-]+)+$")

#: Headers only the Supervisor may set.
_SUPERVISOR_HEADERS = frozenset(
    {
        b"x-ingress-path",
        b"x-remote-user-id",
        b"x-remote-user-name",
        b"x-remote-user-display-name",
    }
)

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


def parse_ip(value: str) -> IPAddress | None:
    """``value`` as an address, IPv4-mapped IPv6 unwrapped; ``None`` if it isn't one."""
    try:
        address = ipaddress.ip_address(value.strip())
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def client_from_forwarded_for(header: str) -> IPAddress | None:
    """The rightmost ``X-Forwarded-For`` hop outside the hassio network.

    Hops right of it were appended by HA core and the Supervisor; hops left of
    it came from the browser's request and can say anything. Unparseable hops
    (the Supervisor writes ``None`` when the request had no such header) are
    skipped.
    """
    for hop in reversed(header.split(",")):
        address = parse_ip(hop)
        if address is not None and address not in SUPERVISOR_NETWORK:
            return address
    return None


def _header(headers: list[tuple[bytes, bytes]], name: bytes) -> str:
    for key, value in headers:
        if key == name:
            return value.decode("latin-1")
    return ""


def _from_supervisor(scope: Scope) -> bool:
    settings = get_settings()
    if not settings.on_home_assistant:
        return False
    client = scope.get("client")
    if not client:
        return False
    peer = parse_ip(str(client[0]))
    return peer is not None and peer == parse_ip(settings.ingress_proxy_ip)


class IngressMiddleware:
    """Pure ASGI middleware (``http`` and ``websocket``), the outermost one."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        headers: list[tuple[bytes, bytes]] = list(scope.get("headers", []))
        if _from_supervisor(scope):
            scope = self._apply(scope, headers)
        elif any(key in _SUPERVISOR_HEADERS for key, _ in headers):
            logger.debug(
                "ingress headers dropped from an untrusted peer", client=scope.get("client")
            )
            scope = dict(scope)
            scope["headers"] = [(k, v) for k, v in headers if k not in _SUPERVISOR_HEADERS]
        await self.app(scope, receive, send)

    @staticmethod
    def _apply(scope: Scope, headers: list[tuple[bytes, bytes]]) -> Scope:
        scope = dict(scope)
        client = client_from_forwarded_for(_header(headers, b"x-forwarded-for"))
        if client is not None:
            port = scope["client"][1] if scope.get("client") else 0
            scope["client"] = (str(client), port)

        prefix = _header(headers, b"x-ingress-path").rstrip("/")
        if prefix and _PREFIX_RE.fullmatch(prefix):
            scope["root_path"] = prefix
        elif prefix:
            logger.warning("invalid X-Ingress-Path ignored", length=len(prefix))

        proto = _header(headers, b"x-forwarded-proto").split(",")[0].strip().lower()
        if proto in ("http", "https"):
            secure = proto == "https"
            if scope["type"] == "websocket":
                scope["scheme"] = "wss" if secure else "ws"
            else:
                scope["scheme"] = proto
        return scope
