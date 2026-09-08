"""Watch-folder ingest for stacking (``initial_plan/12_STACKING_REBUILD.md`` Phase 5).

A Celery beat task calls :func:`run_watch_tick` on a schedule. When
``stacking_watch_dir`` is set, new image files that land there are ingested into a
rolling "watch" :class:`~app.db.models.StackRecord`; once the folder has been
quiet for ``stacking_watch_idle_minutes`` the stack is processed (if
``stacking_watch_auto_process`` is on) and the next file starts a fresh one.

Seen files are tracked in ``DATA_DIR/stacking_watch_seen.json`` (path -> size:mtime)
so a re-written file is re-ingested and a permanently-broken file is not retried
forever.
"""

from __future__ import annotations

import contextlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import StackRecord
from app.logging_config import get_logger
from app.models import InitiateStackRequest
from app.services.job import JobService
from app.services.session import SessionService
from app.services.stacking import StackingService
from app.services.storage import StorageService
from app.utils.app_settings import get_app_settings
from app.utils.image_utils import SUPPORTED_FORMATS

logger = get_logger(__name__)

_MIN_FRAMES = 2
_SEEN_FILE = "stacking_watch_seen.json"


def _seen_path() -> Path:
    return get_settings().data_dir / _SEEN_FILE


def _load_seen() -> dict[str, str]:
    path = _seen_path()
    if not path.exists():
        return {}
    try:
        data: dict[str, str] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_seen(seen: dict[str, str]) -> None:
    with contextlib.suppress(OSError):
        _seen_path().write_text(json.dumps(seen), encoding="utf-8")


def _fingerprint(path: Path) -> str:
    stat = path.stat()
    return f"{stat.st_size}:{int(stat.st_mtime)}"


def _current_watch_stack(db: Session) -> Any:
    return db.scalars(
        select(StackRecord)
        .where(
            StackRecord.source == "watch",
            StackRecord.status.in_(("waiting_for_frames", "ready")),
        )
        .order_by(StackRecord.created_at.desc())
    ).first()


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def run_watch_tick(db: Session, storage: StorageService) -> dict[str, Any]:
    """One poll of the watch folder. Returns a small status dict for the logs/tests."""
    settings = get_app_settings()
    if not settings.stacking_enabled or not settings.stacking_watch_dir:
        return {"status": "disabled"}
    watch_dir = Path(settings.stacking_watch_dir)
    if not watch_dir.is_dir():
        logger.warning("stacking_watch_dir is not a directory", path=settings.stacking_watch_dir)
        return {"status": "no_dir"}

    seen = _load_seen()
    files = sorted(
        p
        for p in watch_dir.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_FORMATS
    )
    new = [p for p in files if seen.get(str(p)) != _fingerprint(p)]

    stacking = StackingService(db, SessionService(db, storage), storage)

    if new:
        return _ingest(db, storage, stacking, new, seen, settings.stacking_max_frames)

    record = _current_watch_stack(db)
    if record is None or record.received_frames < _MIN_FRAMES:
        return {"status": "idle"}
    idle_for = datetime.now(UTC) - _aware(record.updated_at)
    if (
        settings.stacking_watch_auto_process
        and idle_for > timedelta(minutes=settings.stacking_watch_idle_minutes)
    ):
        stacking.dispatch(record.stack_id, JobService(db))
        logger.info("watch stack auto-processing", stack_id=record.stack_id)
        return {"status": "processing", "stack_id": record.stack_id}
    return {"status": "waiting", "stack_id": record.stack_id, "frames": record.received_frames}


def _ingest(
    db: Session,
    storage: StorageService,
    stacking: StackingService,
    new: list[Path],
    seen: dict[str, str],
    max_frames: int,
) -> dict[str, Any]:
    record = _current_watch_stack(db)
    if record is None:
        record = stacking.initiate(InitiateStackRequest(frame_count=_MIN_FRAMES), source="watch")

    remaining = max_frames - record.received_frames
    batch, overflow = new[:remaining], new[remaining:]
    prepared = []
    for path in batch:
        try:
            prepared.append(stacking.prepare_frame(path.read_bytes(), path.name))
        except Exception as exc:  # one unreadable file must not wedge the watch
            logger.warning("watch: skipping unreadable file", file=path.name, error=str(exc))
        seen[str(path)] = _fingerprint(path)
    for path in overflow:  # mark as seen so we don't rescan them every tick
        seen[str(path)] = _fingerprint(path)

    if prepared:
        start = max(storage.stack_frame_indices(record.stack_id), default=-1) + 1
        stacking.add_frames(record.stack_id, start, prepared)
    _save_seen(seen)
    logger.info(
        "watch ingest",
        stack_id=record.stack_id,
        added=len(prepared),
        overflow=len(overflow),
    )
    return {"status": "ingested", "count": len(prepared), "stack_id": record.stack_id}


