"""DepthMapService - depth estimation and parallax layer generation.

See docs/DEPTH_SHIFT for the algorithm. v1 uses Sobel-gradient depth; an ML
backend (MiDaS) is planned for v0.2.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.logging_config import get_logger

if TYPE_CHECKING:
    import numpy as np

logger = get_logger(__name__)


class DepthMapService:
    """Estimates a rough depth map and slices it into parallax layers."""

    def estimate_depth(self, image: np.ndarray) -> np.ndarray:
        """Return a 0-255 depth map (255 = near) from image gradients."""
        raise NotImplementedError

    def generate_parallax_layers(
        self, image: np.ndarray, depth_map: np.ndarray, num_layers: int = 7
    ) -> list[np.ndarray]:
        """Segment the depth map into ``num_layers`` BGRA layers, far to near."""
        raise NotImplementedError

    def render_depth_shift(
        self, layers: list[np.ndarray], offset: tuple[float, float], intensity: int
    ) -> np.ndarray:
        """Composite the layers with a parallax offset (server-side preview)."""
        raise NotImplementedError
