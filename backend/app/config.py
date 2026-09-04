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

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.constants import LOG_FILE_NAME, WORKER_LOG_FILE_NAME


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
    # Set this (to a Postgres URL) before scaling the worker out.
    database_url: str = ""

    # Container topology. Defaults match the docker-compose service names.
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"

    # "sync"  - run the pipeline inside the request (default; no worker needed)
    # "queue" - enqueue a Celery task; progress streams over the WebSocket
    # Tied to whether the compose worker/redis services run, so it stays here.
    processing_mode: str = "sync"

    # Gates /api/admin/* and /api/tokens. Single-user local deployments leave it on.
    admin_enabled: bool = True

    @property
    def is_test(self) -> bool:
        return self.app_env == "test"

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
    def worker_log_file(self) -> Path:
        return self.data_dir / WORKER_LOG_FILE_NAME

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
