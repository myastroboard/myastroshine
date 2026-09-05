"""DepthMapService: gradient depth estimation and parallax layers."""

from __future__ import annotations

import numpy as np
import pytest

from app.models import FocusPoint
from app.services.depth_map import DepthMapService


@pytest.fixture
def service() -> DepthMapService:
    return DepthMapService()


@pytest.fixture
def edged_image() -> np.ndarray:
    """A flat frame with one bright square - a clear high-gradient region."""
    image = np.full((80, 120, 3), 30, dtype=np.uint8)
    image[30:50, 50:70] = 240
    return image


def test_estimate_depth_shape_and_range(service: DepthMapService, edged_image: np.ndarray) -> None:
    """The depth map is single-channel, same H/W, uint8 in 0-255."""
    depth = service.estimate_depth(edged_image)
    assert depth.shape == edged_image.shape[:2]
    assert depth.dtype == np.uint8
    assert 0 <= int(depth.min()) <= int(depth.max()) <= 255


def test_edges_read_as_near(service: DepthMapService, edged_image: np.ndarray) -> None:
    """Depth near the square's border is higher than in the flat corner."""
    depth = service.estimate_depth(edged_image)
    border = depth[28:32, 48:72].mean()
    flat_corner = depth[:10, :10].mean()
    assert border > flat_corner


def test_generate_parallax_layers_count_and_format(
    service: DepthMapService, edged_image: np.ndarray
) -> None:
    """generate_parallax_layers returns exactly num_layers BGRA layers."""
    depth = service.estimate_depth(edged_image)
    layers = service.generate_parallax_layers(edged_image, depth, num_layers=5)

    assert len(layers) == 5
    for layer in layers:
        assert layer.shape == (80, 120, 4)
        assert layer.dtype == np.uint8


def test_layers_partition_the_image(service: DepthMapService, edged_image: np.ndarray) -> None:
    """Every pixel lands in at least one layer's alpha mask."""
    depth = service.estimate_depth(edged_image)
    layers = service.generate_parallax_layers(edged_image, depth, num_layers=7)
    covered = np.zeros((80, 120), dtype=bool)
    for layer in layers:
        covered |= layer[:, :, 3] > 0
    assert covered.all()


def test_depth_statistics(service: DepthMapService, edged_image: np.ndarray) -> None:
    """Statistics are sane and bounded."""
    depth = service.estimate_depth(edged_image)
    stats = service.depth_statistics(depth)
    assert 0 <= stats.min_depth <= stats.mean_depth <= stats.max_depth <= 255
    assert 0.0 <= stats.bright_areas_percent <= 100.0


def test_no_focus_point_is_unchanged(service: DepthMapService, edged_image: np.ndarray) -> None:
    """Omitting focus_point (the default) matches passing it explicitly as None."""
    assert np.array_equal(
        service.estimate_depth(edged_image),
        service.estimate_depth(edged_image, None),
    )


def test_focus_point_pulls_depth_toward_the_chosen_corner(
    service: DepthMapService, edged_image: np.ndarray
) -> None:
    """A focus point reads as near even in an otherwise flat, far region."""
    near_corner = FocusPoint(x=0.05, y=0.05)  # top-left, far from the bright square
    depth = service.estimate_depth(edged_image, near_corner)

    top_left = depth[:10, :10].mean()
    bottom_right = depth[-10:, -10:].mean()
    assert top_left > bottom_right


def test_layer_depth_range() -> None:
    """Bands tile [0, 1] with no gaps."""
    assert DepthMapService.layer_depth_range(0, 5) == (0.0, 0.2)
    assert DepthMapService.layer_depth_range(4, 5) == (0.8, 1.0)
