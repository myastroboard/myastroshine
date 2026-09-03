"""CombinationService - combine aligned frames into a composite (v1.1+).

Methods: median (default, robust), mean (max SNR, needs CR rejection first),
sigma-clip (adaptive, best for 20+ frames).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from app.logging_config import get_logger

if TYPE_CHECKING:
    import numpy as np

logger = get_logger(__name__)


class CombinationService:
    """Stacks aligned frames and estimates the SNR gain."""

    def combine(self, frames: list[np.ndarray], method: str = "median") -> np.ndarray:
        """Combine frames using ``median``, ``mean`` or ``sigma_clip``."""
        raise NotImplementedError

    def estimate_snr_improvement(self, frame_count: int) -> float:
        """Theoretical SNR gain (~sqrt(N))."""
        return math.sqrt(frame_count)
