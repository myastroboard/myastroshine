"""IntegrationService - register, normalise and combine a frame stack.

Three memory-bounded passes over the frames (see
``initial_plan/12_STACKING_REBUILD.md`` Phases 1-3):

1. **Register** - calibrate (Phase 2) then superpixel-debayer every frame (half
   resolution is plenty for star centroids), measure each frame's star count /
   FWHM / roundness / background / noise, **score** them and drop the ones the
   ``quality_filter`` rejects (Phase 3), pick the best remaining frame as the
   reference, and match each other frame's asterisms to it
   (:class:`StarMatchService`) for a transform. Frames that fail to match are
   rejected too.
2. **Align** - load each kept frame again, calibrate it and **interpolating**-
   debayer it at full resolution, warp it into the reference frame (Lanczos,
   the registration transform's translation scaled up from half to full res),
   normalise it (additive + multiplicative to the reference) and stream it to a
   ``float16`` memmap on disk.
3. **Combine** - tile over the memmap rows; per pixel across the stack, do
   Winsorized-sigma rejection and a weighted mean.

Only a few frames and one row-tile are ever resident, so a thousand-frame stack
runs in bounded RAM.
"""

from __future__ import annotations

import contextlib
import math
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

import cv2
import numpy as np
from numpy.lib.format import open_memmap

from app.exceptions import InvalidParameterError
from app.logging_config import get_logger
from app.services.calibration import CalibrationMasters, CalibrationService
from app.services.frame_quality import FrameMeasure, FrameQuality, score_frames
from app.services.star_detection import StarDetectionService
from app.services.star_match import StarMatchService
from app.services.storage import StorageService
from app.utils.image_utils import _auto_stretch_to_uint8
from app.utils.linear_ingest import LinearFrame, debayer_rgb, superpixel_rgb

logger = get_logger(__name__)

ProgressFn = Callable[[str, int], None]

_DETECT_SENSITIVITY = 60
_DETECT_MAX_SIZE = 22
_MIN_REFERENCE_STARS = 8  # below this, registration is hopeless - fall back to no alignment
_MIN_FRAMES_KEPT = 2  # the quality filter never drops below this many frames
_SCALE_CLIP = (0.2, 5.0)
_KAPPA = 3.0  # sigma rejection threshold
_REJECT_ITERATIONS = 2
_MAD_TO_SIGMA = 1.4826
_ROW_TILE = 128
_MIN_ROW_TILE = 8
_TILE_BUDGET_BYTES = 48_000_000  # target working-set for one combine tile (K frames x rows x W x C)
_TINY = 1e-12
_WEIGHT_CLIP = (0.25, 4.0)  # a frame's weight can be at most 4x / at least 1/4 the median
_MIN_COVERAGE = 0.3  # skip pixel rejection where < 30% of frames overlap (rotation wedge)
_MONO_NDIM = 2
_RGB_LUMA = np.array([0.299, 0.587, 0.114], dtype=np.float32)  # data is R, G, B
_NOISE_FLOOR = 1e-6
_SCALE_PERCENTILE = 95


@dataclass
class _FramePlan:
    index: int
    centroids: np.ndarray  # (S, 2), brightest first
    star_count: int
    background: float
    scale: float
    noise: float
    fwhm: float = 0.0  # px, median star FWHM proxy
    roundness: float = 1.0  # 0..1, 1 = round
    matrix: np.ndarray | None = None  # frame -> reference; set in pass 1
    rms: float = 0.0
    registered: bool = False
    #: dropped by the frame-quality filter (kept separate from a registration failure).
    quality_rejected: bool = False

    def measure(self) -> FrameMeasure:
        return FrameMeasure(
            self.index, self.star_count, self.fwhm, self.roundness,
            self.background, self.noise, self.scale,
        )


@dataclass
class IntegrationResult:
    composite: np.ndarray  # (H, W, 3) float32, linear
    coverage: np.ndarray  # (H, W) int32 - how many frames contributed to each pixel
    frames_stacked: int
    registration_failures: int
    reference_index: int
    rejected_samples: int
    registration_rms: float  # mean inlier RMS over the registered frames
    reference_noise: float  # background noise of the reference frame (same units as the composite)
    aligned: bool  # False when the stack was integrated without registration
    quality_rejected: int = 0  # frames dropped by the frame-quality filter
    frame_quality: list[FrameQuality] = field(default_factory=list)
    weights: list[float] = field(default_factory=list)

    @property
    def effective_frames(self) -> float:
        """``(sum w)^2 / sum(w^2)`` - N for equal weights, less when weighting is uneven."""
        w = np.array(self.weights, dtype=np.float64)
        return float(w.sum() ** 2 / np.square(w).sum()) if w.size else 0.0


class IntegrationService:
    """Owns the register -> align -> combine pipeline for one stack."""

    def __init__(self, storage: StorageService) -> None:
        self.storage = storage
        self._detector = StarDetectionService()
        self._matcher = StarMatchService()
        self._calibration = CalibrationService(storage)

    def integrate(
        self,
        stack_id: str,
        indices: list[int],
        *,
        transform: str,
        combination: str,
        rejection: str,
        weighting: str,
        quality_filter: str = "off",
        protected: set[int] | None = None,
        calibration: CalibrationMasters | None = None,
        cosmetic: bool = True,
        on_progress: ProgressFn | None = None,
    ) -> IntegrationResult:
        cal = calibration if calibration is not None and not calibration.is_empty else None
        plans, reference, half_shape, qualities = self._register(
            stack_id, indices, transform, quality_filter, protected or set(), cal, cosmetic,
            on_progress,
        )
        aligned = reference.star_count >= _MIN_REFERENCE_STARS
        registrable = [p for p in plans if not p.quality_rejected]
        kept = [p for p in registrable if p.registered] if aligned else registrable
        quality_by_index = {q.index: q for q in qualities}
        weights = _frame_weights(kept, quality_by_index, weighting)

        aligned_path, full_shape, reference_noise = self._align_to_memmap(
            stack_id, kept, reference, half_shape, aligned, cal, cosmetic, on_progress
        )
        try:
            composite, rejected, coverage = self._combine(
                aligned_path, weights, combination, rejection, full_shape, on_progress
            )
        finally:
            with contextlib.suppress(OSError):
                Path(aligned_path).unlink()

        registered = [p for p in kept if p.rms > 0]
        return IntegrationResult(
            composite=composite,
            coverage=coverage,
            frames_stacked=len(kept),
            registration_failures=(len(registrable) - len(kept)) if aligned else 0,
            reference_index=reference.index,
            rejected_samples=rejected,
            registration_rms=round(float(np.mean([p.rms for p in registered])), 2)
            if registered
            else 0.0,
            reference_noise=reference_noise,
            aligned=aligned,
            quality_rejected=sum(1 for p in plans if p.quality_rejected),
            frame_quality=qualities,
            weights=list(weights),
        )

    # -- pass 1: registration -------------------------------------------------

    def _register(
        self,
        stack_id: str,
        indices: list[int],
        transform: str,
        quality_filter: str,
        protected: set[int],
        calibration: CalibrationMasters | None,
        cosmetic: bool,
        on_progress: ProgressFn | None,
    ) -> tuple[list[_FramePlan], _FramePlan, tuple[int, int, int], list[FrameQuality]]:
        plans: list[_FramePlan] = []
        shape: tuple[int, int, int] | None = None
        for step, index in enumerate(indices):
            data = self._prepared(stack_id, index, calibration, cosmetic)
            frame_shape = (data.shape[0], data.shape[1], data.shape[2])
            if shape is None:
                shape = frame_shape
            elif frame_shape != shape:
                raise InvalidParameterError("All frames must share dimensions to stack")
            plans.append(self._measure(index, data))
            if on_progress and step % 20 == 0:
                on_progress("registration", int(30 * step / max(1, len(indices))))
        assert shape is not None  # noqa: S101 - indices is non-empty (caller guarantees >= 2)

        qualities = score_frames([p.measure() for p in plans], quality_filter)
        rejected = {q.index for q in qualities if not q.accepted} - protected
        if len(plans) - len(rejected) >= _MIN_FRAMES_KEPT:
            for plan in plans:
                plan.quality_rejected = plan.index in rejected
        elif rejected:
            logger.warning(
                "frame-quality filter would drop too many frames - keeping all",
                stack_id=stack_id,
                would_reject=len(rejected),
            )

        pool = [p for p in plans if not p.quality_rejected]
        reference = _pick_reference(pool, plans)
        reference.registered = True
        reference.matrix = np.eye(2, 3, dtype=np.float64)

        if reference.star_count < _MIN_REFERENCE_STARS:
            logger.warning(
                "stack registration skipped - too few stars on the best frame",
                stack_id=stack_id,
                stars=reference.star_count,
            )
            return plans, reference, shape, qualities

        for step, plan in enumerate(plans):
            if plan is reference or plan.quality_rejected:
                continue
            result = self._matcher.align(plan.centroids, reference.centroids, transform)
            if result.ok and result.matrix is not None:
                plan.matrix, plan.rms, plan.registered = result.matrix, result.rms, True
            if on_progress and step % 20 == 0:
                on_progress("registration", 30 + int(20 * step / max(1, len(plans))))
        return plans, reference, shape, qualities

    def _measure(self, index: int, data: np.ndarray) -> _FramePlan:
        luma = data @ _RGB_LUMA
        stars = self._detector.detect(
            _auto_stretch_to_uint8(luma), _DETECT_SENSITIVITY, _DETECT_MAX_SIZE
        )
        stars.sort(key=lambda s: s.radius, reverse=True)
        centroids = np.array([(s.x, s.y) for s in stars], dtype=np.float64).reshape(-1, 2)

        background = float(np.median(data))
        scale = max(float(np.percentile(data, _SCALE_PERCENTILE)) - background, _NOISE_FLOOR)
        noise = max(highpass_noise(luma), _NOISE_FLOOR)
        radii = np.array([s.radius for s in stars], dtype=np.float64)
        fwhm = float(2.0 * np.median(radii)) if radii.size else 0.0
        roundness = float(np.median([s.roundness for s in stars])) if stars else 1.0
        return _FramePlan(
            index, centroids, len(stars), background, scale, noise, fwhm=fwhm, roundness=roundness
        )

    # -- pass 2: align to a memmap -----------------------------------------

    def _align_to_memmap(
        self,
        stack_id: str,
        kept: list[_FramePlan],
        reference: _FramePlan,
        half_shape: tuple[int, int, int],
        aligned: bool,
        calibration: CalibrationMasters | None,
        cosmetic: bool,
        on_progress: ProgressFn | None,
    ) -> tuple[str, tuple[int, int, int], float]:
        """Warp + normalise every kept frame into a ``float16`` memmap.

        Registration measured everything on the half-resolution superpixel
        image; the align pass works at the full-resolution interpolating
        debayer, so each transform's translation is scaled by the resolution
        ratio (rotation / scale are ratios and need no change).
        """
        ref_frame = self._prepared_full(stack_id, reference.index, calibration, cosmetic)
        height, width, channels = ref_frame.shape
        scale_x = width / max(1, half_shape[1])
        scale_y = height / max(1, half_shape[0])
        reference_noise = max(highpass_noise(ref_frame @ _RGB_LUMA), _NOISE_FLOOR)

        path = self.storage.stack_accum_dir(stack_id, create=True) / "aligned.npy"
        memmap = open_memmap(
            path, mode="w+", dtype=np.float16, shape=(len(kept), height, width, channels)
        )
        for slot, plan in enumerate(kept):
            if plan is reference:
                frame = ref_frame
            else:
                frame = self._prepared_full(stack_id, plan.index, calibration, cosmetic)
                if aligned and plan.matrix is not None:
                    matrix = plan.matrix.astype(np.float64).copy()
                    matrix[0, 2] *= scale_x
                    matrix[1, 2] *= scale_y
                    frame = cv2.warpAffine(
                        frame,
                        matrix.astype(np.float32),
                        (width, height),
                        flags=cv2.INTER_LANCZOS4,
                        borderMode=cv2.BORDER_CONSTANT,
                        borderValue=(math.nan, math.nan, math.nan),
                    )
            multiplier = float(np.clip(reference.scale / plan.scale, *_SCALE_CLIP))
            frame = frame * multiplier + (reference.background - multiplier * plan.background)
            memmap[slot] = frame.astype(np.float16)
            if on_progress and slot % 20 == 0:
                on_progress("normalization", 50 + int(25 * slot / max(1, len(kept))))
        memmap.flush()
        del memmap
        return str(path), (height, width, channels), reference_noise

    # -- pass 3: tiled combine ------------------------------------------

    def _combine(
        self,
        aligned_path: str,
        weights: np.ndarray,
        combination: str,
        rejection: str,
        shape: tuple[int, int, int],
        on_progress: ProgressFn | None,
    ) -> tuple[np.ndarray, int, np.ndarray]:
        height, width, channels = shape
        memmap = open_memmap(aligned_path, mode="r")
        w = (weights / weights.sum()).astype(np.float32).reshape(-1, 1, 1, 1)
        min_cover = max(2, math.ceil(_MIN_COVERAGE * len(weights)))
        composite = np.zeros(shape, dtype=np.float32)
        coverage = np.zeros((height, width), dtype=np.int32)
        rejected = 0

        row_bytes = len(weights) * width * channels * 4
        tile_rows = int(np.clip(_TILE_BUDGET_BYTES // max(1, row_bytes), _MIN_ROW_TILE, _ROW_TILE))
        aligned = Path(aligned_path)
        for y0 in range(0, height, tile_rows):
            y1 = min(y0 + tile_rows, height)
            with contextlib.suppress(OSError):
                aligned.touch()  # fresh mtime: the stale-work sweep must leave a live run alone
            block = np.asarray(memmap[:, y0:y1], dtype=np.float32)  # (K, th, W, C)
            tile, cut, cover = _reduce_tile(block, w, combination, rejection, min_cover)
            composite[y0:y1] = tile
            coverage[y0:y1] = cover
            rejected += cut
            if on_progress:
                on_progress("integration", 75 + int(25 * y1 / height))

        del memmap
        return composite, rejected, coverage

    # -- helpers ------------------------------------------------------------

    def _prepared(
        self, stack_id: str, index: int, calibration: CalibrationMasters | None, cosmetic: bool
    ) -> np.ndarray:
        """Calibrate then superpixel-debayer (half-res), returning ``(H, W, 3)`` float32."""
        frame = self._load_calibrated(stack_id, index, calibration, cosmetic)
        return _as_rgb(superpixel_rgb(frame))

    def _prepared_full(
        self, stack_id: str, index: int, calibration: CalibrationMasters | None, cosmetic: bool
    ) -> np.ndarray:
        """Calibrate then interpolating-debayer (full-res), returning ``(H, W, 3)`` float32."""
        return _as_rgb(debayer_rgb(self._load_calibrated(stack_id, index, calibration, cosmetic)))

    def _load_calibrated(
        self, stack_id: str, index: int, calibration: CalibrationMasters | None, cosmetic: bool
    ) -> LinearFrame:
        frame = self.storage.load_linear_frame(stack_id, index)
        if calibration is None:
            return frame
        data = self._calibration.calibrate(
            frame.data,
            calibration,
            light_exposure_s=_exposure_seconds(frame.metadata),
            cosmetic=cosmetic,
        )
        return replace(frame, data=data)


_REF_TIME_WEIGHT = 0.4
_REF_FWHM_WEIGHT = 0.5


def _pick_reference(pool: list[_FramePlan], plans: list[_FramePlan]) -> _FramePlan:
    """Choose the registration reference: the frame nearest the session centre.

    Not "most stars" - on an alt-az mount a frame where a rich cluster has
    drifted to centre, or a transparency spike, is an outlier, and using it as
    the reference shrinks the common footprint and off-centres the target. This
    prefers a **typical** star count near the temporal middle (which halves the
    field rotation to either end) and, among those, the sharpest.
    """
    position = {id(plan): step for step, plan in enumerate(plans)}
    stars = np.array([p.star_count for p in pool], dtype=np.float64)
    fwhm = np.array([p.fwhm for p in pool if p.fwhm > 0], dtype=np.float64)
    median_stars = max(float(np.median(stars)), 1.0)
    median_fwhm = float(np.median(fwhm)) if fwhm.size else 0.0
    middle = max(len(plans) / 2.0, 1.0)

    def cost(plan: _FramePlan) -> float:
        star_dev = abs(plan.star_count - median_stars) / median_stars
        time_dev = abs(position[id(plan)] - middle) / middle
        sharp_dev = (
            max(0.0, plan.fwhm / median_fwhm - 1.0) if median_fwhm > 0 and plan.fwhm > 0 else 0.0
        )
        return star_dev + _REF_TIME_WEIGHT * time_dev + _REF_FWHM_WEIGHT * sharp_dev

    return min(pool, key=cost)


def _as_rgb(frame: LinearFrame) -> np.ndarray:
    """A contiguous ``(H, W, 3)`` float32 view of a debayered / mono frame."""
    data = frame.data.astype(np.float32)
    if data.ndim == _MONO_NDIM:
        data = np.repeat(data[:, :, np.newaxis], 3, axis=2)
    return np.ascontiguousarray(data)


def _exposure_seconds(metadata: dict[str, str]) -> float | None:
    try:
        return float(metadata["exposure_s"])
    except (KeyError, TypeError, ValueError):
        return None


def highpass_noise(gray: np.ndarray) -> float:
    """Robust pixel-to-pixel noise of a centred crop, gradient removed."""
    height, width = gray.shape[:2]
    crop = np.ascontiguousarray(
        gray[height // 4 : 3 * height // 4, width // 4 : 3 * width // 4], dtype=np.float32
    )
    residual = crop - cv2.medianBlur(crop, 3)
    return _MAD_TO_SIGMA * float(np.median(np.abs(residual - np.median(residual))))


def _frame_weights(
    plans: list[_FramePlan], quality_by_index: dict[int, FrameQuality], weighting: str
) -> np.ndarray:
    """Per-frame integration weights, clamped so a bad noise estimate on one
    frame cannot swamp the stack (a raw ``1/noise^2`` spread of 5x becomes 25x).

    - ``none``: equal. ``noise``: ``1/noise^2``. ``quality``: the frame-quality
      scorer's combined weight (SNR + star count + sharpness, already clamped
      and normalised to a median of 1).
    """
    if weighting == "none" or not plans:
        return np.ones(len(plans), dtype=np.float64)
    if weighting == "quality":
        return np.array(
            [quality_by_index[p.index].weight for p in plans], dtype=np.float64
        )
    noise = np.array([p.noise for p in plans], dtype=np.float64)
    return np.clip((np.median(noise) / noise) ** 2, *_WEIGHT_CLIP)


def _reduce_tile(
    block: np.ndarray, weights: np.ndarray, combination: str, rejection: str, min_cover: int
) -> tuple[np.ndarray, int, np.ndarray]:
    """Reject outliers then combine one row-tile across the stack axis.

    Iterative sigma-clip around the mean (fast, sum-based - ``np.nanmedian``
    along the stack axis is ~100x slower and not worth it here). ``block`` is
    NaN where a rotated frame did not cover the pixel; rejection is skipped
    where fewer than ``min_cover`` frames overlap (the field-rotation wedge),
    since the per-pixel sigma there is too noisy to trust.
    """
    finite = np.isfinite(block)
    coverage = finite.sum(axis=0)
    keep = finite.copy()
    rejected = 0

    if rejection in ("sigma", "winsorized_sigma"):
        lo = hi = None
        for _ in range(_REJECT_ITERATIONS):
            count = np.maximum(keep.sum(axis=0), 1)
            mean = np.where(keep, block, 0.0).sum(axis=0) / count
            var = np.where(keep, (block - mean) ** 2, 0.0).sum(axis=0) / count
            spread = _KAPPA * np.sqrt(var)
            lo, hi = mean - spread, mean + spread
            keep = finite & (block >= lo) & (block <= hi) & (coverage >= min_cover)
        keep |= finite & (coverage < min_cover)  # unclipped where too few frames overlap
        rejected = int(np.count_nonzero(finite & ~keep))
        if rejection == "winsorized_sigma" and lo is not None:
            block = np.where(coverage >= min_cover, np.clip(block, lo, hi), block)
            keep = finite

    frame_coverage = coverage[..., 0].astype(np.int32)  # how many frames hit each pixel
    if combination == "median":
        tile = np.nanmedian(np.where(keep, block, np.nan), axis=0)
        return np.nan_to_num(tile, nan=0.0), rejected, frame_coverage

    weight_sum = (keep * weights).sum(axis=0)
    tile = (np.where(keep, block, 0.0) * weights).sum(axis=0) / np.maximum(weight_sum, _TINY)
    return np.where(weight_sum > 0, tile, 0.0).astype(np.float32), rejected, frame_coverage
