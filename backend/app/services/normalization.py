"""NormalizationService - equalize background levels across frames (v1.1+)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.logging_config import get_logger

if TYPE_CHECKING:
    import numpy as np

logger = get_logger(__name__)


class NormalizationService:
    """Shifts each frame so its sky background matches a common reference."""

    def normalize_backgrounds(
        self, frames: list[np.ndarray], reference_bg: float | None = None
    ) -> list[np.ndarray]:
        """Return frames normalized to a shared background level."""
        raise NotImplementedError
