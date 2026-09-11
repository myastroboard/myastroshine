"""Tests for app._read_version's fallback chain.

__version__ is computed once at package-import time, so the "VERSION file
exists and is readable" branch is already exercised just by importing the
package - these fill in the two branches that normal dev import never hits:
the APP_VERSION env override, and the file being unreadable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import app as app_package


def test_read_version_prefers_the_app_version_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_VERSION", "9.9.9-test")
    assert app_package._read_version() == "9.9.9-test"


def test_read_version_falls_back_to_dev_default_when_the_file_is_unreadable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("APP_VERSION", raising=False)

    def _raise(self: Path, *args: object, **kwargs: object) -> str:
        raise OSError("no such file")

    monkeypatch.setattr(Path, "read_text", _raise)
    assert app_package._read_version() == "0.0.0-dev"
