#!/usr/bin/env python3
"""Validate the frontend i18n translation files.

Checks (all are hard failures):
  1. Every language in SUPPORTED_LANGUAGES (frontend/src/i18n/config.ts) has a
     frontend/src/i18n/translations/<lang>.json file, and vice versa.
  2. No JSON file contains duplicate object keys.
  3. No translation key present in en.json is missing from another language.
  4. No translated file contains keys not present in en.json (orphan keys).
  5. No translated leaf value has a different type than the corresponding
     en.json value.
  6. No translation value contains HTML entities (e.g. &amp; &lt; &gt;) - use
     plain Unicode characters instead.
  7. Every `{placeholder}` in an en.json value also appears in the matching
     value of every other language, and vice versa (broken interpolation
     otherwise).

Usage:
    python scripts/validate_i18n.py
"""

from __future__ import annotations

import contextlib
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
I18N_DIR = REPO_ROOT / "frontend" / "src" / "i18n"
TRANSLATIONS_DIR = I18N_DIR / "translations"
CONFIG_FILE = I18N_DIR / "config.ts"
REFERENCE_LANG = "en"

_HTML_ENTITY_RE = re.compile(r"&(?:[a-zA-Z]{2,10}|#\d{1,7}|#x[0-9a-fA-F]{1,6});")
_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z0-9_]+)\}")


def flatten_keys(data: Any, parent: str = "") -> set[str]:
    """Return flattened dot-notation keys from a nested JSON structure."""
    keys: set[str] = set()
    if isinstance(data, dict):
        for key, value in data.items():
            path = f"{parent}.{key}" if parent else str(key)
            if isinstance(value, dict):
                keys.update(flatten_keys(value, path))
            else:
                keys.add(path)
    return keys


def get_leaf_types(data: Any, parent: str = "") -> dict[str, str]:
    """Return {dot-notation-path: type_name} for every leaf node."""
    result: dict[str, str] = {}
    if isinstance(data, dict):
        for key, value in data.items():
            path = f"{parent}.{key}" if parent else str(key)
            if isinstance(value, dict):
                result.update(get_leaf_types(value, path))
            else:
                result[path] = type(value).__name__
    return result


def get_leaf_values(data: Any, parent: str = "") -> dict[str, Any]:
    """Return {dot-notation-path: value} for every leaf node."""
    result: dict[str, Any] = {}
    if isinstance(data, dict):
        for key, value in data.items():
            path = f"{parent}.{key}" if parent else str(key)
            if isinstance(value, dict):
                result.update(get_leaf_values(value, path))
            else:
                result[path] = value
    return result


def find_duplicate_keys(text: str) -> list[str]:
    """Return keys that appear more than once in any JSON object within the text."""
    duplicates: list[str] = []

    def object_pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        seen: dict[str, Any] = {}
        for key, value in pairs:
            if key in seen:
                duplicates.append(key)
            seen[key] = value
        return seen

    with contextlib.suppress(json.JSONDecodeError):
        json.loads(text, object_pairs_hook=object_pairs_hook)
    return duplicates


def find_html_entities(data: Any, parent: str = "") -> list[str]:
    """Return dot-notation paths of leaf strings that contain HTML entities."""
    hits: list[str] = []
    if isinstance(data, dict):
        for key, value in data.items():
            path = f"{parent}.{key}" if parent else str(key)
            hits.extend(find_html_entities(value, path))
    elif isinstance(data, str) and _HTML_ENTITY_RE.search(data):
        hits.append(parent)
    return hits


def parse_supported_languages(source: str) -> list[str]:
    """Extract the SUPPORTED_LANGUAGES tuple from frontend/src/i18n/config.ts."""
    match = re.search(r"SUPPORTED_LANGUAGES\s*=\s*\[([^\]]+)\]", source)
    if not match:
        return []
    return re.findall(r"'([a-z]{2})'", match.group(1))


def validate_declared_languages(declared: list[str], json_languages: list[str]) -> list[str]:
    """Cross-check config.ts's declared languages against the translations/ files present."""
    errors: list[str] = []
    for lang in declared:
        if lang not in json_languages:
            errors.append(f"[{lang}] declared in config.ts but no translations/{lang}.json")
    for lang in json_languages:
        if lang not in declared:
            errors.append(f"[{lang}] translations/{lang}.json exists but not in config.ts")
    return errors


def validate_against_reference(
    lang: str,
    lang_json: Any,
    ref_keys: set[str],
    ref_types: dict[str, str],
    ref_values: dict[str, Any],
) -> list[str]:
    """Check one non-reference language file's keys, types, and placeholders against en.json."""
    errors: list[str] = []
    lang_keys = flatten_keys(lang_json)
    lang_types = get_leaf_types(lang_json)
    lang_values = get_leaf_values(lang_json)

    for key in sorted(ref_keys - lang_keys):
        errors.append(f"[{lang}] missing translation key: '{key}'")
    for key in sorted(lang_keys - ref_keys):
        errors.append(f"[{lang}] extra key not in reference: '{key}'")

    for key in sorted(set(ref_types) & set(lang_types)):
        if ref_types[key] != lang_types[key]:
            errors.append(
                f"[{lang}] type mismatch at '{key}': {ref_types[key]} vs {lang_types[key]}"
            )

    for key in sorted(set(ref_values) & set(lang_values)):
        ref_value, lang_value = ref_values[key], lang_values[key]
        if not isinstance(ref_value, str) or not isinstance(lang_value, str):
            continue
        ref_placeholders = set(_PLACEHOLDER_RE.findall(ref_value))
        lang_placeholders = set(_PLACEHOLDER_RE.findall(lang_value))
        if ref_placeholders != lang_placeholders:
            errors.append(
                f"[{lang}] placeholder mismatch at '{key}': "
                f"{sorted(ref_placeholders)} vs {sorted(lang_placeholders)}"
            )

    return errors


def validate_language_file(
    lang: str,
    raw: str,
    ref_keys: set[str],
    ref_types: dict[str, str],
    ref_values: dict[str, Any],
) -> list[str]:
    """Run every per-file check for one language's translations/<lang>.json."""
    errors: list[str] = [f"[{lang}] duplicate key: '{dup}'" for dup in find_duplicate_keys(raw)]

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        errors.append(f"[{lang}] could not parse translation file: {exc}")
        return errors

    for key in find_html_entities(parsed):
        errors.append(f"[{lang}] HTML entity at '{key}' (use plain Unicode instead)")

    if lang != REFERENCE_LANG and ref_keys:
        errors.extend(validate_against_reference(lang, parsed, ref_keys, ref_types, ref_values))

    return errors


def load_reference(ref_path: Path) -> tuple[set[str], dict[str, str], dict[str, Any], list[str]]:
    """Load en.json and flatten it for cross-language comparison."""
    if not ref_path.exists():
        return set(), {}, {}, [f"reference translation file not found: {ref_path}"]
    try:
        data = json.loads(ref_path.read_text(encoding="utf-8"))
        return flatten_keys(data), get_leaf_types(data), get_leaf_values(data), []
    except (OSError, json.JSONDecodeError) as exc:
        return set(), {}, {}, [f"[{REFERENCE_LANG}] could not load reference file: {exc}"]


def main() -> int:
    if not CONFIG_FILE.exists():
        print(f"ERROR: Config file not found: {CONFIG_FILE}")
        return 1

    json_languages = sorted(p.stem for p in TRANSLATIONS_DIR.glob("*.json"))
    if not json_languages:
        print(f"ERROR: No i18n JSON files found in {TRANSLATIONS_DIR}.")
        return 1

    declared_languages = parse_supported_languages(CONFIG_FILE.read_text(encoding="utf-8"))
    errors = (
        [f"could not parse SUPPORTED_LANGUAGES from {CONFIG_FILE.name}"]
        if not declared_languages
        else []
    )
    errors += validate_declared_languages(declared_languages, json_languages)

    ref_keys, ref_types, ref_values, ref_errors = load_reference(
        TRANSLATIONS_DIR / f"{REFERENCE_LANG}.json"
    )
    errors += ref_errors

    for lang in json_languages:
        lang_path = TRANSLATIONS_DIR / f"{lang}.json"
        try:
            raw = lang_path.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"[{lang}] could not read file: {exc}")
            continue
        errors += validate_language_file(lang, raw, ref_keys, ref_types, ref_values)

    if errors:
        print(f"i18n validation FAILED - {len(errors)} error(s) found:\n")
        for err in errors:
            print(f" X {err}")
        print()
        return 1

    print(f"i18n validation OK - {len(json_languages)} language(s): {json_languages}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
