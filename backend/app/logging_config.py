"""Centralized logging for the backend.

Always obtain a logger through :func:`get_logger`; never import ``logging`` or
configure handlers directly elsewhere in the codebase.
"""

from __future__ import annotations

import logging
import sys
from typing import cast

import structlog

from app.config import get_settings


def configure_logging() -> None:
    """Configure structlog + stdlib logging once, at process start."""
    if structlog.is_configured():
        return

    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    renderer = (
        structlog.dev.ConsoleRenderer()
        if settings.app_env == "development"
        else structlog.processors.JSONRenderer()
    )

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a bound logger for ``name`` (typically ``__name__``)."""
    configure_logging()
    return cast("structlog.stdlib.BoundLogger", structlog.get_logger(name))
