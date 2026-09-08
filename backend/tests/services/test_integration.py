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


def test_cfa_stack_registers_a_shift(storage: StorageService) -> None:
    height, width = 140, 180
    _save_cfa(storage, "s", 0, _star_mosaic(height, width, seed=1, shift=0))
    for i in range(1, 5):
        _save_cfa(storage, "s", i, _star_mosaic(height, width, seed=1, shift=i))

    result = IntegrationService(storage).integrate(
        "s",
        list(range(5)),
        transform="similarity",
        combination="average",
        rejection="none",
        weighting="none",
    )

    assert result.aligned
    assert result.registration_failures == 0
    assert result.registration_rms < 2.0


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
