"""DepthMapService - gradient-based depth estimation and parallax layers.

v1 estimates depth from edge strength: high-detail regions (stars, structure)
read as near (high value), smooth regions (sky, nebula body) as far. An ML
backend (MiDaS) is planned for v0.2. See docs/ALGORITHMS.md.
"""

from __future__ import annotations

import math
from typing import cast

import cv2
import numpy as np

from app.logging_config import get_logger
from app.models import DepthStatistics, FocusPoint
from app.utils.math_utils import normalize_01, to_uint8

logger = get_logger(__name__)

_NEAR_THRESHOLD = 200  # depth values above this count as "near / detailed"
_COLOR_NDIM = 3
# Equal parts detail-based and position-based depth when a focus point is
# given - a first-pass constant, like other heuristics this session, to
# revisit if real testing shows the parallax centering too strong/weak.
_FOCUS_BLEND_WEIGHT = 0.5


class DepthMapService:
    """Estimates a rough depth map and slices it into parallax layers."""

    def estimate_depth(
        self, image: np.ndarray, focus_point: FocusPoint | None = None
    ) -> np.ndarray:
        """Return a single-channel 0-255 depth map (0 = far, 255 = near).

        With no ``focus_point``, depth is purely gradient/edge-based (detail
        reads as near) - unchanged from before this parameter existed. With
        one, a radial field centered on it (near at the point, far at the
        image's corners) is blended in, so the chosen point - not just
        whatever happens to be detailed - reads as "near" in the parallax.
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == _COLOR_NDIM else image

        sobel_x = np.asarray(cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=5), dtype=np.float64)
        sobel_y = np.asarray(cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=5), dtype=np.float64)
        magnitude = np.sqrt(sobel_x**2 + sobel_y**2)
        gradient_depth = normalize_01(magnitude)

        if focus_point is not None:
            height, width = gray.shape[:2]
            yy, xx = np.mgrid[0:height, 0:width]
            focus_x, focus_y = focus_point.x * width, focus_point.y * height
            max_dist = math.hypot(width, height) / 2
            dist = np.sqrt((xx - focus_x) ** 2 + (yy - focus_y) ** 2)
            radial = 1.0 - np.clip(dist / max_dist, 0.0, 1.0)
            gradient_depth = (
                1.0 - _FOCUS_BLEND_WEIGHT
            ) * gradient_depth + _FOCUS_BLEND_WEIGHT * radial

        depth = to_uint8(gradient_depth * 255.0)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        closed = cv2.morphologyEx(depth, cv2.MORPH_CLOSE, kernel)
        return cast("np.ndarray", cv2.GaussianBlur(closed, (21, 21), 0))

    def generate_parallax_layers(
        self, image: np.ndarray, depth_map: np.ndarray, num_layers: int = 7
    ) -> list[np.ndarray]:
        """Slice the depth map into ``num_layers`` BGRA layers, far (0) to near."""
        layers: list[np.ndarray] = []
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

        for index in range(num_layers):
            lo = index * 256 // num_layers
            hi = (index + 1) * 256 // num_layers - 1
            mask = cv2.inRange(depth_map, lo, max(lo, hi))
            mask = cv2.dilate(mask, kernel, iterations=1)

            layer = cv2.cvtColor(image, cv2.COLOR_BGR2BGRA)
            layer[mask == 0] = (0, 0, 0, 0)
            layer[:, :, 3] = mask
            layers.append(layer)

        return layers

    def depth_statistics(self, depth_map: np.ndarray) -> DepthStatistics:
        """Summarise a depth map for the metadata endpoint."""
        near = float(np.count_nonzero(depth_map >= _NEAR_THRESHOLD)) / depth_map.size
        return DepthStatistics(
            min_depth=int(depth_map.min()),
            max_depth=int(depth_map.max()),
            mean_depth=int(depth_map.mean()),
            median_depth=int(np.median(depth_map)),
            bright_areas_percent=round(near * 100, 1),
        )

    @staticmethod
    def layer_depth_range(index: int, num_layers: int) -> tuple[float, float]:
        """The normalised (0-1) depth band covered by layer ``index``."""
        return (index / num_layers, (index + 1) / num_layers)
