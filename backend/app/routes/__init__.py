"""HTTP and WebSocket routers.

Routers may import from ``app.services``; services must not import routers.

Submodules are imported here so ``from app.routes import upload, processing, ...``
resolves for every tool (and so ``app.main`` has a single import site).
"""

from app.routes import (
    admin,
    astrodex,
    depth_shift,
    download,
    health,
    presets,
    processing,
    stack,
    tokens,
    upload,
    websockets,
)

__all__ = [
    "admin",
    "astrodex",
    "depth_shift",
    "download",
    "health",
    "presets",
    "processing",
    "stack",
    "tokens",
    "upload",
    "websockets",
]
