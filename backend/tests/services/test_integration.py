"""IntegrationService: the register -> align -> combine passes on CFA data.

``test_stacking`` covers the already-RGB path; these exercise the Bayer-mosaic
path added in Phase 2 - half-resolution registration, then a full-resolution
interpolating debayer for the align/combine passes, with calibration folded in.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.services.calibration import CalibrationService
from app.services.integration import IntegrationService
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
            "s", list(range(6)), transform="similarity", combination="average",
            rejection="none", weighting="none",
        )

    monkeypatch.undo()
    registers: list[int] = []
    monkeypatch.setattr(svc, "_register", lambda *a, **k: registers.append(1))
    result = svc.integrate(
        "s", list(range(6)), transform="similarity", combination="median",
        rejection="winsorized_sigma", weighting="quality",
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
