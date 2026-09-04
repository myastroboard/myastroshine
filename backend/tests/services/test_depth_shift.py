"""DepthShiftService orchestration and caching."""

from __future__ import annotations

import numpy as np
import pytest

from app.exceptions import ResourceNotFoundError, SessionNotFoundError
from app.services.depth_map import DepthMapService
from app.services.depth_shift import DepthShiftService
from app.services.session import SessionService
from app.services.storage import StorageService


@pytest.fixture
def depth_shift(db_session, tmp_path) -> DepthShiftService:
    storage = StorageService(root=tmp_path)
    return DepthShiftService(SessionService(db_session, storage), storage, DepthMapService())


def _session_with_image(service: DepthShiftService, image: np.ndarray) -> str:
    record = service.sessions.create_session(image_path="")
    service.storage.save_original(record.session_id, image)
    return record.session_id


def test_generate_caches_map_and_layers(
    depth_shift: DepthShiftService, sample_image: np.ndarray
) -> None:
    """generate() writes depth_map.png plus one PNG per requested layer."""
    session_id = _session_with_image(depth_shift, sample_image)

    response = depth_shift.generate(session_id, num_layers=6)

    assert response.num_layers == 6
    assert len(response.depth_layers) == 6
    assert depth_shift.storage.has_depth(session_id)
    assert depth_shift.storage.count_layers(session_id) == 6
    assert response.depth_layers[0].image_url.endswith("/layer_0")


def test_generate_replaces_previous_layers(
    depth_shift: DepthShiftService, sample_image: np.ndarray
) -> None:
    """Re-running with fewer layers removes the stale files."""
    session_id = _session_with_image(depth_shift, sample_image)
    depth_shift.generate(session_id, num_layers=8)
    depth_shift.generate(session_id, num_layers=3)

    assert depth_shift.storage.count_layers(session_id) == 3


def test_metadata_before_and_after(
    depth_shift: DepthShiftService, sample_image: np.ndarray
) -> None:
    """metadata() reports absence, then the stats once generated."""
    session_id = _session_with_image(depth_shift, sample_image)

    assert depth_shift.metadata(session_id).depth_map_generated is False

    depth_shift.generate(session_id, num_layers=5)
    meta = depth_shift.metadata(session_id)
    assert meta.depth_map_generated is True
    assert meta.statistics is not None
    assert len(meta.layer_urls) == 5


def test_layer_file_missing_raises(
    depth_shift: DepthShiftService, sample_image: np.ndarray
) -> None:
    session_id = _session_with_image(depth_shift, sample_image)
    with pytest.raises(ResourceNotFoundError):
        depth_shift.layer_file(session_id, 0)


def test_generate_unknown_session_raises(depth_shift: DepthShiftService) -> None:
    with pytest.raises(SessionNotFoundError):
        depth_shift.generate("11111111-1111-1111-1111-111111111111", num_layers=5)
