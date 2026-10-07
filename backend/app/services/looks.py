"""LooksService - the optional "Style" finishing step, last in the pipeline.

A look is a named mix of a few well-known finishing operations (local
contrast, Orton glow, split toning, a deeper sky black, colour pop, vignette,
warm / cool tones, a shadow lift), driven by one ``amount`` (0-100). Every
operation only redistributes the recorded signal - tone, colour, contrast at a
given scale, a glow made from the image's own bright areas. None adds a star, a
spike or any structure that was not captured. See docs/ALGORITHMS.md "Looks".

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
#: Lifts fade out over the top ``1 / _HIGHLIGHT_ROLLOFF`` of the range (the top half).
_HIGHLIGHT_ROLLOFF = 2.0
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
#: Stars: compact bright peaks - luminance above its own blur at this radius
#: (at least 1.5 px, so a thumbnail's 1-2 px stars still count) ...
_STAR_RADIUS = 0.003
_STAR_MIN_RADIUS_PX = 1.5
#: Bright stars' halos are wider: they are found again at this multiple of the radius.
_BRIGHT_STAR_SCALE = 3.0
#: A bright star's core is among the image's brightest pixels (top 0.3 %).
_BRIGHT_STAR_CORE_PERCENTILE = 99.7
#: Star colour is scaled so a star at this percentile of the star mask gets the full boost.
_STAR_TYPICAL_PERCENTILE = 75.0
#: ... by more than this many noise sigmas (ramping to full over as many again).
_STAR_NOISE_SIGMAS = 5.0
#: Star glow: a round bloom made of each star's own light, spread this wide.
_STAR_GLOW_RADIUS = 0.004
_STAR_GLOW_GAIN = 3.0
_STAR_COLOUR_GAIN = 2.5
#: Galaxy core / arms toning: warm grows with the subject mask squared (the
#: core), cool with ``m * (1 - m)`` (the fainter arms); the sky (m = 0) is untouched.
_CORE_WARM_GAIN = 0.18
_ARMS_COOL_GAIN = 0.8
#: Moon / planet detail: scales are fractions of the *disc's* diameter, not of
#: the frame - a planet is a few dozen pixels in a big black field.
_DISC_FINE = 0.004
_DISC_COARSE = 0.04
_BAND_COARSE = 0.1
_DISC_GAIN = 1.4
_DISC_MIN_FINE_PX = 0.7
#: The limb: the detail boost fades in over this fraction of the diameter inside
#: the disc edge, so the limb gets no bright or dark ring.
_DISC_LIMB_FADE = 0.02
#: A disc smaller than this many pixels across is not a disc to work on.
_DISC_MIN_DIAMETER_PX = 8.0
#: White noise minus its 1 px Gaussian blur keeps this fraction of its sigma.
_PIXEL_RESIDUAL_GAIN = 0.85
#: The glow floor for a frame-filling subject (see :func:`inner_glow`).
_INNER_GLOW_FLOOR_PERCENTILE = 20.0

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
    band itself, which is mostly sky) are faded out rather than boosted, and the
    stars are shielded: they sit in the same band, and boosting them bloats them.
    Lifts fade out near white, so bright cores are not burnt.
    """
    if strength <= 0.0:
        return image
    luma = _luma(image)
    fine = _blur(luma, _LOCAL_CONTRAST_FINE, _LOCAL_CONTRAST_MIN_FINE_PX, region)
    band = fine - _sky_level(luma, _LOCAL_CONTRAST_COARSE, region)
    sigma = float(np.median(np.abs(_sample(band, region)))) * _MAD_TO_SIGMA
    cut_sq = (_LOCAL_CONTRAST_NOISE_SIGMAS * sigma) ** 2
    band *= np.clip(1.0 - cut_sq / np.maximum(band * band, _TINY), 0.0, 1.0)
    band *= 1.0 - _star_shield(luma)
    # Highlight roll-off: a lift fades out towards white, so a bright core
    # (the Lagoon's, Orion's) keeps its detail instead of burning to white.
    headroom = np.clip(_HIGHLIGHT_ROLLOFF * (1.0 - fine), 0.0, 1.0)
    band = np.where(band > 0.0, band * headroom, band)
    out = image + (strength * _LOCAL_CONTRAST_GAIN * band)[:, :, np.newaxis]
    return _clip01(out)


def _orton(
    image: np.ndarray,
    strength: float,
    region: Region,
    floor_percentile: float,
    *,
    starless: bool = False,
) -> np.ndarray:
    if strength <= 0.0:
        return image
    source = image
    if starless:
        source = image * (1.0 - _star_shield(_luma(image)))[:, :, np.newaxis]
    glow = _blur(source, _ORTON_RADIUS, region=region)
    floor = np.percentile(_sample(glow, region), floor_percentile, axis=0)
    glow = np.clip(glow - floor, 0.0, 1.0) * (strength * _ORTON_GAIN)
    out = 1.0 - (1.0 - image) * (1.0 - glow)
    return _clip01(out)


def orton_glow(image: np.ndarray, strength: float, region: Region = None) -> np.ndarray:
    """Soft dreamy glow around bright areas (the Orton effect).

    A blurred copy is screen-blended on top. Only what rises above the blurred
    copy's own median is used, so the glow comes from the object and the sky
    background stays dark.
    """
    return _orton(image, strength, region, _DEEP_BLACK_SKY_PERCENTILE)


def inner_glow(image: np.ndarray, strength: float, region: Region = None) -> np.ndarray:
    """The Orton glow for a subject that fills the frame (a large nebula).

    Same blend, but measured from a low percentile instead of the median: when
    the nebula covers most of the picture its own level *is* the median, and
    :func:`orton_glow` would find almost nothing above it. The glow is made of
    the nebula alone - the stars are left out of its source, so a bright star
    does not swell into a disc.
    """
    return _orton(image, strength, region, _INNER_GLOW_FLOOR_PERCENTILE, starless=True)


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


def _star_radius(luma: np.ndarray) -> float:
    return max(_STAR_MIN_RADIUS_PX, _STAR_RADIUS * _diagonal(luma))


def _peaks(luma: np.ndarray, sigma: float) -> np.ndarray:
    """0..1 where the luminance rises above its own blur at ``sigma`` by > 5 noise sigmas."""
    peak = luma - cv2.GaussianBlur(luma, (0, 0), sigmaX=sigma)
    noise = float(np.median(np.abs(peak))) * _MAD_TO_SIGMA
    cut = _STAR_NOISE_SIGMAS * max(noise, _TINY)
    mask: np.ndarray = np.clip((peak - cut) / cut, 0.0, 1.0)
    return mask


def _star_mask(luma: np.ndarray) -> np.ndarray:
    """0..1 on compact bright peaks (stars), 0 on the background and on extended
    structure (a nebula or a galaxy's disc are wider than the star radius).

    Two scales: the typical star, and three times wider for the few bright
    stars whose halo is larger than the typical radius (see :func:`_bright_peaks`).
    """
    mask: np.ndarray = np.maximum(_peaks(luma, _star_radius(luma)), _bright_peaks(luma))
    return mask


def _grow(mask: np.ndarray, radius: float) -> np.ndarray:
    size = 2 * int(np.ceil(2.0 * radius)) + 1
    grown = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size)))
    blurred: np.ndarray = cv2.GaussianBlur(grown, (0, 0), sigmaX=radius)
    return blurred


def _bright_peaks(luma: np.ndarray) -> np.ndarray:
    """Peaks at three times the star radius - the halo of a bright star.

    Only round the image's very brightest pixels (a bright star's core): at
    that scale a thin nebula filament is a "peak" too, and must keep its boost.
    """
    radius = _BRIGHT_STAR_SCALE * _star_radius(luma)
    cores = (luma >= np.percentile(luma, _BRIGHT_STAR_CORE_PERCENTILE)).astype(np.float32)
    near_core = np.clip(_grow(cores, radius), 0.0, 1.0)
    bright: np.ndarray = _peaks(luma, radius) * near_core
    return bright


def _star_shield(luma: np.ndarray) -> np.ndarray:
    """0..1 over each star and its halo - where structure boosts must not act."""
    radius = _star_radius(luma)
    shield = np.maximum(
        _grow(_peaks(luma, radius), radius),
        _grow(_bright_peaks(luma), _BRIGHT_STAR_SCALE * radius),
    )
    clipped: np.ndarray = np.clip(shield, 0.0, 1.0)
    return clipped


def star_glow(image: np.ndarray, strength: float, region: Region = None) -> np.ndarray:
    """A soft round bloom round the stars, made of their own light.

    The detected stars' pixels are blurred and screen-blended back: brighter
    stars bloom more. Round only - no diffraction spikes, nothing that was not
    in the star's own recorded light.
    """
    if strength <= 0.0:
        return image
    stars = image * _star_mask(_luma(image))[:, :, np.newaxis]
    glow = _blur(stars, _STAR_GLOW_RADIUS, _STAR_MIN_RADIUS_PX) * (strength * _STAR_GLOW_GAIN)
    return _clip01(1.0 - (1.0 - image) * (1.0 - np.clip(glow, 0.0, 1.0)))


def star_colour(image: np.ndarray, strength: float, region: Region = None) -> np.ndarray:
    """Bring out the stars' real colours (blue-white, yellow, orange) - on the stars only.

    The smoothed colour of each star (its rim carries it better than its often
    white-clipped core) is boosted on the star's own pixels - the typical-size
    star mask only, so the nebulosity round a bright star is never tinted with
    a disc of colour. Luminance unchanged.
    """
    if strength <= 0.0:
        return image
    luma = _luma(image)
    weight = _peaks(luma, _star_radius(luma))
    # Scaled on a typical star, not the brightest one (which would leave the
    # rest of the field with almost no colour boost).
    on_stars = weight[weight > _TINY]
    typical = float(np.percentile(on_stars, _STAR_TYPICAL_PERCENTILE)) if on_stars.size else 1.0
    weight = np.clip(weight / max(typical, _TINY), 0.0, 1.0)
    chroma = image - luma[:, :, np.newaxis]
    smooth = _blur(chroma, _LOCAL_CONTRAST_FINE, _LOCAL_CONTRAST_MIN_FINE_PX)
    gain = (strength * _STAR_COLOUR_GAIN * weight)[:, :, np.newaxis]
    return _clip01(image + gain * smooth)


def core_and_arms(image: np.ndarray, strength: float, region: Region = None) -> np.ndarray:
    """Warm the brightest part of the subject, cool its fainter outskirts.

    On a spiral galaxy this follows its real colours - an old, yellow core and
    young, blue arms. Luminance-free tints, proportional to luminance; the
    background sky is untouched.
    """
    if strength <= 0.0:
        return image
    luma = _luma(image)
    subject = _object_mask(luma, region)[:, :, np.newaxis]
    tint = _HIGHLIGHT_TINT * (_CORE_WARM_GAIN * subject * subject) + _SHADOW_TINT * (
        _ARMS_COOL_GAIN * subject * (1.0 - subject)
    )
    return _clip01(image + strength * luma[:, :, np.newaxis] * tint)


def _disc(luma: np.ndarray) -> tuple[np.ndarray, float]:
    """The bright Moon / planet disc (boolean) and its equivalent diameter in px.

    Otsu's threshold on the slightly blurred luminance splits the lit disc from
    the black sky; the diameter is that of a circle of the same area, so a
    partial disc (a crescent, a tight crop) still gets sensible scales.
    """
    smooth = cv2.GaussianBlur(luma, (0, 0), sigmaX=1.0)
    as_u8 = np.clip(smooth * 255.0, 0, 255).astype(np.uint8)
    level, _ = cv2.threshold(as_u8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    disc: np.ndarray = smooth * 255.0 > level
    diameter = 2.0 * float(np.sqrt(np.count_nonzero(disc) / np.pi))
    return disc, diameter


def disc_detail(image: np.ndarray, strength: float, region: Region = None) -> np.ndarray:
    """Sharpen the Moon's surface: craters, rays, the terminator.

    A band-pass at scales relative to the disc's own diameter (0.4 % to 4 %),
    measured inside the disc only (a normalised blur), so the black sky never
    enters it and the limb gets no ring. As elsewhere, noise-level detail fades
    out and lifts fade towards white.
    """
    return _disc_detail(image, strength, _DISC_COARSE)


def band_detail(image: np.ndarray, strength: float, region: Region = None) -> np.ndarray:
    """Sharpen a planet's belts, zones and storms.

    :func:`disc_detail` at a wider scale (up to 10 % of the diameter): a
    planet's bands are far wider, relative to its disc, than lunar craters.
    """
    return _disc_detail(image, strength, _BAND_COARSE)


def _disc_detail(image: np.ndarray, strength: float, coarse_fraction: float) -> np.ndarray:
    if strength <= 0.0:
        return image
    luma = _luma(image)
    disc, diameter = _disc(luma)
    if diameter < _DISC_MIN_DIAMETER_PX:
        return image
    fine_sigma = max(_DISC_MIN_FINE_PX, _DISC_FINE * diameter)
    weight = disc.astype(np.float32)
    norm_fine = np.maximum(cv2.GaussianBlur(weight, (0, 0), sigmaX=fine_sigma), _TINY)
    norm_coarse = np.maximum(
        cv2.GaussianBlur(weight, (0, 0), sigmaX=coarse_fraction * diameter), _TINY
    )
    fine = cv2.GaussianBlur(luma * weight, (0, 0), sigmaX=fine_sigma) / norm_fine
    coarse = (
        cv2.GaussianBlur(luma * weight, (0, 0), sigmaX=coarse_fraction * diameter) / norm_coarse
    )
    band = fine - coarse
    # The noise is read at pixel scale (the band itself is all structure on a
    # detailed disc), then scaled to the fine blur: white noise of sigma s
    # blurred by a Gaussian of sigma g keeps about s / (2 * sqrt(pi) * g).
    residual = luma - cv2.GaussianBlur(luma, (0, 0), sigmaX=1.0)
    pixel_noise = float(np.median(np.abs(residual[disc]))) * _MAD_TO_SIGMA / _PIXEL_RESIDUAL_GAIN
    sigma = pixel_noise / (2.0 * np.sqrt(np.pi) * max(fine_sigma, 0.5))
    cut_sq = (_LOCAL_CONTRAST_NOISE_SIGMAS * sigma) ** 2
    band *= np.clip(1.0 - cut_sq / np.maximum(band * band, _TINY), 0.0, 1.0)
    headroom = np.clip(_HIGHLIGHT_ROLLOFF * (1.0 - fine), 0.0, 1.0)
    band = np.where(band > 0.0, band * headroom, band)
    # Fade in from the limb: distance inside the disc, over a small fraction of it.
    inside = cv2.distanceTransform(disc.astype(np.uint8), cv2.DIST_L2, 5)
    limb = np.clip(inside / max(_DISC_LIMB_FADE * diameter, 1.0), 0.0, 1.0)
    out = image + (strength * _DISC_GAIN * band * limb)[:, :, np.newaxis]
    return _clip01(out)


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
    # Nebulae: a luminous glow on the gas, or its filaments carved out.
    "luminous": Look(
        "luminous",
        ((deep_black, 0.4), (inner_glow, 0.8), (colour_pop, 1.0)),
    ),
    "structure": Look(
        "structure",
        ((deep_black, 0.3), (local_contrast, 1.6), (colour_pop, 0.5)),
    ),
    # Galaxies: a deep black field round a crisp disc, or the core / arms colours.
    "deep_field": Look(
        "deep_field",
        ((deep_black, 0.7), (local_contrast, 0.8), (star_glow, 0.4)),
    ),
    "warm_core": Look(
        "warm_core",
        ((deep_black, 0.3), (core_and_arms, 1.0), (colour_pop, 0.6)),
    ),
    # Star clusters: the stars' own colour and glow, or a velvet black field.
    "sparkle": Look(
        "sparkle",
        ((deep_black, 0.3), (star_colour, 1.0), (star_glow, 1.0)),
    ),
    "night_velvet": Look(
        "night_velvet",
        ((deep_black, 1.6), (star_colour, 0.6), (vignette, 0.5)),
    ),
    # The Moon: crisp craters and terminator in neutral grey, or a soft cool glow.
    "moon_crisp": Look(
        "moon_crisp",
        ((deep_black, 0.3), (disc_detail, 1.0)),
    ),
    "moonlight": Look(
        "moonlight",
        ((disc_detail, 0.4), (orton_glow, 0.7), (cool_tone, 1.0)),
    ),
    # Planets: crisp bands, or their real colours brought out.
    "planet_crisp": Look(
        "planet_crisp",
        ((deep_black, 0.3), (band_detail, 1.0)),
    ),
    "rich_colour": Look(
        "rich_colour",
        ((band_detail, 0.5), (colour_pop, 1.2)),
    ),
}

#: The gallery's groups, by kind of picture (the looks route lists them). The
#: night-landscape group is offered only when the session has a sky mask.
GENERAL_LOOKS: tuple[LookId, ...] = ("vivid", "soft_glow", "cinematic")
NIGHTSCAPE_LOOKS: tuple[LookId, ...] = ("galactic_core", "blue_hour")
NEBULA_LOOKS: tuple[LookId, ...] = ("luminous", "structure")
GALAXY_LOOKS: tuple[LookId, ...] = ("deep_field", "warm_core")
CLUSTER_LOOKS: tuple[LookId, ...] = ("sparkle", "night_velvet")
MOON_LOOKS: tuple[LookId, ...] = ("moon_crisp", "moonlight")
PLANET_LOOKS: tuple[LookId, ...] = ("planet_crisp", "rich_colour")


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
