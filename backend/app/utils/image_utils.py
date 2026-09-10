"""Image load / save / inspect helpers.

Thin wrappers over OpenCV so services never touch the library for IO concerns.
All arrays are BGR ``uint8`` (OpenCV's convention) unless stated otherwise.
"""

from __future__ import annotations

import io
import math
from pathlib import Path

import cv2
import numpy as np

from app.constants import MAX_IMAGE_PIXELS
from app.exceptions import UnsupportedImageError
from app.logging_config import get_logger

logger = get_logger(__name__)

_STANDARD_FORMATS = {".jpg", ".jpeg", ".png", ".tiff", ".tif"}
FITS_FORMATS = {".fits", ".fit", ".fts"}
RAW_FORMATS = {".cr2", ".cr3", ".nef", ".arw", ".dng", ".orf", ".rw2", ".pef", ".raf"}
SUPPORTED_FORMATS = _STANDARD_FORMATS | FITS_FORMATS | RAW_FORMATS

_ENCODE_EXT = {"jpeg": ".jpg", "jpg": ".jpg", "png": ".png", "tiff": ".tif", "tif": ".tif"}

# Auto-stretch for FITS / RAW / 16-bit TIFF-PNG ingest - the same "screen
# transfer function" auto-stretch used across astro tools (PixInsight's
# AutoSTF, Siril, ...) to bring linear scientific/sensor data into a viewable,
# editable range. A plain min-max or bit-shift either crushes the background
# to black (a stacked frame's real signal sits in a tiny slice near zero) or
# lets a single hot pixel/cosmic-ray hit set the ceiling for the whole frame.
_STRETCH_PERCENTILE_LOW = 0.1  # clip below this first - guards the black point
_STRETCH_PERCENTILE_HIGH = 99.9  # ditto above - guards against hot pixels/cosmic rays
_STRETCH_SHADOW_CLIP_SIGMA = 2.8  # shadow (black) point: median - this many robust sigma
_MAD_TO_SIGMA = 1.4826  # scales median-absolute-deviation to a Gaussian-equivalent std
_STRETCH_TARGET_BACKGROUND = 0.25  # background maps to this fraction of the 0-1 range
_MTF_NEUTRAL_MIDTONE = 0.5  # m=0.5 makes the MTF curve the identity - avoid a 0/0 divide
_MTF_IDENTITY_EPSILON = 1e-9
_MTF_SOLVE_EPSILON = 1e-12
_MTF_BALANCE_RANGE = (1e-6, 1 - 1e-6)  # keep the solved m strictly inside (0, 1)

# FITS/decoded-array shape checks - not "3 channels" in the usual BGR sense,
# these are RGB *planes* (see _decode_fits) or a raw decode's channel count.
_MONO_NDIM = 2
_RGB_CUBE_NDIM = 3
_RGB_PLANE_COUNT = 3
_BGRA_CHANNEL_COUNT = 4
_GRAY_ALPHA_CHANNEL_COUNT = 2


def _midtone_transfer(x: np.ndarray, m: float) -> np.ndarray:
    """PixInsight's MTF curve: a rational function through (0,0), (m,0.5), (1,1)."""
    if abs(m - _MTF_NEUTRAL_MIDTONE) < _MTF_IDENTITY_EPSILON:
        return x
    return ((m - 1.0) * x) / (((2.0 * m - 1.0) * x) - m)


def _solve_midtone_balance(background: float, target: float) -> float:
    """The ``m`` for which :func:`_midtone_transfer` maps ``background`` to ``target``."""
    denom = (2.0 * target * background) - target - background
    if abs(denom) < _MTF_SOLVE_EPSILON:
        return _MTF_NEUTRAL_MIDTONE
    return float(np.clip((background * (target - 1.0)) / denom, *_MTF_BALANCE_RANGE))


def _stretch_params(
    plane: np.ndarray,
    target_background: float = _STRETCH_TARGET_BACKGROUND,
    shadow_clip: float = _STRETCH_SHADOW_CLIP_SIGMA,
) -> tuple[float, float, float, float] | None:
    """The (low, high, black_point, midtone) an auto-stretch of ``plane`` would use.

    Returned separately from :func:`_apply_stretch` so a colour image can derive
    one transform from its luminance and apply it to every channel (keeping the
    colour balance) instead of stretching each channel on its own. A deep stack
    passes a lower ``target_background`` / harder ``shadow_clip`` so its read
    noise is not lifted out of the shadows.
    """
    finite = plane[np.isfinite(plane)]
    if finite.size == 0:
        return None
    low, high = np.percentile(finite, [_STRETCH_PERCENTILE_LOW, _STRETCH_PERCENTILE_HIGH])
    if high <= low:
        return None
    normalized = np.nan_to_num(np.clip((plane.astype(np.float64) - low) / (high - low), 0, 1))
    median = float(np.median(normalized))
    sigma = float(np.median(np.abs(normalized - median))) * _MAD_TO_SIGMA
    black_point = max(0.0, median - shadow_clip * sigma)
    clipped = np.clip((normalized - black_point) / max(1e-6, 1.0 - black_point), 0, 1)
    background = float(np.median(clipped))
    balance = (
        _solve_midtone_balance(background, target_background)
        if background > 0
        else _MTF_NEUTRAL_MIDTONE
    )
    return float(low), float(high), black_point, balance


def _stretch_plane_f32(data: np.ndarray, params: tuple[float, float, float, float]) -> np.ndarray:
    """Apply a :func:`_stretch_params` result to a plane -> ``float32`` in ``[0, 1]``.

    The linear core of :func:`_apply_stretch`, kept separate so the composite
    pre-stage (:func:`stretch_composite_linear`) can stay in float instead of
    quantising to uint8 and back.
    """
    low, high, black_point, balance = params
    # nan_to_num after the clip: blank/masked pixels (FITS BLANK, the NaN edges
    # of a registered stack, dead pixels) map to black rather than poisoning the
    # result. (clip already bounds +/-inf.) float32 is plenty for a display
    # stretch and ~2x faster than float64 over a full-res composite.
    normalized = np.nan_to_num(np.clip((data.astype(np.float32) - low) / (high - low), 0, 1))
    clipped = np.clip((normalized - black_point) / max(1e-6, 1.0 - black_point), 0, 1)
    stretched = _midtone_transfer(clipped, balance)
    result: np.ndarray = np.clip(stretched, 0.0, 1.0).astype(np.float32)
    return result


def _apply_stretch(data: np.ndarray, params: tuple[float, float, float, float]) -> np.ndarray:
    """Apply a :func:`_stretch_params` result to a plane -> uint8."""
    return np.clip(_stretch_plane_f32(data, params) * 255.0, 0, 255).astype(np.uint8)


def _auto_stretch_to_uint8(data: np.ndarray) -> np.ndarray:
    """Map one plane of linear scientific/sensor data (any numeric dtype) to uint8."""
    params = _stretch_params(data)
    if params is None:
        return np.zeros(data.shape, dtype=np.uint8)
    return _apply_stretch(data, params)


# -- composite stretch ----------------------------------------------------------
# A stacked composite is colour, linear and very faint; unlike the per-plane
# _auto_stretch_to_uint8 (frame thumbnails, mono FITS) it needs the colour kept:
# neutralise the sky background (so read noise is grey, not rainbow speckle) then
# apply ONE midtone stretch, derived from the luminance, to all three channels.

_COMPOSITE_BG_PERCENTILE = 25.0
_COMPOSITE_TARGET_BACKGROUND = 0.10  # deep stack: keep the noise floor dark, not lifted to 0.25
_COMPOSITE_SHADOW_CLIP = 3.2
_LUMA_RGB = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def stretch_composite_linear(
    composite: np.ndarray,
    target_background: float = _COMPOSITE_TARGET_BACKGROUND,
    shadow_clip: float = _COMPOSITE_SHADOW_CLIP,
) -> np.ndarray:
    """Neutralise + one shared midtone stretch of a linear composite -> BGR ``float32`` ``[0, 1]``.

    Input is an ``(H, W)`` or ``(H, W, 3)`` **RGB-plane** linear array (the
    stacking composite's channel order); output is full-resolution BGR ready for
    the enhancement pipeline. ``target_background`` sets how hard the stretch
    lifts the sky (the editor's "Stretch" control maps onto it).
    """
    rgb = composite.astype(np.float32)
    if rgb.ndim == _MONO_NDIM:
        rgb = np.repeat(rgb[:, :, np.newaxis], _RGB_PLANE_COUNT, axis=2)

    finite = np.isfinite(rgb).all(axis=2)
    if finite.any():
        background = np.array(
            [np.percentile(rgb[..., c][finite], _COMPOSITE_BG_PERCENTILE) for c in range(3)],
            dtype=np.float32,
        )
        rgb = np.clip(np.nan_to_num(rgb - background), 0.0, None)

    params = _stretch_params(rgb @ _LUMA_RGB, target_background, shadow_clip)
    if params is None:
        return np.zeros((*rgb.shape[:2], 3), dtype=np.float32)
    channels = [_stretch_plane_f32(rgb[..., c], params) for c in range(3)]
    return cv2.merge([channels[2], channels[1], channels[0]])  # RGB planes -> BGR


def _decode_fits(data: bytes) -> np.ndarray:
    """Decode a FITS frame into a BGR uint8 array via the auto-stretch above.

    FITS is scientific/linear data (any of 8/16/32-bit int or float; `BSCALE`/
    `BZERO` header scaling is applied transparently by astropy) - a raw
    stacked frame looks almost black without a non-linear stretch, so every
    FITS upload is auto-stretched regardless of its stored dtype. 2D data is
    treated as monochrome: there's no reliable, standard header keyword for a
    Bayer pattern to safely debayer a raw one-shot-colour sensor frame, so
    guessing one risks a garish checkerboard artifact instead - out of scope
    here. A leading or trailing 3-plane axis is read as RGB and stretched with
    one shared, colour-preserving transform (:func:`stretch_composite_linear`,
    the same core the stacked-composite editor uses) and a deep sky target -
    three independent per-channel stretches fight the colour balance and lift
    the sky to a milky grey, which a faint deep-sky stack can't recover from.

    (A direct upload no longer reaches this: ``POST /api/upload`` opens a FITS as
    a linear composite session - see :mod:`app.services.linear_upload`. This
    stays the path for an AstroDex handoff and any other ``decode_image`` caller
    that hands in a FITS.)
    """
    from astropy.io import fits  # noqa: PLC0415 - heavy, only imported for an actual FITS upload

    try:
        with fits.open(io.BytesIO(data)) as hdul:
            hdu = next((h for h in hdul if h.is_image and h.shape), None)
            if hdu is None:
                raise UnsupportedImageError("FITS file has no image data")
            # hdu.shape reads NAXISn straight from the header, before ever
            # touching hdu.data below - checked first so a crafted header
            # (e.g. NAXIS1/NAXIS2 far bigger than the file's real data
            # section) can't force a multi-GB allocation. A generous blanket
            # cap (any declared shape, not just the 2D/3-plane-cube ones this
            # module actually accepts - allowing for an RGB cube's extra
            # elements) is enough: the precise "is this actually 2D or a
            # 3-plane RGB cube" check happens below, safely, on the now
            # size-bounded loaded array.
            if math.prod(hdu.shape) > MAX_IMAGE_PIXELS * _RGB_PLANE_COUNT:
                raise UnsupportedImageError(
                    f"FITS data is {hdu.shape}, exceeding the {MAX_IMAGE_PIXELS:,} px limit"
                )
            array = np.asarray(hdu.data)
    except OSError as exc:
        raise UnsupportedImageError(f"Could not read FITS data: {exc}") from exc

    if array.ndim == _MONO_NDIM:
        planes = [array]
    elif array.ndim == _RGB_CUBE_NDIM and array.shape[0] == _RGB_PLANE_COUNT:
        planes = [array[0], array[1], array[2]]
    elif array.ndim == _RGB_CUBE_NDIM and array.shape[-1] == _RGB_PLANE_COUNT:
        planes = [array[..., 0], array[..., 1], array[..., 2]]
    else:
        raise UnsupportedImageError(f"Unsupported FITS data shape {array.shape}")

    if len(planes) == 1:
        return cv2.cvtColor(_auto_stretch_to_uint8(planes[0]), cv2.COLOR_GRAY2BGR)
    rgb = np.stack([p.astype(np.float32) for p in planes], axis=-1)
    return np.clip(stretch_composite_linear(rgb) * 255.0, 0.0, 255.0).astype(np.uint8)


def _decode_raw(data: bytes) -> np.ndarray:
    """Demosaic a camera RAW file via rawpy/libraw.

    Uses the camera's as-shot white balance and libraw's default sRGB-ish
    tone response - unlike FITS above, this isn't scientific linear data by
    convention, so the goal is the same as opening a RAW in any other photo
    tool: a reasonable, normally-exposed starting point to edit further with
    this app's own sliders, not a from-scratch scientific stretch.
    """
    import rawpy  # noqa: PLC0415 - heavy, only imported for an actual RAW upload

    try:
        with rawpy.imread(io.BytesIO(data)) as raw:
            rgb = raw.postprocess(use_camera_wb=True, output_bps=8)
    except rawpy.LibRawError as exc:  # type: ignore[attr-defined]
        raise UnsupportedImageError(f"Could not decode RAW file: {exc}") from exc
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def _to_bgr_uint8(decoded: np.ndarray) -> np.ndarray:
    """Normalize a ``cv2.IMREAD_UNCHANGED`` result (any depth/channel layout) to BGR uint8."""
    if decoded.dtype != np.uint8:
        if decoded.ndim == _MONO_NDIM:
            planes = [decoded]
        else:
            planes = [decoded[..., c] for c in range(decoded.shape[2])]
        stretched = [_auto_stretch_to_uint8(plane) for plane in planes]
        decoded = stretched[0] if len(stretched) == 1 else np.dstack(stretched)
    if decoded.ndim == _MONO_NDIM:
        return cv2.cvtColor(decoded, cv2.COLOR_GRAY2BGR)
    if decoded.shape[2] == _BGRA_CHANNEL_COUNT:
        return cv2.cvtColor(decoded, cv2.COLOR_BGRA2BGR)
    if decoded.shape[2] <= _GRAY_ALPHA_CHANNEL_COUNT:
        # 1 channel (some decoders keep the trailing axis) or gray+alpha: use the
        # luminance plane, drop any alpha. Without this a 2-channel decode would
        # fall through and be returned as a non-BGR array.
        return cv2.cvtColor(np.ascontiguousarray(decoded[..., 0]), cv2.COLOR_GRAY2BGR)
    return decoded


def extension_of(filename: str | None) -> str:
    """Lowercased file extension (with the dot), or ``""`` if there is none."""
    if not filename or "." not in filename:
        return ""
    return filename[filename.rfind(".") :].lower()


def decode_image(data: bytes, filename: str | None = None) -> np.ndarray:
    """Decode raw upload bytes into a BGR ``uint8`` array.

    ``filename``'s extension picks the decoder for formats OpenCV can't read
    on its own (FITS, camera RAW); anything else - including an unrecognised
    or absent extension - goes through OpenCV, which sniffs the real format
    from the bytes (a genuinely 16-bit source, e.g. a stacked TIFF/PNG, is
    auto-stretched the same way FITS is - see ``_auto_stretch_to_uint8``,
    since it's the same "linear stacked frame" case in a different
    container).

    Raises :class:`UnsupportedImageError` if the bytes are not a readable
    image, or if the decoded pixel count exceeds ``MAX_IMAGE_PIXELS`` (a
    decompression bomb - the compressed upload can be small while the decoded
    array is huge).
    """
    ext = extension_of(filename)
    if ext in FITS_FORMATS:
        image = _decode_fits(data)
    elif ext in RAW_FORMATS:
        image = _decode_raw(data)
    else:
        buffer = np.frombuffer(data, dtype=np.uint8)
        decoded = cv2.imdecode(buffer, cv2.IMREAD_UNCHANGED)
        if decoded is None:
            raise UnsupportedImageError("Could not decode image data")
        image = _to_bgr_uint8(decoded)

    height, width = image.shape[:2]
    if height * width > MAX_IMAGE_PIXELS:
        raise UnsupportedImageError(
            f"Decoded image is {width}x{height} ({height * width:,} px), "
            f"exceeding the {MAX_IMAGE_PIXELS:,} px limit"
        )
    return image


def load_image(path: Path) -> np.ndarray:
    """Load an image file as a BGR ``uint8`` array."""
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise UnsupportedImageError(f"Could not read image at {path}")
    return image


def load_image_gray(path: Path) -> np.ndarray:
    """Load an image file as a single-channel ``uint8`` array."""
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise UnsupportedImageError(f"Could not read image at {path}")
    return image


def save_image(image: np.ndarray, path: Path, quality: int = 95) -> None:
    """Write a BGR array to disk, inferring the format from ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    params: list[int] = []
    suffix = path.suffix.lower()
    if suffix in (".jpg", ".jpeg"):
        params = [cv2.IMWRITE_JPEG_QUALITY, int(quality)]
    elif suffix == ".png":
        params = [cv2.IMWRITE_PNG_COMPRESSION, 6]
    if not cv2.imwrite(str(path), image, params):
        raise OSError(f"Failed to write image to {path}")


def encode_image(image: np.ndarray, fmt: str = "jpeg", quality: int = 95) -> bytes:
    """Encode a BGR array to bytes in ``fmt`` (jpeg / png / tiff)."""
    ext = _ENCODE_EXT.get(fmt.lower())
    if ext is None:
        raise UnsupportedImageError(f"Cannot encode to {fmt}")
    params: list[int] = []
    if ext == ".jpg":
        params = [cv2.IMWRITE_JPEG_QUALITY, int(quality)]
    ok, buffer = cv2.imencode(ext, image, params)
    if not ok:
        raise OSError(f"Failed to encode image as {fmt}")
    return buffer.tobytes()


def make_preview(image: np.ndarray, max_size: int = 512) -> np.ndarray:
    """Downscale so the longest edge is at most ``max_size`` px (no upscaling)."""
    height, width = image.shape[:2]
    longest = max(height, width)
    if longest <= max_size:
        return image
    scale = max_size / longest
    new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    return cv2.resize(image, new_size, interpolation=cv2.INTER_AREA)


def compute_histogram(image: np.ndarray) -> dict[str, list[int]]:
    """Return per-channel 256-bin histograms as ``{"r": [...], "g": [...], "b": [...]}``."""
    # image is BGR: channel 0 = B, 1 = G, 2 = R
    channels = {"b": 0, "g": 1, "r": 2}
    result: dict[str, list[int]] = {}
    for name, index in channels.items():
        hist = cv2.calcHist([image], [index], None, [256], [0, 256])
        result[name] = [int(v) for v in hist.flatten()]
    return {"r": result["r"], "g": result["g"], "b": result["b"]}
