"""StarNet2-backed starless split. The binary is mocked - see test_external_engine
for the shared runner / cache coverage."""

from __future__ import annotations

import numpy as np
import pytest

from app.services import external_engine
from app.services.external_starless import ExternalStarlessService, blend_starless
from tests.support import engine_image, fake_engine_run


def test_blend_at_zero_is_the_original() -> None:
    image = engine_image(64, 64)
    starless, stars = blend_starless(image, np.zeros_like(image), 0)

    assert np.array_equal(starless, image)
    assert not stars.any()


def test_blend_at_full_strength_is_the_estimate_plus_star_flux() -> None:
    image = np.full((8, 8, 3), 200, np.uint8)
    estimate = np.full((8, 8, 3), 50, np.uint8)

    starless, stars = blend_starless(image, estimate, 100)

    assert np.array_equal(starless, estimate)
    assert np.array_equal(stars, np.full((8, 8, 3), 150, np.uint8))


def test_run_model_invokes_starnet2_by_name(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    def run(cmd: list[str], **_kwargs: object):
        seen.append(cmd)
        return fake_engine_run()(cmd)

    monkeypatch.setattr(external_engine.subprocess, "run", run)

    out = ExternalStarlessService("/opt/starnet2", stride=32).run_model(engine_image())

    assert seen[0][0] == "/opt/starnet2"
    assert seen[0][seen[0].index("-s") + 1] == "32"
    assert out.shape == (600, 800, 3)


def test_split_matches_the_classical_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(external_engine.subprocess, "run", fake_engine_run())

    starless, stars = ExternalStarlessService("/opt/starnet2").split(engine_image(), 50, 30, 100)

    assert starless.shape == stars.shape == (600, 800, 3)
