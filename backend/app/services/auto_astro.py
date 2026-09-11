"""AutoAstroService - one-click adaptive enhancement.

Analyses an image's tone distribution, star density, colour cast, and noise
level (luma and chroma), then proposes a ``ProcessingParameters`` starting
point - a computed alternative to the fixed built-in presets. Scope is
deliberately limited to what a single frame's own statistics can drive with
confidence (tone stretch, star reduction, white balance, luma/chroma
denoise); saturation, sharpness, colour grading, and geometry stay at their
defaults - creative choices a heuristic has no business making. See
docs/ALGORITHMS.md "Auto Astro".

``gradient_reduction`` was tried and removed (see git history /
docs/ALGORITHMS.md) - fitting a linear trend to a blurred copy of the frame
looked clean on synthetic, perfectly-symmetric test images, but real
photos tested against real captures (a plain lunar shot, no light pollution
to correct) landed in the *same* severity range as plausible-looking
deep-sky corrections. A single frame's own brightness distribution can't
reliably separate "real gradient" from "asymmetric bright object" - the same
structural confound that already ruled out an auto vignette-correction
heuristic. `vignette_correction` and `gradient_reduction` both stay manual.
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

#: the darker half of the frame stands in for "background sky" on a typical
#: deep-sky frame, where the DSO/stars occupy a minority of pixels - used to
#: keep the white-balance and noise measurements below from being thrown off
#: by the object's own (real) colour and fine structure.
_SKY_PERCENTILE = 50.0
_MIN_SKY_PIXELS = 400  # below this there isn't enough background to measure confidently

_NEUTRAL_KELVIN = 6500

_MIN_COLOR_CAST_RATIO = 0.03  # ignore a cast this small - more likely noise than a real tint
#: Nudge toward neutral, don't fully neutralise: the "Colour calibration"
#: hint's own caveat applies here too - a full correction can't tell a sensor
#: colour cast apart from a target's own real colour (a blue reflection
#: nebula, a red emission nebula), so it risks washing either out.
_WHITE_BALANCE_DAMPING = 0.5
_KELVIN_GAIN_PER_STEP = 0.3  # matches kelvin_to_rgb_gain's blue-channel slope
_MAX_WARM_STEPS = 2.25  # (2000 - 6500) / 2000
_MAX_COOL_STEPS = 0.75  # (8000 - 6500) / 2000

#: median-absolute-deviation-of-the-Laplacian noise sigma (0-255 scale) below
#: which a frame is treated as already clean (a stack, or a low-ISO frame) -
#: propose nothing rather than softening real detail for a marginal reading.
_MIN_NOISE_SIGMA = 1.5
#: Calibrated against real stacked composites (not just synthetic noise): a
#: typical noisy-but-real stack's sky background reads sigma ~15-22, which
#: this maps to a gentle ~20-25 rather than slamming into the cap - an
#: earlier `4.5` scale (tuned only against synthetic per-pixel noise) mapped
#: that same real range to 70-100+, capping out on nearly every real capture
#: tested and over-smoothing genuine DSO detail (dust lanes, star clusters)
#: along with it, since `apply_denoise` runs on the whole frame, not just the
#: sky. A single noisy raw sub-frame (sigma 50+) still reaches the cap.
_NOISE_SCALE = 1.2
_MAX_AUTO_DENOISE = 50  # gentle, matching the star-reduction cap above
#: colour (chroma) noise has no separately-calibrated scale of its own here -
#: it reuses luma's threshold/scale/cap verbatim, on the same reasoning
#: `apply_chroma_denoise` itself is built on (Cr/Cb noise behaves like luma
#: noise, just measured on a different plane), not a claim they're identical
#: in practice.
_MIN_CHROMA_NOISE_SIGMA = _MIN_NOISE_SIGMA
_CHROMA_NOISE_SCALE = _NOISE_SCALE
_MAX_AUTO_CHROMA_DENOISE = _MAX_AUTO_DENOISE


def _sky_mask(gray: np.ndarray) -> np.ndarray:
    threshold = float(np.percentile(gray, _SKY_PERCENTILE))
    return gray <= threshold


class AutoAstroService:
    """Proposes enhancement parameters from an image's own statistics."""

    def __init__(self, star_detector: StarDetectionService) -> None:
        self.star_detector = star_detector

    def suggest_parameters(self, image: np.ndarray) -> ProcessingParameters:
        """Analyse ``image`` (BGR ``uint8``) and propose a parameter set."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == _COLOR_NDIM else image
        sky = _sky_mask(gray)

        contrast, exposure, highlights, shadows = self._suggest_tone(gray)
        star_reduction = self._suggest_star_reduction(image, gray)
        temperature = self._suggest_temperature(image, sky)
        denoise = self._suggest_denoise(gray, sky)
        chroma_denoise = self._suggest_chroma_denoise(image, sky)

        # Round to what the sliders actually step by (2 decimals) - the raw
        # percentile-derived floats have a dozen digits of noise that look
        # broken in the UI and imply far more precision than the heuristic has.
        contrast = round(contrast, 2)
        exposure = round(exposure, 2)
        highlights = round(highlights, 2)
        shadows = round(shadows, 2)

        return ProcessingParameters(
            contrast=contrast,
            exposure=exposure,
            highlights=highlights,
            shadows=shadows,
            star_reduction=star_reduction,
            temperature=temperature,
            denoise=denoise,
            chroma_denoise=chroma_denoise,
        )

    def _suggest_tone(self, gray: np.ndarray) -> tuple[float, float, float, float]:
        """Stretch the real signal range, then push the DSO and background apart.

        Contrast/exposure alone just fill the tonal range; the depth/pop a
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
        exposure = float(np.clip((_TARGET_BLACK_POINT - black_point_after) / 50.0, -1.0, 1.0))

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

        return contrast, exposure, highlights, shadows

    def _suggest_star_reduction(self, image: np.ndarray, gray: np.ndarray) -> int:
        stars = self.star_detector.detect(image, sensitivity=50, max_size=30)
        megapixels = max(gray.size / 1_000_000.0, 0.1)
        density = len(stars) / megapixels
        scaled = _STAR_DENSITY_LOG_SCALE * math.log1p(density)
        return int(np.clip(round(scaled), 0, _MAX_AUTO_STAR_REDUCTION))

    def _suggest_temperature(self, image: np.ndarray, sky: np.ndarray) -> int:
        """Nudge the white balance toward neutral, from the sky background's
        own colour cast - only the temperature (blue/orange) axis, derived
        from the background's blue-vs-red balance. Tint's green/magenta axis
        is left alone: it's harder to tell apart from a real nebula's own
        colour with just one frame's worth of confidence than a broad
        orange/blue cast (typically light pollution or the sensor's own
        response) is.
        """
        if image.ndim != _COLOR_NDIM or int(sky.sum()) < _MIN_SKY_PIXELS:
            return _NEUTRAL_KELVIN
        blue, _green, red = (float(image[:, :, c][sky].mean()) for c in range(_COLOR_NDIM))
        if red < 1.0 or blue < 1.0 or abs(red / blue - 1.0) < _MIN_COLOR_CAST_RATIO:
            return _NEUTRAL_KELVIN

        target_blue_gain = 1.0 + (red / blue - 1.0) * _WHITE_BALANCE_DAMPING
        if target_blue_gain >= 1.0:
            steps = np.clip((target_blue_gain - 1.0) / _KELVIN_GAIN_PER_STEP, 0.0, _MAX_COOL_STEPS)
        else:
            steps = -np.clip((1.0 - target_blue_gain) / _KELVIN_GAIN_PER_STEP, 0.0, _MAX_WARM_STEPS)
        kelvin = np.clip(_NEUTRAL_KELVIN + steps * 2000, 2000, 8000)
        return int(kelvin)

    def _suggest_denoise(self, gray: np.ndarray, sky: np.ndarray) -> int:
        """Estimate noise from the sky background alone (excluding the DSO
        and stars' own real high-frequency detail) via the median absolute
        deviation of the Laplacian - a standard, outlier-robust noise
        estimator, robust to the handful of real edges (star points) that
        still fall inside the background mask.
        """
        if int(sky.sum()) < _MIN_SKY_PIXELS:
            return 0
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        noise_sigma = float(np.median(np.abs(laplacian[sky]))) / 0.6745
        if noise_sigma < _MIN_NOISE_SIGMA:
            return 0
        return int(np.clip(round(noise_sigma * _NOISE_SCALE), 0, _MAX_AUTO_DENOISE))

    def _suggest_chroma_denoise(self, image: np.ndarray, sky: np.ndarray) -> int:
        """Colour speckle is usually more objectionable than luma noise in a
        stacked astro frame (see `apply_chroma_denoise`) - the same
        median-absolute-deviation-of-the-Laplacian estimator as
        `_suggest_denoise`, applied to the Cr/Cb chroma planes instead of
        luma, and to whichever of the two reads noisier.
        """
        if image.ndim != _COLOR_NDIM or int(sky.sum()) < _MIN_SKY_PIXELS:
            return 0
        _y, cr, cb = cv2.split(cv2.cvtColor(image, cv2.COLOR_BGR2YCrCb))
        cr_sigma = float(np.median(np.abs(cv2.Laplacian(cr, cv2.CV_64F)[sky]))) / 0.6745
        cb_sigma = float(np.median(np.abs(cv2.Laplacian(cb, cv2.CV_64F)[sky]))) / 0.6745
        noise_sigma = max(cr_sigma, cb_sigma)
        if noise_sigma < _MIN_CHROMA_NOISE_SIGMA:
            return 0
        return int(np.clip(round(noise_sigma * _CHROMA_NOISE_SCALE), 0, _MAX_AUTO_CHROMA_DENOISE))
