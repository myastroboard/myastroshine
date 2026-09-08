"""StarlessService - split stars from nebulosity, then recombine them (v0.3).

The classic deep-sky workflow: pull the stars out so the starless image can be
stretched / sharpened / denoised hard without bloating the stars, then screen-
blend the stars back at an adjustable strength. Detection is shared with star
reduction (:class:`StarDetectionService`); this service owns the reconstruction
of what sits under the stars and the recombination. See docs/ALGORITHMS.md
"Star removal (starless)".
"""

from __future__ import annotations

import math
from typing import cast

import cv2
import numpy as np
from skimage.morphology import reconstruction

from app.logging_config import get_logger
from app.services.star_detection import StarDetectionService
from app.utils.math_utils import to_uint8

logger = get_logger(__name__)

# Circle drawn per detected star. Generous - the reconstruction estimate under
# the mask *is* the surrounding nebula continued inward, so an oversized mask
# only softens the nebula slightly there, whereas an undersized one leaves a
# bright core and a dark halo ring (the classic bad starless artifact). Star
# reduction can afford 1.6x because it only shrinks; removal has to clear the
# whole star plus its glow.
_STAR_MARGIN = 3.0
_MIN_MASK_RADIUS = 4  # px; even a 1px detection needs a real footprint cleared
_MASK_FEATHER_SIGMA = 2.5
# The star estimate (opening by reconstruction) runs on a downscaled copy: the
# nebula under a star is low-frequency, and a full-res geodesic reconstruction
# at 24MP would cost seconds. 640px keeps small-scale nebula structure while
# staying cheap.
_ESTIMATE_MAX_SIZE = 640
_ERODE_DISK_SCALE = 1.6  # erosion radius (at the downscale) vs. the largest star
# Where the image still rises well above the starless estimate *next to* a
# detected star, that star is bloated past its circle - grow the mask to cover
# it. Bounded to a neighbourhood of the detected stars so an undetected faint
# star or a small nebula knot elsewhere is left alone (that is what the
# sensitivity control is for). Threshold in 0-255 luma-difference units.
_EXCESS_THRESHOLD = 8.0
_EXCESS_DILATE_PX = 2
_BLOAT_REACH_PX = 10  # how far past a star's own circle the bloat grow can extend


class StarlessService:
    """Removes detected stars from an image and blends them back on request."""

    def __init__(self, detector: StarDetectionService) -> None:
        self._detector = detector

    def split(
        self,
        image: np.ndarray,
        sensitivity: int,
        max_size: int,
        removal_amount: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return ``(starless, stars_layer)`` for a BGR ``uint8`` image.

        ``removal_amount`` (1-100) linearly blends between the original and the
        fully star-free reconstruction, so a lower value thins the field rather
        than clearing it. ``stars_layer`` is the removed flux on black, ready
        for :meth:`recombine`. With no stars detected the image is returned
        unchanged alongside an all-black layer.
        """
        stars = self._detector.detect(image, sensitivity, max_size)
        if not stars:
            return image, np.zeros_like(image)

        estimate = self._starless_estimate(image, max_size)

        height, width = image.shape[:2]
        mask = np.zeros((height, width), dtype=np.uint8)
        for star in stars:
            radius = max(_MIN_MASK_RADIUS, round(star.radius * _STAR_MARGIN))
            cv2.circle(mask, (round(star.x), round(star.y)), radius, 255, thickness=-1)
        mask = self._grow_over_bloated_stars(image, estimate, mask)

        weight = cv2.GaussianBlur(
            mask.astype(np.float32) / 255.0, (0, 0), sigmaX=_MASK_FEATHER_SIGMA
        )
        weight = np.clip(weight, 0.0, 1.0)[:, :, np.newaxis] * (removal_amount / 100.0)

        starless = to_uint8(
            image.astype(np.float32) * (1.0 - weight) + estimate.astype(np.float32) * weight
        )
        stars_layer = to_uint8(image.astype(np.int16) - starless.astype(np.int16))
        logger.info("starless split", stars=len(stars), removal=removal_amount)
        return starless, stars_layer

    def _starless_estimate(self, image: np.ndarray, max_size: int) -> np.ndarray:
        """What the nebulosity looks like with the stars gone.

        Opening by reconstruction (erode, then geodesic dilation back under the
        original) removes every bright feature smaller than the erosion element
        while keeping the exact level and shape of everything larger - so it
        follows the nebula's own gradient inward with no plateau or ring, unlike
        a plain opening or an inpaint fill. Runs per channel on a downscaled
        copy, then resized back up.
        """
        height, width = image.shape[:2]
        scale = _ESTIMATE_MAX_SIZE / max(height, width)
        small = (
            cv2.resize(
                image,
                (round(width * scale), round(height * scale)),
                interpolation=cv2.INTER_AREA,
            )
            if scale < 1.0
            else image
        )
        max_radius = 1.5 + (max_size / 100.0) * 20.0  # mirrors StarDetectionService.detect()
        disk_radius = max(2, math.ceil(max_radius * min(scale, 1.0) * _ERODE_DISK_SCALE))
        element = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (disk_radius * 2 + 1, disk_radius * 2 + 1)
        )

        opened = np.empty_like(small)
        for channel in range(small.shape[2]):
            plane = small[:, :, channel]
            seed = cv2.erode(plane, element)
            opened[:, :, channel] = reconstruction(seed, plane, method="dilation").astype(np.uint8)

        if scale < 1.0:
            return cast(
                "np.ndarray",
                cv2.resize(opened, (width, height), interpolation=cv2.INTER_LINEAR),
            )
        return opened

    @staticmethod
    def _grow_over_bloated_stars(
        image: np.ndarray, estimate: np.ndarray, mask: np.ndarray
    ) -> np.ndarray:
        """Add to the mask wherever the image still sits well above the starless
        estimate *and* that spot is right next to a star already masked - a
        bright star bloated past its circle, or its glow. Stays out of the rest
        of the frame so faint stars and nebula knots are the sensitivity
        control's business, not this."""
        excess = cv2.cvtColor(cv2.subtract(image, estimate), cv2.COLOR_BGR2GRAY)
        bloated: np.ndarray = (excess > _EXCESS_THRESHOLD).astype(np.uint8) * 255

        reach = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (_BLOAT_REACH_PX * 2 + 1, _BLOAT_REACH_PX * 2 + 1)
        )
        near_a_star = cv2.dilate(mask, reach)
        bloated = cv2.bitwise_and(bloated, near_a_star)

        smooth = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (_EXCESS_DILATE_PX * 2 + 1, _EXCESS_DILATE_PX * 2 + 1)
        )
        bloated = cv2.morphologyEx(bloated, cv2.MORPH_CLOSE, smooth)
        return cast("np.ndarray", cv2.max(mask, bloated))

    def recombine(
        self, starless: np.ndarray, stars_layer: np.ndarray, recombine_amount: int
    ) -> np.ndarray:
        """Screen-blend ``stars_layer`` back onto a processed starless image.

        ``recombine_amount`` (0-100) scales the star flux before the blend; 0
        returns the starless image untouched. A screen blend (not a plain add)
        because starlight is additive but must not clip the nebulosity it lands
        on. Stars come back tighter and a touch dimmer than a normal edit would
        leave them - that is the point of working starless - so the control
        goes to 100 for a straight restore and beyond-typical values are not
        needed.
        """
        if recombine_amount <= 0:
            return starless
        stars = stars_layer.astype(np.float32) * (recombine_amount / 100.0)
        base = starless.astype(np.float32)
        blended = 255.0 - (255.0 - base) * (255.0 - stars) / 255.0
        return to_uint8(blended)
