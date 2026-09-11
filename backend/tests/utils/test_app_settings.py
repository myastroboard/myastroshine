"""Product settings: the auto-generated secret and the JSON store."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

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


def test_secret_key_second_call_returns_the_cached_value_without_touching_disk() -> None:
    """Back-to-back calls (no reset in between) hit the in-memory cache."""
    app_settings._cache.secret_key = None
    first = load_or_generate_secret_key()
    second = load_or_generate_secret_key()  # cache hit, no lock/disk round trip
    assert second == first


def test_secret_key_double_checked_lock_returns_the_value_set_by_a_racing_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The outer check races another thread that fills the cache between the
    outer read and acquiring the lock - the inner check inside the lock
    catches that instead of generating (and writing) a second key."""

    class _RaceCache:
        settings = None

        def __init__(self) -> None:
            self._reads = 0

        @property
        def secret_key(self) -> str | None:
            self._reads += 1
            return None if self._reads == 1 else "raced-in-by-another-thread"

        @secret_key.setter
        def secret_key(self, _value: str) -> None:
            pass  # the real function's own assignment is a no-op here

    monkeypatch.setattr(app_settings, "_cache", _RaceCache())

    assert load_or_generate_secret_key() == "raced-in-by-another-thread"


def test_get_app_settings_double_checked_lock_returns_the_value_set_by_a_racing_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = AppSettings(max_image_size_mb=42)

    class _RaceCache:
        secret_key = None

        def __init__(self) -> None:
            self._reads = 0

        @property
        def settings(self) -> AppSettings | None:
            self._reads += 1
            return None if self._reads == 1 else sentinel

        @settings.setter
        def settings(self, _value: AppSettings | None) -> None:
            pass

    monkeypatch.setattr(app_settings, "_cache", _RaceCache())

    assert get_app_settings() is sentinel


def test_a_corrupt_settings_file_falls_back_to_defaults() -> None:
    path = get_settings().app_settings_file
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not valid json {", encoding="utf-8")

    reload_app_settings()

    assert get_app_settings().max_image_size_mb == AppSettings().max_image_size_mb


def test_defaults_when_no_file() -> None:
    """A missing app_settings.json yields the shipped defaults."""
    get_settings().app_settings_file.unlink(missing_ok=True)
    reload_app_settings()

    settings = get_app_settings()
    assert settings.max_image_size_mb == AppSettings().max_image_size_mb
    assert settings.stacking_max_frames == AppSettings().stacking_max_frames


def test_save_merges_persists_and_refreshes_cache() -> None:
    """save_app_settings writes the whole object and updates the in-memory copy."""
    save_app_settings({"max_image_size_mb": 250, "stacking_max_frames": 300})

    assert get_app_settings().max_image_size_mb == 250
    on_disk = json.loads(get_settings().app_settings_file.read_text(encoding="utf-8"))
    assert on_disk["max_image_size_mb"] == 250
    assert on_disk["stacking_max_frames"] == 300


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


def test_cors_origins_rejects_wildcard() -> None:
    """allow_credentials=True is always on (main.py) - a "*" origin is a real
    hole, not just a combination browsers already reject."""
    with pytest.raises(ValidationError, match="cors_origins"):
        AppSettings(cors_origins=["*"])


def test_cors_origins_still_allows_specific_hosts() -> None:
    settings = AppSettings(cors_origins=["http://localhost:3000", "https://app.example.com"])
    assert settings.cors_origins == ["http://localhost:3000", "https://app.example.com"]
