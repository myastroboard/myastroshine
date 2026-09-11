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


def test_render_file_falls_back_to_the_raw_timestamp_when_unparseable() -> None:
    """A timestamp that isn't ISO-8601 (or missing) is passed through as-is
    rather than raising out of the formatter."""
    line = logging_config._render_file(
        None,
        "info",
        {"timestamp": "not-a-timestamp", "level": "info", "logger": "app.x", "event": "hi"},
    )
    assert line.startswith("not-a-timestamp - app.x - INFO - hi")


def test_apply_runtime_log_levels_updates_both_handlers_when_present(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.utils import app_settings

    console = logging.StreamHandler()
    file_handler = logging_config._build_file_handler(tmp_path / "app.log")
    monkeypatch.setattr(logging_config._state, "console", console)
    monkeypatch.setattr(logging_config._state, "file", file_handler)
    app_settings.save_app_settings({"console_log_level": "warning", "log_level": "debug"})

    logging_config.apply_runtime_log_levels()

    assert console.level == logging.WARNING
    assert file_handler.level == logging.DEBUG
    file_handler.close()


def test_apply_runtime_log_levels_is_a_noop_with_no_handlers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(logging_config._state, "console", None)
    monkeypatch.setattr(logging_config._state, "file", None)

    logging_config.apply_runtime_log_levels()  # must not raise


def test_truncate_main_log_is_a_noop_when_the_log_file_does_not_exist() -> None:
    logging_config.configure_logging(force=True)
    assert logging_config._state.file is None  # test env: no file handler

    logging_config.truncate_main_log()  # must not raise even though nothing exists

    assert not get_settings().log_file.exists()


def test_truncate_main_log_empties_the_rotating_handlers_stream(tmp_path) -> None:
    log_path = tmp_path / "app.log"
    handler = logging_config._build_file_handler(log_path)
    handler.stream.write("stale content\n")
    handler.stream.flush()
    assert log_path.stat().st_size > 0

    from app import logging_config as module

    original = module._state.file
    module._state.file = handler
    try:
        module.truncate_main_log()
        assert log_path.stat().st_size == 0
    finally:
        module._state.file = original
        handler.close()
