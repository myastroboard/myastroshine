"""CalibrationService - master dark/flat/bias frames and sensor defect removal.

Real stackers calibrate every light frame **on the CFA mosaic, before debayer**
(``initial_plan/12_STACKING_REBUILD.md`` Phase 2):

    calibrated = (light - bias - dark) / flat_field

- **bias / offset** - the sensor's read pedestal (very short exposure).
- **dark** - thermal signal + bias at the light frame's exposure/temperature;
  scaled by the exposure ratio when a separate bias master is available.
- **flat** - the optical path's response (vignetting, dust); its own dark
  (``dark_flat``) or the bias is removed, then it is normalised to a mean of 1.
- **bad-pixel map** - hot pixels from the master dark, dead/cold pixels from the
  master flat; each flagged pixel is replaced with the median of its
  same-Bayer-phase neighbours. This is the honest replacement for the deleted
  "cosmic ray" MAD mask, which clipped real signal.

Masters are built with a per-pixel **median** stack (robust to a satellite
streak or cosmic-ray hit in one calibration sub, and standard for calibration
frames) and cached on disk, keyed on the source frame count so adding more subs
rebuilds them.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from app.exceptions import InvalidParameterError
from app.logging_config import get_logger
from app.services.storage import StorageService

logger = get_logger(__name__)

ProgressFn = Callable[[int], None]

CALIBRATION_KINDS = ("dark", "flat", "bias", "dark_flat")

_MASTER_METHOD = "median"
_MASTER_ITERATIONS = 2
_MASTER_KAPPA = 3.0
_ROW_TILE = 256  # rows per master-stack tile - bounds RAM at K frames * tile * width
_TINY = 1e-8
_MIN_FLAT_FIELD = 0.05  # clamp a normalised flat so a dead corner cannot blow a light pixel up
_HOT_KAPPA = 8.0  # a master-dark pixel this many robust sigma above the median is "hot"
_COLD_KAPPA = 8.0  # a master-flat pixel this far below the median is dead / dust-occluded
_MAD_TO_SIGMA = 1.4826
_MEDIAN_KSIZE = 3
_MONO_NDIM = 2
_COLOR_NDIM = 3
_CFA_STEP = 2


@dataclass(frozen=True)
class CalibrationMasters:
    """The master frames for one stack, plus the derived bad-pixel map.

    Every array is a linear ``float32`` frame in the light frames' own shape -
    a ``(H, W)`` CFA mosaic for a one-shot-colour sensor, or ``(H, W, 3)`` /
    ``(H, W)`` for already-debayered or mono data.
    """

    bias: np.ndarray | None = None
    dark: np.ndarray | None = None
    flat: np.ndarray | None = None
    dark_flat: np.ndarray | None = None
    bad_pixels: np.ndarray | None = None  # bool (H, W), True where the pixel is defective
    dark_exposure_s: float | None = None
    is_cfa: bool = False

    @property
    def is_empty(self) -> bool:
        return (
            self.bias is None
            and self.dark is None
            and self.flat is None
            and self.dark_flat is None
        )


class CalibrationService:
    """Builds and caches master calibration frames and calibrates light frames."""

    def __init__(self, storage: StorageService) -> None:
        self.storage = storage

    # -- master frames -----------------------------------------------------

    def has_frames(self, stack_id: str) -> bool:
        return any(self.storage.cal_frame_counts(stack_id).values())

    def build_masters(
        self,
        stack_id: str,
        light_shape: tuple[int, ...],
        *,
        is_cfa: bool = False,
        on_progress: ProgressFn | None = None,
    ) -> CalibrationMasters:
        """Build (or load from cache) every master the stack has frames for.

        ``light_shape`` is a sample light frame's shape; a master whose frames do
        not match it raises :class:`InvalidParameterError` rather than silently
        producing a broken calibration.
        """
        masters: dict[str, np.ndarray | None] = {}
        for step, kind in enumerate(CALIBRATION_KINDS):
            masters[kind] = self._master(stack_id, kind, light_shape)
            if on_progress:
                on_progress(int(80 * (step + 1) / len(CALIBRATION_KINDS)))

        bad_pixels = self._bad_pixel_map(stack_id, masters, is_cfa=is_cfa)
        if on_progress:
            on_progress(100)
        return CalibrationMasters(
            bias=masters["bias"],
            dark=masters["dark"],
            flat=masters["flat"],
            dark_flat=masters["dark_flat"],
            bad_pixels=bad_pixels,
            dark_exposure_s=self._exposure_seconds(stack_id, "dark"),
            is_cfa=is_cfa,
        )

    def _master(
        self, stack_id: str, kind: str, light_shape: tuple[int, ...]
    ) -> np.ndarray | None:
        indices = self.storage.cal_frame_indices(stack_id, kind)
        if not indices:
            return None

        npy_path = self.storage.master_path(stack_id, kind)
        meta_path = self.storage.master_meta_path(stack_id, kind)
        if npy_path.exists() and meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta.get("source_count") == len(indices):
                cached: np.ndarray = np.load(npy_path)
                return cached

        paths = [self.storage.cal_frame_path(stack_id, kind, i) for i in indices]
        master = _reduce_stack(paths, _MASTER_METHOD)
        if master.shape != tuple(light_shape):
            raise InvalidParameterError(
                f"{kind} calibration frames are {_wh(master.shape)}, "
                f"the light frames are {_wh(light_shape)} - they must match"
            )
        self.storage.stack_cal_root(stack_id, create=True)
        np.save(npy_path, master.astype(np.float32))
        meta_path.write_text(
            json.dumps({"source_count": len(indices), "method": _MASTER_METHOD}), encoding="utf-8"
        )
        logger.info("calibration master built", stack_id=stack_id, kind=kind, frames=len(indices))
        return master

    def _bad_pixel_map(
        self, stack_id: str, masters: dict[str, np.ndarray | None], *, is_cfa: bool
    ) -> np.ndarray | None:
        dark, flat = masters["dark"], masters["flat"]
        if dark is None and flat is None:
            return None

        counts = {k: len(self.storage.cal_frame_indices(stack_id, k)) for k in ("dark", "flat")}
        path = self.storage.bad_pixel_map_path(stack_id)
        meta_path = path.with_suffix(".json")
        if (
            path.exists()
            and meta_path.exists()
            and json.loads(meta_path.read_text(encoding="utf-8")).get("counts") == counts
        ):
            loaded: np.ndarray = np.load(path)
            return loaded

        reference = dark if dark is not None else flat
        assert reference is not None  # noqa: S101 - guarded above
        bad = np.zeros(reference.shape[:2], dtype=bool)
        if dark is not None:
            bad |= _flag_outliers(dark, is_cfa=is_cfa, hot=True, kappa=_HOT_KAPPA)
        if flat is not None:
            bad |= _flag_outliers(flat, is_cfa=is_cfa, hot=False, kappa=_COLD_KAPPA)

        self.storage.stack_cal_root(stack_id, create=True)
        np.save(path, bad)
        meta_path.write_text(json.dumps({"counts": counts}), encoding="utf-8")
        logger.info(
            "bad-pixel map built", stack_id=stack_id, defects=int(bad.sum()), pixels=bad.size
        )
        return bad

    def _exposure_seconds(self, stack_id: str, kind: str) -> float | None:
        indices = self.storage.cal_frame_indices(stack_id, kind)
        if not indices:
            return None
        meta = self.storage.load_cal_acquisition(stack_id, kind, indices[0])
        return _as_float(meta.get("exposure_s"))

    # -- applying calibration -------------------------------------------

    def calibrate(
        self,
        light: np.ndarray,
        masters: CalibrationMasters,
        *,
        light_exposure_s: float | None = None,
        cosmetic: bool = True,
    ) -> np.ndarray:
        """``(light - bias - dark) / flat_field``, then bad-pixel cosmetic repair.

        Operates in whatever shape ``light`` is in (CFA mosaic or debayered);
        every op is element-wise so the arithmetic is the same either way.
        """
        for name in ("bias", "dark", "flat", "dark_flat"):
            master = getattr(masters, name)
            if master is not None and master.shape != light.shape:
                raise InvalidParameterError(
                    f"A light frame is {_wh(light.shape)} but the {name} master is "
                    f"{_wh(master.shape)}"
                )

        out = light.astype(np.float32, copy=True)
        dark = _scaled_dark(masters, light_exposure_s)
        if dark is not None:
            out -= dark
        elif masters.bias is not None:
            out -= masters.bias

        if masters.flat is not None:
            out = out / _flat_field(masters)

        if cosmetic and masters.bad_pixels is not None:
            out = _cosmetic_correct(out, masters.bad_pixels, is_cfa=masters.is_cfa)
        return out.astype(np.float32)


# -- master stacking ----------------------------------------------------------


def _reduce_stack(paths: list[Path], method: str) -> np.ndarray:
    """Combine ``.npy`` calibration frames into one master, tiled over rows."""
    maps = [np.load(p, mmap_mode="r") for p in paths]
    shape = maps[0].shape
    out = np.empty(shape, dtype=np.float32)
    for y0 in range(0, shape[0], _ROW_TILE):
        y1 = min(y0 + _ROW_TILE, shape[0])
        block = np.stack([np.asarray(m[y0:y1], dtype=np.float32) for m in maps])
        out[y0:y1] = _combine_block(block, method)
    return out


def _combine_block(block: np.ndarray, method: str) -> np.ndarray:
    """Reduce ``(K, ...)`` along axis 0 - median or Winsorized-sigma mean."""
    combined: np.ndarray
    if method == "median" or block.shape[0] < _COLOR_NDIM:
        combined = np.median(block, axis=0)
    else:
        mean = block.mean(axis=0)
        std = block.std(axis=0)
        for _ in range(_MASTER_ITERATIONS):
            spread = _MASTER_KAPPA * std
            clipped = np.clip(block, mean - spread, mean + spread)
            mean = clipped.mean(axis=0)
            std = clipped.std(axis=0)
        combined = mean
    return combined.astype(np.float32)


# -- calibration arithmetic -------------------------------------------------


def _scaled_dark(masters: CalibrationMasters, light_exposure_s: float | None) -> np.ndarray | None:
    """Master dark, scaled to the light's exposure when a bias master isolates
    the thermal component (``dark_current = dark - bias``)."""
    dark = masters.dark
    if dark is None:
        return None
    bias, dark_exp = masters.bias, masters.dark_exposure_s
    if bias is not None and light_exposure_s and dark_exp and dark_exp > 0:
        ratio = float(light_exposure_s) / float(dark_exp)
        if abs(ratio - 1.0) > _TINY:
            scaled: np.ndarray = bias + (dark - bias) * ratio
            return scaled
    return dark


def _flat_field(masters: CalibrationMasters) -> np.ndarray:
    """The master flat, its own dark (or the bias) removed and normalised to 1."""
    reference = masters.dark_flat if masters.dark_flat is not None else masters.bias
    field = masters.flat.astype(np.float32, copy=True)  # type: ignore[union-attr]
    if reference is not None:
        field = field - reference
    mean = float(np.mean(field))
    if abs(mean) > _TINY:
        field = field / mean
    clamped: np.ndarray = np.maximum(field, _MIN_FLAT_FIELD)
    return clamped


# -- bad pixels ------------------------------------------------------------


def _flag_outliers(master: np.ndarray, *, is_cfa: bool, hot: bool, kappa: float) -> np.ndarray:
    """A bool ``(H, W)`` map of pixels ``kappa`` robust sigma past the median.

    CFA masters are judged per Bayer phase (the four 2x2 sub-samples sit at
    different signal levels); debayered colour masters per channel.
    """
    if is_cfa and master.ndim == _MONO_NDIM:
        out = np.zeros(master.shape, dtype=bool)
        for r in range(_CFA_STEP):
            for c in range(_CFA_STEP):
                out[r::_CFA_STEP, c::_CFA_STEP] = _plane_outliers(
                    master[r::_CFA_STEP, c::_CFA_STEP], hot=hot, kappa=kappa
                )
        return out
    if master.ndim == _COLOR_NDIM:
        per_channel = [
            _plane_outliers(master[..., ch], hot=hot, kappa=kappa)
            for ch in range(master.shape[2])
        ]
        return np.any(per_channel, axis=0)
    return _plane_outliers(master, hot=hot, kappa=kappa)


def _plane_outliers(plane: np.ndarray, *, hot: bool, kappa: float) -> np.ndarray:
    median = float(np.median(plane))
    sigma = _MAD_TO_SIGMA * float(np.median(np.abs(plane - median))) + _TINY
    if hot:
        result: np.ndarray = plane > median + kappa * sigma
    else:
        result = plane < median - kappa * sigma
    return result


def _cosmetic_correct(frame: np.ndarray, bad: np.ndarray, *, is_cfa: bool) -> np.ndarray:
    """Replace each flagged pixel with the 3x3 median of its own kind of pixel."""
    if is_cfa and frame.ndim == _MONO_NDIM:
        out = frame.copy()
        for r in range(_CFA_STEP):
            for c in range(_CFA_STEP):
                out[r::_CFA_STEP, c::_CFA_STEP] = _median_fill(
                    frame[r::_CFA_STEP, c::_CFA_STEP], bad[r::_CFA_STEP, c::_CFA_STEP]
                )
        return out
    if frame.ndim == _COLOR_NDIM:
        out = frame.copy()
        for ch in range(frame.shape[2]):
            out[..., ch] = _median_fill(frame[..., ch], bad)
        return out
    return _median_fill(frame, bad)


def _median_fill(plane: np.ndarray, bad: np.ndarray) -> np.ndarray:
    if not bad.any():
        return plane
    blurred = cv2.medianBlur(np.ascontiguousarray(plane, dtype=np.float32), _MEDIAN_KSIZE)
    return np.where(bad, blurred, plane)


# -- misc ----------------------------------------------------------------


def _wh(shape: tuple[int, ...]) -> str:
    return f"{shape[1]}x{shape[0]}" if len(shape) >= _MONO_NDIM else str(shape)


def _as_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
