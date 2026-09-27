"""DeepSNR-backed denoise - the quality tier for the ``denoise`` stage.

Optional, operator-installed, never bundled (docs/DEPLOYMENT.md "External ML
engines", THIRD_PARTY.md); the shared arm's-length runner lives in
:mod:`app.services.external_engine`. DeepSNR is a NAFNet restoration model tuned
for uncorrelated high-frequency noise in stacked astro data, so the pipeline runs
it **early** - right after the sky/optics corrections, before any tone stretch or
sharpening - and lets the classical ``denoise`` slot no-op. ``denoise`` (1-100)
still sets the strength via :func:`blend_denoise`.
"""

from __future__ import annotations

import numpy as np

from app.services.external_engine import ProgressCallback, lerp_like, run_cli


def blend_denoise(image: np.ndarray, denoised_estimate: np.ndarray, amount: int) -> np.ndarray:
    """Blend ``amount`` (1-100) of DeepSNR's output back over the input.

    Same lerp shape as :func:`app.services.external_starless.blend_starless`, so a
    lower value is a lighter touch and changing only the strength never re-invokes
    the binary.
    """
    return lerp_like(image, denoised_estimate, max(0, min(100, amount)) / 100.0)


class ExternalDenoiseService:
    """Runs the operator's DeepSNR binary to estimate a denoised image."""

    def __init__(
        self, binary_path: str, stride: int = 0, *, progress_cb: ProgressCallback | None = None
    ) -> None:
        self._path = binary_path
        self._stride = stride
        self._progress_cb = progress_cb

    def run_model(self, image: np.ndarray) -> np.ndarray:
        """Return DeepSNR's denoised estimate, same shape and dtype as ``image``.

        A ``float32`` image is linear data (a stacked composite, before the
        stretch - where DeepSNR is meant to run) and goes through ``--linear``;
        an integer image is display-referred (see :func:`run_cli`).
        """
        return run_cli(
            self._path, image, name="DeepSNR", stride=self._stride, progress_cb=self._progress_cb
        )
