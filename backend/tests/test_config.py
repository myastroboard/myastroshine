"""Structural settings and derived paths."""

from __future__ import annotations

from pathlib import Path

#: A stand-in for the token the Supervisor injects.
SUPERVISOR_TOKEN = "supervisor-token"


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


def test_home_assistant_is_detected_from_the_supervisor_token() -> None:
    """The Supervisor injects SUPERVISOR_TOKEN into every app container; a plain
    Docker install has none."""
    from app.config import Settings

    assert Settings(supervisor_token="").on_home_assistant is False
    assert Settings(supervisor_token=SUPERVISOR_TOKEN).on_home_assistant is True


def test_supervisor_token_never_shows_in_the_settings_repr() -> None:
    from app.config import Settings

    assert SUPERVISOR_TOKEN not in repr(Settings(supervisor_token=SUPERVISOR_TOKEN))


def test_admin_reset_markers_add_the_app_config_folder_only_under_home_assistant() -> None:
    """Under Home Assistant the marker can also be dropped in the app's config
    folder, the one an HA admin reaches through Samba or the File editor."""
    from app.config import Settings

    root = Path("/srv/astro")

    assert Settings(data_dir=root, supervisor_token="").admin_reset_markers == [
        root / "reset-admin"
    ]
    assert Settings(data_dir=root, supervisor_token=SUPERVISOR_TOKEN).admin_reset_markers == [
        root / "reset-admin",
        Path("/config/reset-admin"),
    ]
