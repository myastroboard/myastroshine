"""Shared pytest fixtures.

Every test runs against an isolated SQLite database and storage directory so the
suite never touches real data. Routes get their DB session through a
``dependency_overrides`` binding rather than the module-level engine.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Point settings at a throwaway DB + storage path, rebuilt per test."""
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path / "images"))
    monkeypatch.setenv(
        "ASTRODEX_CALLBACK_URLS", "http://astrodex.test/api/webhooks/enhanced-images"
    )

    from app.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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

    import app.main as main_module
    from app.db.database import get_db

    factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False, future=True)

    def _override_get_db() -> Iterator[object]:
        session = factory()
        try:
            yield session
        finally:
            session.close()

    main_module.app.dependency_overrides[get_db] = _override_get_db
    test_client = TestClient(main_module.app)
    try:
        yield test_client
    finally:
        test_client.close()
        main_module.app.dependency_overrides.clear()


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
