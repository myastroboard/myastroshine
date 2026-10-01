"""Production entry point: serve the app on IPv4 and IPv6 at once.

    python -m app.serve        # the image's CMD

``uvicorn --host ::`` is IPv6-only: asyncio sets ``IPV6_V6ONLY`` on the sockets
it creates, so IPv4 clients - the image's own ``curl localhost`` health check
among them - lose the app. ``--host 0.0.0.0`` is the opposite, and a host name
that resolves to IPv6 (``homeassistant.local`` often does) then cannot reach it.
This opens one dual-stack socket itself (``IPV6_V6ONLY`` off: IPv4 peers show up
as ``::ffff:a.b.c.d``) and hands it to uvicorn, falling back to IPv4 only when
the kernel has no IPv6.

Shutdown is bounded so a container stop ends well inside Docker's 10 s (and the
Home Assistant app's ``timeout``): ``SERVER_SHUTDOWN_GRACE_SECONDS`` for open
connections, then the lifespan stops the background jobs
(``JOB_SHUTDOWN_GRACE_SECONDS``).
"""

from __future__ import annotations

import socket

import uvicorn

from app.constants import SERVER_PORT, SERVER_SHUTDOWN_GRACE_SECONDS
from app.logging_config import get_logger

logger = get_logger(__name__)

_BACKLOG = 2048


def listening_socket(port: int = SERVER_PORT) -> socket.socket:
    """A listening socket on every address: dual stack when possible, else IPv4."""
    try:
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    except OSError as exc:  # kernel built or booted without IPv6
        logger.info("IPv6 unavailable, listening on IPv4 only", error=str(exc))
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", port))  # noqa: S104 - the server listens on every interface
    else:
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("::", port))
    sock.listen(_BACKLOG)
    sock.set_inheritable(True)
    return sock


def main() -> None:
    sock = listening_socket()
    config = uvicorn.Config(
        "app.main:app",
        proxy_headers=False,
        timeout_graceful_shutdown=SERVER_SHUTDOWN_GRACE_SECONDS,
    )
    uvicorn.Server(config).run(sockets=[sock])


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    main()
