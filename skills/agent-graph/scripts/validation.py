#!/usr/bin/env python3
"""Validation helpers shared by the Agent Graph CLI."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any, Mapping

from graph_core import GraphValidationError, TASK_ID_PATTERN, normalize_repo_path


SHELL_OPERATOR_CHARACTERS = frozenset("|&;<>")
CLEANUP_KINDS = frozenset({"process", "worktree", "branch", "temp_path", "terminal", "other"})


class CliValidationError(ValueError):
    """Reports unsafe CLI input or an invalid repository artifact."""


def require_identifier(value: str, context: str) -> str:
    if not isinstance(value, str) or not TASK_ID_PATTERN.fullmatch(value):
        raise CliValidationError(f"{context} must be a safe identifier without path separators")
    return value


def repository_relative_path(repository: Path, value: str | Path, context: str) -> tuple[Path, str]:
    text = value.as_posix() if isinstance(value, Path) else value
    try:
        normalized = normalize_repo_path(text, context)
    except GraphValidationError as error:
        raise CliValidationError(str(error)) from error
    if normalized.endswith("/"):
        raise CliValidationError(f"{context} must name a file")
    resolved = (repository / normalized).resolve()
    try:
        resolved.relative_to(repository.resolve())
    except ValueError as error:
        raise CliValidationError(f"{context} must stay inside the repository") from error
    return resolved, normalized


def load_json_object(path: Path, context: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise CliValidationError(f"{context} does not exist: {path}") from error
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CliValidationError(f"cannot read {context} {path}: {error}") from error
    if not isinstance(value, dict):
        raise CliValidationError(f"{context} must contain one JSON object")
    return value


def direct_command_arguments(command: str) -> list[str]:
    """Parse one direct executable and reject shell composition on every OS."""

    if not isinstance(command, str) or not command.strip():
        raise CliValidationError("check command must be a non-empty string")
    try:
        lexer = shlex.shlex(
            command,
            posix=os.name != "nt",
            punctuation_chars="|&;<>",
        )
        lexer.whitespace_split = True
        arguments = list(lexer)
    except ValueError as error:
        raise CliValidationError(f"check command has invalid quoting: {error}") from error
    if not arguments:
        raise CliValidationError("check command is empty")
    operator = next(
        (
            token
            for token in arguments
            if token and all(character in SHELL_OPERATOR_CHARACTERS for character in token)
        ),
        None,
    )
    if operator is not None:
        raise CliValidationError(
            f"check uses shell operator {operator!r}; move composition into a reviewed script"
        )
    return arguments


def canonical_receipt_id(receipt: Mapping[str, Any]) -> str:
    serialized = json.dumps(receipt, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return "receipt-" + hashlib.sha256(serialized).hexdigest()


def process_exists(process_id: str) -> bool:
    if not process_id.isdigit():
        return False
    if os.name == "nt":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {process_id}", "/FO", "CSV", "/NH"],
            check=False,
            capture_output=True,
            text=True,
        )
        return result.returncode == 0 and f'"{process_id}"' in result.stdout
    try:
        os.kill(int(process_id), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def cleanup_target_exists(repository: Path, kind: str, target: str) -> bool:
    if kind not in CLEANUP_KINDS:
        raise CliValidationError(f"cleanup kind must be one of: {', '.join(sorted(CLEANUP_KINDS))}")
    if kind == "process":
        if not target.isdigit():
            raise CliValidationError("process cleanup target must be a PID")
        return process_exists(target)
    if kind == "branch":
        result = subprocess.run(
            ["git", "-C", str(repository), "show-ref", "--verify", "--quiet", f"refs/heads/{target}"],
            check=False,
        )
        return result.returncode == 0
    if kind in {"worktree", "temp_path"}:
        target_path = Path(target)
        if not target_path.is_absolute():
            target_path = repository / target_path
        if target_path.exists():
            return True
        if kind == "temp_path":
            return False
        result = subprocess.run(
            ["git", "-C", str(repository), "worktree", "list", "--porcelain"],
            check=False,
            capture_output=True,
            text=True,
        )
        registered = {
            Path(line.removeprefix("worktree ")).resolve()
            for line in result.stdout.splitlines()
            if line.startswith("worktree ")
        }
        return target_path.resolve() in registered
    return False
