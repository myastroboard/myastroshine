"""Small helpers shared across test modules."""

from __future__ import annotations

import shutil
import subprocess

import cv2
import numpy as np


def translate(image: np.ndarray, dx: float, dy: float) -> np.ndarray:
    """Shift ``image`` by ``(dx, dy)`` pixels, keeping its size."""
    matrix = np.array([[1.0, 0.0, dx], [0.0, 1.0, dy]], dtype=np.float32)
    return cv2.warpAffine(image, matrix, (image.shape[1], image.shape[0]))


def png_bytes(image: np.ndarray) -> bytes:
    ok, buffer = cv2.imencode(".png", image)
    assert ok
    return buffer.tobytes()


# --- fakes for the starnetastro CLI tools (StarNet2 / DeepSNR) -----------------
# No real binary in CI; these stand in for `subprocess.run` / `subprocess.Popen`
# and just copy the input TIFF to the output path.


def engine_image(height: int = 600, width: int = 800, seed: int = 0) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, 256, (height, width, 3), dtype=np.uint8)


def fake_engine_run(*, returncode: int = 0, write_output: bool = True):
    """Stand-in for ``subprocess.run`` (the no-progress path)."""

    def run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if write_output and returncode == 0:
            _copy_output(cmd)
        return subprocess.CompletedProcess(
            cmd, returncode, stdout="", stderr="boom" if returncode else ""
        )

    return run


def _copy_output(cmd: list[str]) -> None:
    """An identity "model": the output file is the input file, byte for byte.

    Works for every exchange format the runner uses (8/16-bit TIFF, float FITS).
    """
    shutil.copyfile(cmd[cmd.index("-i") + 1], cmd[cmd.index("-o") + 1])


def fake_engine_popen(
    *,
    returncode: int = 0,
    write_output: bool = True,
    lines: list[str] | None = None,
    record: list[list[str]] | None = None,
):
    """Stand-in for ``subprocess.Popen`` (the ``--machine-progress`` path)."""
    progress_lines = lines if lines is not None else ['{"percent": 100.0}\n']

    class _Popen:
        #: The most recent instance, for tests that inspect it after the run.
        last: _Popen | None = None

        def __init__(self, cmd: list[str], **_kwargs: object) -> None:
            if record is not None:
                record.append(cmd)
            self.args = cmd
            if write_output and returncode == 0:
                _copy_output(cmd)
            self.stdout = iter(progress_lines)
            self.returncode = returncode
            self.finished = False
            self.killed = False
            _Popen.last = self

        def poll(self) -> int | None:
            return self.returncode if self.finished else None

        def wait(self, timeout: float | None = None) -> int:
            self.finished = True
            return self.returncode

        def kill(self) -> None:
            self.returncode = -9
            self.killed = True

    return _Popen


class ImmediateTimer:
    """``threading.Timer`` stand-in that fires synchronously on ``start()``."""

    def __init__(self, _interval: float, fn) -> None:
        self._fn = fn

    def start(self) -> None:
        self._fn()

    def cancel(self) -> None:
        pass
