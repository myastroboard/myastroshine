"""WebSocket endpoints for real-time job progress.

Mounted at the application root (no ``/api`` prefix) to match the frontend
contract and the nginx ``/ws/`` proxy location.

Flow: send the current job state from the DB (catch-up for late subscribers),
then, if the job is still running, relay progress events from Redis until a
terminal status arrives.
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.dependencies import DbSession
from app.logging_config import get_logger
from app.services import progress
from app.services.job import TERMINAL_STATUSES, JobService

logger = get_logger(__name__)

router = APIRouter(tags=["websockets"])


async def _stream_job(websocket: WebSocket, job_id: str, db: Session) -> None:
    await websocket.accept()

    job = JobService(db).get_or_none(job_id)
    if job is not None:
        await websocket.send_json(JobService.to_event(job))
        if job.status in TERMINAL_STATUSES:
            await websocket.close()
            return
    else:
        await websocket.send_json({"job_id": job_id, "status": "unknown"})

    try:
        async for event in progress.subscribe(job_id):
            await websocket.send_json(event)
            if event.get("status") in TERMINAL_STATUSES:
                break
    except WebSocketDisconnect:
        return
    except Exception as exc:
        logger.debug("progress stream ended", job_id=job_id, error=str(exc))

    await websocket.close()


@router.websocket("/ws/processing-status/{job_id}")
async def processing_status(websocket: WebSocket, job_id: str, db: DbSession) -> None:
    """Stream progress for a single-image processing job."""
    await _stream_job(websocket, job_id, db)


@router.websocket("/ws/stack-status/{job_id}")
async def stack_status(websocket: WebSocket, job_id: str, db: DbSession) -> None:
    """Stream progress for a stacking job."""
    await _stream_job(websocket, job_id, db)
