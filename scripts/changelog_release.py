#!/usr/bin/env python3
"""Move CHANGELOG.md's ``[Unreleased]`` section into a dated release section.

Used by the release pipeline (.github/workflows/release.yml,
post-release-cleanup.yml) - not part of the normal test/lint suite. The
changelog follows the organization format: ``## [Unreleased]`` holds
``### Features`` / ``### Fixes`` / ``### Breaking changes``, each ``- None.``
until an entry replaces the placeholder; released sections are
``## X.Y.Z (YYYY-MM-DD)``.

Two modes:

    --extract           Print the current [Unreleased] section body to stdout,
                         without the subsections that are still "- None."
                         (used to build GitHub Release notes before the
                         changelog itself is touched).

    --finalize VERSION  Rewrite CHANGELOG.md in place: retitle the current
                         [Unreleased] section as "## VERSION (DATE)" and
                         insert a fresh [Unreleased] template above it.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

CHANGELOG_PATH = Path(__file__).resolve().parent.parent / "CHANGELOG.md"
_UNRELEASED_RE = re.compile(r"^## \[Unreleased\]\s*$", re.MULTILINE)
_NEXT_SECTION_RE = re.compile(r"^## ", re.MULTILINE)
_SUBSECTION_RE = re.compile(r"^### (.+)$", re.MULTILINE)
PLACEHOLDER = "- None."
UNRELEASED_TEMPLATE = (
    f"### Features\n\n{PLACEHOLDER}\n\n"
    f"### Fixes\n\n{PLACEHOLDER}\n\n"
    f"### Breaking changes\n\n{PLACEHOLDER}"
)


def _unreleased_span(text: str) -> tuple[int, int]:
    """Return (body_start, body_end) offsets for the Unreleased section's body,
    i.e. everything after the ``## [Unreleased]`` heading line up to the next
    ``## `` heading (or end of file)."""
    heading = _UNRELEASED_RE.search(text)
    if heading is None:
        raise SystemExit("CHANGELOG.md has no '## [Unreleased]' section")
    body_start = heading.end()
    next_section = _NEXT_SECTION_RE.search(text, pos=body_start)
    body_end = next_section.start() if next_section else len(text)
    return body_start, body_end


def _real_subsections(body: str) -> list[tuple[str, str]]:
    """(title, entries) of every subsection that holds more than the placeholder."""
    parts = _SUBSECTION_RE.split(body)
    subsections = []
    for title, raw_entries in zip(parts[1::2], parts[2::2], strict=True):
        entries = raw_entries.strip("\n")
        if entries.strip() not in ("", PLACEHOLDER):
            subsections.append((title.strip(), entries))
    return subsections


def extract() -> str:
    text = CHANGELOG_PATH.read_text(encoding="utf-8")
    start, end = _unreleased_span(text)
    return "\n\n".join(
        f"### {title}\n\n{entries}" for title, entries in _real_subsections(text[start:end])
    )


def finalize(version: str, date: str) -> None:
    text = CHANGELOG_PATH.read_text(encoding="utf-8")
    start, end = _unreleased_span(text)
    body = text[start:end].strip("\n")
    if not _real_subsections(body):
        raise SystemExit("Nothing under [Unreleased] to release")
    before = text[:start].rstrip("\n")
    after = text[end:].lstrip("\n")
    new_text = f"{before}\n\n{UNRELEASED_TEMPLATE}\n\n## {version} ({date})\n\n{body}\n\n{after}"
    CHANGELOG_PATH.write_text(new_text.rstrip("\n") + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--extract", action="store_true", help="print the Unreleased body")
    group.add_argument("--finalize", metavar="VERSION", help="bare X.Y.Z, no 'v' prefix")
    parser.add_argument(
        "--date",
        default=datetime.now(UTC).strftime("%Y-%m-%d"),
        help="release date (default: today, UTC)",
    )
    args = parser.parse_args()

    if args.extract:
        print(extract())
    else:
        finalize(args.finalize, args.date)
    return 0


if __name__ == "__main__":
    sys.exit(main())
