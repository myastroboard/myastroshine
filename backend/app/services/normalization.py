"""NormalizationService - equalise background levels across frames (v1.1).

Cloud cover and atmospheric extinction shift the sky background between frames;
this brings them all to a common level before combination.
"""

from __future__ import annotations

import numpy as np

from app.logging_config import get_logger

logger = get_logger(__name__)

_BORDER = 32  # px of image edge sampled as "sky background"


def _background_level(frame: np.ndarray) -> float:
    edges = np.concatenate(
        [
            frame[:_BORDER, :].reshape(-1),
            frame[-_BORDER:, :].reshape(-1),
            frame[:, :_BORDER].reshape(-1),
            frame[:, -_BORDER:].reshape(-1),
        ]
    )
    return float(np.median(edges))


class NormalizationService:
    """Shifts each frame so its sky background matches a shared reference."""

    def normalize_backgrounds(
        self, frames: list[np.ndarray], reference_bg: float | None = None
    ) -> list[np.ndarray]:
        if not frames:
            return []
        levels = [_background_level(frame) for frame in frames]
        target = reference_bg if reference_bg is not None else float(np.median(levels))

        out: list[np.ndarray] = []
        for frame, level in zip(frames, levels, strict=True):
            shifted = frame.astype(np.float32) + (target - level)
            out.append(np.clip(shifted, 0, 255).astype(np.uint8))
        logger.debug("backgrounds normalised", target=round(target, 1), n=len(frames))
        return out
