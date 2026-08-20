#!/usr/bin/env python3
"""Resolve the repository and operating system for Agent Graph commands."""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


PROJECT_DIRECTORY_VARIABLE = "AGENT_GRAPH_PROJECT_DIR"
OPERATING_SYSTEM_VARIABLE = "AGENT_GRAPH_OS"
SUPPORTED_OPERATING_SYSTEMS = frozenset({"linux", "macos", "windows"})
ENV_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class RuntimeConfigError(ValueError):
    """Reports invalid or contradictory runtime configuration."""


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    project_directory: Path
    operating_system: str
    env_file: Path | None


def detected_operating_system() -> str:
    if os.name == "nt" or sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise RuntimeConfigError(f"cannot read environment file {path}: {error}") from error
    for line_number, raw_line in enumerate(lines, 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").lstrip()
        key, separator, raw_value = line.partition("=")
        key = key.strip()
        if not separator or not ENV_KEY_PATTERN.fullmatch(key):
            raise RuntimeConfigError(f"{path}:{line_number}: expected KEY=VALUE")
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def resolve_runtime_config(
    *,
    project_directory: Path | None,
    env_file: Path | None,
    current_directory: Path | None = None,
    environment: Mapping[str, str] | None = None,
) -> RuntimeConfig:
    working_directory = (current_directory or Path.cwd()).resolve()
    selected_env = env_file.resolve() if env_file is not None else working_directory / ".env"
    file_values = parse_env_file(selected_env) if selected_env.is_file() else {}
    values = {**file_values, **dict(environment or os.environ)}

    actual_os = detected_operating_system()
    configured_os = values.get(OPERATING_SYSTEM_VARIABLE, "").strip().casefold()
    if configured_os and configured_os not in SUPPORTED_OPERATING_SYSTEMS:
        choices = ", ".join(sorted(SUPPORTED_OPERATING_SYSTEMS))
        raise RuntimeConfigError(f"{OPERATING_SYSTEM_VARIABLE} must be one of: {choices}")
    if configured_os and configured_os != actual_os:
        raise RuntimeConfigError(
            f"{OPERATING_SYSTEM_VARIABLE}={configured_os} does not match detected OS {actual_os}"
        )

    configured_project = values.get(PROJECT_DIRECTORY_VARIABLE, "").strip()
    if project_directory is not None:
        selected_project = project_directory
        base = working_directory
    elif configured_project:
        selected_project = Path(configured_project)
        base = selected_env.parent
    else:
        selected_project = working_directory
        base = working_directory
    if not selected_project.is_absolute():
        selected_project = base / selected_project
    repository = selected_project.resolve()
    if not repository.is_dir():
        raise RuntimeConfigError(f"project directory does not exist: {repository}")
    return RuntimeConfig(
        project_directory=repository,
        operating_system=actual_os,
        env_file=selected_env if selected_env.is_file() else None,
    )


def add_runtime_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--repo",
        type=Path,
        default=argparse.SUPPRESS,
        help=f"repository root; overrides {PROJECT_DIRECTORY_VARIABLE}",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=argparse.SUPPRESS,
        help="configuration file; defaults to .env in the current directory",
    )


def runtime_from_arguments(arguments: argparse.Namespace) -> RuntimeConfig:
    return resolve_runtime_config(
        project_directory=getattr(arguments, "repo", None),
        env_file=getattr(arguments, "env_file", None),
    )
