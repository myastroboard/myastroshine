"""StarlessService - split stars from nebulosity, then recombine them (v0.3).

The classic deep-sky workflow: pull the stars out so the starless image can be
stretched / sharpened / denoised hard without bloating the stars, then screen-
blend the stars back at an adjustable strength. Detection is shared with star
reduction (:class:`StarDetectionService`); this service owns the estimate of
what sits under the stars and the recombination. See docs/ALGORITHMS.md
"Star removal (starless)".
"""

from __future__ import annotations

from typing import cast

import cv2
import numpy as np

from app.logging_config import get_logger
from app.services.star_detection import StarDetectionService
from app.utils.math_utils import to_uint8

logger = get_logger(__name__)

# Circle drawn per detected star. Generous - the estimate under the mask is a
# smoothed, star-free version of the surrounding nebula, so an oversized mask
# only softens the nebula slightly there, whereas an undersized one leaves a
# bright core and a dark halo ring (the classic bad starless artifact). Star
# reduction can afford 1.6x because it only shrinks; removal has to clear the
# whole star plus its glow.
_STAR_MARGIN = 3.0
_MIN_MASK_RADIUS = 4  # px; even a 1px detection needs a real footprint cleared
_MASK_FEATHER_SIGMA = 2.5
# The starless estimate: a two-pass median blur on a downscaled copy. A median
# window rejects stars as outliers even where they crowd 30-40% of it, so it
# holds up on a dense Milky Way field where an opening / geodesic reconstruction
# (tried first) left a blotchy mesh of star-blob remnants; two passes flatten
# the crowded case further. Runs downscaled - the nebula under a star is
# low-frequency, and it only fills the feathered star mask anyway.
_ESTIMATE_MAX_SIZE = 520  # small: a dense faint-star field only smooths out once
# the stars are near sub-pixel, and the estimate only fills the feathered mask
_ESTIMATE_MEDIAN_PASSES = 2
_ESTIMATE_KERNEL_SCALE = 3.0  # median window (at the downscale) vs. the largest star
_ESTIMATE_SMOOTH_SIGMA = 3.0  # tidies the upscale seam and the last of the field
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
        fully star-free estimate, so a lower value thins the field rather than
        clearing it. ``stars_layer`` is the removed flux on black, ready for
        :meth:`recombine`. With no stars detected the image is returned
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

        Two passes of a median blur on a downscaled copy: the median window is
        sized past the largest maskable star, so a star is an outlier the median
        rejects - it survives even a dense field where stars crowd a big
        fraction of the window, which a morphological opening / reconstruction
        does not (that left a blotchy mesh of star remnants on a real Milky Way
        field). The result is smooth and low-frequency, which is all a fill
        under a feathered star mask needs.
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
            else image.copy()
        )
        max_radius = 1.5 + (max_size / 100.0) * 20.0  # mirrors StarDetectionService.detect()
        kernel = round(max_radius * min(scale, 1.0) * _ESTIMATE_KERNEL_SCALE)
        kernel = min(max(5, kernel | 1), 2 * min(small.shape[:2]) - 1)  # odd, >=5, fits

        for _ in range(_ESTIMATE_MEDIAN_PASSES):
            small = cv2.medianBlur(small, kernel)
        small = cv2.GaussianBlur(small, (0, 0), sigmaX=_ESTIMATE_SMOOTH_SIGMA)

        if scale < 1.0:
            return cast(
                "np.ndarray",
                cv2.resize(small, (width, height), interpolation=cv2.INTER_LINEAR),
            )
        return small

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
