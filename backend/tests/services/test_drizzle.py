"""Drizzle: the pixel-drop math and the opt-in integration pass."""

from __future__ import annotations

import numpy as np
import pytest

from app.services.drizzle import drizzle_accumulate, drizzle_finalise
from app.services.integration import IntegrationService
from app.services.storage import StorageService
from app.utils.linear_ingest import LinearFrame

_IDENTITY = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])


def test_a_single_drop_lands_at_the_transformed_location() -> None:
    frame = np.zeros((8, 8, 3), dtype=np.float32)
    frame[4, 4] = [1.0, 2.0, 3.0]
    flux = np.zeros((16, 16, 3), dtype=np.float32)
    weight = np.zeros((16, 16), dtype=np.float32)

    drizzle_accumulate(frame, _IDENTITY, 2, 1.0, flux, weight)

    composite, _ = drizzle_finalise(flux, weight, typical_weight=1.0)
    lit = np.argwhere(flux[:, :, 0] > 0)
    # input pixel (4, 4) -> output (8, 8); the drop splats onto the nearest 2x2.
    assert lit.min(axis=0).tolist() == [7, 7] and lit.max(axis=0).tolist() == [8, 8]
    assert composite[8, 8] == pytest.approx([1.0, 2.0, 3.0], rel=1e-4)  # flux / weight = the value
    # every input pixel deposits coverage (only the 1px output border stays empty)
    assert weight[:-1, :-1].min() > 0


def test_finalise_divides_flux_by_weight() -> None:
    flux = np.full((4, 4, 3), 6.0, dtype=np.float32)
    weight = np.full((4, 4), 2.0, dtype=np.float32)
    weight[0, 0] = 0.0

    composite, coverage = drizzle_finalise(flux, weight, typical_weight=2.0)

    assert composite[1, 1] == pytest.approx([3.0, 3.0, 3.0])
    assert composite[0, 0].tolist() == [0.0, 0.0, 0.0]  # no coverage -> zero, not inf
    assert coverage[1, 1] == 1 and coverage[0, 0] == 0


# -- end to end -----------------------------------------------------------------

_PATTERN = "GRBG"


_STARS = [
    (30, 24), (95, 70), (60, 50), (24, 85), (110, 20), (45, 95),
    (130, 60), (75, 30), (18, 45), (140, 100), (55, 15), (100, 90),
]


def _cfa(height: int, width: int, dx: float, dy: float) -> np.ndarray:
    """A CFA sky with a dozen stars, sub-pixel shifted by (dx, dy)."""
    rng = np.random.default_rng(0)
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    frame = np.full((height, width), 0.02, dtype=np.float32)
    for cx, cy in _STARS:
        frame += 0.9 * np.exp(-(((xx - cx - dx) ** 2 + (yy - cy - dy) ** 2) / 2.5))
    frame += rng.normal(0, 0.003, frame.shape).astype(np.float32)
    return np.clip(frame, 0, 1)


def _save(storage: StorageService, index: int, data: np.ndarray) -> None:
    storage.save_linear_frame(
        "s", index, LinearFrame(data=data, is_cfa=True, bayer_pattern=_PATTERN)
    )


@pytest.fixture
def storage(tmp_path) -> StorageService:
    return StorageService(root=tmp_path)


def test_drizzle_2x_doubles_the_grid_and_stays_valid(storage: StorageService) -> None:
    height, width = 120, 160
    shifts = [(0.0, 0.0), (0.5, 0.0), (0.0, 0.5), (0.5, 0.5), (0.25, 0.75), (0.75, 0.25)]
    for i, (dx, dy) in enumerate(shifts):
        _save(storage, i, _cfa(height, width, dx, dy))

    result = IntegrationService(storage, workers=1).integrate(
        "s", list(range(len(shifts))),
        transform="similarity", combination="average", rejection="winsorized_sigma",
        weighting="noise", drizzle=2,
    )

    assert result.composite.shape == (height * 2, width * 2, 3)
    assert result.coverage.shape == (height * 2, width * 2)
    assert np.isfinite(result.composite).all()
    assert float(result.composite.min()) >= 0.0
    assert float(result.composite.max()) > 5 * float(np.median(result.composite))  # stars survive


def test_drizzle_pass_resumes_after_a_crash(
    storage: StorageService, monkeypatch: pytest.MonkeyPatch
) -> None:
    height, width = 110, 150
    for i, dx in enumerate([-0.5, -0.25, 0.0, 0.25, 0.5, 0.75]):
        _save(storage, i, _cfa(height, width, dx, dx))
    svc = IntegrationService(storage, workers=1)
    kwargs = {
        "transform": "similarity",
        "combination": "average",
        "rejection": "winsorized_sigma",
        "weighting": "noise",
        "drizzle": 2,
    }

    def boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(svc, "_drizzle", boom)
    with pytest.raises(RuntimeError):
        svc.integrate("s", list(range(6)), **kwargs)

    monkeypatch.undo()
    registers: list[int] = []
    monkeypatch.setattr(svc, "_register", lambda *a, **k: registers.append(1))
    result = svc.integrate("s", list(range(6)), **kwargs)

    assert not registers  # resumed from the checkpoint
    assert result.composite.shape == (height * 2, width * 2, 3)
