"""Shared machinery for the optional starnetastro.com CLI engines.

StarNet2 (star removal) and DeepSNR (denoise) are the same CLI family: both are
operator-installed and **never bundled** (docs/DEPLOYMENT.md "External ML
engines", THIRD_PARTY.md), both take ``-i -o -q [-s stride] --machine-progress
--version``, both need >= 512 px 8/16-bit input, and both emit a
``starnetastro.cli.progress.v1`` JSON-Lines progress stream on stderr.

This module is the arm's-length subprocess runner (:func:`run_cli`) and the
per-session estimate cache (:class:`ModelEstimateCache`) they share.

Precision matters here: an 8-bit round trip posterises exactly the faint signal
these models exist to recover, and a later stretch or curve makes the banding
visible. ``run_cli`` therefore keeps the caller's depth - ``uint8`` / ``uint16``
go through a TIFF of the same depth, and ``float32`` (linear data, nominal
``[0, 1]``) goes through a 32-bit FITS with ``--linear``, which both tools
support: they apply their own reversible stretch around inference.
:mod:`app.services.external_starless` / :mod:`app.services.external_denoise` are
thin wrappers that add the model-specific blend.
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
from astropy.io import fits

from app.constants import EXTERNAL_ENGINE_MIN_DIMENSION, EXTERNAL_ENGINE_TIMEOUT_SECONDS
from app.logging_config import get_logger
from app.services.storage import StorageService

logger = get_logger(__name__)

#: ``fraction (0..1) -> None`` - reports how far a pass has got.
ProgressCallback = Callable[[float], None]

#: JSON keys a ``--machine-progress`` line might carry a completion value under.
#: Verified 2026-09-09 against StarNet2 2.6.1 / DeepSNR 1.3.1: both emit, on
#: **stderr**, one ``{"schema":"starnetastro.cli.progress.v1","event":
#: "start|progress|finish","stage":"inference","current":N,"total":M,"percent":P}``
#: line per tile, ``P`` a 0-100 float - so ``"percent"`` is the one that hits. The
#: rest are kept as a hedge; an unrecognised line is ignored, so a schema change
#: costs only the live progress bar, never correctness.
_PROGRESS_KEYS = ("percent", "progress", "fraction", "value", "pct", "completed", "done")


class ExternalEngineError(RuntimeError):
    """The external binary could not run or produced nothing usable - the caller
    should fall back to the classical path, not surface this to the client."""


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


def run_cli(
    binary_path: str,
    image: np.ndarray,
    *,
    name: str,
    stride: int = 0,
    extra_args: list[str] | None = None,
    progress_cb: ProgressCallback | None = None,
) -> np.ndarray:
    """Run one starnetastro CLI tool on an image; return its output.

    ``uint8`` / ``uint16`` input is display-referred BGR, exchanged as a TIFF of
    the same depth. ``float32`` input is **linear** data in nominal ``[0, 1]`` (a
    stacked composite, channel order preserved as given - RGB planes for the
    composite), exchanged as a FITS cube and run with ``--linear``. Same shape and
    dtype as the input - a side below the 512 px floor is upscaled to meet it and
    the result scaled back. Raises :class:`ExternalEngineError` on any failure
    (missing binary, non-zero exit, timeout, unreadable output).
    """
    height, width = image.shape[:2]
    scale = EXTERNAL_ENGINE_MIN_DIMENSION / min(height, width)
    if scale > 1.0:
        upscaled = cv2.resize(
            image, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_CUBIC
        )
        out = _invoke(binary_path, upscaled, name, stride, extra_args or [], progress_cb)
        return cv2.resize(out, (width, height), interpolation=cv2.INTER_AREA)
    return _invoke(binary_path, image, name, stride, extra_args or [], progress_cb)


def _invoke(
    binary_path: str,
    image: np.ndarray,
    name: str,
    stride: int,
    extra_args: list[str],
    progress_cb: ProgressCallback | None,
) -> np.ndarray:
    linear = image.dtype == np.float32
    suffix = ".fits" if linear else ".tif"
    with tempfile.TemporaryDirectory(prefix="onnx-engine-") as tmp:
        in_path = Path(tmp) / f"in{suffix}"
        out_path = Path(tmp) / f"out{suffix}"
        _write_input(in_path, image, name)

        cmd = [binary_path, "-i", str(in_path), "-o", str(out_path), "-q", *extra_args]
        if linear:
            cmd.append("--linear")
        if stride:
            cmd += ["-s", str(stride)]

        if progress_cb is None:
            _run_blocking(cmd, name)
        else:
            _run_streaming([*cmd, "--machine-progress"], name, progress_cb)

        if not out_path.exists():
            raise ExternalEngineError(f"{name} exited cleanly but wrote no output")
        result = _read_output(out_path, image.dtype)

    if result is None:
        raise ExternalEngineError(f"{name} output was unreadable")
    if result.shape != image.shape:
        result = cv2.resize(result, (image.shape[1], image.shape[0]), interpolation=cv2.INTER_AREA)
    return result


def cast_like(reference: np.ndarray, values: np.ndarray) -> np.ndarray:
    """``values`` clipped and cast to ``reference``'s dtype and full-scale range.

    Integer dtypes clip to ``[0, max]`` and round; ``float32`` clips at 0 only
    (linear data may legitimately exceed 1).
    """
    cast: np.ndarray
    if reference.dtype.kind == "u":
        top = _int_max(reference.dtype)
        cast = np.clip(np.rint(values), 0, top).astype(reference.dtype)
    else:
        cast = np.clip(values, 0.0, None).astype(reference.dtype)
    return cast


def _int_max(dtype: np.dtype) -> int:
    """Full-scale value of an unsigned integer dtype."""
    return int(np.iinfo(dtype.type).max)


def lerp_like(image: np.ndarray, estimate: np.ndarray, weight: float) -> np.ndarray:
    """``image * (1 - weight) + estimate * weight``, in ``image``'s dtype."""
    blended = image.astype(np.float32) * (1.0 - weight) + estimate.astype(np.float32) * weight
    return cast_like(image, blended)


def _write_input(path: Path, image: np.ndarray, name: str) -> None:
    if image.dtype == np.float32:
        # Both tools reject float FITS outside [0, 1]; a stacked composite's
        # brightest star cores can sit a hair above it.
        cube = np.clip(np.moveaxis(image, -1, 0) if image.ndim == 3 else image, 0.0, 1.0)  # noqa: PLR2004
        try:
            fits.PrimaryHDU(np.ascontiguousarray(cube, dtype=np.float32)).writeto(path)
        except OSError as exc:
            raise ExternalEngineError(f"could not write the {name} input FITS") from exc
        return
    # cv2 encodes BGR -> RGB for TIFF, so the tool sees correct colour and
    # cv2.imread gives BGR back: the round trip is identity, at the input's depth.
    if not cv2.imwrite(str(path), image):
        raise ExternalEngineError(f"could not write the {name} input TIFF")


def _read_output(path: Path, dtype: np.dtype) -> np.ndarray | None:
    if dtype == np.float32:
        try:
            with fits.open(path, memmap=False) as hdul:
                data = next((h.data for h in hdul if h.data is not None), None)
        except OSError:
            return None
        if data is None:
            return None
        array = np.asarray(data, dtype=np.float32)
        return np.ascontiguousarray(np.moveaxis(array, 0, -1)) if array.ndim == 3 else array  # noqa: PLR2004
    result = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if result is None:
        return None
    if result.ndim == 2:  # noqa: PLR2004 - a mono output for a colour input
        result = cv2.cvtColor(result, cv2.COLOR_GRAY2BGR)
    if result.dtype != dtype:  # the tool promoted/demoted depth - bring it back
        top = _int_max(dtype)
        scale = top / _int_max(result.dtype) if result.dtype.kind == "u" else 1.0
        result = np.clip(np.rint(result.astype(np.float64) * scale), 0, top).astype(dtype)
    typed: np.ndarray = result
    return typed


def _run_blocking(cmd: list[str], name: str) -> None:
    """Run to completion, capturing output - used when nobody wants progress."""
    try:
        completed = subprocess.run(  # noqa: S603 - operator-supplied path, admin-gated
            cmd,
            capture_output=True,
            text=True,
            timeout=EXTERNAL_ENGINE_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ExternalEngineError(f"{name} did not run: {exc}") from exc
    if completed.returncode != 0:
        tail = (completed.stderr or completed.stdout or "").strip()[-400:]
        raise ExternalEngineError(f"{name} exited {completed.returncode}: {tail or 'no output'}")


def _run_streaming(cmd: list[str], name: str, progress_cb: ProgressCallback) -> None:
    """Stream output, forwarding each ``--machine-progress`` line to the callback.

    The read loop runs on the calling thread (so the callback's job / Redis writes
    stay on the thread that owns the DB session); a one-shot timer is the only
    other thread and it just kills a runaway process. Progress is on stderr, which
    is merged into the read pipe.
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
        raise ExternalEngineError(f"{name} did not run: {exc}") from exc

    timed_out = threading.Event()

    def _kill() -> None:
        timed_out.set()
        proc.kill()

    watchdog = threading.Timer(EXTERNAL_ENGINE_TIMEOUT_SECONDS, _kill)
    watchdog.start()
    tail: deque[str] = deque(maxlen=20)
    try:
        for line in proc.stdout or ():
            tail.append(line.rstrip())
            fraction = _parse_progress(line)
            if fraction is not None:
                progress_cb(fraction)
        returncode = proc.wait()
    finally:
        watchdog.cancel()

    if timed_out.is_set():
        raise ExternalEngineError(f"{name} timed out after {EXTERNAL_ENGINE_TIMEOUT_SECONDS}s")
    if returncode != 0:
        joined = " | ".join(tail)[-400:]
        raise ExternalEngineError(f"{name} exited {returncode}: {joined or 'no output'}")


class ModelEstimateCache:
    """Per-session store for an external engine's output estimate.

    The editor re-runs the whole pipeline on every slider move; an ML pass is
    seconds to minutes. Keying on the *pixels* fed to the stage (which already
    fold in every upstream stage) plus the engine settings means an edit that
    does not touch those reuses the estimate, and only a change that alters the
    input or the engine settings pays for a new pass. Entries live in the session
    directory and vanish with it on cleanup.
    """

    def __init__(self, storage: StorageService, session_id: str, name: str) -> None:
        self._dir = storage.session_dir(session_id, create=True) / f"{name}_cache"
        self._name = name

    def get_or_compute(
        self, image: np.ndarray, key_parts: dict[str, Any], compute: Callable[[], np.ndarray]
    ) -> np.ndarray:
        digest = hashlib.sha1(  # a cache key, not a security primitive
            image.tobytes() + str(image.dtype).encode() + repr(sorted(key_parts.items())).encode(),
            usedforsecurity=False,
        ).hexdigest()[:16]
        # .npy, not an image format: lossless at any depth (a 16-bit or float
        # estimate must come back bit-identical, not re-quantised).
        path = self._dir / f"{digest}.npy"

        if path.exists():
            cached: np.ndarray | None
            try:
                cached = np.load(path, allow_pickle=False)
            except OSError, ValueError:
                cached = None
            if cached is not None and cached.shape == image.shape and cached.dtype == image.dtype:
                logger.info("engine cache hit", engine=self._name, key=digest)
                return cached

        result = compute()
        self._dir.mkdir(parents=True, exist_ok=True)
        np.save(path, result, allow_pickle=False)
        logger.info("engine cache store", engine=self._name, key=digest)
        return result
