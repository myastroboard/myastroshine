"""CalibrationService: master frames, calibration arithmetic, bad-pixel repair."""

from __future__ import annotations

import numpy as np
import pytest

from app.exceptions import InvalidParameterError
from app.services.calibration import CalibrationService
from app.services.storage import StorageService
from app.utils.linear_ingest import LinearFrame


@pytest.fixture
def storage(tmp_path) -> StorageService:
    return StorageService(root=tmp_path)


@pytest.fixture
def calibration(storage: StorageService) -> CalibrationService:
    return CalibrationService(storage)


def _save(storage: StorageService, stack_id: str, kind: str, frames: list[np.ndarray], **meta):
    existing = storage.cal_frame_indices(stack_id, kind)
    start = existing[-1] + 1 if existing else 0
    for offset, data in enumerate(frames):
        storage.save_cal_frame(
            stack_id,
            kind,
            start + offset,
            LinearFrame(data=data.astype(np.float32), metadata=dict(meta)),
        )


def test_master_dark_rejects_a_cosmic_ray_hit(
    storage: StorageService, calibration: CalibrationService
) -> None:
    """A Winsorized-sigma stack shrugs off one frame with a bright transient."""
    rng = np.random.default_rng(1)
    darks = [np.full((20, 24), 0.05, np.float32) + rng.normal(0, 0.002, (20, 24)) for _ in range(9)]
    darks[3][10, 12] = 0.9  # cosmic ray on one sub only

    _save(storage, "s", "dark", darks)
    masters = calibration.build_masters("s", (20, 24))

    assert masters.dark is not None
    assert masters.dark[10, 12] == pytest.approx(0.05, abs=0.01)  # transient rejected


def test_calibration_removes_the_flat_field_gradient(
    storage: StorageService, calibration: CalibrationService
) -> None:
    """Dividing by a normalised master flat cancels a vignetting gradient."""
    height, width = 32, 40
    y = np.linspace(0.6, 1.0, height, dtype=np.float32)[:, None]
    x = np.linspace(0.7, 1.0, width, dtype=np.float32)[None, :]
    vignette = y * x  # 1.0 at one corner, 0.42 at the other

    flats = [np.full((height, width), 0.5, np.float32) * vignette for _ in range(5)]
    light = np.full((height, width), 0.3, np.float32) * vignette

    _save(storage, "s", "flat", flats)
    masters = calibration.build_masters("s", (height, width))
    out = calibration.calibrate(light, masters)

    # the residual should be flat: std/mean far smaller than the raw vignette's
    assert float(np.std(out) / np.mean(out)) < 0.02
    assert float(np.std(light) / np.mean(light)) > 0.15


def test_cosmetic_correction_repairs_a_dead_flat_pixel(
    storage: StorageService, calibration: CalibrationService
) -> None:
    """A dust-blocked / dead pixel in the flat would explode after division;
    cosmetic correction replaces it with a neighbour median, and turning it off
    leaves the artefact in."""
    flats = [np.full((24, 24), 0.5, np.float32) for _ in range(6)]
    for flat in flats:
        flat[7, 15] = 0.005  # ~100x below the rest of the field

    light = np.full((24, 24), 0.2, np.float32)

    _save(storage, "s", "flat", flats)
    masters = calibration.build_masters("s", (24, 24))
    assert masters.bad_pixels is not None and masters.bad_pixels[7, 15]

    repaired = calibration.calibrate(light, masters, cosmetic=True)
    assert repaired[7, 15] == pytest.approx(0.2, abs=0.02)

    kept = calibration.calibrate(light, masters, cosmetic=False)
    assert kept[7, 15] > 1.0  # 0.2 / 0.01-ish normalised flat -> blown out


def test_dark_is_scaled_by_the_exposure_ratio(
    storage: StorageService, calibration: CalibrationService
) -> None:
    """With a bias master, the thermal part of the dark scales to the light's exposure."""
    bias = np.full((16, 16), 0.02, np.float32)
    dark = np.full((16, 16), 0.02 + 0.06, np.float32)  # bias + 0.06 thermal at 120 s

    _save(storage, "s", "bias", [bias] * 4)
    _save(storage, "s", "dark", [dark] * 4, exposure_s="120")
    masters = calibration.build_masters("s", (16, 16))

    light = np.full((16, 16), 0.5, np.float32)
    out = calibration.calibrate(light, masters, light_exposure_s=60.0)  # half the dark's exposure

    # subtracted: bias (0.02) + thermal scaled to 0.03  ->  0.5 - 0.05 = 0.45
    assert float(out.mean()) == pytest.approx(0.45, abs=1e-3)


def test_missing_calibration_frames_leave_the_light_untouched(
    storage: StorageService, calibration: CalibrationService
) -> None:
    masters = calibration.build_masters("s", (12, 12))
    assert masters.is_empty
    light = np.full((12, 12), 0.4, np.float32)
    np.testing.assert_array_equal(calibration.calibrate(light, masters), light)


def test_calibration_frames_that_do_not_match_the_lights_raise(
    storage: StorageService, calibration: CalibrationService
) -> None:
    _save(storage, "s", "dark", [np.zeros((10, 10), np.float32)] * 3)
    with pytest.raises(InvalidParameterError, match="must match"):
        calibration.build_masters("s", (20, 20))


def test_master_is_cached_and_rebuilt_when_more_subs_arrive(
    storage: StorageService, calibration: CalibrationService
) -> None:
    _save(storage, "s", "bias", [np.full((8, 8), 0.02, np.float32)] * 3)
    calibration.build_masters("s", (8, 8))
    assert storage.master_path("s", "bias").exists()

    _save(storage, "s", "bias", [np.full((8, 8), 0.10, np.float32)] * 3)  # append brighter subs
    rebuilt = calibration.build_masters("s", (8, 8))
    assert rebuilt.bias is not None
    assert float(rebuilt.bias.mean()) == pytest.approx(0.06, abs=0.01)  # median of 0.02 and 0.10


def test_cfa_bad_pixels_are_judged_per_bayer_phase(
    storage: StorageService, calibration: CalibrationService
) -> None:
    """A hot pixel on the dim R site is caught even though it sits below the G level."""
    mosaic = np.zeros((16, 16), np.float32)
    mosaic[0::2, 0::2] = 0.02  # R sites (GRBG -> R at (1,0)? here just two levels)
    mosaic[0::2, 1::2] = 0.02
    mosaic[1::2, 0::2] = 0.02
    mosaic[1::2, 1::2] = 0.20  # one bright phase
    darks = [mosaic.copy() for _ in range(6)]
    for dark in darks:
        dark[4, 4] = 0.12  # hot on a dim phase - would look normal globally

    _save(storage, "s", "dark", darks)
    masters = calibration.build_masters("s", (16, 16), is_cfa=True)

    assert masters.bad_pixels is not None
    assert masters.bad_pixels[4, 4]
    assert not masters.bad_pixels[5, 5]  # the legitimately bright phase is fine
