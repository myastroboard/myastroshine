"""Linear multi-frame ingest for the stacking pipeline.

Turns any supported upload into a :class:`LinearFrame`: ``float32`` pixel data in
a nominal ``[0, 1]`` range, a CFA (Bayer) mosaic kept intact so calibration and
debayering can happen downstream in the right order. This is deliberately
separate from :func:`app.utils.image_utils.decode_image`, which produces the BGR
``uint8`` array the single-image editor works on - stacking needs the linear,
full-bit-depth data that a non-linear 8-bit stretch throws away.

Supported inputs and how each maps to linear:

- **FITS** (``.fits``/``.fit``/``.fts``) - scientific linear data. ``BZERO``/
  ``BSCALE`` are applied by astropy; the result is divided by the dtype's full
  range (65535 for 16-bit, etc.) to reach ``[0, 1]`` while staying linear. A
  ``BAYERPAT`` header marks the frame as CFA and the 2D data is left as a mosaic.
  A ``(3, H, W)`` / ``(H, W, 3)`` cube is read as R/G/B planes.
- **Camera RAW** (``rawpy``/libraw) - demosaiced by libraw with a linear tone
  curve (``gamma=(1, 1)``, ``no_auto_bright=True``, 16-bit), camera white
  balance applied so a set of frames stays consistent. True CFA-preserving RAW
  ingest (for Bayer drizzle) is a later concern.
- **Everything else** via OpenCV. A 16-bit source (a linear stack export) is
  scaled to ``[0, 1]`` as-is. An 8-bit source is a low-precision, already-
  stretched preview (a Seestar JPEG, a screenshot): it is flagged
  ``already_stretched`` and an approximate sRGB EOTF is applied so the numbers
  are at least closer to linear for the integration maths.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass, field

import cv2
import numpy as np

from app.constants import MAX_IMAGE_PIXELS
from app.exceptions import UnsupportedImageError
from app.logging_config import get_logger
from app.utils.image_utils import (
    FITS_FORMATS,
    RAW_FORMATS,
    _auto_stretch_to_uint8,
    extension_of,
    make_preview,
    stretch_composite_linear,
)

logger = get_logger(__name__)

_RGB_PLANE_COUNT = 3
_MONO_NDIM = 2
_CUBE_NDIM = 3

#: uint dtype -> full-scale value used to normalize to [0, 1].
_FULL_SCALE = {
    np.dtype(np.uint8): 255.0,
    np.dtype(np.uint16): 65535.0,
    np.dtype(np.uint32): 4294967295.0,
    np.dtype(np.int16): 65535.0,
    np.dtype(np.int32): 4294967295.0,
}

#: FITS header keywords copied into LinearFrame.metadata (source key -> our key).
_FITS_META_KEYS = {
    "EXPTIME": "exposure_s",
    "EXPOSURE": "exposure_s",
    "GAIN": "gain",
    "CCD-TEMP": "sensor_temp_c",
    "DATE-OBS": "date_obs",
    "INSTRUME": "instrument",
    "TELESCOP": "telescope",
    "OBJECT": "object",
    "FILTER": "filter",
    "IMAGETYP": "image_type",
    "XPIXSZ": "pixel_size_um",
    "FOCALLEN": "focal_length_mm",
}

_FLOAT_ALREADY_NORMALIZED_MAX = 2.0  # a float FITS above this is treated as raw ADU counts

#: CFA pattern -> OpenCV edge-aware demosaic code. OpenCV 5's named aliases put
#: the pattern's top-left element at pixel (0, 0), matching the FITS BAYERPAT
#: convention (verified: a synthetic ``RGGB`` mosaic round-trips to R/G/B).
_BAYER_EA_CODES = {
    "RGGB": cv2.COLOR_BayerRGGB2RGB_EA,
    "GRBG": cv2.COLOR_BayerGRBG2RGB_EA,
    "GBRG": cv2.COLOR_BayerGBRG2RGB_EA,
    "BGGR": cv2.COLOR_BayerBGGR2RGB_EA,
}
#: Flipping a mosaic vertically (ROWORDER = BOTTOM-UP, even height) swaps the two
#: Bayer rows, turning each pattern into its row-swapped partner.
_BAYER_ROW_SWAP = {"RGGB": "GBRG", "GBRG": "RGGB", "GRBG": "BGGR", "BGGR": "GRBG"}
_DEBAYER_LEVELS = 65535.0
_DEBAYER_MIN_SPAN = 1e-4  # floor for a (near-)flat frame's value range before scaling to 16-bit

# sRGB EOTF (IEC 61966-2-1) constants - used to approximately linearise an 8-bit
# already-stretched preview so the integration maths has something closer to linear.
_SRGB_LINEAR_CUTOFF = 0.04045
_SRGB_LINEAR_SLOPE = 12.92
_SRGB_OFFSET = 0.055
_SRGB_SCALE = 1.055
_SRGB_GAMMA = 2.4


@dataclass(frozen=True)
class LinearFrame:
    """One frame as linear ``float32`` data, CFA mosaic intact if applicable.

    ``data`` is ``(H, W)`` for a mono sensor or an undebayered CFA frame, or
    ``(H, W, 3)`` in **R, G, B** channel order for colour data. Values are
    nominally ``[0, 1]`` but not hard-clipped - a bright star can sit slightly
    above 1.0 and calibration can push pixels slightly below 0.0.
    """

    data: np.ndarray
    is_cfa: bool = False
    bayer_pattern: str | None = None
    source_bit_depth: int = 16
    already_stretched: bool = False
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def is_color(self) -> bool:
        return self.data.ndim == _CUBE_NDIM

    @property
    def shape(self) -> tuple[int, int]:
        return (self.data.shape[0], self.data.shape[1])


def ingest_frame(data: bytes, filename: str | None = None) -> LinearFrame:
    """Decode ``data`` into a :class:`LinearFrame`.

    ``filename``'s extension picks the reader (FITS, RAW, or OpenCV for the
    rest). Raises :class:`UnsupportedImageError` for unreadable bytes or a frame
    that exceeds ``MAX_IMAGE_PIXELS``.
    """
    ext = extension_of(filename)
    if ext in FITS_FORMATS:
        frame = _ingest_fits(data)
    elif ext in RAW_FORMATS:
        frame = _ingest_raw(data)
    else:
        frame = _ingest_standard(data)

    height, width = frame.shape
    if height * width > MAX_IMAGE_PIXELS:
        raise UnsupportedImageError(
            f"Decoded frame is {width}x{height} ({height * width:,} px), "
            f"exceeding the {MAX_IMAGE_PIXELS:,} px limit"
        )
    return frame


# -- FITS -----------------------------------------------------------------------


def _ingest_fits(data: bytes) -> LinearFrame:
    from astropy.io import fits  # noqa: PLC0415 - heavy, only for an actual FITS upload

    try:
        with fits.open(io.BytesIO(data)) as hdul:
            hdu = next((h for h in hdul if h.is_image and h.shape), None)
            if hdu is None:
                raise UnsupportedImageError("FITS file has no image data")
            # Header-only size guard before touching hdu.data (a 2880-byte header
            # can declare NAXISn far larger than the real data section). Mirrors
            # app.utils.image_utils._decode_fits.
            if math.prod(hdu.shape) > MAX_IMAGE_PIXELS * _RGB_PLANE_COUNT:
                raise UnsupportedImageError(
                    f"FITS data is {hdu.shape}, exceeding the {MAX_IMAGE_PIXELS:,} px limit"
                )
            array = np.asarray(hdu.data)
            header = hdu.header
    except OSError as exc:
        raise UnsupportedImageError(f"Could not read FITS data: {exc}") from exc

    metadata = {
        our_key: str(header[src_key]).strip()
        for src_key, our_key in _FITS_META_KEYS.items()
        if src_key in header and str(header[src_key]).strip()
    }
    bayer_pattern = str(header.get("BAYERPAT", "")).strip().upper() or None
    bottom_up = str(header.get("ROWORDER", "")).strip().upper() == "BOTTOM-UP"

    if array.ndim == _MONO_NDIM:
        pixels = _to_unit_float(array)
        if bottom_up:
            pixels = np.flipud(pixels)
            if bayer_pattern and array.shape[0] % 2 == 0:
                bayer_pattern = _BAYER_ROW_SWAP.get(bayer_pattern, bayer_pattern)
        return LinearFrame(
            data=np.ascontiguousarray(pixels),
            is_cfa=bayer_pattern is not None,
            bayer_pattern=bayer_pattern,
            source_bit_depth=_bit_depth_of(array.dtype),
            metadata=metadata,
        )

    planes = _rgb_planes(array)
    stacked = np.stack([_to_unit_float(p) for p in planes], axis=-1)
    if bottom_up:
        stacked = np.flipud(stacked)
    return LinearFrame(
        data=np.ascontiguousarray(stacked),
        source_bit_depth=_bit_depth_of(array.dtype),
        metadata=metadata,
    )


def _rgb_planes(array: np.ndarray) -> list[np.ndarray]:
    if array.ndim == _CUBE_NDIM and array.shape[0] == _RGB_PLANE_COUNT:
        return [array[0], array[1], array[2]]
    if array.ndim == _CUBE_NDIM and array.shape[-1] == _RGB_PLANE_COUNT:
        return [array[..., 0], array[..., 1], array[..., 2]]
    raise UnsupportedImageError(f"Unsupported FITS data shape {array.shape}")


# -- camera RAW ---------------------------------------------------------------


def _ingest_raw(data: bytes) -> LinearFrame:
    import rawpy  # noqa: PLC0415 - heavy, only for an actual RAW upload

    try:
        with rawpy.imread(io.BytesIO(data)) as raw:
            rgb16 = raw.postprocess(
                gamma=(1, 1),
                no_auto_bright=True,
                use_camera_wb=True,
                output_bps=16,
            )
    except rawpy.LibRawError as exc:  # type: ignore[attr-defined]
        raise UnsupportedImageError(f"Could not decode RAW file: {exc}") from exc

    return LinearFrame(
        data=np.ascontiguousarray(rgb16.astype(np.float32) / 65535.0),
        source_bit_depth=16,
        metadata={"image_type": "Light"},
    )


# -- standard formats (OpenCV) ----------------------------------------------


def _ingest_standard(data: bytes) -> LinearFrame:
    buffer = np.frombuffer(data, dtype=np.uint8)
    decoded = cv2.imdecode(buffer, cv2.IMREAD_UNCHANGED)
    if decoded is None:
        raise UnsupportedImageError("Could not decode image data")

    if decoded.ndim == _MONO_NDIM:
        rgb = decoded
    elif decoded.shape[2] == _RGB_PLANE_COUNT:
        rgb = cv2.cvtColor(decoded, cv2.COLOR_BGR2RGB)
    elif decoded.shape[2] >= 4:  # noqa: PLR2004 - BGRA
        rgb = cv2.cvtColor(decoded, cv2.COLOR_BGRA2RGB)
    else:  # 2-channel gray+alpha: keep the luminance plane
        rgb = np.ascontiguousarray(decoded[..., 0])

    already_stretched = decoded.dtype == np.uint8
    pixels = _to_unit_float(rgb)
    if already_stretched:
        pixels = _srgb_to_linear(pixels)

    return LinearFrame(
        data=np.ascontiguousarray(pixels),
        source_bit_depth=_bit_depth_of(decoded.dtype),
        already_stretched=already_stretched,
    )


# -- display ----------------------------------------------------------------

_CFA_2X2 = 2


def to_display_bgr(frame: LinearFrame, max_size: int = 256) -> np.ndarray:
    """An auto-stretched BGR ``uint8`` thumbnail of a linear frame, for the UI.

    A CFA frame is roughly de-mosaiced by 2x2 superpixel averaging (half
    resolution, no interpolation) - enough to spot a trail or cloud in a grid
    tile; the real debayer happens in the stacking pipeline. Each channel is
    stretched independently with the same screen-transfer-function auto-stretch
    the single-image FITS ingest uses.

    The linear plane is **downscaled to the thumbnail size first**, then
    stretched - the STF's median/MAD pass over a few thousand pixels is
    visually the same as over two megapixels and ~20x cheaper (thumbnail
    generation dominates a multi-frame upload).
    """
    if frame.is_cfa and frame.bayer_pattern:
        planes = _cfa_superpixel(frame.data, frame.bayer_pattern)
    elif frame.is_color:
        planes = [frame.data[..., 0], frame.data[..., 1], frame.data[..., 2]]
    else:
        small = make_preview(frame.data, max_size)
        return cv2.cvtColor(_auto_stretch_to_uint8(small), cv2.COLOR_GRAY2BGR)

    small_planes = (make_preview(p, max_size) for p in planes)
    red, green, blue = (_auto_stretch_to_uint8(p) for p in small_planes)
    return cv2.merge([blue, green, red])


def stretch_composite_bgr(composite: np.ndarray, max_size: int = 4096) -> np.ndarray:
    """Auto-stretch a linear stacked composite to a display BGR ``uint8`` frame.

    A thin wrapper over :func:`app.utils.image_utils.stretch_composite_linear`
    (downscale first, then the neutralise + shared-midtone stretch, then quantise)
    for callers that just want a preview JPEG. The editor drives the same linear
    core through :func:`app.services.post_stack.render_stack_base` with a tunable
    target background instead.
    """
    small = make_preview(composite.astype(np.float32), max_size)
    stretched = stretch_composite_linear(small)
    return np.clip(stretched * 255.0, 0, 255).astype(np.uint8)


def superpixel_rgb(frame: LinearFrame) -> LinearFrame:
    """2x2 superpixel de-mosaic of a CFA frame into half-resolution linear RGB.

    No interpolation, so it halves resolution but has zero colour-fringing and
    costs almost nothing - the stacking pipeline uses it for the registration
    measurement pass (star centroids, background), where half resolution is
    plenty, and falls back to it for a Bayer pattern :func:`debayer_rgb` does not
    recognise. A non-CFA frame is returned unchanged.
    """
    if not frame.is_cfa or not frame.bayer_pattern:
        return frame
    red, green, blue = _cfa_superpixel(frame.data, frame.bayer_pattern)
    return LinearFrame(
        data=np.ascontiguousarray(np.stack([red, green, blue], axis=-1)),
        source_bit_depth=frame.source_bit_depth,
        already_stretched=frame.already_stretched,
        metadata=frame.metadata,
    )


def debayer_rgb(frame: LinearFrame) -> LinearFrame:
    """Full-resolution interpolating debayer of a CFA frame into linear RGB.

    Uses OpenCV's **edge-aware** demosaic (``COLOR_BayerXX2RGB_EA``), which keeps
    full resolution and suppresses the zipper artefacts a bilinear debayer
    leaves on the high-contrast edges of a star field. The stacking pipeline
    uses this for the align/combine passes (after calibration, on the CFA
    mosaic). A non-CFA frame is returned unchanged; an unrecognised Bayer
    pattern falls back to :func:`superpixel_rgb`.

    OpenCV only demosaics integer data, so the linear float frame is mapped onto
    16-bit by ``offset + scale`` - preserving the full value range including any
    negative pedestal calibration left behind - then mapped back.
    """
    if not frame.is_cfa or not frame.bayer_pattern:
        return frame
    code = _BAYER_EA_CODES.get(frame.bayer_pattern)
    if code is None:
        logger.warning("unrecognised Bayer pattern, skipping debayer", pattern=frame.bayer_pattern)
        return frame

    data = frame.data.astype(np.float32)
    offset = min(float(data.min()), 0.0)
    scale = max(float(data.max()) - offset, _DEBAYER_MIN_SPAN)
    quantised = np.clip((data - offset) / scale * _DEBAYER_LEVELS, 0, _DEBAYER_LEVELS).astype(
        np.uint16
    )
    rgb = cv2.cvtColor(quantised, code).astype(np.float32) / _DEBAYER_LEVELS * scale + offset
    return LinearFrame(
        data=np.ascontiguousarray(rgb),
        source_bit_depth=frame.source_bit_depth,
        already_stretched=frame.already_stretched,
        metadata=frame.metadata,
    )


def _cfa_superpixel(cfa: np.ndarray, pattern: str) -> list[np.ndarray]:
    """Collapse each Bayer 2x2 cell to one R/G/B triple (half-res, no interpolation)."""
    offsets: dict[str, list[tuple[int, int]]] = {"R": [], "G": [], "B": []}
    for i, channel in enumerate(pattern[:4]):
        offsets.setdefault(channel, []).append((i // _CFA_2X2, i % _CFA_2X2))

    def gather(channel: str) -> np.ndarray:
        cells = [cfa[r::_CFA_2X2, c::_CFA_2X2] for r, c in offsets[channel]]
        rows = min(x.shape[0] for x in cells)
        cols = min(x.shape[1] for x in cells)
        return np.mean([x[:rows, :cols] for x in cells], axis=0).astype(np.float32)

    return [gather("R"), gather("G"), gather("B")]


# -- numeric helpers --------------------------------------------------------


def _to_unit_float(array: np.ndarray) -> np.ndarray:
    """Scale any numeric dtype to a nominal ``[0, 1]`` ``float32``, staying linear."""
    if np.issubdtype(array.dtype, np.floating):
        finite = array[np.isfinite(array)]
        peak = float(finite.max()) if finite.size else 1.0
        scaled = array.astype(np.float32)
        if peak > _FLOAT_ALREADY_NORMALIZED_MAX:
            scaled = scaled / peak
    else:
        scale = _FULL_SCALE.get(np.dtype(array.dtype), float(np.iinfo(array.dtype).max))
        scaled = array.astype(np.float32) / scale
    result: np.ndarray = np.nan_to_num(scaled.astype(np.float32), nan=0.0)
    return result


def _bit_depth_of(dtype: np.dtype) -> int:
    if np.issubdtype(dtype, np.floating):
        return 32
    return int(np.dtype(dtype).itemsize * 8)


def _srgb_to_linear(x: np.ndarray) -> np.ndarray:
    """Approximate sRGB EOTF - the best guess at linearising an 8-bit preview."""
    linear = x / _SRGB_LINEAR_SLOPE
    gamma = ((x + _SRGB_OFFSET) / _SRGB_SCALE) ** _SRGB_GAMMA
    result: np.ndarray = np.where(x <= _SRGB_LINEAR_CUTOFF, linear, gamma).astype(np.float32)
    return result
