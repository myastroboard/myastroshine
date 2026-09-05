"""FastAPI application entry point for MyAstroShine.

Wires configuration, logging, database, the API routers, and the shared error
envelope (see docs/API.md) together.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

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
    star_mask,
    tokens,
    upload,
    websockets,
)
from app.services.preset import PresetService
from app.types import JsonDict
from app.utils.app_settings import get_app_settings, load_or_generate_secret_key

logger = get_logger(__name__)

# The built React SPA, baked into the image by the frontend-builder Dockerfile
# stage (COPY --from=frontend-builder .../dist ./static). Absent in local
# `uvicorn --reload` dev (the Vite dev server serves the frontend instead) and
# in tests - the mount below is skipped when this doesn't exist.
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


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

    # gzip + the security headers a reverse proxy would usually add - this app
    # is served directly (no nginx in front of it).
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    @app.middleware("http")
    async def _security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer-when-downgrade"
        return response

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
        star_mask.router,
        admin.router,
    ):
        app.include_router(router, prefix="/api")

    app.include_router(websockets.router)

    # The built frontend, if this image was built with the frontend-builder
    # stage (see Dockerfile). Mounted *last*: Starlette tries routes in
    # registration order, so every /api and /ws route above still takes
    # priority over this catch-all. The frontend uses hash-based routing
    # (#/settings), so a plain static mount is enough - no SPA-fallback
    # rewriting for arbitrary paths is needed.
    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="frontend")

    return app


app = create_app()
