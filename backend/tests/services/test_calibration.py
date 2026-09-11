"""CalibrationService: master frames, calibration arithmetic, bad-pixel repair."""

from __future__ import annotations

import numpy as np
import pytest

from app.exceptions import InvalidParameterError
from app.services.calibration import (
    CalibrationMasters,
    CalibrationService,
    _combine_block,
    _flat_field,
)
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


def test_master_and_bad_pixel_map_load_from_cache_on_a_second_call(
    storage: StorageService, calibration: CalibrationService
) -> None:
    """Building masters twice with the same source frames hits the on-disk
    cache instead of recombining (both the master itself and its bad-pixel
    map are keyed on the unchanged source frame count)."""
    darks = [np.full((10, 10), 0.05, np.float32) for _ in range(4)]
    darks[0][3, 3] = 0.9  # a defect so a bad-pixel map actually gets built

    _save(storage, "s", "dark", darks)
    first = calibration.build_masters("s", (10, 10))
    second = calibration.build_masters("s", (10, 10))  # no new frames: cache hit both times

    assert first.dark is not None
    assert second.dark is not None
    np.testing.assert_array_equal(first.dark, second.dark)
    np.testing.assert_array_equal(first.bad_pixels, second.bad_pixels)


def test_calibrate_rejects_a_light_frame_shaped_differently_than_a_master(
    storage: StorageService, calibration: CalibrationService
) -> None:
    _save(storage, "s", "bias", [np.full((10, 10), 0.02, np.float32)] * 3)
    masters = calibration.build_masters("s", (10, 10))

    light = np.full((20, 20), 0.4, np.float32)
    with pytest.raises(InvalidParameterError, match="bias master"):
        calibration.calibrate(light, masters)


def test_dark_is_not_rescaled_when_the_exposure_ratio_is_already_one(
    storage: StorageService, calibration: CalibrationService
) -> None:
    """light_exposure_s equal to the dark's own exposure - no rescaling math,
    the raw master dark is subtracted as-is."""
    bias = np.full((16, 16), 0.02, np.float32)
    dark = np.full((16, 16), 0.02 + 0.06, np.float32)

    _save(storage, "s", "bias", [bias] * 4)
    _save(storage, "s", "dark", [dark] * 4, exposure_s="120")
    masters = calibration.build_masters("s", (16, 16))

    light = np.full((16, 16), 0.5, np.float32)
    out = calibration.calibrate(light, masters, light_exposure_s=120.0)  # same as dark's exposure

    assert float(out.mean()) == pytest.approx(0.5 - 0.08, abs=1e-3)  # 0.5 - (bias+thermal)


def test_flat_field_subtracts_its_own_dark_flat_before_normalising() -> None:
    flat = np.full((8, 8), 0.5, np.float32)
    dark_flat = np.full((8, 8), 0.1, np.float32)
    masters = CalibrationMasters(flat=flat, dark_flat=dark_flat)

    field = _flat_field(masters)

    # (0.5 - 0.1) normalised to a mean of 1 is uniformly 1.0 everywhere.
    assert float(field.mean()) == pytest.approx(1.0, abs=1e-4)


def test_flat_field_skips_normalisation_when_the_mean_is_near_zero() -> None:
    """A degenerate flat whose mean is ~0 is left un-normalised (dividing by
    ~0 would blow it up) rather than raising - callers see the raw (clamped)
    field instead of a division artefact."""
    flat = np.array([[1e-10, -1e-10], [1e-10, -1e-10]], dtype=np.float32)
    masters = CalibrationMasters(flat=flat)

    field = _flat_field(masters)

    # normalisation skipped -> only the floor clamp applied, not a /mean rescale
    np.testing.assert_array_equal(field, np.maximum(flat, 0.05))


def test_combine_block_runs_the_winsorized_sigma_reduction_path() -> None:
    """_master always passes method="median" (the module constant) - this is
    the only way the non-median, iterative sigma-clip branch gets exercised."""
    rng = np.random.default_rng(3)
    block = np.full((5, 10, 10), 0.1, np.float32) + rng.normal(0, 0.001, (5, 10, 10)).astype(
        np.float32
    )

    combined = _combine_block(block, "winsorized_sigma")

    assert combined.shape == (10, 10)
    assert combined.dtype == np.float32
    assert float(combined.mean()) == pytest.approx(0.1, abs=0.01)


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
