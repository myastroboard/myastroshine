"""DeepSNR-backed denoise. The binary is mocked - see test_external_engine for the
shared runner / cache coverage."""

from __future__ import annotations

import numpy as np
import pytest

from app.services import external_engine
from app.services.external_denoise import ExternalDenoiseService, blend_denoise
from tests.support import engine_image, fake_engine_run


def test_blend_at_zero_is_the_original() -> None:
    image = engine_image(64, 64)
    assert np.array_equal(blend_denoise(image, np.zeros_like(image), 0), image)


def test_blend_at_full_strength_is_the_estimate() -> None:
    image = np.full((8, 8, 3), 200, np.uint8)
    estimate = np.full((8, 8, 3), 40, np.uint8)
    assert np.array_equal(blend_denoise(image, estimate, 100), estimate)


def test_blend_is_a_linear_mix_at_half_strength() -> None:
    image = np.full((4, 4, 3), 200, np.uint8)
    estimate = np.full((4, 4, 3), 100, np.uint8)
    assert np.array_equal(blend_denoise(image, estimate, 50), np.full((4, 4, 3), 150, np.uint8))


def test_run_model_invokes_deepsnr_by_name(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    def run(cmd: list[str], **_kwargs: object):
        seen.append(cmd)
        return fake_engine_run()(cmd)

    monkeypatch.setattr(external_engine.subprocess, "run", run)

    out = ExternalDenoiseService("/opt/deepsnr", stride=480).run_model(engine_image())

    assert seen[0][0] == "/opt/deepsnr"
    assert seen[0][seen[0].index("-s") + 1] == "480"
    assert "--linear" not in seen[0]  # data is display-referred by this point
    assert out.shape == (600, 800, 3)
