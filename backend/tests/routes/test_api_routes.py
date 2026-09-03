"""Route wiring checks.

Confirms routers are mounted where the spec says. Per-endpoint behaviour is
covered by the dedicated test modules; the still-stubbed endpoints are checked
for their 501 here.
"""

from __future__ import annotations

import pytest

_FAKE_SESSION = "00000000-0000-0000-0000-000000000000"

# Endpoints not yet implemented (later sprints). Bodies are valid so the request
# reaches the handler rather than failing request-model validation first.
NOT_IMPLEMENTED_ENDPOINTS = [
    ("get", "/api/presets", None),
    ("post", "/api/presets", {"name": "x", "parameters": {}}),
    ("post", f"/api/depth-shift/{_FAKE_SESSION}", {}),
    ("get", f"/api/depth-shift/{_FAKE_SESSION}/metadata", None),
    ("post", "/api/stack/initiate", {"frame_count": 3}),
]


def test_openapi_schema_is_served(client) -> None:
    """The OpenAPI schema lists the core API paths."""
    schema = client.get("/openapi.json").json()

    assert "/api/upload" in schema["paths"]
    assert "/api/process/{session_id}" in schema["paths"]
    assert "/api/download/{session_id}" in schema["paths"]
    assert "/api/send-to-astrodex" in schema["paths"]


@pytest.mark.parametrize(("method", "path", "body"), NOT_IMPLEMENTED_ENDPOINTS)
def test_unimplemented_endpoints_return_501(
    client, method: str, path: str, body: dict | None
) -> None:
    """Stub endpoints answer 501 until their sprint lands."""
    call = getattr(client, method)
    response = call(path) if body is None else call(path, json=body)

    assert response.status_code == 501
