"""CombinationService - combine aligned frames into a composite (v1.1).

Methods: median (default, robust), mean (max SNR, needs CR rejection first),
sigma_clip (adaptive mean, best for large stacks). An optional per-pixel
rejection mask (from :class:`CosmicRayService`) excludes flagged samples.
"""

from __future__ import annotations

import math
from typing import cast

import numpy as np

from app.exceptions import InvalidParameterError
from app.logging_config import get_logger

logger = get_logger(__name__)

_SIGMA_CLIP_SIGMA = 2.5
_SIGMA_CLIP_ITERATIONS = 2


class CombinationService:
    """Stacks aligned frames and estimates the SNR gain."""

    def combine(
        self,
        frames: list[np.ndarray],
        method: str = "median",
        reject_mask: np.ndarray | None = None,
    ) -> np.ndarray:
        """Combine frames using ``median``, ``mean`` or ``sigma_clip``."""
        if not frames:
            raise InvalidParameterError("Cannot combine an empty stack")

        stack = np.stack([f.astype(np.float32) for f in frames])
        if reject_mask is not None:
            stack = np.where(reject_mask, np.nan, stack)

        if method == "median":
            result = np.nanmedian(stack, axis=0)
        elif method == "mean":
            result = np.nanmean(stack, axis=0)
        elif method == "sigma_clip":
            result = self._sigma_clip(stack)
        else:
            raise InvalidParameterError(f"Unknown combination method: {method}")

        result = np.nan_to_num(result, nan=0.0)
        return np.clip(result, 0, 255).astype(np.uint8)

    @staticmethod
    def _sigma_clip(stack: np.ndarray) -> np.ndarray:
        result = np.nanmean(stack, axis=0)
        for _ in range(_SIGMA_CLIP_ITERATIONS):
            std = np.sqrt(np.nanmean((stack - result[np.newaxis]) ** 2, axis=0) + 1e-6)
            within = np.abs(stack - result[np.newaxis]) < (_SIGMA_CLIP_SIGMA * std[np.newaxis])
            kept = np.where(within, stack, np.nan)
            result = np.nan_to_num(np.nanmean(kept, axis=0), nan=float(np.nanmean(result)))
        return cast("np.ndarray", result)

    def estimate_snr_improvement(self, frame_count: int) -> float:
        """Theoretical SNR gain (~sqrt(N))."""
        return math.sqrt(frame_count)
