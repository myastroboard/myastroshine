"""Centralized logging for the backend.

One entry point (:func:`get_logger`); never import ``logging`` or configure
handlers directly elsewhere. structlog renders through the stdlib so we get a
rotating file handler in the data volume alongside the console.

Two sinks, two independently controlled levels (PASSATION section 4):

- **console** -> ``stdout`` (``docker logs``); level ``console_log_level``
  (default ``warning``), ``ConsoleRenderer`` in development else JSON.
- **file** -> ``DATA_DIR/myastroshine.log`` (or ``worker.log`` for the Celery
  worker), rotating 10 MB x 5; level ``log_level`` (default ``info``); a plain
  line with the timestamp in the ``TZ`` zone and the UTC offset always shown.

The levels live in ``app_settings.json`` and change at runtime via
:func:`apply_runtime_log_levels` (called at startup and by the admin API).
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import structlog
from structlog.types import EventDict, Processor

from app.config import get_settings
from app.constants import LOG_BACKUP_COUNT, LOG_MAX_BYTES


class _LoggingState:
    configured: bool = False
    console: logging.Handler | None = None
    file: logging.Handler | None = None


_state = _LoggingState()


def _level_no(name: str) -> int:
    return getattr(logging, name.upper(), logging.INFO)


def _add_timestamp(_logger: Any, _method: str, event_dict: EventDict) -> EventDict:
    """Timezone-aware ISO-8601 in the local (``TZ``) zone - the offset is kept."""
    event_dict["timestamp"] = datetime.now(UTC).astimezone().isoformat()
    return event_dict


# Runs for every record, structlog-native or stdlib ("foreign").
_FOREIGN_PRE_CHAIN: list[Processor] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    _add_timestamp,
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
]

# Extra step only meaningful for structlog call sites (foreign records would
# report this module's frame).
_CALLSITE = structlog.processors.CallsiteParameterAdder(
    {
        structlog.processors.CallsiteParameter.FUNC_NAME,
        structlog.processors.CallsiteParameter.LINENO,
    }
)

# Noisy third-party loggers pinned to WARNING regardless of our file level.
_QUIET_LOGGERS = ("httpx", "httpcore", "python_multipart", "PIL", "asyncio")


def _render_file(_logger: Any, _method: str, event_dict: EventDict) -> str:
    """``2026-09-04 21:15:03,142 +0000 - app.x - INFO - [func:12] - message k=v``."""
    raw = str(event_dict.pop("timestamp", ""))
    try:
        dt = datetime.fromisoformat(raw)
        stamp = (
            dt.strftime("%Y-%m-%d %H:%M:%S,") + f"{dt.microsecond // 1000:03d}" + dt.strftime(" %z")
        )
    except ValueError:
        stamp = raw
    level = str(event_dict.pop("level", "")).upper()
    name = event_dict.pop("logger", None) or event_dict.pop("logger_name", None) or "app"
    func = event_dict.pop("func_name", None)
    lineno = event_dict.pop("lineno", None)
    event = event_dict.pop("event", "")
    location = f" [{func}:{lineno}]" if func is not None else ""
    extras = " ".join(f"{k}={v!r}" for k, v in event_dict.items() if not k.startswith("_"))
    head = f"{stamp} - {name} - {level}{location} - {event}"
    return f"{head} {extras}" if extras else head


def _formatter(renderer: Processor) -> structlog.stdlib.ProcessorFormatter:
    return structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=_FOREIGN_PRE_CHAIN,
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
    )


def _build_console_handler() -> logging.Handler:
    settings = get_settings()
    renderer: Processor = (
        structlog.dev.ConsoleRenderer(colors=False)
        if settings.app_env == "development"
        else structlog.processors.JSONRenderer()
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_formatter(renderer))
    handler.setLevel(_level_no(settings.log_level))
    return handler


def _build_file_handler(path: Path) -> logging.Handler:
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT, encoding="utf-8"
    )
    handler.setFormatter(_formatter(_render_file))
    handler.setLevel(_level_no(get_settings().log_level))
    return handler


def configure_logging(*, role: str = "api", force: bool = False) -> None:
    """Wire structlog + stdlib handlers once, at process start.

    ``role="worker"`` sends the file sink to ``worker.log``. No file handler is
    attached under ``APP_ENV=test``.
    """
    if _state.configured and not force:
        return

    settings = get_settings()

    structlog.configure(
        processors=[
            *_FOREIGN_PRE_CHAIN,
            _CALLSITE,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)
        handler.close()

    console = _build_console_handler()
    root.addHandler(console)
    _state.console = console

    file_handler: logging.Handler | None = None
    if not settings.is_test:
        target = settings.worker_log_file if role == "worker" else settings.log_file
        file_handler = _build_file_handler(target)
        root.addHandler(file_handler)
    _state.file = file_handler

    root.setLevel(logging.DEBUG)  # the handlers do the filtering
    for name in _QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    _state.configured = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a bound logger for ``name`` (typically ``__name__``)."""
    configure_logging()
    return cast("structlog.stdlib.BoundLogger", structlog.get_logger(name))


def apply_runtime_log_levels() -> None:
    """Push the levels from ``app_settings.json`` onto the live handlers."""
    from app.utils.app_settings import get_app_settings  # noqa: PLC0415 - breaks an import cycle

    settings = get_app_settings()
    if _state.console is not None:
        _state.console.setLevel(_level_no(settings.console_log_level))
    if _state.file is not None:
        _state.file.setLevel(_level_no(settings.log_level))


def truncate_main_log() -> None:
    """Empty ``myastroshine.log`` in place, keeping the open handler valid."""
    handler = _state.file
    if isinstance(handler, logging.handlers.RotatingFileHandler):
        handler.acquire()
        try:
            if handler.stream is None:
                handler.stream = handler._open()
            handler.stream.truncate(0)
            handler.stream.seek(0)
        finally:
            handler.release()
        return
    path = get_settings().log_file
    if path.exists():
        path.write_text("", encoding="utf-8")
