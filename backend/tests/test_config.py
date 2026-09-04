"""Structural settings and derived paths."""

from __future__ import annotations

from pathlib import Path


def test_paths_derive_from_data_dir() -> None:
    """Every persistence path hangs off a single DATA_DIR root."""
    from app.config import Settings

    root = Path("/srv/astro")
    settings = Settings(data_dir=root)

    assert settings.images_dir == root / "images"
    assert settings.stacks_dir == root / "stacks"
    assert settings.cache_dir == root / "cache"
    assert settings.secret_key_file == root / "secret_key.txt"
    assert settings.app_settings_file == root / "app_settings.json"


def test_database_url_defaults_to_sqlite_under_data_dir() -> None:
    """With no override the DB is a SQLite file inside DATA_DIR/db."""
    from app.config import Settings

    root = Path("/srv/astro")
    settings = Settings(data_dir=root, database_url="")

    assert settings.resolved_database_url == f"sqlite:///{root / 'db' / 'myastroshine.db'}"


def test_database_url_override_wins() -> None:
    """An explicit DATABASE_URL (e.g. Postgres) is used verbatim."""
    from app.config import Settings

    settings = Settings(database_url="postgresql://db/astro")

    assert settings.resolved_database_url == "postgresql://db/astro"
