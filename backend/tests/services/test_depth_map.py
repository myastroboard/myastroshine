"""DepthMapService tests. Filled in during Sprint 4."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="DepthMapService not implemented yet (Sprint 4)")


def test_estimate_depth_returns_same_shape_single_channel() -> None:
    """The depth map matches the input height/width and is single channel."""


def test_generate_parallax_layers_count_matches_request() -> None:
    """generate_parallax_layers returns exactly num_layers BGRA layers."""
