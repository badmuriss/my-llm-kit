#!/usr/bin/env python3
"""Parse task graphs and maintain their canonical event journal."""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence


SCHEMA_VERSION = 1
TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*$")
TASK_HEADER_PATTERN = re.compile(
    r"^\s*-\s+\[([ xX])\]\s+"
    r"([A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*)\s+(.+?)\s*$"
)
FIELD_PATTERN = re.compile(r"^\s+(?:-\s*)?([A-Za-z][A-Za-z-]*):\s*(.*?)\s*$")
EVENT_ID_PATTERN = re.compile(r"^event-[0-9]{6,}$")
COMMIT_PATTERN = re.compile(r"^(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$")
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
        "attempt_started",
        "attempt_observed",
        "attempt_start_failed",
        "attempt_abandoned",
        "driver_degraded",
        "question_opened",
        "question_answered",
        "worker_reported",
        "check_recorded",
        "repair_recorded",
        "task_graded",
        "cleanup_registered",
        "cleanup_finished",
        "journal_repaired",
        "run_completed",
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


def parse_task_graph(source: str | Path, *, source_name: str | None = None) -> TaskGraph:
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
        state = _task_projection(projection, task.id)
        if state.get("grade") is not None or task.id in active_ids:
            continue
        if any(_task_projection(projection, dependency).get("grade") != "pass" for dependency in task.depends):
            continue
        if any(tasks_conflict(task, active) for active in active_writes):
            continue
        if any(tasks_conflict(task, candidate) for candidate in selected):
            continue
        selected.append(task)
    return selected


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
    _validate_string_list(result["checks_run"], "worker result checks_run")
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
    if not isinstance(external_refs, Mapping) or any(
        not isinstance(key, str) or not key or not isinstance(value, (str, int, bool, type(None)))
        for key, value in external_refs.items()
    ):
        raise GraphValidationError("worker result external_refs must be a scalar-valued object")
    return json.loads(json.dumps(dict(result), sort_keys=True))


def validate_coordinator_capsule(capsule: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a transcript-free fresh-coordinator handoff capsule."""

    required = {
        "schema_version",
        "repository",
        "change",
        "run_id",
        "driver",
        "base_commit",
        "dirty_paths",
        "coordinator_generation",
        "resume_command",
    }
    if not isinstance(capsule, Mapping):
        raise GraphValidationError("coordinator capsule must be an object")
    unknown = sorted(set(capsule) - required)
    missing = sorted(required - set(capsule))
    if unknown:
        raise GraphValidationError(f"coordinator capsule has unknown fields: {', '.join(unknown)}")
    if missing:
        raise GraphValidationError(f"coordinator capsule is missing fields: {', '.join(missing)}")
    if capsule["schema_version"] != SCHEMA_VERSION:
        raise GraphValidationError("coordinator capsule schema_version is unsupported")
    repository = _nonempty_string(capsule["repository"], "coordinator capsule repository")
    if not Path(repository).is_absolute():
        raise GraphValidationError("coordinator capsule repository must be absolute")
    for field in ("change", "run_id"):
        value = _nonempty_string(capsule[field], f"coordinator capsule {field}")
        if not TASK_ID_PATTERN.fullmatch(value):
            raise GraphValidationError(f"coordinator capsule {field} is invalid")
    if capsule["driver"] not in {"auto", "host", "orca"}:
        raise GraphValidationError("coordinator capsule driver must be auto, host, or orca")
    _nonempty_string(capsule["base_commit"], "coordinator capsule base_commit")
    dirty_paths = _validate_string_list(capsule["dirty_paths"], "coordinator capsule dirty_paths")
    for dirty_path in dirty_paths:
        normalize_repo_path(dirty_path, "coordinator capsule dirty path")
    generation = capsule["coordinator_generation"]
    if not isinstance(generation, int) or isinstance(generation, bool) or generation < 1:
        raise GraphValidationError("coordinator capsule generation must be a positive integer")
    _nonempty_string(capsule["resume_command"], "coordinator capsule resume_command")
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
        "coordinator": {"id": None, "generation": 0},
        "driver": None,
        "driver_reservation": None,
        "tasks": {},
        "attempts": {},
        "questions": {},
        "cleanup": {},
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
            }
        state.update(
            {
                "change": change,
                "run_id": run_id,
                "status": "active",
                "base_commit": data.get("base_commit"),
                "dirty_paths": list(data.get("dirty_paths", [])),
                "tasks": task_states,
            }
        )
        state["coordinator"] = {
            "id": data.get("coordinator_id"),
            "generation": generation,
        }
    elif state["status"] == "new":
        raise JournalError("run_started must be the first event")
    elif event_type == "coordinator_claimed":
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
    elif event_type == "attempt_reserved":
        task_id = _known_task(state, data.get("task_id"))
        attempt_id = _nonempty_string(data.get("attempt_id"), "attempt_reserved attempt_id")
        if attempt_id in state["attempts"]:
            raise JournalError(f"duplicate attempt ID: {attempt_id}")
        attempt = json.loads(json.dumps(dict(data), sort_keys=True))
        attempt["status"] = "reserved"
        state["attempts"][attempt_id] = attempt
        state["tasks"][task_id]["attempt_ids"].append(attempt_id)
        state["tasks"][task_id]["status"] = "reserved"
    elif event_type == "attempt_started":
        task_id = _known_task(state, data.get("task_id"))
        attempt_id = _nonempty_string(data.get("attempt_id"), "attempt_started attempt_id")
        existing = state["attempts"].get(attempt_id)
        if existing is None:
            attempt = json.loads(json.dumps(dict(data), sort_keys=True))
            state["attempts"][attempt_id] = attempt
            state["tasks"][task_id]["attempt_ids"].append(attempt_id)
        elif existing.get("status") in {"reserved", "interrupted"} and existing.get("task_id") == task_id:
            attempt = existing
            attempt.update(json.loads(json.dumps(dict(data), sort_keys=True)))
        else:
            raise JournalError(f"duplicate attempt ID: {attempt_id}")
        attempt["status"] = "running"
        state["tasks"][task_id]["status"] = "running"
    elif event_type in {"attempt_start_failed", "attempt_abandoned"}:
        attempt_id = _nonempty_string(data.get("attempt_id"), f"{event_type} attempt_id")
        if attempt_id not in state["attempts"]:
            raise JournalError(f"{event_type} references unknown attempt: {attempt_id}")
        attempt = state["attempts"][attempt_id]
        if attempt["status"] not in {"reserved", "running", "interrupted"}:
            raise JournalError(f"attempt cannot transition from {attempt['status']}: {attempt_id}")
        attempt.update(json.loads(json.dumps(dict(data), sort_keys=True)))
        attempt["status"] = "interrupted" if event_type == "attempt_start_failed" else "abandoned"
        state["tasks"][attempt["task_id"]]["status"] = attempt["status"]
    elif event_type == "attempt_observed":
        attempt_id = _nonempty_string(data.get("attempt_id"), "attempt_observed attempt_id")
        if attempt_id not in state["attempts"]:
            raise JournalError(f"attempt_observed references unknown attempt: {attempt_id}")
        if "cursor" in data:
            state["attempts"][attempt_id]["cursor"] = data.get("cursor")
        state["attempts"][attempt_id]["last_poll_receipt"] = data.get("receipt_path")
    elif event_type == "driver_degraded":
        state["degradations"].append(json.loads(json.dumps(dict(data), sort_keys=True)))
    elif event_type == "question_opened":
        attempt_id = _nonempty_string(data.get("attempt_id"), "question_opened attempt_id")
        if attempt_id not in state["attempts"]:
            raise JournalError(f"question references unknown attempt: {attempt_id}")
        question_id = _nonempty_string(data.get("question_id"), "question_opened question_id")
        if question_id in state["questions"]:
            raise JournalError(f"duplicate question ID: {question_id}")
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
        task_id = attempt["task_id"]
        if data.get("task_id", task_id) != task_id:
            raise JournalError("worker report task does not match its attempt")
        attempt["status"] = "reported"
        attempt["report"] = json.loads(json.dumps(dict(data), sort_keys=True))
        state["tasks"][task_id]["status"] = "reported"
    elif event_type == "check_recorded":
        task_id = _known_task(state, data.get("task_id"))
        state["tasks"][task_id]["check"] = json.loads(json.dumps(dict(data), sort_keys=True))
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
        if state["tasks"][task_id]["grade"] is not None:
            raise JournalError(f"task already graded: {task_id}")
        state["tasks"][task_id]["grade"] = grade
        state["tasks"][task_id]["status"] = grade
        state["tasks"][task_id]["note"] = _nonempty_string(
            data.get("note"), "task_graded note"
        )
        evidence_refs = data.get("evidence_refs", [])
        if not isinstance(evidence_refs, list) or any(
            not isinstance(reference, str) or not reference for reference in evidence_refs
        ):
            raise JournalError("task_graded evidence_refs must be an array of strings")
        state["tasks"][task_id]["evidence_refs"] = list(evidence_refs)
    elif event_type == "cleanup_registered":
        cleanup_id = _nonempty_string(data.get("cleanup_id"), "cleanup_registered cleanup_id")
        if cleanup_id in state["cleanup"]:
            raise JournalError(f"duplicate cleanup ID: {cleanup_id}")
        state["cleanup"][cleanup_id] = {
            **json.loads(json.dumps(dict(data), sort_keys=True)),
            "status": "pending",
        }
    elif event_type == "cleanup_finished":
        cleanup_id = _nonempty_string(data.get("cleanup_id"), "cleanup_finished cleanup_id")
        if cleanup_id not in state["cleanup"]:
            raise JournalError(f"unknown cleanup ID: {cleanup_id}")
        state["cleanup"][cleanup_id]["status"] = "done"
        state["cleanup"][cleanup_id]["receipt"] = data.get("receipt")
    elif event_type == "journal_repaired":
        _nonempty_string(data.get("artifact"), "journal_repaired artifact")
    elif event_type == "run_completed":
        outcome = data.get("outcome")
        if outcome not in {"pass", "partial", "blocked"}:
            raise JournalError("run_completed outcome must be pass, partial, or blocked")
        state["status"] = "complete"
        state["outcome"] = outcome
    state["last_sequence"] = event["sequence"]
    return state


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

    def replay(self) -> dict[str, Any]:
        """Replay complete journal lines; reject any unhandled partial tail."""

        events, partial = self._read_complete_events()
        if partial:
            raise JournalError("journal has a partial final line; repair it before replay")
        return replay_events(events)

    def recover_partial_line(
        self,
        artifact_path: Path,
        *,
        coordinator_generation: int,
    ) -> dict[str, Any]:
        """Archive and remove only a non-newline-terminated final journal line."""

        with self._lock:
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
        with self._lock:
            events, partial = self._read_complete_events()
            if partial:
                raise JournalError("journal has a partial final line; repair it before appending")
            projection = replay_events(events)
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
            return next_projection

    def verify_projection(self) -> dict[str, Any]:
        """Rebuild the journal and require the saved projection to match."""

        projection = self.replay()
        if not self.projection_path.is_file():
            raise JournalError(f"saved projection does not exist: {self.projection_path}")
        try:
            saved = json.loads(self.projection_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise JournalError(f"cannot read saved projection: {error}") from error
        if saved != projection:
            raise JournalError("saved projection does not match journal replay")
        return projection

    def rebuild_projection(self) -> dict[str, Any]:
        """Rebuild the disposable saved projection from the canonical journal."""

        projection = self.replay()
        atomic_write_json(self.projection_path, projection)
        return projection


# Short aliases keep downstream driver and CLI code readable.
parse_tasks = parse_tasks_file
paths_overlap = path_scopes_overlap
schedule_ready = ready_tasks
replay_journal = replay_events
