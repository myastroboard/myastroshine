"""CosmicRayService - detect and reject cosmic ray hits across a stack (v1.1).

Cosmic rays spike a pixel in a single frame. Two strategies:
- Laplacian: fast, flags isolated high-frequency pixels.
- Statistical: per-pixel median + sigma; flag frames deviating > N sigma.
"""

from __future__ import annotations

import cv2
import numpy as np

from app.logging_config import get_logger

logger = get_logger(__name__)

_LAPLACIAN_THRESHOLD = 40.0
_MIN_FRAMES_FOR_STATS = 3
_MIN_ABSOLUTE_DEVIATION = 12.0  # a real cosmic ray is a large spike, not sensor noise


class CosmicRayService:
    """Identifies pixels that spike in a minority of frames."""

    def detect_laplacian(self, frames: list[np.ndarray]) -> np.ndarray:
        """Return a per-pixel boolean mask of likely cosmic rays."""
        stack = np.stack([f.astype(np.float32) for f in frames])
        hit_count = np.zeros(stack.shape[1:], dtype=np.int16)
        for frame in stack:
            response = np.abs(cv2.Laplacian(frame, cv2.CV_32F))
            hit_count += (response > _LAPLACIAN_THRESHOLD).astype(np.int16)
        # a real feature appears in most frames; a cosmic ray in just one or two
        return (hit_count >= 1) & (hit_count <= max(1, len(frames) // 3))

    def build_mask(self, frames: list[np.ndarray], threshold: float = 3.0) -> np.ndarray:
        """Per-sample boolean mask (shape ``(n_frames, h, w, c)``) of outliers.

        A sample is flagged when it deviates more than ``threshold`` robust sigma
        (MAD-based, so a lone cosmic ray does not inflate its own estimate) from
        the per-pixel median across the stack.
        """
        stack = np.stack([f.astype(np.float32) for f in frames])
        if len(frames) < _MIN_FRAMES_FOR_STATS:
            return np.zeros(stack.shape, dtype=bool)

        median = np.median(stack, axis=0)
        deviation = np.abs(stack - median[np.newaxis])
        mad = np.median(deviation, axis=0)
        sigma = 1.4826 * mad + 1e-3  # normal-consistent robust scale
        mask: np.ndarray = (deviation > (threshold * sigma[np.newaxis])) & (
            deviation > _MIN_ABSOLUTE_DEVIATION
        )
        removed = int(mask.sum())
        if removed:
            logger.info("cosmic rays flagged", samples=removed)
        return mask

    def reject_statistical(
        self, frames: list[np.ndarray], threshold: float = 3.0
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return ``(cosmic_mask, combined)`` - the mask plus a clipped mean."""
        stack = np.stack([f.astype(np.float32) for f in frames])
        mask = self.build_mask(frames, threshold)
        kept = np.where(mask, np.nan, stack)
        combined = np.nan_to_num(np.nanmean(kept, axis=0), nan=0.0)
        return mask, np.clip(combined, 0, 255).astype(np.uint8)
