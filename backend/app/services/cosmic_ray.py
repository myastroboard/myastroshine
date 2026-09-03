"""CosmicRayService - detect and reject cosmic ray hits (v1.1+).

Two strategies: fast Laplacian outlier detection, and statistical (sigma) outlier
rejection with iterative sigma-clipping.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.logging_config import get_logger

if TYPE_CHECKING:
    import numpy as np

logger = get_logger(__name__)


class CosmicRayService:
    """Identifies pixels spiking in a minority of frames."""

    def detect_laplacian(self, frames: list[np.ndarray]) -> np.ndarray:
        """Fast per-pixel cosmic ray mask via Laplacian response."""
        raise NotImplementedError

    def reject_statistical(
        self, frames: list[np.ndarray], threshold: float = 3.0
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return ``(cosmic_mask, combined)`` using sigma-based rejection."""
        raise NotImplementedError
