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
_FITS_FORMATS = {".fits", ".fit", ".fts"}
_RAW_FORMATS = {".cr2", ".cr3", ".nef", ".arw", ".dng", ".orf", ".rw2", ".pef", ".raf"}
SUPPORTED_FORMATS = _STANDARD_FORMATS | _FITS_FORMATS | _RAW_FORMATS

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


def _auto_stretch_to_uint8(data: np.ndarray) -> np.ndarray:
    """Map one plane of linear scientific/sensor data (any numeric dtype) to uint8."""
    finite = data[np.isfinite(data)]
    if finite.size == 0:
        return np.zeros(data.shape, dtype=np.uint8)
    low, high = np.percentile(finite, [_STRETCH_PERCENTILE_LOW, _STRETCH_PERCENTILE_HIGH])
    if high <= low:
        return np.zeros(data.shape, dtype=np.uint8)

    normalized = np.clip((data.astype(np.float64) - low) / (high - low), 0, 1)
    median = float(np.median(normalized))
    sigma = float(np.median(np.abs(normalized - median))) * _MAD_TO_SIGMA
    black_point = max(0.0, median - _STRETCH_SHADOW_CLIP_SIGMA * sigma)
    clipped = np.clip((normalized - black_point) / max(1e-6, 1.0 - black_point), 0, 1)

    background = float(np.median(clipped))
    stretched: np.ndarray
    if background <= 0:
        stretched = clipped
    else:
        balance = _solve_midtone_balance(background, _STRETCH_TARGET_BACKGROUND)
        stretched = _midtone_transfer(clipped, balance)
    return np.clip(stretched * 255.0, 0, 255).astype(np.uint8)


def _decode_fits(data: bytes) -> np.ndarray:
    """Decode a FITS frame into a BGR uint8 array via the auto-stretch above.

    FITS is scientific/linear data (any of 8/16/32-bit int or float; `BSCALE`/
    `BZERO` header scaling is applied transparently by astropy) - a raw
    stacked frame looks almost black without a non-linear stretch, so every
    FITS upload is auto-stretched regardless of its stored dtype. 2D data is
    treated as monochrome: there's no reliable, standard header keyword for a
    Bayer pattern to safely debayer a raw one-shot-colour sensor frame, so
    guessing one risks a garish checkerboard artifact instead - out of scope
    here. A leading or trailing 3-plane axis is read as RGB, each plane
    stretched independently (this also auto-balances each channel's own black
    level, not just overall brightness - a deliberate, simple choice over a
    single shared transform that would preserve the FITS file's original
    colour balance exactly).
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

    stretched = [_auto_stretch_to_uint8(plane) for plane in planes]
    if len(stretched) == 1:
        return cv2.cvtColor(stretched[0], cv2.COLOR_GRAY2BGR)
    red, green, blue = stretched
    return cv2.merge([blue, green, red])


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
    return decoded


def _extension_of(filename: str | None) -> str:
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
    ext = _extension_of(filename)
    if ext in _FITS_FORMATS:
        image = _decode_fits(data)
    elif ext in _RAW_FORMATS:
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
