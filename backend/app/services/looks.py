"""LooksService - the optional "Style" finishing step, last in the pipeline.

A look is a named mix of a few well-known finishing operations (local
contrast, Orton glow, split toning, a deeper sky black, colour pop, vignette,
warm / cool tones, a shadow lift), driven by one ``amount`` (0-100). Every
operation only redistributes the recorded signal - tone, colour, contrast at a
given scale, a glow made from the image's own bright areas. None adds a star, a
spike or any structure that was not captured. See docs/ALGORITHMS.md "Looks"
and initial_plan/15_LOOKS_STEP.md.

Spatial sizes are fractions of the image diagonal, not pixels, so a ~320 px
gallery thumbnail shows the same look as the full-resolution export.

Every function takes and returns a **BGR float32** array in ``[0, 1]`` and is
an identity transform at strength 0. Its optional ``region`` (a boolean mask)
picks the pixels its statistics - sky level, noise, brightest structure - are
measured on: a night-landscape look measures the sky on the sky and the
foreground on the foreground, then blends the two through the soft sky mask.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

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
#: Whole-region tints (warm / cool), relative to luminance like split toning.
_TONE_GAIN = 0.25
#: Shadow lift: ``ratio = 1 + gain * (1 - L)^2`` - darks open up by at most
#: ``1 + gain`` (a gain, never an offset: black stays black and no grey veil),
#: midtones a little, white not at all.
_LIFT_GAIN = 0.6
#: Feather of the sky / foreground blend, so a tree line shows no seam.
_SKY_BLEND_RADIUS = 0.002
#: A region needs this many pixels for its statistics; below, the whole frame is used.
_MIN_REGION_PIXELS = 64
_SKY_MATTE_HALF = 0.5
#: Scale of a night sky's own background (light-pollution dome, gradients),
#: removed before deciding what is "structure" on a night landscape.
_SKY_BACKGROUND_RADIUS = 0.06
#: A "sky" pixel darker than this fraction of the local sky level is an
#: intrusion (a leaf the matte missed) and is left out of the sky's level.
_SKY_DARK_INTRUSION = 0.75
#: Width of the strip of sky along the foreground that is never the "subject".
_SKY_EDGE_FADE = 0.01

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

#: Pixels a statistic is measured on; ``None`` = the whole frame.
Region = np.ndarray | None


def _diagonal(image: np.ndarray) -> float:
    height, width = image.shape[:2]
    return float(np.hypot(height, width))


def _blur(
    image: np.ndarray, fraction: float, min_px: float = 0.5, region: Region = None
) -> np.ndarray:
    """Gaussian blur, ``fraction`` of the diagonal wide.

    With ``region``, a normalised blur over the region only: the sky next to a
    tree line is averaged with sky, never with the dark foreground - otherwise
    the sky's edge reads as "brighter than its surroundings" and a contrast or
    glow operation draws a halo along the trees.
    """
    sigma = max(min_px, fraction * _diagonal(image))
    if region is None:
        blurred: np.ndarray = cv2.GaussianBlur(image, (0, 0), sigmaX=sigma)
        return blurred
    weight = region.astype(np.float32)
    norm = np.maximum(cv2.GaussianBlur(weight, (0, 0), sigmaX=sigma), _TINY)
    if image.ndim == 3:  # noqa: PLR2004 - a colour image
        weight, norm = weight[:, :, np.newaxis], norm[:, :, np.newaxis]
    normalised: np.ndarray = cv2.GaussianBlur(image * weight, (0, 0), sigmaX=sigma) / norm
    return normalised


def _sky_level(luma: np.ndarray, fraction: float, region: Region) -> np.ndarray:
    """The local background level ``fraction`` of the diagonal wide.

    On a night landscape (``region`` = the sky), pixels much darker than the
    local sky are left out as well: the phone's sky matte is coarser than a
    tree, and dark leaves counted as "sky" would pull the level down next to
    them, which a contrast boost then turns into a bright halo round the tree.
    """
    level = _blur(luma, fraction, region=region)
    if region is None:
        return level
    return _blur(luma, fraction, region=region & (luma >= _SKY_DARK_INTRUSION * level))


def _clip01(image: np.ndarray) -> np.ndarray:
    clipped: np.ndarray = np.clip(image, 0.0, 1.0)
    return clipped


def _luma(image: np.ndarray) -> np.ndarray:
    luma: np.ndarray = image @ _LUMA_BGR
    return luma


def _sample(values: np.ndarray, region: Region) -> np.ndarray:
    """``values``' pixels inside ``region`` - all of them without one, or when it is tiny."""
    if region is None or int(np.count_nonzero(region)) < _MIN_REGION_PIXELS:
        flat: np.ndarray = values.reshape(-1, *values.shape[2:])
        return flat
    picked: np.ndarray = values[region]
    return picked


def _object_mask(luma: np.ndarray, region: Region = None) -> np.ndarray:
    """0 on the background sky .. 1 on the brightest structure, softly blurred.

    With ``region`` (a night landscape's sky), "structure" is what stands out
    from the *local* sky level - the Milky Way's band and clouds - not the
    sky's broad brightest gradient, which is the light-pollution dome over the
    horizon and must not be warmed or saturated as if it were the subject.
    """
    smooth = _blur(luma, _COLOUR_POP_MASK_RADIUS, region=region)
    if region is not None:
        smooth = smooth - _sky_level(luma, _SKY_BACKGROUND_RADIUS, region)
    sample = _sample(smooth, region)
    sky = float(np.percentile(sample, _DEEP_BLACK_SKY_PERCENTILE))
    top = float(np.percentile(sample, _COLOUR_POP_TOP_PERCENTILE))
    mask: np.ndarray = np.clip((smooth - sky) / max(top - sky, _TINY), 0.0, 1.0)
    if region is not None:
        # The sky right against the foreground is never the subject: a matte
        # edge or a bright rim round a tree would otherwise be tinted.
        inside = _blur(region.astype(np.float32), _SKY_EDGE_FADE)
        mask *= np.clip((inside - _SKY_MATTE_HALF) / (1.0 - _SKY_MATTE_HALF) * 2.0, 0.0, 1.0)
    return mask


def local_contrast(image: np.ndarray, strength: float, region: Region = None) -> np.ndarray:
    """Lift medium-scale structure (filaments, dust lanes, arms) by ``strength``.

    A band-pass of the luminance (fine blur minus coarse blur) is added back to
    every channel, so colour is kept and neither pixel noise nor the overall sky
    level is touched. Band values at the noise level (measured robustly on the
    band itself, which is mostly sky) are faded out rather than boosted.
    """
    if strength <= 0.0:
        return image
    luma = _luma(image)
    fine = _blur(luma, _LOCAL_CONTRAST_FINE, _LOCAL_CONTRAST_MIN_FINE_PX, region)
    band = fine - _sky_level(luma, _LOCAL_CONTRAST_COARSE, region)
    sigma = float(np.median(np.abs(_sample(band, region)))) * _MAD_TO_SIGMA
    cut_sq = (_LOCAL_CONTRAST_NOISE_SIGMAS * sigma) ** 2
    band *= np.clip(1.0 - cut_sq / np.maximum(band * band, _TINY), 0.0, 1.0)
    out = image + (strength * _LOCAL_CONTRAST_GAIN * band)[:, :, np.newaxis]
    return _clip01(out)


def orton_glow(image: np.ndarray, strength: float, region: Region = None) -> np.ndarray:
    """Soft dreamy glow around bright areas (the Orton effect).

    A blurred copy is screen-blended on top. Only what rises above the blurred
    copy's own median is used, so the glow comes from the object and the sky
    background stays dark.
    """
    if strength <= 0.0:
        return image
    glow = _blur(image, _ORTON_RADIUS, region=region)
    floor = np.median(_sample(glow, region), axis=0)
    glow = np.clip(glow - floor, 0.0, 1.0) * (strength * _ORTON_GAIN)
    out = 1.0 - (1.0 - image) * (1.0 - glow)
    return _clip01(out)


def deep_black(image: np.ndarray, strength: float, region: Region = None) -> np.ndarray:
    """Darken the background sky with a soft toe; bright areas are untouched.

    The luminance goes through ``L' = L * L / (L + k) * (1 + k)``: 1 stays 1,
    the sky level (``k`` at full strength) is roughly halved, darker pixels fall
    off smoothly towards black - never clipped. Colours are scaled by
    ``L' / L``, which is never above 1, so nothing gets brighter.
    """
    if strength <= 0.0:
        return image
    luma = _luma(image)
    sky = min(
        float(np.percentile(_sample(luma, region), _DEEP_BLACK_SKY_PERCENTILE)),
        _DEEP_BLACK_MAX_SKY,
    )
    k = strength * sky
    if k <= 0.0:
        return image
    ratio = luma / (luma + k) * (1.0 + k)
    ratio = np.minimum(ratio, 1.0)
    out = image * ratio[:, :, np.newaxis]
    return _clip01(out)


def colour_pop(image: np.ndarray, strength: float, region: Region = None) -> np.ndarray:
    """Richer colour on the object, not on the background.

    Saturation is raised where the (slightly blurred) luminance stands above the
    sky level, so the target's real colours deepen while the background's colour
    noise is left alone. Only the smoothed colour is boosted - the pixel-scale
    colour grain stays as it was. Luminance-preserving.
    """
    if strength <= 0.0:
        return image
    luma = _luma(image)
    mask = _object_mask(luma, region)
    gain = (strength * _COLOUR_POP_GAIN * mask)[:, :, np.newaxis]
    chroma = image - luma[:, :, np.newaxis]
    smooth_chroma = _blur(chroma, _LOCAL_CONTRAST_FINE, _LOCAL_CONTRAST_MIN_FINE_PX)
    return _clip01(image + gain * smooth_chroma)


def split_toning(image: np.ndarray, strength: float, region: Region = None) -> np.ndarray:
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
    subject = _object_mask(luma, region)[:, :, np.newaxis]
    tint = _SHADOW_TINT * (_SPLIT_TONE_SHADOW_GAIN * (1.0 - subject)) + _HIGHLIGHT_TINT * (
        _SPLIT_TONE_HIGHLIGHT_GAIN * subject
    )
    out = image + strength * luma[:, :, np.newaxis] * tint
    return _clip01(out)


def vignette(image: np.ndarray, strength: float, region: Region = None) -> np.ndarray:
    """Gently darken towards the corners to draw the eye to the centre (no statistics)."""
    if strength <= 0.0:
        return image
    height, width = image.shape[:2]
    ys = np.linspace(-1.0, 1.0, height, dtype=np.float32)[:, np.newaxis]
    xs = np.linspace(-1.0, 1.0, width, dtype=np.float32)[np.newaxis, :]
    radius_sq = (xs * xs + ys * ys) / 2.0  # 0 at the centre, 1 in the corners
    falloff = radius_sq * radius_sq * (3.0 - 2.0 * radius_sq)  # smooth, flat centre
    gain = 1.0 - strength * _VIGNETTE_GAIN * falloff
    return _clip01(image * gain[:, :, np.newaxis])


def _tone(image: np.ndarray, strength: float, tint: np.ndarray) -> np.ndarray:
    luma = _luma(image)[:, :, np.newaxis]
    return _clip01(image + (strength * _TONE_GAIN) * luma * tint)


def warm_tone(image: np.ndarray, strength: float, region: Region = None) -> np.ndarray:
    """A warm (amber) cast, luminance-neutral and proportional - black stays black."""
    if strength <= 0.0:
        return image
    return _tone(image, strength, _HIGHLIGHT_TINT)


def cool_tone(image: np.ndarray, strength: float, region: Region = None) -> np.ndarray:
    """A cool (blue-teal) cast, luminance-neutral and proportional - black stays black."""
    if strength <= 0.0:
        return image
    return _tone(image, strength, _SHADOW_TINT)


def lift_shadows(image: np.ndarray, strength: float, region: Region = None) -> np.ndarray:
    """Open up dark areas (a night foreground) without a grey veil.

    Colours are scaled by ``1 + g * (1 - L)^2``: largest in the darks (at most
    ``1 + g``), small in the midtones, none at white. A gain, not an offset, so
    hues are kept and pure black stays black.
    """
    if strength <= 0.0:
        return image
    luma = np.clip(_luma(image), 0.0, 1.0)
    ratio = 1.0 + strength * _LIFT_GAIN * (1.0 - luma) ** 2
    return _clip01(image * ratio[:, :, np.newaxis])


class Operation(Protocol):
    """A building block: ``(image, strength, region) -> image``."""

    def __call__(self, image: np.ndarray, strength: float, region: Region = None) -> np.ndarray: ...


Steps = tuple[tuple[Operation, float], ...]


@dataclass(frozen=True)
class Look:
    """A look: operations applied in order, each with its weight at amount 100.

    A night-landscape look also has ``ground_steps``: ``steps`` then apply to the
    sky and ``ground_steps`` to the foreground, blended through the sky mask.
    Without a sky mask, ``steps`` apply to the whole frame.
    """

    look_id: LookId
    steps: Steps
    ground_steps: Steps | None = None


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
    # Night landscapes (a sky mask): the Milky Way's core warms, the sky around
    # it cools, dust lanes gain contrast, and the foreground opens up - kept
    # natural, never tinted to match the sky.
    "galactic_core": Look(
        "galactic_core",
        ((local_contrast, 1.0), (split_toning, 1.0), (colour_pop, 0.8)),
        ground_steps=((lift_shadows, 0.7), (local_contrast, 0.3)),
    ),
    # A cool night sky with a soft glow on the band over a warm foreground.
    "blue_hour": Look(
        "blue_hour",
        ((cool_tone, 1.6), (orton_glow, 1.0), (local_contrast, 0.4)),
        ground_steps=((lift_shadows, 0.6), (warm_tone, 1.0)),
    ),
}

#: Looks offered for every image, and the night-landscape ones offered only
#: when the session has a sky mask (the gallery reads both from the looks route).
GENERAL_LOOKS: tuple[LookId, ...] = ("vivid", "soft_glow", "cinematic")
NIGHTSCAPE_LOOKS: tuple[LookId, ...] = ("galactic_core", "blue_hour")


def look_description(look: LookParameters) -> str | None:
    """The text an export carries in its metadata when a look is active."""
    if look.look_id is None or look.amount <= 0:
        return None
    return f"MyAstroShine style: {look.look_id} ({look.amount}%)"


def _run(image: np.ndarray, steps: Steps, scale: float, region: Region) -> np.ndarray:
    result = image
    for operation, weight in steps:
        result = operation(result, weight * scale, region)
    return result.astype(np.float32, copy=False)


class LooksService:
    """Applies the session's look (or none) to a finished image."""

    def apply(
        self, image: np.ndarray, params: LookParameters, sky_mask: np.ndarray | None = None
    ) -> np.ndarray:
        """Apply ``params``'s look at its amount; identity when there is none.

        ``sky_mask`` (0..1 or boolean, any size - it is resized to the image) is
        used only by a night-landscape look; without one, that look's sky steps
        apply to the whole frame.
        """
        if params.look_id is None or params.amount <= 0:
            return image
        scale = params.amount / 100.0
        look = LOOKS[params.look_id]
        if look.ground_steps is None or sky_mask is None:
            return _run(image, look.steps, scale, None)

        weight: np.ndarray = sky_mask.astype(np.float32)
        if weight.shape != image.shape[:2]:
            weight = cv2.resize(weight, image.shape[1::-1], interpolation=cv2.INTER_LINEAR)
        sky_region = weight >= _SKY_MATTE_HALF
        sky = _run(image, look.steps, scale, sky_region)
        ground = _run(image, look.ground_steps, scale, ~sky_region)
        blend = np.clip(_blur(weight, _SKY_BLEND_RADIUS), 0.0, 1.0)[:, :, np.newaxis]
        return _clip01(sky * blend + ground * (1.0 - blend)).astype(np.float32, copy=False)
