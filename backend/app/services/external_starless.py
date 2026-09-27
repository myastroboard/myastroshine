"""StarNet2-backed star/nebula split - a drop-in for :class:`StarlessService`.

Optional quality tier for star removal (docs/ALGORITHMS.md "Quality path"; setup
and licensing in docs/DEPLOYMENT.md and THIRD_PARTY.md). The StarNet2 binary is
operator-installed and **never bundled**; the shared arm's-length runner lives in
:mod:`app.services.external_engine`.

:meth:`ExternalStarlessService.run_model` is the expensive part (a full-resolution
CPU pass is minutes) and the unit :class:`~app.services.external_engine.ModelEstimateCache`
stores. :func:`blend_starless` then applies ``removal_amount`` exactly the way
:meth:`StarlessService.split` does, so the 0-100 control means the same thing on
both engines and changing only its strength never re-invokes the binary.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from app.services.external_engine import ProgressCallback, cast_like, lerp_like, run_cli

#: ``(image, sensitivity, max_size, removal_amount) -> (starless, stars_layer)`` -
#: the shape the pipeline's split step calls, shared with ``StarlessService.split``.
#: The pipeline calls it with BGR ``float32`` ``[0, 1]`` and expects the same back.
StarlessSplitFn = Callable[[np.ndarray, int, int, int], tuple[np.ndarray, np.ndarray]]


def blend_starless(
    image: np.ndarray, starless_estimate: np.ndarray, removal_amount: int
) -> tuple[np.ndarray, np.ndarray]:
    """Apply ``removal_amount`` (1-100) to a full-frame star-free estimate.

    Mirrors :meth:`StarlessService.split`'s final blend: a lower value thins the
    star field rather than clearing it, and ``stars_layer`` is the removed flux on
    black, ready for :meth:`StarlessService.recombine`.
    """
    starless = lerp_like(image, starless_estimate, max(0, min(100, removal_amount)) / 100.0)
    difference = image.astype(np.float32) - starless.astype(np.float32)
    stars_layer = cast_like(image, difference)
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
        """Return StarNet2's star-free estimate, same shape and dtype as ``image``."""
        return run_cli(
            self._path, image, name="StarNet2", stride=self._stride, progress_cb=self._progress_cb
        )
