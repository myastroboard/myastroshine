"""Route wiring checks.

Confirms routers are mounted where the spec says. Per-endpoint behaviour is
covered by the dedicated test modules.
"""

from __future__ import annotations


def test_openapi_schema_is_served(client) -> None:
    """The OpenAPI schema lists every top-level API path."""
    paths = client.get("/openapi.json").json()["paths"]

    for expected in (
        "/api/upload",
        "/api/process/{session_id}",
        "/api/download/{session_id}",
        "/api/presets",
        "/api/depth-shift/{session_id}",
        "/api/tokens",
        "/api/astrodex/receive",
        "/api/send-to-astrodex",
        "/api/stack/initiate",
        "/api/stack/{stack_id}/process",
    ):
        assert expected in paths, expected
