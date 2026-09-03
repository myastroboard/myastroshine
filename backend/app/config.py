"""Application settings loaded from environment variables / .env.

Access settings through :func:`get_settings` so the object is built once and
reused (and easily overridden in tests).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed view over the environment configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_env: str = "development"
    debug: bool = True
    log_level: str = "info"

    # Database
    database_url: str = "sqlite:///./data/db/myastroshine.db"

    # Storage
    storage_path: Path = Path("./data/images")
    max_image_size_mb: int = 100
    session_expiry_hours: int = 24

    # API
    api_title: str = "MyAstroShine"
    api_version: str = "0.1.0"
    api_port: int = 8002  # host uses 8000 for other projects
    api_cors_origins: str = "http://localhost:3000,http://myastroshine.local"

    # AstroDex integration
    astrodex_webhook_secret: str = "change-me"  # noqa: S105 - placeholder, must be set via env
    astrodex_callback_urls: str = ""
    astrodex_max_retries: int = 3
    astrodex_retry_delay_seconds: int = 5

    # Redis / Celery (optional, phase 2+)
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"

    # Processing
    max_workers: int = 4
    denoise_enable_ml: bool = False
    depth_detection_method: str = "gradient"
    preview_max_size: int = 512

    # Stacking (v1.1+)
    stacking_enabled: bool = True
    stacking_max_frames: int = 100
    stacking_detector: str = "orb"
    stacking_combination_default: str = "median"
    stacking_cosmic_ray_threshold: float = 3.0
    stacking_temp_dir: Path = Path("./data/stacks")

    @property
    def cors_origins(self) -> list[str]:
        """CORS origins as a list."""
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]

    @property
    def callback_url_allowlist(self) -> list[str]:
        """Trusted AstroDex callback URLs."""
        return [url.strip() for url in self.astrodex_callback_urls.split(",") if url.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance."""
    return Settings()
