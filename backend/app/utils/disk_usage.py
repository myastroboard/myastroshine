"""Disk-usage reporting for the health check and the admin Settings panel.

The stacking folder-watch mode (``app.services.stack_watch``) is meant to run
unattended on a NAS for hours - a filling data volume should be visible before
it becomes an outage, not discovered later in a "disk full" error in the logs.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from app.config import get_settings
from app.types import JsonDict


def volume_usage() -> JsonDict:
    """Total/used/free bytes for the filesystem ``DATA_DIR`` lives on.

    A single ``shutil.disk_usage`` syscall - cheap enough to compute on every
    ``/api/health`` hit.
    """
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(settings.data_dir)
    return {"total_bytes": usage.total, "used_bytes": usage.used, "free_bytes": usage.free}


def _dir_size(path: Path, *, exclude: Path | None = None) -> int:
    if not path.exists():
        return 0
    return sum(
        f.stat().st_size
        for f in path.rglob("*")
        if f.is_file() and (exclude is None or exclude not in f.parents)
    )


def data_breakdown() -> JsonDict:
    """How ``DATA_DIR``'s own bytes split by what put them there.

    Not the filesystem-level ``volume_usage`` above - this walks the app's own
    directories. ``StorageService`` stores a stack's working files under
    ``images_dir/stacks/`` (not the sibling ``Settings.stacks_dir``, which
    ``ensure_data_dirs`` creates but nothing else touches) - the "images" and
    "stacks" buckets below reflect that real layout, not the settings property
    name, so they don't double-count each other.
    """
    settings = get_settings()
    stacks_dir = settings.images_dir / "stacks"
    logs_bytes = sum(
        p.stat().st_size
        for pattern in (f"{settings.log_file.name}*", f"{settings.worker_log_file.name}*")
        for p in settings.data_dir.glob(pattern)
        if p.is_file()
    )
    return {
        "images_bytes": _dir_size(settings.images_dir, exclude=stacks_dir),
        "stacks_bytes": _dir_size(stacks_dir),
        "db_bytes": _dir_size(settings.db_dir),
        "logs_bytes": logs_bytes,
    }
