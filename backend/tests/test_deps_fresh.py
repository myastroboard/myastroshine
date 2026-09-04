"""Every pinned dependency must be the latest released version.

``test_all_dependencies_are_latest`` shells out to ``scripts/check_deps_fresh.py``
(which queries PyPI and the npm registry) and fails if any pin is behind.

It is a networked test:
  - skipped automatically when the registries cannot be reached
  - skipped when ``SKIP_DEPS_FRESH=1`` is set (use in fully offline CI)

The other tests here cover the checker's own parsing/comparison logic offline.

Run just this file:
  pytest backend/tests/test_deps_fresh.py
  python scripts/check_deps_fresh.py        # same logic, human-readable
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_deps_fresh.py"


def _load_checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_deps_fresh", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses needs the module registered
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


@pytest.mark.parametrize(
    ("pinned", "latest", "expected"),
    [
        ("1.2.3", "1.2.3", "ok"),
        ("1.2.3", "1.2.4", "outdated"),
        ("2.0.0", "1.9.9", "ahead"),
        ("19.2.8", "19.2.18", "outdated"),  # numeric compare, not lexical
        ("0.0.32", "0.0.32", "ok"),
    ],
)
def test_compare_semantics(pinned: str, latest: str, expected: str) -> None:
    """Version comparison is numeric and direction-aware."""
    assert checker.compare(pinned, latest) == expected


def test_requirements_are_fully_pinned() -> None:
    """Every runtime/dev requirement uses an exact '==' pin the checker can read."""
    for req in checker.REQUIREMENTS:
        pins = checker.parse_requirements(req)
        assert pins, f"no pins parsed from {req.name}"
        for name, version in pins.items():
            assert version[0].isdigit(), f"{name} in {req.name} is not pinned to a concrete version"


def test_package_json_versions_are_parsed() -> None:
    """Frontend deps and devDeps resolve to concrete versions."""
    pins = checker.parse_package_json(checker.PACKAGE_JSON)
    assert {"react", "vite", "typescript"} <= pins.keys()


@pytest.mark.skipif(os.environ.get("SKIP_DEPS_FRESH") == "1", reason="SKIP_DEPS_FRESH=1")
def test_all_dependencies_are_latest() -> None:
    """No dependency in requirements*.txt or package.json is behind its registry."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--json"],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )

    if proc.returncode == 2:
        pytest.skip(f"dependency registries unreachable:\n{proc.stdout}\n{proc.stderr}")

    results = json.loads(proc.stdout)
    outdated = [r for r in results if r["status"] == "outdated"]

    assert not outdated, (
        "outdated dependencies (run: python scripts/check_deps_fresh.py):\n"
        + "\n".join(
            f"  {r['ecosystem']:4} {r['name']}: pinned {r['pinned']} -> latest {r['latest']}"
            for r in outdated
        )
    )
