"""IntegrationService: the register -> align -> combine passes on CFA data.

``test_stacking`` covers the already-RGB path; these exercise the Bayer-mosaic
path added in Phase 2 - half-resolution registration, then a full-resolution
interpolating debayer for the align/combine passes, with calibration folded in.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.services.calibration import CalibrationService
from app.services.integration import IntegrationService, _reduce_tile
from app.services.storage import StorageService
from app.utils.linear_ingest import LinearFrame

_PATTERN = "GRBG"
_CHANNEL_AT = {"R": 0, "G": 1, "B": 2}


@pytest.fixture
def storage(tmp_path) -> StorageService:
    return StorageService(root=tmp_path)


def _mosaic(height: int, width: int, rgb: tuple[float, float, float]) -> np.ndarray:
    out = np.zeros((height, width), dtype=np.float32)
    for i, channel in enumerate(_PATTERN):
        row, col = i // 2, i % 2
        out[row::2, col::2] = rgb[_CHANNEL_AT[channel]]
    return out


def _star_mosaic(height: int, width: int, seed: int, shift: int) -> np.ndarray:
    """A CFA sky with ~40 stars, optionally shifted by whole Bayer cells."""
    rng = np.random.default_rng(seed)
    frame = _mosaic(height, width, (0.10, 0.14, 0.12))
    frame += rng.normal(0, 0.004, frame.shape).astype(np.float32)
    for _ in range(40):
        cy = int(rng.integers(12, height - 12)) // 2 * 2 + shift * 2
        cx = int(rng.integers(12, width - 12)) // 2 * 2 + shift * 2
        if 0 <= cy < height - 2 and 0 <= cx < width - 2:
            frame[cy : cy + 2, cx : cx + 2] += 0.6
    return np.clip(frame, 0, 1)


def _save_cfa(storage: StorageService, stack_id: str, index: int, data: np.ndarray) -> None:
    storage.save_linear_frame(
        stack_id, index, LinearFrame(data=data, is_cfa=True, bayer_pattern=_PATTERN)
    )


def test_cfa_stack_is_debayered_to_full_resolution(storage: StorageService) -> None:
    height, width = 120, 160
    for i in range(5):
        _save_cfa(storage, "s", i, _star_mosaic(height, width, seed=i, shift=0))

    result = IntegrationService(storage).integrate(
        "s",
        list(range(5)),
        transform="similarity",
        combination="average",
        rejection="winsorized_sigma",
        weighting="none",
    )

    assert result.composite.shape == (height, width, 3)  # full res, not the half-res superpixel
    assert result.composite.max() > result.composite.mean()  # stars survived, not washed out


def test_thread_pool_matches_the_sequential_result(storage: StorageService) -> None:
    """workers=4 (parallel register/align/combine) must be bit-identical to workers=1."""
    height, width = 130, 170
    for i in range(6):
        _save_cfa(storage, "s", i, _star_mosaic(height, width, seed=1, shift=i - 3))

    kwargs = {
        "transform": "similarity",
        "combination": "average",
        "rejection": "winsorized_sigma",
        "weighting": "noise",
    }
    seq = IntegrationService(storage, workers=1).integrate("s", list(range(6)), **kwargs)
    par = IntegrationService(storage, workers=4).integrate("s", list(range(6)), **kwargs)

    assert np.allclose(seq.composite, par.composite, equal_nan=True)
    assert seq.reference_index == par.reference_index
    assert seq.frames_stacked == par.frames_stacked
    assert seq.rejected_samples == par.rejected_samples


def _raise_boom(*_args: object, **_kwargs: object) -> None:
    raise RuntimeError("boom")


def test_a_run_killed_in_combine_resumes_from_the_checkpoint(
    storage: StorageService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The align memmap + plan.json survive a crash; the retry skips register/align."""
    height, width = 130, 170
    for i in range(6):
        _save_cfa(storage, "s", i, _star_mosaic(height, width, seed=1, shift=i - 3))
    kwargs = {
        "transform": "similarity",
        "combination": "average",
        "rejection": "winsorized_sigma",
        "weighting": "noise",
    }

    svc = IntegrationService(storage, workers=1)
    real_combine = svc._combine
    monkeypatch.setattr(svc, "_combine", _raise_boom)
    with pytest.raises(RuntimeError):
        svc.integrate("s", list(range(6)), **kwargs)

    checkpoint = storage.stack_accum_dir("s") / "plan.json"
    assert checkpoint.exists()  # kept for the retry
    assert (storage.stack_accum_dir("s") / "aligned.npy").exists()

    monkeypatch.setattr(svc, "_combine", real_combine)
    registers: list[int] = []
    monkeypatch.setattr(svc, "_register", lambda *a, **k: registers.append(1))
    result = svc.integrate("s", list(range(6)), **kwargs)

    assert not registers  # resumed - the register pass did not run
    assert result.frames_stacked >= 2
    assert result.composite.shape == (height, width, 3)
    assert not checkpoint.exists()  # dropped on success


def test_re_combining_with_a_different_rejection_resumes(
    storage: StorageService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The resume signature ignores rejection/weighting, so changing them on a
    retry still reuses the aligned memmap instead of re-registering."""
    height, width = 130, 170
    for i in range(6):
        _save_cfa(storage, "s", i, _star_mosaic(height, width, seed=1, shift=i - 3))
    svc = IntegrationService(storage, workers=1)

    monkeypatch.setattr(svc, "_combine", _raise_boom)
    with pytest.raises(RuntimeError):
        svc.integrate(
            "s",
            list(range(6)),
            transform="similarity",
            combination="average",
            rejection="none",
            weighting="none",
        )

    monkeypatch.undo()
    registers: list[int] = []
    monkeypatch.setattr(svc, "_register", lambda *a, **k: registers.append(1))
    result = svc.integrate(
        "s",
        list(range(6)),
        transform="similarity",
        combination="median",
        rejection="winsorized_sigma",
        weighting="quality",
    )
    assert not registers
    assert result.composite.shape == (height, width, 3)


def test_cfa_stack_registers_a_shift(storage: StorageService) -> None:
    height, width = 140, 180
    for i in range(6):
        _save_cfa(storage, "s", i, _star_mosaic(height, width, seed=1, shift=i - 2))

    result = IntegrationService(storage).integrate(
        "s",
        list(range(6)),
        transform="similarity",
        combination="average",
        rejection="none",
        weighting="none",
    )

    assert result.aligned
    assert result.frames_stacked >= 5  # the reference plus at least four aligned frames
    assert result.registration_rms < 2.0


def _thin_mosaic(height: int, width: int) -> np.ndarray:
    """A near-starless CFA frame - a cloudy sub."""
    frame = _mosaic(height, width, (0.10, 0.14, 0.12))
    for cy, cx in ((20, 20), (60, 90), (100, 40)):
        frame[cy : cy + 2, cx : cx + 2] += 0.5
    return np.clip(frame, 0, 1)


def test_quality_filter_drops_a_star_poor_frame(storage: StorageService) -> None:
    """A cloudy (near-starless) sub is quality-rejected and does not reach the composite."""
    height, width = 140, 180
    for i in range(5):
        _save_cfa(storage, "s", i, _star_mosaic(height, width, seed=1, shift=0))
    _save_cfa(storage, "s", 5, _thin_mosaic(height, width))

    result = IntegrationService(storage).integrate(
        "s",
        list(range(6)),
        transform="similarity",
        combination="average",
        rejection="none",
        weighting="quality",
        quality_filter="moderate",
    )

    assert result.quality_rejected == 1
    assert len(result.frame_quality) == 6
    assert [q.index for q in result.frame_quality if not q.accepted] == [5]
    assert result.frames_stacked <= 5  # never the cloudy frame
    assert len(result.weights) == result.frames_stacked


def test_protected_frame_is_not_quality_rejected(storage: StorageService) -> None:
    height, width = 140, 180
    for i in range(5):
        _save_cfa(storage, "s", i, _star_mosaic(height, width, seed=1, shift=0))
    _save_cfa(storage, "s", 5, _thin_mosaic(height, width))

    result = IntegrationService(storage).integrate(
        "s",
        list(range(6)),
        transform="similarity",
        combination="average",
        rejection="none",
        weighting="none",
        quality_filter="moderate",
        protected={5},
    )

    assert result.quality_rejected == 0
    assert result.frame_quality[5].accepted is False  # still flagged in the report


def test_calibration_through_integrate_flattens_a_gradient(storage: StorageService) -> None:
    height, width = 120, 160
    ramp = np.linspace(0.6, 1.0, width, dtype=np.float32)[None, :]
    for i in range(4):
        _save_cfa(storage, "s", i, _star_mosaic(height, width, seed=i, shift=0) * ramp)
    for i in range(4):
        storage.save_cal_frame(
            "s",
            "flat",
            i,
            LinearFrame(
                data=(_mosaic(height, width, (0.5, 0.5, 0.5)) * ramp),
                is_cfa=True,
                bayer_pattern=_PATTERN,
            ),
        )

    masters = CalibrationService(storage).build_masters("s", (height, width), is_cfa=True)
    result = IntegrationService(storage).integrate(
        "s",
        list(range(4)),
        transform="similarity",
        combination="average",
        rejection="none",
        weighting="none",
        calibration=masters,
    )

    # column-to-column background trend should be far weaker than the raw 1.0:0.6 ramp
    sky = np.median(result.composite, axis=2)
    left = float(np.median(sky[:, : width // 4]))
    right = float(np.median(sky[:, -width // 4 :]))
    assert abs(left - right) / max(left, right, 1e-6) < 0.15


def _trail_stack(frames: int) -> np.ndarray:
    """A flat, noisy sky stack ``(K, H, W, 1)`` with a bright trail in frame 0 only."""
    rng = np.random.default_rng(3)
    block = (0.05 + rng.normal(0, 0.002, (frames, 32, 1024, 1))).astype(np.float32)
    block[0, 16, :, 0] += 0.5
    return block


@pytest.mark.parametrize("frames", [3, 5, 10])
@pytest.mark.parametrize("rejection", ["sigma", "winsorized_sigma"])
def test_a_one_frame_trail_is_rejected_in_a_short_stack(frames: int, rejection: str) -> None:
    """An aircraft trail in one frame of a short stack leaves no ghost in the mean.

    A mean / std that includes the outlier can never place it ``_KAPPA`` sigma
    away when there are 10 frames or fewer; the median / MAD first pass can.
    """
    weights = np.full((frames, 1, 1, 1), 1.0 / frames, dtype=np.float32)
    tile, rejected, _ = _reduce_tile(_trail_stack(frames), weights, "average", rejection, 2)
    trail_excess = float(tile[16].mean() - tile[4].mean())
    # An unrejected trail would add 0.5 / frames; a trail clamped to the upper
    # bound instead of dropped would still add 3 sigma / frames (0.0006 for 10
    # frames, a visible line once stretched). Dropped, only noise is left: the
    # difference of two 1024-pixel row means is within about 0.00006.
    assert abs(trail_excess) < 0.0002
    assert rejected >= 1024


def test_rejection_handles_partial_coverage() -> None:
    """Pixels a rotated frame did not cover (NaN) are ignored, not treated as outliers."""
    block = _trail_stack(6)
    block[1:3, :, :8] = np.nan  # two frames miss the left strip
    weights = np.full((6, 1, 1, 1), 1.0 / 6, dtype=np.float32)
    tile, _, coverage = _reduce_tile(block, weights, "average", "sigma", 2)
    assert np.isfinite(tile).all()
    assert coverage[0, 0] == 4  # 6 frames minus the 2 missing
    assert abs(float(tile[4, :8].mean()) - 0.05) < 0.003


def test_identical_samples_are_not_clipped_to_one_value() -> None:
    """Where most samples are identical (MAD = 0), the std stands in for the spread.

    Otherwise every sample off the median by a single quantisation step would be
    rejected.
    """
    block = np.full((7, 4, 4, 1), 0.2, dtype=np.float32)
    block[5] = 0.2 + 1 / 255
    block[6] = 0.2 + 2 / 255
    weights = np.full((7, 1, 1, 1), 1.0 / 7, dtype=np.float32)
    tile, rejected, _ = _reduce_tile(block, weights, "average", "sigma", 2)
    assert rejected == 0
    assert np.allclose(tile, block.mean(axis=0))


def _distorted_star_frame(shift: float, rng_seed: int = 21) -> np.ndarray:
    """An RGB sky of ~600 small stars, shifted by ``shift`` px, seen through a
    barrel-distorted wide-angle lens (the lens stays put while the sky moves)."""
    height, width = 360, 480
    rng = np.random.default_rng(rng_seed)
    stars = np.column_stack([rng.uniform(-40, width + 40, 600), rng.uniform(0, height, 600)])
    stars[:, 0] += shift
    centre = np.array([width / 2, height / 2])
    offset = stars - centre
    r2 = (offset**2).sum(axis=1, keepdims=True) / (np.hypot(width, height) / 2) ** 2
    seen = centre + offset * (1 + 0.08 * r2)
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    frame = np.full((height, width), 0.05, dtype=np.float32)
    for (x, y), flux in zip(seen, rng.uniform(0.2, 0.6, len(seen)), strict=True):
        if 2 <= x < width - 2 and 2 <= y < height - 2:
            y0, y1, x0, x1 = int(y) - 4, int(y) + 5, int(x) - 4, int(x) + 5
            patch = (slice(max(y0, 0), y1), slice(max(x0, 0), x1))
            frame[patch] += flux * np.exp(-((xx[patch] - x) ** 2 + (yy[patch] - y) ** 2) / 2.0)
    noise = np.random.default_rng(int(shift * 10) + 1).normal(0, 0.002, frame.shape)
    return np.repeat((frame + noise)[..., np.newaxis], 3, axis=2).astype(np.float32)


def test_a_distorted_wide_field_registers_with_a_polynomial_warp(
    storage: StorageService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Frames whose stars drift differently across the field (distortion) align
    far better with the refined warp than with the global transform alone."""
    from app.services import integration

    def stack(stack_id: str) -> float:
        for i, shift in enumerate((0.0, 8.0, 16.0)):
            storage.save_linear_frame(stack_id, i, LinearFrame(data=_distorted_star_frame(shift)))
        result = IntegrationService(storage).integrate(
            stack_id,
            [0, 1, 2],
            transform="similarity",
            combination="average",
            rejection="sigma",
            weighting="none",
        )
        assert result.aligned
        return result.registration_rms

    refined = stack("warp-on")
    monkeypatch.setattr(integration, "refine_warp", lambda *_args: None)
    rigid = stack("warp-off")
    assert refined < 0.6 * rigid


def test_drizzle_rejects_with_the_warp_the_align_pass_used(
    storage: StorageService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Drizzle's outlier rejection compares each input pixel with the median of
    the warp-aligned frames, so it must place pixels with that same warp: placing
    them with the global transform (as before) rejected clearly more star pixels
    toward the field edges."""
    from app.services import integration

    shifts = (0.0, 15.0, 30.0, 45.0, 60.0)
    for i, shift in enumerate(shifts):
        storage.save_linear_frame("s", i, LinearFrame(data=_distorted_star_frame(shift)))

    def star_rejection(legacy: bool) -> float:
        rejected: list[float] = []
        keep_fn = integration._drizzle_keep

        def spy(
            frame: np.ndarray, coords: tuple[np.ndarray, np.ndarray], *rest: object
        ) -> np.ndarray:
            keep = keep_fn(frame, coords, *rest)  # type: ignore[arg-type]
            stars = frame.mean(axis=2) > 0.15
            rejected.append(float(1.0 - keep[stars].mean()))
            return keep

        monkeypatch.setattr(integration, "_drizzle_keep", spy)
        service = IntegrationService(storage)
        if legacy:
            drizzle = service._drizzle

            def global_placement(stack_id: str, kept: list, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
                for plan in kept:
                    plan.warp = None
                return drizzle(stack_id, kept, *args, **kwargs)

            monkeypatch.setattr(service, "_drizzle", global_placement)
        service.integrate(
            "s",
            list(range(len(shifts))),
            transform="similarity",
            combination="average",
            rejection="sigma",
            weighting="none",
            drizzle=2,
        )
        monkeypatch.undo()
        return float(np.mean(sorted(rejected)[1:]))  # the reference frame is not warped

    assert star_rejection(legacy=False) < star_rejection(legacy=True) - 0.08
