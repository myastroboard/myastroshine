"""LooksService - the optional "Style" finishing step, last in the pipeline.

A look is a named mix of a few well-known finishing operations (local
contrast, Orton glow, split toning, a deeper sky black, colour pop, vignette),
driven by one ``amount`` (0-100). Every operation only redistributes the
recorded signal - tone, colour, contrast at a given scale, a glow made from the
image's own bright areas. None adds a star, a spike or any structure that was
not captured. See docs/ALGORITHMS.md "Looks" and initial_plan/15_LOOKS_STEP.md.

Spatial sizes are fractions of the image diagonal, not pixels, so a ~320 px
gallery thumbnail shows the same look as the full-resolution export.

Every function takes and returns a **BGR float32** array in ``[0, 1]`` and is
an identity transform at strength 0.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import cv2
import numpy as np

from app.models import LookId, LookParameters

_LUMA_BGR = np.array([0.0722, 0.7152, 0.2126], dtype=np.float32)
_TINY = 1e-6

#: Local contrast is a difference of Gaussians: everything finer than the small
#: radius (pixel noise, star cores) and coarser than the large one (the overall
#: sky level) is left alone, so structure is lifted without sharpening grain.
_LOCAL_CONTRAST_FINE = 0.002  # of the diagonal
_LOCAL_CONTRAST_COARSE = 0.02
_LOCAL_CONTRAST_GAIN = 2.5
_LOCAL_CONTRAST_MIN_FINE_PX = 1.0  # a thumbnail's fine blur must still average out pixel noise
#: Band coefficients within this many noise sigmas fade out (non-negative
#: garrote, as in ``app.utils.starlet``), so leftover grain is never boosted.
_LOCAL_CONTRAST_NOISE_SIGMAS = 3.0
_MAD_TO_SIGMA = 1.0 / 0.6745
_ORTON_RADIUS = 0.012
_ORTON_GAIN = 1.6
_DEEP_BLACK_SKY_PERCENTILE = 50.0  # most of an astro frame is background sky
_DEEP_BLACK_MAX_SKY = 0.5  # a bright frame has no "sky" to deepen
_COLOUR_POP_GAIN = 1.0
_COLOUR_POP_TOP_PERCENTILE = 99.0
_COLOUR_POP_MASK_RADIUS = 0.004
#: Tint strength relative to each pixel's own luminance: proportional, so black
#: stays neutral black and a dark sky gets a hint of colour, not a wash.
_SPLIT_TONE_SHADOW_GAIN = 0.2
_SPLIT_TONE_HIGHLIGHT_GAIN = 0.35
_VIGNETTE_GAIN = 0.35

#: Split-toning tints in BGR, scaled to zero luma (``tint @ _LUMA_BGR == 0``) so
#: they shift the hue without brightening or darkening anything.
_TEAL = np.array([1.0, 0.25, -1.0], dtype=np.float32)
_AMBER = np.array([-1.0, 0.1, 1.0], dtype=np.float32)


def _zero_luma(tint: np.ndarray) -> np.ndarray:
    """Remove the luma component of a tint and normalise it to unit length."""
    weights = _LUMA_BGR / float(_LUMA_BGR @ _LUMA_BGR)
    neutral = tint - float(tint @ _LUMA_BGR) * weights
    unit: np.ndarray = (neutral / float(np.linalg.norm(neutral))).astype(np.float32)
    return unit


_SHADOW_TINT = _zero_luma(_TEAL)
_HIGHLIGHT_TINT = _zero_luma(_AMBER)


def _diagonal(image: np.ndarray) -> float:
    height, width = image.shape[:2]
    return float(np.hypot(height, width))


def _blur(image: np.ndarray, fraction: float, min_px: float = 0.5) -> np.ndarray:
    sigma = max(min_px, fraction * _diagonal(image))
    blurred: np.ndarray = cv2.GaussianBlur(image, (0, 0), sigmaX=sigma)
    return blurred


def _clip01(image: np.ndarray) -> np.ndarray:
    clipped: np.ndarray = np.clip(image, 0.0, 1.0)
    return clipped


def _luma(image: np.ndarray) -> np.ndarray:
    luma: np.ndarray = image @ _LUMA_BGR
    return luma


def _object_mask(luma: np.ndarray) -> np.ndarray:
    """0 on the background sky .. 1 on the brightest structure, softly blurred."""
    smooth = _blur(luma, _COLOUR_POP_MASK_RADIUS)
    sky = float(np.percentile(smooth, _DEEP_BLACK_SKY_PERCENTILE))
    top = float(np.percentile(smooth, _COLOUR_POP_TOP_PERCENTILE))
    mask: np.ndarray = np.clip((smooth - sky) / max(top - sky, _TINY), 0.0, 1.0)
    return mask


def local_contrast(image: np.ndarray, strength: float) -> np.ndarray:
    """Lift medium-scale structure (filaments, dust lanes, arms) by ``strength``.

    A band-pass of the luminance (fine blur minus coarse blur) is added back to
    every channel, so colour is kept and neither pixel noise nor the overall sky
    level is touched. Band values at the noise level (measured robustly on the
    band itself, which is mostly sky) are faded out rather than boosted.
    """
    if strength <= 0.0:
        return image
    luma = _luma(image)
    fine = _blur(luma, _LOCAL_CONTRAST_FINE, _LOCAL_CONTRAST_MIN_FINE_PX)
    band = fine - _blur(luma, _LOCAL_CONTRAST_COARSE)
    sigma = float(np.median(np.abs(band))) * _MAD_TO_SIGMA
    cut_sq = (_LOCAL_CONTRAST_NOISE_SIGMAS * sigma) ** 2
    band *= np.clip(1.0 - cut_sq / np.maximum(band * band, _TINY), 0.0, 1.0)
    out = image + (strength * _LOCAL_CONTRAST_GAIN * band)[:, :, np.newaxis]
    return _clip01(out)


def orton_glow(image: np.ndarray, strength: float) -> np.ndarray:
    """Soft dreamy glow around bright areas (the Orton effect).

    A blurred copy is screen-blended on top. Only what rises above the blurred
    copy's own median is used, so the glow comes from the object and the sky
    background stays dark.
    """
    if strength <= 0.0:
        return image
    glow = _blur(image, _ORTON_RADIUS)
    floor = np.median(glow.reshape(-1, 3), axis=0)
    glow = np.clip(glow - floor, 0.0, 1.0) * (strength * _ORTON_GAIN)
    out = 1.0 - (1.0 - image) * (1.0 - glow)
    return _clip01(out)


def deep_black(image: np.ndarray, strength: float) -> np.ndarray:
    """Darken the background sky with a soft toe; bright areas are untouched.

    The luminance goes through ``L' = L * L / (L + k) * (1 + k)``: 1 stays 1,
    the sky level (``k`` at full strength) is roughly halved, darker pixels fall
    off smoothly towards black - never clipped. Colours are scaled by
    ``L' / L``, which is never above 1, so nothing gets brighter.
    """
    if strength <= 0.0:
        return image
    luma = _luma(image)
    sky = min(float(np.percentile(luma, _DEEP_BLACK_SKY_PERCENTILE)), _DEEP_BLACK_MAX_SKY)
    k = strength * sky
    if k <= 0.0:
        return image
    ratio = luma / (luma + k) * (1.0 + k)
    ratio = np.minimum(ratio, 1.0)
    out = image * ratio[:, :, np.newaxis]
    return _clip01(out)


def colour_pop(image: np.ndarray, strength: float) -> np.ndarray:
    """Richer colour on the object, not on the background.

    Saturation is raised where the (slightly blurred) luminance stands above the
    sky level, so the target's real colours deepen while the background's colour
    noise is left alone. Luminance-preserving.
    """
    if strength <= 0.0:
        return image
    luma = _luma(image)
    mask = _object_mask(luma)
    factor = (1.0 + strength * _COLOUR_POP_GAIN * mask)[:, :, np.newaxis]
    luma3 = luma[:, :, np.newaxis]
    return _clip01(luma3 + (image - luma3) * factor)


def split_toning(image: np.ndarray, strength: float) -> np.ndarray:
    """Cool background, warm subject - the "cinematic" colour contrast.

    "Highlight" means above the image's own sky level (the same object mask as
    :func:`colour_pop`), so on a dark astro frame the object warms up and the
    sky cools, instead of the whole frame counting as shadow. The tints carry no
    luminance and scale with each pixel's luminance, so brightness is unchanged
    and black stays neutral black.
    """
    if strength <= 0.0:
        return image
    luma = _luma(image)
    subject = _object_mask(luma)[:, :, np.newaxis]
    tint = _SHADOW_TINT * (_SPLIT_TONE_SHADOW_GAIN * (1.0 - subject)) + _HIGHLIGHT_TINT * (
        _SPLIT_TONE_HIGHLIGHT_GAIN * subject
    )
    out = image + strength * luma[:, :, np.newaxis] * tint
    return _clip01(out)


def vignette(image: np.ndarray, strength: float) -> np.ndarray:
    """Gently darken towards the corners to draw the eye to the centre."""
    if strength <= 0.0:
        return image
    height, width = image.shape[:2]
    ys = np.linspace(-1.0, 1.0, height, dtype=np.float32)[:, np.newaxis]
    xs = np.linspace(-1.0, 1.0, width, dtype=np.float32)[np.newaxis, :]
    radius_sq = (xs * xs + ys * ys) / 2.0  # 0 at the centre, 1 in the corners
    falloff = radius_sq * radius_sq * (3.0 - 2.0 * radius_sq)  # smooth, flat centre
    gain = 1.0 - strength * _VIGNETTE_GAIN * falloff
    return _clip01(image * gain[:, :, np.newaxis])


Operation = Callable[[np.ndarray, float], np.ndarray]


@dataclass(frozen=True)
class Look:
    """A look: operations applied in order, each with its weight at amount 100."""

    look_id: LookId
    steps: tuple[tuple[Operation, float], ...]


#: The catalogue. Order inside a look matters: tone first (deep_black), then
#: structure, then glow / colour, then framing (vignette).
LOOKS: dict[LookId, Look] = {
    "vivid": Look(
        "vivid",
        ((deep_black, 0.5), (local_contrast, 1.0), (colour_pop, 1.0)),
    ),
    "soft_glow": Look(
        "soft_glow",
        ((deep_black, 0.4), (orton_glow, 1.0)),
    ),
    "cinematic": Look(
        "cinematic",
        ((local_contrast, 0.3), (split_toning, 1.0), (vignette, 0.6)),
    ),
}


def look_description(look: LookParameters) -> str | None:
    """The text an export carries in its metadata when a look is active."""
    if look.look_id is None or look.amount <= 0:
        return None
    return f"MyAstroShine style: {look.look_id} ({look.amount}%)"


class LooksService:
    """Applies the session's look (or none) to a finished image."""

    def apply(self, image: np.ndarray, params: LookParameters) -> np.ndarray:
        """Apply ``params``'s look at its amount; identity when there is none."""
        if params.look_id is None or params.amount <= 0:
            return image
        scale = params.amount / 100.0
        result = image
        for operation, weight in LOOKS[params.look_id].steps:
            result = operation(result, weight * scale)
        return result.astype(np.float32, copy=False)
