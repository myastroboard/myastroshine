"""StarNet2-backed star/nebula split - a drop-in for :class:`StarlessService`.

Optional quality tier for star removal (initial_plan/13_EXTERNAL_ML_ENGINES.md).
The StarNet2 binary is operator-installed and **never bundled**; this module only
shells out to it. Everything here is arm's-length: write a TIFF, run the process,
read a TIFF back - no linking, no import of the tool's code.

:meth:`ExternalStarlessService.run_model` is the expensive part (a full-resolution
CPU pass is minutes) and the unit the cache in :class:`StarlessModelCache` stores.
:func:`blend_starless` then applies ``removal_amount`` exactly the way
:meth:`StarlessService.split` does, so the 0-100 control means the same thing on
both engines and changing only its strength never re-invokes the binary.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import threading
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from app.constants import STARNET2_MIN_DIMENSION, STARNET2_RUN_TIMEOUT_SECONDS
from app.logging_config import get_logger
from app.services.storage import StorageService
from app.utils.math_utils import to_uint8

logger = get_logger(__name__)

#: ``(image, sensitivity, max_size, removal_amount) -> (starless, stars_layer)`` -
#: the shape the pipeline's split step calls, shared with ``StarlessService.split``.
StarlessSplitFn = Callable[[np.ndarray, int, int, int], tuple[np.ndarray, np.ndarray]]

#: ``fraction (0..1) -> None`` - reports how far a StarNet2 pass has got.
ProgressCallback = Callable[[float], None]

#: JSON keys a ``--machine-progress`` line might carry a completion value under.
#: StarNet2's exact schema is not pinned here (it is part of the pre-merge
#: verification) - an unrecognised line is ignored, so a format change costs only
#: the live progress bar, never correctness.
_PROGRESS_KEYS = ("progress", "percent", "fraction", "value", "pct", "completed", "done")


class ExternalStarlessError(RuntimeError):
    """StarNet2 could not run or produced nothing usable - the caller should
    fall back to the classical split, not surface this to the client."""


def _parse_progress(line: str) -> float | None:
    """Best-effort read of one ``--machine-progress`` line into a 0..1 fraction."""
    stripped = line.strip()
    if not stripped.startswith("{"):
        return None
    try:
        payload = json.loads(stripped)
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    for key in _PROGRESS_KEYS:
        raw = payload.get(key)
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            continue
        value = float(raw)
        return max(0.0, min(1.0, value / 100.0 if value > 1.0 else value))
    return None


def blend_starless(
    image: np.ndarray, starless_estimate: np.ndarray, removal_amount: int
) -> tuple[np.ndarray, np.ndarray]:
    """Apply ``removal_amount`` (1-100) to a full-frame star-free estimate.

    Mirrors :meth:`StarlessService.split`'s final blend: a lower value thins the
    star field rather than clearing it, and ``stars_layer`` is the removed flux on
    black, ready for :meth:`StarlessService.recombine`.
    """
    weight = max(0, min(100, removal_amount)) / 100.0
    starless = to_uint8(
        image.astype(np.float32) * (1.0 - weight)
        + starless_estimate.astype(np.float32) * weight
    )
    stars_layer = to_uint8(image.astype(np.int16) - starless.astype(np.int16))
    return starless, stars_layer


class ExternalStarlessService:
    """Runs the operator's StarNet2 binary to estimate a star-free image."""

    def __init__(
        self, binary_path: str, stride: int = 0, *, progress_cb: ProgressCallback | None = None
    ) -> None:
        self._path = binary_path
        self._stride = stride
        self._progress_cb = progress_cb

    def split(
        self, image: np.ndarray, _sensitivity: int, _max_size: int, removal_amount: int
    ) -> tuple[np.ndarray, np.ndarray]:
        """``StarlessService.split``-compatible entry point.

        ``sensitivity`` / ``max_size`` are ignored - StarNet2 decides what a star
        is. Detection controls stay meaningful for the classical engine only.
        """
        return blend_starless(image, self.run_model(image), removal_amount)

    def run_model(self, image: np.ndarray) -> np.ndarray:
        """Return StarNet2's star-free estimate for a BGR ``uint8`` image.

        Same shape as the input. Raises :class:`ExternalStarlessError` on any
        failure (missing binary, non-zero exit, timeout, unreadable output).
        """
        height, width = image.shape[:2]
        scale = STARNET2_MIN_DIMENSION / min(height, width)
        if scale > 1.0:  # StarNet2 rejects a side below its minimum
            upscaled = cv2.resize(
                image, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_CUBIC
            )
            estimate = self._invoke(upscaled)
            return cv2.resize(estimate, (width, height), interpolation=cv2.INTER_AREA)
        return self._invoke(image)

    def _invoke(self, image: np.ndarray) -> np.ndarray:
        with tempfile.TemporaryDirectory(prefix="starnet2-") as tmp:
            in_path = Path(tmp) / "in.tif"
            out_path = Path(tmp) / "out.tif"
            # cv2 encodes BGR -> RGB for TIFF, so the tool sees correct colour and
            # cv2.imread gives BGR back: the round trip is identity.
            if not cv2.imwrite(str(in_path), image):
                raise ExternalStarlessError("could not write the StarNet2 input TIFF")

            cmd = [self._path, "-i", str(in_path), "-o", str(out_path), "-q"]
            if self._stride:
                cmd += ["-s", str(self._stride)]

            if self._progress_cb is None:
                self._run_blocking(cmd)
            else:
                self._run_streaming([*cmd, "--machine-progress"])

            if not out_path.exists():
                raise ExternalStarlessError("StarNet2 exited cleanly but wrote no output")
            estimate = cv2.imread(str(out_path), cv2.IMREAD_COLOR)

        if estimate is None:
            raise ExternalStarlessError("StarNet2 output TIFF was unreadable")
        if estimate.shape != image.shape:
            estimate = cv2.resize(
                estimate, (image.shape[1], image.shape[0]), interpolation=cv2.INTER_AREA
            )
        return estimate

    def _run_blocking(self, cmd: list[str]) -> None:
        """Run to completion, capturing output - used when nobody wants progress."""
        try:
            completed = subprocess.run(  # noqa: S603 - operator-supplied path, admin-gated
                cmd,
                capture_output=True,
                text=True,
                timeout=STARNET2_RUN_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ExternalStarlessError(f"StarNet2 did not run: {exc}") from exc
        if completed.returncode != 0:
            tail = (completed.stderr or completed.stdout or "").strip()[-400:]
            raise ExternalStarlessError(
                f"StarNet2 exited {completed.returncode}: {tail or 'no output'}"
            )

    def _run_streaming(self, cmd: list[str]) -> None:
        """Stream stdout, forwarding each ``--machine-progress`` line to the callback.

        The read loop runs on the calling thread (so the callback's job / Redis
        writes stay on the thread that owns the DB session); a one-shot timer is
        the only other thread and it just kills a runaway process.
        """
        try:
            proc = subprocess.Popen(  # noqa: S603 - operator-supplied path, admin-gated
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            raise ExternalStarlessError(f"StarNet2 did not run: {exc}") from exc

        timed_out = threading.Event()

        def _kill() -> None:
            timed_out.set()
            proc.kill()

        watchdog = threading.Timer(STARNET2_RUN_TIMEOUT_SECONDS, _kill)
        watchdog.start()
        tail: deque[str] = deque(maxlen=20)
        try:
            for line in proc.stdout or ():
                tail.append(line.rstrip())
                fraction = _parse_progress(line)
                if fraction is not None and self._progress_cb is not None:
                    self._progress_cb(fraction)
            returncode = proc.wait()
        finally:
            watchdog.cancel()

        if timed_out.is_set():
            raise ExternalStarlessError(
                f"StarNet2 timed out after {STARNET2_RUN_TIMEOUT_SECONDS}s"
            )
        if returncode != 0:
            joined = " | ".join(tail)[-400:]
            raise ExternalStarlessError(f"StarNet2 exited {returncode}: {joined or 'no output'}")


class StarlessModelCache:
    """Per-session store for StarNet2's star-free estimate.

    The editor re-runs the whole pipeline on every slider move; a full-resolution
    StarNet2 pass is minutes. Keying on the *pixels* fed to the split (which already
    fold in every upstream stage) plus the engine settings means a creative-only
    edit - contrast, curves, sharpening - reuses the estimate, and only a change
    that alters the pre-split image or the engine settings pays for a new pass.
    Entries live in the session directory and vanish with it on cleanup.
    """

    def __init__(self, storage: StorageService, session_id: str) -> None:
        self._dir = storage.session_dir(session_id, create=True) / "starless_cache"

    def get_or_compute(
        self, image: np.ndarray, key_parts: dict[str, Any], compute: Callable[[], np.ndarray]
    ) -> np.ndarray:
        digest = hashlib.sha1(  # a cache key, not a security primitive
            image.tobytes() + repr(sorted(key_parts.items())).encode(), usedforsecurity=False
        ).hexdigest()[:16]
        path = self._dir / f"{digest}.png"

        if path.exists():
            cached = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if cached is not None and cached.shape == image.shape:
                logger.info("starless cache hit", key=digest)
                return cached

        result = compute()
        self._dir.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(path), result)
        logger.info("starless cache store", key=digest)
        return result
