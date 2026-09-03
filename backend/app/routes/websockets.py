"""WebSocket endpoints.

Mounted at the application root (no ``/api`` prefix) to match the frontend
contract and the nginx ``/ws/`` proxy location.
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket

from app.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["websockets"])


@router.websocket("/ws/processing-status/{job_id}")
async def processing_status(websocket: WebSocket, job_id: str) -> None:
    """Stream progress updates for a single-image processing job (Sprint 3)."""
    await websocket.accept()
    await websocket.send_json({"job_id": job_id, "status": "not_implemented"})
    await websocket.close()


@router.websocket("/ws/stack-status/{job_id}")
async def stack_status(websocket: WebSocket, job_id: str) -> None:
    """Stream progress updates for a stacking job (Sprint 6)."""
    await websocket.accept()
    await websocket.send_json({"job_id": job_id, "status": "not_implemented"})
    await websocket.close()
