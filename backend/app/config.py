"""Structural configuration - the deployment shape only.

These values describe *where* the app runs: the persistence root, the container
topology, the run mode. Everything a user might want to tune at runtime lives in
``app_settings.json`` and is reached through
:func:`app.utils.app_settings.get_app_settings` - never read ``os.environ`` for a
product setting.

``docker compose up`` must work with none of these set: the defaults target the
compose service names and a ``/data`` volume.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.constants import ADMIN_RESET_MARKER, HA_APP_CONFIG_DIR, LOG_FILE_NAME


class Settings(BaseSettings):
    """Typed view over the environment configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Deployment shape
    app_env: str = "development"  # development | production | test
    log_level: str = "info"  # bootstrap level; the runtime level lives in app_settings

    # The single persistence root. Everything the app writes is derived from it.
    data_dir: Path = Path("./data")

    # Optional database override. Empty -> a SQLite file under ``data_dir``.
    database_url: str = ""

    # Gates /api/admin/* and /api/tokens. Single-user local deployments leave it on.
    admin_enabled: bool = True

    # Injected by the Home Assistant Supervisor into every app container: its
    # presence is how the app knows it runs as an HA app (app/utils/ingress.py).
    # Never logged.
    supervisor_token: str = Field(default="", repr=False)
    # The Supervisor's ingress proxy. Only the e2e fake Supervisor overrides it.
    ingress_proxy_ip: str = "172.30.32.2"

    @property
    def is_test(self) -> bool:
        return self.app_env == "test"

    @property
    def on_home_assistant(self) -> bool:
        return bool(self.supervisor_token)

    @property
    def admin_reset_markers(self) -> list[Path]:
        """Files whose presence at startup clears the admin password.

        ``reset-admin`` in the data directory, and under Home Assistant also in
        the app's config folder (``/addon_configs/<slug>/`` on the host, reached
        through Samba or the File editor - tools only HA admins have).
        """
        markers = [self.data_dir / ADMIN_RESET_MARKER]
        if self.on_home_assistant:
            markers.append(HA_APP_CONFIG_DIR / ADMIN_RESET_MARKER)
        return markers

    @property
    def db_dir(self) -> Path:
        return self.data_dir / "db"

    @property
    def resolved_database_url(self) -> str:
        """The database URL, deriving a SQLite path under ``data_dir`` if unset."""
        return self.database_url or f"sqlite:///{self.db_dir / 'myastroshine.db'}"

    @property
    def images_dir(self) -> Path:
        return self.data_dir / "images"

    @property
    def stacks_dir(self) -> Path:
        return self.data_dir / "stacks"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def log_file(self) -> Path:
        return self.data_dir / LOG_FILE_NAME

    @property
    def secret_key_file(self) -> Path:
        return self.data_dir / "secret_key.txt"

    @property
    def app_settings_file(self) -> Path:
        return self.data_dir / "app_settings.json"

    def ensure_data_dirs(self) -> None:
        """Create the persistence tree. Called once at startup."""
        for path in (self.db_dir, self.images_dir, self.stacks_dir, self.cache_dir):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance."""
    return Settings()
