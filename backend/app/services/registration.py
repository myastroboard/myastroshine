"""RegistrationService - align multiple frames (v1.1+).

Feature detection (SIFT or ORB) -> matching (Lowe's ratio) -> RANSAC homography
-> warp to the reference frame. See docs/08 planning notes for the algorithm.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.logging_config import get_logger

if TYPE_CHECKING:
    import numpy as np

logger = get_logger(__name__)


class RegistrationService:
    """Aligns a set of frames onto a reference frame."""

    def __init__(self, detector: str = "orb") -> None:
        self.detector = detector

    def register(
        self, frames: list[np.ndarray], reference_idx: int = 0
    ) -> tuple[list[np.ndarray], list[np.ndarray]]:
        """Return ``(aligned_frames, homographies)``."""
        raise NotImplementedError
