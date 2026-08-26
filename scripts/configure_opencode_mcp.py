#!/usr/bin/env python3
"""Idempotently register one local MCP server in OpenCode's user config."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any


IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class ConfigError(ValueError):
    """Reports a config that cannot be safely updated."""


def _strip_jsonc_comments(text: str) -> str:
    """Remove JSONC comments without treating URL text as a comment."""

    output: list[str] = []
    index = 0
    in_string = False
    escaped = False
    while index < len(text):
        char = text[index]
        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            output.append(char)
            index += 1
        elif text.startswith("//", index):
            newline = text.find("\n", index)
            index = len(text) if newline == -1 else newline
        elif text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end == -1:
                raise ConfigError("OpenCode config has an unterminated block comment")
            index = end + 2
        else:
            output.append(char)
            index += 1
    return "".join(output)


def _parse_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = path.read_text(encoding="utf-8")
        json_text = re.sub(r",\s*([}\]])", r"\1", _strip_jsonc_comments(raw))
        parsed = json.loads(json_text)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ConfigError(f"cannot parse OpenCode config {path}: {error}") from error
    if not isinstance(parsed, dict):
        raise ConfigError("OpenCode config root must be a JSON object")
    return parsed


def _backup_path(path: Path) -> Path:
    base = Path(f"{path}.bak-{date.today():%Y%m%d}")
    candidate = base
    suffix = 1
    while candidate.exists():
        candidate = Path(f"{base}-{suffix}")
        suffix += 1
    return candidate


def configure(path: Path, name: str, command: list[str], *, dry_run: bool = False) -> str:
    if not IDENTIFIER.fullmatch(name):
        raise ConfigError(f"invalid MCP server name: {name!r}")
    if not command or any(not isinstance(item, str) or not item for item in command):
        raise ConfigError("MCP command must contain at least one non-empty argument")

    config = _parse_config(path)
    raw_mcp = config.get("mcp", {})
    if not isinstance(raw_mcp, dict):
        raise ConfigError("OpenCode config mcp field must be an object")
    mcp = raw_mcp
    desired = {"type": "local", "command": command}
    existing = mcp.get(name)
    if existing is not None:
        if not isinstance(existing, dict):
            raise ConfigError(f"OpenCode MCP entry {name!r} is not an object")
        if existing.get("type") == desired["type"] and existing.get("command") == command:
            return f"{name}: already configured"
        raise ConfigError(
            f"OpenCode MCP entry {name!r} already exists with a different command; refusing to replace it"
        )

    mcp[name] = desired
    config["mcp"] = mcp
    if dry_run:
        return f"{name}: would update {path}"

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = _backup_path(path)
        try:
            backup.write_bytes(path.read_bytes())
        except OSError as error:
            raise ConfigError(f"cannot back up OpenCode config {path}: {error}") from error
        print(f"  backup saved at {backup}")

    mode = path.stat().st_mode if path.exists() else 0o644
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            json.dump(config, temporary, indent=2, ensure_ascii=False)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.chmod(temporary_name, mode)
        os.replace(temporary_name, path)
    except OSError as error:
        if temporary_name:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
        raise ConfigError(f"cannot write OpenCode config {path}: {error}") from error
    return f"{name}: configured in {path}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True, help="OpenCode opencode.json path")
    parser.add_argument("--name", required=True, help="MCP server name")
    parser.add_argument("--command", nargs="+", required=True, help="local MCP command and arguments")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        print(configure(args.config, args.name, args.command, dry_run=args.dry_run))
    except ConfigError as error:
        print(f"OpenCode MCP configuration failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
