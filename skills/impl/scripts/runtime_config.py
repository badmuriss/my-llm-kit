#!/usr/bin/env python3
"""Resolve the impl project and operating system from CLI or a local .env file."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence


PROJECT_DIRECTORY_VARIABLE = "IMPL_PROJECT_DIR"
OPERATING_SYSTEM_VARIABLE = "IMPL_OS"
SUPPORTED_OPERATING_SYSTEMS = {"linux", "macos", "windows"}
ENV_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class RuntimeConfigError(ValueError):
    """Reports invalid or contradictory runtime configuration."""


@dataclass(frozen=True)
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
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
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
    selected_env_file = env_file.resolve() if env_file is not None else working_directory / ".env"
    env_values = parse_env_file(selected_env_file) if selected_env_file.is_file() else {}
    merged_environment = {**env_values, **dict(environment or os.environ)}

    configured_os = merged_environment.get(OPERATING_SYSTEM_VARIABLE, "").strip().lower()
    actual_os = detected_operating_system()
    if configured_os and configured_os not in SUPPORTED_OPERATING_SYSTEMS:
        choices = ", ".join(sorted(SUPPORTED_OPERATING_SYSTEMS))
        raise RuntimeConfigError(f"{OPERATING_SYSTEM_VARIABLE} must be one of: {choices}")
    if configured_os and configured_os != actual_os:
        raise RuntimeConfigError(
            f"{OPERATING_SYSTEM_VARIABLE}={configured_os} does not match detected OS {actual_os}"
        )

    configured_project = merged_environment.get(PROJECT_DIRECTORY_VARIABLE, "").strip()
    if project_directory is not None:
        selected_project = project_directory
        project_base = working_directory
    elif configured_project:
        selected_project = Path(configured_project)
        project_base = selected_env_file.parent
    else:
        selected_project = working_directory
        project_base = working_directory
    if not selected_project.is_absolute():
        selected_project = project_base / selected_project
    resolved_project = selected_project.resolve()
    if not resolved_project.is_dir():
        raise RuntimeConfigError(f"project directory does not exist: {resolved_project}")

    return RuntimeConfig(
        project_directory=resolved_project,
        operating_system=actual_os,
        env_file=selected_env_file if selected_env_file.is_file() else None,
    )


def add_runtime_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--repo",
        type=Path,
        help=f"project directory; overrides {PROJECT_DIRECTORY_VARIABLE}",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        help="configuration file; defaults to .env in the current directory",
    )


def runtime_from_arguments(arguments: argparse.Namespace) -> RuntimeConfig:
    return resolve_runtime_config(
        project_directory=arguments.repo,
        env_file=arguments.env_file,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Show the resolved impl runtime configuration.")
    add_runtime_arguments(parser)
    arguments = parser.parse_args(argv)
    try:
        runtime = runtime_from_arguments(arguments)
    except (OSError, RuntimeConfigError) as error:
        print(f"impl-runtime: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "project_directory": str(runtime.project_directory),
                "operating_system": runtime.operating_system,
                "env_file": str(runtime.env_file) if runtime.env_file else None,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
