"""PresetService: built-in seeding and user preset CRUD."""

from __future__ import annotations

import pytest

from app.exceptions import DuplicateResourceError, ForbiddenError, PayloadTooLargeError
from app.models import ProcessingParameters
from app.services.preset import PresetService


def test_ensure_defaults_is_idempotent(db_session) -> None:
    """Seeding twice still leaves exactly the five built-ins."""
    service = PresetService(db_session)
    service.ensure_defaults()
    service.ensure_defaults()

    built_in = [p for p in service.list_presets() if p.author == "system"]
    assert {p.name for p in built_in} == {"Nebula", "Galaxy", "Deep Field", "Lunar", "Cluster"}


def test_list_presets_orders_system_first(db_session) -> None:
    """User presets come after the built-ins."""
    service = PresetService(db_session)
    service.save_preset("My M31", ProcessingParameters(contrast=1.3))

    authors = [p.author for p in service.list_presets()]
    assert authors[:5] == ["system"] * 5
    assert authors[-1] == "user"


def test_save_preset_rejects_duplicate_name(db_session) -> None:
    """A second preset with the same name is refused."""
    service = PresetService(db_session)
    service.save_preset("Andromeda", ProcessingParameters())
    with pytest.raises(DuplicateResourceError):
        service.save_preset("Andromeda", ProcessingParameters())


def test_save_preset_enforces_limit(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    """Once the user preset cap is hit, saving raises PayloadTooLargeError."""
    monkeypatch.setattr("app.services.preset.MAX_USER_PRESETS", 2)
    service = PresetService(db_session)
    service.save_preset("a", ProcessingParameters())
    service.save_preset("b", ProcessingParameters())
    with pytest.raises(PayloadTooLargeError):
        service.save_preset("c", ProcessingParameters())


def test_delete_user_preset(db_session) -> None:
    """A user preset can be deleted; it disappears from the list."""
    service = PresetService(db_session)
    record = service.save_preset("Temp", ProcessingParameters())
    service.delete_preset(record.preset_id)
    assert record.preset_id not in {p.preset_id for p in service.list_presets()}


def test_cannot_delete_builtin(db_session) -> None:
    """Built-in presets are protected."""
    service = PresetService(db_session)
    service.ensure_defaults()
    with pytest.raises(ForbiddenError):
        service.delete_preset("system_nebula")


def test_get_preset_parameters_are_valid(db_session) -> None:
    """A built-in preset round-trips into ProcessingParameters."""
    service = PresetService(db_session)
    preset = service.get_preset("system_lunar")
    params = ProcessingParameters(**preset.parameters)
    assert params.sharpness == 1.5
