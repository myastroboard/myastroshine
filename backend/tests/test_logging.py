"""Logging configuration: the rotating file sink and the line format."""

from __future__ import annotations

import logging
import logging.handlers

import pytest

from app import logging_config
from app.config import get_settings
from app.constants import LOG_BACKUP_COUNT, LOG_MAX_BYTES


def test_file_line_format_has_offset_module_and_callsite() -> None:
    """`<ts>,<ms> <offset> - <logger> - LEVEL [func:line] - event k=v`."""
    line = logging_config._render_file(
        None,
        "info",
        {
            "timestamp": "2026-09-04T21:15:03.142363+00:00",
            "level": "info",
            "logger": "app.services.stacking",
            "func_name": "combine",
            "lineno": 88,
            "event": "stack combined",
            "frames": 12,
        },
    )

    assert line == (
        "2026-09-04 21:15:03,142 +0000 - app.services.stacking - INFO "
        "[combine:88] - stack combined frames=12"
    )


def test_build_file_handler_is_rotating_with_the_documented_limits(tmp_path) -> None:
    handler = logging_config._build_file_handler(tmp_path / "sub" / "app.log")

    assert isinstance(handler, logging.handlers.RotatingFileHandler)
    assert handler.maxBytes == LOG_MAX_BYTES
    assert handler.backupCount == LOG_BACKUP_COUNT
    assert (tmp_path / "sub").is_dir()
    handler.close()


def test_configure_logging_attaches_a_file_sink_outside_tests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Under a non-test APP_ENV the rotating file handler is wired and writes."""
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    try:
        logging_config.configure_logging(force=True)
        log_path = get_settings().log_file

        logging_config.get_logger("test.logging").warning("hello file", answer=42)

        assert logging_config._state.file is not None
        text = log_path.read_text(encoding="utf-8")
        assert "hello file answer=42" in text
        assert " - WARNING [" in text
    finally:
        monkeypatch.setenv("APP_ENV", "test")
        get_settings.cache_clear()
        logging_config.configure_logging(force=True)


def test_no_file_sink_under_app_env_test() -> None:
    logging_config.configure_logging(force=True)
    assert logging_config._state.file is None
