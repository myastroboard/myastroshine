"""FastAPI application entry point for MyAstroShine.

Wires configuration, logging, database, the API routers, and the shared error
envelope (see docs/API.md) together.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.config import get_settings
from app.constants import API_TITLE
from app.db import database
from app.db.database import init_db
from app.exceptions import AppError, InvalidParameterError
from app.logging_config import apply_runtime_log_levels, configure_logging, get_logger
from app.routes import (
    admin,
    astrodex,
    depth_shift,
    download,
    health,
    presets,
    processing,
    stack,
    tokens,
    upload,
    websockets,
)
from app.services.preset import PresetService
from app.types import JsonDict
from app.utils.app_settings import get_app_settings, load_or_generate_secret_key

logger = get_logger(__name__)


def _error_body(code: str, message: str, details: JsonDict, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": message,
            "error_code": code,
            "details": details,
            "request_id": f"req_{uuid.uuid4().hex[:12]}",
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup and shutdown hooks."""
    configure_logging()
    settings = get_settings()
    settings.ensure_data_dirs()
    load_or_generate_secret_key()
    apply_runtime_log_levels()
    init_db()
    with database.SessionLocal() as db:
        PresetService(db).ensure_defaults()

    logger.info("startup complete", env=settings.app_env, version=__version__)
    yield
    logger.info("shutdown")


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(title=API_TITLE, version=__version__, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_app_settings().cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(AppError)
    async def _handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        return _error_body(exc.error_code, exc.message, exc.details, exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
        err = InvalidParameterError("Invalid request parameters")
        details = {"errors": jsonable_encoder(exc.errors())}
        return _error_body(err.error_code, err.message, details, err.status_code)

    for router in (
        health.router,
        upload.router,
        processing.router,
        depth_shift.router,
        download.router,
        astrodex.router,
        presets.router,
        tokens.router,
        stack.router,
        admin.router,
    ):
        app.include_router(router, prefix="/api")

    # WebSocket routes are mounted at the root to match the /ws/ nginx proxy.
    app.include_router(websockets.router)

    return app


app = create_app()
