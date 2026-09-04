"""ProcessingParameters wire contract.

The frontend sends these fields in snake_case (its case-conversion layer relies
on this). Every field must round-trip; unknown fields must be rejected so a
mis-cased key like ``depthShiftIntensity`` fails loudly instead of being ignored.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models import ProcessingParameters

_WIRE = {
    "contrast": 1.5,
    "brightness": 0.1,
    "saturation": 1.2,
    "highlights": 0.0,
    "shadows": 0.2,
    "clarity": 0.8,
    "vibrance": 1.1,
    "denoise": 30,
    "sharpness": 1.2,
    "temperature": 5500,
    "tint": 5,
    "depth_shift_intensity": 40,
}


def test_all_wire_fields_round_trip() -> None:
    params = ProcessingParameters(**_WIRE)
    assert params.depth_shift_intensity == 40
    assert params.model_dump() == _WIRE


def test_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ProcessingParameters(depthShiftIntensity=40)  # type: ignore[call-arg]


def test_out_of_range_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ProcessingParameters(contrast=9.0)
