#!/usr/bin/env python3
"""Check that every pinned dependency is the latest released version.

Reads the pins from:
  - backend/requirements.txt
  - backend/requirements-dev.txt   (PyPI)
  - frontend/package.json          (npm registry)

and compares each against the newest stable release on its registry.

Exit codes:
  0  every dependency is up to date (or was explicitly ignored)
  1  at least one dependency is behind
  2  a registry lookup failed (network / unknown package) and --strict was not
     relaxed; with --offline the script skips all lookups and exits 0

Usage:
  python scripts/check_deps_fresh.py
  python scripts/check_deps_fresh.py --json
  python scripts/check_deps_fresh.py --ignore numpy --ignore vite
  python scripts/check_deps_fresh.py --offline        # CI without network
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

try:
    from packaging.version import InvalidVersion, Version
except ModuleNotFoundError:  # pragma: no cover - packaging ships with pip
    print("error: 'packaging' is required (pip install packaging)", file=sys.stderr)
    raise SystemExit(2) from None

REPO_ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = [
    REPO_ROOT / "backend" / "requirements.txt",
    REPO_ROOT / "backend" / "requirements-dev.txt",
]
PACKAGE_JSON = REPO_ROOT / "frontend" / "package.json"
IGNORE_FILE = REPO_ROOT / "scripts" / "deps_fresh_ignore.txt"

USER_AGENT = "myastroshine-deps-fresh/1.0"
TIMEOUT = 20

Status = Literal["ok", "outdated", "ahead", "error", "ignored"]


@dataclass
class Result:
    ecosystem: Literal["pypi", "npm"]
    name: str
    pinned: str
    latest: str | None
    status: Status
    detail: str = ""


# --------------------------------------------------------------------------- #
# Parsing pinned versions
# --------------------------------------------------------------------------- #

_REQ_LINE = re.compile(
    r"^\s*(?P<name>[A-Za-z0-9._-]+)\s*(?:\[[^\]]+\])?\s*===?\s*(?P<version>[A-Za-z0-9._+!-]+)"
)


def parse_requirements(path: Path) -> dict[str, str]:
    pins: dict[str, str] = {}
    if not path.exists():
        return pins
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "-")):
            continue
        match = _REQ_LINE.match(line)
        if match:
            pins[match["name"].lower()] = match["version"]
    return pins


def parse_package_json(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    pins: dict[str, str] = {}
    for section in ("dependencies", "devDependencies", "optionalDependencies"):
        for name, spec in data.get(section, {}).items():
            cleaned = re.sub(r"^[\s^~>=<v]+", "", spec).split(" ")[0]
            if re.match(r"^\d", cleaned):
                pins[name] = cleaned
    return pins


def load_ignores(cli_ignores: list[str]) -> set[str]:
    ignores = {name.lower() for name in cli_ignores}
    if IGNORE_FILE.exists():
        for raw in IGNORE_FILE.read_text(encoding="utf-8").splitlines():
            line = raw.split("#", 1)[0].strip()
            if line:
                ignores.add(line.lower())
    return ignores


# --------------------------------------------------------------------------- #
# Registry lookups
# --------------------------------------------------------------------------- #


def _get_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.load(response)


def latest_pypi(name: str) -> str:
    data = _get_json(f"https://pypi.org/pypi/{name}/json")
    best: Version | None = None
    for version, files in data.get("releases", {}).items():
        if not files or all(f.get("yanked") for f in files):
            continue
        try:
            parsed = Version(version)
        except InvalidVersion:
            continue
        if parsed.is_prerelease:
            continue
        if best is None or parsed > best:
            best = parsed
    if best is not None:
        return str(best)
    return str(data["info"]["version"])


def latest_npm(name: str) -> str:
    quoted = name.replace("/", "%2f")
    data = _get_json(f"https://registry.npmjs.org/{quoted}/latest")
    return str(data["version"])


# --------------------------------------------------------------------------- #
# Comparison
# --------------------------------------------------------------------------- #


def compare(pinned: str, latest: str) -> Status:
    try:
        pinned_v, latest_v = Version(pinned), Version(latest)
    except InvalidVersion:
        return "ok" if pinned == latest else "outdated"
    if pinned_v == latest_v:
        return "ok"
    return "ahead" if pinned_v > latest_v else "outdated"


def check(
    ecosystem: Literal["pypi", "npm"],
    pins: dict[str, str],
    ignores: set[str],
) -> list[Result]:
    lookup = latest_pypi if ecosystem == "pypi" else latest_npm
    results: list[Result] = []
    for name, pinned in sorted(pins.items()):
        if name.lower() in ignores:
            results.append(Result(ecosystem, name, pinned, None, "ignored"))
            continue
        try:
            latest = lookup(name)
        except (urllib.error.URLError, urllib.error.HTTPError, KeyError, TimeoutError) as exc:
            results.append(Result(ecosystem, name, pinned, None, "error", str(exc)))
            continue
        results.append(Result(ecosystem, name, pinned, latest, compare(pinned, latest)))
    return results


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #

_SYMBOL = {
    "ok": "OK",
    "outdated": "OUTDATED",
    "ahead": "AHEAD",
    "error": "ERROR",
    "ignored": "ignored",
}


def print_table(results: list[Result]) -> None:
    name_width = max((len(r.name) for r in results), default=10)
    for r in results:
        latest = r.latest or "-"
        line = f"  {_SYMBOL[r.status]:9} {r.name:<{name_width}}  {r.pinned:>14} -> {latest}"
        if r.detail:
            line += f"   ({r.detail})"
        print(line)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--offline", action="store_true", help="skip all lookups, exit 0")
    parser.add_argument(
        "--ignore",
        action="append",
        default=[],
        metavar="NAME",
        help="dependency name to skip (repeatable); also read from scripts/deps_fresh_ignore.txt",
    )
    parser.add_argument(
        "--allow-lookup-errors",
        action="store_true",
        help="treat registry lookup failures as non-fatal",
    )
    args = parser.parse_args(argv)

    if args.offline:
        print("check_deps_fresh: --offline, skipping registry lookups")
        return 0

    ignores = load_ignores(args.ignore)

    py_pins: dict[str, str] = {}
    for req in REQUIREMENTS:
        py_pins.update(parse_requirements(req))
    js_pins = parse_package_json(PACKAGE_JSON)

    results = check("pypi", py_pins, ignores) + check("npm", js_pins, ignores)

    outdated = [r for r in results if r.status == "outdated"]
    errors = [r for r in results if r.status == "error"]

    if args.json:
        print(json.dumps([r.__dict__ for r in results], indent=2))
    else:
        print(f"\nPyPI ({len(py_pins)}) + npm ({len(js_pins)}) dependencies\n")
        print_table(results)
        print()
        if outdated:
            print(f"{len(outdated)} outdated: " + ", ".join(r.name for r in outdated))
        if errors:
            print(f"{len(errors)} lookup error(s): " + ", ".join(r.name for r in errors))
        if not outdated and not errors:
            print("All dependencies are at their latest release.")

    if outdated:
        return 1
    if errors and not args.allow_lookup_errors:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
