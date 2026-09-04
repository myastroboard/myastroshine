"""Shared pytest fixtures.

Every test runs against an isolated SQLite database and storage directory so the
suite never touches real data. Routes get their DB session through a
``dependency_overrides`` binding rather than the module-level engine.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest

# Before any `app.*` import: keep import-time logging setup in test mode (no file
# handler writing into ./data). The per-test fixture re-points DATA_DIR.
os.environ.setdefault("APP_ENV", "test")


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Point every settings-derived path at a throwaway ``DATA_DIR``, per test."""
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    from app import logging_config
    from app.config import get_settings
    from app.utils import app_settings

    get_settings.cache_clear()
    app_settings._cache.settings = None
    app_settings._cache.secret_key = None
    logging_config.configure_logging(force=True)
    # The AstroDex tests expect this callback host allow-listed and no retry backoff.
    app_settings.save_app_settings(
        {
            "astrodex_callback_urls": ["http://astrodex.test/api/webhooks/enhanced-images"],
            "astrodex_retry_delay_seconds": 0,
        }
    )
    yield
    get_settings.cache_clear()
    app_settings._cache.settings = None
    app_settings._cache.secret_key = None
    logging_config.configure_logging(force=True)


@pytest.fixture
def db_engine(tmp_path: Path):
    """A fresh SQLite engine with the schema created."""
    from sqlalchemy import create_engine

    from app.db.models import Base

    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine) -> Iterator[object]:
    """A SQLAlchemy session bound to the test engine."""
    from sqlalchemy.orm import sessionmaker

    factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False, future=True)
    session = factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_engine) -> Iterator[object]:
    """A FastAPI TestClient wired to the test engine.

    The lifespan is not started (no ``with``): the schema is created by the
    ``db_engine`` fixture and the DB session comes from a dependency override,
    so the module-level engine is never touched.
    """
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    import app.db.database as database_module
    import app.main as main_module
    from app.db.database import get_db

    factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False, future=True)

    def _override_get_db() -> Iterator[object]:
        session = factory()
        try:
            yield session
        finally:
            session.close()

    # Background jobs / Celery tasks open their own session via
    # database.SessionLocal(); point that at the test engine too.
    original_session_local = database_module.SessionLocal
    database_module.SessionLocal = factory
    main_module.app.dependency_overrides[get_db] = _override_get_db
    test_client = TestClient(main_module.app)
    try:
        yield test_client
    finally:
        test_client.close()
        main_module.app.dependency_overrides.clear()
        database_module.SessionLocal = original_session_local


@pytest.fixture
def sample_image() -> np.ndarray:
    """A small deterministic BGR image with a gradient and colour blocks."""
    rng = np.random.default_rng(42)
    image = np.zeros((64, 96, 3), dtype=np.uint8)
    image[:, :, 0] = np.linspace(0, 255, 96, dtype=np.uint8)  # blue ramp
    image[:32, :, 2] = 200  # red block, top half
    image[32:, :, 1] = 150  # green block, bottom half
    noise = rng.integers(-10, 10, image.shape, dtype=np.int16)
    return np.clip(image.astype(np.int16) + noise, 0, 255).astype(np.uint8)


@pytest.fixture
def sample_jpeg(sample_image: np.ndarray) -> bytes:
    """The sample image encoded as JPEG bytes."""
    import cv2

    ok, buffer = cv2.imencode(".jpg", sample_image)
    assert ok
    return buffer.tobytes()


@pytest.fixture
def star_field() -> np.ndarray:
    """A dark frame with ~80 stars of varied size/brightness plus faint
    background texture - enough distinctive structure for ORB and SIFT."""
    import cv2

    rng = np.random.default_rng(7)
    image = rng.integers(8, 18, (120, 160, 3), dtype=np.uint8)
    for _ in range(80):
        y, x = int(rng.integers(8, 112)), int(rng.integers(8, 152))
        radius = int(rng.integers(1, 4))
        brightness = int(rng.integers(120, 255))
        cv2.circle(image, (x, y), radius, (brightness, brightness, brightness), -1)
    return cv2.GaussianBlur(image, (3, 3), 0)


@pytest.fixture
def webhook_token(db_session) -> tuple[object, str]:
    """A live webhook token; returns ``(record, raw_token)``."""
    from app.services.token import TokenService

    return TokenService(db_session).create_token("test-integration")


@pytest.fixture
def auth_header(webhook_token) -> dict[str, str]:
    """An ``Authorization: Bearer`` header for the test token."""
    return {"Authorization": f"Bearer {webhook_token[1]}"}
