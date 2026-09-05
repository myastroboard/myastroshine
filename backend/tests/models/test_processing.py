"""ProcessingParameters wire contract.

The frontend sends these fields in snake_case (its case-conversion layer relies
on this). Every field must round-trip; unknown fields must be rejected so a
mis-cased key like ``depthShiftIntensity`` fails loudly instead of being ignored.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models import GeometryParameters, ProcessingParameters

_WIRE = {
    "geometry": {
        "straighten": -3.5,
        "rotate_quarters": 1,
        "flip_horizontal": True,
        "flip_vertical": False,
        "crop_x": 0.1,
        "crop_y": 0.05,
        "crop_w": 0.8,
        "crop_h": 0.9,
    },
    "contrast": 1.5,
    "brightness": 0.1,
    "saturation": 1.2,
    "highlights": 0.0,
    "shadows": 0.2,
    "clarity": 0.8,
    "vibrance": 1.1,
    "denoise": 30,
    "star_reduction": 20,
    "star_sensitivity": 65,
    "star_max_size": 40,
    "sharpness": 1.2,
    "temperature": 5500,
    "tint": 5,
    "depth_shift_intensity": 40,
    "curve_points": [{"x": 0, "y": 0}, {"x": 128, "y": 160}, {"x": 255, "y": 255}],
}


def test_all_wire_fields_round_trip() -> None:
    params = ProcessingParameters(**_WIRE)
    assert params.depth_shift_intensity == 40
    assert params.geometry.rotate_quarters == 1
    assert params.curve_points[1].y == 160
    assert params.model_dump() == _WIRE


def test_curve_points_defaults_to_empty() -> None:
    """Omitting curve_points means "no curve" (identity), not a validation error."""
    assert ProcessingParameters().curve_points == []


def test_curve_points_rejects_a_single_point() -> None:
    with pytest.raises(ValidationError):
        ProcessingParameters(curve_points=[{"x": 0, "y": 0}])


def test_curve_points_must_start_at_zero() -> None:
    with pytest.raises(ValidationError):
        ProcessingParameters(curve_points=[{"x": 10, "y": 0}, {"x": 255, "y": 255}])


def test_curve_points_must_end_at_255() -> None:
    with pytest.raises(ValidationError):
        ProcessingParameters(curve_points=[{"x": 0, "y": 0}, {"x": 250, "y": 255}])


def test_curve_points_must_be_strictly_increasing() -> None:
    with pytest.raises(ValidationError):
        ProcessingParameters(
            curve_points=[
                {"x": 0, "y": 0},
                {"x": 128, "y": 100},
                {"x": 128, "y": 200},
                {"x": 255, "y": 255},
            ]
        )


def test_curve_point_level_out_of_range_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ProcessingParameters(curve_points=[{"x": 0, "y": 0}, {"x": 255, "y": 300}])


def test_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ProcessingParameters(depthShiftIntensity=40)  # type: ignore[call-arg]


def test_unknown_geometry_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        GeometryParameters(rotateQuarters=1)  # type: ignore[call-arg]


def test_out_of_range_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ProcessingParameters(contrast=9.0)


def test_crop_past_edge_is_rejected() -> None:
    with pytest.raises(ValidationError):
        GeometryParameters(crop_x=0.5, crop_w=0.8)
