#!/usr/bin/env python3
"""Print one install-manifest section as shell-safe pipe-delimited rows."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence


SECTIONS = {
    "own_repositories": ("name", "url"),
    "community_skills": ("name", "url", "path"),
    "plugins": ("marketplace", "plugin"),
    "reduced_install_skills": (),
}
EMPTY_SECTIONS = {"community_skills"}


class ManifestError(ValueError):
    """Reports an invalid shared installer manifest."""


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ManifestError(f"{path}: invalid JSON: {error.msg}") from error
    if not isinstance(manifest, dict) or set(manifest) != set(SECTIONS):
        raise ManifestError(f"{path}: manifest sections do not match the installer contract")
    return manifest


def section_rows(manifest: dict[str, Any], section: str) -> tuple[str, ...]:
    entries = manifest[section]
    if not isinstance(entries, list) or (not entries and section not in EMPTY_SECTIONS):
        raise ManifestError(f"{section} must be a non-empty array")
    fields = SECTIONS[section]
    rows: list[str] = []
    for index, entry in enumerate(entries):
        if not fields:
            if not isinstance(entry, str) or not entry or "|" in entry:
                raise ManifestError(f"{section}[{index}] must be a non-empty safe string")
            rows.append(entry)
            continue
        if not isinstance(entry, dict) or tuple(entry) != fields:
            raise ManifestError(f"{section}[{index}] fields must be: {', '.join(fields)}")
        values = tuple(entry[field] for field in fields)
        if not all(isinstance(value, str) and value and "|" not in value for value in values):
            raise ManifestError(f"{section}[{index}] contains an invalid value")
        rows.append("|".join(values))
    return tuple(rows)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("section", choices=tuple(SECTIONS))
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).parents[1] / "install-manifest.json",
    )
    arguments = parser.parse_args(argv)
    try:
        rows = section_rows(load_manifest(arguments.manifest), arguments.section)
    except (ManifestError, OSError) as error:
        print(f"install-manifest: {error}", file=sys.stderr)
        return 1
    print("\n".join(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
