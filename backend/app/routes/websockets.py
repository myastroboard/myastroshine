"""WebSocket endpoints for real-time job progress.

Mounted at the application root (no ``/api`` prefix) to match the frontend
contract and the nginx ``/ws/`` proxy location.

Flow: send the current job state from the DB (catch-up for late subscribers),
then, if the job is still running, relay progress events from Redis until a
terminal status arrives.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.db import database
from app.logging_config import get_logger
from app.services import progress
from app.services.job import TERMINAL_STATUSES, JobService

logger = get_logger(__name__)

router = APIRouter(tags=["websockets"])


def _catch_up(job_id: str) -> tuple[dict[str, Any], bool]:
    """The current job event and whether it is terminal.

    Read with a short-lived session that hands its pooled connection straight
    back. A progress socket can stay open for minutes; holding a DB connection
    open that whole time exhausts the pool once a handful of them are live (a
    burst of edits opens one socket per job).
    """
    with database.SessionLocal() as db:
        job = JobService(db).get_or_none(job_id)
        if job is None:
            return {"job_id": job_id, "status": "unknown"}, False
        return JobService.to_event(job), job.status in TERMINAL_STATUSES


async def _stream_job(websocket: WebSocket, job_id: str) -> None:
    await websocket.accept()

    event, terminal = _catch_up(job_id)
    await websocket.send_json(event)
    if terminal:
        await websocket.close()
        return

    try:
        async for update in progress.subscribe(job_id):
            await websocket.send_json(update)
            if update.get("status") in TERMINAL_STATUSES:
                break
    except WebSocketDisconnect:
        return
    except Exception as exc:
        logger.debug("progress stream ended", job_id=job_id, error=str(exc))

    await websocket.close()


@router.websocket("/ws/processing-status/{job_id}")
async def processing_status(websocket: WebSocket, job_id: str) -> None:
    """Stream progress for a single-image processing job."""
    await _stream_job(websocket, job_id)


@router.websocket("/ws/stack-status/{job_id}")
async def stack_status(websocket: WebSocket, job_id: str) -> None:
    """Stream progress for a stacking job."""
    await _stream_job(websocket, job_id)
