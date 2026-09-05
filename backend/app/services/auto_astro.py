"""AutoAstroService - one-click adaptive enhancement.

Analyses an image's tone distribution and star density, then proposes a
``ProcessingParameters`` starting point - a computed alternative to the fixed
built-in presets. Scope is deliberately limited to what the histogram / black
point / star density can drive with confidence (tone stretch + star
reduction); saturation, denoise, sharpness, colour, and geometry stay at their
defaults. See docs/ALGORITHMS.md "Auto Astro".
"""

from __future__ import annotations

import math

import cv2
import numpy as np

from app.logging_config import get_logger
from app.models import ProcessingParameters
from app.services.star_detection import StarDetectionService

logger = get_logger(__name__)

_COLOR_NDIM = 3
_MIN_USABLE_RANGE = 10.0  # below this, the frame is too flat to safely stretch
_TARGET_RANGE = 210.0  # aim to fill most, not all, of 0-255 - leaves headroom
_TARGET_BLACK_POINT = 3.0  # near-black, not lifted - a crushed background reads as depth
_HIGHLIGHT_CLIP_THRESHOLD = 250
_SHADOW_CRUSH_THRESHOLD = 5
_SHADOW_CRUSH_BASELINE = 0.3  # deep-sky frames are mostly dark sky already
# `apply_highlights_shadows` weights shadows toward the darkest pixels only
# (`shadow_mask = (1-gray)**2`), so a negative value mostly darkens the empty
# background - not the DSO itself - which is exactly the separation real
# astro processing wants (crush the sky, let the object pop against it).
_DEPTH_SHADOWS = -0.35
# Real star fields span orders of magnitude in density - a single short frame
# might show tens of stars/MP, a deep stack can show 1000+/MP. A linear
# density-to-reduction mapping saturates at the cap for almost any real busy
# field (1000/MP * a linear scale blows past any sane cap immediately),
# defeating "gentle starting point"; log1p keeps it graduated across that
# whole range instead of an on/off switch at "moderately busy or denser".
_STAR_DENSITY_LOG_SCALE = 5.0
_MAX_AUTO_STAR_REDUCTION = 50  # a gentle starting point, not maxed out


class AutoAstroService:
    """Proposes enhancement parameters from an image's own statistics."""

    def __init__(self, star_detector: StarDetectionService) -> None:
        self.star_detector = star_detector

    def suggest_parameters(self, image: np.ndarray) -> ProcessingParameters:
        """Analyse ``image`` (BGR ``uint8``) and propose a parameter set."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == _COLOR_NDIM else image

        contrast, brightness, highlights, shadows = self._suggest_tone(gray)
        star_reduction = self._suggest_star_reduction(image, gray)

        # Round to what the sliders actually step by (2 decimals) - the raw
        # percentile-derived floats have a dozen digits of noise that look
        # broken in the UI and imply far more precision than the heuristic has.
        contrast = round(contrast, 2)
        brightness = round(brightness, 2)
        highlights = round(highlights, 2)
        shadows = round(shadows, 2)

        return ProcessingParameters(
            contrast=contrast,
            brightness=brightness,
            highlights=highlights,
            shadows=shadows,
            star_reduction=star_reduction,
        )

    def _suggest_tone(self, gray: np.ndarray) -> tuple[float, float, float, float]:
        """Stretch the real signal range, then push the DSO and background apart.

        Contrast/brightness alone just fill the tonal range; the depth/pop a
        DSO shot wants comes from treating the background and the object
        differently, not from a single uniform curve - see ``shadows`` and
        ``highlights`` below.
        """
        black_point = float(np.percentile(gray, 0.5))
        white_point = float(np.percentile(gray, 99.5))
        usable_range = white_point - black_point
        if usable_range < _MIN_USABLE_RANGE:
            return 1.0, 0.0, 0.0, 0.0

        contrast = float(np.clip(_TARGET_RANGE / max(usable_range, 1.0), 0.5, 3.0))

        mean = float(gray.mean())
        black_point_after = (black_point - mean) * contrast + mean
        brightness = float(np.clip((_TARGET_BLACK_POINT - black_point_after) / 50.0, -1.0, 1.0))

        # Pull back only if a meaningful fraction is already clipping to
        # white. Deliberately never boosts highlights upward: this pipeline
        # runs `star_reduction` *after* highlights/contrast (see
        # `apply_parameters`), so pushing bright pixels up here blows out
        # stars toward flat, saturated plateaus before the shrink step ever
        # sees them - erosion can't meaningfully shrink a plateau with no
        # gradient left to eat into. A DSO's own brightness comes from the
        # contrast stretch above, not from this.
        clipped_fraction = float((gray >= _HIGHLIGHT_CLIP_THRESHOLD).mean())
        highlights = float(np.clip(-clipped_fraction * 8.0, -1.0, 0.0))

        # Darken the background for separation/depth - unless the frame is
        # already mostly near-black, which reads as a genuinely faint target
        # rather than "background that would benefit from more crush".
        crushed_fraction = float((gray <= _SHADOW_CRUSH_THRESHOLD).mean())
        shadows = _DEPTH_SHADOWS if crushed_fraction < _SHADOW_CRUSH_BASELINE * 2 else 0.0

        return contrast, brightness, highlights, shadows

    def _suggest_star_reduction(self, image: np.ndarray, gray: np.ndarray) -> int:
        stars = self.star_detector.detect(image, sensitivity=50, max_size=30)
        megapixels = max(gray.size / 1_000_000.0, 0.1)
        density = len(stars) / megapixels
        scaled = _STAR_DENSITY_LOG_SCALE * math.log1p(density)
        return int(np.clip(round(scaled), 0, _MAX_AUTO_STAR_REDUCTION))
