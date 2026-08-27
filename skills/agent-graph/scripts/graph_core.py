#!/usr/bin/env python3
"""Parse task graphs and maintain their canonical event journal."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence


SCRIPTS_DIRECTORY = Path(__file__).resolve().parent
if str(SCRIPTS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIRECTORY))


from browser_surfaces import (
    BrowserSurfaceError,
    validate_browser_surface_request,
    validate_receipt_for_request,
    visible_paint_proven,
)


SCHEMA_VERSION = 1
TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*$")
TASK_HEADER_PATTERN = re.compile(
    r"^\s*-\s+\[([ xX])\]\s+"
    r"([A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*)\s+(.+?)\s*$"
)
FIELD_PATTERN = re.compile(r"^\s+(?:-\s*)?([A-Za-z][A-Za-z-]*):\s*(.*?)\s*$")
EVENT_ID_PATTERN = re.compile(r"^event-[0-9]{6,}$")
COMMIT_PATTERN = re.compile(r"^(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$")
HOST_RUN_REPOSITORY_PATTERN = re.compile(
    r"^host-run-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
MODES = frozenset({"read", "write"})
ISOLATIONS = frozenset({"auto", "worktree"})
GRADES = frozenset({"pass", "fail", "unobserved", "blocked"})
REQUIRED_TASK_FIELDS = frozenset(
    {"depends", "paths", "mode", "isolation", "acceptance", "check"}
)
REPEATED_TASK_FIELDS = frozenset({"visual", "visual-scope"})
CORE_EVENT_TYPES = frozenset(
    {
        "run_started",
        "coordinator_claimed",
        "coordinator_transferred",
        "coordinator_taken_over",
        "driver_selected",
        "driver_selection_reserved",
        "driver_selection_failed",
        "task_ready",
        "attempt_reserved",
        "attempt_scope_frozen",
        "attempt_started",
        "attempt_observed",
        "attempt_start_failed",
        "attempt_abandoned",
        "attempt_provider_result_rejected",
        "attempt_result_quarantined",
        "driver_degraded",
        "delegation_requested",
        "delegation_approved",
        "delegation_rejected",
        "delegation_started",
        "delegation_reported",
        "delegation_released",
        "graph_amended",
        "process_decision_amended",
        "question_opened",
        "question_answered",
        "worker_reported",
        "attempt_check_rejected",
        "attempt_audit_rejected",
        "attempt_audit_exhausted",
        "finding_recorded",
        "coordinator_decision_recorded",
        "checked_task_imported",
        "check_execution_recorded",
        "check_execution_recovered",
        "check_recorded",
        "repair_recorded",
        "task_graded",
        "cleanup_registered",
        "cleanup_finished",
        "cleanup_unverifiable",
        "cleanup_retained",
        "journal_repaired",
        "run_completed",
        "browser_surface_requested",
        "browser_surface_receipt",
        "browser_surface_observed",
        "browser_surface_captured",
        "browser_surface_released",
    }
)
EFFORTS = frozenset({"low", "medium", "high", "xhigh"})
PLACEMENT_KINDS = frozenset(
    {"current-workspace", "existing-workspace", "create-child-worktree"}
)
WORKSPACE_KINDS = frozenset({"folder", "git-worktree"})
WORKSPACE_AUTHORITY_KINDS = frozenset({"host-run", "orca"})
TERMINAL_CLEANUP_STATUSES = frozenset({"done", "verified", "retained"})
NODE_TYPES = frozenset(
    {
        "task",
        "attempt",
        "note-reference",
        "evidence",
        "browser-surface",
    }
)
EDGE_TYPES = frozenset(
    {
        "depends_on",
        "context_for",
        "spawned_by",
        "reports_to",
        "produces",
        "uses",
    }
)
TRANSCRIPT_FIELDS = frozenset(
    {"conversation", "messages", "prompt", "terminal_output", "transcript"}
)
BROWSER_CONTENT_FIELDS = frozenset(
    {
        "accessibility_tree",
        "authorization",
        "authorization_data",
        "cookie",
        "cookies",
        "dom",
        "frame",
        "frames",
        "html",
        "live_frame",
        "screenshot",
        "screenshot_bytes",
        "storage",
    }
)


class GraphError(ValueError):
    """Base error for an invalid graph or unsafe state transition."""


class GraphValidationError(GraphError):
    """Reports an invalid task or structured graph artifact."""


class JournalError(GraphError):
    """Reports journal corruption or an invalid event."""


class StaleCoordinatorError(JournalError):
    """Reports a mutation from a fenced coordinator generation."""


class StaleRevisionError(JournalError):
    """Reports a mutation based on a journal revision that has moved."""


class TaskNotReadyError(JournalError):
    """Reports a checked import whose declared dependencies are not passing."""

    code = "task_not_ready"


@dataclass(frozen=True, slots=True)
class TaskContract:
    """One validated task from an OpenSpec task graph."""

    id: str
    title: str
    depends: tuple[str, ...]
    paths: tuple[str, ...]
    mode: str
    isolation: str
    acceptance: str
    check: str
    context: str = ""
    visual: tuple[str, ...] = ()
    visual_scope: tuple[str, ...] = ()
    checked: bool = False
    source_line: int = 0

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["depends"] = list(self.depends)
        result["paths"] = list(self.paths)
        result["visual"] = list(self.visual)
        result["visual_scope"] = list(self.visual_scope)
        return result


@dataclass(frozen=True, slots=True)
class TaskGraph:
    """A validated, document-ordered directed acyclic task graph."""

    tasks: tuple[TaskContract, ...]

    def by_id(self) -> dict[str, TaskContract]:
        return {task.id: task for task in self.tasks}

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": SCHEMA_VERSION, "tasks": [task.to_dict() for task in self.tasks]}


def _nonempty_string(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GraphValidationError(f"{context} must be a non-empty string")
    return value.strip()


def _identifier(value: Any, context: str) -> str:
    identifier = _nonempty_string(value, context)
    if not TASK_ID_PATTERN.fullmatch(identifier):
        raise GraphValidationError(f"{context} is invalid")
    return identifier


def _workspace_key(value: Any, context: str) -> str:
    key = _nonempty_string(value, context)
    if len(key.encode("utf-8")) > 4096 or any(ord(character) < 32 for character in key):
        raise GraphValidationError(f"{context} must be a bounded opaque identity")
    return key


def _exact_fields(
    value: Any,
    required: set[str] | frozenset[str],
    optional: set[str] | frozenset[str],
    context: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise GraphValidationError(f"{context} must be an object")
    unknown = sorted(set(value) - required - optional)
    missing = sorted(required - set(value))
    if unknown:
        raise GraphValidationError(f"{context} has unknown fields: {', '.join(unknown)}")
    if missing:
        raise GraphValidationError(f"{context} is missing fields: {', '.join(missing)}")
    return value


def _absolute_path(value: Any, context: str) -> str:
    path = _nonempty_string(value, context)
    if not (path.startswith("/") or re.match(r"^[A-Za-z]:[\\/].+", path)):
        raise GraphValidationError(f"{context} must be absolute")
    return path


def _reject_transcript_fields(value: Any, context: str) -> None:
    if isinstance(value, Mapping):
        forbidden = sorted(
            key for key in value if isinstance(key, str) and key.casefold() in TRANSCRIPT_FIELDS
        )
        if forbidden:
            raise GraphValidationError(
                f"{context} contains transcript fields: {', '.join(forbidden)}"
            )
        for key, item in value.items():
            _reject_transcript_fields(item, f"{context}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_transcript_fields(item, f"{context}[{index}]")


def _parse_list(value: str, context: str, *, allow_empty: bool) -> tuple[str, ...]:
    if not value.startswith("[") or not value.endswith("]"):
        raise GraphValidationError(f"{context} must use [item, item] syntax")
    body = value[1:-1].strip()
    if not body:
        if allow_empty:
            return ()
        raise GraphValidationError(f"{context} must contain at least one item")
    items = tuple(item.strip() for item in body.split(","))
    if any(not item for item in items):
        raise GraphValidationError(f"{context} contains an empty item")
    if len(set(items)) != len(items):
        raise GraphValidationError(f"{context} contains a duplicate item")
    return items


def normalize_repo_path(value: str, context: str = "path") -> str:
    """Validate and return one normalized repository-relative path scope."""

    path = _nonempty_string(value, context)
    if "\\" in path:
        raise GraphValidationError(f"{context} must use forward slashes")
    if path.startswith("/") or re.match(r"^[A-Za-z]:", path):
        raise GraphValidationError(f"{context} must be repository-relative")
    if any(character in path for character in "*?[]{}"):
        raise GraphValidationError(f"{context} must use a file or directory prefix, not a glob")
    directory = path.endswith("/")
    body = path[:-1] if directory else path
    if not body or "//" in body:
        raise GraphValidationError(f"{context} is not normalized")
    parts = PurePosixPath(body).parts
    if any(part in {"", ".", ".."} for part in parts):
        raise GraphValidationError(f"{context} cannot contain . or .. segments")
    normalized = PurePosixPath(*parts).as_posix()
    if normalized != body:
        raise GraphValidationError(f"{context} is not normalized")
    return normalized + ("/" if directory else "")


def _parse_task_block(
    path: Path,
    line_number: int,
    header: re.Match[str],
    block: Sequence[str],
) -> TaskContract:
    checked, task_id, title = header.groups()
    values: dict[str, str] = {}
    repeated: dict[str, list[str]] = {name: [] for name in REPEATED_TASK_FIELDS}
    for offset, line in enumerate(block, start=1):
        if not line.strip():
            continue
        match = FIELD_PATTERN.fullmatch(line)
        if not match:
            raise GraphValidationError(
                f"{path}:{line_number + offset}: task {task_id} has an invalid field line"
            )
        name, value = match.groups()
        name = name.casefold()
        if name in REPEATED_TASK_FIELDS:
            repeated[name].append(_nonempty_string(value, f"task {task_id} {name}"))
            continue
        if name not in REQUIRED_TASK_FIELDS | {"context"}:
            raise GraphValidationError(f"{path}:{line_number + offset}: unknown field {name}")
        if name in values:
            raise GraphValidationError(f"{path}:{line_number + offset}: duplicate field {name}")
        values[name] = value
    missing = sorted(REQUIRED_TASK_FIELDS - values.keys())
    if missing:
        raise GraphValidationError(
            f"{path}:{line_number}: task {task_id} is missing fields: {', '.join(missing)}"
        )
    depends = _parse_list(values["depends"], f"task {task_id} Depends", allow_empty=True)
    paths = tuple(
        normalize_repo_path(item, f"task {task_id} Paths")
        for item in _parse_list(values["paths"], f"task {task_id} Paths", allow_empty=False)
    )
    if len(set(paths)) != len(paths):
        raise GraphValidationError(f"task {task_id} Paths contains a duplicate path")
    mode = values["mode"].strip().casefold()
    if mode not in MODES:
        raise GraphValidationError(f"task {task_id} Mode must be read or write")
    isolation = values["isolation"].strip().casefold()
    if isolation not in ISOLATIONS:
        raise GraphValidationError(f"task {task_id} Isolation must be auto or worktree")
    acceptance = _nonempty_string(values["acceptance"], f"task {task_id} Acceptance")
    check = _nonempty_string(values["check"], f"task {task_id} Check")
    return TaskContract(
        id=task_id,
        title=_nonempty_string(title, f"task {task_id} title"),
        depends=depends,
        paths=paths,
        mode=mode,
        isolation=isolation,
        acceptance=acceptance,
        check=check,
        context=values.get("context", "").strip(),
        visual=tuple(repeated["visual"]),
        visual_scope=tuple(repeated["visual-scope"]),
        checked=checked.casefold() == "x",
        source_line=line_number,
    )


def parse_task_graph(
    source: str | Path,
    *,
    source_name: str | None = None,
) -> TaskGraph:
    """Parse and validate a task graph from Markdown text or a file path."""

    if isinstance(source, Path):
        path = source
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise GraphValidationError(f"cannot read task graph {path}: {error}") from error
    else:
        text = source
        path = Path(source_name or "tasks.md")
    lines = text.splitlines()
    tasks: list[TaskContract] = []
    index = 0
    while index < len(lines):
        if not re.match(r"^\s*-\s+\[[ xX]\]", lines[index]):
            index += 1
            continue
        header = TASK_HEADER_PATTERN.fullmatch(lines[index])
        if not header:
            raise GraphValidationError(f"{path}:{index + 1}: task needs a stable leading ID")
        block_end = index + 1
        while block_end < len(lines) and not re.match(
            r"^\s*-\s+\[[ xX]\]", lines[block_end]
        ):
            block_end += 1
        tasks.append(_parse_task_block(path, index + 1, header, lines[index + 1 : block_end]))
        index = block_end
    if not tasks:
        raise GraphValidationError(f"{path}: no task contracts found")
    validate_task_graph(tasks)
    return TaskGraph(tuple(tasks))


def parse_tasks_file(path: Path) -> list[TaskContract]:
    """Compatibility-sized convenience wrapper for callers that need a list."""

    return list(parse_task_graph(path).tasks)


def validate_task_graph(tasks: Sequence[TaskContract]) -> None:
    """Validate task identity, dependency references, and acyclicity."""

    task_ids: set[str] = set()
    for task in tasks:
        if not TASK_ID_PATTERN.fullmatch(task.id):
            raise GraphValidationError(f"invalid task ID: {task.id}")
        if task.id in task_ids:
            raise GraphValidationError(f"duplicate task ID: {task.id}")
        task_ids.add(task.id)
    for task in tasks:
        if task.id in task.depends:
            raise GraphValidationError(f"task {task.id} cannot depend on itself")
        unknown = sorted(set(task.depends) - task_ids)
        if unknown:
            raise GraphValidationError(
                f"task {task.id} has unknown dependencies: {', '.join(unknown)}"
            )
    dependencies = {task.id: task.depends for task in tasks}
    visiting: list[str] = []
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visited:
            return
        if task_id in visiting:
            start = visiting.index(task_id)
            cycle = visiting[start:] + [task_id]
            raise GraphValidationError(f"task dependency cycle: {' -> '.join(cycle)}")
        visiting.append(task_id)
        for dependency in dependencies[task_id]:
            visit(dependency)
        visiting.pop()
        visited.add(task_id)

    for task in tasks:
        visit(task.id)


def path_scopes_overlap(first: str, second: str) -> bool:
    """Return whether two normalized file or directory scopes overlap."""

    first = normalize_repo_path(first, "first path")
    second = normalize_repo_path(second, "second path")
    first_directory = first.endswith("/")
    second_directory = second.endswith("/")
    first_parts = PurePosixPath(first.rstrip("/")).parts
    second_parts = PurePosixPath(second.rstrip("/")).parts
    shared = min(len(first_parts), len(second_parts))
    if first_parts[:shared] != second_parts[:shared]:
        return False
    if len(first_parts) == len(second_parts):
        return True
    if len(first_parts) < len(second_parts):
        return first_directory
    return second_directory


def tasks_conflict(first: TaskContract, second: TaskContract) -> bool:
    """Return whether two tasks cannot write concurrently."""

    if first.mode != "write" or second.mode != "write":
        return False
    return any(path_scopes_overlap(left, right) for left in first.paths for right in second.paths)


def _task_projection(projection: Mapping[str, Any], task_id: str) -> Mapping[str, Any]:
    tasks = projection.get("tasks", {})
    if not isinstance(tasks, Mapping):
        return {}
    task = tasks.get(task_id, {})
    return task if isinstance(task, Mapping) else {}


def _cleanup_attempt_ids(cleanup: Mapping[str, Any]) -> set[str]:
    attempt_ids: set[str] = set()
    direct_attempt_id = cleanup.get("attempt_id")
    if isinstance(direct_attempt_id, str):
        attempt_ids.add(direct_attempt_id)
    owner = cleanup.get("owner")
    if isinstance(owner, Mapping):
        attempt_id = owner.get("attempt_id")
        if isinstance(attempt_id, str):
            attempt_ids.add(attempt_id)
    elif isinstance(owner, str):
        attempt_ids.add(owner)
    return attempt_ids


def cleanup_is_terminal(cleanup: Mapping[str, Any]) -> bool:
    """Return whether cleanup reached a retry- and completion-safe outcome."""

    return cleanup.get("status") in TERMINAL_CLEANUP_STATUSES


def unresolved_cleanup_ids(projection: Mapping[str, Any]) -> list[str]:
    """Return every cleanup obligation that still blocks run completion."""

    cleanup = projection.get("cleanup", {})
    if not isinstance(cleanup, Mapping):
        cleanup = {}
    blocking = {
        cleanup_id
        for cleanup_id, record in cleanup.items()
        if isinstance(cleanup_id, str)
        and (not isinstance(record, Mapping) or not cleanup_is_terminal(record))
    }
    attempts = projection.get("attempts", {})
    if isinstance(attempts, Mapping):
        for attempt in attempts.values():
            if not isinstance(attempt, Mapping):
                continue
            cleanup_id = attempt.get("cleanup_id")
            if not isinstance(cleanup_id, str):
                continue
            record = cleanup.get(cleanup_id)
            if not isinstance(record, Mapping) or not cleanup_is_terminal(record):
                blocking.add(cleanup_id)
    return sorted(blocking)


def pending_cleanup_ids_for_task(
    projection: Mapping[str, Any], task_id: str
) -> list[str]:
    """Return cleanup that must settle before a task can start another attempt."""

    task = _task_projection(projection, task_id)
    attempt_ids = {
        attempt_id
        for attempt_id in task.get("attempt_ids", [])
        if isinstance(attempt_id, str)
    }
    cleanup = projection.get("cleanup", {})
    if not isinstance(cleanup, Mapping):
        cleanup = {}
    blocking: set[str] = set()
    attempts = projection.get("attempts", {})
    if isinstance(attempts, Mapping):
        for attempt_id in attempt_ids:
            attempt = attempts.get(attempt_id)
            if not isinstance(attempt, Mapping):
                continue
            cleanup_id = attempt.get("cleanup_id")
            if not isinstance(cleanup_id, str):
                continue
            record = cleanup.get(cleanup_id)
            if not isinstance(record, Mapping) or not cleanup_is_terminal(record):
                blocking.add(cleanup_id)
    for cleanup_id, record in cleanup.items():
        if (
            isinstance(cleanup_id, str)
            and isinstance(record, Mapping)
            and _cleanup_attempt_ids(record) & attempt_ids
            and not cleanup_is_terminal(record)
        ):
            blocking.add(cleanup_id)
    return sorted(blocking)


def pending_cleanup_ids_for_attempt(
    projection: Mapping[str, Any], attempt_id: str
) -> list[str]:
    """Return cleanup obligations anchored to one exact attempt."""

    cleanup = projection.get("cleanup", {})
    if not isinstance(cleanup, Mapping):
        cleanup = {}
    blocking: set[str] = set()
    attempt = projection.get("attempts", {}).get(attempt_id)
    if isinstance(attempt, Mapping):
        cleanup_id = attempt.get("cleanup_id")
        if isinstance(cleanup_id, str):
            record = cleanup.get(cleanup_id)
            if not isinstance(record, Mapping) or not cleanup_is_terminal(record):
                blocking.add(cleanup_id)
    for cleanup_id, record in cleanup.items():
        if (
            isinstance(cleanup_id, str)
            and isinstance(record, Mapping)
            and attempt_id in _cleanup_attempt_ids(record)
            and not cleanup_is_terminal(record)
        ):
            blocking.add(cleanup_id)
    return sorted(blocking)


def ready_tasks(
    graph: TaskGraph | Sequence[TaskContract],
    projection: Mapping[str, Any],
    *,
    active_task_ids: Iterable[str] | None = None,
) -> list[TaskContract]:
    """Return a deterministic maximal ready wave in document order."""

    tasks = graph.tasks if isinstance(graph, TaskGraph) else tuple(graph)
    by_id = {task.id: task for task in tasks}
    if active_task_ids is None:
        active_ids = {
            task.id
            for task in tasks
            if _task_projection(projection, task.id).get("status")
            in {"reserved", "running", "reported", "interrupted"}
        }
    else:
        active_ids = set(active_task_ids)
    active_writes = [by_id[task_id] for task_id in active_ids if task_id in by_id]
    selected: list[TaskContract] = []
    for task in tasks:
        if not _task_is_admitted_by_reduction(projection, task.id):
            continue
        state = _task_projection(projection, task.id)
        if (
            state.get("grade") is not None
            or state.get("status") in {"cancelled", "blocked"}
            or task.id in active_ids
        ):
            continue
        if pending_cleanup_ids_for_task(projection, task.id):
            continue
        if any(_task_projection(projection, dependency).get("grade") != "pass" for dependency in task.depends):
            continue
        if any(tasks_conflict(task, active) for active in active_writes):
            continue
        if any(tasks_conflict(task, candidate) for candidate in selected):
            continue
        selected.append(task)
        # A durable graph is evidence topology, not permission to fan out.
        # Older projections have no execution_mode and retain their historical
        # maximal-wave behavior; new runs start with one writer.
        if projection.get("execution_mode") == "single_writer" and task.mode != "read":
            break
    return selected


def _task_is_admitted_by_reduction(
    projection: Mapping[str, Any], task_id: str
) -> bool:
    reduction = projection.get("reduction")
    if projection.get("execution_mode") != "single_writer" or not isinstance(
        reduction, Mapping
    ):
        return True
    retained_task_ids = reduction.get("retained_task_ids")
    return isinstance(retained_task_ids, list) and task_id in retained_task_ids


def task_is_dispatchable(
    graph: TaskGraph | Sequence[TaskContract],
    projection: Mapping[str, Any],
    task: TaskContract,
) -> bool:
    """Return whether one explicitly requested task can start an attempt."""

    tasks = graph.tasks if isinstance(graph, TaskGraph) else tuple(graph)
    if not _task_is_admitted_by_reduction(projection, task.id):
        return False
    state = _task_projection(projection, task.id)
    # Scheduling fences always win over repair authorization.  In particular,
    # a consumed decision cannot race a reserved/running writer.
    if state.get("grade") is not None or state.get("status") in {
        "reserved", "running", "interrupted", "cancelled", "blocked",
    }:
        return False
    if pending_cleanup_ids_for_task(projection, task.id):
        return False
    if any(_task_projection(projection, dependency).get("grade") != "pass" for dependency in task.depends):
        return False
    technical_attempts = sum(
        1
        for attempt_id in state.get("attempt_ids", [])
        for attempt in [projection.get("attempts", {}).get(attempt_id)]
        if isinstance(attempt, Mapping)
        and (
            isinstance(attempt.get("report"), Mapping)
            or isinstance(attempt.get("check"), Mapping)
            or attempt.get("status") in {"reported", "audit-rejected", "check-rejected", "audit-exhausted"}
        )
    )
    decision = state.get("coordinator_decision")
    # One implementation and one bounded repair are automatic. A third
    # attempt requires one explicit public coordinator decision; a fourth is
    # never dispatchable.
    if technical_attempts >= 3:
        return False
    if technical_attempts == 2:
        return (
            isinstance(decision, Mapping)
            and decision.get("action") in {"amend_acceptance", "amend_paths", "regroup"}
            and not state.get("decision_consumed")
        )
    if state.get("status") == "reported":
        return False

    active_writes = [
        candidate
        for candidate in tasks
        if candidate.mode == "write"
        and _task_projection(projection, candidate.id).get("status")
        in {"reserved", "running", "reported", "interrupted"}
    ]
    if task.mode != "write":
        return True
    if projection.get("execution_mode") == "single_writer":
        return not active_writes
    return not any(tasks_conflict(task, active) for active in active_writes)


def task_blockers(
    task: TaskContract, projection: Mapping[str, Any]
) -> list[dict[str, str | None]]:
    """Describe dependency grades that prevent a task from becoming ready."""

    blockers: list[dict[str, str | None]] = []
    for dependency in task.depends:
        grade = _task_projection(projection, dependency).get("grade")
        if grade != "pass":
            blockers.append({"task_id": dependency, "grade": grade})
    return blockers


def _validate_string_list(value: Any, context: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise GraphValidationError(f"{context} must be an array of non-empty strings")
    if len(set(value)) != len(value):
        raise GraphValidationError(f"{context} must not contain duplicates")
    return list(value)


def _validate_audit_finding_refs(value: Any) -> list[str]:
    references = _validate_string_list(
        value, "attempt_audit_rejected finding_refs"
    )
    if not references:
        raise GraphValidationError(
            "attempt_audit_rejected finding_refs must not be empty"
        )
    for reference in references:
        if reference.startswith("file:"):
            path = reference.removeprefix("file:")
            if normalize_repo_path(path, "attempt_audit_rejected file reference") != path:
                raise GraphValidationError(
                    "attempt_audit_rejected file reference must be canonical"
                )
        elif reference.startswith("commit:"):
            revision = reference.removeprefix("commit:")
            if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", revision):
                raise GraphValidationError(
                    "attempt_audit_rejected commit reference must use a canonical full SHA"
                )
        else:
            raise GraphValidationError(
                "attempt_audit_rejected finding_refs must use file: or commit:"
            )
    return references


FINDING_CLASSIFICATIONS = frozenset({
    "acceptance_violation", "reproducible_regression", "security_or_integrity",
    "hardening", "advisory",
})
BLOCKING_FINDING_CLASSIFICATIONS = frozenset({
    "acceptance_violation", "reproducible_regression", "security_or_integrity",
})


def validate_finding(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the compact public finding contract."""
    required = {"schema_version", "finding_id", "classification", "task_id", "attempt_id", "acceptance_reference", "evidence_ref", "affected", "reproduction", "smallest_repair_hypothesis", "why_current_check_does_not_detect"}
    if set(value) != required:
        raise GraphValidationError("finding fields must match the public contract")
    if value["schema_version"] != 1 or value["classification"] not in FINDING_CLASSIFICATIONS:
        raise GraphValidationError("finding classification is invalid")
    for field in ("finding_id", "task_id", "attempt_id", "acceptance_reference", "evidence_ref", "smallest_repair_hypothesis", "why_current_check_does_not_detect"):
        _nonempty_string(value[field], f"finding {field}")
    if not value["evidence_ref"].startswith("file:"):
        raise GraphValidationError("finding evidence_ref must use file:")
    normalize_repo_path(value["evidence_ref"].removeprefix("file:"), "finding evidence path")
    affected = value["affected"]
    if not isinstance(affected, list) or not affected or any(not isinstance(item, Mapping) for item in affected):
        raise GraphValidationError("finding affected must be a non-empty array of objects")
    for item in affected:
        if set(item) != {"file", "identity"}:
            raise GraphValidationError("finding affected entries require file and identity")
        normalize_repo_path(item["file"], "finding affected file")
        _nonempty_string(item["identity"], "finding affected identity")
    reproduction = value["reproduction"]
    if not isinstance(reproduction, Mapping) or set(reproduction) != {"steps", "observed", "expected"}:
        raise GraphValidationError("finding reproduction is incomplete")
    _validate_string_list(reproduction["steps"], "finding reproduction steps")
    _nonempty_string(reproduction["observed"], "finding reproduction observed")
    _nonempty_string(reproduction["expected"], "finding reproduction expected")
    return json.loads(json.dumps(dict(value), sort_keys=True))


def _unresolved_blocking_findings(
    state: Mapping[str, Any], task_id: str, attempt_id: str
) -> list[str]:
    findings = state.get("findings", {})
    if not isinstance(findings, Mapping):
        return []
    return sorted(
        finding_id
        for finding_id, finding in findings.items()
        if isinstance(finding_id, str)
        and isinstance(finding, Mapping)
        and finding.get("task_id") == task_id
        and finding.get("attempt_id") == attempt_id
        and finding.get("classification") in BLOCKING_FINDING_CLASSIFICATIONS
    )


def _carry_forward_hardening(
    state: dict[str, Any], task_id: str, attempt_id: str
) -> None:
    findings = state.get("findings", {})
    if not isinstance(findings, Mapping):
        return
    references = sorted(
        finding["evidence_ref"]
        for finding in findings.values()
        if isinstance(finding, Mapping)
        and finding.get("task_id") == task_id
        and finding.get("attempt_id") == attempt_id
        and finding.get("classification") == "hardening"
        and isinstance(finding.get("evidence_ref"), str)
    )
    if not references:
        return
    carry_forward = {
        "status": "carry_forward",
        "task_id": task_id,
        "attempt_id": attempt_id,
        "finding_refs": references,
    }
    if carry_forward not in state["degradations"]:
        state["degradations"].append(carry_forward)


def path_is_within_scopes(path: str, scopes: Sequence[str]) -> bool:
    """Return whether a file path belongs to one declared task scope."""

    normalized = normalize_repo_path(path, "changed file")
    if normalized.endswith("/"):
        raise GraphValidationError("changed file must name a file, not a directory")
    for scope in scopes:
        scope = normalize_repo_path(scope, "task path")
        if scope.endswith("/") and normalized.startswith(scope):
            return True
        if normalized == scope:
            return True
    return False


def _opaque_identity(value: Any, context: str) -> str:
    value = _nonempty_string(value, context)
    if len(value) > 4096 or any(ord(character) < 32 for character in value):
        raise GraphValidationError(f"{context} must be an opaque identity without control characters")
    return value


def _validate_workspace_identity(value: Any, context: str) -> dict[str, Any]:
    workspace = _exact_fields(
        value,
        {"execution_host_id", "workspace_key", "kind", "path"},
        {"worktree_path"},
        context,
    )
    _opaque_identity(workspace["execution_host_id"], f"{context} execution_host_id")
    _workspace_key(workspace["workspace_key"], f"{context} workspace_key")
    kind = workspace["kind"]
    if kind not in WORKSPACE_KINDS:
        raise GraphValidationError(f"{context} kind must be folder or git-worktree")
    path = _absolute_path(workspace["path"], f"{context} path")
    worktree_path = workspace.get("worktree_path")
    if kind == "git-worktree":
        if worktree_path is None:
            raise GraphValidationError(f"{context} git-worktree needs worktree_path")
        if _absolute_path(worktree_path, f"{context} worktree_path") != path:
            raise GraphValidationError(f"{context} worktree_path must equal path")
    elif worktree_path is not None:
        raise GraphValidationError(f"{context} folder cannot define worktree_path")
    return json.loads(json.dumps(dict(workspace), sort_keys=True))


def validate_workspace_bootstrap_receipt(
    receipt: Mapping[str, Any],
    *,
    expected_run_id: str | None = None,
    expected_repository: Path | None = None,
) -> dict[str, Any]:
    """Validate the authority-issued identity used to bind a public run."""

    receipt = _exact_fields(
        receipt,
        {
            "schema_version",
            "repository_id",
            "canonical_root",
            "execution_host",
            "orchestration_home",
            "execution_workspace",
            "base_revision",
            "dirty_paths",
            "authority",
        },
        set(),
        "workspace bootstrap receipt",
    )
    if receipt["schema_version"] != SCHEMA_VERSION:
        raise GraphValidationError("workspace bootstrap receipt schema_version is unsupported")
    _identifier(receipt["repository_id"], "workspace bootstrap receipt repository_id")
    canonical_root = _absolute_path(
        receipt["canonical_root"], "workspace bootstrap receipt canonical_root"
    )
    host = _exact_fields(
        receipt["execution_host"],
        {"id", "boundary"},
        set(),
        "workspace bootstrap receipt execution_host",
    )
    host_id = _opaque_identity(host["id"], "workspace bootstrap receipt execution_host id")
    if host["boundary"] not in {"local", "remote"}:
        raise GraphValidationError(
            "workspace bootstrap receipt execution_host boundary must be local or remote"
        )
    orchestration_home = _validate_workspace_identity(
        receipt["orchestration_home"], "workspace bootstrap receipt orchestration_home"
    )
    execution_workspace = _validate_workspace_identity(
        receipt["execution_workspace"], "workspace bootstrap receipt execution_workspace"
    )
    if orchestration_home["path"] != canonical_root:
        raise GraphValidationError(
            "workspace bootstrap receipt canonical_root must equal orchestration_home path"
        )
    if execution_workspace["execution_host_id"] != host_id:
        raise GraphValidationError(
            "workspace bootstrap receipt execution_workspace does not belong to execution_host"
        )
    _nonempty_string(receipt["base_revision"], "workspace bootstrap receipt base_revision")
    dirty_paths = _validate_string_list(
        receipt["dirty_paths"], "workspace bootstrap receipt dirty_paths"
    )
    for dirty_path in dirty_paths:
        normalize_repo_path(dirty_path, "workspace bootstrap receipt dirty path")
    authority = _exact_fields(
        receipt["authority"],
        {"kind", "scope", "issued_for_run_id"},
        set(),
        "workspace bootstrap receipt authority",
    )
    if authority["kind"] not in WORKSPACE_AUTHORITY_KINDS:
        raise GraphValidationError("workspace bootstrap receipt authority kind is unsupported")
    if authority["scope"] != "run":
        raise GraphValidationError("workspace bootstrap receipt authority scope must be run")
    _identifier(
        authority["issued_for_run_id"],
        "workspace bootstrap receipt authority issued_for_run_id",
    )
    if authority["kind"] == "host-run":
        repository_id = str(receipt["repository_id"])
        if not HOST_RUN_REPOSITORY_PATTERN.fullmatch(repository_id):
            raise GraphValidationError(
                "host-run workspace receipt repository_id must contain a canonical UUIDv4"
            )
        if host["boundary"] != "local":
            raise GraphValidationError("host-run workspace receipt execution host must be local")
        if orchestration_home != execution_workspace:
            raise GraphValidationError(
                "host-run workspace receipt orchestration and execution identities must match"
            )
        if orchestration_home["kind"] != "folder":
            raise GraphValidationError("host-run workspace receipt must use a folder workspace")
        if orchestration_home["path"] != canonical_root:
            raise GraphValidationError(
                "host-run workspace receipt workspace path must equal canonical_root"
            )
        if orchestration_home["workspace_key"] != f"folder:{repository_id}":
            raise GraphValidationError(
                "host-run workspace receipt workspace_key must match repository_id"
            )
    if expected_run_id is not None:
        expected_run_id = _identifier(expected_run_id, "expected workspace receipt run_id")
        if authority["issued_for_run_id"] != expected_run_id:
            raise GraphValidationError(
                "workspace bootstrap receipt was issued for another run"
            )
    if expected_repository is not None:
        expected_root = str(expected_repository.resolve())
        if canonical_root != expected_root:
            raise GraphValidationError(
                "workspace bootstrap receipt canonical_root does not match the repository"
            )
    return json.loads(json.dumps(dict(receipt), sort_keys=True))


def validate_workspace_scope(scope: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one pinned orchestration and execution workspace identity."""

    required = {
        "schema_version",
        "repository_id",
        "canonical_root",
        "execution_host",
        "orchestration_home",
        "execution_workspace",
        "base_revision",
        "dirty_paths",
        "run_id",
        "coordinator_generation",
        "binding_receipt_ref",
        "binding_receipt_hash",
    }
    scope = _exact_fields(scope, required, set(), "workspace scope")
    if scope["schema_version"] != SCHEMA_VERSION:
        raise GraphValidationError("workspace scope schema_version is unsupported")
    _identifier(scope["repository_id"], "workspace scope repository_id")
    canonical_root = _absolute_path(scope["canonical_root"], "workspace scope canonical_root")
    host = _exact_fields(
        scope["execution_host"], {"id", "boundary"}, set(), "workspace scope execution_host"
    )
    host_id = _opaque_identity(host["id"], "workspace scope execution_host id")
    if host["boundary"] not in {"local", "remote"}:
        raise GraphValidationError("workspace scope execution_host boundary must be local or remote")
    orchestration_home = _validate_workspace_identity(
        scope["orchestration_home"], "workspace scope orchestration_home"
    )
    execution_workspace = _validate_workspace_identity(
        scope["execution_workspace"], "workspace scope execution_workspace"
    )
    if execution_workspace["execution_host_id"] != host_id:
        raise GraphValidationError(
            "workspace scope execution_workspace does not belong to execution_host"
        )
    if orchestration_home["path"] != canonical_root:
        raise GraphValidationError(
            "workspace scope canonical_root must equal orchestration_home path"
        )
    _nonempty_string(scope["base_revision"], "workspace scope base_revision")
    dirty_paths = _validate_string_list(scope["dirty_paths"], "workspace scope dirty_paths")
    for dirty_path in dirty_paths:
        normalize_repo_path(dirty_path, "workspace scope dirty path")
    _identifier(scope["run_id"], "workspace scope run_id")
    generation = scope["coordinator_generation"]
    if not isinstance(generation, int) or isinstance(generation, bool) or generation < 1:
        raise GraphValidationError(
            "workspace scope coordinator_generation must be a positive integer"
        )
    receipt_ref = _nonempty_string(
        scope["binding_receipt_ref"], "workspace scope binding_receipt_ref"
    )
    if not receipt_ref.startswith("artifact:"):
        raise GraphValidationError("workspace scope binding_receipt_ref must use artifact:")
    normalize_repo_path(
        receipt_ref.removeprefix("artifact:"), "workspace scope binding receipt path"
    )
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(scope["binding_receipt_hash"])):
        raise GraphValidationError("workspace scope binding_receipt_hash must be sha256")
    return json.loads(json.dumps(dict(scope), sort_keys=True))


def _validate_placement_request(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise GraphValidationError("placement request must be an object")
    kind = value.get("kind")
    if kind not in PLACEMENT_KINDS:
        raise GraphValidationError("placement request kind is unsupported")
    required = {"kind"}
    if kind == "existing-workspace":
        required |= {"execution_host_id", "workspace_key"}
    elif kind == "create-child-worktree":
        required |= {"execution_host_id", "parent_workspace_key", "name_hint"}
    request = _exact_fields(value, required, set(), "placement request")
    for field in required - {"kind"}:
        if field in {"workspace_key", "parent_workspace_key"}:
            _workspace_key(request[field], f"placement request {field}")
        elif field == "execution_host_id":
            _opaque_identity(request[field], f"placement request {field}")
        else:
            _identifier(request[field], f"placement request {field}")
    return json.loads(json.dumps(dict(request), sort_keys=True))


def _validate_resolved_placement(value: Any) -> dict[str, Any]:
    placement = _exact_fields(
        value,
        {"execution_host_id", "workspace_key", "kind", "path", "receipt_ref"},
        set(),
        "resolved placement",
    )
    _opaque_identity(placement["execution_host_id"], "resolved placement execution_host_id")
    _workspace_key(placement["workspace_key"], "resolved placement workspace_key")
    if placement["kind"] not in WORKSPACE_KINDS:
        raise GraphValidationError("resolved placement kind must be folder or git-worktree")
    if placement["path"] is not None:
        _absolute_path(placement["path"], "resolved placement path")
    receipt_ref = _nonempty_string(placement["receipt_ref"], "resolved placement receipt_ref")
    if not receipt_ref.startswith("artifact:"):
        raise GraphValidationError("resolved placement receipt_ref must use artifact:")
    normalize_repo_path(receipt_ref.removeprefix("artifact:"), "resolved placement receipt path")
    return json.loads(json.dumps(dict(placement), sort_keys=True))


def validate_execution_profile(
    profile: Mapping[str, Any],
    workspace_scope: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate requested and resolved attempt routing without silent fallback."""

    profile = _exact_fields(
        profile,
        {
            "role",
            "requested",
            "resolved",
            "fallback_reason",
            "placement_request",
            "resolved_placement",
        },
        set(),
        "execution profile",
    )
    _identifier(profile["role"], "execution profile role")
    requested = _exact_fields(
        profile["requested"], {"lane", "agent", "model", "effort"}, set(), "requested profile"
    )
    if requested["lane"] not in {"fast", "balanced", "strong"}:
        raise GraphValidationError("requested profile lane is unsupported")
    for field in ("agent", "model"):
        if requested[field] is not None:
            _nonempty_string(requested[field], f"requested profile {field}")
    if requested["effort"] not in EFFORTS:
        raise GraphValidationError("requested profile effort is unsupported")
    resolved = _exact_fields(
        profile["resolved"], {"agent", "model", "effort"}, set(), "resolved profile"
    )
    for field in ("agent", "model"):
        _nonempty_string(resolved[field], f"resolved profile {field}")
    if resolved["effort"] not in EFFORTS:
        raise GraphValidationError("resolved profile effort is unsupported")
    fallback_reason = profile["fallback_reason"]
    if fallback_reason is not None:
        _nonempty_string(fallback_reason, "execution profile fallback_reason")
    diverged = any(
        requested[field] is not None and requested[field] != resolved[field]
        for field in ("agent", "model", "effort")
    )
    if diverged and fallback_reason is None:
        raise GraphValidationError("execution profile divergence needs fallback_reason")
    request = _validate_placement_request(profile["placement_request"])
    placement = _validate_resolved_placement(profile["resolved_placement"])
    scope = validate_workspace_scope(workspace_scope)
    current = scope["execution_workspace"]
    if request["kind"] == "current-workspace":
        if (
            placement["execution_host_id"] != current["execution_host_id"]
            or placement["workspace_key"] != current["workspace_key"]
            or placement["kind"] != current["kind"]
            or placement["path"] not in {None, current["path"]}
        ):
            raise GraphValidationError("current-workspace placement identity does not match the pin")
    elif request["kind"] == "existing-workspace":
        if (
            placement["execution_host_id"] != request["execution_host_id"]
            or placement["workspace_key"] != request["workspace_key"]
        ):
            raise GraphValidationError("resolved placement does not match requested workspace")
    else:
        known_parents = {
            (scope["orchestration_home"]["execution_host_id"], scope["orchestration_home"]["workspace_key"]),
            (current["execution_host_id"], current["workspace_key"]),
        }
        requested_parent = (request["execution_host_id"], request["parent_workspace_key"])
        if requested_parent not in known_parents:
            raise GraphValidationError("child placement parent is outside the pinned workspace scope")
        if (
            placement["execution_host_id"] != request["execution_host_id"]
            or placement["workspace_key"] == request["parent_workspace_key"]
            or placement["kind"] != "git-worktree"
        ):
            raise GraphValidationError("resolved child placement does not match its exact parent")
    return json.loads(json.dumps(dict(profile), sort_keys=True))


def _validate_cursor(value: Any, context: str) -> dict[str, Any]:
    cursor = _exact_fields(
        value, {"stream_id", "sequence", "revision"}, set(), context
    )
    _identifier(cursor["stream_id"], f"{context} stream_id")
    for number in ("sequence", "revision"):
        if (
            not isinstance(cursor[number], int)
            or isinstance(cursor[number], bool)
            or cursor[number] < 0
        ):
            raise GraphValidationError(f"{context} {number} must be non-negative")
    return json.loads(json.dumps(dict(cursor), sort_keys=True))


def validate_agent_graph_view(view: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the bounded, transcript-free Maestro projection contract."""

    view = _exact_fields(
        view,
        {
            "schema_version",
            "protocol",
            "kind",
            "workspace_scope",
            "change",
            "run_id",
            "coordinator",
            "capabilities",
            "nodes",
            "edges",
            "removed_node_ids",
            "removed_edge_ids",
            "revision",
            "cursor",
            "from_cursor",
            "reset_required",
            "progress",
        },
        set(),
        "agent graph view",
    )
    if view["schema_version"] != SCHEMA_VERSION or view["protocol"] != "agent-graph-view/v1":
        raise GraphValidationError("agent graph view protocol is unsupported")
    if view["kind"] not in {"snapshot", "delta"}:
        raise GraphValidationError("agent graph view kind must be snapshot or delta")
    scope = validate_workspace_scope(view["workspace_scope"])
    if view["run_id"] != scope["run_id"]:
        raise GraphValidationError("agent graph view run_id does not match workspace scope")
    _identifier(view["change"], "agent graph view change")
    coordinator = _exact_fields(
        view["coordinator"], {"id", "generation"}, set(), "agent graph view coordinator"
    )
    _identifier(coordinator["id"], "agent graph view coordinator id")
    if coordinator["generation"] != scope["coordinator_generation"]:
        raise GraphValidationError("agent graph view coordinator generation does not match the pin")
    capabilities = _exact_fields(
        view["capabilities"],
        {"agents", "efforts", "placement_kinds", "watch_deltas"},
        set(),
        "agent graph view capabilities",
    )
    agents = _validate_string_list(capabilities["agents"], "agent graph view agents")
    efforts = _validate_string_list(capabilities["efforts"], "agent graph view efforts")
    placements = _validate_string_list(
        capabilities["placement_kinds"], "agent graph view placement_kinds"
    )
    if len(agents) > 32 or len(efforts) > 4 or len(placements) > 3:
        raise GraphValidationError("agent graph view capabilities exceed their bounds")
    if not set(efforts) <= EFFORTS or not set(placements) <= PLACEMENT_KINDS:
        raise GraphValidationError("agent graph view capabilities contain unsupported values")
    if not isinstance(capabilities["watch_deltas"], bool):
        raise GraphValidationError("agent graph view watch_deltas must be boolean")
    nodes = view["nodes"]
    edges = view["edges"]
    if not isinstance(nodes, list) or len(nodes) > 1000:
        raise GraphValidationError("agent graph view nodes exceed the bounded array")
    if not isinstance(edges, list) or len(edges) > 3000:
        raise GraphValidationError("agent graph view edges exceed the bounded array")
    node_ids: set[str] = set()
    for node in nodes:
        node = _exact_fields(
            node,
            {"id", "type", "status", "summary"},
            {"task_id", "attempt_id", "profile", "blockers", "snapshot"},
            "agent graph view node",
        )
        node_id = _identifier(node["id"], "agent graph view node id")
        if node_id in node_ids:
            raise GraphValidationError(f"agent graph view has duplicate node: {node_id}")
        node_ids.add(node_id)
        if node["type"] not in NODE_TYPES:
            raise GraphValidationError("agent graph view node type is unsupported")
        _nonempty_string(node["status"], "agent graph view node status")
        summary = _nonempty_string(node["summary"], "agent graph view node summary")
        if len(summary.encode("utf-8")) > 2048:
            raise GraphValidationError("agent graph view node summary exceeds 2048 bytes")
        if "task_id" in node:
            _identifier(node["task_id"], "agent graph view node task_id")
        if "attempt_id" in node:
            _identifier(node["attempt_id"], "agent graph view node attempt_id")
        if node["type"] == "attempt":
            if not {"task_id", "attempt_id", "profile"} <= set(node):
                raise GraphValidationError("attempt node needs task_id, attempt_id, and profile")
            validate_execution_profile(node["profile"], scope)
        if node["type"] == "note-reference":
            if "snapshot" not in node:
                raise GraphValidationError("note-reference node needs a snapshot")
            _validate_note_snapshot(node["snapshot"], "agent graph view note snapshot")
    edge_ids: set[str] = set()
    for edge in edges:
        edge = _exact_fields(
            edge, {"id", "type", "source_id", "target_id"}, set(), "agent graph view edge"
        )
        edge_id = _identifier(edge["id"], "agent graph view edge id")
        if edge_id in edge_ids:
            raise GraphValidationError(f"agent graph view has duplicate edge: {edge_id}")
        edge_ids.add(edge_id)
        if edge["type"] not in EDGE_TYPES:
            raise GraphValidationError("agent graph view edge type is unsupported")
        if view["kind"] == "snapshot" and (
            edge["source_id"] not in node_ids or edge["target_id"] not in node_ids
        ):
            raise GraphValidationError("agent graph view edge references an unknown node")
    for field in ("removed_node_ids", "removed_edge_ids"):
        _validate_string_list(view[field], f"agent graph view {field}")
    revision = view["revision"]
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
        raise GraphValidationError("agent graph view revision must be non-negative")
    for field in ("cursor", "from_cursor"):
        cursor = view[field]
        if cursor is None:
            continue
        _validate_cursor(cursor, f"agent graph view {field}")
    if view["cursor"] is not None and view["cursor"]["revision"] != revision:
        raise GraphValidationError("agent graph view cursor revision does not match the view")
    if not isinstance(view["reset_required"], bool):
        raise GraphValidationError("agent graph view reset_required must be boolean")
    from run_progress import validate_run_progress_summary

    try:
        progress = validate_run_progress_summary(view["progress"])
    except ValueError as error:
        raise GraphValidationError(f"agent graph view progress is invalid: {error}") from error
    activity = progress["last_activity"]
    if revision == 0 and activity is not None:
        raise GraphValidationError(
            "agent graph view at revision zero cannot have journal activity"
        )
    if revision > 0 and activity is None:
        raise GraphValidationError(
            "agent graph view with journal activity requires progress last_activity"
        )
    if activity is not None and activity["sequence"] != revision:
        raise GraphValidationError(
            "agent graph view progress activity sequence does not match the view revision"
        )
    _reject_transcript_fields(view, "agent graph view")
    return json.loads(json.dumps(dict(view), sort_keys=True))


def _validate_actor_envelope(value: Any, context: str) -> dict[str, Any]:
    actor = _exact_fields(
        value,
        {"actor_id", "kind", "authenticated", "session_id"},
        set(),
        context,
    )
    _identifier(actor["actor_id"], f"{context} actor_id")
    if actor["kind"] not in {"user", "coordinator", "worker", "system"}:
        raise GraphValidationError(f"{context} kind is unsupported")
    if actor["authenticated"] is not True:
        raise GraphValidationError(f"{context} must be authenticated")
    _identifier(actor["session_id"], f"{context} session_id")
    return json.loads(json.dumps(dict(actor), sort_keys=True))


def _validate_note_snapshot(value: Any, context: str) -> dict[str, Any]:
    snapshot = _exact_fields(
        value,
        {
            "note_id",
            "revision",
            "content_hash",
            "media_type",
            "title",
            "snapshot_path",
            "byte_count",
        },
        set(),
        context,
    )
    _identifier(snapshot["note_id"], f"{context} note_id")
    _identifier(snapshot["revision"], f"{context} revision")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(snapshot["content_hash"])):
        raise GraphValidationError(f"{context} content_hash must be sha256")
    if snapshot["media_type"] != "text/markdown":
        raise GraphValidationError(f"{context} media_type must be text/markdown")
    _nonempty_string(snapshot["title"], f"{context} title")
    normalize_repo_path(snapshot["snapshot_path"], f"{context} snapshot_path")
    byte_count = snapshot["byte_count"]
    if not isinstance(byte_count, int) or isinstance(byte_count, bool) or byte_count < 1:
        raise GraphValidationError(f"{context} byte_count must be positive")
    return json.loads(json.dumps(dict(snapshot), sort_keys=True))


def _validate_workspace_anchor(value: Any, context: str) -> dict[str, Any]:
    anchor = _exact_fields(
        value,
        {"repository_id", "execution_host_id", "workspace_key", "run_id"},
        set(),
        context,
    )
    for field in anchor:
        if field == "workspace_key":
            _workspace_key(anchor[field], f"{context} {field}")
        elif field == "execution_host_id":
            _opaque_identity(anchor[field], f"{context} {field}")
        else:
            _identifier(anchor[field], f"{context} {field}")
    return json.loads(json.dumps(dict(anchor), sort_keys=True))


def _anchor_matches_scope(anchor: Mapping[str, Any], scope: Mapping[str, Any]) -> bool:
    workspace = scope["orchestration_home"]
    return (
        anchor["repository_id"] == scope["repository_id"]
        and anchor["execution_host_id"] == workspace["execution_host_id"]
        and anchor["workspace_key"] == workspace["workspace_key"]
        and anchor["run_id"] == scope["run_id"]
    )


def validate_maestro_mutation(
    mutation: Mapping[str, Any], workspace_scope: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate one authenticated, revision-fenced Canvas mutation."""

    mutation = _exact_fields(
        mutation,
        {
            "schema_version",
            "protocol",
            "mutation_id",
            "workspace",
            "actor",
            "coordinator_generation",
            "expected_revision",
            "operation",
        },
        set(),
        "maestro mutation",
    )
    if mutation["schema_version"] != SCHEMA_VERSION or mutation["protocol"] != "maestro-mutation/v1":
        raise GraphValidationError("maestro mutation protocol is unsupported")
    _identifier(mutation["mutation_id"], "maestro mutation mutation_id")
    scope = validate_workspace_scope(workspace_scope)
    anchor = _validate_workspace_anchor(mutation["workspace"], "maestro mutation workspace")
    if not _anchor_matches_scope(anchor, scope):
        raise GraphValidationError("maestro mutation workspace does not match the pinned scope")
    _validate_actor_envelope(mutation["actor"], "maestro mutation actor")
    if mutation["coordinator_generation"] != scope["coordinator_generation"]:
        raise GraphValidationError("maestro mutation uses a stale coordinator generation")
    revision = mutation["expected_revision"]
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
        raise GraphValidationError("maestro mutation expected_revision must be non-negative")
    operation = mutation["operation"]
    if not isinstance(operation, Mapping):
        raise GraphValidationError("maestro mutation operation must be an object")
    kind = operation.get("kind")
    if kind == "move-node":
        operation = _exact_fields(
            operation, {"kind", "node_id", "position"}, set(), "move-node operation"
        )
        _identifier(operation["node_id"], "move-node operation node_id")
        position = _exact_fields(
            operation["position"], {"x", "y"}, set(), "move-node operation position"
        )
        if any(
            not isinstance(position[axis], (int, float)) or isinstance(position[axis], bool)
            for axis in ("x", "y")
        ):
            raise GraphValidationError("move-node operation position must be numeric")
    elif kind == "pin-note-snapshot":
        operation = _exact_fields(
            operation, {"kind", "task_id", "snapshot"}, set(), "pin-note-snapshot operation"
        )
        _identifier(operation["task_id"], "pin-note-snapshot operation task_id")
        _validate_note_snapshot(operation["snapshot"], "pin-note-snapshot operation snapshot")
    else:
        raise GraphValidationError("maestro mutation operation kind is unsupported")
    _reject_transcript_fields(mutation, "maestro mutation")
    return json.loads(json.dumps(dict(mutation), sort_keys=True))


def validate_delegation_intent(
    intent: Mapping[str, Any], workspace_scope: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate one authenticated child request against its pinned parent workspace."""

    intent = _exact_fields(
        intent,
        {
            "schema_version",
            "protocol",
            "intent_id",
            "workspace",
            "actor",
            "coordinator_generation",
            "expected_revision",
            "parent_task_id",
            "parent_attempt_id",
            "purpose",
            "role",
            "requested",
            "placement_request",
            "context_refs",
            "paths",
            "check",
        },
        set(),
        "delegation intent",
    )
    if intent["schema_version"] != SCHEMA_VERSION or intent["protocol"] != "delegation-intent/v1":
        raise GraphValidationError("delegation intent protocol is unsupported")
    for field in ("intent_id", "parent_task_id", "parent_attempt_id", "role"):
        _identifier(intent[field], f"delegation intent {field}")
    scope = validate_workspace_scope(workspace_scope)
    anchor = _validate_workspace_anchor(intent["workspace"], "delegation intent workspace")
    if not _anchor_matches_scope(anchor, scope):
        raise GraphValidationError("delegation intent workspace does not match the pinned scope")
    _validate_actor_envelope(intent["actor"], "delegation intent actor")
    if intent["coordinator_generation"] != scope["coordinator_generation"]:
        raise GraphValidationError("delegation intent uses a stale coordinator generation")
    if not isinstance(intent["expected_revision"], int) or isinstance(intent["expected_revision"], bool) or intent["expected_revision"] < 0:
        raise GraphValidationError("delegation intent expected_revision must be non-negative")
    _nonempty_string(intent["purpose"], "delegation intent purpose")
    requested = _exact_fields(
        intent["requested"], {"lane", "agent", "model", "effort"}, set(), "delegation requested profile"
    )
    if requested["lane"] not in {"fast", "balanced", "strong"} or requested["effort"] not in EFFORTS:
        raise GraphValidationError("delegation requested profile is unsupported")
    for field in ("agent", "model"):
        if requested[field] is not None:
            _nonempty_string(requested[field], f"delegation requested profile {field}")
    _validate_placement_request(intent["placement_request"])
    _validate_string_list(intent["context_refs"], "delegation intent context_refs")
    paths = _validate_string_list(intent["paths"], "delegation intent paths")
    if not paths:
        raise GraphValidationError("delegation intent paths must not be empty")
    for path in paths:
        normalize_repo_path(path, "delegation intent path")
    _nonempty_string(intent["check"], "delegation intent check")
    _reject_transcript_fields(intent, "delegation intent")
    return json.loads(json.dumps(dict(intent), sort_keys=True))


def validate_delegation_result(
    result: Mapping[str, Any],
    delegation: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate a child report without allowing it to settle its parent task."""

    required = {
        "delegation_id", "task_id", "attempt_id", "outcome", "summary",
        "files_changed", "checks_run", "evidence_refs", "questions", "external_refs",
    }
    if not isinstance(result, Mapping):
        raise GraphValidationError("delegation result must be an object")
    unknown = sorted(set(result) - required)
    missing = sorted(required - set(result))
    if unknown:
        raise GraphValidationError(f"delegation result has unknown fields: {', '.join(unknown)}")
    if missing:
        raise GraphValidationError(f"delegation result is missing fields: {', '.join(missing)}")
    if result["delegation_id"] != delegation.get("delegation_id"):
        raise GraphValidationError("delegation result does not match the delegation")
    if result["task_id"] != delegation.get("parent_task_id"):
        raise GraphValidationError("delegation result task_id does not match the parent task")
    if result["attempt_id"] != delegation.get("child_attempt_id"):
        raise GraphValidationError("delegation result attempt_id does not match the child")
    if result["outcome"] != "reported":
        raise GraphValidationError("delegation result outcome must be reported")
    _nonempty_string(result["summary"], "delegation result summary")
    files = _validate_string_list(result["files_changed"], "delegation result files_changed")
    for changed_file in files:
        if not path_is_within_scopes(changed_file, delegation.get("paths", [])):
            raise GraphValidationError(f"delegation changed file is outside approved paths: {changed_file}")
    checks = _validate_string_list(result["checks_run"], "delegation result checks_run")
    if not checks:
        raise GraphValidationError("delegation result checks_run must contain at least one check")
    evidence = _validate_string_list(result["evidence_refs"], "delegation result evidence_refs")
    for reference in evidence:
        kind, separator, target = reference.partition(":")
        if not separator or kind not in {"file", "commit"} or not target:
            raise GraphValidationError("delegation evidence refs must use file: or commit:")
        if kind == "file":
            normalize_repo_path(target, "delegation evidence path")
        elif not COMMIT_PATTERN.fullmatch(target):
            raise GraphValidationError("delegation commit evidence must use a full SHA")
    if not isinstance(result["questions"], list) or any(
        not isinstance(item, Mapping) for item in result["questions"]
    ):
        raise GraphValidationError("delegation result questions must be an array of objects")
    external_refs = result["external_refs"]
    if not isinstance(external_refs, Mapping) or any(
        not isinstance(key, str) or not key or not isinstance(value, (str, int, bool, type(None)))
        for key, value in external_refs.items()
    ):
        raise GraphValidationError("delegation result external_refs must be a scalar-valued object")
    return json.loads(json.dumps(dict(result), sort_keys=True))


def _validate_lifecycle_receipt(
    value: Any, state: Mapping[str, Any], context: str
) -> dict[str, Any]:
    receipt = _exact_fields(
        value, {"receipt_id", "receipt_path", "sha256", "byte_length"}, set(), context
    )
    _identifier(receipt["receipt_id"], f"{context} receipt_id")
    path = normalize_repo_path(receipt["receipt_path"], f"{context} receipt_path")
    expected_prefix = f"openspec/runs/{state['change']}/{state['run_id']}/artifacts/"
    if not path.startswith(expected_prefix):
        raise GraphValidationError(f"{context} receipt_path is outside the run artifacts")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(receipt["sha256"])):
        raise GraphValidationError(f"{context} sha256 must be a canonical SHA-256")
    byte_length = receipt["byte_length"]
    if not isinstance(byte_length, int) or isinstance(byte_length, bool) or byte_length < 1:
        raise GraphValidationError(f"{context} byte_length must be positive")
    return json.loads(json.dumps(dict(receipt), sort_keys=True))


def _require_unclaimed_lifecycle_receipt(
    state: Mapping[str, Any], receipt: Mapping[str, Any], context: str
) -> None:
    for existing_delegation in state.get("delegations", {}).values():
        if not isinstance(existing_delegation, Mapping):
            continue
        lifecycle = existing_delegation.get("lifecycle_receipts", {})
        if not isinstance(lifecycle, Mapping):
            continue
        for existing_receipt in lifecycle.values():
            if not isinstance(existing_receipt, Mapping):
                continue
            if existing_receipt.get("receipt_id") == receipt["receipt_id"]:
                raise JournalError(f"{context} receipt ID is already bound to a delegation lifecycle")


def validate_cleanup_owner(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the full identity required to release one attempt-owned resource."""

    owner_fields = {
        "execution_host_id", "workspace_key", "terminal_id", "incarnation_id",
        "process_root", "provenance",
    }
    owner = _exact_fields(
        value,
        owner_fields,
        {"attempt_id", "coordinator_generation"},
        "cleanup owner",
    )
    has_attempt = "attempt_id" in owner
    has_generation = "coordinator_generation" in owner
    if has_attempt == has_generation:
        raise GraphValidationError(
            "cleanup owner must name exactly one attempt_id or coordinator_generation"
        )
    _opaque_identity(owner["execution_host_id"], "cleanup owner execution_host_id")
    if has_attempt:
        _identifier(owner["attempt_id"], "cleanup owner attempt_id")
    else:
        generation = owner["coordinator_generation"]
        if not isinstance(generation, int) or isinstance(generation, bool) or generation < 1:
            raise GraphValidationError("cleanup owner coordinator_generation must be positive")
    terminal_id = owner["terminal_id"]
    incarnation_id = owner["incarnation_id"]
    if (terminal_id is None) != (incarnation_id is None):
        raise GraphValidationError("cleanup owner terminal and incarnation identities must appear together")
    if terminal_id is not None:
        _identifier(terminal_id, "cleanup owner terminal_id")
        _identifier(incarnation_id, "cleanup owner incarnation_id")
    _workspace_key(owner["workspace_key"], "cleanup owner workspace_key")
    if owner["process_root"] is not None and (
        not isinstance(owner["process_root"], int)
        or isinstance(owner["process_root"], bool)
        or owner["process_root"] < 1
    ):
        raise GraphValidationError("cleanup owner process_root must be a positive integer or null")
    _nonempty_string(owner["provenance"], "cleanup owner provenance")
    return json.loads(json.dumps(dict(owner), sort_keys=True))


def validate_cleanup_target(kind: Any, value: Any) -> dict[str, Any] | str:
    """Validate the public cleanup target without coercing legacy journal data."""

    if kind == "process":
        target = _exact_fields(value, {"kind", "root_pid"}, set(), "process cleanup target")
        if target["kind"] != "process":
            raise GraphValidationError("process cleanup target kind must be process")
        root_pid = target["root_pid"]
        if not isinstance(root_pid, int) or isinstance(root_pid, bool) or root_pid < 1:
            raise GraphValidationError("process cleanup target root_pid must be a positive integer")
        return {"kind": "process", "root_pid": root_pid}
    return _nonempty_string(value, "cleanup target")


def _cleanup_identity_reused(
    cleanup: Mapping[str, Any], kind: str, target: dict[str, Any] | str, owner: Mapping[str, Any]
) -> bool:
    existing_owner = cleanup.get("owner")
    if (
        not isinstance(existing_owner, Mapping)
        or cleanup.get("kind") != kind
        or existing_owner.get("execution_host_id") != owner.get("execution_host_id")
        or existing_owner.get("workspace_key") != owner.get("workspace_key")
    ):
        return False
    if kind == "terminal":
        return (
            cleanup.get("target") == target
            and existing_owner.get("terminal_id") == owner.get("terminal_id")
            and existing_owner.get("incarnation_id") == owner.get("incarnation_id")
        )
    if kind == "process":
        return (
            isinstance(cleanup.get("target"), Mapping)
            and isinstance(target, Mapping)
            and cleanup["target"].get("root_pid") == target.get("root_pid")
            and existing_owner.get("process_root") == owner.get("process_root")
        )
    return False


def validate_worker_result(
    result: Mapping[str, Any],
    task: TaskContract,
    attempt_id: str,
) -> dict[str, Any]:
    """Validate one terminal worker report against its task and attempt."""

    required = {
        "task_id",
        "attempt_id",
        "outcome",
        "summary",
        "files_changed",
        "checks_run",
        "evidence_refs",
        "questions",
        "external_refs",
    }
    if not isinstance(result, Mapping):
        raise GraphValidationError("worker result must be an object")
    unknown = sorted(set(result) - required)
    missing = sorted(required - set(result))
    if unknown:
        raise GraphValidationError(f"worker result has unknown fields: {', '.join(unknown)}")
    if missing:
        raise GraphValidationError(f"worker result is missing fields: {', '.join(missing)}")
    if result["task_id"] != task.id:
        raise GraphValidationError("worker result task_id does not match the attempt")
    if result["attempt_id"] != attempt_id:
        raise GraphValidationError("worker result attempt_id does not match the attempt")
    if result["outcome"] != "reported":
        raise GraphValidationError("worker result outcome must be reported")
    _nonempty_string(result["summary"], "worker result summary")
    files = _validate_string_list(result["files_changed"], "worker result files_changed")
    if task.mode == "read" and files:
        raise GraphValidationError("read tasks cannot report changed files")
    for changed_file in files:
        if not path_is_within_scopes(changed_file, task.paths):
            raise GraphValidationError(f"changed file is outside task Paths: {changed_file}")
    checks = _validate_string_list(result["checks_run"], "worker result checks_run")
    if files and not checks:
        raise GraphValidationError("worker result checks_run must contain at least one check")
    evidence = _validate_string_list(result["evidence_refs"], "worker result evidence_refs")
    for reference in evidence:
        kind, separator, target = reference.partition(":")
        if not separator or kind not in {"file", "commit"} or not target:
            raise GraphValidationError("evidence refs must use file: or commit:")
        if kind == "file":
            normalize_repo_path(target, "file evidence path")
        elif not COMMIT_PATTERN.fullmatch(target):
            raise GraphValidationError("commit evidence must use a full SHA")
    questions = result["questions"]
    if not isinstance(questions, list) or any(not isinstance(item, Mapping) for item in questions):
        raise GraphValidationError("worker result questions must be an array of objects")
    external_refs = result["external_refs"]
    if not isinstance(external_refs, Mapping):
        raise GraphValidationError("worker result external_refs must be a scalar-valued object")
    for key, value in external_refs.items():
        if not isinstance(key, str) or not key:
            raise GraphValidationError("worker result external_refs contains an invalid key")
        if not isinstance(value, (str, int, bool, type(None))):
            raise GraphValidationError(
                f"worker result external_refs[{key!r}] has unsupported type "
                f"{type(value).__name__}"
            )
    forbidden_external_refs = sorted(
        key
        for key in external_refs
        if isinstance(key, str) and key.casefold() in BROWSER_CONTENT_FIELDS
    )
    if forbidden_external_refs:
        raise GraphValidationError(
            "worker result external_refs contains browser contents: "
            + ", ".join(forbidden_external_refs)
        )
    return json.loads(json.dumps(dict(result), sort_keys=True))


def effective_attempt_scope(
    task: TaskContract, attempt_id: str, projection: Mapping[str, Any]
) -> dict[str, Any]:
    """Return the immutable result scope for one attempt and its amendments."""

    _identifier(attempt_id, "attempt ID")
    amendments = projection.get("graph_amendments", {})
    if not isinstance(amendments, Mapping):
        raise GraphValidationError("projection graph_amendments must be an object")
    matching = sorted(
        (amendment_id, amendment)
        for amendment_id, amendment in amendments.items()
        if isinstance(amendment_id, str)
        and isinstance(amendment, Mapping)
        and amendment.get("parent_task_id") == task.id
        and amendment.get("parent_attempt_id") == attempt_id
    )
    amendment_ids = [amendment_id for amendment_id, _ in matching]
    paths = list(task.paths)
    for _amendment_id, amendment in matching:
        raw_paths = amendment.get("paths")
        if not isinstance(raw_paths, list):
            raise GraphValidationError("graph amendment paths must be an array")
        for path in raw_paths:
            normalized = normalize_repo_path(path, "graph amendment path")
            if normalized not in paths:
                paths.append(normalized)
    scope = {"attempt_id": attempt_id, "parent_task_id": task.id, "paths": paths, "amendment_ids": amendment_ids}
    payload = json.dumps(scope, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return {**scope, "digest": f"sha256:{hashlib.sha256(payload).hexdigest()}"}


def validate_coordinator_capsule(capsule: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a transcript-free fresh-coordinator handoff capsule."""

    required = {
        "schema_version",
        "protocol_version",
        "workspace_scope",
        "change",
        "run_id",
        "driver",
        "capability_summary",
        "routing_overrides",
        "coordinator_generation",
        "resume_command",
        "control_runtime",
    }
    capsule = _exact_fields(capsule, required, set(), "coordinator capsule")
    if (
        capsule["schema_version"] != SCHEMA_VERSION
        or capsule["protocol_version"] != SCHEMA_VERSION
    ):
        raise GraphValidationError("coordinator capsule schema version is unsupported")
    scope = validate_workspace_scope(capsule["workspace_scope"])
    for field in ("change", "run_id"):
        _identifier(capsule[field], f"coordinator capsule {field}")
    if capsule["run_id"] != scope["run_id"]:
        raise GraphValidationError("coordinator capsule run_id does not match workspace scope")
    if capsule["driver"] not in {"auto", "host", "orca"}:
        raise GraphValidationError("coordinator capsule driver must be auto, host, or orca")
    for field in ("capability_summary", "routing_overrides", "control_runtime"):
        if not isinstance(capsule[field], Mapping):
            raise GraphValidationError(f"coordinator capsule {field} must be an object")
    generation = capsule["coordinator_generation"]
    if not isinstance(generation, int) or isinstance(generation, bool) or generation < 1:
        raise GraphValidationError("coordinator capsule generation must be a positive integer")
    if generation != scope["coordinator_generation"]:
        raise GraphValidationError(
            "coordinator capsule generation does not match workspace scope"
        )
    _nonempty_string(capsule["resume_command"], "coordinator capsule resume_command")
    _reject_transcript_fields(capsule, "coordinator capsule")
    return json.loads(json.dumps(dict(capsule), sort_keys=True))


def empty_projection() -> dict[str, Any]:
    """Return the neutral projection before the first journal event."""

    return {
        "schema_version": SCHEMA_VERSION,
        "change": None,
        "run_id": None,
        "status": "new",
        "outcome": None,
        "base_commit": None,
        "dirty_paths": [],
        "workspace_scope": None,
        "control_runtime": None,
        "coordinator": {"id": None, "generation": 0},
        "driver": None,
        "driver_reservation": None,
        "process_decision": None,
        "graph_contract": None,
        "reduction": None,
        "execution_mode": "single_writer",
        "tasks": {},
        "attempts": {},
        "delegations": {},
        "graph_amendments": {},
        "questions": {},
        "cleanup": {},
        "browser_surfaces": {},
        "check_executions": {},
        "degradations": [],
        "last_sequence": 0,
    }


def _event_data(event: Mapping[str, Any]) -> Mapping[str, Any]:
    data = event.get("data")
    if not isinstance(data, Mapping):
        raise JournalError("event data must be an object")
    return data


def _known_task(state: Mapping[str, Any], task_id: Any) -> str:
    task_id = _nonempty_string(task_id, "event task_id")
    if task_id not in state["tasks"]:
        raise JournalError(f"event references unknown task: {task_id}")
    return task_id


def _browser_surface_attempt(state: Mapping[str, Any], request: Mapping[str, Any]) -> Mapping[str, Any]:
    """Require a surface request to use the exact reserved attempt placement."""

    task_id = _known_task(state, request["task_id"])
    attempt = state["attempts"].get(request["attempt_id"])
    if not isinstance(attempt, Mapping) or attempt.get("task_id") != task_id:
        raise JournalError("browser surface request does not belong to its task attempt")
    profile = attempt.get("execution_profile")
    if not isinstance(profile, Mapping) or not isinstance(profile.get("resolved_placement"), Mapping):
        raise JournalError("browser surface request attempt has no exact resolved placement")
    placement = profile["resolved_placement"]
    if (
        placement.get("execution_host_id") != request["execution_host_id"]
        or placement.get("workspace_key") != request["workspace_key"]
    ):
        raise JournalError("browser surface request placement diverges from its attempt")
    return attempt


def _apply_browser_surface_receipt(state: dict[str, Any], receipt: Mapping[str, Any]) -> None:
    request_id = receipt["request_id"]
    record = state["browser_surfaces"].get(request_id)
    if not isinstance(record, Mapping):
        raise JournalError("browser surface receipt references an unknown request")
    request = record.get("request")
    if not isinstance(request, Mapping):
        raise JournalError("browser surface request record is malformed")
    try:
        observed = validate_receipt_for_request(receipt, request)
    except BrowserSurfaceError as error:
        raise JournalError(f"browser surface receipt is invalid: {error}") from error
    operation = observed["operation"]
    receipts = record.get("receipts")
    if not isinstance(receipts, dict):
        raise JournalError("browser surface receipt record is malformed")
    existing = receipts.get(operation)
    if existing is not None:
        if existing != observed:
            raise JournalError("browser surface receipt replay differs from the recorded receipt")
        return
    if any(
        isinstance(prior, Mapping) and prior.get("receipt_id") == observed["receipt_id"]
        for prior in receipts.values()
    ):
        raise JournalError("browser surface receipt ID cannot be reused for another operation")
    prior_receipts = [prior for prior in receipts.values() if isinstance(prior, Mapping)]
    stable_surface = {key: value for key, value in observed["surface"].items() if key != "page_binding"}
    if prior_receipts and any(
        not isinstance(prior.get("surface"), Mapping)
        or {key: value for key, value in prior["surface"].items() if key != "page_binding"} != stable_surface
        for prior in prior_receipts
    ):
        raise JournalError("browser surface receipt targets a different exact page binding")
    pinned_page_bindings = [
        prior["surface"].get("page_binding")
        for prior in prior_receipts
        if isinstance(prior.get("surface"), Mapping) and prior["surface"].get("page_binding") is not None
    ]
    if pinned_page_bindings and any(binding != observed["surface"].get("page_binding") for binding in pinned_page_bindings):
        raise JournalError("browser surface receipt page binding drifted after bind")
    current = record.get("status")
    status = observed["status"]
    if status in {"unsupported", "unavailable", "outcome_unknown", "unverifiable"}:
        if current in {"released", "retained"}:
            raise JournalError("released browser surface cannot regress to an unavailable outcome")
        record["status"] = status
        receipts[operation] = observed
        return
    elif operation == "reserve":
        if current != "requested" or status != "reserved":
            raise JournalError("browser surface reserve requires a requested surface")
        record["status"] = "reserved"
    elif operation == "bind":
        if current not in {"requested", "reserved"} or status != "bound":
            raise JournalError("browser surface bind requires a requested or reserved surface")
        record["status"] = "bound"
    elif operation == "capture":
        if current != "bound" or status != "captured":
            raise JournalError("browser surface capture requires a settled exact page binding")
        if request["mode"] == "visible":
            bound = receipts.get("bind")
            if not isinstance(bound, Mapping) or not visible_paint_proven(bound, request):
                raise JournalError("visible browser surface capture requires prior focused native-pane paint proof")
            if not visible_paint_proven(observed, request):
                raise JournalError("visible browser surface capture requires focused native-pane paint proof")
        record["status"] = "captured"
    elif operation == "release":
        if current != "captured":
            raise JournalError("browser surface release requires a captured surface")
        attempt = state["attempts"].get(request["attempt_id"])
        capture = receipts.get("capture")
        if not isinstance(attempt, Mapping) or attempt.get("status") != "reported":
            raise JournalError("browser surface release requires a settled reported attempt")
        if not isinstance(capture, Mapping) or capture.get("surface") != observed["surface"]:
            raise JournalError("browser surface release requires durable matching capture evidence")
        capture_evidence = capture.get("capture")
        if not isinstance(capture_evidence, Mapping) or capture_evidence.get("artifact_hash") is None:
            raise JournalError("browser surface release requires durable capture evidence")
        if request["retention"] == "retain":
            if status != "retained":
                raise JournalError("retained browser surface cannot be released")
        else:
            if status == "released":
                if observed["surface"]["harness_owned"] is not True:
                    raise JournalError("browser surface cleanup requires Harness ownership")
            elif status != "retained" or observed["surface"]["harness_owned"] is not False:
                raise JournalError(
                    "unretained browser surface must release or retain a user-owned page"
                )
        record["status"] = status
    else:
        raise JournalError("browser surface receipt operation is unsupported")
    receipts[operation] = observed


def apply_event(projection: Mapping[str, Any], event: Mapping[str, Any]) -> dict[str, Any]:
    """Apply one validated event and return a fresh projection."""

    state = json.loads(json.dumps(projection))
    event_type = event["type"]
    data = _event_data(event)
    if event_type == "run_started":
        if state["status"] != "new":
            raise JournalError("run_started must be the first event")
        change = _nonempty_string(data.get("change"), "run_started change")
        run_id = _nonempty_string(data.get("run_id"), "run_started run_id")
        generation = data.get("coordinator_generation", 1)
        if not isinstance(generation, int) or isinstance(generation, bool) or generation < 1:
            raise JournalError("run_started coordinator_generation must be positive")
        raw_tasks = data.get("tasks")
        if not isinstance(raw_tasks, list) or not raw_tasks:
            raise JournalError("run_started tasks must be a non-empty array")
        workspace_scope = None
        if data.get("workspace_scope") is not None:
            try:
                workspace_scope = validate_workspace_scope(data.get("workspace_scope"))
            except GraphValidationError as error:
                raise JournalError(f"run_started workspace_scope is invalid: {error}") from error
            if workspace_scope["run_id"] != run_id:
                raise JournalError("run_started workspace_scope run_id does not match")
            if workspace_scope["coordinator_generation"] != generation:
                raise JournalError("run_started workspace_scope coordinator generation does not match")
        control_runtime = data.get("control_runtime")
        if control_runtime is not None and not isinstance(control_runtime, Mapping):
            raise JournalError("run_started control_runtime must be an object when present")
        task_states: dict[str, Any] = {}
        for raw_task in raw_tasks:
            if not isinstance(raw_task, Mapping):
                raise JournalError("run_started task must be an object")
            task_id = _nonempty_string(raw_task.get("id"), "run_started task id")
            if task_id in task_states:
                raise JournalError(f"run_started contains duplicate task: {task_id}")
            task_states[task_id] = {
                "contract": json.loads(json.dumps(dict(raw_task), sort_keys=True)),
                "status": "pending",
                "grade": None,
                "attempt_ids": [],
                "check": None,
                "hypotheses": [],
                "evidence_refs": [],
                "note": "",
                "import_receipt": None,
            }
        state.update(
            {
                "change": change,
                "run_id": run_id,
                "status": "active",
                "base_commit": data.get("base_commit"),
                "dirty_paths": list(data.get("dirty_paths", [])),
                "workspace_scope": workspace_scope,
                "control_runtime": (
                    json.loads(json.dumps(dict(control_runtime), sort_keys=True))
                    if control_runtime is not None
                    else None
                ),
                "process_decision": (
                    json.loads(json.dumps(dict(data["process_decision"]), sort_keys=True))
                    if isinstance(data.get("process_decision"), Mapping)
                    else None
                ),
                "graph_contract": (
                    json.loads(json.dumps(dict(data["graph_contract"]), sort_keys=True))
                    if isinstance(data.get("graph_contract"), Mapping)
                    else None
                ),
                "execution_mode": "single_writer",
                "tasks": task_states,
            }
        )
        state["coordinator"] = {
            "id": data.get("coordinator_id"),
            "generation": generation,
        }
    elif state["status"] == "new":
        raise JournalError("run_started must be the first event")
    else:
        reducer = _EVENT_REDUCERS.get(event_type)
        if reducer is not None:
            reducer(state, event_type, data, event)
    state["last_sequence"] = event["sequence"]
    return state


def _apply_control_event(
    state: dict[str, Any],
    event_type: str,
    data: Mapping[str, Any],
    event: Mapping[str, Any],
) -> None:
    if event_type == "coordinator_claimed":
        state["coordinator"]["id"] = _nonempty_string(
            data.get("coordinator_id"), "coordinator_claimed coordinator_id"
        )
    elif event_type in {"coordinator_transferred", "coordinator_taken_over"}:
        next_generation = data.get("coordinator_generation")
        if next_generation != state["coordinator"]["generation"] + 1:
            raise JournalError(f"{event_type} must increment coordinator_generation by one")
        state["coordinator"] = {
            "id": data.get("coordinator_id"),
            "generation": next_generation,
        }
        if state["workspace_scope"] is not None:
            state["workspace_scope"]["coordinator_generation"] = next_generation
    elif event_type == "driver_selected":
        driver = data.get("driver")
        if driver not in {"host", "orca"}:
            raise JournalError("driver_selected driver must be host or orca")
        if state["driver"] is not None and state["driver"] != driver:
            raise JournalError("the selected driver cannot change during a run")
        state["driver"] = driver
        state["driver_reservation"] = None
    elif event_type == "driver_selection_reserved":
        if state["driver"] is not None:
            raise JournalError("cannot reserve driver selection after a driver is selected")
        if state["driver_reservation"] is not None:
            raise JournalError("driver selection is already reserved")
        state["driver_reservation"] = {
            **json.loads(json.dumps(dict(data), sort_keys=True)),
            "status": "reserved",
        }
    elif event_type == "driver_selection_failed":
        if not isinstance(state["driver_reservation"], Mapping):
            raise JournalError("driver selection failure has no reservation")
        state["driver_reservation"].update(
            **json.loads(json.dumps(dict(data), sort_keys=True)),
            status="failed",
        )
    elif event_type == "task_ready":
        task_id = _known_task(state, data.get("task_id"))
        if state["tasks"][task_id]["grade"] is None:
            state["tasks"][task_id]["status"] = "ready"


def _apply_graph_event(
    state: dict[str, Any],
    event_type: str,
    data: Mapping[str, Any],
    event: Mapping[str, Any],
) -> None:
    if event_type == "delegation_requested":
        if state["workspace_scope"] is None:
            raise JournalError("delegation_requested requires a pinned workspace scope")
        try:
            intent = validate_delegation_intent(data.get("intent"), state["workspace_scope"])
        except GraphValidationError as error:
            raise JournalError(f"delegation_requested intent is invalid: {error}") from error
        if intent["expected_revision"] != state["last_sequence"]:
            raise JournalError("delegation_requested expected_revision is stale")
        if intent["intent_id"] in state["delegations"]:
            raise JournalError(f"duplicate delegation intent: {intent['intent_id']}")
        parent_task_id = _known_task(state, intent["parent_task_id"])
        parent_attempt = state["attempts"].get(intent["parent_attempt_id"])
        if not isinstance(parent_attempt, Mapping) or parent_attempt.get("task_id") != parent_task_id:
            raise JournalError("delegation parent attempt is not anchored to its parent task")
        if state["tasks"][parent_task_id]["grade"] is not None:
            raise JournalError("delegation parent task is already graded")
        if parent_attempt.get("status") not in {"running", "reported"}:
            raise JournalError("delegation parent attempt is not active")
        state["delegations"][intent["intent_id"]] = {
            "delegation_id": intent["intent_id"],
            "parent_task_id": parent_task_id,
            "parent_attempt_id": intent["parent_attempt_id"],
            "intent": intent,
            "status": "requested",
        }
    elif event_type == "graph_amended":
        amendment = _exact_fields(
            data,
            {"amendment_id", "parent_task_id", "parent_attempt_id", "paths", "reason", "coordinator_id", "coordinator_generation"},
            set(),
            "graph_amended",
        )
        amendment_id = _identifier(amendment["amendment_id"], "graph_amended amendment_id")
        if amendment_id in state["graph_amendments"]:
            raise JournalError(f"duplicate graph amendment: {amendment_id}")
        parent_task_id = _known_task(state, amendment["parent_task_id"])
        parent_attempt_id = _identifier(amendment["parent_attempt_id"], "graph_amended parent_attempt_id")
        parent_attempt = state["attempts"].get(parent_attempt_id)
        if not isinstance(parent_attempt, Mapping) or parent_attempt.get("task_id") != parent_task_id:
            raise JournalError("graph_amended parent attempt is not anchored to its parent task")
        if parent_attempt.get("status") != "reserved" or parent_attempt.get("scope_frozen") is True:
            raise JournalError("graph_amended parent attempt scope is already immutable")
        if state["tasks"][parent_task_id]["grade"] is not None:
            raise JournalError("graph_amended parent task is already graded")
        if amendment["coordinator_id"] != state["coordinator"]["id"]:
            raise JournalError("graph_amended coordinator ID does not own the current generation")
        if amendment["coordinator_generation"] != state["coordinator"]["generation"]:
            raise JournalError("graph_amended coordinator generation is stale")
        paths = _validate_string_list(amendment["paths"], "graph_amended paths")
        if not paths:
            raise JournalError("graph_amended paths must not be empty")
        for path in paths:
            normalize_repo_path(path, "graph_amended path")
        state["graph_amendments"][amendment_id] = {
            "amendment_id": amendment_id,
            "parent_task_id": parent_task_id,
            "parent_attempt_id": parent_attempt_id,
            "paths": paths,
            "reason": _nonempty_string(amendment["reason"], "graph_amended reason"),
            "coordinator_id": amendment["coordinator_id"],
            "coordinator_generation": amendment["coordinator_generation"],
        }
        parent_attempt["effective_scope"] = effective_attempt_scope(
            TaskContract(**state["tasks"][parent_task_id]["contract"]), parent_attempt_id, state
        )
    elif event_type == "process_decision_amended":
        amendment = _exact_fields(
            data,
            {"decision", "graph_contract", "reduction"},
            set(),
            "process_decision_amended",
        )
        current = state.get("process_decision")
        decision = amendment["decision"]
        if not isinstance(current, Mapping) or not isinstance(decision, Mapping):
            raise JournalError("process_decision_amended requires current and replacement decisions")
        current_revision = current.get("revision")
        if not isinstance(current_revision, int) or decision.get("revision") != current_revision + 1:
            raise JournalError("process_decision_amended replacement revision is stale")
        history = decision.get("amendments")
        if not isinstance(history, list) or len(history) != decision["revision"] - 1:
            raise JournalError("process_decision_amended history is incomplete")
        latest = history[-1]
        if (
            not isinstance(latest, Mapping)
            or latest.get("from_revision") != current_revision
            or latest.get("to_revision") != decision["revision"]
            or latest.get("from_mode") != current.get("mode")
            or latest.get("to_mode") != decision.get("mode")
        ):
            raise JournalError("process_decision_amended latest transition is inconsistent")

        graph_contract = amendment["graph_contract"]
        reduction = amendment["reduction"]
        if decision.get("mode") == "graph":
            if (
                not isinstance(graph_contract, Mapping)
                or graph_contract.get("decision_revision") != decision["revision"]
                or reduction is not None
            ):
                raise JournalError("graph amendment requires a current graph contract")
            packets = graph_contract.get("packets")
            if not isinstance(packets, list) or not isinstance(graph_contract.get("integrator"), str) or not graph_contract["integrator"]:
                raise JournalError("parallel expansion requires packets and an integration owner")
            ready_writes = []
            packet_ids = {packet.get("packet_id") for packet in packets if isinstance(packet, Mapping)}
            for task_id, task_state in state["tasks"].items():
                contract = task_state.get("contract") if isinstance(task_state, Mapping) else None
                if task_id not in packet_ids or not isinstance(contract, Mapping) or contract.get("mode") != "write" or not contract.get("check"):
                    continue
                candidate_task = TaskContract(**contract)
                if task_state.get("status") not in {"pending", "ready"} or not task_is_dispatchable(
                    [TaskContract(**item["contract"]) for item in state["tasks"].values() if isinstance(item, Mapping) and isinstance(item.get("contract"), Mapping)], state, candidate_task
                ):
                    continue
                ready_writes.append(candidate_task)
            if len(ready_writes) < 2 or any(tasks_conflict(left, right) for index, left in enumerate(ready_writes) for right in ready_writes[index + 1 :]):
                raise JournalError("parallel expansion requires two ready isolated write packets with individual checks")
            state["execution_mode"] = "parallel"
            state["reduction"] = None
        else:
            if graph_contract is not None or not isinstance(reduction, Mapping):
                raise JournalError("graph reduction requires one single-integrator plan")
            reduction = _exact_fields(
                reduction,
                {"integrator", "reason", "cleanup_plan", "retained_task_ids"},
                set(),
                "process_decision_amended reduction",
            )
            for field in ("integrator", "reason", "cleanup_plan"):
                _nonempty_string(reduction[field], f"process_decision_amended reduction {field}")
            _validate_string_list(
                reduction["retained_task_ids"],
                "process_decision_amended reduction retained_task_ids",
            )
            state["reduction"] = json.loads(json.dumps(dict(reduction), sort_keys=True))
            state["execution_mode"] = "single_writer"
        state["process_decision"] = json.loads(json.dumps(dict(decision), sort_keys=True))
        state["graph_contract"] = (
            json.loads(json.dumps(dict(graph_contract), sort_keys=True))
            if isinstance(graph_contract, Mapping)
            else None
        )


def _apply_delegation_event(
    state: dict[str, Any],
    event_type: str,
    data: Mapping[str, Any],
    event: Mapping[str, Any],
) -> None:
    if event_type == "delegation_approved":
        approval = _exact_fields(
            data,
            {"delegation_id", "paths", "context_refs", "context_revision", "execution_profile"},
            {"amendment_id"},
            "delegation_approved",
        )
        delegation_id = _identifier(approval["delegation_id"], "delegation_approved delegation_id")
        delegation = state["delegations"].get(delegation_id)
        if not isinstance(delegation, Mapping) or delegation.get("status") != "requested":
            raise JournalError("delegation_approved requires a requested delegation")
        paths = _validate_string_list(approval["paths"], "delegation_approved paths")
        context_refs = _validate_string_list(approval["context_refs"], "delegation_approved context_refs")
        if not paths:
            raise JournalError("delegation_approved paths must not be empty")
        intent = delegation["intent"]
        parent_task = TaskContract(**state["tasks"][delegation["parent_task_id"]]["contract"])
        parent_scope = effective_attempt_scope(
            parent_task, delegation["parent_attempt_id"], state
        )
        amendment_id = approval.get("amendment_id")
        amendment = state["graph_amendments"].get(amendment_id) if amendment_id else None
        if amendment is not None and (
            amendment.get("parent_task_id") != delegation["parent_task_id"]
            or amendment.get("parent_attempt_id") != delegation["parent_attempt_id"]
        ):
            raise JournalError("delegation amendment belongs to another parent attempt")
        for path in paths:
            normalize_repo_path(path, "delegation_approved path")
            if not path_is_within_scopes(path, parent_scope["paths"]):
                raise JournalError("delegation approval widens paths without a graph amendment")
            if not path_is_within_scopes(path, intent["paths"]):
                raise JournalError("delegation approval widens the requested paths")
        if not set(context_refs).issubset(intent["context_refs"]):
            raise JournalError("delegation approval widens context references")
        context_revision = _nonempty_string(approval["context_revision"], "delegation_approved context_revision")
        if state["workspace_scope"] is None:
            raise JournalError("delegation_approved requires a pinned workspace scope")
        try:
            profile = validate_execution_profile(approval["execution_profile"], state["workspace_scope"])
        except GraphValidationError as error:
            raise JournalError(f"delegation_approved execution profile is invalid: {error}") from error
        delegation.update({
            "status": "approved", "paths": paths, "context_refs": context_refs,
            "context_revision": context_revision, "execution_profile": profile,
            **({"amendment_id": amendment_id} if amendment_id else {}),
        })
    elif event_type == "delegation_rejected":
        rejection = _exact_fields(data, {"delegation_id", "reason"}, set(), "delegation_rejected")
        delegation_id = _identifier(rejection["delegation_id"], "delegation_rejected delegation_id")
        delegation = state["delegations"].get(delegation_id)
        if not isinstance(delegation, Mapping) or delegation.get("status") != "requested":
            raise JournalError("delegation_rejected requires a requested delegation")
        delegation.update({"status": "rejected", "reason": _nonempty_string(rejection["reason"], "delegation_rejected reason")})
    elif event_type == "delegation_started":
        started = _exact_fields(
            data,
            {"delegation_id", "child_attempt_id", "resource_owner", "receipt"},
            set(),
            "delegation_started",
        )
        delegation_id = _identifier(started["delegation_id"], "delegation_started delegation_id")
        delegation = state["delegations"].get(delegation_id)
        if not isinstance(delegation, Mapping) or delegation.get("status") != "approved":
            raise JournalError("delegation_started requires an approved delegation")
        parent_attempt = state["attempts"].get(delegation.get("parent_attempt_id"))
        if (
            not isinstance(parent_attempt, Mapping)
            or parent_attempt.get("task_id") != delegation.get("parent_task_id")
            or parent_attempt.get("status") not in {"running", "reported"}
            or state["tasks"][delegation["parent_task_id"]]["grade"] is not None
        ):
            raise JournalError("delegation_started requires an active anchored parent attempt")
        child_attempt_id = _identifier(started["child_attempt_id"], "delegation_started child_attempt_id")
        if child_attempt_id in state["attempts"] or any(
            item.get("child_attempt_id") == child_attempt_id
            for item in state["delegations"].values() if isinstance(item, Mapping)
        ):
            raise JournalError(f"duplicate child attempt ID: {child_attempt_id}")
        try:
            owner = validate_cleanup_owner(started["resource_owner"])
        except GraphValidationError as error:
            raise JournalError(f"delegation_started resource owner is invalid: {error}") from error
        if owner["attempt_id"] != child_attempt_id:
            raise JournalError("delegation_started resource owner does not match child attempt")
        placement = delegation["execution_profile"]["resolved_placement"]
        if (
            owner["execution_host_id"] != placement["execution_host_id"]
            or owner["workspace_key"] != placement["workspace_key"]
        ):
            raise JournalError(
                "delegation_started resource owner does not match the approved placement"
            )
        receipt = _validate_lifecycle_receipt(started["receipt"], state, "delegation_started receipt")
        _require_unclaimed_lifecycle_receipt(state, receipt, "delegation_started")
        delegation.update({
            "status": "started", "child_attempt_id": child_attempt_id,
            "resource_owner": owner,
            "lifecycle_receipts": {"started": receipt},
            "spawned_by": delegation["parent_attempt_id"],
        })
    elif event_type == "delegation_reported":
        report_data = _exact_fields(data, {"delegation_id", "result", "receipt"}, set(), "delegation_reported")
        delegation_id = _identifier(report_data["delegation_id"], "delegation_reported delegation_id")
        delegation = state["delegations"].get(delegation_id)
        if not isinstance(delegation, Mapping) or delegation.get("status") != "started":
            raise JournalError("delegation_reported requires a started delegation")
        try:
            result = validate_delegation_result(report_data["result"], delegation)
        except GraphValidationError as error:
            raise JournalError(f"delegation_reported result is invalid: {error}") from error
        receipt = _validate_lifecycle_receipt(report_data["receipt"], state, "delegation_reported receipt")
        _require_unclaimed_lifecycle_receipt(state, receipt, "delegation_reported")
        delegation.update({
            "status": "reported", "report": result,
            "lifecycle_receipts": {**delegation["lifecycle_receipts"], "reported": receipt},
        })
    elif event_type == "delegation_released":
        release = _exact_fields(data, {"delegation_id", "cleanup_id", "receipt"}, set(), "delegation_released")
        delegation_id = _identifier(release["delegation_id"], "delegation_released delegation_id")
        delegation = state["delegations"].get(delegation_id)
        if not isinstance(delegation, Mapping) or delegation.get("status") != "reported":
            raise JournalError("delegation_released requires a reported delegation")
        cleanup_id = _identifier(release["cleanup_id"], "delegation_released cleanup_id")
        cleanup = state["cleanup"].get(cleanup_id)
        if not isinstance(cleanup, Mapping):
            raise JournalError("delegation_released requires an owned cleanup")
        if cleanup.get("owner") != delegation.get("resource_owner"):
            raise JournalError("delegation_released cleanup owner does not match the child")
        terminal_cleanup_id = delegation.get("cleanup_id")
        terminal_cleanup = state["cleanup"].get(terminal_cleanup_id)
        if cleanup.get("kind") == "terminal":
            valid_terminal = cleanup.get("status") == "verified"
            if cleanup_id != terminal_cleanup_id or not valid_terminal or not cleanup.get("receipt"):
                raise JournalError("delegation_released requires verified terminal cleanup with a receipt")
        else:
            if cleanup.get("kind") != "process" or cleanup.get("status") != "verified" or not cleanup.get("receipt"):
                raise JournalError("delegation_released requires verified process cleanup with a receipt")
            if (
                cleanup.get("delegation_id") is not None
                and cleanup.get("delegation_id") != delegation_id
            ):
                raise JournalError("delegation_released process cleanup belongs to a different delegation")
            if cleanup.get("delegation_id") != delegation_id:
                if (
                    not isinstance(terminal_cleanup, Mapping)
                    or terminal_cleanup.get("delegation_id") != delegation_id
                    or terminal_cleanup.get("kind") != "terminal"
                    or terminal_cleanup.get("status") != "retained"
                    or not isinstance(terminal_cleanup.get("receipt"), Mapping)
                    or terminal_cleanup["receipt"].get("observation") != "unobserved"
                ):
                    raise JournalError("delegation_released process cleanup is not linked to the delegation")
        receipt = _validate_lifecycle_receipt(release["receipt"], state, "delegation_released receipt")
        _require_unclaimed_lifecycle_receipt(state, receipt, "delegation_released")
        delegation.update({
            "status": "released",
            "cleanup_id": cleanup_id,
            "lifecycle_receipts": {**delegation["lifecycle_receipts"], "released": receipt},
        })


def _apply_attempt_reservation_event(
    state: dict[str, Any],
    event_type: str,
    data: Mapping[str, Any],
    event: Mapping[str, Any],
) -> None:
    if event_type == "attempt_reserved":
        task_id = _known_task(state, data.get("task_id"))
        attempt_id = _nonempty_string(data.get("attempt_id"), "attempt_reserved attempt_id")
        if attempt_id in state["attempts"]:
            raise JournalError(f"duplicate attempt ID: {attempt_id}")
        if state["workspace_scope"] is None:
            raise JournalError("attempt_reserved requires a pinned workspace scope")
        try:
            reserved_scope = validate_workspace_scope(data["workspace_scope"])
            if reserved_scope != state["workspace_scope"]:
                raise JournalError("attempt_reserved workspace_scope diverges from the pinned scope")
            validate_execution_profile(data["execution_profile"], reserved_scope)
            task = TaskContract(**state["tasks"][task_id]["contract"])
            expected_scope = effective_attempt_scope(task, attempt_id, state)
            supplied_scope = data.get("effective_scope", expected_scope)
            if supplied_scope != expected_scope:
                raise JournalError("attempt_reserved effective_scope diverges from the exact amendment union")
        except (KeyError, GraphValidationError) as error:
            raise JournalError(f"attempt_reserved identity is invalid: {error}") from error
        attempt = json.loads(json.dumps(dict(data), sort_keys=True))
        attempt["effective_scope"] = expected_scope
        attempt["scope_frozen"] = False
        attempt["status"] = "reserved"
        state["attempts"][attempt_id] = attempt
        state["tasks"][task_id]["attempt_ids"].append(attempt_id)
        state["tasks"][task_id]["status"] = "reserved"
    elif event_type == "attempt_scope_frozen":
        attempt_id = _nonempty_string(data.get("attempt_id"), "attempt_scope_frozen attempt_id")
        attempt = state["attempts"].get(attempt_id)
        if not isinstance(attempt, Mapping) or attempt.get("status") != "reserved":
            raise JournalError("attempt_scope_frozen requires a reserved attempt")
        if attempt.get("scope_frozen") is True:
            raise JournalError("attempt scope is already immutable")
        task = TaskContract(**state["tasks"][str(attempt["task_id"])]["contract"])
        expected_scope = effective_attempt_scope(task, attempt_id, state)
        if data.get("effective_scope") != expected_scope or attempt.get("effective_scope") != expected_scope:
            raise JournalError("attempt_scope_frozen effective_scope diverges from the exact amendment union")
        attempt["scope_frozen"] = True


def _apply_attempt_start_event(
    state: dict[str, Any],
    event_type: str,
    data: Mapping[str, Any],
    event: Mapping[str, Any],
) -> None:
    if event_type == "attempt_started":
        task_id = _known_task(state, data.get("task_id"))
        attempt_id = _nonempty_string(data.get("attempt_id"), "attempt_started attempt_id")
        existing = state["attempts"].get(attempt_id)
        if existing is None:
            raise JournalError("attempt_started requires a reserved attempt")
        elif existing.get("status") in {"reserved", "interrupted"} and existing.get("task_id") == task_id:
            if existing.get("scope_frozen") is not True:
                raise JournalError("attempt_started requires an immutable effective scope")
            if data.get("workspace_scope") != existing.get("workspace_scope"):
                raise JournalError("attempt_started workspace_scope diverges from the reserved identity")
            if data.get("execution_profile") != existing.get("execution_profile"):
                raise JournalError("attempt_started execution_profile diverges from the reserved identity")
            if data.get("effective_scope") != existing.get("effective_scope"):
                raise JournalError("attempt_started effective_scope diverges from the reserved identity")
            started_owner = data.get("resource_owner")
            if started_owner is not None:
                try:
                    owner = validate_cleanup_owner(started_owner)
                except GraphValidationError as error:
                    raise JournalError(f"attempt_started resource_owner is invalid: {error}") from error
                if owner["attempt_id"] != attempt_id or owner["terminal_id"] is None:
                    if owner["attempt_id"] != attempt_id:
                        raise JournalError("attempt_started resource_owner does not match attempt")
            attempt = existing
            attempt.update(json.loads(json.dumps(dict(data), sort_keys=True)))
        else:
            raise JournalError(f"duplicate attempt ID: {attempt_id}")
        owner = attempt.get("resource_owner")
        cleanup_id = attempt.get("cleanup_id")
        registration = data.get("cleanup_registration")
        if isinstance(owner, Mapping):
            if not isinstance(cleanup_id, str) or not isinstance(registration, Mapping):
                raise JournalError("owned Orca attempt_started requires embedded cleanup registration")
            registration = _exact_fields(
                registration,
                {"cleanup_id", "kind", "target", "owner", "external_refs"},
                set(),
                "attempt_started cleanup_registration",
            )
            if (
                registration["cleanup_id"] != cleanup_id
                or registration["owner"] != owner
                or registration["external_refs"] != attempt.get("external_refs")
                or not isinstance(registration["target"], str)
                or not registration["target"]
                or registration["kind"] not in {"terminal", "other"}
            ):
                raise JournalError("attempt_started cleanup registration is not exact")
            expected_kind = "terminal" if owner["terminal_id"] is not None else "other"
            expected_target = owner["terminal_id"] if owner["terminal_id"] is not None else registration["target"]
            if registration["kind"] != expected_kind or registration["target"] != expected_target:
                raise JournalError("attempt_started cleanup registration does not match resource identity")
            scope = attempt.get("workspace_scope")
            workspace = scope.get("execution_workspace") if isinstance(scope, Mapping) else None
            if (
                not isinstance(workspace, Mapping)
                or owner.get("execution_host_id") != workspace.get("execution_host_id")
                or owner.get("workspace_key") != workspace.get("workspace_key")
            ):
                raise JournalError("cleanup registration owner does not match the attempt workspace")
            if owner["terminal_id"] is None:
                refs = attempt.get("external_refs")
                if not isinstance(refs, Mapping):
                    raise JournalError("provider cleanup requires authoritative external references")
                runtime_id = refs.get("runtime_id")
                worktree_id = refs.get("worktree_id")
                run_id = refs.get("run_id")
                dispatch_id = refs.get("dispatch_id")
                if (
                    refs.get("tier") != "supervised"
                    or registration["target"] != dispatch_id
                    or not all(isinstance(value, str) and value for value in (runtime_id, worktree_id, run_id, dispatch_id))
                    or owner.get("provenance")
                    != f"orca-supervised:{runtime_id}:{worktree_id}:{run_id}:{dispatch_id}"
                ):
                    raise JournalError("provider cleanup registration is not bound to the authoritative receipt")
            else:
                refs = registration["external_refs"]
                terminal = refs.get("terminal") if isinstance(refs, Mapping) else None
                ownership = terminal.get("ownership") if isinstance(terminal, Mapping) else None
                if (
                    refs.get("tier") != "tracked-terminal"
                    or not isinstance(ownership, Mapping)
                    or ownership.get("attempt_id") != attempt_id
                    or ownership.get("run_id") != refs.get("run_id")
                    or ownership.get("dispatch_id") != refs.get("dispatch_id")
                    or terminal.get("handle") != owner["terminal_id"]
                    or terminal.get("incarnation_id") != owner["incarnation_id"]
                    or terminal.get("process_root") != owner["process_root"]
                    or owner.get("provenance") != f"orca:{refs.get('run_id')}:{refs.get('dispatch_id')}"
                ):
                    raise JournalError("terminal cleanup registration is not bound to the authoritative receipt")
            existing_cleanup = state["cleanup"].get(cleanup_id)
            normalized_cleanup = {
                "cleanup_id": cleanup_id,
                "kind": registration["kind"],
                "target": registration["target"],
                "attempt_id": attempt_id,
                "owner": json.loads(json.dumps(dict(owner), sort_keys=True)),
                "external_refs": json.loads(json.dumps(dict(registration["external_refs"]), sort_keys=True)),
                "status": "pending",
            }
            if existing_cleanup is None:
                state["cleanup"][cleanup_id] = normalized_cleanup
            elif any(existing_cleanup.get(key) != value for key, value in normalized_cleanup.items() if key != "status"):
                raise JournalError("attempt_started cleanup registration diverges from persisted cleanup")
        elif cleanup_id is not None or registration is not None:
            raise JournalError("unowned attempt_started cannot register cleanup")
        attempt["status"] = "running"
        state["tasks"][task_id]["status"] = "running"
    elif event_type in {"attempt_start_failed", "attempt_abandoned"}:
        attempt_id = _nonempty_string(data.get("attempt_id"), f"{event_type} attempt_id")
        if attempt_id not in state["attempts"]:
            raise JournalError(f"{event_type} references unknown attempt: {attempt_id}")
        attempt = state["attempts"][attempt_id]
        if attempt["status"] not in {"reserved", "running", "interrupted"}:
            raise JournalError(f"attempt cannot transition from {attempt['status']}: {attempt_id}")
        if event_type == "attempt_abandoned":
            pending_cleanup = pending_cleanup_ids_for_attempt(state, attempt_id)
            if attempt.get("post_start_unresolved") is True:
                if (
                    pending_cleanup
                    or not any(
                        isinstance(record, Mapping)
                        and attempt_id in _cleanup_attempt_ids(record)
                        and record.get("status") in {"verified", "retained"}
                        for record in state["cleanup"].values()
                    )
                ):
                    raise JournalError(
                        "attempt_abandoned requires verified or retained post-start cleanup"
                    )
            elif pending_cleanup:
                raise JournalError(
                    "attempt_abandoned requires terminal cleanup: "
                    + ", ".join(pending_cleanup)
                )
        attempt.update(json.loads(json.dumps(dict(data), sort_keys=True)))
        if event_type == "attempt_start_failed" and isinstance(data.get("resource_owner"), Mapping):
            owner = validate_cleanup_owner(data["resource_owner"])
            registration = _exact_fields(
                data.get("cleanup_registration"),
                {"cleanup_id", "kind", "target", "owner", "external_refs"},
                set(),
                "attempt_start_failed cleanup_registration",
            )
            cleanup_id = data.get("cleanup_id")
            if (
                owner["attempt_id"] != attempt_id
                or registration["owner"] != owner
                or not isinstance(registration["external_refs"], Mapping)
                or registration["cleanup_id"] != cleanup_id
                or not isinstance(cleanup_id, str)
                or cleanup_id in state["cleanup"]
            ):
                raise JournalError("attempt_start_failed cleanup registration is not exact")
            expected_kind = "terminal" if owner["terminal_id"] is not None else "other"
            expected_target = owner["terminal_id"] or registration["target"]
            if registration["kind"] != expected_kind or registration["target"] != expected_target:
                raise JournalError("attempt_start_failed cleanup registration does not match owner")
            scope = attempt.get("workspace_scope")
            workspace = scope.get("execution_workspace") if isinstance(scope, Mapping) else None
            if (
                not isinstance(workspace, Mapping)
                or owner.get("execution_host_id") != workspace.get("execution_host_id")
                or owner.get("workspace_key") != workspace.get("workspace_key")
            ):
                raise JournalError("failed cleanup owner does not match the attempt workspace")
            if owner["terminal_id"] is None:
                evidence = data.get("receipt")
                refs = evidence.get("returned_refs") if isinstance(evidence, Mapping) else None
                if not isinstance(refs, Mapping) or registration["external_refs"] != refs:
                    raise JournalError("failed provider cleanup requires authoritative returned references")
                runtime_id = refs.get("runtime_id")
                worktree_id = refs.get("worktree_id")
                run_id = refs.get("run_id")
                dispatch_id = refs.get("dispatch_id")
                if (
                    refs.get("tier") != "supervised"
                    or registration["target"] != dispatch_id
                    or not all(isinstance(value, str) and value for value in (runtime_id, worktree_id, run_id, dispatch_id))
                    or owner.get("provenance")
                    != f"orca-supervised:{runtime_id}:{worktree_id}:{run_id}:{dispatch_id}"
                ):
                    raise JournalError("failed provider cleanup registration is not bound to returned references")
            else:
                evidence = data.get("receipt")
                refs = evidence.get("returned_refs") if isinstance(evidence, Mapping) else None
                terminal = refs.get("terminal") if isinstance(refs, Mapping) else None
                ownership = terminal.get("ownership") if isinstance(terminal, Mapping) else None
                if (
                    not isinstance(refs, Mapping)
                    or registration["external_refs"] != refs
                    or refs.get("tier") != "tracked-terminal"
                    or not isinstance(ownership, Mapping)
                    or ownership.get("attempt_id") != attempt_id
                    or ownership.get("run_id") != refs.get("run_id")
                    or ownership.get("dispatch_id") != refs.get("dispatch_id")
                    or terminal.get("handle") != owner["terminal_id"]
                    or terminal.get("incarnation_id") != owner["incarnation_id"]
                    or terminal.get("process_root") != owner["process_root"]
                    or owner.get("provenance") != f"orca:{refs.get('run_id')}:{refs.get('dispatch_id')}"
                ):
                    raise JournalError("failed terminal cleanup registration is not bound to returned references")
            state["cleanup"][cleanup_id] = {
                "cleanup_id": cleanup_id,
                "kind": registration["kind"],
                "target": registration["target"],
                "attempt_id": attempt_id,
                "owner": owner,
                "external_refs": json.loads(json.dumps(dict(registration["external_refs"]), sort_keys=True)),
                "status": "pending",
            }
        attempt["status"] = "interrupted" if event_type == "attempt_start_failed" else "abandoned"
        state["tasks"][attempt["task_id"]]["status"] = attempt["status"]


def _apply_attempt_result_event(
    state: dict[str, Any],
    event_type: str,
    data: Mapping[str, Any],
    event: Mapping[str, Any],
) -> None:
    if event_type == "attempt_provider_result_rejected":
        try:
            rejection = _exact_fields(
                data,
                {"task_id", "attempt_id", "candidate"},
                set(),
                "attempt_provider_result_rejected",
            )
            attempt_id = _identifier(
                rejection["attempt_id"], "attempt_provider_result_rejected attempt_id"
            )
            candidate = _exact_fields(
                rejection["candidate"],
                {"evidence_ref", "sha256", "byte_length", "reason"},
                set(),
                "attempt_provider_result_rejected candidate",
            )
            evidence_ref = _nonempty_string(
                candidate["evidence_ref"], "attempt_provider_result_rejected evidence_ref"
            )
            if not evidence_ref.startswith("file:"):
                raise GraphValidationError(
                    "attempt_provider_result_rejected evidence_ref must use file:"
                )
            normalize_repo_path(
                evidence_ref.removeprefix("file:"),
                "attempt_provider_result_rejected evidence path",
            )
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(candidate["sha256"])):
                raise GraphValidationError(
                    "attempt_provider_result_rejected sha256 must be sha256"
                )
            byte_length = candidate["byte_length"]
            if not isinstance(byte_length, int) or isinstance(byte_length, bool) or byte_length < 1:
                raise GraphValidationError(
                    "attempt_provider_result_rejected byte_length must be positive"
                )
            _nonempty_string(candidate["reason"], "attempt_provider_result_rejected reason")
        except GraphValidationError as error:
            raise JournalError(f"attempt_provider_result_rejected is invalid: {error}") from error
        attempt = state["attempts"].get(attempt_id)
        if not isinstance(attempt, Mapping):
            raise JournalError(
                f"attempt_provider_result_rejected references unknown attempt: {attempt_id}"
            )
        task_id = _known_task(state, rejection["task_id"])
        if attempt.get("task_id") != task_id:
            raise JournalError(
                "attempt_provider_result_rejected task does not match its attempt"
            )
        if attempt.get("status") != "running":
            raise JournalError(
                "attempt_provider_result_rejected requires a running attempt"
            )
        if attempt.get("provider_result_rejection") is not None:
            raise JournalError(
                f"attempt already has a rejected provider result: {attempt_id}"
            )
        attempt["provider_result_rejection"] = json.loads(
            json.dumps(dict(candidate), sort_keys=True)
        )
    elif event_type == "attempt_result_quarantined":
        try:
            quarantine = _exact_fields(
                data,
                {
                    "task_id",
                    "attempt_id",
                    "idempotency_key",
                    "original_path",
                    "quarantine_path",
                    "sha256",
                    "byte_length",
                    "validation_error_code",
                    "generation",
                    "revision",
                    "receipt_path",
                },
                set(),
                "attempt_result_quarantined",
            )
            task_id = _known_task(state, quarantine["task_id"])
            attempt_id = _identifier(
                quarantine["attempt_id"], "attempt_result_quarantined attempt_id"
            )
            _identifier(
                quarantine["idempotency_key"],
                "attempt_result_quarantined idempotency_key",
            )
            original_path = normalize_repo_path(
                _nonempty_string(
                    quarantine["original_path"],
                    "attempt_result_quarantined original_path",
                ),
                "attempt_result_quarantined original_path",
            )
            quarantine_path = normalize_repo_path(
                _nonempty_string(
                    quarantine["quarantine_path"],
                    "attempt_result_quarantined quarantine_path",
                ),
                "attempt_result_quarantined quarantine_path",
            )
            receipt_path = normalize_repo_path(
                _nonempty_string(
                    quarantine["receipt_path"],
                    "attempt_result_quarantined receipt_path",
                ),
                "attempt_result_quarantined receipt_path",
            )
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(quarantine["sha256"])):
                raise GraphValidationError("attempt_result_quarantined sha256 must be sha256")
            byte_length = quarantine["byte_length"]
            if not isinstance(byte_length, int) or isinstance(byte_length, bool) or byte_length < 1:
                raise GraphValidationError("attempt_result_quarantined byte_length must be positive")
            error_code = _nonempty_string(
                quarantine["validation_error_code"],
                "attempt_result_quarantined validation_error_code",
            )
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", error_code):
                raise GraphValidationError(
                    "attempt_result_quarantined validation_error_code is invalid"
                )
            for field in ("generation", "revision"):
                value = quarantine[field]
                if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                    raise GraphValidationError(
                        f"attempt_result_quarantined {field} must be positive"
                    )
        except GraphValidationError as error:
            raise JournalError(f"attempt_result_quarantined is invalid: {error}") from error
        attempt = state["attempts"].get(attempt_id)
        if not isinstance(attempt, Mapping):
            raise JournalError(
                f"attempt_result_quarantined references unknown attempt: {attempt_id}"
            )
        if attempt.get("task_id") != task_id:
            raise JournalError("attempt_result_quarantined task does not match its attempt")
        if attempt.get("status") != "running":
            raise JournalError("attempt_result_quarantined requires a running attempt")
        expected_prefix = f"openspec/runs/{state['change']}/{state['run_id']}/"
        expected_original = f"{expected_prefix}results/{attempt_id}.json"
        expected_quarantine = (
            f"{expected_prefix}artifacts/result-quarantine/sha256/"
            f"{str(quarantine['sha256']).removeprefix('sha256:')}.json"
        )
        expected_receipt_prefix = f"{expected_prefix}artifacts/result-quarantine/receipts/"
        if (
            original_path != expected_original
            or quarantine_path != expected_quarantine
            or not receipt_path.startswith(expected_receipt_prefix)
            or receipt_path != f"{expected_receipt_prefix}{quarantine['idempotency_key']}.json"
        ):
            raise JournalError("attempt_result_quarantined paths are outside the canonical run quarantine")
        if quarantine["generation"] > event["coordinator_generation"]:
            raise JournalError("attempt_result_quarantined generation is newer than its event")
        if quarantine["revision"] > event["sequence"]:
            raise JournalError("attempt_result_quarantined revision is newer than its event")
        if attempt.get("result_quarantine") is not None:
            raise JournalError(f"attempt already has a quarantined result: {attempt_id}")
        for existing_attempt in state["attempts"].values():
            if not isinstance(existing_attempt, Mapping):
                continue
            existing = existing_attempt.get("result_quarantine")
            if isinstance(existing, Mapping) and existing.get("idempotency_key") == quarantine["idempotency_key"]:
                raise JournalError("attempt_result_quarantined idempotency key is already claimed")
        attempt["result_quarantine"] = json.loads(json.dumps(dict(quarantine), sort_keys=True))
        attempt["transport_failure"] = True
    elif event_type == "attempt_observed":
        attempt_id = _nonempty_string(data.get("attempt_id"), "attempt_observed attempt_id")
        if attempt_id not in state["attempts"]:
            raise JournalError(f"attempt_observed references unknown attempt: {attempt_id}")
        if "cursor" in data:
            raw_cursor = data.get("cursor")
            if isinstance(raw_cursor, Mapping):
                try:
                    cursor = _validate_cursor(raw_cursor, "attempt_observed cursor")
                except GraphValidationError as error:
                    raise JournalError(f"attempt_observed cursor is invalid: {error}") from error
            elif raw_cursor is None:
                cursor = None
            else:
                cursor = _nonempty_string(raw_cursor, "attempt_observed cursor")
            state["attempts"][attempt_id]["cursor"] = cursor
        state["attempts"][attempt_id]["last_poll_receipt"] = data.get("receipt_path")
    elif event_type == "driver_degraded":
        state["degradations"].append(json.loads(json.dumps(dict(data), sort_keys=True)))


def _apply_interaction_event(
    state: dict[str, Any],
    event_type: str,
    data: Mapping[str, Any],
    event: Mapping[str, Any],
) -> None:
    if event_type == "question_opened":
        attempt_id = _nonempty_string(data.get("attempt_id"), "question_opened attempt_id")
        if attempt_id not in state["attempts"]:
            raise JournalError(f"question references unknown attempt: {attempt_id}")
        question_id = _nonempty_string(data.get("question_id"), "question_opened question_id")
        if question_id in state["questions"]:
            raise JournalError(f"duplicate question ID: {question_id}")
        versioned = "actor" in data or "prompt" in data
        try:
            if versioned:
                _exact_fields(
                    data,
                    {"question_id", "attempt_id", "actor", "prompt"},
                    {"receipt_path", "delivery_id"},
                    "question_opened versioned payload",
                )
                _validate_actor_envelope(data["actor"], "question_opened actor")
                _nonempty_string(data["prompt"], "question_opened prompt")
            else:
                _exact_fields(
                    data,
                    {"question_id", "attempt_id", "body", "receipt_path"},
                    {"delivery_id"},
                    "question_opened legacy payload",
                )
                _nonempty_string(data["body"], "question_opened body")
                _nonempty_string(data["receipt_path"], "question_opened receipt_path")
            if "delivery_id" in data and (versioned or data["delivery_id"] is not None):
                _nonempty_string(data["delivery_id"], "question_opened delivery_id")
        except GraphValidationError as error:
            raise JournalError(f"question_opened is invalid: {error}") from error
        state["questions"][question_id] = {
            **json.loads(json.dumps(dict(data), sort_keys=True)),
            "status": "open",
        }
    elif event_type == "question_answered":
        question_id = _nonempty_string(data.get("question_id"), "question_answered question_id")
        if question_id not in state["questions"]:
            raise JournalError(f"answer references unknown question: {question_id}")
        if state["questions"][question_id]["status"] != "open":
            raise JournalError(f"question already answered: {question_id}")
        state["questions"][question_id]["status"] = "answered"
        state["questions"][question_id]["answer"] = data.get("answer")
    elif event_type == "worker_reported":
        attempt_id = _nonempty_string(data.get("attempt_id"), "worker_reported attempt_id")
        if attempt_id not in state["attempts"]:
            raise JournalError(f"report references unknown attempt: {attempt_id}")
        attempt = state["attempts"][attempt_id]
        if attempt["status"] != "running":
            raise JournalError(f"attempt already has a terminal report: {attempt_id}")
        if attempt.get("result_quarantine") is not None:
            raise JournalError(f"attempt result slot is quarantined: {attempt_id}")
        task_id = attempt["task_id"]
        if data.get("task_id", task_id) != task_id:
            raise JournalError("worker report task does not match its attempt")
        report_scope = data.get("effective_scope")
        if report_scope != attempt.get("effective_scope"):
            raise JournalError("worker report effective_scope diverges from the attempt")
        attempt["status"] = "reported"
        attempt["report"] = json.loads(json.dumps(dict(data), sort_keys=True))
        state["tasks"][task_id]["status"] = "reported"
        decision = state["tasks"][task_id].get("coordinator_decision")
        if isinstance(decision, Mapping) and decision.get("action") in {"amend_acceptance", "amend_paths", "regroup"}:
            state["tasks"][task_id]["decision_consumed"] = True


def _apply_finding_event(
    state: dict[str, Any],
    event_type: str,
    data: Mapping[str, Any],
    event: Mapping[str, Any],
) -> None:
    if event_type == "attempt_check_rejected":
        rejection = _exact_fields(
            data,
            {"task_id", "attempt_id", "hypothesis"},
            set(),
            "attempt_check_rejected",
        )
        task_id = _known_task(state, rejection["task_id"])
        attempt_id = _identifier(
            rejection["attempt_id"], "attempt_check_rejected attempt_id"
        )
        hypothesis = _nonempty_string(
            rejection["hypothesis"], "attempt_check_rejected hypothesis"
        )
        if " ".join(hypothesis.split()) != hypothesis:
            raise JournalError("attempt_check_rejected hypothesis must be canonical")
        attempt = state["attempts"].get(attempt_id)
        if not isinstance(attempt, Mapping) or attempt.get("task_id") != task_id:
            raise JournalError("attempt_check_rejected task does not match its attempt")
        task = state["tasks"][task_id]
        if task["grade"] is not None:
            raise JournalError(f"cannot reject a graded task: {task_id}")
        if attempt.get("status") != "reported":
            raise JournalError("attempt_check_rejected requires a reported attempt")
        if not task["attempt_ids"] or task["attempt_ids"][-1] != attempt_id:
            raise JournalError("attempt_check_rejected requires the latest task attempt")
        check = attempt.get("check")
        if (
            not isinstance(check, Mapping)
            or check.get("attempt_id") != attempt_id
            or check.get("status") != "failed"
            or not isinstance(check.get("exit_code"), int)
            or isinstance(check.get("exit_code"), bool)
            or check.get("exit_code") == 0
        ):
            raise JournalError("attempt_check_rejected requires the latest attempt's failed check")
        pending_cleanup = pending_cleanup_ids_for_attempt(state, attempt_id)
        if pending_cleanup:
            raise JournalError(
                "attempt_check_rejected requires settled attempt cleanup: "
                + ", ".join(pending_cleanup)
            )
        if hypothesis in task["hypotheses"]:
            raise JournalError(f"duplicate repair hypothesis for task {task_id}")
        if len(task["hypotheses"]) >= 2:
            raise JournalError(f"task {task_id} reached the repair hypothesis cap")
        attempt["check_rejection"] = {"hypothesis": hypothesis}
        attempt["status"] = "check-rejected"
        task["hypotheses"].append(hypothesis)
        task["status"] = "pending"
        task["check"] = None
    elif event_type == "finding_recorded":
        try:
            finding = validate_finding(data)
        except GraphValidationError as error:
            raise JournalError(f"finding_recorded is invalid: {error}") from error
        task_id = _known_task(state, finding["task_id"])
        attempt_id = finding["attempt_id"]
        attempt = state["attempts"].get(attempt_id)
        if not isinstance(attempt, Mapping) or attempt.get("task_id") != task_id:
            raise JournalError("finding_recorded attempt does not match its task")
        if finding["finding_id"] in state.setdefault("findings", {}):
            if state["findings"][finding["finding_id"]] != finding:
                raise JournalError("finding_recorded ID was reused with different content")
            return state
        state["findings"][finding["finding_id"]] = finding
    elif event_type == "coordinator_decision_recorded":
        decision = _exact_fields(
            data, {"decision_id", "task_id", "action", "note"}, set(),
            "coordinator_decision_recorded",
        )
        decision_id = _identifier(decision["decision_id"], "coordinator decision ID")
        task_id = _known_task(state, decision["task_id"])
        action = decision["action"]
        if action not in {"amend_acceptance", "amend_paths", "regroup", "accept_check", "input_required", "blocked"}:
            raise JournalError("coordinator decision action is invalid")
        _nonempty_string(decision["note"], "coordinator decision note")
        existing = state.setdefault("coordinator_decisions", {}).get(decision_id)
        if existing is not None:
            if existing != dict(decision):
                raise JournalError("coordinator decision ID was reused with different content")
            return state
        task = state["tasks"][task_id]
        attempt_ids = task.get("attempt_ids", [])
        latest = state["attempts"].get(attempt_ids[-1]) if attempt_ids else None
        if not isinstance(latest, Mapping) or latest.get("status") not in {
            "reported", "check-rejected", "audit-rejected", "audit-exhausted",
        }:
            raise JournalError("coordinator decision requires the latest reported or audit-exhausted attempt")
        latest_check = latest.get("check")
        if not isinstance(latest_check, Mapping) or latest_check.get("attempt_id") != attempt_ids[-1]:
            raise JournalError("coordinator decision requires the latest attempt's own check")
        if pending_cleanup_ids_for_attempt(state, attempt_ids[-1]):
            raise JournalError("coordinator decision requires settled attempt cleanup")
        technical_attempts = sum(
            1 for attempt_id in attempt_ids
            for candidate in [state["attempts"].get(attempt_id)]
            if isinstance(candidate, Mapping)
            and (isinstance(candidate.get("report"), Mapping)
                 or isinstance(candidate.get("check"), Mapping)
                 or candidate.get("status") in {"reported", "audit-rejected", "check-rejected", "audit-exhausted"})
        )
        if technical_attempts < 2:
            raise JournalError("coordinator decision requires two technical attempts")
        if action == "accept_check" and latest.get("status") != "reported":
            raise JournalError("accept_check requires the latest reported attempt")
        if action == "accept_check" and (
            latest_check.get("status") != "passed" or latest_check.get("exit_code") != 0
        ):
            raise JournalError("accept_check requires a passing latest check")
        unresolved_blocking = _unresolved_blocking_findings(
            state, task_id, attempt_ids[-1]
        )
        if action == "accept_check" and unresolved_blocking:
            raise JournalError("accept_check requires all blocking findings to be resolved")
        if action == "blocked":
            task["grade"] = "blocked"
            task["status"] = "blocked"
        elif action == "input_required":
            task["status"] = "pending"
        elif action == "accept_check":
            task["grade"] = "pass"
            task["status"] = "pass"
            _carry_forward_hardening(state, task_id, attempt_ids[-1])
        elif action in {"amend_acceptance", "amend_paths", "regroup"}:
            latest["status"] = "superseded"
            task["status"] = "pending"
        task["coordinator_decision"] = dict(decision)
        state["coordinator_decisions"][decision_id] = dict(decision)


def _apply_attempt_audit_event(
    state: dict[str, Any],
    event_type: str,
    data: Mapping[str, Any],
    event: Mapping[str, Any],
) -> None:
    if event_type == "attempt_audit_rejected":
        try:
            rejection = _exact_fields(
                data,
                {"rejection_id", "task_id", "attempt_id", "finding_refs", "hypothesis"},
                set(),
                "attempt_audit_rejected",
            )
            rejection_id = _identifier(
                rejection["rejection_id"], "attempt_audit_rejected rejection_id"
            )
            attempt_id = _identifier(
                rejection["attempt_id"], "attempt_audit_rejected attempt_id"
            )
            finding_refs = _validate_audit_finding_refs(rejection["finding_refs"])
            hypothesis = _nonempty_string(
                rejection["hypothesis"], "attempt_audit_rejected hypothesis"
            )
            if " ".join(hypothesis.split()) != hypothesis:
                raise GraphValidationError(
                    "attempt_audit_rejected hypothesis must be canonical"
                )
        except GraphValidationError as error:
            raise JournalError(f"attempt_audit_rejected is invalid: {error}") from error
        attempt = state["attempts"].get(attempt_id)
        if not isinstance(attempt, Mapping):
            raise JournalError(
                f"attempt_audit_rejected references unknown attempt: {attempt_id}"
            )
        task_id = _known_task(state, rejection["task_id"])
        if attempt.get("task_id") != task_id:
            raise JournalError("attempt_audit_rejected task does not match its attempt")
        task = state["tasks"][task_id]
        if task["grade"] is not None:
            raise JournalError(f"cannot reject a graded task: {task_id}")
        if attempt.get("status") != "reported":
            raise JournalError(
                f"attempt_audit_rejected requires a reported attempt: {attempt_id}"
            )
        if not task["attempt_ids"] or task["attempt_ids"][-1] != attempt_id:
            raise JournalError("attempt_audit_rejected requires the latest task attempt")
        for existing_attempt in state["attempts"].values():
            existing_rejection = existing_attempt.get("audit_rejection", {})
            if (
                isinstance(existing_rejection, Mapping)
                and existing_rejection.get("rejection_id") == rejection_id
            ):
                raise JournalError(
                    f"duplicate attempt audit rejection ID: {rejection_id}"
                )
        current_check = task.get("check")
        attempt_check = attempt.get("check")
        if (
            not isinstance(current_check, Mapping)
            or current_check.get("attempt_id") != attempt_id
            or current_check.get("status") != "passed"
            or current_check.get("exit_code") != 0
            or attempt_check != current_check
        ):
            raise JournalError(
                "attempt_audit_rejected requires the latest attempt's passing check"
            )
        if hypothesis in task["hypotheses"]:
            raise JournalError(f"duplicate repair hypothesis for task {task_id}")
        if len(task["hypotheses"]) >= 2:
            raise JournalError(f"task {task_id} reached the repair hypothesis cap")
        pending_cleanup = pending_cleanup_ids_for_attempt(state, attempt_id)
        if pending_cleanup:
            raise JournalError(
                "attempt_audit_rejected requires settled attempt cleanup: "
                + ", ".join(pending_cleanup)
            )
        findings = state.get("findings", {})
        if not isinstance(findings, Mapping) or not finding_refs:
            raise JournalError("attempt_audit_rejected requires registered structured findings")
        for evidence_ref in finding_refs:
            matches = [
                finding for finding in findings.values()
                if isinstance(finding, Mapping) and finding.get("evidence_ref") == evidence_ref
            ]
            if len(matches) != 1:
                raise JournalError("attempt_audit_rejected requires exact registered evidence_ref")
            finding = matches[0]
            if (
                finding.get("task_id") != task_id
                or finding.get("attempt_id") != attempt_id
                or finding.get("classification") not in BLOCKING_FINDING_CLASSIFICATIONS
            ):
                raise JournalError("attempt_audit_rejected finding is not blocking or task/attempt exact")
        attempt["check"] = json.loads(json.dumps(dict(current_check), sort_keys=True))
        attempt["status"] = "audit-rejected"
        attempt["audit_rejection"] = {
            "rejection_id": rejection_id,
            "finding_refs": list(finding_refs),
            "hypothesis": hypothesis,
        }
        task["hypotheses"].append(hypothesis)
        task["status"] = "pending"
        task["check"] = None
    elif event_type == "attempt_audit_exhausted":
        try:
            exhaustion = _exact_fields(
                data,
                {"rejection_id", "task_id", "attempt_id", "finding_refs", "hypothesis"},
                set(),
                "attempt_audit_exhausted",
            )
            rejection_id = _identifier(
                exhaustion["rejection_id"], "attempt_audit_exhausted rejection_id"
            )
            task_id = _known_task(state, exhaustion["task_id"])
            attempt_id = _identifier(
                exhaustion["attempt_id"], "attempt_audit_exhausted attempt_id"
            )
            finding_refs = _validate_audit_finding_refs(exhaustion["finding_refs"])
            hypothesis = _nonempty_string(
                exhaustion["hypothesis"], "attempt_audit_exhausted hypothesis"
            )
            if " ".join(hypothesis.split()) != hypothesis:
                raise GraphValidationError(
                    "attempt_audit_exhausted hypothesis must be canonical"
                )
        except GraphValidationError as error:
            raise JournalError(f"attempt_audit_exhausted is invalid: {error}") from error
        attempt = state["attempts"].get(attempt_id)
        if not isinstance(attempt, Mapping) or attempt.get("task_id") != task_id:
            raise JournalError("attempt_audit_exhausted task does not match its attempt")
        task = state["tasks"][task_id]
        if task["grade"] is not None:
            raise JournalError(f"cannot exhaust a graded task: {task_id}")
        if attempt.get("status") != "reported":
            raise JournalError("attempt_audit_exhausted requires a reported attempt")
        if not task["attempt_ids"] or task["attempt_ids"][-1] != attempt_id:
            raise JournalError("attempt_audit_exhausted requires the latest task attempt")
        for existing_attempt in state["attempts"].values():
            existing = existing_attempt.get("audit_exhaustion", {})
            if isinstance(existing, Mapping) and existing.get("rejection_id") == rejection_id:
                raise JournalError(
                    f"duplicate attempt audit exhaustion ID: {rejection_id}"
                )
        check = attempt.get("check")
        if (
            not isinstance(check, Mapping)
            or check.get("attempt_id") != attempt_id
            or check.get("status") != "passed"
            or check.get("exit_code") != 0
            or task.get("check") != check
        ):
            raise JournalError(
                "attempt_audit_exhausted requires the latest attempt's passing check"
            )
        if not (hypothesis in task["hypotheses"] or len(task["hypotheses"]) >= 2):
            raise JournalError("attempt_audit_exhausted requires a repeated hypothesis or exhausted cap")
        pending_cleanup = pending_cleanup_ids_for_attempt(state, attempt_id)
        if pending_cleanup:
            raise JournalError(
                "attempt_audit_exhausted requires settled attempt cleanup: "
                + ", ".join(pending_cleanup)
            )
        attempt["status"] = "audit-exhausted"
        attempt["audit_exhaustion"] = {
            "rejection_id": rejection_id,
            "finding_refs": list(finding_refs),
            "hypothesis": hypothesis,
        }
        task["status"] = "blocked"
        task["grade"] = "blocked"
        task["note"] = "Audit repair hypotheses are exhausted."


def _apply_check_execution_event(
    state: dict[str, Any],
    event_type: str,
    data: Mapping[str, Any],
    event: Mapping[str, Any],
) -> None:
    if event_type == "check_execution_recorded":
        required = {
            "execution_id", "command_digest", "source_snapshot_digest",
            "execution_policy_digest", "timeout_seconds", "output_cap_bytes",
            "owner_generation", "lifecycle", "artifact_ref", "cleanup_ref", "cleanup_id",
            "process_root", "process_group", "process_start_identity", "cleanup_authority",
            "cleanup_authority_id", "consumer_ref",
        }
        _exact_fields(data, required, set(), "check_execution_recorded")
        execution_id = _identifier(data["execution_id"], "check_execution_recorded execution_id")
        command_digest = _nonempty_string(data["command_digest"], "check_execution_recorded command_digest")
        snapshot_digest = _nonempty_string(data["source_snapshot_digest"], "check_execution_recorded source_snapshot_digest")
        policy_digest = _nonempty_string(data["execution_policy_digest"], "check_execution_recorded execution_policy_digest")
        timeout_seconds = data["timeout_seconds"]
        output_cap_bytes = data["output_cap_bytes"]
        if (
            not isinstance(timeout_seconds, (int, float))
            or isinstance(timeout_seconds, bool)
            or not math.isfinite(timeout_seconds)
            or not 0 < timeout_seconds <= 3_600
        ):
            raise JournalError("check_execution_recorded timeout_seconds is outside the supported bound")
        if (
            not isinstance(output_cap_bytes, int)
            or isinstance(output_cap_bytes, bool)
            or not 1 <= output_cap_bytes <= 1_048_576
        ):
            raise JournalError("check_execution_recorded output_cap_bytes is outside the supported bound")
        owner_generation = data["owner_generation"]
        if not isinstance(owner_generation, int) or isinstance(owner_generation, bool) or owner_generation < 1:
            raise JournalError("check_execution_recorded owner_generation must be positive")
        lifecycle = data["lifecycle"]
        if lifecycle not in {"running", "passed", "failed", "blocked"}:
            raise JournalError("check_execution_recorded lifecycle is invalid")
        artifact_ref = _nonempty_string(data["artifact_ref"], "check_execution_recorded artifact_ref")
        cleanup_ref = _nonempty_string(data["cleanup_ref"], "check_execution_recorded cleanup_ref")
        cleanup_id = _identifier(data["cleanup_id"], "check_execution_recorded cleanup_id")
        process_root = data["process_root"]
        process_group = data["process_group"]
        process_start_identity = data["process_start_identity"]
        cleanup_authority = _nonempty_string(data["cleanup_authority"], "check_execution_recorded cleanup_authority")
        cleanup_authority_id = data["cleanup_authority_id"]
        if not isinstance(process_root, int) or isinstance(process_root, bool) or process_root < 1:
            raise JournalError("check_execution_recorded process_root must be positive")
        if cleanup_authority == "process_group":
            if not isinstance(process_group, int) or isinstance(process_group, bool) or process_group < 1:
                raise JournalError("check_execution_recorded process_group must be positive")
            if not isinstance(process_start_identity, str) or not process_start_identity:
                raise JournalError("check_execution_recorded process_start_identity must be non-empty")
            if cleanup_authority_id is not None:
                raise JournalError("check_execution_recorded process_group cannot have an authority ID")
        elif cleanup_authority == "job_object":
            if process_group is not None or process_start_identity is not None:
                raise JournalError("check_execution_recorded Job authority fields are invalid")
            if not isinstance(cleanup_authority_id, str) or not cleanup_authority_id:
                raise JournalError("check_execution_recorded Job authority ID must be non-empty")
        else:
            raise JournalError("check_execution_recorded cleanup authority is invalid")
        consumer_ref = _nonempty_string(data["consumer_ref"], "check_execution_recorded consumer_ref")
        existing = state["check_executions"].get(execution_id)
        identity = {
            "execution_id": execution_id,
            "command_digest": command_digest,
            "source_snapshot_digest": snapshot_digest,
            "execution_policy_digest": policy_digest,
            "timeout_seconds": timeout_seconds,
            "output_cap_bytes": output_cap_bytes,
            "owner_generation": owner_generation,
            "lifecycle": lifecycle,
            "artifact_ref": artifact_ref,
            "cleanup_ref": cleanup_ref,
            "cleanup_id": cleanup_id,
            "process_root": process_root,
            "process_group": process_group,
            "process_start_identity": process_start_identity,
            "cleanup_authority": cleanup_authority,
            "cleanup_authority_id": cleanup_authority_id,
        }
        if existing is None:
            if lifecycle != "running":
                raise JournalError("check execution must first be recorded as running")
            state["check_executions"][execution_id] = {**identity, "consumer_refs": [consumer_ref]}
        else:
            immutable_fields = set(identity) - {"lifecycle", "cleanup_ref"}
            if not isinstance(existing, Mapping) or any(existing.get(key) != identity[key] for key in immutable_fields):
                raise JournalError("check execution identity conflicts with its durable record")
            current_lifecycle = existing.get("lifecycle")
            if current_lifecycle == "running" and lifecycle in {"passed", "failed", "blocked"}:
                existing["lifecycle"] = lifecycle
            elif current_lifecycle != lifecycle:
                raise JournalError("check execution lifecycle transition conflicts with its durable record")
            if existing.get("cleanup_ref") != cleanup_ref:
                raise JournalError("check execution cleanup reference conflicts before recovery")
            consumers = existing.get("consumer_refs")
            if not isinstance(consumers, list):
                raise JournalError("check execution consumers are malformed")
            if consumer_ref not in consumers:
                consumers.append(consumer_ref)
    elif event_type == "check_execution_recovered":
        data = _exact_fields(
            data,
            {"execution_id", "owner_generation", "lifecycle", "cleanup_ref", "cleanup_id"},
            set(),
            "check_execution_recovered",
        )
        execution_id = _identifier(data["execution_id"], "check_execution_recovered execution_id")
        owner_generation = data["owner_generation"]
        if not isinstance(owner_generation, int) or isinstance(owner_generation, bool) or owner_generation < 1:
            raise JournalError("check_execution_recovered owner_generation must be positive")
        if data["lifecycle"] != "failed_verified":
            raise JournalError("check_execution_recovered lifecycle must be failed_verified")
        cleanup_ref = _nonempty_string(data["cleanup_ref"], "check_execution_recovered cleanup_ref")
        cleanup_id = _identifier(data["cleanup_id"], "check_execution_recovered cleanup_id")
        existing = state["check_executions"].get(execution_id)
        if not isinstance(existing, Mapping):
            raise JournalError("check_execution_recovered execution is missing")
        if existing.get("owner_generation") != owner_generation or existing.get("cleanup_id") != cleanup_id:
            raise JournalError("check_execution_recovered identity conflicts with durable execution")
        if existing.get("lifecycle") == "failed_verified":
            if existing.get("cleanup_ref") != cleanup_ref:
                raise JournalError("check_execution_recovered cleanup reference conflicts")
        elif existing.get("lifecycle") == "blocked":
            existing["lifecycle"] = "failed_verified"
            existing["cleanup_ref"] = cleanup_ref
        else:
            raise JournalError("check_execution_recovered requires a blocked execution")
    elif event_type == "checked_task_imported":
        task_id = _known_task(state, data.get("task_id"))
        task = state["tasks"][task_id]
        if task["contract"].get("checked") is not True:
            raise JournalError(f"task is not source-checked: {task_id}")
        event_data = _exact_fields(
            data,
            {"task_id", "import_id", "source_checked", "check", "note"},
            set(),
            "checked_task_imported",
        )
        import_id = _identifier(event_data["import_id"], "checked_task_imported import_id")
        if task["import_receipt"] is not None:
            if task["import_receipt"].get("import_id") == import_id:
                raise JournalError(f"checked task import already committed: {import_id}")
            raise JournalError(f"checked task already imported: {task_id}")
        if event_data["source_checked"] is not True:
            raise JournalError("checked_task_imported source_checked must be true")
        check = _exact_fields(
            event_data["check"],
            {
                "task_id",
                "command",
                "status",
                "exit_code",
                "duration_ms",
                "attempts",
                "total_duration_ms",
                "artifact",
                "evidence_ref",
            },
            set(),
            "checked_task_imported check",
        )
        if (
            check["task_id"] != task_id
            or check["command"] != task["contract"].get("check")
            or check["status"] != "passed"
            or check["exit_code"] != 0
        ):
            raise JournalError("checked_task_imported requires the exact passing task check")
        evidence_ref = _nonempty_string(
            check["evidence_ref"], "checked_task_imported evidence_ref"
        )
        if evidence_ref != f"file:{check['artifact']}":
            raise JournalError("checked_task_imported evidence_ref must name its artifact")
        note = _nonempty_string(event_data["note"], "checked_task_imported note")
        task["import_receipt"] = {
            "task_id": task_id,
            "import_id": import_id,
            "source_checked": True,
            "check_command": check["command"],
            "evidence_ref": evidence_ref,
        }
        task["check"] = json.loads(json.dumps(dict(check), sort_keys=True))
        task["grade"] = "pass"
        task["status"] = "pass"
        task["note"] = note
        task["evidence_refs"] = [evidence_ref]


def _apply_task_result_event(
    state: dict[str, Any],
    event_type: str,
    data: Mapping[str, Any],
    event: Mapping[str, Any],
) -> None:
    if event_type == "check_recorded":
        task_id = _known_task(state, data.get("task_id"))
        attempt_id = _nonempty_string(data.get("attempt_id"), "check_recorded attempt_id")
        attempt = state["attempts"].get(attempt_id)
        if not isinstance(attempt, Mapping):
            raise JournalError(f"check_recorded references unknown attempt: {attempt_id}")
        task = state["tasks"][task_id]
        if attempt.get("task_id") != task_id:
            raise JournalError("check_recorded task does not match its attempt")
        if not task["attempt_ids"] or task["attempt_ids"][-1] != attempt_id:
            raise JournalError("check_recorded requires the latest task attempt")
        if attempt.get("status") != "reported":
            raise JournalError("check_recorded requires a reported attempt")
        if data.get("status") not in {"passed", "failed"}:
            raise JournalError("check_recorded status must be passed or failed")
        exit_code = data.get("exit_code")
        if not isinstance(exit_code, int) or isinstance(exit_code, bool) or exit_code < 0:
            raise JournalError("check_recorded exit_code must be non-negative")
        command = _nonempty_string(data.get("command"), "check_recorded command")
        if data["status"] == "passed" and exit_code != 0:
            raise JournalError("a passed check must have exit_code zero")
        if data["status"] == "failed" and exit_code == 0:
            raise JournalError("a failed check must have a nonzero exit_code")
        contract = task["contract"]
        if contract.get("checked") is True:
            receipt = task["import_receipt"]
            if receipt is not None:
                if command != contract.get("check") or command != receipt.get("check_command"):
                    raise JournalError("checked task import must execute the recorded check")
                evidence_ref = _nonempty_string(
                    data.get("evidence_ref"), "check_recorded evidence_ref"
                )
                if evidence_ref != receipt.get("evidence_ref"):
                    raise JournalError("checked task import evidence does not match its receipt")
        check = json.loads(json.dumps(dict(data), sort_keys=True))
        attempt["check"] = check
        task["check"] = json.loads(json.dumps(check))
    elif event_type == "repair_recorded":
        task_id = _known_task(state, data.get("task_id"))
        task = state["tasks"][task_id]
        if task["grade"] is not None:
            raise JournalError(f"cannot record a repair after grading task {task_id}")
        hypothesis = _nonempty_string(data.get("hypothesis"), "repair_recorded hypothesis")
        if hypothesis in task["hypotheses"]:
            raise JournalError(f"duplicate repair hypothesis for task {task_id}")
        if len(task["hypotheses"]) >= 2:
            raise JournalError(f"task {task_id} reached the repair hypothesis cap")
        task["hypotheses"].append(hypothesis)
    elif event_type == "task_graded":
        task_id = _known_task(state, data.get("task_id"))
        grade = data.get("grade")
        if grade not in GRADES:
            raise JournalError(f"invalid task grade: {grade}")
        task = state["tasks"][task_id]
        if task["grade"] is not None:
            raise JournalError(f"task already graded: {task_id}")
        active_attempts = [
            attempt_id
            for attempt_id in task["attempt_ids"]
            if state["attempts"].get(attempt_id, {}).get("status")
            in {"reserved", "running", "interrupted"}
        ]
        if active_attempts:
            raise JournalError(
                f"task_graded requires no active attempts: {', '.join(active_attempts)}"
            )
        if grade in {"blocked", "unobserved"}:
            pending_cleanup = pending_cleanup_ids_for_task(state, task_id)
            if pending_cleanup:
                raise JournalError(
                    "task_graded requires terminal cleanup for "
                    f"{grade}: {', '.join(pending_cleanup)}"
                )
        if grade == "pass" and task["contract"].get("checked") is True:
            check = task["check"]
            if (
                task["import_receipt"] is None
                or not isinstance(check, Mapping)
                or check.get("status") != "passed"
                or check.get("exit_code") != 0
            ):
                raise JournalError("checked task pass needs explicit passing check-backed import")
        if grade == "pass" and task["attempt_ids"]:
            latest_attempt_id = task["attempt_ids"][-1]
            unresolved_blocking = _unresolved_blocking_findings(
                state, task_id, latest_attempt_id
            )
            if unresolved_blocking:
                raise JournalError(
                    "task pass requires an explicit decision for blocking findings: "
                    + ", ".join(unresolved_blocking)
                )
        task["grade"] = grade
        task["status"] = grade
        task["note"] = _nonempty_string(
            data.get("note"), "task_graded note"
        )
        evidence_refs = data.get("evidence_refs", [])
        if not isinstance(evidence_refs, list) or any(
            not isinstance(reference, str) or not reference for reference in evidence_refs
        ):
            raise JournalError("task_graded evidence_refs must be an array of strings")
        task["evidence_refs"] = list(evidence_refs)
        if grade == "pass" and task["attempt_ids"]:
            _carry_forward_hardening(state, task_id, task["attempt_ids"][-1])


def _apply_cleanup_registration_event(
    state: dict[str, Any],
    event_type: str,
    data: Mapping[str, Any],
    event: Mapping[str, Any],
) -> None:
    if event_type == "cleanup_registered":
        cleanup_id = _nonempty_string(data.get("cleanup_id"), "cleanup_registered cleanup_id")
        if cleanup_id in state["cleanup"]:
            raise JournalError(f"duplicate cleanup ID: {cleanup_id}")
        raw_owner = data.get("owner")
        delegated_child: Mapping[str, Any] | None = None
        identity_version = data.get("identity_version")
        if identity_version == 1:
            try:
                registered = _exact_fields(
                    data,
                    {"cleanup_id", "kind", "target", "owner", "identity_version"},
                    {"delegation_id"},
                    "cleanup_registered typed identity",
                )
                kind = _nonempty_string(registered["kind"], "cleanup_registered kind")
                target = validate_cleanup_target(kind, registered["target"])
                owner = validate_cleanup_owner(registered["owner"])
                delegation_id = registered.get("delegation_id")
                if delegation_id is not None:
                    delegation_id = _identifier(
                        delegation_id, "cleanup_registered delegation_id"
                    )
                    delegation = state["delegations"].get(delegation_id)
                    if (
                        not isinstance(delegation, Mapping)
                        or delegation.get("status") not in {"started", "reported"}
                        or delegation.get("resource_owner") != owner
                    ):
                        raise JournalError(
                            "cleanup_registered delegation link does not match the child"
                        )
            except GraphValidationError as error:
                raise JournalError(f"cleanup_registered typed identity is invalid: {error}") from error
            workspace_scope = state.get("workspace_scope")
            workspace = (
                workspace_scope.get("execution_workspace")
                if isinstance(workspace_scope, Mapping)
                else None
            )
            if (
                not isinstance(workspace, Mapping)
                or owner["execution_host_id"] != workspace.get("execution_host_id")
                or owner["workspace_key"] != workspace.get("workspace_key")
            ):
                raise JournalError("cleanup_registered owner does not match the run workspace")
            attempt_id = owner.get("attempt_id")
            if isinstance(attempt_id, str):
                attempt = state["attempts"].get(attempt_id)
                if (
                    not isinstance(attempt, Mapping)
                    and (
                        delegation_id is None
                        or delegation.get("child_attempt_id") != attempt_id
                    )
                ):
                    raise JournalError("cleanup_registered owner references an unknown attempt")
                recorded_owner = attempt.get("resource_owner") if isinstance(attempt, Mapping) else None
                if isinstance(recorded_owner, Mapping) and owner != recorded_owner:
                    raise JournalError("cleanup_registered owner does not match the attempt identity")
            elif owner["coordinator_generation"] != state["coordinator"]["generation"]:
                raise JournalError("cleanup_registered owner uses a stale coordinator generation")
            if kind == "process":
                if owner["process_root"] != target["root_pid"]:
                    raise JournalError("process cleanup target does not match its owner root PID")
            elif kind == "terminal":
                if owner["terminal_id"] is None or target != owner["terminal_id"]:
                    raise JournalError("terminal cleanup target does not match its owner")
            for existing_id, existing_cleanup in state["cleanup"].items():
                if isinstance(existing_cleanup, Mapping) and _cleanup_identity_reused(
                    existing_cleanup, kind, target, owner
                ):
                    raise JournalError(
                        f"cleanup identity is already registered as {existing_id}"
                    )
            state["cleanup"][cleanup_id] = {
                "cleanup_id": cleanup_id,
                "kind": kind,
                "target": target,
                "owner": owner,
                "identity_version": 1,
                "status": "pending",
                **({"delegation_id": delegation_id} if delegation_id is not None else {}),
            }
            state["last_sequence"] = event["sequence"]
            return state
        if identity_version is not None:
            raise JournalError("cleanup_registered identity_version is unsupported")
        if isinstance(raw_owner, Mapping):
            try:
                owner = validate_cleanup_owner(raw_owner)
            except GraphValidationError as error:
                raise JournalError(f"cleanup_registered owner is invalid: {error}") from error
            attempt_id = data.get("attempt_id")
            known_attempt = state["attempts"].get(attempt_id)
            delegated_child = next(
                (
                    delegation for delegation in state["delegations"].values()
                    if isinstance(delegation, Mapping)
                    and delegation.get("child_attempt_id") == attempt_id
                ),
                None,
            )
            owner_on_record = (
                known_attempt.get("resource_owner") if isinstance(known_attempt, Mapping)
                else delegated_child.get("resource_owner") if isinstance(delegated_child, Mapping)
                else None
            )
            reserved_provider_cleanup = (
                isinstance(known_attempt, Mapping)
                and known_attempt.get("status") == "reserved"
                and data.get("kind") == "other"
                and owner["terminal_id"] is None
            )
            if owner["attempt_id"] != attempt_id or (
                owner != owner_on_record and not reserved_provider_cleanup
            ):
                raise JournalError("cleanup_registered owner does not match an anchored attempt")
            if isinstance(delegated_child, Mapping):
                if (
                    (data.get("kind") == "terminal" and (owner["terminal_id"] is None or data.get("target") != owner["terminal_id"]))
                    or (data.get("kind") == "process" and (owner["process_root"] is None or data.get("target") != {"kind": "process", "root_pid": owner["process_root"]}))
                    or data.get("kind") not in {"terminal", "process"}
                ):
                    raise JournalError("delegation cleanup must name the owned terminal or process tree")
        else:
            if data.get("kind") == "terminal":
                raise JournalError(
                    "terminal cleanup requires an attempt-owned resource receipt"
                )
            _nonempty_string(raw_owner, "cleanup_registered owner")
            _nonempty_string(data.get("kind"), "cleanup_registered kind")
            _nonempty_string(data.get("target"), "cleanup_registered target")
        state["cleanup"][cleanup_id] = {
            **json.loads(json.dumps(dict(data), sort_keys=True)),
            "status": "pending",
            **({"delegation_id": delegated_child["delegation_id"]} if delegated_child else {}),
        }
        if isinstance(raw_owner, Mapping):
            for delegation in state["delegations"].values():
                if (
                    isinstance(delegation, Mapping)
                    and delegation.get("child_attempt_id") == data.get("attempt_id")
                    and delegation.get("resource_owner") == owner
                ):
                    existing_cleanup_id = delegation.get("cleanup_id")
                    if data.get("kind") == "terminal":
                        if existing_cleanup_id is not None and existing_cleanup_id != cleanup_id:
                            raise JournalError("delegation child already has a cleanup record")
                        delegation["cleanup_id"] = cleanup_id
                    break


def _apply_cleanup_finish_event(
    state: dict[str, Any],
    event_type: str,
    data: Mapping[str, Any],
    event: Mapping[str, Any],
) -> None:
    if event_type == "cleanup_finished":
        cleanup_id = _nonempty_string(data.get("cleanup_id"), "cleanup_finished cleanup_id")
        if cleanup_id not in state["cleanup"]:
            raise JournalError(f"unknown cleanup ID: {cleanup_id}")
        cleanup = state["cleanup"][cleanup_id]
        receipt = data.get("receipt")
        if cleanup.get("identity_version") == 1:
            owner = cleanup["owner"]
            kind = cleanup["kind"]
            if cleanup.get("status") not in {"pending", "unverifiable"}:
                raise JournalError("typed cleanup is not eligible for verification")
            if kind == "process":
                process_receipt = _exact_fields(
                    receipt,
                    {"kind", "owner", "target", "descendant_pids", "status"},
                    set(),
                    "cleanup_finished process receipt",
                )
                descendants = process_receipt["descendant_pids"]
                if (
                    process_receipt["kind"] != "process"
                    or process_receipt["status"] != "verified"
                    or process_receipt["owner"] != owner
                    or process_receipt["target"] != cleanup["target"]
                    or not isinstance(descendants, list)
                    or any(
                        not isinstance(pid, int) or isinstance(pid, bool) or pid < 1
                        for pid in descendants
                    )
                    or len(set(descendants)) != len(descendants)
                ):
                    raise JournalError("typed process cleanup receipt does not match its identity")
            elif kind == "terminal":
                terminal_receipt = _exact_fields(
                    receipt,
                    {"kind", "owner", "terminal_id", "incarnation_id", "status"},
                    set(),
                    "cleanup_finished terminal receipt",
                )
                if (
                    terminal_receipt["kind"] != "terminal"
                    or terminal_receipt["status"] != "verified"
                    or terminal_receipt["owner"] != owner
                    or terminal_receipt["terminal_id"] != cleanup["target"]
                    or terminal_receipt["incarnation_id"] != owner["incarnation_id"]
                ):
                    raise JournalError("typed terminal cleanup receipt does not match its owner")
            else:
                raise JournalError("typed cleanup kind must be process or terminal")
            cleanup["status"] = "verified"
        elif isinstance(cleanup.get("owner"), Mapping):
            owner = cleanup["owner"]
            if owner["terminal_id"] is None:
                if cleanup.get("status") not in {"pending", "unverifiable"}:
                    raise JournalError("provider cleanup is not eligible for verification")
                provider_receipt = _exact_fields(
                    receipt,
                    {"kind", "owner", "dispatch_id", "runtime_id", "worktree_id", "run_id", "status"},
                    set(),
                    "cleanup_finished provider receipt",
                )
                refs = cleanup.get("external_refs")
                if (
                    cleanup.get("kind") != "other"
                    or provider_receipt["kind"] != "provider-dispatch"
                    or provider_receipt["owner"] != owner
                    or provider_receipt["dispatch_id"] != cleanup.get("target")
                    or provider_receipt["status"] not in {"released", "already_released"}
                    or not isinstance(refs, Mapping)
                    or refs.get("tier") != "supervised"
                    or any(
                        provider_receipt[field] != refs.get(field)
                        for field in ("runtime_id", "worktree_id", "run_id")
                    )
                    or owner.get("provenance")
                    != f"orca-supervised:{refs.get('runtime_id')}:{refs.get('worktree_id')}:{refs.get('run_id')}:{cleanup.get('target')}"
                ):
                    raise JournalError("typed provider cleanup receipt does not match its owner")
            else:
                terminal_receipt = _exact_fields(
                    receipt,
                    {"kind", "owner", "terminal_id", "incarnation_id", "status"},
                    set(),
                    "cleanup_finished terminal receipt",
                )
                if (
                    cleanup.get("kind") != "terminal"
                    or terminal_receipt["kind"] != "terminal"
                    or terminal_receipt["status"] != "verified"
                    or terminal_receipt["owner"] != owner
                    or terminal_receipt["terminal_id"] != owner["terminal_id"]
                    or terminal_receipt["incarnation_id"] != owner["incarnation_id"]
                ):
                    raise JournalError("typed terminal cleanup receipt does not match its owner")
            cleanup["status"] = "verified"
        else:
            cleanup["status"] = "done"
        cleanup["receipt"] = receipt


def _apply_cleanup_settlement_event(
    state: dict[str, Any],
    event_type: str,
    data: Mapping[str, Any],
    event: Mapping[str, Any],
) -> None:
    if event_type == "cleanup_unverifiable":
        cleanup_id = _nonempty_string(
            data.get("cleanup_id"), "cleanup_unverifiable cleanup_id"
        )
        cleanup = state["cleanup"].get(cleanup_id)
        if not isinstance(cleanup, Mapping):
            raise JournalError(f"unknown cleanup ID: {cleanup_id}")
        typed_cleanup_retry = (
            isinstance(cleanup.get("owner"), Mapping)
            and isinstance(cleanup["owner"].get("attempt_id"), str)
            and cleanup.get("status") == "unverifiable"
        )
        if cleanup.get("status") != "pending" and not typed_cleanup_retry:
            raise JournalError(f"cleanup is not pending: {cleanup_id}")
        receipt = data.get("receipt")
        if not isinstance(receipt, Mapping):
            raise JournalError("cleanup_unverifiable requires an evidence receipt")
        cleanup["status"] = "unverifiable"
        cleanup["receipt"] = json.loads(json.dumps(dict(receipt), sort_keys=True))
    elif event_type == "cleanup_retained":
        try:
            retained = _exact_fields(
                data,
                {"cleanup_id", "receipt"},
                set(),
                "cleanup_retained",
            )
            cleanup_id = _identifier(
                retained["cleanup_id"], "cleanup_retained cleanup_id"
            )
            if retained["receipt"] is None or retained["receipt"] == "":
                raise GraphValidationError("cleanup_retained receipt must not be empty")
        except GraphValidationError as error:
            raise JournalError(f"cleanup_retained is invalid: {error}") from error
        cleanup = state["cleanup"].get(cleanup_id)
        if not isinstance(cleanup, Mapping):
            raise JournalError(f"unknown cleanup ID: {cleanup_id}")
        if cleanup.get("status") in {"done", "verified", "retained"}:
            raise JournalError(f"cleanup is already terminal: {cleanup_id}")
        if (
            cleanup.get("identity_version") is None
            and isinstance(retained["receipt"], Mapping)
            and retained["receipt"].get("kind") == "legacy-retention"
        ):
            receipt = retained["receipt"]
            try:
                legacy_receipt = _exact_fields(
                    receipt,
                    {"kind", "reason", "replacement_cleanup_id"},
                    set(),
                    "legacy cleanup retention receipt",
                )
                if legacy_receipt["kind"] != "legacy-retention":
                    raise GraphValidationError("legacy cleanup retention kind must be legacy-retention")
                reason = _nonempty_string(legacy_receipt["reason"], "legacy cleanup retention reason")
                if len(reason.encode("utf-8")) > 4096:
                    raise GraphValidationError("legacy cleanup retention reason exceeds 4096 bytes")
                replacement_id = _identifier(
                    legacy_receipt["replacement_cleanup_id"],
                    "legacy cleanup retention replacement_cleanup_id",
                )
            except GraphValidationError as error:
                raise JournalError(f"legacy cleanup retention is invalid: {error}") from error
            replacement = state["cleanup"].get(replacement_id)
            if replacement_id == cleanup_id or not isinstance(replacement, Mapping):
                raise JournalError("legacy cleanup retention requires a distinct replacement cleanup")
        cleanup["status"] = "retained"
        cleanup["receipt"] = retained["receipt"]


def _apply_terminal_event(
    state: dict[str, Any],
    event_type: str,
    data: Mapping[str, Any],
    event: Mapping[str, Any],
) -> None:
    if event_type == "journal_repaired":
        _nonempty_string(data.get("artifact"), "journal_repaired artifact")
    elif event_type == "browser_surface_requested":
        try:
            request = validate_browser_surface_request(data)
        except BrowserSurfaceError as error:
            raise JournalError(f"browser surface request is invalid: {error}") from error
        _browser_surface_attempt(state, request)
        existing = state["browser_surfaces"].get(request["request_id"])
        if existing is not None:
            if not isinstance(existing, Mapping) or existing.get("request") != request:
                raise JournalError("browser surface request ID was replayed with different content")
        else:
            for record in state["browser_surfaces"].values():
                if not isinstance(record, Mapping):
                    raise JournalError("browser surface record is malformed")
                prior = record.get("request")
                if isinstance(prior, Mapping) and prior.get("idempotency_key") == request["idempotency_key"]:
                    if prior != request:
                        raise JournalError("browser surface idempotency key was replayed with different content")
                    break
            else:
                state["browser_surfaces"][request["request_id"]] = {
                    "request": request,
                    "status": "requested",
                    "receipts": {},
                }
    elif event_type in {
        "browser_surface_receipt",
        "browser_surface_observed",
        "browser_surface_captured",
        "browser_surface_released",
    }:
        if set(data) != {"receipt"} or not isinstance(data.get("receipt"), Mapping):
            raise JournalError("browser surface receipt event requires exactly one receipt")
        _apply_browser_surface_receipt(state, data["receipt"])
    elif event_type == "run_completed":
        outcome = data.get("outcome")
        if outcome not in {"pass", "partial", "blocked"}:
            raise JournalError("run_completed outcome must be pass, partial, or blocked")
        if outcome == "pass" and (
            any(isinstance(task, Mapping) and task.get("carry_forward_findings") for task in state["tasks"].values())
            or any(isinstance(item, Mapping) and item.get("status") == "carry_forward" for item in state["degradations"])
        ):
            raise JournalError("run_completed pass cannot include carry-forward findings")
        unsettled_cleanup = unresolved_cleanup_ids(state)
        if unsettled_cleanup:
            raise JournalError(
                "run_completed requires terminal cleanup: "
                + ", ".join(unsettled_cleanup)
            )
        active_delegations = sorted(
            delegation_id
            for delegation_id, delegation in state["delegations"].items()
            if isinstance(delegation, Mapping)
            and delegation.get("status") not in {"rejected", "released"}
        )
        if active_delegations:
            raise JournalError(
                "run_completed requires terminal delegations: "
                + ", ".join(active_delegations)
            )
        state["status"] = "complete"
        state["outcome"] = outcome


_EVENT_REDUCER_GROUPS = (
    (
        frozenset(
            {
                "coordinator_claimed",
                "coordinator_transferred",
                "coordinator_taken_over",
                "driver_selected",
                "driver_selection_reserved",
                "driver_selection_failed",
                "task_ready",
            }
        ),
        _apply_control_event,
    ),
    (
        frozenset(
            {
                "delegation_requested",
                "graph_amended",
                "process_decision_amended",
            }
        ),
        _apply_graph_event,
    ),
    (
        frozenset(
            {
                "delegation_approved",
                "delegation_rejected",
                "delegation_started",
                "delegation_reported",
                "delegation_released",
            }
        ),
        _apply_delegation_event,
    ),
    (
        frozenset(
            {
                "attempt_reserved",
                "attempt_scope_frozen",
            }
        ),
        _apply_attempt_reservation_event,
    ),
    (
        frozenset({"attempt_started", "attempt_start_failed", "attempt_abandoned"}),
        _apply_attempt_start_event,
    ),
    (
        frozenset(
            {
                "attempt_provider_result_rejected",
                "attempt_result_quarantined",
                "attempt_observed",
                "driver_degraded",
            }
        ),
        _apply_attempt_result_event,
    ),
    (
        frozenset({"question_opened", "question_answered", "worker_reported"}),
        _apply_interaction_event,
    ),
    (
        frozenset(
            {
                "attempt_check_rejected",
                "finding_recorded",
                "coordinator_decision_recorded",
            }
        ),
        _apply_finding_event,
    ),
    (
        frozenset({"attempt_audit_rejected", "attempt_audit_exhausted"}),
        _apply_attempt_audit_event,
    ),
    (
        frozenset(
            {
                "check_execution_recorded",
                "check_execution_recovered",
                "checked_task_imported",
            }
        ),
        _apply_check_execution_event,
    ),
    (
        frozenset({"check_recorded", "repair_recorded", "task_graded"}),
        _apply_task_result_event,
    ),
    (frozenset({"cleanup_registered"}), _apply_cleanup_registration_event),
    (frozenset({"cleanup_finished"}), _apply_cleanup_finish_event),
    (
        frozenset({"cleanup_unverifiable", "cleanup_retained"}),
        _apply_cleanup_settlement_event,
    ),
    (
        frozenset(
            {
                "journal_repaired",
                "browser_surface_requested",
                "browser_surface_receipt",
                "browser_surface_observed",
                "browser_surface_captured",
                "browser_surface_released",
                "run_completed",
            }
        ),
        _apply_terminal_event,
    ),
)
_EVENT_REDUCERS = {
    event_type: reducer
    for event_types, reducer in _EVENT_REDUCER_GROUPS
    for event_type in event_types
}
if (
    sum(len(event_types) for event_types, _ in _EVENT_REDUCER_GROUPS)
    != len(_EVENT_REDUCERS)
    or frozenset(_EVENT_REDUCERS) != CORE_EVENT_TYPES - {"run_started"}
):
    raise RuntimeError("event reducer registry must cover each core event exactly once")


def validate_event(event: Mapping[str, Any], expected_sequence: int) -> None:
    """Validate the journal envelope before projection."""

    required = {
        "schema_version",
        "event_id",
        "sequence",
        "type",
        "timestamp",
        "coordinator_generation",
        "data",
    }
    if not isinstance(event, Mapping):
        raise JournalError("journal event must be an object")
    if set(event) != required:
        unknown = sorted(set(event) - required)
        missing = sorted(required - set(event))
        details = []
        if missing:
            details.append(f"missing {', '.join(missing)}")
        if unknown:
            details.append(f"unknown {', '.join(unknown)}")
        raise JournalError(f"invalid event fields: {'; '.join(details)}")
    if event["schema_version"] != SCHEMA_VERSION:
        raise JournalError("unsupported event schema_version")
    if event["sequence"] != expected_sequence:
        raise JournalError(
            f"event sequence must be {expected_sequence}, got {event['sequence']}"
        )
    if event["event_id"] != f"event-{expected_sequence:06d}":
        raise JournalError("event_id does not match sequence")
    if event["type"] not in CORE_EVENT_TYPES:
        raise JournalError(f"unknown event type: {event['type']}")
    _nonempty_string(event["timestamp"], "event timestamp")
    generation = event["coordinator_generation"]
    if not isinstance(generation, int) or isinstance(generation, bool) or generation < 0:
        raise JournalError("event coordinator_generation must be a non-negative integer")
    if not isinstance(event["data"], Mapping):
        raise JournalError("event data must be an object")


def replay_events(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Rebuild a complete projection from an ordered event iterable."""

    projection = empty_projection()
    for sequence, event in enumerate(events, start=1):
        validate_event(event, sequence)
        generation = projection["coordinator"]["generation"]
        if event["type"] == "run_started":
            if event["coordinator_generation"] not in {0, event["data"].get("coordinator_generation", 1)}:
                raise JournalError("run_started has inconsistent coordinator generation")
        elif event["coordinator_generation"] != generation:
            raise StaleCoordinatorError(
                f"event {sequence} uses coordinator generation "
                f"{event['coordinator_generation']}, current generation is {generation}"
            )
        projection = apply_event(projection, event)
    return projection


def atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Atomically replace a JSON file and sync its containing directory."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
        if hasattr(os, "O_DIRECTORY"):
            directory = os.open(path.parent, os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


class EventJournal:
    """Append and replay one coordinator-owned graph journal."""

    def __init__(self, path: Path, projection_path: Path | None = None) -> None:
        self.path = Path(path)
        self.projection_path = projection_path or self.path.with_name("state.json")
        self._lock = threading.RLock()
        self._expected_revision: int | None = None

    @contextmanager
    def _interprocess_lock(self) -> Iterable[None]:
        """Hold a portable advisory lock shared by every journal process."""

        lock_path = self.path.with_name(f".{self.path.name}.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+b") as handle:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                if handle.tell() == 0:
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                return
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _read_complete_events(self) -> tuple[list[dict[str, Any]], bytes]:
        if not self.path.exists():
            return [], b""
        raw = self.path.read_bytes()
        partial = b""
        complete = raw
        if raw and not raw.endswith(b"\n"):
            boundary = raw.rfind(b"\n")
            complete = raw[: boundary + 1] if boundary >= 0 else b""
            partial = raw[boundary + 1 :]
        events: list[dict[str, Any]] = []
        for line_number, line in enumerate(complete.splitlines(), start=1):
            if not line.strip():
                raise JournalError(f"journal line {line_number} is empty")
            try:
                value = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise JournalError(f"journal corruption at line {line_number}: {error}") from error
            if not isinstance(value, dict):
                raise JournalError(f"journal line {line_number} must contain an object")
            events.append(value)
        return events, partial

    def _recent_events_unlocked(self, limit: int) -> list[dict[str, Any]]:
        """Read a bounded tail for status watches without retaining the journal."""

        if limit < 1 or not self.path.exists():
            return []
        maximum_bytes = 4 * 1024 * 1024
        with self.path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            position = handle.tell()
            chunks: list[bytes] = []
            newline_count = 0
            read_bytes = 0
            while position > 0 and newline_count <= limit and read_bytes < maximum_bytes:
                chunk_size = min(8192, position, maximum_bytes - read_bytes)
                position -= chunk_size
                handle.seek(position)
                chunk = handle.read(chunk_size)
                chunks.append(chunk)
                newline_count += chunk.count(b"\n")
                read_bytes += len(chunk)
            tail = b"".join(reversed(chunks))
        lines = tail.splitlines()
        if position > 0 and lines:
            lines = lines[1:]
        if tail and not tail.endswith(b"\n") and lines:
            lines = lines[:-1]
        if len(lines) > limit:
            lines = lines[-limit:]
        events: list[dict[str, Any]] = []
        for line in lines:
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise JournalError(f"journal tail is unreadable: {error}") from error
            if not isinstance(event, dict):
                raise JournalError("journal tail must contain objects")
            events.append(event)
        return events

    def recent_events(self, limit: int) -> list[dict[str, Any]]:
        """Return a tail observed under the same lock as append and projection saves."""

        with self._lock, self._interprocess_lock():
            return self._recent_events_unlocked(limit)

    def watch_snapshot(self, limit: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Read journal tail and saved projection as one consistent observation."""

        with self._lock, self._interprocess_lock():
            events = self._recent_events_unlocked(limit)
            if not self.projection_path.is_file():
                raise JournalError(f"saved projection does not exist: {self.projection_path}")
            try:
                projection = json.loads(self.projection_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as error:
                raise JournalError(f"cannot read saved projection: {error}") from error
            if not isinstance(projection, dict):
                raise JournalError("saved projection must contain an object")
            sequence = projection.get("last_sequence")
            if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
                raise JournalError("saved projection has an invalid cursor")
            if events:
                observed = events[-1].get("sequence")
                if not isinstance(observed, int) or observed != sequence:
                    raise JournalError("saved projection does not match the latest journal event")
            elif sequence:
                raise JournalError("saved projection has no observable journal tail")
            return events, projection

    def watch_replay_snapshot(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Replay complete journal lines, tolerating an incomplete final watch line."""

        with self._lock, self._interprocess_lock():
            events, _ = self._read_complete_events()
            projection = replay_events(events)
            self._expected_revision = projection["last_sequence"]
            return events, projection

    def replay(self) -> dict[str, Any]:
        """Replay complete journal lines; reject any unhandled partial tail."""

        _, projection = self.replay_snapshot()
        return projection

    def replay_snapshot(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Return one locked, replay-verified event and projection snapshot."""

        with self._lock, self._interprocess_lock():
            events, partial = self._read_complete_events()
            if partial:
                raise JournalError("journal has a partial final line; repair it before replay")
            projection = replay_events(events)
            self._expected_revision = projection["last_sequence"]
            return events, projection

    def _reconcile_staged_check_recoveries(self, projection: Mapping[str, Any]) -> None:
        """Finish only a fenced recovery that the journal already made public."""

        executions = projection.get("check_executions")
        if not isinstance(executions, Mapping):
            return
        if not executions:
            return
        directory = self.path.parent / "artifacts" / "check-executions"
        lock_path = directory / ".lock"
        directory.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+b") as handle:
            if os.name == "nt":
                import msvcrt

                if lock_path.stat().st_size == 0:
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                for execution_id, execution in executions.items():
                    if not isinstance(execution, Mapping) or execution.get("lifecycle") != "failed_verified":
                        continue
                    record_path = directory / f"{execution_id}.json"
                    try:
                        record = json.loads(record_path.read_text(encoding="utf-8"))
                    except (OSError, UnicodeError, json.JSONDecodeError) as error:
                        raise JournalError(
                            f"check execution side record is unreadable: {execution_id}"
                        ) from error
                    if not isinstance(record, dict):
                        raise JournalError("check execution side record must be an object")
                    if record.get("lifecycle") == "failed_verified":
                        continue
                    fields = (
                        "execution_id", "command_digest", "source_snapshot_digest",
                        "execution_policy_digest", "timeout_seconds", "output_cap_bytes",
                        "owner_generation", "artifact_ref", "cleanup_ref", "cleanup_id",
                        "owner_pid", "process_root", "process_group", "process_start_identity",
                        "cleanup_authority", "cleanup_authority_id",
                    )
                    if (
                        record.get("lifecycle") != "blocked"
                        or any(record.get(field) != execution.get(field) for field in fields if field != "owner_pid")
                    ):
                        raise JournalError("check execution recovery has diverged from its public fence")
                    staged_identity = {
                        **{field: record.get(field) for field in fields},
                        "lifecycle": "blocked",
                    }
                    digest = "sha256:" + hashlib.sha256(
                        json.dumps(staged_identity, separators=(",", ":"), sort_keys=True).encode("utf-8")
                    ).hexdigest()
                    if record.get("recovery_stage") != {
                        "status": "prepared", "identity_digest": digest
                    }:
                        raise JournalError("check execution recovery is not a prepared fenced transition")
                    cleanup_path = self.path.parents[4] / str(record["cleanup_ref"])
                    try:
                        cleanup = json.loads(cleanup_path.read_text(encoding="utf-8"))
                    except (OSError, UnicodeError, json.JSONDecodeError) as error:
                        raise JournalError("check execution recovery cleanup is unreadable") from error
                    if not isinstance(cleanup, dict) or cleanup.get("status") != "verified_absent" or cleanup.get("verified_absent") is not True:
                        raise JournalError("check execution recovery cleanup proof is missing")
                    record["lifecycle"] = "failed_verified"
                    record["recovery_stage"] = {"status": "committed", "identity_digest": digest}
                    atomic_write_json(record_path, record)
            finally:
                if os.name == "nt":
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def recover_partial_line(
        self,
        artifact_path: Path,
        *,
        coordinator_generation: int,
    ) -> dict[str, Any]:
        """Archive and remove only a non-newline-terminated final journal line."""

        with self._lock, self._interprocess_lock():
            events, partial = self._read_complete_events()
            if not partial:
                raise JournalError("journal has no partial final line to recover")
            projection = replay_events(events)
            current_generation = projection["coordinator"]["generation"]
            if coordinator_generation != current_generation:
                raise StaleCoordinatorError(
                    f"coordinator generation {coordinator_generation} is stale; "
                    f"current generation is {current_generation}"
                )
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            with artifact_path.open("xb") as artifact:
                artifact.write(partial)
                artifact.flush()
                os.fsync(artifact.fileno())
            complete_length = self.path.stat().st_size - len(partial)
            with self.path.open("r+b") as handle:
                handle.truncate(complete_length)
                handle.flush()
                os.fsync(handle.fileno())
        return self.append(
            "journal_repaired",
            {"artifact": artifact_path.as_posix(), "discarded_bytes": len(partial)},
            coordinator_generation=coordinator_generation,
        )

    def append(
        self,
        event_type: str,
        data: Mapping[str, Any],
        *,
        coordinator_generation: int,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        """Append one fenced event, sync it, and atomically save its projection."""

        if event_type not in CORE_EVENT_TYPES:
            raise JournalError(f"unknown event type: {event_type}")
        if not isinstance(data, Mapping):
            raise JournalError("event data must be an object")
        with self._lock, self._interprocess_lock():
            events, partial = self._read_complete_events()
            if partial:
                raise JournalError("journal has a partial final line; repair it before appending")
            projection = replay_events(events)
            actual_revision = projection["last_sequence"]
            if (
                self._expected_revision is not None
                and actual_revision != self._expected_revision
            ):
                raise StaleRevisionError(
                    f"journal revision {self._expected_revision} is stale; "
                    f"current revision is {actual_revision}"
                )
            current_generation = projection["coordinator"]["generation"]
            if event_type == "run_started":
                if events:
                    raise JournalError("run_started must be the first event")
                declared_generation = data.get("coordinator_generation", 1)
                if coordinator_generation not in {0, declared_generation}:
                    raise StaleCoordinatorError("run_started has inconsistent coordinator generation")
            elif coordinator_generation != current_generation:
                raise StaleCoordinatorError(
                    f"coordinator generation {coordinator_generation} is stale; "
                    f"current generation is {current_generation}"
                )
            sequence = len(events) + 1
            event = {
                "schema_version": SCHEMA_VERSION,
                "event_id": f"event-{sequence:06d}",
                "sequence": sequence,
                "type": event_type,
                "timestamp": timestamp or datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "coordinator_generation": coordinator_generation,
                "data": json.loads(json.dumps(dict(data), sort_keys=True)),
            }
            validate_event(event, sequence)
            next_projection = apply_event(projection, event)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            serialized = json.dumps(event, separators=(",", ":"), sort_keys=True) + "\n"
            with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())
            atomic_write_json(self.projection_path, next_projection)
            self._expected_revision = next_projection["last_sequence"]
            return next_projection

    def import_checked_task(
        self,
        task_id: str,
        *,
        import_id: str,
        coordinator_generation: int,
        note: str,
        timeout_seconds: float = 300,
        output_cap_bytes: int = 65_536,
    ) -> dict[str, Any]:
        """Execute and atomically import one source-checked task by stable identity."""

        task_id = _identifier(task_id, "checked import task_id")
        import_id = _identifier(import_id, "checked import import_id")
        note = _nonempty_string(note, "checked import note")
        if (
            not isinstance(timeout_seconds, (int, float))
            or isinstance(timeout_seconds, bool)
            or not math.isfinite(timeout_seconds)
            or not 0 < timeout_seconds <= 3_600
        ):
            raise JournalError("checked import timeout_seconds is outside the supported bound")
        if (
            not isinstance(output_cap_bytes, int)
            or isinstance(output_cap_bytes, bool)
            or not 1 <= output_cap_bytes <= 1_048_576
        ):
            raise JournalError("checked import output_cap_bytes is outside the supported bound")

        with self._lock:
            projection = self.replay()
            current_generation = projection["coordinator"]["generation"]
            if coordinator_generation != current_generation:
                raise StaleCoordinatorError(
                    f"coordinator generation {coordinator_generation} is stale; "
                    f"current generation is {current_generation}"
                )
            task = projection.get("tasks", {}).get(task_id)
            if not isinstance(task, Mapping):
                raise JournalError(f"checked import references unknown task: {task_id}")
            receipt = task.get("import_receipt")
            already_committed = isinstance(receipt, Mapping)
            if isinstance(receipt, Mapping):
                if receipt.get("import_id") != import_id:
                    raise JournalError(f"checked task already imported: {task_id}")
                if task.get("note") != note:
                    raise JournalError("checked import retry changed the committed note")
            if not already_committed and task.get("grade") is not None:
                raise JournalError(f"checked task already graded: {task_id}")
            contract = task.get("contract", {})
            if contract.get("checked") is not True:
                raise JournalError(f"task is not source-checked: {task_id}")
            dependencies = contract.get("depends", [])
            if not isinstance(dependencies, list):
                raise JournalError("checked import task dependencies are malformed")
            blockers = [
                {"task_id": dependency, "grade": projection.get("tasks", {}).get(dependency, {}).get("grade")}
                for dependency in dependencies
                if projection.get("tasks", {}).get(dependency, {}).get("grade") != "pass"
            ]
            if blockers:
                raise TaskNotReadyError(
                    "task dependencies are not ready: "
                    + ", ".join(f"{blocker['task_id']}={blocker['grade'] or 'missing'}" for blocker in blockers)
                )
            command = _nonempty_string(contract.get("check"), "checked import task check")
            scope = projection.get("workspace_scope")
            if not isinstance(scope, Mapping):
                raise JournalError("checked import requires a pinned workspace scope")
            validated_scope = validate_workspace_scope(scope)
            if validated_scope["execution_host"]["boundary"] != "local":
                raise JournalError("checked import execution_scope_unsupported")
            if (
                validated_scope["execution_workspace"]
                != validated_scope["orchestration_home"]
            ):
                raise JournalError("checked import execution_scope_unsupported")
            workspace = Path(validated_scope["execution_workspace"]["path"])
            orchestration_home = Path(validated_scope["orchestration_home"]["path"])
            if (
                workspace.resolve() != orchestration_home.resolve()
                or str(orchestration_home.resolve()) != validated_scope["canonical_root"]
            ):
                raise JournalError("checked import execution_scope_unsupported")
            if not workspace.is_dir():
                raise JournalError(f"checked import workspace does not exist: {workspace}")
            if already_committed:
                check = task.get("check")
                if not isinstance(check, Mapping):
                    raise JournalError("checked import check is missing after commit")
                artifact_relative = _nonempty_string(check.get("artifact"), "checked import artifact")
                artifact = orchestration_home / artifact_relative
                if not artifact.is_file():
                    raise JournalError("checked import evidence is missing after commit")
            else:
                from validation import CheckExecutionError, direct_command_arguments, run_shared_check

                executable = direct_command_arguments(command)
                consumer_ref = f"import:{task_id}:{import_id}"

                def record_running(record: Mapping[str, Any]) -> None:
                    self.append(
                        "check_execution_recorded",
                        {
                            "execution_id": record["execution_id"],
                            "command_digest": record["command_digest"],
                            "source_snapshot_digest": record["source_snapshot_digest"],
                            "execution_policy_digest": record["execution_policy_digest"],
                            "timeout_seconds": record["timeout_seconds"],
                            "output_cap_bytes": record["output_cap_bytes"],
                            "owner_generation": record["owner_generation"],
                            "lifecycle": record["lifecycle"],
                            "artifact_ref": record["artifact_ref"],
                            "cleanup_ref": record["cleanup_ref"],
                            "cleanup_id": record["cleanup_id"],
                            "process_root": record["process_root"],
                            "process_group": record["process_group"],
                            "process_start_identity": record["process_start_identity"],
                            "cleanup_authority": record["cleanup_authority"],
                            "cleanup_authority_id": record["cleanup_authority_id"],
                            "consumer_ref": consumer_ref,
                        },
                        coordinator_generation=coordinator_generation,
                    )

                try:
                    execution = run_shared_check(
                        executable,
                        repository=orchestration_home,
                        workspace=workspace,
                        run_directory=self.path.parent,
                        workspace_scope=validated_scope,
                        base_revision=projection.get("base_commit"),
                        owner_generation=coordinator_generation,
                        timeout_seconds=timeout_seconds,
                        output_cap_bytes=output_cap_bytes,
                        consumer_ref=consumer_ref,
                        on_running=record_running,
                    )
                except CheckExecutionError as error:
                    raise JournalError(str(error)) from error
                artifact_relative = execution.artifact_ref
                artifact = orchestration_home / artifact_relative
                binding = {
                    "execution_id": execution.execution_id,
                    "command_digest": execution.command_digest,
                    "source_snapshot_digest": execution.source_snapshot_digest,
                    "execution_policy_digest": execution.execution_policy_digest,
                    "timeout_seconds": execution.timeout_seconds,
                    "output_cap_bytes": execution.output_cap_bytes,
                    "owner_generation": execution.owner_generation,
                    "lifecycle": execution.lifecycle,
                    "artifact_ref": execution.artifact_ref,
                    "cleanup_ref": execution.cleanup_ref,
                    "cleanup_id": execution.cleanup_id,
                    "process_root": execution.process_root,
                    "process_group": execution.process_group,
                    "process_start_identity": execution.process_start_identity,
                    "cleanup_authority": execution.cleanup_authority,
                    "cleanup_authority_id": execution.cleanup_authority_id or None,
                    "consumer_ref": consumer_ref,
                }
                projection = self.replay()
                recorded = projection.get("check_executions", {}).get(execution.execution_id)
                if (
                    not isinstance(recorded, Mapping)
                    or binding["consumer_ref"] not in recorded.get("consumer_refs", [])
                    or binding["lifecycle"] != recorded.get("lifecycle")
                ):
                    try:
                        projection = self.append(
                            "check_execution_recorded", binding,
                            coordinator_generation=coordinator_generation,
                        )
                    except StaleRevisionError:
                        projection = self.replay()
                        recorded = projection.get("check_executions", {}).get(execution.execution_id)
                        if (
                            not isinstance(recorded, Mapping)
                            or binding["consumer_ref"] not in recorded.get("consumer_refs", [])
                            or binding["lifecycle"] != recorded.get("lifecycle")
                        ):
                            projection = self.append(
                                "check_execution_recorded", binding,
                                coordinator_generation=coordinator_generation,
                            )
            try:
                evidence = json.loads(artifact.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as error:
                raise JournalError(f"checked import evidence is unreadable: {artifact}") from error
            if not isinstance(evidence, Mapping):
                raise JournalError("checked import evidence must be an object")
            try:
                evidence = _exact_fields(
                    evidence,
                    {
                        "schema_version", "execution_id", "command_digest", "source_snapshot_digest",
                        "execution_policy_digest", "timeout_seconds", "output_cap_bytes",
                        "exit_code", "duration_ms", "stdout", "stderr", "start_error",
                        "timed_out", "residue_unverifiable",
                    },
                    set(),
                    "checked import evidence",
                )
                if evidence["schema_version"] != SCHEMA_VERSION or isinstance(
                    evidence["schema_version"], bool
                ):
                    raise GraphValidationError("checked import evidence schema_version is invalid")
                for digest_field in (
                    "command_digest",
                    "source_snapshot_digest",
                    "execution_policy_digest",
                ):
                    if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(evidence[digest_field])):
                        raise GraphValidationError(
                            f"checked import evidence {digest_field} must be sha256"
                        )
                timeout_seconds = evidence["timeout_seconds"]
                output_cap_bytes = evidence["output_cap_bytes"]
                if (
                    not isinstance(timeout_seconds, (int, float))
                    or isinstance(timeout_seconds, bool)
                    or not math.isfinite(timeout_seconds)
                    or not 0 < timeout_seconds <= 3_600
                    or not isinstance(output_cap_bytes, int)
                    or isinstance(output_cap_bytes, bool)
                    or not 1 <= output_cap_bytes <= 1_048_576
                ):
                    raise GraphValidationError("checked import evidence policy is invalid")
                policy = {
                    "output_cap_bytes": output_cap_bytes,
                    "timeout_seconds": float(timeout_seconds),
                }
                policy_digest = f"sha256:{hashlib.sha256(json.dumps(policy, separators=(',', ':'), sort_keys=True).encode('utf-8')).hexdigest()}"
                if evidence["execution_policy_digest"] != policy_digest:
                    raise GraphValidationError("checked import evidence policy digest diverges")
                if (
                    not isinstance(evidence["exit_code"], int)
                    or isinstance(evidence["exit_code"], bool)
                    or not isinstance(evidence["duration_ms"], int)
                    or isinstance(evidence["duration_ms"], bool)
                    or evidence["duration_ms"] < 0
                ):
                    raise GraphValidationError("checked import evidence numbers are invalid")
                for output_field in ("stdout", "stderr"):
                    if not isinstance(evidence[output_field], str):
                        raise GraphValidationError(
                            f"checked import evidence {output_field} must be text"
                        )
                execution = projection.get("check_executions", {}).get(evidence["execution_id"])
                if not isinstance(execution, Mapping):
                    raise GraphValidationError("checked import evidence has no durable execution")
                for field in (
                    "execution_id",
                    "command_digest",
                    "source_snapshot_digest",
                    "execution_policy_digest",
                    "timeout_seconds",
                    "output_cap_bytes",
                ):
                    if execution.get(field) != evidence[field]:
                        raise GraphValidationError(
                            f"checked import evidence {field} diverges from its durable execution"
                        )
                if execution.get("artifact_ref") != artifact_relative:
                    raise GraphValidationError(
                        "checked import evidence artifact diverges from its durable execution"
                    )
            except GraphValidationError as error:
                raise JournalError(f"checked import evidence is invalid: {error}") from error
            if evidence.get("exit_code") != 0:
                raise JournalError(
                    f"checked import check failed; evidence: {artifact_relative}"
                )
            check = {
                "task_id": task_id,
                "command": command,
                "status": "passed",
                "exit_code": 0,
                "duration_ms": evidence["duration_ms"],
                "attempts": 1,
                "total_duration_ms": evidence["duration_ms"],
                "artifact": artifact_relative,
                "evidence_ref": f"file:{artifact_relative}",
            }
            if already_committed:
                if task.get("check") != check:
                    raise JournalError("checked import evidence diverges from the committed check")
                atomic_write_json(self.projection_path, projection)
                return projection
            try:
                return self.append(
                    "checked_task_imported",
                    {
                        "task_id": task_id,
                        "import_id": import_id,
                        "source_checked": True,
                        "check": check,
                        "note": note,
                    },
                    coordinator_generation=coordinator_generation,
                )
            except JournalError:
                replayed = self.replay()
                replayed_receipt = replayed["tasks"][task_id].get("import_receipt")
                if isinstance(replayed_receipt, Mapping) and replayed_receipt.get(
                    "import_id"
                ) == import_id:
                    atomic_write_json(self.projection_path, replayed)
                    return replayed
                raise

    def verify_projection(self) -> dict[str, Any]:
        """Rebuild the journal and require the saved projection to match."""

        with self._lock, self._interprocess_lock():
            events, partial = self._read_complete_events()
            if partial:
                raise JournalError("journal has a partial final line; repair it before replay")
            projection = replay_events(events)
            if not self.projection_path.is_file():
                raise JournalError(f"saved projection does not exist: {self.projection_path}")
            try:
                saved = json.loads(self.projection_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as error:
                raise JournalError(f"cannot read saved projection: {error}") from error
            if saved != projection:
                raise JournalError("saved projection does not match journal replay")
            self._reconcile_staged_check_recoveries(projection)
            self._expected_revision = projection["last_sequence"]
            return projection

    def rebuild_projection(self) -> dict[str, Any]:
        """Rebuild the disposable saved projection from the canonical journal."""

        with self._lock, self._interprocess_lock():
            events, partial = self._read_complete_events()
            if partial:
                raise JournalError("journal has a partial final line; repair it before replay")
            projection = replay_events(events)
            atomic_write_json(self.projection_path, projection)
            self._expected_revision = projection["last_sequence"]
            return projection


# Short aliases keep downstream driver and CLI code readable.
parse_tasks = parse_tasks_file
paths_overlap = path_scopes_overlap
schedule_ready = ready_tasks
replay_journal = replay_events
