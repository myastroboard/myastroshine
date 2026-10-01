"""The production entry point: one socket for IPv4 and IPv6, bounded shutdown."""

from __future__ import annotations

import socket
from typing import Any

import pytest

from app import serve


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _connects(family: int, host: str, port: int) -> bool:
    with socket.socket(family, socket.SOCK_STREAM) as client:
        client.settimeout(2)
        try:
            client.connect((host, port))
        except OSError:
            return False
        return True


@pytest.mark.skipif(not socket.has_ipv6, reason="no IPv6 on this host")
def test_one_socket_accepts_ipv4_and_ipv6() -> None:
    port = _free_port()
    sock = serve.listening_socket(port)
    try:
        assert sock.family == socket.AF_INET6
        assert sock.getsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY) == 0
        assert _connects(socket.AF_INET, "127.0.0.1", port)
        assert _connects(socket.AF_INET6, "::1", port)
    finally:
        sock.close()


def test_falls_back_to_ipv4_without_ipv6(monkeypatch: pytest.MonkeyPatch) -> None:
    real_socket = socket.socket

    def no_ipv6(family: int = socket.AF_INET, *args: Any, **kwargs: Any) -> socket.socket:
        if family == socket.AF_INET6:
            raise OSError("Address family not supported by protocol")
        return real_socket(family, *args, **kwargs)

    monkeypatch.setattr(serve.socket, "socket", no_ipv6)
    port = _free_port()
    sock = serve.listening_socket(port)
    try:
        assert sock.family == socket.AF_INET
        assert _connects(socket.AF_INET, "127.0.0.1", port)
    finally:
        sock.close()


def test_main_hands_the_socket_to_uvicorn_with_a_bounded_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}
    fake_socket = object()
    monkeypatch.setattr(serve, "listening_socket", lambda: fake_socket)

    def run(self: Any, sockets: list[object]) -> None:
        seen["sockets"] = sockets
        seen["config"] = self.config

    monkeypatch.setattr(serve.uvicorn.Server, "run", run)

    serve.main()

    assert seen["sockets"] == [fake_socket]
    assert seen["config"].app == "app.main:app"
    assert seen["config"].timeout_graceful_shutdown == serve.SERVER_SHUTDOWN_GRACE_SECONDS
    assert seen["config"].proxy_headers is False
