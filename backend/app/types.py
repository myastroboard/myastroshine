"""Small shared type aliases used across the backend."""

from __future__ import annotations

from typing import Any

# A JSON-object-shaped dict, as returned by route handlers and passed around
# as loosely-typed payloads (parameters, webhook bodies, metadata).
JsonDict = dict[str, Any]
