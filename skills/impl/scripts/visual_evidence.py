#!/usr/bin/env python3
"""Validate vision-reviewed screenshots for one frontend implementation task."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
import zlib
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence


SCHEMA_VERSION = 1
PLATFORM_PROFILES = {
    "desktop": {"width": 1920, "height": 1080, "browser": "chromium"},
    "notebook": {"width": 1366, "height": 768, "browser": "chromium"},
    "tablet": {"width": 810, "height": 1080, "browser": "webkit"},
    "mobile": {"width": 390, "height": 664, "browser": "webkit"},
}
EXPECTATION_PATTERN = re.compile(
    r"^(?P<id>[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*)\s*\|\s*"
    r"(?P<surface>[^|]+?)\s*\|\s*(?P<platform>[a-z]+)\s*\|\s*"
    r"(?P<width>\d+)x(?P<height>\d+)\s*\|\s*"
    r"(?P<state>[^|]+?)$"
)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
VISION_TOOLS = {"computer-use", "view_image"}


class VisualEvidenceError(ValueError):
    """Reports invalid or incomplete visual evidence."""


def parse_expectation(value: str) -> dict[str, Any]:
    match = EXPECTATION_PATTERN.fullmatch(value.strip())
    if not match:
        raise VisualEvidenceError(
            "Visual entries must use: <id> | <route-or-component> | "
            "<platform> | <width>x<height> | <state>"
        )
    parsed: dict[str, Any] = match.groupdict()
    parsed["width"] = int(parsed["width"])
    parsed["height"] = int(parsed["height"])
    profile = PLATFORM_PROFILES.get(parsed["platform"])
    if profile is None:
        raise VisualEvidenceError(
            f"Visual platform must be one of: {', '.join(PLATFORM_PROFILES)}"
        )
    if (parsed["width"], parsed["height"]) != (profile["width"], profile["height"]):
        raise VisualEvidenceError(
            f"Visual platform {parsed['platform']} requires "
            f"{profile['width']}x{profile['height']}"
        )
    return parsed


def validate_expectation_matrix(expectations: Sequence[str]) -> None:
    grouped: dict[tuple[str, str], set[str]] = {}
    for expectation in expectations:
        parsed = parse_expectation(expectation)
        group = (parsed["surface"], parsed["state"])
        platforms = grouped.setdefault(group, set())
        if parsed["platform"] in platforms:
            raise VisualEvidenceError(
                f"duplicate {parsed['platform']} Visual entry for "
                f"{parsed['surface']} in state {parsed['state']}"
            )
        platforms.add(parsed["platform"])

    required = set(PLATFORM_PROFILES)
    for (surface, state), platforms in grouped.items():
        missing = required - platforms
        if missing:
            raise VisualEvidenceError(
                f"Visual matrix for {surface} in state {state} is missing: "
                f"{', '.join(sorted(missing))}"
            )


def repo_file(repo: Path, relative_value: str, context: str) -> Path:
    relative = Path(relative_value)
    if relative.is_absolute() or ".." in relative.parts:
        raise VisualEvidenceError(f"{context} must stay inside the repository")
    root = repo.resolve()
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise VisualEvidenceError(f"{context} must stay inside the repository") from error
    if not resolved.is_file():
        raise VisualEvidenceError(f"{context} does not exist: {relative_value}")
    return resolved


def png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        raise VisualEvidenceError(f"screenshot is not a PNG: {path}")

    position = len(PNG_SIGNATURE)
    width = height = bit_depth = color_type = interlace = None
    compressed = bytearray()
    saw_end = False
    while position + 12 <= len(data):
        length = struct.unpack(">I", data[position : position + 4])[0]
        chunk_type = data[position + 4 : position + 8]
        chunk_start = position + 8
        chunk_end = chunk_start + length
        crc_end = chunk_end + 4
        if crc_end > len(data):
            raise VisualEvidenceError(f"screenshot has a truncated PNG chunk: {path}")
        chunk = data[chunk_start:chunk_end]
        expected_crc = struct.unpack(">I", data[chunk_end:crc_end])[0]
        actual_crc = zlib.crc32(chunk_type + chunk) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            raise VisualEvidenceError(f"screenshot has an invalid PNG checksum: {path}")
        if chunk_type == b"IHDR":
            if length != 13:
                raise VisualEvidenceError(f"screenshot has an invalid PNG header: {path}")
            width, height, bit_depth, color_type, _, _, interlace = struct.unpack(">IIBBBBB", chunk)
        elif chunk_type == b"IDAT":
            compressed.extend(chunk)
        elif chunk_type == b"IEND":
            saw_end = True
            break
        position = crc_end

    if not saw_end or not compressed or width is None or height is None:
        raise VisualEvidenceError(f"screenshot is not a complete PNG: {path}")
    if bit_depth != 8 or color_type not in {2, 6} or interlace != 0:
        raise VisualEvidenceError(
            f"screenshot must be a non-interlaced 8-bit RGB or RGBA PNG: {path}"
        )
    bytes_per_pixel = 3 if color_type == 2 else 4
    try:
        pixels = zlib.decompress(bytes(compressed))
    except zlib.error as error:
        raise VisualEvidenceError(f"screenshot pixel data is corrupt: {path}") from error
    expected_size = height * (1 + width * bytes_per_pixel)
    if len(pixels) != expected_size:
        raise VisualEvidenceError(f"screenshot pixel data has the wrong size: {path}")
    if len(set(pixels[: min(len(pixels), 200_000)])) < 8:
        raise VisualEvidenceError(f"screenshot appears blank or synthetic: {path}")
    return width, height


def parse_reviewed_at(value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        raise VisualEvidenceError("reviewed_at must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise VisualEvidenceError("reviewed_at must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise VisualEvidenceError("reviewed_at must include a timezone")


def validate_manifest(
    repo: Path,
    manifest_path: Path,
    change: str,
    task_id: str,
    expectations: Sequence[str],
) -> dict[str, Any]:
    validate_expectation_matrix(expectations)
    required_directory = (repo.resolve() / ".visual-evidence" / change).resolve()
    try:
        manifest_path.resolve().relative_to(required_directory)
    except ValueError as error:
        raise VisualEvidenceError(
            f"visual evidence manifest must be stored under "
            f".visual-evidence/{change}/"
        ) from error
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise VisualEvidenceError(f"invalid visual evidence manifest: {error}") from error
    required = {
        "schema_version",
        "change",
        "task",
        "reviewed_with",
        "reviewed_at",
        "results",
    }
    if not isinstance(manifest, dict) or set(manifest) != required:
        raise VisualEvidenceError("visual evidence manifest has missing or unknown fields")
    if manifest["schema_version"] != SCHEMA_VERSION:
        raise VisualEvidenceError(f"visual evidence schema_version must be {SCHEMA_VERSION}")
    if manifest["change"] != change or manifest["task"] != task_id:
        raise VisualEvidenceError("visual evidence change and task must match impl state")
    if manifest["reviewed_with"] not in VISION_TOOLS:
        raise VisualEvidenceError("reviewed_with must be computer-use or view_image")
    parse_reviewed_at(manifest["reviewed_at"])
    if not isinstance(manifest["results"], list):
        raise VisualEvidenceError("visual evidence results must be an array")

    expected = {value: parse_expectation(value) for value in expectations}
    observed: set[str] = set()
    result_fields = {
        "expectation",
        "browser",
        "screenshot",
        "sha256",
        "status",
        "observation",
    }
    for result in manifest["results"]:
        if not isinstance(result, dict) or set(result) != result_fields:
            raise VisualEvidenceError("each visual result has missing or unknown fields")
        expectation = result["expectation"]
        if expectation not in expected:
            raise VisualEvidenceError(f"unexpected visual result: {expectation}")
        if expectation in observed:
            raise VisualEvidenceError(f"duplicate visual result: {expectation}")
        if result["status"] != "pass":
            raise VisualEvidenceError(f"visual result did not pass: {expectation}")
        expected_browser = PLATFORM_PROFILES[expected[expectation]["platform"]]["browser"]
        if result["browser"] != expected_browser:
            raise VisualEvidenceError(
                f"visual result for {expectation} requires browser {expected_browser}"
            )
        if not isinstance(result["observation"], str) or len(result["observation"].strip()) < 20:
            raise VisualEvidenceError(f"visual result needs a concrete observation: {expectation}")
        screenshot_value = result["screenshot"]
        if not isinstance(screenshot_value, str):
            raise VisualEvidenceError(f"visual screenshot path must be a string: {expectation}")
        required_prefix = Path(".visual-evidence") / change
        screenshot_relative = Path(screenshot_value)
        if not screenshot_relative.is_relative_to(required_prefix):
            raise VisualEvidenceError(
                f"visual screenshot must be stored under {required_prefix.as_posix()}/"
            )
        screenshot = repo_file(repo, screenshot_value, "visual screenshot")
        try:
            screenshot.resolve().relative_to(required_directory)
        except ValueError as error:
            raise VisualEvidenceError(
                f"visual screenshot must resolve under {required_prefix.as_posix()}/"
            ) from error
        digest = result["sha256"]
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise VisualEvidenceError(f"visual screenshot needs a lowercase SHA-256: {expectation}")
        actual_digest = hashlib.sha256(screenshot.read_bytes()).hexdigest()
        if digest != actual_digest:
            raise VisualEvidenceError(f"visual screenshot changed after review: {expectation}")
        actual_width, actual_height = png_dimensions(screenshot)
        if actual_width != expected[expectation]["width"]:
            raise VisualEvidenceError(
                f"screenshot width for {expectation} is {actual_width}, expected {expected[expectation]['width']}"
            )
        if actual_height < expected[expectation]["height"]:
            raise VisualEvidenceError(
                f"screenshot height for {expectation} is {actual_height}, expected at least {expected[expectation]['height']}"
            )
        observed.add(expectation)

    missing = set(expected) - observed
    if missing:
        raise VisualEvidenceError(f"missing visual results: {', '.join(sorted(missing))}")
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate frontend visual evidence.")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--change", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--expectation", action="append", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    repo = arguments.repo.resolve()
    manifest = arguments.manifest
    if not manifest.is_absolute():
        manifest = repo / manifest
    try:
        validate_manifest(repo, manifest, arguments.change, arguments.task, arguments.expectation)
        print("visual evidence passed")
    except VisualEvidenceError as error:
        print(f"visual-evidence: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
