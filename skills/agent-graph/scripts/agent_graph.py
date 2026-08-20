#!/usr/bin/env python3
"""Cross-platform command line runtime for repository-owned agent graphs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence


SCRIPTS_DIRECTORY = Path(__file__).resolve().parent
if str(SCRIPTS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIRECTORY))

from drivers.base import DriverError, DriverReceipt  # noqa: E402
from drivers.host import (  # noqa: E402
    DuplicateResultError,
    HostDriver,
    dependency_digest_from_projection,
)
from drivers.orca import OrcaDriver  # noqa: E402
from graph_core import (  # noqa: E402
    GRADES,
    SCHEMA_VERSION,
    EventJournal,
    GraphError,
    JournalError,
    StaleCoordinatorError,
    TaskContract,
    TaskGraph,
    atomic_write_json,
    parse_task_graph,
    ready_tasks,
    task_blockers,
    validate_coordinator_capsule,
    validate_worker_result,
)
from runtime_config import (  # noqa: E402
    RuntimeConfigError,
    add_runtime_arguments,
    runtime_from_arguments,
)
from validation import (  # noqa: E402
    CLEANUP_KINDS,
    CliValidationError,
    canonical_receipt_id,
    cleanup_target_exists,
    direct_command_arguments,
    load_json_object,
    repository_relative_path,
    require_identifier,
)
from visual_evidence import (  # noqa: E402
    VisualEvidenceError,
    parse_visual_scope,
    validate_manifest,
)


RUNS_DIRECTORY = Path("openspec/runs")
OUTCOMES = frozenset({"pass", "partial", "blocked"})
DRIVERS = frozenset({"auto", "host", "orca"})
FRONTEND_SUFFIXES = frozenset(
    {
        ".astro", ".avif", ".css", ".gif", ".html", ".jpeg", ".jpg",
        ".jsx", ".less", ".mdx", ".png", ".sass", ".scss", ".svelte",
        ".svg", ".tsx", ".vue", ".webp",
    }
)


class AgentGraphCliError(RuntimeError):
    """An actionable error with a stable machine-facing code."""

    def __init__(self, message: str, *, code: str = "invalid_operation") -> None:
        super().__init__(message)
        self.code = code


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _git(repository: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _current_commit(repository: Path) -> str:
    result = _git(repository, "rev-parse", "HEAD")
    return result.stdout.strip() if result.returncode == 0 else "unborn"


def _dirty_paths(repository: Path) -> list[str]:
    result = _git(repository, "status", "--porcelain=v1", "-z")
    if result.returncode != 0:
        return []
    paths: set[str] = set()
    entries = result.stdout.split("\0")
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if not entry:
            continue
        status = entry[:2]
        path = entry[3:]
        if status[0] in {"R", "C"} and index < len(entries):
            path = entries[index]
            index += 1
        if path:
            paths.add(Path(path).as_posix())
    return sorted(paths)


def _changed_paths_since(repository: Path, base_commit: str) -> list[str]:
    paths: set[str] = set()
    for arguments in (
        ("diff", "--name-only", base_commit),
        ("ls-files", "--others", "--exclude-standard"),
    ):
        result = _git(repository, *arguments)
        if result.returncode != 0:
            raise AgentGraphCliError(
                f"cannot inspect changed paths with git {' '.join(arguments)}",
                code="git_inspection_failed",
            )
        paths.update(line.strip() for line in result.stdout.splitlines() if line.strip())
    return sorted(paths)


def _frontend_paths(paths: Sequence[str]) -> list[str]:
    return sorted(path for path in paths if Path(path).suffix.casefold() in FRONTEND_SUFFIXES)


def _task_file(repository: Path, change: str) -> Path:
    require_identifier(change, "change")
    change_directory = repository / "openspec" / "changes" / change
    missing = [name for name in ("proposal.md", "design.md", "tasks.md") if not (change_directory / name).is_file()]
    if missing:
        raise AgentGraphCliError(
            f"OpenSpec change {change} is missing: {', '.join(missing)}",
            code="change_not_found",
        )
    return change_directory / "tasks.md"


def _load_graph(repository: Path, change: str) -> TaskGraph:
    return parse_task_graph(_task_file(repository, change))


def _run_directory(repository: Path, change: str, run_id: str | None) -> Path:
    require_identifier(change, "change")
    root = repository / RUNS_DIRECTORY / change
    if run_id is not None:
        require_identifier(run_id, "run_id")
        directory = root / run_id
        if not (directory / "events.jsonl").is_file():
            raise AgentGraphCliError(f"run does not exist: {change}/{run_id}", code="run_not_found")
        return directory
    candidates = sorted(
        directory
        for directory in root.iterdir()
        if directory.is_dir() and (directory / "events.jsonl").is_file()
    ) if root.is_dir() else []
    active: list[Path] = []
    for directory in candidates:
        try:
            state = EventJournal(directory / "events.jsonl").replay()
        except JournalError:
            active.append(directory)
            continue
        if state.get("status") == "active":
            active.append(directory)
    if len(active) == 1:
        return active[0]
    if not active:
        raise AgentGraphCliError(f"no active run exists for {change}", code="run_not_found")
    raise AgentGraphCliError(
        f"multiple active runs exist for {change}; pass --run-id",
        code="ambiguous_run",
    )


def _new_run_directory(repository: Path, change: str, run_id: str) -> Path:
    require_identifier(change, "change")
    require_identifier(run_id, "run_id")
    directory = repository / RUNS_DIRECTORY / change / run_id
    if directory.exists() and any(directory.iterdir()):
        raise AgentGraphCliError(f"run directory already exists: {directory}", code="run_exists")
    directory.mkdir(parents=True, exist_ok=True)
    for name in ("artifacts", "capsules", "results"):
        (directory / name).mkdir(exist_ok=True)
    return directory


def _journal(directory: Path) -> EventJournal:
    return EventJournal(directory / "events.jsonl", directory / "state.json")


def _projection(directory: Path) -> dict[str, Any]:
    return _journal(directory).verify_projection()


def _generation(arguments: argparse.Namespace, projection: Mapping[str, Any]) -> int:
    supplied = getattr(arguments, "generation", None)
    if supplied is None:
        raise AgentGraphCliError(
            "mutating commands require --generation from the coordinator capsule",
            code="generation_required",
        )
    current = projection["coordinator"]["generation"]
    if supplied != current:
        raise StaleCoordinatorError(
            f"coordinator generation {supplied} is stale; current generation is {current}"
        )
    return supplied


def _task_from_state(projection: Mapping[str, Any], task_id: str) -> TaskContract:
    task_state = projection.get("tasks", {}).get(task_id)
    if not isinstance(task_state, Mapping):
        raise AgentGraphCliError(f"unknown task: {task_id}", code="unknown_task")
    contract = task_state.get("contract")
    if not isinstance(contract, Mapping):
        raise AgentGraphCliError(f"task {task_id} has a malformed saved contract", code="invalid_state")
    try:
        return TaskContract(
            id=str(contract["id"]),
            title=str(contract["title"]),
            depends=tuple(contract["depends"]),
            paths=tuple(contract["paths"]),
            mode=str(contract["mode"]),
            isolation=str(contract["isolation"]),
            acceptance=str(contract["acceptance"]),
            check=str(contract["check"]),
            context=str(contract.get("context", "")),
            visual=tuple(contract.get("visual", ())),
            visual_scope=tuple(contract.get("visual_scope", ())),
            checked=bool(contract.get("checked", False)),
            source_line=int(contract.get("source_line", 0)),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise AgentGraphCliError(f"task {task_id} has a malformed saved contract", code="invalid_state") from error


def _saved_graph(projection: Mapping[str, Any]) -> TaskGraph:
    return TaskGraph(tuple(_task_from_state(projection, task_id) for task_id in projection["tasks"]))


def _write_receipt(repository: Path, directory: Path, receipt: Mapping[str, Any]) -> tuple[str, str]:
    receipt_id = canonical_receipt_id(receipt)
    path = directory / "artifacts" / "receipts" / f"{receipt_id}.json"
    if path.exists():
        if load_json_object(path, "saved receipt") != dict(receipt):
            raise AgentGraphCliError(f"receipt collision: {receipt_id}", code="receipt_collision")
    else:
        atomic_write_json(path, dict(receipt))
    return receipt_id, path.relative_to(repository).as_posix()


def _driver_receipt(repository: Path, directory: Path, receipt: DriverReceipt) -> tuple[str, str]:
    return _write_receipt(repository, directory, receipt.to_dict())


def _driver_for_state(repository: Path, directory: Path, projection: Mapping[str, Any]):
    selected = projection.get("driver")
    if selected == "host":
        return HostDriver(repository, directory)
    if selected == "orca":
        driver = OrcaDriver(repository)
        driver.detect()
        events, _ = _journal(directory)._read_complete_events()
        selection = next((event["data"] for event in events if event["type"] == "driver_selected"), {})
        refs = selection.get("external_refs", {}) if isinstance(selection, Mapping) else {}
        if isinstance(refs, Mapping):
            driver.run_id = refs.get("run_id")
            task_ids = refs.get("task_ids")
            if isinstance(task_ids, Mapping):
                driver.task_ids = {str(key): str(value) for key, value in task_ids.items()}
        for attempt_id, attempt in projection.get("attempts", {}).items():
            if not isinstance(attempt, Mapping):
                continue
            attempt_refs = attempt.get("external_refs")
            terminal = attempt_refs.get("terminal") if isinstance(attempt_refs, Mapping) else None
            if attempt.get("tier") == "tracked-terminal" and isinstance(terminal, Mapping):
                driver.created_terminals[str(attempt_id)] = dict(terminal)
        return driver
    raise AgentGraphCliError("run has no selected driver", code="driver_not_selected")


def _select_driver(
    repository: Path,
    directory: Path,
    requested: str,
    graph: TaskGraph,
    *,
    retry_request: str | None = None,
):
    if requested not in DRIVERS:
        raise AgentGraphCliError(f"unknown driver: {requested}", code="invalid_driver")
    detection_error: dict[str, Any] | None = None
    if requested in {"auto", "orca"}:
        orca = OrcaDriver(repository)
        try:
            detected = orca.detect()
        except DriverError as error:
            if requested == "orca":
                raise
            detection_error = {"code": error.code, "message": str(error), "receipt": error.receipt}
        else:
            started = orca.start_run(
                f"Implement OpenSpec change {graph.tasks[0].id.split('-')[0]}",
                [
                    {
                        "id": task.id,
                        "depends": list(task.depends),
                        "capsule": task.acceptance,
                    }
                    for task in graph.tasks
                ],
                retry_request=retry_request,
            )
            return "orca", orca, detected, started, "Orca satisfied the tracked lifecycle contract"
    host = HostDriver(repository, directory)
    detected = host.detect()
    started = host.start_run("Execute the repository agent graph", [task.to_dict() for task in graph.tasks])
    reason = "host was explicitly selected"
    if detection_error:
        reason = f"auto selected host because Orca detection failed: {detection_error['code']}"
    return "host", host, detected, started, reason


def _select_and_record_driver(
    repository: Path,
    directory: Path,
    journal: EventJournal,
    projection: dict[str, Any],
    requested: str,
    graph: TaskGraph,
    generation: int,
    *,
    recover: bool = False,
) -> tuple[dict[str, Any], dict[str, str | None]]:
    reservation = projection.get("driver_reservation")
    if reservation is not None and not recover:
        raise AgentGraphCliError(
            "driver selection has an incomplete reservation; run resume and reconcile it before retrying",
            code="driver_selection_incomplete",
        )
    if isinstance(reservation, Mapping):
        reservation_id = str(reservation["reservation_id"])
        if reservation.get("requested") != requested:
            raise AgentGraphCliError("driver reservation requested another driver", code="driver_selection_mismatch")
    else:
        reservation_id = (
            f"driver-selection-{projection['run_id']}-generation-{generation}"
        )
        projection = journal.append(
            "driver_selection_reserved",
            {"reservation_id": reservation_id, "requested": requested},
            coordinator_generation=generation,
        )
    try:
        selected, _, detection, started, reason = _select_driver(
            repository, directory, requested, graph, retry_request=reservation_id
        )
    except DriverError as error:
        journal.append(
            "driver_selection_failed",
            {
                "reservation_id": reservation_id,
                "code": error.code,
                "message": str(error),
                "receipt": error.receipt,
            },
            coordinator_generation=generation,
        )
        raise
    detected_id, detected_path = _driver_receipt(repository, directory, detection)
    started_id, started_path = _driver_receipt(repository, directory, started)
    projection = journal.append(
        "driver_selected",
        {
            "reservation_id": reservation_id,
            "requested": requested,
            "driver": selected,
            "reason": reason,
            "external_refs": dict(started.external_refs),
            "receipts": [detected_path, started_path],
            "receipt_ids": [detected_id, started_id],
        },
        coordinator_generation=generation,
    )
    return projection, {"requested": requested, "selected": selected, "reason": reason}


def _initialize(
    repository: Path,
    change: str,
    run_id: str,
    coordinator_id: str,
    driver_name: str,
    *,
    defer_driver: bool = False,
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    require_identifier(coordinator_id, "coordinator_id")
    graph = _load_graph(repository, change)
    directory = _new_run_directory(repository, change, run_id)
    journal = _journal(directory)
    projection = journal.append(
        "run_started",
        {
            "change": change,
            "run_id": run_id,
            "coordinator_id": coordinator_id,
            "coordinator_generation": 1,
            "base_commit": _current_commit(repository),
            "dirty_paths": _dirty_paths(repository),
            "tasks": [task.to_dict() for task in graph.tasks],
        },
        coordinator_generation=1,
    )
    if defer_driver:
        return directory, projection, {
            "requested": driver_name,
            "selected": None,
            "reason": "driver selection is deferred until the fresh coordinator claims the run",
        }
    projection, selection = _select_and_record_driver(
        repository, directory, journal, projection, driver_name, graph, 1
    )
    return directory, projection, selection


def command_validate(arguments: argparse.Namespace) -> dict[str, Any]:
    graph = _load_graph(arguments.repo, arguments.change)
    return {"change": arguments.change, "valid": True, "task_count": len(graph.tasks), "tasks": [task.to_dict() for task in graph.tasks]}


def command_init(arguments: argparse.Namespace) -> dict[str, Any]:
    directory, projection, selection = _initialize(
        arguments.repo,
        arguments.change,
        arguments.run_id,
        arguments.coordinator_id,
        arguments.driver,
    )
    return {"run_directory": directory.relative_to(arguments.repo).as_posix(), "driver_selection": selection, "state": projection}


def command_bootstrap(arguments: argparse.Namespace) -> dict[str, Any]:
    bootstrap_id = arguments.bootstrap_id or f"bootstrap-{os.getpid()}"
    require_identifier(bootstrap_id, "bootstrap_id")
    directory, projection, selection = _initialize(
        arguments.repo,
        arguments.change,
        arguments.run_id,
        bootstrap_id,
        arguments.driver,
        defer_driver=True,
    )
    generation = projection["coordinator"]["generation"] + 1
    projection = _journal(directory).append(
        "coordinator_transferred",
        {
            "coordinator_id": None,
            "coordinator_generation": generation,
            "from_coordinator_id": bootstrap_id,
            "handoff": "fresh-top-level-session",
        },
        coordinator_generation=generation - 1,
    )
    relative_capsule = (
        directory / "capsules" / f"coordinator-generation-{generation}.json"
    ).relative_to(arguments.repo).as_posix()
    capsule = validate_coordinator_capsule(
        {
            "schema_version": SCHEMA_VERSION,
            "repository": str(arguments.repo),
            "change": arguments.change,
            "run_id": arguments.run_id,
            "driver": arguments.driver,
            "base_commit": _current_commit(arguments.repo),
            "dirty_paths": _dirty_paths(arguments.repo),
            "coordinator_generation": generation,
            "resume_command": f"$impl --coordinator-capsule {relative_capsule}",
        }
    )
    atomic_write_json(arguments.repo / relative_capsule, capsule)
    return {
        "change": arguments.change,
        "run_id": arguments.run_id,
        "capsule_path": relative_capsule,
        "invocation": capsule["resume_command"],
        "coordinator_generation": generation,
        "bootstrap_generation": generation - 1,
        "continue_in_bootstrap": False,
        "driver_selection": selection,
        "state": projection,
    }


def command_claim(arguments: argparse.Namespace) -> dict[str, Any]:
    path, relative = repository_relative_path(arguments.repo, arguments.capsule, "coordinator capsule")
    capsule = validate_coordinator_capsule(load_json_object(path, "coordinator capsule"))
    if Path(capsule["repository"]).resolve() != arguments.repo:
        raise AgentGraphCliError("coordinator capsule belongs to another repository", code="capsule_mismatch")
    directory = _run_directory(arguments.repo, capsule["change"], capsule["run_id"])
    journal = _journal(directory)
    projection = journal.verify_projection()
    generation = capsule["coordinator_generation"]
    if generation != projection["coordinator"]["generation"]:
        raise StaleCoordinatorError(
            f"capsule generation {generation} is stale; current generation is {projection['coordinator']['generation']}"
        )
    current_id = projection["coordinator"]["id"]
    idempotent = current_id == arguments.coordinator_id
    if current_id is not None and not idempotent:
        raise AgentGraphCliError(
            f"generation {generation} is already claimed by {current_id}; use takeover",
            code="coordinator_already_claimed",
        )
    if not idempotent:
        projection = journal.append(
            "coordinator_claimed",
            {"coordinator_id": arguments.coordinator_id, "capsule_path": relative},
            coordinator_generation=generation,
        )
    selection = None
    if projection.get("driver") is None:
        graph = _saved_graph(projection)
        projection, selection = _select_and_record_driver(
            arguments.repo,
            directory,
            journal,
            projection,
            capsule["driver"],
            graph,
            generation,
        )
    return {
        "claimed": True,
        "idempotent": idempotent,
        "capsule_path": relative,
        "driver_selection": selection,
        "state": projection,
    }


def command_takeover(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    projection = journal.verify_projection()
    generation = _generation(arguments, projection)
    driver = (
        _driver_for_state(arguments.repo, directory, projection)
        if projection.get("driver")
        else None
    )
    attempts = []
    for attempt_id, attempt in projection["attempts"].items():
        if attempt.get("status") not in {"reserved", "running", "interrupted"}:
            continue
        attempts.append({**attempt, "attempt_id": attempt_id, "task": _task_from_state(projection, attempt["task_id"]).to_dict()})
    reconciliation = (
        driver.reconcile(attempts)
        if driver is not None
        else DriverReceipt(
            "reconcile",
            "driver-selection-incomplete",
            raw={"driver_reservation": projection.get("driver_reservation")},
        )
    )
    receipt_id, receipt_path = _driver_receipt(arguments.repo, directory, reconciliation)
    next_generation = generation + 1
    projection = journal.append(
        "coordinator_taken_over",
        {
            "coordinator_id": arguments.coordinator_id,
            "coordinator_generation": next_generation,
            "prior_coordinator_id": projection["coordinator"]["id"],
            "reconciliation_receipt": receipt_path,
            "reconciliation_receipt_id": receipt_id,
        },
        coordinator_generation=generation,
    )
    return {"taken_over": True, "coordinator_generation": next_generation, "reconciliation": reconciliation.to_dict(), "state": projection}


def command_recover_driver_selection(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    projection = journal.verify_projection()
    generation = _generation(arguments, projection)
    if projection.get("driver") is not None:
        return {"recovered": True, "idempotent": True, "state": projection}
    reservation = projection.get("driver_reservation")
    if not isinstance(reservation, Mapping):
        raise AgentGraphCliError("run has no driver selection reservation", code="reservation_not_found")
    requested = str(reservation.get("requested") or "")
    projection, selection = _select_and_record_driver(
        arguments.repo,
        directory,
        journal,
        projection,
        requested,
        _saved_graph(projection),
        generation,
        recover=True,
    )
    return {"recovered": True, "idempotent": False, "driver_selection": selection, "state": projection}


def command_resume(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    try:
        projection = journal.verify_projection()
    except JournalError as error:
        if "partial final line" in str(error):
            if arguments.generation is None:
                raise
            artifact = directory / "artifacts" / f"partial-journal-{int(time.time())}.bin"
            projection = journal.recover_partial_line(artifact, coordinator_generation=arguments.generation)
        else:
            projection = journal.rebuild_projection()
    driver = _driver_for_state(arguments.repo, directory, projection) if projection.get("driver") else None
    attempts = [
        {**attempt, "attempt_id": attempt_id, "task": _task_from_state(projection, attempt["task_id"]).to_dict()}
        for attempt_id, attempt in projection["attempts"].items()
        if attempt.get("status") in {"reserved", "running", "interrupted"}
    ]
    if driver is None:
        reconciliation = DriverReceipt(
            "reconcile",
            "driver-selection-incomplete",
            raw={"driver_reservation": projection.get("driver_reservation")},
        )
    else:
        reconciliation = driver.reconcile(attempts)
    receipt_id, receipt_path = _driver_receipt(arguments.repo, directory, reconciliation)
    return {
        "change": projection["change"],
        "run_id": projection["run_id"],
        "coordinator": projection["coordinator"],
        "running_attempts": [
            attempt["attempt_id"] for attempt in attempts if attempt.get("status") == "running"
        ],
        "reserved_attempts": [
            attempt_id
            for attempt_id, attempt in projection["attempts"].items()
            if attempt.get("status") in {"reserved", "interrupted"}
        ],
        "driver_reservation": projection.get("driver_reservation"),
        "pending_cleanup": [item for item in projection["cleanup"].values() if item["status"] == "pending"],
        "dirty_paths": _dirty_paths(arguments.repo),
        "reconciliation_receipt": receipt_path,
        "reconciliation_receipt_id": receipt_id,
        "instruction": "Inspect the diff and reconciliation receipt before restarting work.",
    }


def command_ready(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    projection = _projection(directory)
    graph = _saved_graph(projection)
    selected = ready_tasks(graph, projection)
    return {
        "change": projection["change"],
        "run_id": projection["run_id"],
        "ready": [task.to_dict() for task in selected],
        "blocked": [
            {"task_id": task.id, "blockers": task_blockers(task, projection)}
            for task in graph.tasks
            if projection["tasks"][task.id]["grade"] is None and task not in selected and task_blockers(task, projection)
        ],
    }


def command_dispatch(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    projection = journal.verify_projection()
    generation = _generation(arguments, projection)
    graph = _saved_graph(projection)
    task = _task_from_state(projection, arguments.task)
    if task.id not in {candidate.id for candidate in ready_tasks(graph, projection)}:
        blockers = task_blockers(task, projection)
        detail = f"; blockers: {blockers}" if blockers else "; another active write owns an overlapping path"
        raise AgentGraphCliError(f"task {task.id} is not ready{detail}", code="task_not_ready")
    previous_attempts = projection["tasks"][task.id]["attempt_ids"]
    attempt_id = arguments.attempt_id or f"attempt-{task.id.lower()}-{len(previous_attempts) + 1:03d}"
    require_identifier(attempt_id, "attempt_id")
    dependency_digest = dependency_digest_from_projection(task, projection)
    driver = _driver_for_state(arguments.repo, directory, projection)
    request = {
        "task_id": task.id,
        "attempt_id": attempt_id,
        "task": task.to_dict(),
        "dependency_digest": dependency_digest,
        "worker_handle": arguments.worker,
        "local": arguments.local,
    }
    if projection["tasks"][task.id]["status"] != "ready":
        projection = journal.append("task_ready", {"task_id": task.id}, coordinator_generation=generation)
    projection = journal.append(
        "attempt_reserved",
        {
            "task_id": task.id,
            "attempt_id": attempt_id,
            "driver": projection["driver"],
            "worker": arguments.worker or ("local" if arguments.local else "host"),
            "task": task.to_dict(),
            "dependency_digest": dependency_digest,
        },
        coordinator_generation=generation,
    )
    try:
        receipt = driver.start_attempt(request)
    except DriverError as error:
        journal.append(
            "attempt_start_failed",
            {
                "task_id": task.id,
                "attempt_id": attempt_id,
                "code": error.code,
                "message": str(error),
                "receipt": error.receipt,
            },
            coordinator_generation=generation,
        )
        raise
    receipt_id, receipt_path = _driver_receipt(arguments.repo, directory, receipt)
    refs = dict(receipt.external_refs)
    cleanup_id = f"cleanup-{attempt_id}" if projection["driver"] == "orca" else None
    projection = journal.append(
        "attempt_started",
        {
            "task_id": task.id,
            "attempt_id": attempt_id,
            "driver": projection["driver"],
            "worker": arguments.worker or ("local" if arguments.local else "host"),
            "tier": refs.get("tier"),
            "external_refs": refs,
            "receipt_id": receipt_id,
            "receipt_path": receipt_path,
            "task": task.to_dict(),
            "dependency_digest": dependency_digest,
            "cleanup_id": cleanup_id,
        },
        coordinator_generation=generation,
    )
    if cleanup_id:
        projection = journal.append(
            "cleanup_registered",
            {
                "cleanup_id": cleanup_id,
                "kind": "terminal",
                "target": str(refs.get("dispatch_id") or attempt_id),
                "owner": attempt_id,
            },
            coordinator_generation=generation,
        )
    if receipt.degradation:
        projection = journal.append(
            "driver_degraded",
            {"attempt_id": attempt_id, "receipt_path": receipt_path, **dict(receipt.degradation)},
            coordinator_generation=generation,
        )
    return {"attempt_id": attempt_id, "capsule": refs.get("capsule_path"), "receipt": receipt.to_dict(), "state": projection}


def _result_argument(arguments: argparse.Namespace) -> dict[str, Any]:
    if arguments.result_json is not None:
        try:
            value = json.loads(arguments.result_json)
        except json.JSONDecodeError as error:
            raise AgentGraphCliError(f"--result-json is invalid JSON: {error.msg}", code="invalid_result") from error
        if not isinstance(value, dict):
            raise AgentGraphCliError("--result-json must contain an object", code="invalid_result")
        return value
    if arguments.result is None:
        raise AgentGraphCliError("record-result requires --result or --result-json", code="invalid_result")
    path, _ = repository_relative_path(arguments.repo, arguments.result, "worker result")
    return load_json_object(path, "worker result")


def _append_report(
    repository: Path,
    directory: Path,
    journal: EventJournal,
    projection: dict[str, Any],
    generation: int,
    attempt_id: str,
    result: Mapping[str, Any],
    receipt: Mapping[str, Any],
) -> tuple[dict[str, Any], bool]:
    attempt = projection["attempts"].get(attempt_id)
    if not isinstance(attempt, Mapping):
        raise AgentGraphCliError(f"unknown attempt: {attempt_id}", code="unknown_attempt")
    task = _task_from_state(projection, attempt["task_id"])
    validated = validate_worker_result(result, task, attempt_id)
    if attempt.get("status") == "reported":
        saved = attempt.get("report", {})
        comparable = {key: saved.get(key) for key in validated}
        if comparable != validated:
            raise AgentGraphCliError(f"attempt already has a different terminal report: {attempt_id}", code="duplicate_result")
        return projection, True
    receipt_id, receipt_path = _write_receipt(repository, directory, dict(receipt))
    projection = journal.append(
        "worker_reported",
        {**validated, "receipt_id": receipt_id, "receipt_path": receipt_path},
        coordinator_generation=generation,
    )
    return projection, False


def command_record_result(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    projection = journal.verify_projection()
    generation = _generation(arguments, projection)
    attempt = projection["attempts"].get(arguments.attempt)
    if not isinstance(attempt, Mapping):
        raise AgentGraphCliError(f"unknown attempt: {arguments.attempt}", code="unknown_attempt")
    result = _result_argument(arguments)
    task = _task_from_state(projection, attempt["task_id"])
    driver = _driver_for_state(arguments.repo, directory, projection)
    receipt_payload: Mapping[str, Any]
    if isinstance(driver, HostDriver):
        try:
            receipt = driver.record_result(task, arguments.attempt, result, projection=projection)
        except DuplicateResultError:
            saved = driver.read_result(task, arguments.attempt)
            if saved != validate_worker_result(result, task, arguments.attempt):
                raise
            receipt = DriverReceipt(
                "record_result",
                "reported",
                local_ids={"task_id": task.id, "attempt_id": arguments.attempt},
                raw={"result": saved, "recovered_existing_file": True},
            )
        receipt_payload = receipt.to_dict()
    else:
        receipt_payload = {"operation": "record_result", "status": "reported", "result": result}
    projection, idempotent = _append_report(
        arguments.repo,
        directory,
        journal,
        projection,
        generation,
        arguments.attempt,
        result,
        receipt_payload,
    )
    return {"attempt_id": arguments.attempt, "reported": True, "idempotent": idempotent, "state": projection}


def _walk_mappings(value: Any):
    if isinstance(value, Mapping):
        yield value
        for nested in value.values():
            yield from _walk_mappings(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_mappings(nested)


def _json_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, Mapping) else {}
    return {}


def _provider_messages(value: Any) -> list[Mapping[str, Any]]:
    messages: list[Mapping[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in _walk_mappings(value):
        kind = item.get("type") or item.get("kind")
        if kind not in {"question", "worker_done", "escalation", "worker_reported"}:
            continue
        message_id = str(
            item.get("messageId")
            or item.get("message_id")
            or item.get("id")
            or item.get("questionId")
            or item.get("question_id")
            or ""
        )
        key = (str(kind), message_id)
        if key not in seen:
            seen.add(key)
            messages.append(item)
    return messages


def _provider_delivery_id(value: Any) -> str | None:
    for item in _walk_mappings(value):
        delivery_id = item.get("deliveryId") or item.get("delivery_id")
        if isinstance(delivery_id, str) and delivery_id:
            return delivery_id
        if isinstance(item.get("messages"), list):
            candidate = item.get("id")
            if isinstance(candidate, str) and candidate.startswith("delivery"):
                return candidate
    return None


def _driver_attempt(attempt: Mapping[str, Any], attempt_id: str, task: TaskContract) -> dict[str, Any]:
    result = {**attempt, "attempt_id": attempt_id, "task": task.to_dict()}
    refs = attempt.get("external_refs")
    if isinstance(refs, Mapping):
        terminal = refs.get("terminal")
        result.update(
            {
                "dispatch_id": refs.get("dispatch_id"),
                "external_task_id": refs.get("task_id"),
                "terminal_handle": terminal.get("handle") if isinstance(terminal, Mapping) else None,
                "run_id": refs.get("run_id"),
            }
        )
    return result


def _provider_worker_result(
    message: Mapping[str, Any],
    task: TaskContract,
    attempt_id: str,
    attempt: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = _json_mapping(message.get("payload"))
    if attempt is not None:
        refs = attempt.get("external_refs")
        refs = refs if isinstance(refs, Mapping) else {}
        expected_task = attempt.get("external_task_id") or refs.get("task_id")
        expected_dispatch = attempt.get("dispatch_id") or refs.get("dispatch_id")
        actual_task = payload.get("taskId") or payload.get("task_id")
        actual_dispatch = payload.get("dispatchId") or payload.get("dispatch_id")
        if not actual_task or not actual_dispatch:
            raise AgentGraphCliError(
                "Orca lifecycle message omitted taskId or dispatchId",
                code="provider_identity_missing",
            )
        if actual_task != expected_task or actual_dispatch != expected_dispatch:
            raise AgentGraphCliError(
                "Orca lifecycle message does not match its local attempt",
                code="provider_identity_mismatch",
            )
    files = message.get("filesModified") or message.get("files_modified") or payload.get("filesModified") or payload.get("files_modified") or []
    if isinstance(files, str):
        files = [item.strip() for item in files.split(",") if item.strip()]
    if not isinstance(files, list):
        files = []
    checks = message.get("checksRun") or message.get("checks_run") or []
    if isinstance(checks, str):
        checks = [checks]
    if not isinstance(checks, list):
        checks = []
    message_id = str(message.get("messageId") or message.get("message_id") or message.get("id") or "")
    return validate_worker_result(
        {
            "task_id": task.id,
            "attempt_id": attempt_id,
            "outcome": "reported",
            "summary": str(message.get("body") or message.get("subject") or "Orca worker completed."),
            "files_changed": files,
            "checks_run": checks,
            "evidence_refs": [],
            "questions": [],
            "external_refs": {
                "provider": "orca",
                "message_id": message_id,
                "task_id": payload.get("taskId") or payload.get("task_id"),
                "dispatch_id": payload.get("dispatchId") or payload.get("dispatch_id"),
                "provider_outcome": message.get("outcome") or payload.get("outcome"),
            },
        },
        task,
        attempt_id,
    )


def _orca_attempt_for_message(
    projection: Mapping[str, Any], message: Mapping[str, Any]
) -> tuple[str, Mapping[str, Any]]:
    payload = _json_mapping(message.get("payload"))
    task_id = payload.get("taskId") or payload.get("task_id")
    dispatch_id = payload.get("dispatchId") or payload.get("dispatch_id")
    if not task_id or not dispatch_id:
        raise AgentGraphCliError(
            "Orca lifecycle message omitted taskId or dispatchId",
            code="provider_identity_missing",
        )
    matches: list[tuple[str, Mapping[str, Any]]] = []
    for attempt_id, attempt in projection["attempts"].items():
        if not isinstance(attempt, Mapping):
            continue
        refs = attempt.get("external_refs")
        if not isinstance(refs, Mapping):
            continue
        if refs.get("task_id") == task_id and refs.get("dispatch_id") == dispatch_id:
            matches.append((attempt_id, attempt))
    if len(matches) != 1:
        raise AgentGraphCliError(
            f"Orca lifecycle identity resolved {len(matches)} local attempts",
            code="provider_identity_ambiguous",
        )
    return matches[0]


def _finish_driver_cleanup(
    repository: Path,
    directory: Path,
    journal: EventJournal,
    projection: dict[str, Any],
    generation: int,
    attempt_id: str,
    driver: HostDriver | OrcaDriver,
) -> tuple[dict[str, Any], dict[str, Any]]:
    attempt = projection["attempts"].get(attempt_id)
    if not isinstance(attempt, Mapping):
        raise AgentGraphCliError(f"unknown attempt: {attempt_id}", code="unknown_attempt")
    cleanup_id = attempt.get("cleanup_id")
    cleanup = projection["cleanup"].get(cleanup_id) if cleanup_id else None
    if not isinstance(cleanup, Mapping):
        raise AgentGraphCliError(
            f"attempt has no driver-owned cleanup: {attempt_id}",
            code="cleanup_not_owned",
        )
    if cleanup.get("owner") != attempt_id:
        raise AgentGraphCliError(
            f"cleanup owner does not match attempt: {attempt_id}",
            code="cleanup_owner_mismatch",
        )
    if cleanup.get("status") == "done":
        return projection, {
            "attempt_id": attempt_id,
            "cleanup_id": cleanup_id,
            "finished": True,
            "idempotent": True,
        }
    if attempt.get("status") != "reported":
        raise AgentGraphCliError(
            f"driver cleanup recovery requires a reported attempt, got {attempt.get('status')}",
            code="cleanup_not_recoverable",
        )
    task = _task_from_state(projection, attempt["task_id"])
    released = driver.release(_driver_attempt(attempt, attempt_id, task))
    receipt_id, receipt_path = _driver_receipt(repository, directory, released)
    projection = journal.append(
        "cleanup_finished",
        {
            "cleanup_id": cleanup_id,
            "receipt": {
                "receipt_id": receipt_id,
                "receipt_path": receipt_path,
                "driver": released.to_dict(),
            },
        },
        coordinator_generation=generation,
    )
    return projection, {
        "attempt_id": attempt_id,
        "cleanup_id": cleanup_id,
        "finished": True,
        "idempotent": False,
        "receipt_id": receipt_id,
        "receipt_path": receipt_path,
    }


def command_sync(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    projection = journal.verify_projection()
    generation = _generation(arguments, projection)
    driver = _driver_for_state(arguments.repo, directory, projection)
    observed: list[dict[str, Any]] = []
    for attempt_id, attempt in list(projection["attempts"].items()):
        if not isinstance(attempt, Mapping):
            continue
        cleanup_id = attempt.get("cleanup_id")
        cleanup = projection["cleanup"].get(cleanup_id) if cleanup_id else None
        if attempt.get("status") != "reported" or not isinstance(cleanup, Mapping):
            continue
        if cleanup.get("status") != "pending":
            continue
        projection, recovered = _finish_driver_cleanup(
            arguments.repo,
            directory,
            journal,
            projection,
            generation,
            attempt_id,
            driver,
        )
        observed.append({"cleanup_recovery": recovered})
    running: list[tuple[str, Mapping[str, Any], TaskContract, dict[str, Any]]] = []
    for attempt_id, attempt in list(projection["attempts"].items()):
        if attempt.get("status") != "running":
            continue
        task = _task_from_state(projection, attempt["task_id"])
        poll_attempt = _driver_attempt(attempt, attempt_id, task)
        running.append((attempt_id, attempt, task, poll_attempt))
        if isinstance(driver, OrcaDriver):
            receipt = driver.poll(
                poll_attempt,
                cursor=attempt.get("cursor"),
                include_delivery=False,
            )
        else:
            receipt = driver.poll(poll_attempt, cursor=attempt.get("cursor"))
        receipt_id, receipt_path = _driver_receipt(arguments.repo, directory, receipt)
        observed.append({"attempt_id": attempt_id, "receipt_id": receipt_id, "receipt_path": receipt_path})
        projection = journal.append(
            "attempt_observed",
            {"attempt_id": attempt_id, "cursor": receipt.external_refs.get("cursor"), "receipt_path": receipt_path},
            coordinator_generation=generation,
        )
        if isinstance(driver, OrcaDriver):
            continue
        for item in _provider_messages(receipt.raw):
            event_type = item.get("type") or item.get("kind")
            result = item.get("result")
            if event_type == "worker_reported" and isinstance(result, Mapping):
                projection, _ = _append_report(arguments.repo, directory, journal, projection, generation, attempt_id, result, receipt.to_dict())
            elif event_type == "worker_done":
                result = _provider_worker_result(item, task, attempt_id)
                projection, _ = _append_report(
                    arguments.repo,
                    directory,
                    journal,
                    projection,
                    generation,
                    attempt_id,
                    result,
                    receipt.to_dict(),
                )
            elif event_type in {"question", "question_opened"}:
                question_id = str(item.get("question_id") or item.get("id") or "")
                if question_id and question_id not in projection["questions"]:
                    projection = journal.append(
                        "question_opened",
                        {"question_id": question_id, "attempt_id": attempt_id, "body": item.get("body") or item.get("message"), "receipt_path": receipt_path},
                        coordinator_generation=generation,
                    )

    if isinstance(driver, OrcaDriver):
        delivery = driver.check_delivery(str(driver.run_id))
        delivery_receipt = DriverReceipt("check_delivery", "observed", raw=delivery)
        delivery_receipt_id, delivery_receipt_path = _driver_receipt(
            arguments.repo, directory, delivery_receipt
        )
        delivery_id = _provider_delivery_id(delivery)
        has_open_question = False
        for item in _provider_messages(delivery):
            attempt_id, attempt = _orca_attempt_for_message(projection, item)
            task = _task_from_state(projection, attempt["task_id"])
            poll_attempt = _driver_attempt(attempt, attempt_id, task)
            event_type = item.get("type") or item.get("kind")
            if event_type == "question":
                question_id = str(item.get("messageId") or item.get("message_id") or item.get("id") or "")
                if not question_id:
                    raise AgentGraphCliError("Orca question omitted its message ID", code="invalid_receipt")
                existing = projection["questions"].get(question_id)
                if not isinstance(existing, Mapping):
                    projection = journal.append(
                        "question_opened",
                        {
                            "question_id": question_id,
                            "attempt_id": attempt_id,
                            "body": item.get("body") or item.get("question"),
                            "receipt_path": delivery_receipt_path,
                            "delivery_id": delivery_id,
                        },
                        coordinator_generation=generation,
                    )
                    existing = projection["questions"][question_id]
                if existing.get("status") == "open":
                    has_open_question = True
            elif event_type == "escalation":
                raise AgentGraphCliError(
                    f"Orca worker escalated attempt {attempt_id}",
                    code="provider_escalation",
                )
            elif event_type == "worker_done":
                if attempt.get("status") == "reported":
                    continue
                if attempt.get("status") != "running":
                    raise AgentGraphCliError(
                        f"Orca completion targets attempt in {attempt.get('status')}",
                        code="provider_state_mismatch",
                    )
                result = _provider_worker_result(item, task, attempt_id, poll_attempt)
                projection, _ = _append_report(
                    arguments.repo,
                    directory,
                    journal,
                    projection,
                    generation,
                    attempt_id,
                    result,
                    delivery_receipt.to_dict(),
                )
                released = driver.release(poll_attempt)
                release_id, release_path = _driver_receipt(arguments.repo, directory, released)
                cleanup_id = attempt.get("cleanup_id")
                cleanup = projection["cleanup"].get(cleanup_id) if cleanup_id else None
                if isinstance(cleanup, Mapping) and cleanup.get("status") == "pending":
                    projection = journal.append(
                        "cleanup_finished",
                        {
                            "cleanup_id": cleanup_id,
                            "receipt": {
                                "receipt_id": release_id,
                                "receipt_path": release_path,
                                "driver": released.to_dict(),
                            },
                        },
                        coordinator_generation=generation,
                    )
        delivery_observation = {
            "delivery_id": delivery_id,
            "receipt_id": delivery_receipt_id,
            "receipt_path": delivery_receipt_path,
        }
        if delivery_id and not has_open_question:
            ack = driver.ack_delivery(str(driver.run_id), delivery_id)
            ack_id, ack_path = _write_receipt(arguments.repo, directory, ack)
            delivery_observation.update({"ack_receipt_id": ack_id, "ack_receipt_path": ack_path})
        observed.append(delivery_observation)
    return {"observed": observed, "state": projection}


def command_recover_cleanup(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    projection = journal.verify_projection()
    generation = _generation(arguments, projection)
    driver = _driver_for_state(arguments.repo, directory, projection)
    projection, recovery = _finish_driver_cleanup(
        arguments.repo,
        directory,
        journal,
        projection,
        generation,
        arguments.attempt,
        driver,
    )
    return {**recovery, "state": projection}


def command_reply(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    projection = journal.verify_projection()
    generation = _generation(arguments, projection)
    question = projection["questions"].get(arguments.question)
    if not isinstance(question, Mapping):
        raise AgentGraphCliError(f"unknown question: {arguments.question}", code="unknown_question")
    if question.get("status") == "answered":
        if question.get("answer") != arguments.body:
            raise AgentGraphCliError("question was already answered differently", code="duplicate_reply")
        return {"question_id": arguments.question, "answered": True, "idempotent": True, "state": projection}
    attempt_id = question["attempt_id"]
    attempt = projection["attempts"][attempt_id]
    task = _task_from_state(projection, attempt["task_id"])
    driver_attempt = _driver_attempt(attempt, attempt_id, task)
    driver = _driver_for_state(arguments.repo, directory, projection)
    receipt = driver.send(
        driver_attempt,
        {
            "kind": "reply",
            "message_id": arguments.question,
            "body": arguments.body,
            "delivery_id": question.get("delivery_id"),
        },
    )
    receipt_id, receipt_path = _driver_receipt(arguments.repo, directory, receipt)
    projection = journal.append(
        "question_answered",
        {"question_id": arguments.question, "answer": arguments.body, "receipt_id": receipt_id, "receipt_path": receipt_path},
        coordinator_generation=generation,
    )
    delivery_id = question.get("delivery_id")
    if delivery_id and isinstance(driver, OrcaDriver):
        still_open = any(
            value.get("delivery_id") == delivery_id and value.get("status") == "open"
            for value in projection["questions"].values()
        )
        if not still_open:
            ack = driver.ack_delivery(str(driver_attempt.get("run_id") or driver.run_id), str(delivery_id))
            _write_receipt(arguments.repo, directory, ack)
    return {"question_id": arguments.question, "answered": True, "idempotent": False, "state": projection}


def command_run_check(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    projection = journal.verify_projection()
    generation = _generation(arguments, projection)
    task = _task_from_state(projection, arguments.task)
    command = task.check
    if command.casefold() == "missing validation evidence":
        raise AgentGraphCliError(
            f"task {task.id} has Check: missing validation evidence; grade it unobserved",
            code="missing_check",
        )
    executable = direct_command_arguments(command)
    started = time.monotonic()
    try:
        completed = subprocess.run(
            executable,
            cwd=arguments.repo,
            shell=False,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        exit_code = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
        start_error = None
    except OSError as error:
        exit_code = 127
        stdout = ""
        stderr = str(error)
        start_error = str(error)
    duration_ms = round((time.monotonic() - started) * 1000)
    prior = projection["tasks"][task.id].get("check") or {}
    attempt_number = int(prior.get("attempts", 0)) + 1
    artifact = directory / "artifacts" / "checks" / f"{task.id}-{attempt_number:03d}.json"
    atomic_write_json(
        artifact,
        {
            "command": command,
            "arguments": executable,
            "exit_code": exit_code,
            "duration_ms": duration_ms,
            "stdout": stdout,
            "stderr": stderr,
            "start_error": start_error,
        },
    )
    data = {
        "task_id": task.id,
        "command": command,
        "status": "passed" if exit_code == 0 else "failed",
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "attempts": attempt_number,
        "total_duration_ms": int(prior.get("total_duration_ms", 0)) + duration_ms,
        "artifact": artifact.relative_to(arguments.repo).as_posix(),
    }
    projection = journal.append("check_recorded", data, coordinator_generation=generation)
    if exit_code != 0:
        raise AgentGraphCliError(
            f"task {task.id} check failed with exit code {exit_code}; output: {data['artifact']}",
            code="check_failed",
        )
    return {"task_id": task.id, "check": data, "state": projection}


def command_grade(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    projection = journal.verify_projection()
    generation = _generation(arguments, projection)
    task = _task_from_state(projection, arguments.task)
    state = projection["tasks"][task.id]
    if state["grade"] is not None:
        if state["grade"] == arguments.grade:
            return {"task_id": task.id, "grade": arguments.grade, "idempotent": True, "state": projection}
        raise AgentGraphCliError(f"task {task.id} is already graded {state['grade']}", code="task_already_graded")
    check = state.get("check") or {}
    if arguments.grade == "pass" and check.get("status") != "passed":
        raise AgentGraphCliError("grade pass requires a recorded passing check", code="evidence_required")
    if arguments.grade == "fail" and check.get("status") != "failed":
        raise AgentGraphCliError("grade fail requires a recorded failing check", code="evidence_required")
    if arguments.grade in {"pass", "fail"}:
        attempts = [projection["attempts"][attempt_id] for attempt_id in state["attempt_ids"]]
        if not attempts or attempts[-1].get("status") != "reported":
            raise AgentGraphCliError("evidence grade requires a terminal worker report", code="worker_report_required")
    if arguments.grade == "pass" and task.visual:
        manifest_refs = [
            reference.removeprefix("file:")
            for reference in arguments.evidence_ref
            if reference.startswith("file:")
        ]
        if len(manifest_refs) != 1:
            raise AgentGraphCliError(
                "frontend grade pass requires exactly one file: visual manifest",
                code="visual_evidence_required",
            )
        manifest_path, _ = repository_relative_path(
            arguments.repo, manifest_refs[0], "visual manifest"
        )
        try:
            validate_manifest(
                arguments.repo,
                manifest_path,
                projection["change"],
                task.id,
                task.visual,
                [parse_visual_scope(value) for value in task.visual_scope],
            )
        except VisualEvidenceError as error:
            raise AgentGraphCliError(str(error), code="visual_evidence_invalid") from error
    projection = journal.append(
        "task_graded",
        {"task_id": task.id, "grade": arguments.grade, "note": arguments.note, "evidence_refs": arguments.evidence_ref},
        coordinator_generation=generation,
    )
    return {"task_id": task.id, "grade": arguments.grade, "idempotent": False, "state": projection}


def command_record_repair(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    projection = journal.verify_projection()
    generation = _generation(arguments, projection)
    _task_from_state(projection, arguments.task)
    try:
        projection = journal.append(
            "repair_recorded",
            {"task_id": arguments.task, "hypothesis": arguments.hypothesis},
            coordinator_generation=generation,
        )
    except JournalError as error:
        raise AgentGraphCliError(str(error), code="repair_cap_reached") from error
    return {
        "task_id": arguments.task,
        "hypotheses": projection["tasks"][arguments.task]["hypotheses"],
        "state": projection,
    }


def command_recover_attempt(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    projection = journal.verify_projection()
    generation = _generation(arguments, projection)
    attempt = projection["attempts"].get(arguments.attempt)
    if not isinstance(attempt, Mapping):
        raise AgentGraphCliError(f"unknown attempt: {arguments.attempt}", code="unknown_attempt")
    if attempt.get("status") == "running":
        return {"attempt_id": arguments.attempt, "recovered": True, "idempotent": True, "state": projection}
    if attempt.get("status") not in {"reserved", "interrupted"}:
        raise AgentGraphCliError(
            f"attempt cannot be recovered from {attempt.get('status')}",
            code="attempt_not_recoverable",
        )
    task = _task_from_state(projection, attempt["task_id"])
    driver = _driver_for_state(arguments.repo, directory, projection)
    request = {
        "task_id": task.id,
        "attempt_id": arguments.attempt,
        "recover": True,
        "task": task.to_dict(),
        "dependency_digest": attempt.get("dependency_digest", []),
        "worker_handle": attempt.get("worker"),
        "local": attempt.get("worker") == "local",
    }
    receipt = driver.start_attempt(request)
    receipt_id, receipt_path = _driver_receipt(arguments.repo, directory, receipt)
    refs = dict(receipt.external_refs)
    cleanup_id = attempt.get("cleanup_id") or (
        f"cleanup-{arguments.attempt}" if projection["driver"] == "orca" else None
    )
    projection = journal.append(
        "attempt_started",
        {
            "task_id": task.id,
            "attempt_id": arguments.attempt,
            "driver": projection["driver"],
            "worker": attempt.get("worker"),
            "tier": refs.get("tier"),
            "external_refs": refs,
            "receipt_id": receipt_id,
            "receipt_path": receipt_path,
            "task": task.to_dict(),
            "dependency_digest": attempt.get("dependency_digest", []),
            "cleanup_id": cleanup_id,
        },
        coordinator_generation=generation,
    )
    if cleanup_id and cleanup_id not in projection["cleanup"]:
        projection = journal.append(
            "cleanup_registered",
            {
                "cleanup_id": cleanup_id,
                "kind": "terminal",
                "target": str(refs.get("dispatch_id") or arguments.attempt),
                "owner": arguments.attempt,
            },
            coordinator_generation=generation,
        )
    return {
        "attempt_id": arguments.attempt,
        "recovered": True,
        "idempotent": False,
        "receipt": receipt.to_dict(),
        "state": projection,
    }


def command_abandon_attempt(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    projection = journal.verify_projection()
    generation = _generation(arguments, projection)
    attempt = projection["attempts"].get(arguments.attempt)
    if not isinstance(attempt, Mapping):
        raise AgentGraphCliError(f"unknown attempt: {arguments.attempt}", code="unknown_attempt")
    if attempt.get("status") == "abandoned":
        return {"attempt_id": arguments.attempt, "abandoned": True, "idempotent": True, "state": projection}
    if attempt.get("status") not in {"reserved", "running", "interrupted"}:
        raise AgentGraphCliError(
            f"attempt cannot be abandoned from {attempt.get('status')}",
            code="attempt_not_abandonable",
        )
    if not projection.get("driver"):
        raise AgentGraphCliError("driver selection must be recovered first", code="driver_not_selected")
    task = _task_from_state(projection, attempt["task_id"])
    driver_attempt = _driver_attempt(attempt, arguments.attempt, task)
    driver = _driver_for_state(arguments.repo, directory, projection)
    reconciled = driver.reconcile([driver_attempt])
    reconcile_id, reconcile_path = _driver_receipt(arguments.repo, directory, reconciled)
    cleanup_receipt: DriverReceipt
    if attempt.get("status") == "running":
        cleanup_receipt = driver.release(driver_attempt)
    elif isinstance(driver, HostDriver):
        cleanup_receipt = driver.release(driver_attempt)
    else:
        observations = reconciled.raw if isinstance(reconciled.raw, list) else []
        if len(observations) != 1 or observations[0].get("resource_state") != "absent":
            raise AgentGraphCliError(
                "reserved Orca attempt still has possible external resources; recover it before abandonment",
                code="cleanup_unproven",
            )
        cleanup_receipt = DriverReceipt(
            "release",
            "released",
            local_ids={"attempt_id": arguments.attempt},
            raw={"resource_state": "absent", "reconciliation_receipt": reconcile_path},
        )
    cleanup_receipt_id, cleanup_receipt_path = _driver_receipt(
        arguments.repo, directory, cleanup_receipt
    )
    cleanup_id = attempt.get("cleanup_id")
    cleanup = projection["cleanup"].get(cleanup_id) if cleanup_id else None
    if isinstance(cleanup, Mapping) and cleanup.get("status") == "pending":
        projection = journal.append(
            "cleanup_finished",
            {
                "cleanup_id": cleanup_id,
                "receipt": {
                    "receipt_id": cleanup_receipt_id,
                    "receipt_path": cleanup_receipt_path,
                    "driver": cleanup_receipt.to_dict(),
                },
            },
            coordinator_generation=generation,
        )
    projection = journal.append(
        "attempt_abandoned",
        {
            "attempt_id": arguments.attempt,
            "task_id": attempt["task_id"],
            "reason": arguments.reason,
            "reconciliation": {
                "receipt_id": reconcile_id,
                "receipt_path": reconcile_path,
            },
            "cleanup_receipt": {
                "receipt_id": cleanup_receipt_id,
                "receipt_path": cleanup_receipt_path,
            },
        },
        coordinator_generation=generation,
    )
    return {"attempt_id": arguments.attempt, "abandoned": True, "idempotent": False, "state": projection}


def command_cleanup_register(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    projection = journal.verify_projection()
    generation = _generation(arguments, projection)
    if arguments.kind not in CLEANUP_KINDS:
        raise AgentGraphCliError(f"unknown cleanup kind: {arguments.kind}", code="invalid_cleanup")
    cleanup_id = arguments.cleanup_id or f"cleanup-{len(projection['cleanup']) + 1:03d}"
    require_identifier(cleanup_id, "cleanup_id")
    existing = projection["cleanup"].get(cleanup_id)
    expected = {"cleanup_id": cleanup_id, "kind": arguments.kind, "target": arguments.target, "owner": arguments.owner}
    if existing:
        if any(existing.get(key) != value for key, value in expected.items()):
            raise AgentGraphCliError(f"cleanup ID already refers to another target: {cleanup_id}", code="duplicate_cleanup")
        return {"cleanup_id": cleanup_id, "registered": True, "idempotent": True, "state": projection}
    projection = journal.append("cleanup_registered", expected, coordinator_generation=generation)
    return {"cleanup_id": cleanup_id, "registered": True, "idempotent": False, "state": projection}


def command_cleanup_finish(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    projection = journal.verify_projection()
    generation = _generation(arguments, projection)
    cleanup_id = arguments.cleanup_id
    if cleanup_id is None and arguments.target is not None:
        matches = [key for key, value in projection["cleanup"].items() if value.get("target") == arguments.target]
        if len(matches) != 1:
            raise AgentGraphCliError("cleanup target is missing or ambiguous", code="unknown_cleanup")
        cleanup_id = matches[0]
    if cleanup_id not in projection["cleanup"]:
        raise AgentGraphCliError(f"unknown cleanup: {cleanup_id}", code="unknown_cleanup")
    cleanup = projection["cleanup"][cleanup_id]
    if cleanup["status"] == "done":
        return {"cleanup_id": cleanup_id, "finished": True, "idempotent": True, "state": projection}
    owner = projection["attempts"].get(cleanup.get("owner"))
    if isinstance(owner, Mapping) and owner.get("cleanup_id") == cleanup_id:
        raise AgentGraphCliError(
            f"cleanup {cleanup_id} is driver-owned; use recover-cleanup for attempt {cleanup['owner']}",
            code="driver_cleanup_requires_recovery",
        )
    if cleanup_target_exists(arguments.repo, cleanup["kind"], cleanup["target"]):
        raise AgentGraphCliError(f"cleanup target still exists: {cleanup['target']}", code="cleanup_pending")
    receipt: Any = arguments.receipt
    if cleanup["kind"] in {"terminal", "other"} and not receipt:
        raise AgentGraphCliError(f"cleanup kind {cleanup['kind']} requires --receipt", code="cleanup_receipt_required")
    if receipt:
        try:
            receipt = json.loads(receipt)
        except json.JSONDecodeError:
            pass
    projection = journal.append(
        "cleanup_finished",
        {"cleanup_id": cleanup_id, "receipt": receipt},
        coordinator_generation=generation,
    )
    return {"cleanup_id": cleanup_id, "finished": True, "idempotent": False, "state": projection}


def _status_result(projection: Mapping[str, Any]) -> dict[str, Any]:
    tasks = []
    for task_id, task in projection["tasks"].items():
        contract = task["contract"]
        latest_attempt = task["attempt_ids"][-1] if task["attempt_ids"] else None
        attempt = projection["attempts"].get(latest_attempt, {}) if latest_attempt else {}
        tasks.append(
            {
                "task_id": task_id,
                "title": contract["title"],
                "dependencies": contract["depends"],
                "status": task["status"],
                "attempt_id": latest_attempt,
                "driver_tier": attempt.get("tier"),
                "worker": attempt.get("worker"),
                "evidence_grade": task["grade"],
                "blockers": task_blockers(_task_from_state(projection, task_id), projection),
            }
        )
    return {
        "change": projection["change"],
        "run_id": projection["run_id"],
        "status": projection["status"],
        "outcome": projection["outcome"],
        "coordinator": projection["coordinator"],
        "driver": projection["driver"],
        "tasks": tasks,
        "cleanup": list(projection["cleanup"].values()),
        "degradations": projection["degradations"],
        "last_sequence": projection["last_sequence"],
    }


def command_status(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    state_path = directory / "state.json"
    iterations = arguments.iterations if arguments.watch else 1
    snapshots: list[dict[str, Any]] = []
    last_sequence = -1
    count = 0
    while iterations is None or count < iterations:
        projection = load_json_object(state_path, "saved projection")
        if projection.get("last_sequence") != last_sequence:
            snapshots.append(_status_result(projection))
            last_sequence = projection.get("last_sequence", -1)
        count += 1
        if iterations is None or count < iterations:
            time.sleep(arguments.interval)
    return snapshots[-1] if len(snapshots) == 1 else {"snapshots": snapshots}


def command_digest(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    projection = _projection(directory)
    return {
        "change": projection["change"],
        "run_id": projection["run_id"],
        "outcome": projection["outcome"],
        "tasks": [
            {
                "task_id": task_id,
                "grade": task["grade"],
                "check_artifact": (task.get("check") or {}).get("artifact"),
                "attempts": task["attempt_ids"],
            }
            for task_id, task in projection["tasks"].items()
        ],
        "pending_cleanup": [value for value in projection["cleanup"].values() if value["status"] == "pending"],
        "degradations": projection["degradations"],
    }


def command_complete(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    projection = journal.verify_projection()
    generation = _generation(arguments, projection)
    if projection["status"] == "complete":
        if projection["outcome"] != arguments.outcome:
            raise AgentGraphCliError("run already completed with another outcome", code="run_complete")
        return {"completed": True, "idempotent": True, "state": projection}
    running = [
        attempt_id
        for attempt_id, attempt in projection["attempts"].items()
        if attempt["status"] in {"reserved", "running", "interrupted"}
    ]
    if running:
        raise AgentGraphCliError(f"reconcile running attempts first: {', '.join(running)}", code="attempts_running")
    pending_cleanup = [key for key, value in projection["cleanup"].items() if value["status"] == "pending"]
    if pending_cleanup:
        raise AgentGraphCliError(f"finish cleanup first: {', '.join(pending_cleanup)}", code="cleanup_pending")
    if arguments.outcome == "pass":
        ungraded = [task_id for task_id, task in projection["tasks"].items() if task["grade"] != "pass"]
        if ungraded:
            raise AgentGraphCliError(f"pass outcome requires every task to pass: {', '.join(ungraded)}", code="ungraded_tasks")
        base_commit = projection.get("base_commit")
        if isinstance(base_commit, str) and base_commit:
            changed_frontend = _frontend_paths(_changed_paths_since(arguments.repo, base_commit))
            has_visual_contract = any(
                bool(task["contract"].get("visual"))
                for task in projection["tasks"].values()
            )
            if changed_frontend and not has_visual_contract:
                raise AgentGraphCliError(
                    "frontend changes require Visual entries and vision-reviewed evidence: "
                    + ", ".join(changed_frontend),
                    code="visual_contract_required",
                )
    projection = journal.append("run_completed", {"outcome": arguments.outcome}, coordinator_generation=generation)
    return {"completed": True, "idempotent": False, "state": projection}


def _probe_tasks() -> tuple[TaskContract, TaskContract]:
    root = TaskContract(
        id="ORCA-PROBE-01",
        title="Read the repository instructions and ask one bounded question",
        depends=(),
        paths=("AGENTS.md",),
        mode="read",
        isolation="auto",
        context="This is a read-only live transport probe. Do not modify repository files.",
        acceptance=(
            "Read only the first heading of AGENTS.md. Ask the coordinator whether to "
            "continue with option yes or no, wait for the answer, then report worker_done "
            "with outcome succeeded and no modified files. Do not edit any file."
        ),
        check=f'{shlex.quote(sys.executable)} -c "from pathlib import Path; assert Path(\'AGENTS.md\').is_file()"',
        visual=(),
        visual_scope=(),
        checked=False,
        source_line=0,
    )
    dependent = TaskContract(
        id="ORCA-PROBE-02",
        title="Read the dependent repository marker",
        depends=(root.id,),
        paths=("README.md",),
        mode="read",
        isolation="auto",
        context="This task must not start until the first task has a local pass grade.",
        acceptance=(
            "Confirm README.md exists, make no edits, and report worker_done with outcome "
            "succeeded and no modified files."
        ),
        check=f'{shlex.quote(sys.executable)} -c "from pathlib import Path; assert Path(\'README.md\').is_file()"',
        visual=(),
        visual_scope=(),
        checked=False,
        source_line=0,
    )
    return root, dependent


def _probe_result(receipt: Mapping[str, Any]) -> Mapping[str, Any]:
    result = receipt.get("result", receipt)
    return result if isinstance(result, Mapping) else {}


def _probe_messages(receipt: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return _provider_messages(receipt)


def _probe_delivery_id(receipt: Mapping[str, Any]) -> str | None:
    return _provider_delivery_id(receipt)


def _probe_terminal_identities(value: Any, driver: OrcaDriver) -> list[dict[str, Any]]:
    identities: dict[str, dict[str, Any]] = {}
    for item in _walk_mappings(value):
        if not any(key in item for key in ("handle", "terminalHandle", "agentTerminalHandle")):
            continue
        candidates = [item]
        agent_handle = item.get("agentTerminalHandle")
        if isinstance(agent_handle, str):
            candidates.append({**item, "handle": agent_handle})
        for candidate in candidates:
            try:
                identity = driver._terminal_identity({"result": {"terminal": candidate}})
            except DriverError:
                continue
            identities[str(identity["handle"])] = identity
    return list(identities.values())


def _probe_live_handles(receipt: Mapping[str, Any]) -> set[str]:
    handles: set[str] = set()
    for item in _walk_mappings(receipt):
        value = item.get("handle") or item.get("terminalHandle") or item.get("agentTerminalHandle")
        if isinstance(value, str) and value.startswith("term_"):
            handles.add(value)
    return handles


def _probe_source_fingerprint(repository: Path, artifact_relative: str) -> str:
    excluded = ("openspec/runs/", artifact_relative)
    digest = hashlib.sha256()
    diff = _git(
        repository,
        "diff",
        "--binary",
        "--no-ext-diff",
        "--",
        ".",
        ":(exclude)openspec/runs/**",
        f":(exclude){artifact_relative}",
    )
    if diff.returncode != 0:
        raise AgentGraphCliError("cannot fingerprint the repository diff", code="probe_integrity_failed")
    digest.update(diff.stdout.encode("utf-8", errors="surrogateescape"))
    untracked = _git(repository, "ls-files", "--others", "--exclude-standard", "-z")
    if untracked.returncode != 0:
        raise AgentGraphCliError("cannot fingerprint untracked source files", code="probe_integrity_failed")
    for relative in sorted(path for path in untracked.stdout.split("\0") if path):
        if relative.startswith(excluded[0]) or relative == excluded[1]:
            continue
        path = repository / relative
        if not path.is_file():
            continue
        digest.update(relative.encode("utf-8", errors="surrogateescape"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _probe_attempt(driver: OrcaDriver, receipt: DriverReceipt, attempt_id: str) -> dict[str, Any]:
    refs = dict(receipt.external_refs)
    terminal = refs.get("terminal")
    return {
        "attempt_id": attempt_id,
        "tier": refs.get("tier"),
        "dispatch_id": refs.get("dispatch_id"),
        "external_task_id": refs.get("task_id"),
        "terminal_handle": terminal.get("handle") if isinstance(terminal, Mapping) else None,
        "run_id": refs.get("run_id"),
    }


def _probe_write_session(path: Path, session: Mapping[str, Any]) -> None:
    atomic_write_json(path, dict(session))


def _probe_child_cleanup(
    driver: OrcaDriver,
    attempts: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    for attempt in reversed(attempts):
        try:
            released = driver.release(attempt)
            receipts.append(released.to_dict())
            continue
        except DriverError as release_error:
            receipts.append({"operation": "release", "status": "error", "code": release_error.code, "receipt": release_error.receipt})
        dispatch_id = str(attempt.get("dispatch_id") or "")
        if dispatch_id:
            stopped = driver._call("orchestration", "worker-stop", "--dispatch", dispatch_id, "--json", allow_error=True)
            receipts.append({"operation": "worker-stop", "raw": stopped})
            released = driver._call("orchestration", "worker-release", "--dispatch", dispatch_id, "--json", allow_error=True)
            receipts.append({"operation": "worker-release", "raw": released})
        terminal_handle = attempt.get("terminal_handle")
        if terminal_handle:
            closed = driver._call("terminal", "close", "--terminal", str(terminal_handle), "--tab", "--json", allow_error=True)
            receipts.append({"operation": "terminal-close", "raw": closed})
    return receipts


def command_probe_orca_child(arguments: argparse.Namespace) -> dict[str, Any]:
    session_path = Path(arguments.session).resolve()
    session = load_json_object(session_path, "Orca probe session")
    repository = Path(session["repository"]).resolve()
    if repository != arguments.repo:
        raise AgentGraphCliError("probe session belongs to another repository", code="probe_session_mismatch")
    coordinator_handle = os.environ.get("ORCA_TERMINAL_HANDLE")
    expected_handle = session["coordinator_identity"]["handle"]
    if coordinator_handle != expected_handle:
        raise AgentGraphCliError(
            "probe child is not running in the fresh coordinator terminal",
            code="probe_coordinator_mismatch",
        )

    journal = EventJournal(Path(session["journal_path"]), Path(session["projection_path"]))
    generation = int(session["coordinator_generation"])
    coordinator_id = f"orca-terminal:{coordinator_handle}"
    receipts: dict[str, Any] = {}
    active_attempts: list[dict[str, Any]] = []
    cleanup_receipts: list[dict[str, Any]] = []
    driver = OrcaDriver(repository)
    tasks = _probe_tasks()
    graph = TaskGraph(tasks)
    try:
        projection = journal.append(
            "coordinator_claimed",
            {"coordinator_id": coordinator_id, "capsule_path": session["capsule_path"]},
            coordinator_generation=generation,
        )
        detected = driver.detect()
        started = driver.start_run(
            "Agent Graph bounded read-only Orca live probe",
            [{"id": task.id, "depends": list(task.depends), "capsule": task.acceptance} for task in tasks],
        )
        receipts["detect"] = detected.to_dict()
        receipts["start_run"] = started.to_dict()
        receipts["run_current"] = driver._call("orchestration", "run-current", "--json")
        receipts["dependency_before"] = driver._call(
            "orchestration", "task-list", "--run", str(driver.run_id), "--ready", "--brief", "--json"
        )
        journal.append(
            "driver_selected",
            {
                "requested": "orca",
                "driver": "orca",
                "reason": "real Orca runtime satisfied orchestration.contract.v1",
                "external_refs": dict(started.external_refs),
                "receipts": [],
                "receipt_ids": [],
            },
            coordinator_generation=generation,
        )

        local_transitions: list[dict[str, Any]] = []
        question_receipts: list[dict[str, Any]] = []
        reports: list[dict[str, Any]] = []
        grades: list[dict[str, Any]] = []
        degradations: list[dict[str, Any]] = []
        worker_identities: list[dict[str, Any]] = []
        dispatch_receipts: list[dict[str, Any]] = []

        for index, task in enumerate(tasks, start=1):
            before_ready = [candidate.id for candidate in ready_tasks(graph, projection)]
            if task.id not in before_ready:
                raise AgentGraphCliError(f"probe task was not locally ready: {task.id}", code="probe_dependency_failed")
            local_transitions.append({"task_id": task.id, "ready_before_dispatch": before_ready})
            attempt_id = f"orca-probe-attempt-{index:02d}"
            started_attempt = driver.start_attempt(
                {"task_id": task.id, "attempt_id": attempt_id, "task": task.to_dict(), "dependency_digest": {}}
            )
            attempt = _probe_attempt(driver, started_attempt, attempt_id)
            active_attempts.append(attempt)
            identities = _probe_terminal_identities(started_attempt.to_dict(), driver)
            for identity in identities:
                if identity not in worker_identities:
                    worker_identities.append(identity)
            session["worker_identities"] = worker_identities
            session["dispatch_ids"] = [item["dispatch_id"] for item in active_attempts if item.get("dispatch_id")]
            _probe_write_session(session_path, session)

            projection = journal.append("task_ready", {"task_id": task.id}, coordinator_generation=generation)
            projection = journal.append(
                "attempt_started",
                {
                    "task_id": task.id,
                    "attempt_id": attempt_id,
                    "driver": "orca",
                    "worker": "codex",
                    "tier": attempt["tier"],
                    "external_refs": dict(started_attempt.external_refs),
                    "receipt_id": canonical_receipt_id(started_attempt.to_dict()),
                    "receipt_path": "inline:orca-live.json",
                    "task": task.to_dict(),
                    "dependency_digest": {},
                },
                coordinator_generation=generation,
            )
            cleanup_id = f"cleanup-{attempt_id}"
            projection = journal.append(
                "cleanup_registered",
                {"cleanup_id": cleanup_id, "kind": "terminal", "target": str(attempt["dispatch_id"]), "owner": attempt_id},
                coordinator_generation=generation,
            )
            if started_attempt.degradation:
                degradation = {"attempt_id": attempt_id, **dict(started_attempt.degradation)}
                degradations.append(degradation)
                projection = journal.append("driver_degraded", degradation, coordinator_generation=generation)

            cursor: str | None = None
            terminal_message: Mapping[str, Any] | None = None
            pending_delivery: str | None = None
            deadline = time.monotonic() + 420
            while time.monotonic() < deadline and terminal_message is None:
                polled = driver.poll(attempt, cursor=cursor)
                cursor_value = polled.external_refs.get("cursor")
                cursor = str(cursor_value) if cursor_value is not None else cursor
                delivery = polled.raw.get("delivery", {}) if isinstance(polled.raw, Mapping) else {}
                delivery_id = _probe_delivery_id(delivery) if isinstance(delivery, Mapping) else None
                messages = _probe_messages(delivery) if isinstance(delivery, Mapping) else []
                for message in messages:
                    kind = message.get("type") or message.get("kind")
                    message_id = str(
                        message.get("messageId")
                        or message.get("message_id")
                        or message.get("id")
                        or message.get("questionId")
                        or message.get("question_id")
                        or ""
                    )
                    if kind == "question":
                        if not message_id:
                            raise AgentGraphCliError("Orca question omitted its message ID", code="invalid_receipt")
                        projection = journal.append(
                            "question_opened",
                            {"question_id": message_id, "attempt_id": attempt_id, "body": message.get("body") or message.get("question"), "receipt_path": "inline:orca-live.json"},
                            coordinator_generation=generation,
                        )
                        replied = driver.send(attempt, {"kind": "reply", "message_id": message_id, "body": "yes"})
                        question_receipts.append({"question": dict(message), "reply": replied.to_dict(), "delivery_id": delivery_id})
                        projection = journal.append(
                            "question_answered",
                            {"question_id": message_id, "answer": "yes", "receipt_id": canonical_receipt_id(replied.to_dict()), "receipt_path": "inline:orca-live.json"},
                            coordinator_generation=generation,
                        )
                    elif kind == "escalation":
                        raise AgentGraphCliError("Orca worker escalated during the live probe", code="probe_worker_escalated")
                    elif kind == "worker_done":
                        payload = _json_mapping(message.get("payload"))
                        outcome = message.get("outcome") or payload.get("outcome")
                        if outcome not in {"succeeded", "success"}:
                            raise AgentGraphCliError(f"Orca worker reported outcome {outcome!r}", code="probe_worker_failed")
                        terminal_message = message
                        pending_delivery = delivery_id
                if delivery_id and terminal_message is None:
                    ack = driver._call("orchestration", "check", "--run", str(driver.run_id), "--ack", delivery_id, "--json")
                    question_receipts.append({"ack": ack, "delivery_id": delivery_id})
            if terminal_message is None:
                raise AgentGraphCliError(f"timed out waiting for {task.id}", code="probe_timeout")
            if index == 1 and not question_receipts:
                raise AgentGraphCliError("root worker completed without the required ask/reply", code="probe_question_missing")

            result = _provider_worker_result(terminal_message, task, attempt_id, attempt)
            result["external_refs"].update(
                {
                    "orca_run_id": driver.run_id,
                    "orca_task_id": attempt["external_task_id"],
                    "orca_dispatch_id": attempt["dispatch_id"],
                }
            )
            reports.append(result)
            projection = journal.append("worker_reported", result, coordinator_generation=generation)

            executable = direct_command_arguments(task.check)
            checked = subprocess.run(executable, cwd=repository, check=False, capture_output=True, text=True, encoding="utf-8")
            check_data = {
                "task_id": task.id,
                "command": task.check,
                "status": "passed" if checked.returncode == 0 else "failed",
                "exit_code": checked.returncode,
                "duration_ms": 0,
                "attempts": 1,
                "total_duration_ms": 0,
                "artifact": "inline:orca-live.json",
            }
            projection = journal.append("check_recorded", check_data, coordinator_generation=generation)
            if checked.returncode != 0:
                raise AgentGraphCliError(f"local probe check failed for {task.id}: {checked.stderr}", code="probe_check_failed")
            grade = {"task_id": task.id, "grade": "pass", "note": "The read-only worker report and local check passed.", "evidence_refs": ["file:openspec/changes/portable-agent-graph-orchestration/evidence/orca-live.json"]}
            grades.append(grade)
            projection = journal.append("task_graded", grade, coordinator_generation=generation)

            released = driver.release(attempt)
            cleanup_receipts.append(released.to_dict())
            active_attempts.remove(attempt)
            projection = journal.append(
                "cleanup_finished",
                {"cleanup_id": cleanup_id, "receipt": released.to_dict()},
                coordinator_generation=generation,
            )
            if pending_delivery:
                ack = driver._call("orchestration", "check", "--run", str(driver.run_id), "--ack", pending_delivery, "--json")
                question_receipts.append({"ack": ack, "delivery_id": pending_delivery})
            dispatch_receipts.append(driver._call("orchestration", "dispatch-show", "--task", str(attempt["external_task_id"]), "--json"))
            if index == 1:
                receipts["dependency_after_root"] = driver._call(
                    "orchestration", "task-list", "--run", str(driver.run_id), "--ready", "--brief", "--json"
                )
                local_transitions[-1]["ready_after_local_grade"] = [candidate.id for candidate in ready_tasks(graph, projection)]

        projection = journal.append("run_completed", {"outcome": "pass"}, coordinator_generation=generation)
        final_terminals = driver._call("terminal", "list", "--worktree", f"id:{driver.worktree_id}", "--json")
        worker_handles = {identity["handle"] for identity in worker_identities}
        live_handles = _probe_live_handles(final_terminals)
        if worker_handles & live_handles:
            raise AgentGraphCliError("an Orca worker terminal remains live after release", code="cleanup_failed")
        result = {
            "claimed_coordinator": {"id": coordinator_id, "generation": generation, "terminal_identity": session["coordinator_identity"]},
            "orca": {"command": list(driver.command), "runtime_id": driver.runtime_id, "worktree_id": driver.worktree_id, "run_id": driver.run_id, "task_ids": dict(driver.task_ids)},
            "receipts": receipts,
            "attempt_receipts": dispatch_receipts,
            "question_reply": question_receipts,
            "worker_reports": reports,
            "local_evidence_grades": grades,
            "local_dependency_transitions": local_transitions,
            "driver_tiers": [item.get("tier") for item in projection["attempts"].values()],
            "degradations": degradations,
            "worker_terminal_identities": worker_identities,
            "cleanup_receipts": cleanup_receipts,
            "terminal_list_after_workers": final_terminals,
            "projection": projection,
        }
        atomic_write_json(Path(session["result_path"]), result)
        session["status"] = "succeeded"
        _probe_write_session(session_path, session)
        return {"probe": "succeeded", "run_id": driver.run_id}
    except BaseException as error:
        cleanup_receipts.extend(_probe_child_cleanup(driver, active_attempts))
        session["status"] = "failed"
        session["error"] = {"type": type(error).__name__, "message": str(error)}
        session["cleanup_receipts"] = cleanup_receipts
        _probe_write_session(session_path, session)
        raise


def _probe_close_identity(driver: OrcaDriver, identity: Mapping[str, Any]) -> dict[str, Any]:
    shown = driver._call("terminal", "show", "--terminal", str(identity["handle"]), "--json", allow_error=True)
    if shown.get("ok") is False:
        return {"show": shown, "already_gone": True}
    actual = driver._terminal_identity(shown)
    keys = ("runtime_id", "handle", "pty_id", "incarnation_id", "worktree_id", "tab_id", "leaf_id")
    if any(actual.get(key) != identity.get(key) for key in keys):
        raise AgentGraphCliError("probe terminal identity changed before cleanup", code="cleanup_unproven")
    closed = driver._call("terminal", "close", "--terminal", str(identity["handle"]), "--tab", "--json")
    return {"show": shown, "close": closed, "already_gone": False}


def command_probe_orca(arguments: argparse.Namespace) -> dict[str, Any]:
    artifact_path, artifact_relative = repository_relative_path(arguments.repo, arguments.artifact, "Orca evidence artifact")
    source_before = _probe_source_fingerprint(arguments.repo, artifact_relative)
    driver = OrcaDriver(arguments.repo)
    detected = driver.detect()
    run_id = f"orca-probe-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{os.getpid()}"
    run_directory = _new_run_directory(arguments.repo, arguments.change, run_id)
    journal = _journal(run_directory)
    tasks = _probe_tasks()
    bootstrap_id = f"bootstrap-{os.getpid()}"
    journal.append(
        "run_started",
        {"change": arguments.change, "run_id": run_id, "coordinator_id": bootstrap_id, "coordinator_generation": 1, "base_commit": _current_commit(arguments.repo), "dirty_paths": _dirty_paths(arguments.repo), "tasks": [task.to_dict() for task in tasks]},
        coordinator_generation=1,
    )
    journal.append(
        "coordinator_transferred",
        {"coordinator_id": None, "coordinator_generation": 2, "from_coordinator_id": bootstrap_id, "handoff": "fresh-top-level-orca-terminal"},
        coordinator_generation=1,
    )
    journal_before_stale = (run_directory / "events.jsonl").read_bytes()
    stale_error: str | None = None
    try:
        journal.append("task_ready", {"task_id": tasks[0].id}, coordinator_generation=1)
    except StaleCoordinatorError as error:
        stale_error = str(error)
    if stale_error is None or (run_directory / "events.jsonl").read_bytes() != journal_before_stale:
        raise AgentGraphCliError("bootstrap generation was not fenced after handoff", code="probe_fencing_failed")

    coordinator_receipts: dict[str, Any] = {"detect": detected.to_dict()}
    coordinator_identity: dict[str, Any] | None = None
    session_path = run_directory / "artifacts" / "probe-session.json"
    result_path = run_directory / "artifacts" / "probe-result.json"
    capsule_path = run_directory / "capsules" / "coordinator-generation-2.json"
    final_terminal_list: Mapping[str, Any] | None = None
    try:
        created = driver._call(
            "terminal", "create", "--worktree", f"id:{driver.worktree_id}", "--title", f"agent-graph-probe-coordinator-{run_id}", "--command", "codex", "--json"
        )
        try:
            coordinator_identity = driver._terminal_identity(created)
        except DriverError:
            created_handles = _probe_live_handles(created)
            if len(created_handles) != 1:
                raise
            created_show = driver._call("terminal", "show", "--terminal", next(iter(created_handles)), "--json")
            coordinator_receipts["terminal_show_after_create"] = created_show
            coordinator_identity = driver._terminal_identity(created_show)
        if coordinator_identity["handle"] in driver._terminal_snapshot:
            raise AgentGraphCliError("Orca reused a pre-existing terminal for the coordinator", code="cleanup_unproven")
        waited = driver._call("terminal", "wait", "--terminal", str(coordinator_identity["handle"]), "--for", "tui-idle", "--timeout-ms", "60000", "--json")
        capsule = {
            "schema_version": SCHEMA_VERSION,
            "repository": str(arguments.repo),
            "change": arguments.change,
            "run_id": run_id,
            "driver": "orca",
            "base_commit": _current_commit(arguments.repo),
            "dirty_paths": _dirty_paths(arguments.repo),
            "coordinator_generation": 2,
            "resume_command": f"python3 skills/agent-graph/scripts/agent_graph.py probe-orca-child --session {session_path}",
        }
        atomic_write_json(capsule_path, capsule)
        session = {
            "repository": str(arguments.repo),
            "journal_path": str(run_directory / "events.jsonl"),
            "projection_path": str(run_directory / "state.json"),
            "result_path": str(result_path),
            "capsule_path": capsule_path.relative_to(arguments.repo).as_posix(),
            "coordinator_generation": 2,
            "coordinator_identity": coordinator_identity,
            "worker_identities": [],
            "dispatch_ids": [],
            "status": "pending",
        }
        _probe_write_session(session_path, session)
        child_command = (
            f"{shlex.quote(sys.executable)} {shlex.quote(str(Path(__file__).resolve()))} "
            f"probe-orca-child --repo {shlex.quote(str(arguments.repo))} --session {shlex.quote(str(session_path))}"
        )
        prompt = (
            "You are the fresh coordinator for a bounded read-only integration probe. "
            "Do not inspect or edit repository source. Run exactly this command, wait for it to finish, then stop: "
            f"{child_command}"
        )
        delivered = driver._call("terminal", "send", "--terminal", str(coordinator_identity["handle"]), "--text", prompt, "--enter", "--json")
        coordinator_receipts.update({"terminal_create": created, "terminal_wait": waited, "prompt_delivery": delivered})

        deadline = time.monotonic() + 720
        while time.monotonic() < deadline and not result_path.is_file():
            current_session = load_json_object(session_path, "Orca probe session")
            if current_session.get("status") == "failed":
                error = current_session.get("error", {})
                raise AgentGraphCliError(f"fresh Orca coordinator failed: {error}", code="live_probe_failed")
            time.sleep(2)
        if not result_path.is_file():
            raise AgentGraphCliError("fresh Orca coordinator did not finish within 720 seconds", code="probe_timeout")
        child_result = load_json_object(result_path, "Orca probe result")
        if child_result.get("projection", {}).get("outcome") != "pass":
            raise AgentGraphCliError("fresh Orca coordinator did not complete its local graph", code="live_probe_failed")
        source_after_workers = _probe_source_fingerprint(arguments.repo, artifact_relative)
        if source_after_workers != source_before:
            raise AgentGraphCliError("the read-only Orca probe changed repository source", code="probe_integrity_failed")
    finally:
        cleanup_failures: list[str] = []
        current_session = load_json_object(session_path, "Orca probe session") if session_path.is_file() else {}
        dispatch_ids = current_session.get("dispatch_ids", []) if isinstance(current_session, Mapping) else []
        for dispatch_id in dispatch_ids if isinstance(dispatch_ids, list) else []:
            stopped = driver._call("orchestration", "worker-stop", "--dispatch", str(dispatch_id), "--json", allow_error=True)
            coordinator_receipts.setdefault("recovery", []).append({"worker_stop": stopped})
            released = driver._call("orchestration", "worker-release", "--dispatch", str(dispatch_id), "--json", allow_error=True)
            coordinator_receipts.setdefault("recovery", []).append({"worker_release": released})
        identities = current_session.get("worker_identities", []) if isinstance(current_session, Mapping) else []
        for identity in identities if isinstance(identities, list) else []:
            if not isinstance(identity, Mapping):
                continue
            try:
                coordinator_receipts.setdefault("recovery", []).append({"worker_terminal": _probe_close_identity(driver, identity)})
            except (DriverError, AgentGraphCliError) as error:
                cleanup_failures.append(str(error))
        if coordinator_identity is not None:
            try:
                coordinator_receipts["coordinator_cleanup"] = _probe_close_identity(driver, coordinator_identity)
            except (DriverError, AgentGraphCliError) as error:
                cleanup_failures.append(str(error))
        final_terminal_list = driver._call("terminal", "list", "--worktree", f"id:{driver.worktree_id}", "--json")
        created_handles = {
            str(identity.get("handle"))
            for identity in ([coordinator_identity] if coordinator_identity else []) + ([item for item in identities if isinstance(item, Mapping)] if isinstance(identities, list) else [])
            if identity and identity.get("handle")
        }
        remaining = created_handles & _probe_live_handles(final_terminal_list)
        if remaining:
            cleanup_failures.append(f"created terminals remain live: {', '.join(sorted(remaining))}")
        shutil.rmtree(run_directory)
        if cleanup_failures:
            raise AgentGraphCliError("; ".join(cleanup_failures), code="cleanup_failed")

    source_after_cleanup = _probe_source_fingerprint(arguments.repo, artifact_relative)
    if source_after_cleanup != source_before:
        raise AgentGraphCliError("repository source changed during probe cleanup", code="probe_integrity_failed")
    artifact = {
        "schema_version": 1,
        "observed_at": _now(),
        "change": arguments.change,
        "probe": "real-orca-read-only",
        "mocked": False,
        "source_integrity": {"algorithm": "sha256 of tracked diff plus nonignored untracked files, excluding probe run and artifact", "before": source_before, "after": source_after_cleanup, "unchanged": True},
        "handoff": {
            "bootstrap_coordinator_id": bootstrap_id,
            "bootstrap_generation": 1,
            "fresh_generation": 2,
            "stale_mutation_rejected": True,
            "stale_error": stale_error,
            "fresh_coordinator": child_result["claimed_coordinator"],
            "coordinator_modeled_as_worker_dispatch": False,
            "coordinator_dispatch_id": None,
        },
        "runtime": child_result["orca"],
        "runtime_capabilities": child_result["receipts"]["detect"]["external_refs"]["capabilities"],
        "local_and_orca_ids": {
            "local_run_id": run_id,
            "orca_run_id": child_result["orca"]["run_id"],
            "orca_task_ids": child_result["orca"]["task_ids"],
            "worker_reports": child_result["worker_reports"],
        },
        "dependency_transition": {
            "local": child_result["local_dependency_transitions"],
            "orca_before": child_result["receipts"]["dependency_before"],
            "orca_after_root": child_result["receipts"]["dependency_after_root"],
        },
        "question_reply": child_result["question_reply"],
        "worker_reports": child_result["worker_reports"],
        "local_evidence_grades": child_result["local_evidence_grades"],
        "driver_tiers": child_result["driver_tiers"],
        "degradations": child_result["degradations"],
        "cleanup": {
            "worker_receipts": child_result["cleanup_receipts"],
            "coordinator_receipts": coordinator_receipts,
            "final_terminal_list": final_terminal_list,
            "created_terminal_handles": sorted({child_result["claimed_coordinator"]["terminal_identity"]["handle"], *[identity["handle"] for identity in child_result["worker_terminal_identities"]]}),
            "all_created_terminals_gone": True,
        },
        "raw_receipts": {
            "coordinator": coordinator_receipts,
            "driver": child_result["receipts"],
            "dispatches": child_result["attempt_receipts"],
        },
        "local_projection": child_result["projection"],
    }
    atomic_write_json(artifact_path, artifact)
    return {
        "artifact": artifact_relative,
        "fresh_coordinator": artifact["handoff"]["fresh_coordinator"]["id"],
        "orca_run_id": artifact["runtime"]["run_id"],
        "driver_tiers": artifact["driver_tiers"],
        "all_created_terminals_gone": True,
        "source_unchanged": True,
    }


def _add_common(parser: argparse.ArgumentParser, *, run: bool = True, mutate: bool = False) -> None:
    add_runtime_arguments(parser)
    parser.add_argument("--json", action="store_true", help="emit the stable JSON envelope")
    if run:
        parser.add_argument("--change", required=True)
        parser.add_argument("--run-id")
    if mutate:
        parser.add_argument("--generation", "--coordinator-generation", type=int, dest="generation")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a durable repository-owned agent task graph.")
    add_runtime_arguments(parser)
    parser.add_argument("--json", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate")
    _add_common(validate, run=False)
    validate.add_argument("--change", required=True)
    validate.set_defaults(handler=command_validate)

    initialize = commands.add_parser("init")
    _add_common(initialize, run=False)
    initialize.add_argument("--change", required=True)
    initialize.add_argument("--run-id", required=True)
    initialize.add_argument("--coordinator-id", required=True)
    initialize.add_argument("--driver", choices=sorted(DRIVERS), default="auto")
    initialize.set_defaults(handler=command_init)

    bootstrap = commands.add_parser("bootstrap")
    _add_common(bootstrap, run=False)
    bootstrap.add_argument("--change", required=True)
    bootstrap.add_argument("--run-id", required=True)
    bootstrap.add_argument("--bootstrap-id")
    bootstrap.add_argument("--driver", choices=sorted(DRIVERS), default="auto")
    bootstrap.set_defaults(handler=command_bootstrap)

    claim = commands.add_parser("claim-coordinator")
    _add_common(claim, run=False)
    claim.add_argument("--capsule", "--coordinator-capsule", dest="capsule", required=True)
    claim.add_argument("--coordinator-id", required=True)
    claim.set_defaults(handler=command_claim)

    takeover = commands.add_parser("takeover")
    _add_common(takeover, mutate=True)
    takeover.add_argument("--coordinator-id", required=True)
    takeover.set_defaults(handler=command_takeover)

    recover_driver = commands.add_parser("recover-driver-selection")
    _add_common(recover_driver, mutate=True)
    recover_driver.set_defaults(handler=command_recover_driver_selection)

    resume = commands.add_parser("resume")
    _add_common(resume, mutate=True)
    resume.set_defaults(handler=command_resume)

    ready = commands.add_parser("ready")
    _add_common(ready)
    ready.set_defaults(handler=command_ready)

    dispatch = commands.add_parser("dispatch")
    _add_common(dispatch, mutate=True)
    dispatch.add_argument("--task", required=True)
    dispatch.add_argument("--attempt-id")
    dispatch.add_argument("--worker")
    dispatch.add_argument("--local", action="store_true")
    dispatch.set_defaults(handler=command_dispatch)

    sync = commands.add_parser("sync")
    _add_common(sync, mutate=True)
    sync.set_defaults(handler=command_sync)

    record = commands.add_parser("record-result")
    _add_common(record, mutate=True)
    record.add_argument("--attempt", "--attempt-id", dest="attempt", required=True)
    record.add_argument("--result")
    record.add_argument("--result-json")
    record.set_defaults(handler=command_record_result)

    reply = commands.add_parser("reply")
    _add_common(reply, mutate=True)
    reply.add_argument("--question", "--question-id", dest="question", required=True)
    reply.add_argument("--body", required=True)
    reply.set_defaults(handler=command_reply)

    check = commands.add_parser("run-check")
    _add_common(check, mutate=True)
    check.add_argument("--task", required=True)
    check.set_defaults(handler=command_run_check)

    grade = commands.add_parser("grade")
    _add_common(grade, mutate=True)
    grade.add_argument("--task", required=True)
    grade.add_argument("--grade", choices=sorted(GRADES), required=True)
    grade.add_argument("--note", required=True)
    grade.add_argument("--evidence-ref", action="append", default=[])
    grade.set_defaults(handler=command_grade)

    repair = commands.add_parser("record-repair")
    _add_common(repair, mutate=True)
    repair.add_argument("--task", required=True)
    repair.add_argument("--hypothesis", required=True)
    repair.set_defaults(handler=command_record_repair)

    abandon = commands.add_parser("abandon-attempt")
    _add_common(abandon, mutate=True)
    abandon.add_argument("--attempt", "--attempt-id", dest="attempt", required=True)
    abandon.add_argument("--reason", required=True)
    abandon.set_defaults(handler=command_abandon_attempt)

    recover_attempt = commands.add_parser("recover-attempt")
    _add_common(recover_attempt, mutate=True)
    recover_attempt.add_argument("--attempt", "--attempt-id", dest="attempt", required=True)
    recover_attempt.set_defaults(handler=command_recover_attempt)

    recover_cleanup = commands.add_parser("recover-cleanup")
    _add_common(recover_cleanup, mutate=True)
    recover_cleanup.add_argument("--attempt", "--attempt-id", dest="attempt", required=True)
    recover_cleanup.set_defaults(handler=command_recover_cleanup)

    for name in ("cleanup-register", "add-cleanup"):
        cleanup = commands.add_parser(name)
        _add_common(cleanup, mutate=True)
        cleanup.add_argument("--cleanup-id")
        cleanup.add_argument("--kind", choices=sorted(CLEANUP_KINDS), required=True)
        cleanup.add_argument("--target", required=True)
        cleanup.add_argument("--owner", required=True)
        cleanup.set_defaults(handler=command_cleanup_register)

    for name in ("cleanup-finish", "finish-cleanup"):
        finish = commands.add_parser(name)
        _add_common(finish, mutate=True)
        finish.add_argument("--cleanup-id")
        finish.add_argument("--target")
        finish.add_argument("--receipt")
        finish.set_defaults(handler=command_cleanup_finish)

    status = commands.add_parser("status")
    _add_common(status)
    status.add_argument("--watch", action="store_true")
    status.add_argument("--interval", type=float, default=1.0)
    status.add_argument("--iterations", type=int)
    status.set_defaults(handler=command_status)

    digest = commands.add_parser("digest")
    _add_common(digest)
    digest.set_defaults(handler=command_digest)

    complete = commands.add_parser("complete")
    _add_common(complete, mutate=True)
    complete.add_argument("--outcome", choices=sorted(OUTCOMES), required=True)
    complete.set_defaults(handler=command_complete)

    probe = commands.add_parser("probe-orca")
    _add_common(probe, run=False)
    probe.add_argument("--change", required=True)
    probe.add_argument("--artifact", required=True)
    probe.set_defaults(handler=command_probe_orca)

    probe_child = commands.add_parser("probe-orca-child", help=argparse.SUPPRESS)
    _add_common(probe_child, run=False)
    probe_child.add_argument("--session", required=True)
    probe_child.set_defaults(handler=command_probe_orca_child)
    return parser


def _human_status(result: Mapping[str, Any]) -> str:
    lines = [
        f"Run {result['change']}/{result['run_id']}: {result['status']}",
        f"Coordinator: {result['coordinator']['id']} generation {result['coordinator']['generation']}; driver: {result['driver']}",
    ]
    for task in result["tasks"]:
        blockers = ", ".join(item["task_id"] for item in task["blockers"]) or "none"
        lines.append(
            f"{task['task_id']} {task['status']} | deps={','.join(task['dependencies']) or 'none'} | attempt={task['attempt_id'] or 'none'} | tier={task['driver_tier'] or 'none'} | worker={task['worker'] or 'none'} | grade={task['evidence_grade'] or 'none'} | blockers={blockers}"
        )
    pending = [item["cleanup_id"] for item in result["cleanup"] if item["status"] == "pending"]
    lines.append(f"Pending cleanup: {', '.join(pending) or 'none'}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        arguments.repo = runtime_from_arguments(arguments).project_directory
        result = arguments.handler(arguments)
        if arguments.command == "status" and not arguments.json:
            print(_human_status(result))
        else:
            print(json.dumps({"ok": True, "command": arguments.command, "result": result}, indent=2, sort_keys=True))
        return 0
    except (AgentGraphCliError, CliValidationError, DriverError, GraphError, RuntimeConfigError, OSError) as error:
        code = getattr(error, "code", None) or (
            "stale_coordinator" if isinstance(error, StaleCoordinatorError) else "invalid_graph"
        )
        payload = {"ok": False, "error": {"code": code, "message": str(error), "command": getattr(arguments, "command", None)}}
        print(json.dumps(payload, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
