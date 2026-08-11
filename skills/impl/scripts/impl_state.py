#!/usr/bin/env python3
"""Persist and reconcile crash-safe state for one OpenSpec implementation run."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

from runtime_config import RuntimeConfigError, add_runtime_arguments, runtime_from_arguments
from visual_evidence import (
    VisualEvidenceError,
    parse_expectation,
    validate_expectation_matrix,
    validate_manifest,
)


SCHEMA_VERSION = 4
MAX_REPAIR_HYPOTHESES = 2
STATE_DIRECTORY = Path("openspec/impl-state")
CHANGE_PATTERN = re.compile(r"^[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*$")
RUN_ID_PATTERN = CHANGE_PATTERN
COMMIT_PATTERN = re.compile(r"^(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$")
TASK_PATTERN = re.compile(
    r"^\s*-\s+\[([ xX])\]\s+((?=[A-Za-z0-9._-]*\d)[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*)\s+(.+?)\s*$"
)
CHECK_PATTERN = re.compile(r"^\s+(?:-\s*)?Check:\s*(.+?)\s*$", re.IGNORECASE)
VISUAL_PATTERN = re.compile(r"^\s+(?:-\s*)?Visual:\s*(.+?)\s*$", re.IGNORECASE)
MISSING_CHECK_MARKER = "missing validation evidence"
TASK_STATUSES = {"pending", "running", "interrupted", "pass", "fail", "unobserved", "blocked"}
UPDATE_TASK_STATUSES = TASK_STATUSES - {"interrupted"}
CHECK_STATUSES = {"pending", "passed", "failed", "unobserved"}
CLEANUP_KINDS = {"process", "worktree", "branch", "temp_path", "other"}
CLEANUP_STATUSES = {"pending", "done"}
RUN_STATUSES = {"active", "complete"}
OUTCOMES = {"pass", "partial", "blocked"}


class StateError(ValueError):
    """Reports invalid impl state or an unsafe transition."""


def now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as temporary_file:
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
        os.chmod(temporary_name, mode)
        os.replace(temporary_name, path)
        if hasattr(os, "O_DIRECTORY"):
            directory_descriptor = os.open(path.parent, os.O_DIRECTORY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def require_change(change: str) -> str:
    if not CHANGE_PATTERN.fullmatch(change):
        raise StateError("change must be one OpenSpec slug without path separators")
    return change


def state_path(repo: Path, change: str) -> Path:
    return repo / STATE_DIRECTORY / f"{require_change(change)}.json"


def current_commit(repo: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "unborn"


def dirty_paths(repo: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [line[3:] for line in result.stdout.splitlines() if len(line) > 3]


FRONTEND_SUFFIXES = {
    ".astro",
    ".avif",
    ".css",
    ".gif",
    ".html",
    ".jpeg",
    ".jpg",
    ".jsx",
    ".less",
    ".mdx",
    ".png",
    ".sass",
    ".scss",
    ".svelte",
    ".svg",
    ".tsx",
    ".vue",
    ".webp",
}


def changed_paths_since(repo: Path, base_commit: str) -> list[str]:
    paths: set[str] = set()
    commands = [
        ["git", "-C", str(repo), "diff", "--name-only", base_commit],
        ["git", "-C", str(repo), "ls-files", "--others", "--exclude-standard"],
    ]
    for command in commands:
        result = subprocess.run(command, check=False, capture_output=True, text=True)
        if result.returncode == 0:
            paths.update(line.strip() for line in result.stdout.splitlines() if line.strip())
    return sorted(paths)


def frontend_paths(paths: Sequence[str]) -> list[str]:
    return sorted(path for path in paths if Path(path).suffix.casefold() in FRONTEND_SUFFIXES)


def validate_external_evidence_ref(repo: Path, reference: str, context: str) -> None:
    kind, separator, target = reference.partition(":")
    if not separator or kind not in {"file", "commit"} or not target.strip():
        raise StateError(f"{context} evidence must use file: or commit:")
    target = target.strip()
    if kind == "file":
        relative_path = Path(target)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise StateError(f"{context} file evidence must stay inside the repository")
        root = repo.resolve()
        evidence_path = (root / relative_path).resolve()
        try:
            evidence_path.relative_to(root)
        except ValueError as error:
            raise StateError(
                f"{context} file evidence must stay inside the repository"
            ) from error
        if not evidence_path.is_file():
            raise StateError(f"{context} evidence file does not exist: {target}")
        return
    if not COMMIT_PATTERN.fullmatch(target):
        raise StateError(f"{context} commit evidence must use a full immutable SHA")
    result = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", f"{target}^{{commit}}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise StateError(f"{context} evidence commit does not exist: {target}")


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


def parse_pending_tasks(tasks_file: Path) -> list[dict[str, Any]]:
    if not tasks_file.is_file():
        raise StateError(f"tasks file does not exist: {tasks_file}")
    lines = tasks_file.read_text(encoding="utf-8").splitlines()
    tasks: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        line_number = index + 1
        if not re.match(r"^\s*-\s+\[[ xX]\]", line):
            continue
        match = TASK_PATTERN.fullmatch(line)
        if not match:
            raise StateError(f"{tasks_file}:{line_number}: task needs a stable leading id")
        checked, task_id, text = match.groups()
        if checked.lower() == "x":
            continue
        block_end = len(lines)
        for candidate_index in range(index + 1, len(lines)):
            if re.match(r"^\s*-\s+\[[ xX]\]", lines[candidate_index]):
                block_end = candidate_index
                break
        checks = [
            check_match.group(1).strip()
            for candidate in lines[index + 1 : block_end]
            if (check_match := CHECK_PATTERN.fullmatch(candidate))
        ]
        if len(checks) != 1:
            raise StateError(
                f"{tasks_file}:{line_number}: task {task_id} needs exactly one Check: line"
            )
        command = None if checks[0].casefold() == MISSING_CHECK_MARKER else checks[0]
        visual_expectations = [
            visual_match.group(1).strip()
            for candidate in lines[index + 1 : block_end]
            if (visual_match := VISUAL_PATTERN.fullmatch(candidate))
        ]
        if len(visual_expectations) != len(set(visual_expectations)):
            raise StateError(
                f"{tasks_file}:{line_number}: task {task_id} has duplicate Visual entries"
            )
        for expectation in visual_expectations:
            try:
                parse_expectation(expectation)
            except VisualEvidenceError as error:
                raise StateError(
                    f"{tasks_file}:{line_number}: task {task_id} has invalid Visual entry: {error}"
                ) from error
        if visual_expectations:
            try:
                validate_expectation_matrix(visual_expectations)
            except VisualEvidenceError as error:
                raise StateError(
                    f"{tasks_file}:{line_number}: task {task_id} has incomplete Visual coverage: "
                    f"{error}"
                ) from error
        tasks.append(
            {
                "id": task_id,
                "text": text,
                "status": "pending",
                "worker": None,
                "hypotheses": [],
                "evidence_refs": [],
                "visual_expectations": visual_expectations,
                "check": {
                    "command": command,
                    "status": "unobserved" if command is None else "pending",
                    "exit_code": None,
                    "duration_ms": None,
                    "total_duration_ms": 0,
                    "attempts": 0,
                },
                "note": "",
            }
        )
    task_ids = [task["id"] for task in tasks]
    if len(task_ids) != len(set(task_ids)):
        raise StateError(f"{tasks_file} contains duplicate task ids")
    if not tasks:
        raise StateError("no unchecked tasks remain; stop instead of inventing work")
    return tasks


def validate_state(state: Any, path: Path) -> dict[str, Any]:
    if not isinstance(state, dict):
        raise StateError(f"{path} must contain an object")
    required = {
        "schema_version",
        "change",
        "run_id",
        "status",
        "outcome",
        "started_at",
        "updated_at",
        "base_commit",
        "last_observed_commit",
        "tasks",
        "cleanup",
        "digest",
    }
    if state.keys() != required:
        missing = required - state.keys()
        unknown = state.keys() - required
        details = []
        if missing:
            details.append(f"missing {', '.join(sorted(missing))}")
        if unknown:
            details.append(f"unknown {', '.join(sorted(unknown))}")
        raise StateError(f"{path}: {'; '.join(details)}")
    if state["schema_version"] != SCHEMA_VERSION:
        raise StateError(f"{path}: schema_version must be {SCHEMA_VERSION}")
    require_change(state["change"])
    if not isinstance(state["run_id"], str) or not RUN_ID_PATTERN.fullmatch(state["run_id"]):
        raise StateError(f"{path}: run_id must be safe for use as a filename")
    if state["status"] not in RUN_STATUSES:
        raise StateError(f"{path}: invalid run status")
    if state["outcome"] is not None and state["outcome"] not in OUTCOMES:
        raise StateError(f"{path}: invalid outcome")
    if state["status"] == "active" and state["outcome"] is not None:
        raise StateError(f"{path}: active state cannot have an outcome")
    if state["status"] == "complete" and state["outcome"] is None:
        raise StateError(f"{path}: complete state requires an outcome")
    for field in ("started_at", "updated_at", "base_commit", "last_observed_commit"):
        if not isinstance(state[field], str) or not state[field].strip():
            raise StateError(f"{path}: {field} must be a non-empty string")
    if not isinstance(state["tasks"], list) or not isinstance(state["cleanup"], list):
        raise StateError(f"{path}: tasks and cleanup must be arrays")
    if not isinstance(state["digest"], list) or not all(
        isinstance(entry, str) and entry.strip() for entry in state["digest"]
    ):
        raise StateError(f"{path}: digest must contain non-empty strings")

    task_ids: list[str] = []
    for task in state["tasks"]:
        if not isinstance(task, dict) or task.keys() != {
            "id",
            "text",
            "status",
            "worker",
            "hypotheses",
            "evidence_refs",
            "visual_expectations",
            "check",
            "note",
        }:
            raise StateError(f"{path}: invalid task entry")
        if task["status"] not in TASK_STATUSES:
            raise StateError(f"{path}: invalid status for task {task.get('id')}")
        if not isinstance(task["id"], str) or not task["id"].strip():
            raise StateError(f"{path}: task id must be a non-empty string")
        if not isinstance(task["text"], str) or not task["text"].strip():
            raise StateError(f"{path}: task text must be a non-empty string")
        if task["worker"] is not None and (
            not isinstance(task["worker"], str) or not task["worker"].strip()
        ):
            raise StateError(f"{path}: task worker must be null or a non-empty string")
        if not isinstance(task["note"], str):
            raise StateError(f"{path}: task note must be a string")
        if not isinstance(task["hypotheses"], list) or not all(
            isinstance(entry, str) and entry.strip() for entry in task["hypotheses"]
        ):
            raise StateError(f"{path}: invalid hypotheses for task {task.get('id')}")
        if len(task["hypotheses"]) > MAX_REPAIR_HYPOTHESES or len(
            task["hypotheses"]
        ) != len(
            set(task["hypotheses"])
        ):
            raise StateError(f"{path}: task hypotheses must be distinct and capped at two")
        if not isinstance(task["evidence_refs"], list) or not all(
            isinstance(entry, str) and entry.strip() for entry in task["evidence_refs"]
        ):
            raise StateError(f"{path}: invalid arrays for task {task.get('id')}")
        if len(task["evidence_refs"]) != len(set(task["evidence_refs"])):
            raise StateError(f"{path}: duplicate evidence refs for task {task.get('id')}")
        if not isinstance(task["visual_expectations"], list) or not all(
            isinstance(entry, str) and entry.strip() for entry in task["visual_expectations"]
        ):
            raise StateError(f"{path}: invalid visual expectations for task {task.get('id')}")
        if len(task["visual_expectations"]) != len(set(task["visual_expectations"])):
            raise StateError(f"{path}: duplicate visual expectations for task {task.get('id')}")
        for expectation in task["visual_expectations"]:
            try:
                parse_expectation(expectation)
            except VisualEvidenceError as error:
                raise StateError(
                    f"{path}: invalid visual expectation for task {task.get('id')}: {error}"
                ) from error
        if task["visual_expectations"]:
            try:
                validate_expectation_matrix(task["visual_expectations"])
            except VisualEvidenceError as error:
                raise StateError(
                    f"{path}: incomplete visual coverage for task {task.get('id')}: {error}"
                ) from error
        check = task["check"]
        if not isinstance(check, dict) or check.keys() != {
            "command",
            "status",
            "exit_code",
            "duration_ms",
            "total_duration_ms",
            "attempts",
        }:
            raise StateError(f"{path}: invalid check for task {task.get('id')}")
        if check["command"] is not None and (
            not isinstance(check["command"], str) or not check["command"].strip()
        ):
            raise StateError(f"{path}: task check command must be null or non-empty")
        if check["status"] not in CHECK_STATUSES:
            raise StateError(f"{path}: invalid check status for task {task.get('id')}")
        if not isinstance(check["attempts"], int) or check["attempts"] < 0:
            raise StateError(f"{path}: invalid check attempts for task {task.get('id')}")
        if check["exit_code"] is not None and not isinstance(check["exit_code"], int):
            raise StateError(f"{path}: invalid check exit code for task {task.get('id')}")
        if check["duration_ms"] is not None and (
            not isinstance(check["duration_ms"], int) or check["duration_ms"] < 0
        ):
            raise StateError(f"{path}: invalid check duration for task {task.get('id')}")
        if not isinstance(check["total_duration_ms"], int) or check["total_duration_ms"] < 0:
            raise StateError(f"{path}: invalid total check duration for task {task.get('id')}")
        if check["command"] is None and check["status"] != "unobserved":
            raise StateError(f"{path}: missing check must stay unobserved")
        if check["status"] == "pending" and (
            check["attempts"] != 0
            or check["exit_code"] is not None
            or check["duration_ms"] is not None
            or check["total_duration_ms"] != 0
        ):
            raise StateError(f"{path}: pending check cannot contain a result")
        if check["status"] == "passed" and (
            check["attempts"] < 1 or check["exit_code"] != 0
        ):
            raise StateError(f"{path}: passed check requires a zero exit code")
        if check["status"] == "failed" and check["attempts"] < 1:
            raise StateError(f"{path}: failed check requires an attempt")
        if task["status"] == "running" and task["worker"] is None:
            raise StateError(f"{path}: running task {task['id']} requires a worker")
        if task["status"] == "pass" and check["status"] != "passed":
            raise StateError(f"{path}: task {task['id']} cannot pass without a passed check")
        if task["status"] == "fail" and check["status"] != "failed":
            raise StateError(f"{path}: task {task['id']} cannot fail without a failed check")
        if task["status"] in {"pass", "fail", "unobserved", "blocked"} and not task[
            "note"
        ].strip():
            raise StateError(f"{path}: final task {task['id']} requires a note")
        task_ids.append(task["id"])
    if len(task_ids) != len(set(task_ids)):
        raise StateError(f"{path}: duplicate task ids")

    cleanup_targets: list[str] = []
    for obligation in state["cleanup"]:
        if not isinstance(obligation, dict) or obligation.keys() != {
            "kind",
            "target",
            "owner",
            "status",
        }:
            raise StateError(f"{path}: invalid cleanup entry")
        if obligation["kind"] not in CLEANUP_KINDS or obligation["status"] not in CLEANUP_STATUSES:
            raise StateError(f"{path}: invalid cleanup kind or status")
        for field in ("target", "owner"):
            if not isinstance(obligation[field], str) or not obligation[field].strip():
                raise StateError(f"{path}: cleanup {field} must be a non-empty string")
        if obligation["kind"] == "process" and not obligation["target"].isdigit():
            raise StateError(f"{path}: process cleanup target must be a PID")
        cleanup_targets.append(obligation["target"])
    if len(cleanup_targets) != len(set(cleanup_targets)):
        raise StateError(f"{path}: duplicate cleanup targets")
    return state


def load_state(repo: Path, change: str) -> tuple[Path, dict[str, Any]]:
    path = state_path(repo, change)
    if not path.is_file():
        raise StateError(f"state does not exist: {path}")
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise StateError(f"{path}: invalid JSON: {error.msg}") from error
    validated = validate_state(state, path)
    for task in validated["tasks"]:
        for reference in task["evidence_refs"]:
            validate_external_evidence_ref(repo, reference, f"task {task['id']}")
        if task["status"] == "pass" and task["visual_expectations"]:
            validate_task_visual_evidence(repo, validated["change"], task)
    return path, validated


def save_state(path: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = now()
    validate_state(state, path)
    atomic_write_text(path, json.dumps(state, indent=2) + "\n")


def find_task(state: dict[str, Any], task_id: str) -> dict[str, Any]:
    for task in state["tasks"]:
        if task["id"] == task_id:
            return task
    raise StateError(f"unknown task: {task_id}")


def validate_task_visual_evidence(repo: Path, change: str, task: dict[str, Any]) -> None:
    errors: list[str] = []
    for reference in task["evidence_refs"]:
        kind, _, target = reference.partition(":")
        if kind != "file" or not target.casefold().endswith(".json"):
            continue
        manifest_path = repo / target
        try:
            validate_manifest(
                repo,
                manifest_path,
                change,
                task["id"],
                task["visual_expectations"],
            )
            return
        except VisualEvidenceError as error:
            errors.append(f"{target}: {error}")
    details = f" ({'; '.join(errors)})" if errors else ""
    raise StateError(
        f"task {task['id']} requires a valid vision-reviewed manifest in --evidence-ref{details}"
    )


def command_init(arguments: argparse.Namespace) -> dict[str, Any]:
    repo = arguments.repo.resolve()
    path = state_path(repo, arguments.change)
    if path.exists():
        _, existing = load_state(repo, arguments.change)
        if existing["status"] == "active":
            raise StateError(f"active state already exists: {path}; resume it")
    tasks_file = repo / "openspec" / "changes" / arguments.change / "tasks.md"
    commit = current_commit(repo)
    timestamp = now()
    state = {
        "schema_version": SCHEMA_VERSION,
        "change": arguments.change,
        "run_id": arguments.run_id,
        "status": "active",
        "outcome": None,
        "started_at": timestamp,
        "updated_at": timestamp,
        "base_commit": commit,
        "last_observed_commit": commit,
        "tasks": parse_pending_tasks(tasks_file),
        "cleanup": [],
        "digest": [],
    }
    save_state(path, state)
    return state


def command_update_task(arguments: argparse.Namespace) -> dict[str, Any]:
    repo = arguments.repo.resolve()
    path, state = load_state(repo, arguments.change)
    if state["status"] != "active":
        raise StateError("cannot update a completed run")
    task = find_task(state, arguments.task)
    if arguments.hypothesis:
        if arguments.hypothesis in task["hypotheses"]:
            raise StateError("repair hypotheses must be distinct")
        if len(task["hypotheses"]) >= MAX_REPAIR_HYPOTHESES:
            raise StateError("repair hypothesis cap reached; grade the task blocked")
        task["hypotheses"].append(arguments.hypothesis)
    for reference in arguments.evidence_ref:
        validate_external_evidence_ref(repo, reference, f"task {arguments.task}")
        if reference not in task["evidence_refs"]:
            task["evidence_refs"].append(reference)
    if arguments.status == "running" and not arguments.worker:
        raise StateError("running tasks require --worker")
    if arguments.status == "pass" and task["check"]["status"] != "passed":
        raise StateError("status pass requires a recorded passing check")
    if arguments.status == "pass" and task["visual_expectations"]:
        validate_task_visual_evidence(repo, state["change"], task)
    if arguments.status == "fail" and task["check"]["status"] != "failed":
        raise StateError("status fail requires a recorded failed check")
    if arguments.status in {"pass", "fail", "unobserved", "blocked"} and not arguments.note:
        raise StateError(f"status {arguments.status} requires --note")
    task["status"] = arguments.status
    if arguments.worker:
        task["worker"] = arguments.worker
    if arguments.note:
        task["note"] = arguments.note
    if arguments.status in {"pending", "pass", "fail", "unobserved", "blocked"}:
        task["worker"] = None
    state["last_observed_commit"] = current_commit(repo)
    save_state(path, state)
    return state


def command_run_check(arguments: argparse.Namespace) -> dict[str, Any]:
    repo = arguments.repo.resolve()
    path, state = load_state(repo, arguments.change)
    if state["status"] != "active":
        raise StateError("cannot run a check for a completed run")
    task = find_task(state, arguments.task)
    check = task["check"]
    command = check["command"]
    if command is None:
        raise StateError(
            f"task {arguments.task} has Check: {MISSING_CHECK_MARKER}; grade it unobserved"
        )
    if task["status"] in {"pass", "fail", "unobserved", "blocked"}:
        task["status"] = "pending"
        task["worker"] = None
        task["note"] = ""

    started = time.monotonic()
    try:
        command_arguments: str | list[str]
        if os.name == "nt":
            command_arguments = command
        else:
            command_arguments = shlex.split(command)
            if not command_arguments:
                raise StateError(f"task {arguments.task} check command is empty")
            shell_operators = {"&&", "||", "|", ";", "<", ">"}
            if any(argument in shell_operators for argument in command_arguments):
                raise StateError(
                    f"task {arguments.task} check uses shell operators; move it into a reviewed script"
                )
        result = subprocess.run(
            command_arguments,
            cwd=repo,
            shell=False,
            check=False,
        )
        exit_code = result.returncode
    except ValueError as error:
        raise StateError(f"task {arguments.task} check has invalid quoting: {error}") from error
    except OSError as error:
        exit_code = 127
        check["attempts"] += 1
        check["exit_code"] = exit_code
        duration_ms = round((time.monotonic() - started) * 1000)
        check["duration_ms"] = duration_ms
        check["total_duration_ms"] += duration_ms
        check["status"] = "failed"
        save_state(path, state)
        raise StateError(f"task {arguments.task} check could not start: {error}") from error
    check["attempts"] += 1
    check["exit_code"] = exit_code
    duration_ms = round((time.monotonic() - started) * 1000)
    check["duration_ms"] = duration_ms
    check["total_duration_ms"] += duration_ms
    check["status"] = "passed" if exit_code == 0 else "failed"
    state["last_observed_commit"] = current_commit(repo)
    save_state(path, state)

    if exit_code != 0:
        raise StateError(f"task {arguments.task} check failed with exit code {exit_code}")
    return {
        "change": state["change"],
        "task": task["id"],
        "check": check,
    }


def command_add_cleanup(arguments: argparse.Namespace) -> dict[str, Any]:
    path, state = load_state(arguments.repo.resolve(), arguments.change)
    if state["status"] != "active":
        raise StateError("cannot add cleanup to a completed run")
    if any(entry["target"] == arguments.target for entry in state["cleanup"]):
        raise StateError(f"cleanup target already exists: {arguments.target}")
    state["cleanup"].append(
        {
            "kind": arguments.kind,
            "target": arguments.target,
            "owner": arguments.owner,
            "status": "pending",
        }
    )
    save_state(path, state)
    return state


def cleanup_still_exists(repo: Path, obligation: dict[str, str]) -> bool:
    kind = obligation["kind"]
    target = obligation["target"]
    if kind == "process":
        return process_exists(target)
    if kind == "branch":
        result = subprocess.run(
            ["git", "-C", str(repo), "show-ref", "--verify", "--quiet", f"refs/heads/{target}"],
            check=False,
        )
        return result.returncode == 0
    if kind in {"worktree", "temp_path"}:
        target_path = Path(target)
        if not target_path.is_absolute():
            target_path = repo / target_path
        if target_path.exists():
            return True
        if kind == "temp_path":
            return False
        result = subprocess.run(
            ["git", "-C", str(repo), "worktree", "list", "--porcelain"],
            check=False,
            capture_output=True,
            text=True,
        )
        registered_paths = [
            Path(line.removeprefix("worktree ")).resolve()
            for line in result.stdout.splitlines()
            if line.startswith("worktree ")
        ]
        return target_path.resolve() in registered_paths
    return False


def command_finish_cleanup(arguments: argparse.Namespace) -> dict[str, Any]:
    repo = arguments.repo.resolve()
    path, state = load_state(repo, arguments.change)
    if state["status"] != "active":
        raise StateError("cannot update cleanup on a completed run")
    for obligation in state["cleanup"]:
        if obligation["target"] == arguments.target:
            if cleanup_still_exists(repo, obligation):
                raise StateError(f"cleanup target still exists: {arguments.target}")
            obligation["status"] = "done"
            save_state(path, state)
            return state
    raise StateError(f"unknown cleanup target: {arguments.target}")


def command_digest(arguments: argparse.Namespace) -> dict[str, Any]:
    path, state = load_state(arguments.repo.resolve(), arguments.change)
    if state["status"] != "active":
        raise StateError("cannot update the digest on a completed run")
    state["digest"].append(arguments.entry)
    save_state(path, state)
    return state


def command_resume(arguments: argparse.Namespace) -> dict[str, Any]:
    repo = arguments.repo.resolve()
    path, state = load_state(repo, arguments.change)
    if state["status"] != "active":
        raise StateError("cannot resume a completed run")
    interrupted: list[str] = []
    for task in state["tasks"]:
        if task["status"] != "running":
            continue
        task["status"] = "interrupted"
        task["worker"] = None
        task["note"] = "Interrupted before evidence was reconciled."
        interrupted.append(task["id"])
    recorded_commit = state["last_observed_commit"]
    observed_commit = current_commit(repo)
    state["last_observed_commit"] = observed_commit
    save_state(path, state)
    process_status = []
    for obligation in state["cleanup"]:
        if obligation["kind"] != "process" or obligation["status"] != "pending":
            continue
        target = obligation["target"]
        process_status.append(
            {"target": target, "alive": process_exists(target)}
        )
    return {
        "change": state["change"],
        "run_id": state["run_id"],
        "interrupted_tasks": interrupted,
        "recorded_commit": recorded_commit,
        "observed_commit": observed_commit,
        "head_changed": recorded_commit != observed_commit,
        "dirty_paths": dirty_paths(repo),
        "pending_cleanup": [
            entry for entry in state["cleanup"] if entry["status"] == "pending"
        ],
        "process_status": process_status,
        "instruction": (
            "Inspect diffs and listed processes before dispatching or restarting commands."
        ),
    }


def command_complete(arguments: argparse.Namespace) -> dict[str, Any]:
    repo = arguments.repo.resolve()
    path, state = load_state(repo, arguments.change)
    unstable = [
        task["id"]
        for task in state["tasks"]
        if task["status"] in {"running", "interrupted"}
    ]
    if unstable:
        raise StateError(f"reconcile running or interrupted tasks first: {', '.join(unstable)}")
    pending_cleanup = [
        entry["target"] for entry in state["cleanup"] if entry["status"] == "pending"
    ]
    if pending_cleanup:
        raise StateError(f"finish cleanup first: {', '.join(pending_cleanup)}")
    if arguments.outcome == "pass":
        not_passed = [task["id"] for task in state["tasks"] if task["status"] != "pass"]
        if not_passed:
            raise StateError(f"pass outcome requires every task to pass: {', '.join(not_passed)}")
        changed_frontend = frontend_paths(changed_paths_since(repo, state["base_commit"]))
        if changed_frontend and not any(task["visual_expectations"] for task in state["tasks"]):
            raise StateError(
                "frontend changes require Visual entries and vision-reviewed evidence: "
                + ", ".join(changed_frontend)
            )
    state["status"] = "complete"
    state["outcome"] = arguments.outcome
    state["last_observed_commit"] = current_commit(repo)
    save_state(path, state)
    return state


def command_show(arguments: argparse.Namespace) -> dict[str, Any]:
    _, state = load_state(arguments.repo.resolve(), arguments.change)
    return state


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage crash-safe impl run state.")
    add_runtime_arguments(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--change", required=True)
    init_parser.add_argument("--run-id", required=True)
    init_parser.set_defaults(handler=command_init)

    update_parser = subparsers.add_parser("update-task")
    update_parser.add_argument("--change", required=True)
    update_parser.add_argument("--task", required=True)
    update_parser.add_argument("--status", choices=sorted(UPDATE_TASK_STATUSES), required=True)
    update_parser.add_argument("--worker")
    update_parser.add_argument("--hypothesis")
    update_parser.add_argument("--evidence-ref", action="append", default=[])
    update_parser.add_argument("--note")
    update_parser.set_defaults(handler=command_update_task)

    check_parser = subparsers.add_parser("run-check")
    check_parser.add_argument("--change", required=True)
    check_parser.add_argument("--task", required=True)
    check_parser.set_defaults(handler=command_run_check)

    cleanup_parser = subparsers.add_parser("add-cleanup")
    cleanup_parser.add_argument("--change", required=True)
    cleanup_parser.add_argument("--kind", choices=sorted(CLEANUP_KINDS), required=True)
    cleanup_parser.add_argument("--target", required=True)
    cleanup_parser.add_argument("--owner", required=True)
    cleanup_parser.set_defaults(handler=command_add_cleanup)

    finish_parser = subparsers.add_parser("finish-cleanup")
    finish_parser.add_argument("--change", required=True)
    finish_parser.add_argument("--target", required=True)
    finish_parser.set_defaults(handler=command_finish_cleanup)

    digest_parser = subparsers.add_parser("digest")
    digest_parser.add_argument("--change", required=True)
    digest_parser.add_argument("--entry", required=True)
    digest_parser.set_defaults(handler=command_digest)

    resume_parser = subparsers.add_parser("resume")
    resume_parser.add_argument("--change", required=True)
    resume_parser.set_defaults(handler=command_resume)

    complete_parser = subparsers.add_parser("complete")
    complete_parser.add_argument("--change", required=True)
    complete_parser.add_argument("--outcome", choices=sorted(OUTCOMES), required=True)
    complete_parser.set_defaults(handler=command_complete)

    show_parser = subparsers.add_parser("show")
    show_parser.add_argument("--change", required=True)
    show_parser.set_defaults(handler=command_show)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        arguments.repo = runtime_from_arguments(arguments).project_directory
        result = arguments.handler(arguments)
        print(json.dumps(result, indent=2))
    except (RuntimeConfigError, StateError, OSError) as error:
        print(f"impl-state: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
