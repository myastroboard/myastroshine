"""StarDetectionService - per-star blob detection for the star-reduction pipeline.

Isolates compact bright features from the smoothly varying background with a
white top-hat (the same pre-filter the old global star-reduction blend used),
then finds each connected bright region as one star. Runs at native
resolution: an earlier version detected on a downscaled copy to keep
`blob_dog`'s multi-scale search inside the performance budget, but the
anti-aliasing from that downscale routinely erased small/faint stars before
detection ever saw them - visibly under-catching a real, busy star field.
`cv2.connectedComponentsWithStats` is a single near-linear pass, cheap enough
at full 24MP resolution that no downscale is needed at all. See
docs/ALGORITHMS.md.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

from app.logging_config import get_logger
from app.utils.math_utils import normalize_01

logger = get_logger(__name__)

_STAR_KERNEL_SIZE = 9  # px; compact bright features up to this size read as stars
_COLOR_NDIM = 3
_MIN_RADIUS = 0.5  # px; a single bright pixel is a valid (tiny) star


@dataclass(frozen=True)
class StarSource:
    """One detected star, in pixel coordinates of the image passed to ``detect``."""

    x: float
    y: float
    radius: float


class StarDetectionService:
    """Finds individual stars as bright, compact connected regions."""

    def detect(self, image: np.ndarray, sensitivity: int, max_size: int) -> list[StarSource]:
        """Detect stars in ``image`` (BGR or grayscale ``uint8``).

        ``sensitivity`` (0-100) trades off the brightness threshold applied to
        the isolated top-hat: higher finds fainter, smaller stars. ``max_size``
        (0-100) caps the equivalent radius (from the connected region's pixel
        area) considered a star, so bright diffuse cores (galaxy nuclei,
        nebula knots) aren't picked up as one.
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == _COLOR_NDIM else image
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (_STAR_KERNEL_SIZE, _STAR_KERNEL_SIZE)
        )
        tophat = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, kernel).astype(np.float32)
        if float(tophat.max()) < 1.0:
            return []

        isolated = normalize_01(tophat)
        # Higher sensitivity -> lower threshold -> fainter/smaller points register.
        threshold = 0.5 - (sensitivity / 100.0) * 0.48  # 0.5..0.02
        binary = (isolated >= threshold).astype(np.uint8)
        if not binary.any():
            return []

        max_radius = 1.5 + (max_size / 100.0) * 20.0  # 1.5..21.5 px
        _, _, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)

        stars = []
        for label in range(1, len(stats)):  # label 0 is the background
            area = int(stats[label, cv2.CC_STAT_AREA])
            radius = max(_MIN_RADIUS, math.sqrt(area / math.pi))
            if radius > max_radius:
                continue
            cx, cy = centroids[label]
            stars.append(StarSource(x=float(cx), y=float(cy), radius=radius))
        return stars
