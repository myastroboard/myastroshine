"""Product settings: the auto-generated secret and the JSON store."""

from __future__ import annotations

import json

from app.config import get_settings
from app.utils import app_settings
from app.utils.app_settings import (
    AppSettings,
    get_app_settings,
    load_or_generate_secret_key,
    reload_app_settings,
    save_app_settings,
)


def test_secret_key_generated_once_and_persisted() -> None:
    """First call writes DATA_DIR/secret_key.txt; later calls return the same value."""
    app_settings._cache.secret_key = None
    key = load_or_generate_secret_key()

    assert len(key) == 64  # token_hex(32)
    key_file = get_settings().secret_key_file
    assert key_file.read_text(encoding="utf-8").strip() == key

    app_settings._cache.secret_key = None
    assert load_or_generate_secret_key() == key


def test_defaults_when_no_file() -> None:
    """A missing app_settings.json yields the shipped defaults."""
    get_settings().app_settings_file.unlink(missing_ok=True)
    reload_app_settings()

    settings = get_app_settings()
    assert settings.max_image_size_mb == AppSettings().max_image_size_mb
    assert settings.stacking_detector == "orb"


def test_save_merges_persists_and_refreshes_cache() -> None:
    """save_app_settings writes the whole object and updates the in-memory copy."""
    save_app_settings({"max_image_size_mb": 250, "stacking_detector": "sift"})

    assert get_app_settings().max_image_size_mb == 250
    on_disk = json.loads(get_settings().app_settings_file.read_text(encoding="utf-8"))
    assert on_disk["max_image_size_mb"] == 250
    assert on_disk["stacking_detector"] == "sift"


def test_unknown_keys_are_ignored() -> None:
    """A stray key in the payload does not blow up or get persisted."""
    save_app_settings({"not_a_real_setting": True, "preview_max_size": 1024})

    assert get_app_settings().preview_max_size == 1024
    assert not hasattr(get_app_settings(), "not_a_real_setting")


def test_reload_picks_up_an_external_write() -> None:
    """Editing the file directly and calling reload takes effect."""
    path = get_settings().app_settings_file
    path.write_text(json.dumps({"session_expiry_hours": 72}), encoding="utf-8")

    reload_app_settings()

    assert get_app_settings().session_expiry_hours == 72
