"""Capability probe for the optional external ML engines.

StarNet2 / DeepSNR are operator-installed binaries (see
initial_plan/13_EXTERNAL_ML_ENGINES.md) - nothing ships in the image. This module
answers one question for the Settings panel, the public client config, and the
pipeline: is the configured path a working binary, and is its version one this app
has been tested against?

It runs ``<path> --version`` with a short timeout. Every failure mode is a
structured :class:`~app.models.engines.EngineStatus`, never an exception. Results
are memoised until settings change (``app.utils.app_settings`` clears the cache on
every write / reload), so a newly mounted binary is picked up as soon as the
operator saves the path - and an unconfigured engine (the default) never spawns a
subprocess at all.
"""

from __future__ import annotations

import re
import shutil
import subprocess

from app.constants import (
    DEEPSNR_TESTED_VERSIONS,
    ENGINE_PROBE_TIMEOUT_SECONDS,
    STARNET2_TESTED_VERSIONS,
)
from app.logging_config import get_logger
from app.models.engines import EngineStatus

logger = get_logger(__name__)

_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")

_cache: dict[str, EngineStatus] = {}


def _version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _in_tested_range(version: str, tested: tuple[str, str]) -> bool:
    low, high = tested
    return _version_tuple(low) <= _version_tuple(version) < _version_tuple(high)


def _run_error(path: str, name: str, exc: OSError | subprocess.TimeoutExpired) -> str:
    """A human line for the case where ``--version`` could not even run."""
    if isinstance(exc, FileNotFoundError):
        return f"Not found at {path}"
    if isinstance(exc, PermissionError):
        return f"Not executable: {path}"
    if isinstance(exc, subprocess.TimeoutExpired):
        return f"{name} --version timed out"
    return f"Cannot run {path}: {exc.strerror or exc}"  # wrong architecture, corrupt binary, ...


def _classify(
    completed: subprocess.CompletedProcess[str], tested: tuple[str, str], name: str
) -> EngineStatus:
    """Turn a finished ``--version`` run into an :class:`EngineStatus`."""
    match = _VERSION_RE.search(f"{completed.stdout}\n{completed.stderr}")
    if match is None:
        if completed.returncode != 0:
            return EngineStatus(
                configured=True,
                found=False,
                detail=f"{name} --version failed (exit {completed.returncode})",
            )
        return EngineStatus(
            configured=True, found=True, detail=f"{name} found, but its version was unreadable"
        )

    version = ".".join(match.groups())
    if _in_tested_range(version, tested):
        return EngineStatus(
            configured=True,
            found=True,
            version=version,
            known_good=True,
            detail=f"{name} {version} detected",
        )
    return EngineStatus(
        configured=True,
        found=True,
        version=version,
        known_good=False,
        detail=(
            f"{name} {version} detected - untested "
            f"(tested {tested[0]} up to but not including {tested[1]}), enabled anyway"
        ),
    )


def probe_engine(path: str, tested: tuple[str, str], *, name: str) -> EngineStatus:
    """Probe the binary at ``path`` by running ``--version``. Never raises.

    ``tested`` is the half-open ``(min, max)`` version range this app's CLI
    invocation is known to work with; a binary outside it is still reported as
    ``found`` but not ``known_good``.
    """
    if not path.strip():
        return EngineStatus(configured=False, found=False, detail="No path configured")

    resolved = shutil.which(path) or path
    try:
        completed = subprocess.run(  # noqa: S603 - operator-supplied path, admin-gated setting
            [resolved, "--version"],
            capture_output=True,
            text=True,
            timeout=ENGINE_PROBE_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return EngineStatus(configured=True, found=False, detail=_run_error(path, name, exc))
    return _classify(completed, tested, name)


def get_engine_statuses() -> dict[str, EngineStatus]:
    """Probe every configured engine, memoised until settings change.

    Keys: ``"starnet2"``, ``"deepsnr"``.
    """
    if _cache:
        return dict(_cache)

    from app.utils.app_settings import get_app_settings  # noqa: PLC0415 - avoids an import cycle

    settings = get_app_settings()
    _cache["starnet2"] = probe_engine(
        settings.starnet2_path, STARNET2_TESTED_VERSIONS, name="StarNet2"
    )
    _cache["deepsnr"] = probe_engine(settings.deepsnr_path, DEEPSNR_TESTED_VERSIONS, name="DeepSNR")
    for engine, status in _cache.items():
        if status.configured:
            logger.info("engine probe", engine=engine, found=status.found, detail=status.detail)
    return dict(_cache)


def clear_engine_probe_cache() -> None:
    """Forget the memoised probe results (called on every settings change)."""
    _cache.clear()
