#!/usr/bin/env python3
"""Cross-platform command line runtime for repository-owned agent graphs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence


SCRIPTS_DIRECTORY = Path(__file__).resolve().parent
if str(SCRIPTS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIRECTORY))

from drivers.base import DriverError, DriverReceipt, persisted_driver_context  # noqa: E402
from drivers.host import (  # noqa: E402
    HostDriver,
    dependency_digest_from_projection,
)
from drivers.orca import OrcaDriver  # noqa: E402
from browser_surfaces import (  # noqa: E402
    BrowserSurfaceError,
    public_receipt,
    validate_browser_surface_request,
)
from graph_core import (  # noqa: E402
    GRADES,
    SCHEMA_VERSION,
    EventJournal,
    GraphError,
    JournalError,
    StaleCoordinatorError,
    StaleRevisionError,
    TaskContract,
    TaskGraph,
    atomic_write_json,
    cleanup_is_terminal,
    parse_task_graph,
    path_is_within_scopes,
    pending_cleanup_ids_for_attempt,
    pending_cleanup_ids_for_task,
    ready_tasks,
    replay_events,
    task_is_dispatchable,
    task_blockers,
    unresolved_cleanup_ids,
    validate_coordinator_capsule,
    validate_delegation_intent,
    validate_maestro_mutation,
    validate_delegation_result,
    validate_agent_graph_view,
    validate_execution_profile,
    validate_cleanup_owner,
    validate_cleanup_target,
    validate_workspace_bootstrap_receipt,
    validate_workspace_scope,
    validate_worker_result,
    validate_finding,
    BLOCKING_FINDING_CLASSIFICATIONS,
    effective_attempt_scope,
)
from runtime_config import (  # noqa: E402
    RuntimeConfigError,
    add_runtime_arguments,
    format_command,
    runtime_from_arguments,
)
from runtime_pin import (  # noqa: E402
    CONTROL_RUNTIME_REF_FILE,
    ControlRuntimeError,
    ROUTING_POLICY_SEED_SOURCE_PATH,
    ROUTING_POLICY_SEED_SNAPSHOT_PATH,
    create_control_runtime,
    load_run_control_runtime,
    release_control_runtime,
    verify_control_runtime,
)
from routing import ROLES, RoutingError, RuntimeCatalog, RoutingPolicy, load_routing_policy, plan_route  # noqa: E402
from adaptive_intake import (  # noqa: E402
    decide_process,
    evaluate_stop_conditions,
    load_signals,
    validate_graph_transition,
)
from context_capsules import build_reused_session_handoff  # noqa: E402
from validation import (  # noqa: E402
    CLEANUP_KINDS,
    CliValidationError,
    canonical_receipt_id,
    cleanup_target_exists,
    direct_command_arguments,
    load_json_object,
    repository_relative_path,
    require_identifier,
    run_bounded_command,
    run_shared_check,
    recover_shared_check,
    finalize_shared_check_recovery,
    load_shared_check_record,
    CheckExecutionError,
)
from visual_evidence import (  # noqa: E402
    VisualEvidenceError,
    parse_visual_scope,
    validate_manifest,
)
from maestro_bridge import (  # noqa: E402
    CoordinatorInbox,
    MaestroBridgeError,
    build_delta,
    build_reset,
    build_snapshot,
    negotiate_capabilities,
)
from run_progress import build_run_progress_summary  # noqa: E402


RUNS_DIRECTORY = Path("openspec/runs")
WORKSPACE_BOOTSTRAP_RECEIPT_FILE = Path("artifacts/workspace-bootstrap-receipt-v1.json")
ROUTING_POLICY_SNAPSHOT_FILE = Path("artifacts/routing-policy-v1.json")
WATCH_RETENTION = 64
WATCH_MAX_DELTAS = 16
CHECK_TIMEOUT_SECONDS = 300.0
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

    def __init__(self, message: str, *, code: str = "invalid_operation", details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = dict(details or {})


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
            paths.add(path if path.endswith("/") else Path(path).as_posix())
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


def _is_bootstrap_dirty_path(path: str, bootstrap_dirty_paths: Sequence[str]) -> bool:
    """Keep pre-existing dirty files out of completion provenance checks."""

    return any(
        path == dirty_path
        or (dirty_path.endswith("/") and path.startswith(dirty_path))
        for dirty_path in bootstrap_dirty_paths
    )


def _completion_provenance(
    repository: Path,
    directory: Path,
    projection: Mapping[str, Any],
    changed_paths: Sequence[str],
) -> tuple[list[str], list[str]]:
    """Return post-bootstrap owned paths and paths lacking task-report provenance."""

    bootstrap_dirty_paths = projection.get("dirty_paths", [])
    if not isinstance(bootstrap_dirty_paths, list) or not all(
        isinstance(path, str) for path in bootstrap_dirty_paths
    ):
        raise AgentGraphCliError(
            "run is missing its bootstrap dirty-path snapshot",
            code="bootstrap_provenance_missing",
        )
    run_path = directory.relative_to(repository).as_posix().rstrip("/") + "/"
    task_states = projection.get("tasks", {})
    attempts = projection.get("attempts", {})
    if not isinstance(task_states, Mapping) or not isinstance(attempts, Mapping):
        raise AgentGraphCliError("run is missing task provenance", code="provenance_missing")

    owned: list[str] = []
    unowned: list[str] = []
    for path in changed_paths:
        if path.startswith(run_path) or _is_bootstrap_dirty_path(path, bootstrap_dirty_paths):
            continue
        matching_report = False
        for attempt in attempts.values():
            if not isinstance(attempt, Mapping) or attempt.get("status") != "reported":
                continue
            task_id = attempt.get("task_id")
            task = task_states.get(task_id) if isinstance(task_id, str) else None
            report = attempt.get("report")
            if not isinstance(task, Mapping) or not isinstance(report, Mapping):
                continue
            contract = task.get("contract")
            report_paths = report.get("files_changed")
            if (
                not isinstance(contract, Mapping)
                or not isinstance(contract.get("paths"), list)
                or not isinstance(report_paths, list)
                or path not in report_paths
            ):
                continue
            if path_is_within_scopes(path, contract["paths"]):
                matching_report = True
                break
        if matching_report:
            owned.append(path)
        else:
            unowned.append(path)
    return sorted(owned), sorted(unowned)


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


def _run_progress_summary(
    projection: Mapping[str, Any], *, last_event: Mapping[str, Any] | None = None, events: list[Mapping[str, Any]] | None = None
) -> dict[str, Any]:
    return build_run_progress_summary(projection, last_event=last_event, events=events)


def _run_progress_from_journal(journal: EventJournal) -> dict[str, Any]:
    events, projection = journal.replay_snapshot()
    last_event = events[-1] if events else None
    return _run_progress_summary(projection, last_event=last_event, events=events)


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


def _routing_for_task(
    task: TaskContract,
    workspace_scope: Mapping[str, Any],
    *,
    driver_name: str = "host",
    route_input: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Resolve a persisted worker route from the selected driver's catalog."""

    workspace = workspace_scope["execution_workspace"]
    if driver_name not in {"host", "orca"}:
        raise AgentGraphCliError(f"unsupported execution driver: {driver_name}", code="invalid_driver")
    role = "implementation" if task.mode == "write" else "documentation"
    if driver_name == "host":
        if route_input is not None:
            if not isinstance(route_input, Mapping) or not isinstance(route_input.get("routing_policy"), Mapping):
                raise AgentGraphCliError("Host dispatch requires a pinned routing policy", code="routing_catalog_missing")
            try:
                RoutingPolicy.from_mapping(route_input["routing_policy"])
            except RoutingError as error:
                raise AgentGraphCliError(f"Host routing policy is invalid: {error}", code="routing_invalid") from error
        requested = {"lane": "balanced", "agent": None, "model": None, "effort": "medium"}
        resolved = {"agent": "host-native", "model": "host-native", "effort": "medium"}
        decision = {
            "outcome": "resolved",
            "role": role,
            "requested": requested,
            "resolved": resolved,
            "fallback_reason": None,
            "blocked_reason": None,
            "escalation_reason": None,
            "source_ref": "host-native",
        }
    else:
        if not isinstance(route_input, Mapping):
            raise AgentGraphCliError(
                "Orca dispatch requires a coordinator-supplied route input",
                code="routing_catalog_missing",
            )
        catalog = route_input.get("capability_catalog")
        policy = route_input.get("routing_policy")
        request = route_input.get("routing_request")
        if not isinstance(catalog, Mapping) or not isinstance(request, Mapping) or not isinstance(policy, Mapping):
            raise AgentGraphCliError("route input is missing policy, catalog, or routing request", code="routing_catalog_missing")
        allowed_request = {"role", "risk", "required_tools", "context_tokens", "check_strength", "escalation_reason", "overrides"}
        if set(request) - allowed_request:
            raise AgentGraphCliError("route input has unsupported routing request fields", code="routing_invalid")
        role = request.get("role")
        if not isinstance(role, str) or role not in ROLES or role == "coordinator":
            raise AgentGraphCliError("route input must classify one non-coordinator worker role", code="routing_invalid")
        try:
            catalog_value = RuntimeCatalog.from_mapping(catalog)
            request_values = dict(request)
            request_values.pop("role", None)
            decision = plan_route(
                catalog_value,
                policy=RoutingPolicy.from_mapping(policy),
                role=role,
                **request_values,
            )
            if decision.outcome != "resolved":
                raise RoutingError(str(decision.blocked_reason))
            resolved_profile = decision.execution_profile()
            resolved = resolved_profile["resolved"]
            capability = next(
                (
                    candidate for candidate in catalog_value.profiles
                    if candidate.agent == resolved["agent"] and candidate.model == resolved["model"]
                ),
                None,
            )
            if (
                resolved["effort"] in {"xhigh", "max"}
                or capability is None
                or capability.lane == "strong"
            ) and not decision.escalation_reason:
                raise RoutingError("worker strong or exceptional-effort routing requires an exceptional escalation reason")
        except RoutingError as error:
            raise AgentGraphCliError(
                f"cannot resolve the persisted Orca execution profile: {error}",
                code="routing_unavailable",
            ) from error
        requested = dict(resolved_profile["requested"])
        resolved = dict(resolved_profile["resolved"])
        decision = decision.to_dict()
    profile = {
        "role": role,
        "requested": requested,
        "resolved": resolved,
        "fallback_reason": decision["fallback_reason"],
        "placement_request": {"kind": "current-workspace"},
        "resolved_placement": {
            "execution_host_id": workspace["execution_host_id"],
            "workspace_key": workspace["workspace_key"],
            "kind": workspace["kind"],
            "path": workspace["path"],
            "receipt_ref": workspace_scope["binding_receipt_ref"],
        },
    }
    return validate_execution_profile(profile, workspace_scope), decision


def _execution_profile_for_task(
    task: TaskContract,
    workspace_scope: Mapping[str, Any],
    *,
    driver_name: str = "host",
    route_input: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the profile portion of the durable routing decision."""

    return _routing_for_task(
        task, workspace_scope, driver_name=driver_name, route_input=route_input
    )[0]


def _route_input(
    repository: Path, relative_path: str, projection: Mapping[str, Any]
) -> tuple[dict[str, Any], str, str]:
    path, normalized = repository_relative_path(repository, relative_path, "route input")
    value = load_json_object(path, "route input")
    if set(value) not in ({"authority", "capability_catalog", "routing_request"}, {"authority", "routing_policy", "capability_catalog", "routing_request"}):
        raise AgentGraphCliError("route input must contain authority, policy, catalog, and routing request only", code="routing_invalid")
    if "routing_policy" not in value:
        value["routing_policy"] = _default_routing_policy_input(repository)["routing_policy"]
    try:
        RoutingPolicy.from_mapping(value["routing_policy"])
    except RoutingError as error:
        raise AgentGraphCliError(f"route input policy is invalid: {error}", code="routing_invalid") from error
    authority = value["authority"]
    if not isinstance(authority, Mapping) or set(authority) != {"coordinator_id", "coordinator_generation", "source"}:
        raise AgentGraphCliError("route input authority is invalid", code="routing_invalid")
    coordinator = projection.get("coordinator", {})
    if (
        authority.get("coordinator_id") != coordinator.get("id")
        or authority.get("coordinator_generation") != coordinator.get("generation")
        or not isinstance(authority.get("source"), str)
        or not authority["source"]
    ):
        raise AgentGraphCliError("route input authority does not match the active coordinator", code="routing_invalid")
    serialized = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return value, normalized, f"sha256:{hashlib.sha256(serialized).hexdigest()}"


def _pin_routing_policy(
    repository: Path, directory: Path, policy: Mapping[str, Any]
) -> tuple[dict[str, Any], str, str]:
    """Freeze the first validated policy before the run reserves an attempt."""

    snapshot = directory / ROUTING_POLICY_SNAPSHOT_FILE
    if snapshot.exists():
        value = load_json_object(snapshot, "pinned routing policy")
    else:
        try:
            value = json.loads(json.dumps(dict(policy), sort_keys=True))
            RoutingPolicy.from_mapping(value)
            atomic_write_json(snapshot, value)
        except (RoutingError, OSError, TypeError, ValueError) as error:
            raise AgentGraphCliError(f"cannot pin routing policy: {error}", code="routing_invalid") from error
    try:
        RoutingPolicy.from_mapping(value)
    except RoutingError as error:
        raise AgentGraphCliError(f"pinned routing policy is invalid: {error}", code="routing_invalid") from error
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return value, repository_relative_path(repository, snapshot.relative_to(repository).as_posix(), "pinned routing policy")[1], f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _default_routing_policy_input(repository: Path) -> dict[str, Any]:
    """Return the external policy source used by provider-independent Host dispatch."""

    pinned_source = SCRIPTS_DIRECTORY.parent / ROUTING_POLICY_SEED_SNAPSHOT_PATH
    source = next(
        (
            candidate
            for candidate in (
                pinned_source,
                SCRIPTS_DIRECTORY.parents[1] / ROUTING_POLICY_SEED_SOURCE_PATH,
                repository / "skills" / "impl" / "references" / "routing-policy.seed.json",
            )
            if candidate.is_file()
        ),
        repository / "skills" / "impl" / "references" / "routing-policy.seed.json",
    )
    try:
        return {
            "routing_policy": json.loads(source.read_text(encoding="utf-8")),
            "routing_policy_source": "skills/impl/references/routing-policy.seed.json",
        }
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AgentGraphCliError(f"cannot load default routing policy: {error}", code="routing_invalid") from error


def _persist_routing_decision(
    repository: Path,
    directory: Path,
    *,
    route_input: Mapping[str, Any],
    route_input_path: str,
    route_input_sha256: str,
    decision: Mapping[str, Any],
    execution_profile: Mapping[str, Any],
    routing_summary: Mapping[str, Any],
    authority: Mapping[str, Any] | None = None,
    authority_transfer: Mapping[str, Any] | None = None,
    launch_argv: Sequence[str] | None = None,
) -> dict[str, Any]:
    persisted_authority = authority or route_input["authority"]
    receipt_id, receipt_path = _write_receipt(
        repository,
        directory,
        {
            "kind": "routing-decision",
            "route_input": dict(route_input),
            "route_input_path": route_input_path,
            "route_input_sha256": route_input_sha256,
            "decision": dict(decision),
            "execution_profile": dict(execution_profile),
            "routing_summary": dict(routing_summary),
            **({"authority_transfer": dict(authority_transfer)} if authority_transfer is not None else {}),
            **({"launch_argv": list(launch_argv)} if launch_argv is not None else {}),
        },
    )
    raw_hash = f"sha256:{hashlib.sha256((repository / receipt_path).read_bytes()).hexdigest()}"
    return {
        "receipt_id": receipt_id,
        "receipt_path": receipt_path,
        "sha256": raw_hash,
        "authority": json.loads(json.dumps(dict(persisted_authority), sort_keys=True)),
    }


def _routing_summary(
    decision: Mapping[str, Any], route_input: Mapping[str, Any] | None
) -> dict[str, Any]:
    """Keep cost-policy evidence visible without projecting the catalog body."""

    resolved = decision.get("resolved")
    request = route_input.get("routing_request") if isinstance(route_input, Mapping) else {}
    catalog = route_input.get("capability_catalog") if isinstance(route_input, Mapping) else {}
    policy = route_input.get("routing_policy") if isinstance(route_input, Mapping) else {}
    cost_rank = None
    if isinstance(resolved, Mapping) and isinstance(catalog, Mapping):
        try:
            selected = next(
                profile for profile in RuntimeCatalog.from_mapping(catalog).profiles
                if profile.agent == resolved.get("agent") and profile.model == resolved.get("model")
            )
            cost_rank = selected.cost_rank
        except (RoutingError, StopIteration):
            cost_rank = None
    return {
        "role": decision.get("role"),
        "risk": request.get("risk") if isinstance(request, Mapping) else None,
        "risk_rationale": {
            "risk": request.get("risk") if isinstance(request, Mapping) else None,
            "required_tools": list(request.get("required_tools", ())) if isinstance(request, Mapping) else [],
            "context_tokens": request.get("context_tokens") if isinstance(request, Mapping) else None,
        },
        "requested": dict(decision.get("requested", {})) if isinstance(decision.get("requested"), Mapping) else None,
        "effort_rationale": {
            "check_strength": request.get("check_strength") if isinstance(request, Mapping) else None,
            "requested_effort": (
                request.get("overrides", {}).get("effort")
                if isinstance(request, Mapping) and isinstance(request.get("overrides"), Mapping)
                else None
            ),
            "escalation_reason": decision.get("escalation_reason"),
        },
        "escalation_reason": decision.get("escalation_reason"),
        "resolved": dict(resolved) if isinstance(resolved, Mapping) else None,
        "fallback_reason": decision.get("fallback_reason"),
        "cost_rank": cost_rank,
        "policy_id": policy.get("policy_id") if isinstance(policy, Mapping) else None,
        "policy_digest": route_input.get("routing_policy_digest") if isinstance(route_input, Mapping) else None,
        "policy_source": (
            route_input.get("routing_policy_source")
            if isinstance(route_input, Mapping)
            else None
        ) or (policy.get("metadata", {}).get("source") if isinstance(policy, Mapping) and isinstance(policy.get("metadata"), Mapping) else None),
        "usage_observations": {
            "usage": "unavailable",
            "tokens": "unavailable",
            "cache": "unavailable",
            "quota": "unavailable",
            "cost": "unavailable",
        },
    }


def _verify_persisted_routing_decision(
    repository: Path,
    reference: Any,
    decision: Mapping[str, Any],
    execution_profile: Mapping[str, Any],
    routing_summary: Mapping[str, Any],
    launch_argv: Sequence[str] | None = None,
) -> dict[str, str]:
    if not isinstance(reference, Mapping) or set(reference) != {"receipt_id", "receipt_path", "sha256", "authority"}:
        raise AgentGraphCliError("attempt routing decision reference is invalid", code="attempt_identity_missing")
    receipt_id = reference["receipt_id"]
    receipt_path = reference["receipt_path"]
    expected_hash = reference["sha256"]
    if not isinstance(receipt_id, str) or not isinstance(receipt_path, str) or not isinstance(expected_hash, str):
        raise AgentGraphCliError("attempt routing decision reference is invalid", code="attempt_identity_missing")
    path, normalized = repository_relative_path(repository, receipt_path, "routing decision receipt")
    receipt = load_json_object(path, "routing decision receipt")
    actual_id = canonical_receipt_id(receipt)
    try:
        actual_hash = f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
    except OSError as error:
        raise AgentGraphCliError("persisted routing decision receipt is unreadable", code="attempt_identity_missing") from error
    embedded_input = receipt.get("route_input")
    authority = embedded_input.get("authority") if isinstance(embedded_input, Mapping) else None
    expected_authority = reference.get("authority")
    if (
        actual_id != receipt_id
        or actual_hash != expected_hash
        or normalized != receipt_path
        or receipt.get("kind") != "routing-decision"
        or receipt.get("decision") != dict(decision)
        or receipt.get("execution_profile") != dict(execution_profile)
        or receipt.get("routing_summary") != dict(routing_summary)
        or not isinstance(embedded_input, Mapping)
        or set(embedded_input) not in (
            {"authority", "routing_policy", "capability_catalog", "routing_request"},
            {"authority", "routing_policy", "routing_policy_path", "routing_policy_digest", "capability_catalog", "routing_request"},
        )
        or not isinstance(authority, Mapping)
        or (
            receipt.get("authority_transfer") is None
            and authority != expected_authority
        )
        or not isinstance(authority.get("source"), str)
        or not authority["source"]
        or (launch_argv is not None and receipt.get("launch_argv") != list(launch_argv))
    ):
        raise AgentGraphCliError("persisted routing decision receipt does not match the attempt", code="attempt_identity_missing")
    transfer = receipt.get("authority_transfer")
    if transfer is not None:
        if (
            not isinstance(transfer, Mapping)
            or set(transfer) != {"from", "to"}
            or transfer.get("from") != authority
            or transfer.get("to") != expected_authority
        ):
            raise AgentGraphCliError("persisted routing authority transfer is invalid", code="attempt_identity_missing")
    return {"receipt_id": receipt_id, "receipt_path": receipt_path, "sha256": expected_hash}


def _probe_launch_argv(decision: Mapping[str, Any], route_input: Mapping[str, Any]) -> list[str]:
    """Materialize a catalog-selected coordinator launch without a shell contract."""

    resolved = decision.get("resolved")
    if not isinstance(resolved, Mapping) or not all(
        isinstance(resolved.get(field), str) and resolved[field]
        for field in ("agent", "model", "effort")
    ):
        raise AgentGraphCliError("probe routing decision has no resolved agent", code="probe_profile_missing")
    def token(value: str) -> str:
        if any(character in value for character in ("\x00", "\n", "\r")):
            raise AgentGraphCliError("probe launch token is unsafe", code="probe_profile_missing")
        return value
    model = token(resolved["model"])
    effort = token(resolved["effort"])
    if resolved["agent"].casefold() == "codex":
        return ["codex", "--yolo", "--model", model, "-c", f"model_reasoning_effort={effort}"]
    catalog = route_input.get("capability_catalog")
    profiles = catalog.get("profiles") if isinstance(catalog, Mapping) else None
    selected = next(
        (
            item for item in profiles
            if isinstance(item, Mapping)
            and item.get("agent") == resolved.get("agent")
            and item.get("model") == resolved.get("model")
        ),
        None,
    ) if isinstance(profiles, list) else None
    launch_argv = selected.get("launch_argv") if isinstance(selected, Mapping) else None
    if (
        not isinstance(launch_argv, list)
        or not launch_argv
        or any(not isinstance(item, str) or not item for item in launch_argv)
    ):
        raise AgentGraphCliError("non-Codex probe capability requires catalog launch_argv", code="probe_profile_missing")
    if "{model}" not in launch_argv or "{effort}" not in launch_argv:
        raise AgentGraphCliError("non-Codex launch_argv must materialize model and effort", code="probe_profile_missing")
    return [token(model if item == "{model}" else effort if item == "{effort}" else item) for item in launch_argv]


def _probe_launch_command_text(argv: Sequence[str]) -> str:
    if not argv or any(not isinstance(item, str) or not item or any(char in item for char in ("\x00", "\n", "\r")) for item in argv):
        raise AgentGraphCliError("probe launch argv is invalid", code="probe_profile_missing")
    return shlex.join(list(argv))


def _preflight_probe_launch(argv: Sequence[str]) -> None:
    """Ask the locally installed CLI to parse the frozen argv without opening a session."""

    if argv and argv[0] == "codex":
        try:
            completed = subprocess.run(
                [*argv, "--help"], capture_output=True, text=True, timeout=10, check=False
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise AgentGraphCliError("Codex probe launch preflight is unavailable", code="probe_profile_missing") from error
        if completed.returncode != 0:
            raise AgentGraphCliError("Codex probe launch argv is unsupported by the local CLI", code="probe_profile_missing")


def _resource_owner_from_receipt(
    receipt_refs: Mapping[str, Any], attempt_id: str, workspace_scope: Mapping[str, Any]
) -> dict[str, Any] | None:
    terminal = receipt_refs.get("terminal")
    if not isinstance(terminal, Mapping):
        return None
    ownership = terminal.get("ownership")
    if not isinstance(ownership, Mapping):
        return None
    try:
        if any(
            ownership.get(field) != receipt_refs.get(field)
            for field in ("dispatch_id", "run_id")
        ) or ownership.get("attempt_id") != attempt_id:
            return None
        workspace = workspace_scope["execution_workspace"]
        owner = validate_cleanup_owner(
            {
                "execution_host_id": workspace["execution_host_id"],
                "workspace_key": workspace["workspace_key"],
                "attempt_id": attempt_id,
                "terminal_id": terminal["handle"],
                "incarnation_id": terminal["incarnation_id"],
                "process_root": terminal.get("process_root"),
                "provenance": f"orca:{receipt_refs['run_id']}:{receipt_refs['dispatch_id']}",
            }
        )
    except (GraphError, KeyError, TypeError):
        return None
    return owner


def _probe_execution_profile(
    task: TaskContract, workspace_scope: Mapping[str, Any], route_input: Mapping[str, Any]
) -> dict[str, Any]:
    return _routing_for_task(
        task, workspace_scope, driver_name="orca", route_input=route_input
    )[0]


def _orca_lifecycle_from_receipt(
    refs: Mapping[str, Any],
    attempt_id: str,
    workspace_scope: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    """Accept cleanup authority only from an exact tracked-terminal receipt."""

    tier = refs.get("tier")
    if tier == "supervised":
        if refs.get("terminal") is not None:
            raise AgentGraphCliError("supervised Orca receipt claims terminal authority", code="cleanup_unproven")
        try:
            runtime_id = refs["runtime_id"]
            worktree_id = refs["worktree_id"]
            run_id = refs["run_id"]
            dispatch_id = refs["dispatch_id"]
            if not all(isinstance(value, str) and value for value in (runtime_id, worktree_id, run_id, dispatch_id)):
                raise KeyError("provider identity")
            workspace = workspace_scope["execution_workspace"]
            owner = validate_cleanup_owner(
                {
                    "execution_host_id": workspace["execution_host_id"],
                    "workspace_key": workspace["workspace_key"],
                    "attempt_id": attempt_id,
                    "terminal_id": None,
                    "incarnation_id": None,
                    "process_root": None,
                    "provenance": f"orca-supervised:{runtime_id}:{worktree_id}:{run_id}:{dispatch_id}",
                }
            )
        except (GraphError, KeyError, TypeError):
            raise AgentGraphCliError(
                "supervised Orca receipt omitted exact provider cleanup identity",
                code="cleanup_unproven",
            ) from None
        return owner, f"cleanup-{attempt_id}"
    if tier != "tracked-terminal":
        raise AgentGraphCliError("Orca start receipt has an unknown lifecycle tier", code="invalid_receipt")
    owner = _resource_owner_from_receipt(refs, attempt_id, workspace_scope)
    if owner is None:
        raise AgentGraphCliError(
            "tracked-terminal Orca receipt omitted authoritative terminal ownership",
            code="cleanup_unproven",
        )
    return owner, f"cleanup-{attempt_id}"


def _supervised_release_state(receipt: DriverReceipt) -> str | None:
    """Read only the public worker-release terminal state from its raw receipt."""

    raw = receipt.raw
    if not isinstance(raw, Mapping):
        return None
    if raw.get("ok") is False:
        error = raw.get("error")
        if isinstance(error, Mapping) and error.get("code") == "already_released":
            return "already_released"
        return None
    result = raw.get("result", raw)
    if not isinstance(result, Mapping):
        return None
    state = next((result.get(key) for key in ("state", "status", "outcome") if key in result), None)
    return state if state in {"released", "already_released"} else None


def _rollback_post_start_failure(
    repository: Path,
    directory: Path,
    journal: EventJournal,
    generation: int,
    driver: HostDriver | OrcaDriver,
    task: TaskContract,
    attempt_id: str,
    workspace_scope: Mapping[str, Any],
    execution_profile: Mapping[str, Any],
    refs: Mapping[str, Any],
    start_receipt: DriverReceipt,
    reason: str,
) -> None:
    """Record one failed post-effect start and retain an exact recovery obligation."""

    owner: dict[str, Any] | None
    try:
        owner, cleanup_id = _orca_lifecycle_from_receipt(refs, attempt_id, workspace_scope)
    except AgentGraphCliError:
        owner, cleanup_id = None, None
    rollback: dict[str, Any]
    release_refs: Mapping[str, Any] = {}
    try:
        context = persisted_driver_context({
            "workspace_scope": workspace_scope,
            "execution_profile": execution_profile,
            "resolved_placement": execution_profile.get("resolved_placement"),
            "external_refs": refs,
        })
        release = driver.release({
            "attempt_id": attempt_id,
            "task_id": task.id,
            "tier": refs.get("tier"),
            "dispatch_id": refs.get("dispatch_id"),
            "external_task_id": refs.get("task_id"),
            "run_id": refs.get("run_id"),
            **context,
        })
        rollback = {"status": "returned", "receipt": release.to_dict()}
        release_refs = release.external_refs if isinstance(release.external_refs, Mapping) else {}
    except DriverError as error:
        rollback = {"status": "unverifiable", "error": str(error)}
    if owner is None and release_refs:
        owner = _resource_owner_from_receipt(release_refs, attempt_id, workspace_scope)
        cleanup_id = f"cleanup-{attempt_id}" if owner is not None else None
    released = False
    if owner is not None and rollback.get("status") == "returned":
        released_receipt = rollback["receipt"]
        released_refs = released_receipt.get("external_refs", {}) if isinstance(released_receipt, Mapping) else {}
        if owner["terminal_id"] is None:
            released = (
                isinstance(released_refs, Mapping)
                and released_refs.get("tier") == "supervised" == refs.get("tier")
                and released_refs.get("dispatch_id") == refs.get("dispatch_id")
                and all(
                    getattr(driver, attribute, None) == refs.get(field)
                    for attribute, field in (("runtime_id", "runtime_id"), ("run_id", "run_id"))
                )
                and isinstance(released_receipt, Mapping)
                and _supervised_release_state(DriverReceipt("release", "released", raw=released_receipt.get("raw"))) is not None
            )
        else:
            released = (
                isinstance(released_refs, Mapping)
                and released_refs.get("tier") == "tracked-terminal"
                and _resource_owner_from_receipt(released_refs, attempt_id, workspace_scope) == owner
            )
    evidence = {"start": start_receipt.to_dict(), "returned_refs": dict(refs), "rollback": rollback}
    failure = {"task_id": task.id, "attempt_id": attempt_id, "code": "post_start_validation_failed", "message": reason, "receipt": evidence, "post_start_unresolved": not released}
    current_cleanup = journal.verify_projection().get("cleanup", {})
    if owner is not None and not released:
        matching_cleanup = next(
            (
                known_id for known_id, record in current_cleanup.items()
                if isinstance(record, Mapping) and record.get("owner") == owner
            ),
            None,
        )
        if isinstance(matching_cleanup, str):
            cleanup_id = matching_cleanup
        else:
            owner_digest = hashlib.sha256(
                json.dumps(owner, separators=(",", ":"), sort_keys=True).encode("utf-8")
            ).hexdigest()[:16]
            cleanup_id = f"cleanup-{attempt_id}-{owner_digest}"
    existing_cleanup = current_cleanup.get(cleanup_id) if cleanup_id else None
    if owner is not None and not released and cleanup_id is not None and existing_cleanup is None:
        failure.update({
            "resource_owner": owner,
            "cleanup_id": cleanup_id,
            "cleanup_registration": {
                "cleanup_id": cleanup_id,
                "kind": "terminal" if owner["terminal_id"] is not None else "other",
                "target": owner["terminal_id"] or refs["dispatch_id"],
                "owner": owner,
                "external_refs": dict(refs),
            },
        })
    journal.append("attempt_start_failed", failure, coordinator_generation=generation)


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


def _workspace_receipt_hash(receipt: Mapping[str, Any]) -> str:
    serialized = json.dumps(receipt, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(serialized).hexdigest()


def _automatic_host_workspace_receipt(repository: Path, run_id: str) -> dict[str, Any]:
    repository_id = f"host-run-{uuid.uuid4()}"
    workspace_key = f"folder:{repository_id}"
    root = str(repository.resolve())
    workspace = {
        "execution_host_id": "local",
        "workspace_key": workspace_key,
        "kind": "folder",
        "path": root,
    }
    return validate_workspace_bootstrap_receipt(
        {
            "schema_version": SCHEMA_VERSION,
            "repository_id": repository_id,
            "canonical_root": root,
            "execution_host": {"id": "local", "boundary": "local"},
            "orchestration_home": workspace,
            "execution_workspace": workspace,
            "base_revision": _current_commit(repository),
            "dirty_paths": _dirty_paths(repository),
            "authority": {
                "kind": "host-run",
                "scope": "run",
                "issued_for_run_id": run_id,
            },
        },
        expected_run_id=run_id,
        expected_repository=repository,
    )


def _workspace_receipt_for_new_run(
    repository: Path,
    run_id: str,
    driver_name: str,
    supplied_path: str | None,
) -> dict[str, Any]:
    if supplied_path is None:
        if driver_name != "host":
            raise AgentGraphCliError(
                f"--driver {driver_name} requires an explicit --workspace-receipt",
                code="workspace_receipt_required",
            )
        receipt = _automatic_host_workspace_receipt(repository, run_id)
    else:
        supplied = Path(supplied_path)
        if supplied.is_absolute():
            path = supplied.resolve()
        else:
            path, _ = repository_relative_path(
                repository, supplied_path, "workspace bootstrap receipt"
            )
        try:
            receipt = validate_workspace_bootstrap_receipt(
                load_json_object(path, "workspace bootstrap receipt"),
                expected_run_id=run_id,
                expected_repository=repository,
            )
        except GraphError as error:
            raise AgentGraphCliError(
                str(error), code="workspace_receipt_mismatch"
            ) from error
    return receipt


def _require_current_execution_scope(
    repository: Path, scope: Mapping[str, Any]
) -> None:
    expected_root = str(repository.resolve())
    if (
        scope.get("canonical_root") != expected_root
        or scope.get("execution_host", {}).get("boundary") != "local"
        or scope.get("execution_workspace") != scope.get("orchestration_home")
        or scope.get("execution_workspace", {}).get("path") != expected_root
        or scope.get("orchestration_home", {}).get("path") != expected_root
    ):
        raise AgentGraphCliError(
            "the pinned execution host and workspace are not executable by this runtime",
            code="execution_scope_unsupported",
        )


def _persist_workspace_scope(
    repository: Path,
    directory: Path,
    receipt: Mapping[str, Any],
    *,
    run_id: str,
    coordinator_generation: int,
) -> dict[str, Any]:
    receipt_path = directory / WORKSPACE_BOOTSTRAP_RECEIPT_FILE
    atomic_write_json(receipt_path, receipt)
    receipt_relative = receipt_path.relative_to(repository).as_posix()
    return validate_workspace_scope(
        {
            "schema_version": SCHEMA_VERSION,
            "repository_id": receipt["repository_id"],
            "canonical_root": receipt["canonical_root"],
            "execution_host": receipt["execution_host"],
            "orchestration_home": receipt["orchestration_home"],
            "execution_workspace": receipt["execution_workspace"],
            "base_revision": receipt["base_revision"],
            "dirty_paths": receipt["dirty_paths"],
            "run_id": run_id,
            "coordinator_generation": coordinator_generation,
            "binding_receipt_ref": f"artifact:{receipt_relative}",
            "binding_receipt_hash": _workspace_receipt_hash(receipt),
        }
    )


def _verify_workspace_binding(
    repository: Path,
    directory: Path,
    projection: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        scope = validate_workspace_scope(projection.get("workspace_scope"))
    except (GraphError, TypeError) as error:
        raise AgentGraphCliError(
            f"saved workspace scope is invalid: {error}", code="workspace_binding_invalid"
        ) from error
    expected_root = str(repository.resolve())
    if scope["canonical_root"] != expected_root:
        raise AgentGraphCliError(
            "saved workspace scope does not match --repo", code="workspace_binding_invalid"
        )
    receipt_relative = scope["binding_receipt_ref"].removeprefix("artifact:")
    receipt_path, _ = repository_relative_path(
        repository, receipt_relative, "saved workspace bootstrap receipt"
    )
    expected_path = (directory / WORKSPACE_BOOTSTRAP_RECEIPT_FILE).resolve()
    if receipt_path != expected_path:
        raise AgentGraphCliError(
            "saved workspace receipt reference does not belong to this run",
            code="workspace_binding_invalid",
        )
    try:
        receipt = validate_workspace_bootstrap_receipt(
            load_json_object(receipt_path, "saved workspace bootstrap receipt")
        )
    except (GraphError, CliValidationError) as error:
        raise AgentGraphCliError(
            f"saved workspace bootstrap receipt is invalid: {error}",
            code="workspace_binding_invalid",
        ) from error
    if _workspace_receipt_hash(receipt) != scope["binding_receipt_hash"]:
        raise AgentGraphCliError(
            "saved workspace bootstrap receipt hash does not match",
            code="workspace_binding_invalid",
        )
    for field in (
        "repository_id",
        "canonical_root",
        "execution_host",
        "orchestration_home",
        "execution_workspace",
        "base_revision",
        "dirty_paths",
    ):
        if scope[field] != receipt[field]:
            raise AgentGraphCliError(
                f"saved workspace scope {field} does not match its receipt",
                code="workspace_binding_invalid",
            )
    if receipt["authority"]["issued_for_run_id"] != projection.get("run_id"):
        raise AgentGraphCliError(
            "saved workspace receipt was issued for another run",
            code="workspace_binding_invalid",
        )
    if scope["run_id"] != projection.get("run_id"):
        raise AgentGraphCliError(
            "saved workspace scope run does not match", code="workspace_binding_invalid"
        )
    coordinator = projection.get("coordinator", {})
    if scope["coordinator_generation"] != coordinator.get("generation"):
        raise AgentGraphCliError(
            "saved workspace scope coordinator generation does not match",
            code="workspace_binding_invalid",
        )
    return scope


def _driver_for_state(repository: Path, directory: Path, projection: Mapping[str, Any]):
    _require_current_execution_scope(repository, projection.get("workspace_scope", {}))
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
    _require_current_execution_scope(repository, projection.get("workspace_scope", {}))
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


def _process_decision_field_path(error: CliValidationError) -> str:
    """Return the stable source field associated with a decision validation error."""

    message = str(error)
    schema_location = re.search(r"invalid process decision at ([^:]+):", message)
    if schema_location:
        parts = schema_location.group(1).split(".")
        rendered = "".join(
            f"[{part}]" if part.isdigit() else f".{part}" for part in parts
        )
        unexpected = re.search(r"\('([^']+)' was unexpected\)", message)
        if unexpected:
            rendered += f".{unexpected.group(1)}"
        return f"decision{rendered}"

    paths_by_message = (
        ("process decision revision", "decision.revision"),
        ("process decision amendments", "decision.amendments"),
        ("process decision amendment", "decision.amendments"),
        ("process decision mode", "decision.mode"),
        ("process decision selected check", "decision.selected_check"),
        ("material question", "decision.material_questions"),
        ("graph contract references", "graph_contract.decision_revision"),
        ("graph contract lacks", "graph_contract.permission_observed"),
        ("graph contract requires", "graph_contract"),
        ("graph contract packets", "graph_contract.packets"),
        ("graph contract has", "decision.observations.shared_write_coupling"),
        ("graph packet has no task", "graph_contract.packets"),
        ("graph packet contract diverges", "graph_contract.packets"),
        ("check command", "decision.selected_check.command"),
    )
    for prefix, field_path in paths_by_message:
        if message.startswith(prefix):
            return field_path
    return "decision"


def _load_process_decision_source(
    repository: Path,
    change: str,
    graph: TaskGraph,
    process_decision_path: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Parse and validate the complete source-owned graph decision once."""

    if process_decision_path is None:
        decision_path = repository / "openspec" / "changes" / change / "process-decision.json"
    else:
        decision_path, _ = repository_relative_path(
            repository, process_decision_path, "graph process decision"
        )
    if not decision_path.is_file():
        raise AgentGraphCliError(
            "graph bootstrap requires a current process-decision.json",
            code="process_decision_required",
            details={"field_path": "process-decision.json"},
        )

    decision_payload = load_json_object(decision_path, "graph process decision")
    try:
        process_decision, graph_contract = validate_graph_transition(
            decision_payload, graph.tasks
        )
    except CliValidationError as error:
        raise AgentGraphCliError(
            str(error),
            code="process_decision_invalid",
            details={"field_path": _process_decision_field_path(error)},
        ) from error

    try:
        direct_command_arguments(process_decision["selected_check"]["command"])
    except CliValidationError as error:
        raise AgentGraphCliError(
            str(error),
            code="process_decision_invalid",
            details={"field_path": "decision.selected_check.command"},
        ) from error
    for index, packet in enumerate(graph_contract["packets"]):
        try:
            direct_command_arguments(packet["check"]["command"])
        except CliValidationError as error:
            raise AgentGraphCliError(
                str(error),
                code="process_decision_invalid",
                details={"field_path": f"graph_contract.packets[{index}].check.command"},
            ) from error
    return process_decision, graph_contract


def _initialize(
    repository: Path,
    change: str,
    run_id: str,
    coordinator_id: str,
    driver_name: str,
    workspace_receipt_path: str | None,
    process_decision_path: str | None,
    *,
    defer_driver: bool = False,
) -> tuple[Path, dict[str, Any], dict[str, Any], dict[str, Any]]:
    require_identifier(coordinator_id, "coordinator_id")
    graph = _load_graph(repository, change)
    process_decision, graph_contract = _load_process_decision_source(
        repository, change, graph, process_decision_path
    )
    stop_reasons = evaluate_stop_conditions(
        process_decision,
        permission_observed=graph_contract["permission_observed"],
    )
    if stop_reasons:
        raise AgentGraphCliError(
            f"graph transition stopped: {', '.join(stop_reasons)}",
            code="process_stop_condition",
            details={"stop_reasons": stop_reasons},
        )
    workspace_receipt = _workspace_receipt_for_new_run(
        repository, run_id, driver_name, workspace_receipt_path
    )
    if not defer_driver:
        _require_current_execution_scope(repository, workspace_receipt)
    directory = _new_run_directory(repository, change, run_id)
    control_runtime = create_control_runtime(
        source_root=SCRIPTS_DIRECTORY.parent,
        run_directory=directory,
        source_revision=_current_commit(repository),
    )
    workspace_scope = _persist_workspace_scope(
        repository,
        directory,
        workspace_receipt,
        run_id=run_id,
        coordinator_generation=1,
    )
    journal = _journal(directory)
    projection = journal.append(
        "run_started",
        {
            "change": change,
            "run_id": run_id,
            "coordinator_id": coordinator_id,
            "coordinator_generation": 1,
            "base_commit": workspace_receipt["base_revision"],
            "dirty_paths": workspace_receipt["dirty_paths"],
            "workspace_scope": workspace_scope,
            "control_runtime": control_runtime,
            "process_decision": process_decision,
            "graph_contract": graph_contract,
            "tasks": [task.to_dict() for task in graph.tasks],
        },
        coordinator_generation=1,
    )
    if defer_driver:
        return (
            directory,
            projection,
            {
                "requested": driver_name,
                "selected": None,
                "reason": "driver selection is deferred until the fresh coordinator claims the run",
            },
            control_runtime,
        )
    projection, selection = _select_and_record_driver(
        repository, directory, journal, projection, driver_name, graph, 1
    )
    return directory, projection, selection, control_runtime


def command_intake(arguments: argparse.Namespace) -> dict[str, Any]:
    if arguments.request_file:
        request_path, _ = repository_relative_path(
            arguments.repo, arguments.request_file, "adaptive intake request"
        )
        try:
            request = request_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise CliValidationError(f"cannot read adaptive intake request: {error}") from error
    else:
        request = arguments.request

    signals_path: Path | None = None
    if arguments.signals_file:
        signals_path, _ = repository_relative_path(
            arguments.repo, arguments.signals_file, "adaptive intake signals"
        )
    signals = load_signals(arguments.signals_json, signals_path)
    return decide_process(
        arguments.repo,
        request=request,
        check_command=arguments.check,
        signals=signals,
        use_safe_defaults=arguments.use_safe_defaults,
    )


def command_validate(arguments: argparse.Namespace) -> dict[str, Any]:
    graph = _load_graph(arguments.repo, arguments.change)
    process_decision, graph_contract = _load_process_decision_source(
        arguments.repo, arguments.change, graph, None
    )
    return {
        "change": arguments.change,
        "valid": True,
        "task_count": len(graph.tasks),
        "tasks": [task.to_dict() for task in graph.tasks],
        "process_decision": process_decision,
        "graph_contract": graph_contract,
    }


def command_init(arguments: argparse.Namespace) -> dict[str, Any]:
    directory, projection, selection, control_runtime = _initialize(
        arguments.repo,
        arguments.change,
        arguments.run_id,
        arguments.coordinator_id,
        arguments.driver,
        arguments.workspace_receipt,
        arguments.process_decision,
    )
    return {
        "run_directory": directory.relative_to(arguments.repo).as_posix(),
        "control_runtime": control_runtime,
        "driver_selection": selection,
        "state": projection,
    }


def command_bootstrap(arguments: argparse.Namespace) -> dict[str, Any]:
    bootstrap_id = arguments.bootstrap_id or f"bootstrap-{os.getpid()}"
    require_identifier(bootstrap_id, "bootstrap_id")
    directory, projection, selection, control_runtime = _initialize(
        arguments.repo,
        arguments.change,
        arguments.run_id,
        bootstrap_id,
        arguments.driver,
        arguments.workspace_receipt,
        arguments.process_decision,
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
    coordinator_id = f"coordinator-generation-{generation}"
    resume_arguments = [
        str(Path(sys.executable).resolve()),
        control_runtime["entrypoint"],
        "claim-coordinator",
        "--repo",
        str(arguments.repo),
        "--coordinator-capsule",
        relative_capsule,
        "--coordinator-id",
        coordinator_id,
    ]
    capsule = validate_coordinator_capsule(
        {
            "schema_version": SCHEMA_VERSION,
            "protocol_version": SCHEMA_VERSION,
            "workspace_scope": projection["workspace_scope"],
            "change": arguments.change,
            "run_id": arguments.run_id,
            "driver": arguments.driver,
            "capability_summary": {
                "agents": [],
                "models": [],
                "efforts": [],
                "placement_kinds": sorted({
                    "current-workspace",
                    "existing-workspace",
                    "create-child-worktree",
                }),
                "execution_hosts": sorted({
                    projection["workspace_scope"]["orchestration_home"]["execution_host_id"],
                    projection["workspace_scope"]["execution_workspace"]["execution_host_id"],
                }),
            },
            "routing_overrides": {
                "agent": None,
                "model": None,
                "effort": None,
                "placement_request": None,
            },
            "coordinator_generation": generation,
            "resume_command": format_command(resume_arguments),
            "control_runtime": control_runtime,
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
        "control_runtime": control_runtime,
        "driver_selection": selection,
        "state": projection,
    }


def command_claim(arguments: argparse.Namespace) -> dict[str, Any]:
    path, relative = repository_relative_path(arguments.repo, arguments.capsule, "coordinator capsule")
    raw_capsule = load_json_object(path, "coordinator capsule")
    capsule_runtime = verify_control_runtime(raw_capsule.get("control_runtime", {}))
    capsule = validate_coordinator_capsule(raw_capsule)
    if capsule["workspace_scope"]["canonical_root"] != str(arguments.repo):
        raise AgentGraphCliError("coordinator capsule belongs to another repository", code="capsule_mismatch")
    directory = _run_directory(arguments.repo, capsule["change"], capsule["run_id"])
    saved_runtime = verify_control_runtime(load_run_control_runtime(directory))
    if capsule_runtime != saved_runtime:
        raise ControlRuntimeError("coordinator capsule control runtime does not match the run")
    journal = _journal(directory)
    projection = journal.verify_projection()
    saved_scope = _verify_workspace_binding(arguments.repo, directory, projection)
    if capsule["workspace_scope"] != saved_scope:
        raise AgentGraphCliError(
            "coordinator capsule workspace scope does not match the run",
            code="capsule_mismatch",
        )
    _require_current_execution_scope(arguments.repo, saved_scope)
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
    verify_control_runtime(load_run_control_runtime(directory))
    journal = _journal(directory)
    projection = journal.verify_projection()
    scope = _verify_workspace_binding(arguments.repo, directory, projection)
    _require_current_execution_scope(arguments.repo, scope)
    generation = _generation(arguments, projection)
    attempts = []
    for attempt_id, attempt in projection["attempts"].items():
        if attempt.get("status") not in {"reserved", "running", "interrupted"}:
            continue
        attempts.append(
            _driver_attempt(
                attempt,
                attempt_id,
                _task_from_state(projection, attempt["task_id"]),
            )
        )
    driver = (
        _driver_for_state(arguments.repo, directory, projection)
        if projection.get("driver")
        else None
    )
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
    verify_control_runtime(load_run_control_runtime(directory))
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
    scope = _verify_workspace_binding(arguments.repo, directory, projection)
    _require_current_execution_scope(arguments.repo, scope)
    _generation(arguments, projection)
    attempts = [
        _driver_attempt(
            attempt,
            attempt_id,
            _task_from_state(projection, attempt["task_id"]),
        )
        for attempt_id, attempt in projection["attempts"].items()
        if attempt.get("status") in {"reserved", "running", "interrupted"}
    ]
    driver = _driver_for_state(arguments.repo, directory, projection) if projection.get("driver") else None
    if isinstance(driver, HostDriver):
        for attempt_id, attempt in projection["attempts"].items():
            if not isinstance(attempt, Mapping):
                continue
            _raise_active_host_quarantine(directory, attempt_id, attempt)
            if attempt.get("status") == "reported":
                _verify_reported_result_slot(directory, attempt_id, attempt)
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
        "pending_cleanup": [
            item
            for item in projection["cleanup"].values()
            if not cleanup_is_terminal(item)
        ],
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


def command_amend_decision(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    projection = journal.verify_projection()
    generation = _generation(arguments, projection)
    decision_path, _ = repository_relative_path(
        arguments.repo, arguments.decision, "amended process decision"
    )
    payload = load_json_object(decision_path, "amended process decision")
    decision = payload.get("decision", payload)
    graph_contract = payload.get("graph_contract")
    if isinstance(decision, Mapping) and decision.get("mode") == "graph":
        decision, graph_contract = validate_graph_transition(
            payload, _load_graph(arguments.repo, arguments.change).tasks
        )
    elif not isinstance(decision, Mapping):
        raise AgentGraphCliError(
            "amended process decision is missing", code="process_decision_invalid"
        )
    reduction = None
    if arguments.reduction_json:
        try:
            reduction = json.loads(arguments.reduction_json)
        except json.JSONDecodeError as error:
            raise AgentGraphCliError(
                f"reduction plan is invalid JSON: {error}", code="process_reduction_invalid"
            ) from error
        if not isinstance(reduction, Mapping):
            raise AgentGraphCliError(
                "reduction plan must be one object", code="process_reduction_invalid"
            )
    projection = journal.append(
        "process_decision_amended",
        {
            "decision": decision,
            "graph_contract": graph_contract,
            "reduction": reduction,
        },
        coordinator_generation=generation,
    )
    cleanup = {"released": [], "pending": []}
    if decision.get("mode") != "graph" and isinstance(projection.get("reduction"), Mapping):
        cleanup, projection = _release_reduction_surplus(
            arguments.repo,
            directory,
            journal,
            projection,
            generation,
            projection["reduction"],
        )
    return {
        "decision_revision": decision.get("revision"),
        "mode": decision.get("mode"),
        "reduction": projection.get("reduction"),
        "cleanup": cleanup,
        "state": projection,
    }


def _delegation(directory: Path, projection: Mapping[str, Any], delegation_id: str) -> Mapping[str, Any]:
    require_identifier(delegation_id, "delegation_id")
    delegation = projection.get("delegations", {}).get(delegation_id)
    if not isinstance(delegation, Mapping):
        raise AgentGraphCliError(f"unknown delegation: {delegation_id}", code="unknown_delegation")
    return delegation


def _delegation_json(repository: Path, path: str, label: str) -> dict[str, Any]:
    resolved, _ = repository_relative_path(repository, path, label)
    return load_json_object(resolved, label)


def _lifecycle_receipt(repository: Path, receipt_id: str, receipt_path: str) -> dict[str, Any]:
    require_identifier(receipt_id, "receipt_id")
    path, normalized = repository_relative_path(repository, receipt_path, "lifecycle receipt")
    expected_prefix = "openspec/runs/"
    if not normalized.startswith(expected_prefix) or "/artifacts/" not in normalized:
        raise AgentGraphCliError("lifecycle receipt must be a run artifact", code="invalid_receipt")
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise AgentGraphCliError(f"cannot read lifecycle receipt: {error}", code="invalid_receipt") from error
    if not payload:
        raise AgentGraphCliError("lifecycle receipt must not be empty", code="invalid_receipt")
    return {
        "receipt_id": receipt_id,
        "receipt_path": normalized,
        "sha256": f"sha256:{hashlib.sha256(payload).hexdigest()}",
        "byte_length": len(payload),
    }


def command_request_delegation(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    projection = journal.verify_projection()
    generation = _generation(arguments, projection)
    scope = projection.get("workspace_scope")
    if not isinstance(scope, Mapping):
        raise AgentGraphCliError("delegation requires a pinned workspace scope", code="invalid_state")
    intent = validate_delegation_intent(_delegation_json(arguments.repo, arguments.intent, "delegation intent"), scope)
    existing = projection.get("delegations", {}).get(intent["intent_id"])
    if isinstance(existing, Mapping):
        if existing.get("intent") != intent:
            raise AgentGraphCliError("delegation intent ID already has different content", code="duplicate_delegation")
        return {"delegation_id": intent["intent_id"], "requested": True, "idempotent": True, "state": projection}
    projection = journal.append("delegation_requested", {"intent": intent}, coordinator_generation=generation)
    return {"delegation_id": intent["intent_id"], "requested": True, "idempotent": False, "state": projection}


def command_amend_graph(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    projection = journal.verify_projection()
    generation = _generation(arguments, projection)
    amendment_id = require_identifier(arguments.amendment_id, "amendment_id")
    expected = {
        "amendment_id": amendment_id,
        "parent_task_id": require_identifier(arguments.parent_task, "parent_task"),
        "parent_attempt_id": require_identifier(arguments.parent_attempt, "parent_attempt"),
        "paths": arguments.path,
        "reason": arguments.reason,
        "coordinator_id": projection["coordinator"]["id"],
        "coordinator_generation": generation,
    }
    existing = projection.get("graph_amendments", {}).get(amendment_id)
    if isinstance(existing, Mapping):
        if dict(existing) != expected:
            raise AgentGraphCliError("graph amendment ID already has different content", code="duplicate_amendment")
        return {"amendment_id": amendment_id, "amended": True, "idempotent": True, "state": projection}
    projection = journal.append("graph_amended", expected, coordinator_generation=generation)
    return {"amendment_id": amendment_id, "amended": True, "idempotent": False, "state": projection}


def command_approve_delegation(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    projection = journal.verify_projection()
    generation = _generation(arguments, projection)
    delegation = _delegation(directory, projection, arguments.delegation)
    scope = projection.get("workspace_scope")
    if not isinstance(scope, Mapping):
        raise AgentGraphCliError("delegation requires a pinned workspace scope", code="invalid_state")
    profile = validate_execution_profile(_delegation_json(arguments.repo, arguments.execution_profile, "execution profile"), scope)
    paths = arguments.path or list(delegation["intent"]["paths"])
    context_refs = arguments.context_ref or list(delegation["intent"]["context_refs"])
    expected = {
        "delegation_id": arguments.delegation,
        "paths": paths,
        "context_refs": context_refs,
        "context_revision": arguments.context_revision,
        "execution_profile": profile,
        **({"amendment_id": arguments.amendment_id} if arguments.amendment_id else {}),
    }
    if delegation.get("status") in {"approved", "started", "reported", "released"}:
        saved = {
            key: delegation.get(key)
            for key in ("paths", "context_refs", "context_revision", "execution_profile", "amendment_id")
            if key != "amendment_id" or "amendment_id" in delegation
        }
        if saved != {key: value for key, value in expected.items() if key != "delegation_id"}:
            raise AgentGraphCliError("delegation was approved with different content", code="duplicate_delegation")
        return {"delegation_id": arguments.delegation, "approved": True, "idempotent": True, "state": projection}
    projection = journal.append("delegation_approved", expected, coordinator_generation=generation)
    return {"delegation_id": arguments.delegation, "approved": True, "idempotent": False, "state": projection}


def command_reject_delegation(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    projection = journal.verify_projection()
    generation = _generation(arguments, projection)
    delegation = _delegation(directory, projection, arguments.delegation)
    if delegation.get("status") == "rejected":
        if delegation.get("reason") != arguments.reason:
            raise AgentGraphCliError("delegation was rejected with another reason", code="duplicate_delegation")
        return {"delegation_id": arguments.delegation, "rejected": True, "idempotent": True, "state": projection}
    projection = journal.append("delegation_rejected", {"delegation_id": arguments.delegation, "reason": arguments.reason}, coordinator_generation=generation)
    return {"delegation_id": arguments.delegation, "rejected": True, "idempotent": False, "state": projection}


def command_start_delegation(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    projection = journal.verify_projection()
    generation = _generation(arguments, projection)
    delegation = _delegation(directory, projection, arguments.delegation)
    try:
        owner = validate_cleanup_owner(json.loads(arguments.resource_owner))
    except (json.JSONDecodeError, GraphError) as error:
        raise AgentGraphCliError(f"invalid delegation resource owner: {error}", code="invalid_delegation") from error
    receipt = _lifecycle_receipt(arguments.repo, arguments.receipt_id, arguments.receipt_path)
    expected = {
        "delegation_id": arguments.delegation,
        "child_attempt_id": arguments.child_attempt,
        "resource_owner": owner,
        "receipt": receipt,
    }
    if delegation.get("status") in {"started", "reported", "released"}:
        saved = {
            "delegation_id": arguments.delegation,
            "child_attempt_id": delegation.get("child_attempt_id"),
            "resource_owner": delegation.get("resource_owner"),
            "receipt": delegation.get("lifecycle_receipts", {}).get("started"),
        }
        if saved != expected:
            raise AgentGraphCliError("delegation was started with different receipt identity", code="duplicate_delegation")
        return {"delegation_id": arguments.delegation, "started": True, "idempotent": True, "state": projection}
    projection = journal.append("delegation_started", expected, coordinator_generation=generation)
    return {"delegation_id": arguments.delegation, "started": True, "idempotent": False, "state": projection}


def command_report_delegation(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    projection = journal.verify_projection()
    generation = _generation(arguments, projection)
    delegation = _delegation(directory, projection, arguments.delegation)
    result = _delegation_json(arguments.repo, arguments.result, "delegation result")
    receipt = _lifecycle_receipt(arguments.repo, arguments.receipt_id, arguments.receipt_path)
    expected = {"delegation_id": arguments.delegation, "result": result, "receipt": receipt}
    if delegation.get("status") in {"reported", "released"}:
        saved = {"delegation_id": arguments.delegation, "result": delegation.get("report"), "receipt": delegation.get("lifecycle_receipts", {}).get("reported")}
        if saved != expected:
            raise AgentGraphCliError("delegation already has a different report", code="duplicate_delegation")
        return {"delegation_id": arguments.delegation, "reported": True, "idempotent": True, "state": projection}
    projection = journal.append("delegation_reported", expected, coordinator_generation=generation)
    return {"delegation_id": arguments.delegation, "reported": True, "idempotent": False, "state": projection}


def command_release_delegation(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    projection = journal.verify_projection()
    generation = _generation(arguments, projection)
    delegation = _delegation(directory, projection, arguments.delegation)
    receipt = _lifecycle_receipt(arguments.repo, arguments.receipt_id, arguments.receipt_path)
    expected = {"delegation_id": arguments.delegation, "cleanup_id": arguments.cleanup_id, "receipt": receipt}
    if delegation.get("status") == "released":
        saved = {"delegation_id": arguments.delegation, "cleanup_id": delegation.get("cleanup_id"), "receipt": delegation.get("lifecycle_receipts", {}).get("released")}
        if saved != expected:
            raise AgentGraphCliError("delegation was released with a different receipt", code="duplicate_delegation")
        return {"delegation_id": arguments.delegation, "released": True, "idempotent": True, "state": projection}
    projection = journal.append("delegation_released", expected, coordinator_generation=generation)
    return {"delegation_id": arguments.delegation, "released": True, "idempotent": False, "state": projection}


def command_register_delegation_cleanup(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    projection = journal.verify_projection()
    generation = _generation(arguments, projection)
    delegation = _delegation(directory, projection, arguments.delegation)
    if delegation.get("status") not in {"started", "reported"}:
        raise AgentGraphCliError("delegation cleanup requires a started child", code="invalid_delegation")
    cleanup_id = require_identifier(arguments.cleanup_id, "cleanup_id")
    target: Any = arguments.target
    if arguments.kind == "process":
        try:
            target = json.loads(target)
        except json.JSONDecodeError as error:
            raise AgentGraphCliError("process cleanup target must be JSON", code="invalid_cleanup") from error
    expected = {
        "cleanup_id": cleanup_id,
        "kind": arguments.kind,
        "target": target,
        "owner": delegation["resource_owner"],
        "delegation_id": arguments.delegation,
    }
    if arguments.kind == "process":
        expected["identity_version"] = 1
    else:
        expected["attempt_id"] = delegation["child_attempt_id"]
    existing = projection["cleanup"].get(cleanup_id)
    if isinstance(existing, Mapping):
        if any(existing.get(key) != value for key, value in expected.items()):
            raise AgentGraphCliError("cleanup ID already has different ownership", code="duplicate_cleanup")
        return {"cleanup_id": cleanup_id, "registered": True, "idempotent": True, "state": projection}
    projection = journal.append("cleanup_registered", expected, coordinator_generation=generation)
    return {"cleanup_id": cleanup_id, "registered": True, "idempotent": False, "state": projection}


def _reused_host_session_handoff(
    *,
    graph: TaskGraph,
    projection: Mapping[str, Any],
    task: TaskContract,
    worker_handle: str | None,
    workspace_scope: Mapping[str, Any],
    execution_profile: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Return the incremental handoff only for one proven compatible Host handle.

    Host deliberately has no agent-launch fallback.  Reuse is therefore opt-in
    through the exact native handle passed by the active coordinator; every
    uncertainty returns ``None`` and lets the coordinator remain the writer.
    """

    if not isinstance(worker_handle, str) or not worker_handle:
        return None
    dependencies = set(task.depends)
    if not dependencies:
        return None
    tasks = projection.get("tasks")
    attempts = projection.get("attempts")
    if not isinstance(tasks, Mapping) or not isinstance(attempts, Mapping):
        return None
    compatible_attempts: list[tuple[str, Mapping[str, Any]]] = []
    for dependency in task.depends:
        prior_state = tasks.get(dependency)
        if not isinstance(prior_state, Mapping) or prior_state.get("grade") != "pass":
            return None
        attempt_ids = prior_state.get("attempt_ids")
        if not isinstance(attempt_ids, list):
            return None
        for attempt_id in reversed(attempt_ids):
            candidate = attempts.get(attempt_id)
            if not isinstance(candidate, Mapping):
                return None
            if candidate.get("status") != "reported":
                continue
            refs = candidate.get("external_refs")
            report = candidate.get("report")
            if not isinstance(refs, Mapping) or not isinstance(report, Mapping):
                return None
            if (
                refs.get("tier") == "host-native"
                and refs.get("worker_handle") == worker_handle
                and candidate.get("workspace_scope") == workspace_scope
                and candidate.get("execution_profile") == execution_profile
            ):
                compatible_attempts.append((dependency, candidate))
    if len(compatible_attempts) != 1:
        return None
    prior_task_id, prior_attempt = compatible_attempts[0]
    selected_report = prior_attempt.get("report")
    if not isinstance(selected_report, Mapping):
        return None
    prior_check = prior_attempt.get("check")
    check_label = (
        prior_check.get("command")
        if isinstance(prior_check, Mapping) and isinstance(prior_check.get("command"), str)
        else ""
    )
    dependency_summaries: list[dict[str, str]] = []
    for dependency in task.depends:
        dependency_state = tasks.get(dependency)
        if not isinstance(dependency_state, Mapping):
            return None
        summary = ""
        attempt_ids = dependency_state.get("attempt_ids")
        if isinstance(attempt_ids, list):
            for attempt_id in reversed(attempt_ids):
                candidate = attempts.get(attempt_id)
                dependency_report = candidate.get("report") if isinstance(candidate, Mapping) else None
                if isinstance(dependency_report, Mapping):
                    summary = str(dependency_report.get("summary", ""))
                    break
        if not summary and isinstance(dependency_state.get("import_receipt"), Mapping):
            summary = str(dependency_state["import_receipt"].get("note", ""))
        dependency_summaries.append({"task_id": dependency, "summary": summary})
    try:
        return build_reused_session_handoff(
            task_id=task.id,
            acceptance=task.acceptance,
            dependency_summaries=dependency_summaries,
            diff_since_previous_check=list(selected_report.get("files_changed", [])),
            unresolved_material_finding_refs=[],
            allowed_paths=task.paths,
            check=task.check,
            session_memory={
                "decisions": [f"Task {prior_task_id} passed before this handoff."],
                "invariants": ["Each task keeps its own attempt, check, evidence, grade, and cleanup."],
                "central_files": list(selected_report.get("files_changed", [])),
                "traps": [],
                "green_checks": [check_label] if check_label else [],
                "carry_forward_findings": [],
            },
        )
    except (KeyError, TypeError, ValueError):
        # A malformed historical report is not a safe reason to reuse context.
        return None


def _reused_orca_session_terminal(
    *,
    graph: TaskGraph,
    projection: Mapping[str, Any],
    task: TaskContract,
    workspace_scope: Mapping[str, Any],
    execution_profile: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Return one persisted terminal lease for a compatible serial Orca task."""

    if workspace_scope.get("execution_host", {}).get("boundary") != "local":
        return None
    dependencies = set(task.depends)
    if not dependencies:
        return None
    for prior_task in reversed(graph.tasks[: graph.tasks.index(task)]):
        if prior_task.id not in dependencies:
            continue
        prior_state = projection.get("tasks", {}).get(prior_task.id)
        if not isinstance(prior_state, Mapping) or prior_state.get("grade") != "pass":
            return None
        attempt_ids = prior_state.get("attempt_ids")
        if not isinstance(attempt_ids, list):
            return None
        for attempt_id in reversed(attempt_ids):
            attempt = projection.get("attempts", {}).get(attempt_id)
            if not isinstance(attempt, Mapping) or attempt.get("status") != "reported":
                continue
            refs = attempt.get("external_refs")
            cleanup_id = attempt.get("cleanup_id")
            cleanup = projection.get("cleanup", {}).get(cleanup_id)
            tier = refs.get("tier") if isinstance(refs, Mapping) else None
            terminal = (
                refs.get("reusable_session_terminal")
                if tier == "supervised"
                else refs.get("terminal")
            ) if isinstance(refs, Mapping) else None
            if (
                not isinstance(refs, Mapping)
                or tier not in {"supervised", "tracked-terminal"}
                or not isinstance(terminal, Mapping)
                or attempt.get("workspace_scope") != workspace_scope
                or attempt.get("execution_profile") != execution_profile
                or not isinstance(cleanup, Mapping)
                or cleanup_is_terminal(cleanup)
            ):
                return None
            return {
                "terminal": dict(terminal),
                "execution_profile": dict(execution_profile),
                "workspace_scope": dict(workspace_scope),
                "lease_status": "active",
                "cleanup_tier": tier,
            }
        return None
    return None


def _session_handoff_from_projection(
    *, task: TaskContract, projection: Mapping[str, Any]
) -> dict[str, Any] | None:
    """Derive one bounded follow-up capsule from accepted dependency evidence."""

    summaries: list[dict[str, str]] = []
    latest_report: Mapping[str, Any] | None = None
    for dependency in task.depends:
        task_state = projection.get("tasks", {}).get(dependency)
        if not isinstance(task_state, Mapping) or task_state.get("grade") != "pass":
            return None
        attempt_ids = task_state.get("attempt_ids")
        if not isinstance(attempt_ids, list):
            return None
        reports = [
            projection.get("attempts", {}).get(attempt_id, {}).get("report")
            for attempt_id in reversed(attempt_ids)
            if isinstance(projection.get("attempts", {}).get(attempt_id), Mapping)
        ]
        report = next((item for item in reports if isinstance(item, Mapping)), None)
        if report is None:
            return None
        summaries.append({"task_id": dependency, "summary": str(report.get("summary", ""))})
        latest_report = report
    if latest_report is None:
        return None
    previous_files = list(latest_report.get("files_changed", []))
    previous_check = ""
    for dependency in reversed(task.depends):
        check = projection.get("tasks", {}).get(dependency, {}).get("check")
        if isinstance(check, Mapping) and isinstance(check.get("command"), str):
            previous_check = check["command"]
            break
    try:
        return build_reused_session_handoff(
            task_id=task.id,
            acceptance=task.acceptance,
            dependency_summaries=summaries,
            diff_since_previous_check=previous_files,
            unresolved_material_finding_refs=[],
            allowed_paths=task.paths,
            check=task.check,
            session_memory={
                "decisions": ["Accepted dependency evidence is retained by reference."],
                "invariants": ["Every task keeps its own attempt, check, evidence, grade, and cleanup."],
                "central_files": previous_files,
                "traps": [],
                "green_checks": [previous_check] if previous_check else [],
                "carry_forward_findings": [],
            },
        )
    except (TypeError, ValueError):
        return None


def command_dispatch(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    projection = journal.verify_projection()
    workspace_scope = _verify_workspace_binding(arguments.repo, directory, projection)
    _require_current_execution_scope(arguments.repo, workspace_scope)
    generation = _generation(arguments, projection)
    graph = _saved_graph(projection)
    task = _task_from_state(projection, arguments.task)
    pending_cleanup = pending_cleanup_ids_for_task(projection, task.id)
    if pending_cleanup:
        raise AgentGraphCliError(
            f"finish or retain cleanup before retrying {task.id}: {', '.join(pending_cleanup)}",
            code="cleanup_pending",
        )
    if not task_is_dispatchable(graph, projection, task):
        blockers = task_blockers(task, projection)
        detail = f"; blockers: {blockers}" if blockers else "; task is graded, active, awaiting cleanup, or fenced by an active writer"
        raise AgentGraphCliError(f"task {task.id} is not ready{detail}", code="task_not_ready")
    previous_attempts = projection["tasks"][task.id]["attempt_ids"]
    attempt_id = arguments.attempt_id or f"attempt-{task.id.lower()}-{len(previous_attempts) + 1:03d}"
    require_identifier(attempt_id, "attempt_id")
    if attempt_id in projection["attempts"]:
        raise AgentGraphCliError(
            f"attempt ID already exists: {attempt_id}", code="duplicate_attempt"
        )
    effective_scope = effective_attempt_scope(task, attempt_id, projection)
    dependency_digest = dependency_digest_from_projection(task, projection)
    route_ref = None
    if projection["driver"] == "orca":
        if not getattr(arguments, "route_input", None):
            raise AgentGraphCliError("Orca dispatch requires --route-input", code="routing_catalog_missing")
        route_input, route_input_path, route_input_sha256 = _route_input(
            arguments.repo, arguments.route_input, projection
        )
    else:
        route_input = _default_routing_policy_input(arguments.repo)
    pinned_policy, policy_path, policy_digest = _pin_routing_policy(
        arguments.repo, directory, route_input["routing_policy"]
    )
    route_input["routing_policy"] = pinned_policy
    route_input["routing_policy_path"] = policy_path
    route_input["routing_policy_digest"] = policy_digest
    execution_profile, routing_decision = _routing_for_task(
        task,
        workspace_scope,
        driver_name=str(projection["driver"]),
        route_input=route_input,
    )
    routing_summary = _routing_summary(routing_decision, route_input)
    if projection["driver"] == "orca":
        route_ref = _persist_routing_decision(
            arguments.repo,
            directory,
            route_input=route_input,
            route_input_path=route_input_path,
            route_input_sha256=route_input_sha256,
            decision=routing_decision,
            execution_profile=execution_profile,
            routing_summary=routing_summary,
        )
    driver = _driver_for_state(arguments.repo, directory, projection)
    session_handoff = (
        _reused_host_session_handoff(
            graph=graph,
            projection=projection,
            task=task,
            worker_handle=arguments.worker,
            workspace_scope=workspace_scope,
            execution_profile=execution_profile,
        )
        if projection["driver"] == "host" and not arguments.local
        else None
    )
    session_terminal = (
        _reused_orca_session_terminal(
            graph=graph,
            projection=projection,
            task=task,
            workspace_scope=workspace_scope,
            execution_profile=execution_profile,
        )
        if projection["driver"] == "orca"
        else None
    )
    if (
        session_terminal is not None
        and projection["driver"] == "orca"
        and session_terminal.get("cleanup_tier") == "supervised"
        and "maestro.terminal-lease.v1" not in getattr(driver, "runtime_capabilities", frozenset())
    ):
        # A managed terminal may only transfer through the public v1 lease protocol.
        session_terminal = None
    if session_terminal is not None:
        session_handoff = _session_handoff_from_projection(task=task, projection=projection)
        if session_handoff is None:
            session_terminal = None
    request = {
        "task_id": task.id,
        "attempt_id": attempt_id,
        "task": task.to_dict(),
        "effective_scope": effective_scope,
        "dependency_digest": dependency_digest,
        "worker_handle": arguments.worker,
        "local": arguments.local,
        "workspace_scope": workspace_scope,
        "execution_profile": execution_profile,
        "routing_decision": routing_decision,
        "routing_summary": routing_summary,
        **({"routing_decision_ref": route_ref} if route_ref is not None else {}),
        "external_refs": {},
        **({"session_handoff": session_handoff} if session_handoff is not None else {}),
        **({"session_terminal": session_terminal} if session_terminal is not None else {}),
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
            "effective_scope": effective_scope,
            "dependency_digest": dependency_digest,
            "workspace_scope": workspace_scope,
            "execution_profile": execution_profile,
            "resolved_placement": execution_profile["resolved_placement"],
            "external_refs": {},
            **({"session_handoff": session_handoff} if session_handoff is not None else {}),
            **({"session_terminal": session_terminal} if session_terminal is not None else {}),
            "routing_decision": routing_decision,
            "routing_summary": routing_summary,
            **({"routing_decision_ref": route_ref} if route_ref is not None else {}),
        },
        coordinator_generation=generation,
    )
    if getattr(arguments, "defer_launch", False):
        return {"attempt_id": attempt_id, "reserved": True, "state": projection}
    projection = journal.append(
        "attempt_scope_frozen",
        {"attempt_id": attempt_id, "effective_scope": projection["attempts"][attempt_id]["effective_scope"]},
        coordinator_generation=generation,
    )
    reserved_attempt = projection["attempts"][attempt_id]
    try:
        context = persisted_driver_context(reserved_attempt)
    except DriverError as error:
        raise AgentGraphCliError(str(error), code=error.code) from error
    workspace_scope = context["workspace_scope"]
    execution_profile = context["execution_profile"]
    request.update(context)
    request["effective_scope"] = json.loads(json.dumps(reserved_attempt["effective_scope"], sort_keys=True))
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
    if projection["driver"] == "orca" and refs.get("tier") == "supervised":
        runtime_id = getattr(driver, "runtime_id", None)
        if not isinstance(runtime_id, str) or not runtime_id:
            _rollback_post_start_failure(arguments.repo, directory, journal, generation, driver, task, attempt_id, workspace_scope, execution_profile, refs, receipt, "missing runtime identity")
            raise AgentGraphCliError(
                "supervised Orca start lacks its authoritative runtime identity", code="cleanup_unproven"
            )
        refs["runtime_id"] = runtime_id
    if projection["driver"] == "orca":
        try:
            started_owner, cleanup_id = _orca_lifecycle_from_receipt(refs, attempt_id, workspace_scope)
        except AgentGraphCliError as error:
            _rollback_post_start_failure(arguments.repo, directory, journal, generation, driver, task, attempt_id, workspace_scope, execution_profile, refs, receipt, str(error))
            raise
    else:
        started_owner, cleanup_id = None, None
    cleanup_registration = (
        {
            "cleanup_id": cleanup_id,
            "kind": "terminal" if started_owner["terminal_id"] is not None else "other",
            "target": started_owner["terminal_id"] or refs["dispatch_id"],
            "owner": started_owner,
            "external_refs": dict(refs),
        }
        if cleanup_id and started_owner is not None
        else None
    )
    try:
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
            "effective_scope": effective_scope,
            "dependency_digest": dependency_digest,
            "workspace_scope": workspace_scope,
            "execution_profile": execution_profile,
            "routing_decision": routing_decision,
            "routing_summary": routing_summary,
            **({"resource_owner": started_owner} if started_owner is not None else {}),
            "cleanup_id": cleanup_id,
            **({"cleanup_registration": cleanup_registration} if cleanup_registration is not None else {}),
            },
            coordinator_generation=generation,
        )
    except JournalError as error:
        _rollback_post_start_failure(arguments.repo, directory, journal, generation, driver, task, attempt_id, workspace_scope, execution_profile, refs, receipt, str(error))
        raise
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


def _task_for_effective_scope(
    task: TaskContract, scope: Mapping[str, Any]
) -> TaskContract:
    paths = scope.get("paths")
    amendment_ids = scope.get("amendment_ids")
    if not isinstance(paths, list) or not isinstance(amendment_ids, list):
        raise AgentGraphCliError(
            "attempt is missing its immutable effective scope", code="scope_drift"
        )
    mode = "write" if task.mode == "read" and amendment_ids else task.mode
    return TaskContract(**{**task.to_dict(), "mode": mode, "paths": tuple(paths)})


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
    if isinstance(attempt.get("result_quarantine"), Mapping):
        _raise_result_slot_quarantined(attempt_id, attempt["result_quarantine"])
    task = _task_from_state(projection, attempt["task_id"])
    scope = attempt.get("effective_scope")
    expected_scope = effective_attempt_scope(task, attempt_id, projection)
    if scope != expected_scope:
        raise AgentGraphCliError("attempt effective scope digest drift", code="scope_drift")
    effective_task = _task_for_effective_scope(task, scope)
    validated = validate_worker_result(result, effective_task, attempt_id)
    if attempt.get("status") == "reported":
        _verify_reported_result_slot(directory, attempt_id, attempt)
        saved = attempt.get("report", {})
        comparable = {key: saved.get(key) for key in validated}
        if comparable != validated:
            raise AgentGraphCliError(f"attempt already has a different terminal report: {attempt_id}", code="duplicate_result")
        return projection, True
    receipt_id, receipt_path = _write_receipt(repository, directory, dict(receipt))
    report_scope = scope
    if not isinstance(report_scope, Mapping):
        raise AgentGraphCliError("attempt is missing its immutable effective scope", code="scope_drift")
    result_path = _safe_run_file(
        directory, Path("results") / f"{require_identifier(attempt_id, 'attempt_id')}.json", "result slot"
    )
    result_digest = "sha256:" + hashlib.sha256(
        _read_regular_file(result_path, "result slot")
    ).hexdigest() if result_path.exists() else None
    projection = journal.append(
        "worker_reported",
        {
            **validated,
            "effective_scope": json.loads(json.dumps(dict(report_scope), sort_keys=True)),
            "receipt_id": receipt_id,
            "receipt_path": receipt_path,
            **({"result_digest": result_digest} if result_digest is not None else {}),
        },
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
    if isinstance(attempt.get("result_quarantine"), Mapping):
        _raise_result_slot_quarantined(arguments.attempt, attempt["result_quarantine"])
    driver = _driver_for_state(arguments.repo, directory, projection)
    if isinstance(driver, HostDriver) and attempt.get("status") == "reported":
        _verify_reported_result_slot(directory, arguments.attempt, attempt)
    task = _task_from_state(projection, attempt["task_id"])
    scope = attempt.get("effective_scope")
    expected_scope = effective_attempt_scope(task, arguments.attempt, projection)
    if scope != expected_scope:
        raise AgentGraphCliError("attempt effective scope digest drift", code="scope_drift")
    effective_task = _task_for_effective_scope(task, scope)
    if arguments.result is not None:
        result_path, normalized_result_path = repository_relative_path(
            arguments.repo, arguments.result, "worker result"
        )
        expected_result_path = (
            directory / "results" / f"{require_identifier(arguments.attempt, 'attempt_id')}.json"
        )
        if result_path == expected_result_path:
            raw = _read_regular_file(result_path, "candidate")
            if _candidate_validation_error(raw, effective_task, arguments.attempt) is not None:
                quarantine_arguments = argparse.Namespace(
                    **vars(arguments),
                    task=task.id,
                    candidate=normalized_result_path,
                    idempotency_key=f"record-result-{arguments.attempt}",
                )
                quarantined = command_quarantine_result(quarantine_arguments)
                return {
                    "attempt_id": arguments.attempt,
                    "reported": False,
                    "quarantined": True,
                    "receipt": quarantined["receipt"],
                    "state": quarantined["state"],
                }
    result = _result_argument(arguments)
    validated = validate_worker_result(result, effective_task, arguments.attempt)
    receipt_payload: Mapping[str, Any]
    if isinstance(driver, HostDriver):
        receipt = driver.record_result(effective_task, arguments.attempt, validated, projection=projection)
        receipt_payload = receipt.to_dict()
    else:
        receipt_payload = {"operation": "record_result", "status": "reported", "result": validated}
    projection, idempotent = _append_report(
        arguments.repo,
        directory,
        journal,
        projection,
        generation,
        arguments.attempt,
        validated,
        receipt_payload,
    )
    return {"attempt_id": arguments.attempt, "reported": True, "idempotent": idempotent, "state": projection}


def _safe_run_file(
    directory: Path,
    relative: Path,
    context: str,
    *,
    allow_missing_parents: bool = False,
) -> Path:
    """Resolve a run-owned path only through real, non-symlink directories."""

    run_root = directory.resolve()
    candidate = directory / relative
    current = directory
    for part in relative.parts[:-1]:
        current /= part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError as error:
            if allow_missing_parents:
                continue
            raise AgentGraphCliError(f"{context} parent is missing: {current}", code="quarantine_path_missing") from error
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise AgentGraphCliError(f"{context} parent is unsafe: {current}", code="quarantine_path_unsafe")
    try:
        candidate.resolve().relative_to(run_root)
    except ValueError as error:
        raise AgentGraphCliError(f"{context} escapes its run", code="quarantine_path_escape") from error
    return candidate


def _candidate_validation_error(raw: bytes, task: TaskContract, attempt_id: str) -> str | None:
    try:
        candidate = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError:
        return "invalid_encoding"
    except json.JSONDecodeError:
        return "invalid_json"
    try:
        validate_worker_result(candidate, task, attempt_id)
    except GraphError:
        return "invalid_worker_result"
    return None


def _canonical_worker_result_bytes(result: Mapping[str, Any]) -> bytes:
    """Serialize a provider result deterministically before validating it."""

    return json.dumps(
        dict(result), ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _materialize_write_once_result_candidate(
    directory: Path, attempt_id: str, raw: bytes
) -> Path:
    """Durably publish one immutable canonical result candidate without replacement."""

    result_path = _safe_run_file(
        directory,
        Path("results") / f"{require_identifier(attempt_id, 'attempt_id')}.json",
        "candidate",
    )
    parent = result_path.parent
    try:
        parent_mode = parent.lstat().st_mode
    except FileNotFoundError as error:
        raise AgentGraphCliError("candidate parent is missing", code="quarantine_path_missing") from error
    if stat.S_ISLNK(parent_mode) or not stat.S_ISDIR(parent_mode):
        raise AgentGraphCliError("candidate parent is unsafe", code="quarantine_path_unsafe")
    temporary_path = parent / f".{attempt_id}.{uuid.uuid4().hex}.candidate"
    try:
        with temporary_path.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary_path, result_path)
        except FileExistsError:
            existing = _read_regular_file(result_path, "candidate")
            if existing != raw:
                raise AgentGraphCliError(
                    "canonical provider result candidate already differs",
                    code="provider_delivery_identity_mismatch",
                )
        except OSError as error:
            raise AgentGraphCliError(
                f"cannot materialize canonical candidate: {error}",
                code="quarantine_relocation_failed",
            ) from error
        else:
            try:
                directory_handle = os.open(parent, os.O_RDONLY)
                try:
                    os.fsync(directory_handle)
                finally:
                    os.close(directory_handle)
            except OSError as error:
                raise AgentGraphCliError(
                    f"cannot synchronize canonical candidate directory: {error}",
                    code="quarantine_relocation_failed",
                ) from error
    finally:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass
    return result_path


def _orca_quarantine_idempotency_key(
    attempt_id: str, message_id: str, delivery_id: str
) -> str:
    identity = f"{attempt_id}\0{message_id}\0{delivery_id}".encode("utf-8")
    return f"orca-result-{hashlib.sha256(identity).hexdigest()[:32]}"


def _read_regular_file(path: Path, context: str) -> bytes:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError as error:
        raise AgentGraphCliError(f"{context} is missing", code="candidate_missing") from error
    if stat.S_ISLNK(mode):
        raise AgentGraphCliError(f"{context} cannot be a symlink", code="candidate_symlink")
    if not stat.S_ISREG(mode):
        raise AgentGraphCliError(f"{context} must be a regular file", code="candidate_unsafe")
    try:
        return path.read_bytes()
    except OSError as error:
        raise AgentGraphCliError(f"cannot read {context}: {error}", code="candidate_unreadable") from error


def _raise_result_slot_quarantined(attempt_id: str, receipt: Mapping[str, Any]) -> None:
    raise AgentGraphCliError(
        f"result slot is quarantined for {attempt_id}",
        code="result_slot_quarantined",
        details={"attempt_id": attempt_id, "receipt": dict(receipt)},
    )


ACTIVE_QUARANTINE_STATUSES = frozenset(
    {"reserved", "running", "interrupted", "reported", "audit-rejected"}
)


def _has_active_result_quarantine(attempt: Mapping[str, Any]) -> bool:
    return (
        attempt.get("status") in ACTIVE_QUARANTINE_STATUSES
        and isinstance(attempt.get("result_quarantine"), Mapping)
    )


def _legacy_malformed_evidence(
    directory: Path, attempt_id: str, attempt: Mapping[str, Any]
) -> bytes | None:
    """Verify legacy Host rejection evidence before evaluating its quarantine gate."""

    rejection = attempt.get("provider_result_rejection")
    if not isinstance(rejection, Mapping):
        return None
    evidence_ref = rejection.get("evidence_ref")
    if not isinstance(evidence_ref, str) or not evidence_ref.startswith("file:"):
        raise AgentGraphCliError("malformed candidate evidence is invalid", code="malformed_candidate_collision")
    path = directory.parent.parent.parent.parent / evidence_ref.removeprefix("file:")
    if not path.is_file():
        raise AgentGraphCliError(
            "malformed candidate evidence is missing",
            code="malformed_candidate_evidence_missing",
        )
    raw = _read_regular_file(path, "malformed candidate evidence")
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    if digest != rejection.get("sha256") or len(raw) != rejection.get("byte_length"):
        raise AgentGraphCliError(
            "malformed candidate evidence already differs",
            code="malformed_candidate_collision",
        )
    return raw


def _raise_active_host_quarantine(
    directory: Path, attempt_id: str, attempt: Mapping[str, Any]
) -> None:
    if _has_active_result_quarantine(attempt):
        _legacy_malformed_evidence(directory, attempt_id, attempt)
        _raise_result_slot_quarantined(attempt_id, attempt["result_quarantine"])


def _preserve_divergent_result_bytes(directory: Path, raw: bytes) -> str:
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    relative = Path("artifacts") / "result-quarantine" / "sha256" / f"{digest[7:]}.json"
    path = _safe_run_file(directory, relative, "result-slot integrity evidence", allow_missing_parents=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        if _read_regular_file(path, "result-slot integrity evidence") != raw:
            raise AgentGraphCliError(
                "content-addressed result-slot integrity evidence conflicts",
                code="result_slot_integrity",
                details={"observed_digest": digest},
            )
    else:
        try:
            with path.open("xb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError:
            if _read_regular_file(path, "result-slot integrity evidence") != raw:
                raise AgentGraphCliError(
                    "content-addressed result-slot integrity evidence conflicts",
                    code="result_slot_integrity",
                    details={"observed_digest": digest},
                )
    return digest


def _verify_reported_result_slot(
    directory: Path, attempt_id: str, attempt: Mapping[str, Any]
) -> None:
    report = attempt.get("report")
    if not isinstance(report, Mapping):
        return
    accepted_digest = report.get("result_digest")
    if not isinstance(accepted_digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", accepted_digest):
        return
    receipt_path = report.get("receipt_path")
    if not isinstance(receipt_path, str) or not receipt_path:
        return
    result_path = _safe_run_file(
        directory, Path("results") / f"{require_identifier(attempt_id, 'attempt_id')}.json", "result slot"
    )
    try:
        raw = _read_regular_file(result_path, "result slot")
    except AgentGraphCliError as error:
        if error.code != "candidate_missing":
            raise
        raise AgentGraphCliError(
            f"reported result slot is missing for {attempt_id}",
            code="result_slot_integrity",
            details={
                "attempt_id": attempt_id,
                "accepted_receipt": receipt_path,
                "accepted_digest": accepted_digest,
                "observed_digest": "missing",
            },
        ) from error
    observed_digest = _preserve_divergent_result_bytes(directory, raw) if (
        "sha256:" + hashlib.sha256(raw).hexdigest()
    ) != accepted_digest else accepted_digest
    if observed_digest == accepted_digest:
        return
    raise AgentGraphCliError(
        f"reported result slot diverged for {attempt_id}",
        code="result_slot_integrity",
        details={
            "attempt_id": attempt_id,
            "accepted_receipt": receipt_path,
            "accepted_digest": accepted_digest,
            "observed_digest": observed_digest,
        },
    )


def _quarantine_receipt_matches(receipt: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    return dict(receipt) == dict(expected)


def _recoverable_quarantine_receipt(
    receipt: Mapping[str, Any],
    *,
    task_id: str,
    attempt_id: str,
    idempotency_key: str,
    expected_original: str,
    expected_receipt_path: str,
    generation: int,
    revision: int,
) -> dict[str, Any]:
    """Validate an unjournaled durable receipt before recovering its event."""

    sha256 = receipt.get("sha256")
    byte_length = receipt.get("byte_length")
    validation_error_code = receipt.get("validation_error_code")
    if (
        not isinstance(sha256, str)
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", sha256)
        or not isinstance(byte_length, int)
        or isinstance(byte_length, bool)
        or byte_length < 1
        or not isinstance(validation_error_code, str)
        or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", validation_error_code)
    ):
        raise AgentGraphCliError("quarantine receipt is malformed", code="receipt_collision")
    receipt_generation = receipt.get("generation")
    receipt_revision = receipt.get("revision")
    if (
        not isinstance(receipt_generation, int)
        or isinstance(receipt_generation, bool)
        or receipt_generation < 1
        or receipt_generation > generation
        or not isinstance(receipt_revision, int)
        or isinstance(receipt_revision, bool)
        or receipt_revision < 1
        or receipt_revision > revision
    ):
        raise AgentGraphCliError("quarantine receipt issuance metadata is invalid", code="receipt_collision")
    expected = {
        "task_id": task_id,
        "attempt_id": attempt_id,
        "idempotency_key": idempotency_key,
        "original_path": expected_original,
        "quarantine_path": (
            f"{expected_original.rsplit('/results/', 1)[0]}/artifacts/result-quarantine/"
            f"sha256/{sha256.removeprefix('sha256:')}.json"
        ),
        "sha256": sha256,
        "byte_length": byte_length,
        "validation_error_code": validation_error_code,
        "generation": receipt_generation,
        "revision": receipt_revision,
        "receipt_path": expected_receipt_path,
    }
    if not _quarantine_receipt_matches(receipt, expected):
        raise AgentGraphCliError("quarantine receipt collides", code="receipt_collision")
    return expected


def _verify_saved_quarantine_artifacts(
    directory: Path,
    run_relative: str,
    receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Confirm durable evidence before an idempotent replay can remove a candidate."""

    idempotency_key = receipt.get("idempotency_key")
    sha256 = receipt.get("sha256")
    byte_length = receipt.get("byte_length")
    if (
        not isinstance(idempotency_key, str)
        or not re.fullmatch(r"[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*", idempotency_key)
        or not isinstance(sha256, str)
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", sha256)
        or not isinstance(byte_length, int)
        or isinstance(byte_length, bool)
        or byte_length < 1
    ):
        raise AgentGraphCliError("saved quarantine receipt is invalid", code="receipt_collision")
    receipt_relative = Path("artifacts") / "result-quarantine" / "receipts" / f"{idempotency_key}.json"
    expected_receipt_path = f"{run_relative}/{receipt_relative.as_posix()}"
    if receipt.get("receipt_path") != expected_receipt_path:
        raise AgentGraphCliError("saved quarantine receipt path is invalid", code="receipt_collision")
    receipt_path = _safe_run_file(directory, receipt_relative, "quarantine receipt")
    if not receipt_path.exists() and not receipt_path.is_symlink():
        raise AgentGraphCliError("quarantine receipt is missing", code="receipt_missing")
    _read_regular_file(receipt_path, "quarantine receipt")
    if not _quarantine_receipt_matches(load_json_object(receipt_path, "quarantine receipt"), receipt):
        raise AgentGraphCliError("quarantine receipt differs from the journal", code="receipt_collision")
    evidence_relative = Path("artifacts") / "result-quarantine" / "sha256" / f"{sha256[7:]}.json"
    expected_evidence_path = f"{run_relative}/{evidence_relative.as_posix()}"
    if receipt.get("quarantine_path") != expected_evidence_path:
        raise AgentGraphCliError("saved quarantine evidence path is invalid", code="receipt_collision")
    evidence_path = _safe_run_file(directory, evidence_relative, "quarantine evidence")
    if not evidence_path.exists() and not evidence_path.is_symlink():
        raise AgentGraphCliError("quarantine evidence is missing", code="quarantine_evidence_missing")
    evidence = _read_regular_file(evidence_path, "quarantine evidence")
    if len(evidence) != byte_length or "sha256:" + hashlib.sha256(evidence).hexdigest() != sha256:
        raise AgentGraphCliError("quarantine evidence conflicts with its receipt", code="quarantine_collision")
    return dict(receipt)


def _canonical_quarantine_idempotency_key(
    raw: bytes | None, attempt_id: str, supplied_key: str
) -> str:
    """Bind Orca quarantine receipts to the completion's own identities."""

    supplied_key = require_identifier(supplied_key, "idempotency_key")
    if raw is None:
        return supplied_key
    try:
        candidate = _json_mapping(raw.decode("utf-8"))
    except UnicodeDecodeError:
        return supplied_key
    refs = candidate.get("external_refs")
    if not isinstance(refs, Mapping) or refs.get("provider") != "orca":
        return supplied_key
    message_id = refs.get("message_id")
    delivery_id = refs.get("delivery_id")
    if not isinstance(message_id, str) or not message_id or not isinstance(delivery_id, str) or not delivery_id:
        return supplied_key
    canonical_key = _orca_quarantine_idempotency_key(
        attempt_id, message_id, delivery_id
    )
    if supplied_key != canonical_key:
        raise AgentGraphCliError(
            "quarantine idempotency key does not match the canonical delivery identity",
            code="quarantine_identity_mismatch",
        )
    return canonical_key


def command_quarantine_result(arguments: argparse.Namespace) -> dict[str, Any]:
    """Fence and preserve one invalid canonical worker-result candidate."""

    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    projection = journal.verify_projection()
    _verify_workspace_binding(arguments.repo, directory, projection)
    generation = _generation(arguments, projection)
    task_id = require_identifier(arguments.task, "task")
    attempt_id = require_identifier(arguments.attempt, "attempt")
    attempt = projection["attempts"].get(attempt_id)
    if not isinstance(attempt, Mapping):
        raise AgentGraphCliError(f"unknown attempt: {attempt_id}", code="unknown_attempt")
    if attempt.get("task_id") != task_id:
        raise AgentGraphCliError("quarantine task does not match the attempt", code="attempt_task_mismatch")
    if attempt.get("status") != "running":
        raise AgentGraphCliError("quarantine requires a running attempt", code="attempt_not_running")
    task = _task_from_state(projection, task_id)
    scope = attempt.get("effective_scope")
    if scope != effective_attempt_scope(task, attempt_id, projection):
        raise AgentGraphCliError("attempt effective scope digest drift", code="scope_drift")
    effective_task = _task_for_effective_scope(task, scope)
    run_relative = directory.relative_to(arguments.repo).as_posix()
    expected_original = f"{run_relative}/results/{attempt_id}.json"
    if arguments.candidate != expected_original:
        raise AgentGraphCliError("candidate is not the canonical result path", code="candidate_path_mismatch")
    candidate_path = _safe_run_file(directory, Path("results") / f"{attempt_id}.json", "candidate")
    raw = _read_regular_file(candidate_path, "candidate") if candidate_path.exists() or candidate_path.is_symlink() else None
    idempotency_key = _canonical_quarantine_idempotency_key(
        raw, attempt_id, arguments.idempotency_key
    )
    receipt_relative = Path("artifacts") / "result-quarantine" / "receipts" / f"{idempotency_key}.json"
    receipt_path = _safe_run_file(
        directory, receipt_relative, "quarantine receipt", allow_missing_parents=True
    )
    expected_receipt_path = f"{run_relative}/{receipt_relative.as_posix()}"
    existing_receipt = None
    if receipt_path.exists() or receipt_path.is_symlink():
        _read_regular_file(receipt_path, "quarantine receipt")
        existing_receipt = load_json_object(receipt_path, "quarantine receipt")
    saved = attempt.get("result_quarantine")
    if saved is not None and not isinstance(saved, Mapping):
        raise AgentGraphCliError("saved quarantine receipt is invalid", code="receipt_collision")
    if isinstance(saved, Mapping):
        saved = _verify_saved_quarantine_artifacts(directory, run_relative, saved)
    if raw is not None and _candidate_validation_error(raw, effective_task, attempt_id) is None:
        raise AgentGraphCliError("candidate is a valid worker result", code="candidate_not_malformed")
    if saved is not None:
        if saved.get("idempotency_key") != idempotency_key:
            raise AgentGraphCliError("attempt already has a different quarantine receipt", code="receipt_collision")
        if raw is not None and saved.get("sha256") != "sha256:" + hashlib.sha256(raw).hexdigest():
            raise AgentGraphCliError("candidate bytes conflict with the durable receipt", code="quarantine_collision")
        if raw is not None:
            candidate_path.unlink()
        return {"attempt_id": attempt_id, "quarantined": True, "idempotent": True, "receipt": dict(saved), "state": projection}
    if existing_receipt is not None:
        receipt = _recoverable_quarantine_receipt(
            existing_receipt,
            task_id=task_id,
            attempt_id=attempt_id,
            idempotency_key=idempotency_key,
            expected_original=expected_original,
            expected_receipt_path=expected_receipt_path,
            generation=generation,
            revision=projection["last_sequence"] + 1,
        )
        quarantine_path = _safe_run_file(
            directory,
            Path("artifacts") / "result-quarantine" / "sha256" / f"{receipt['sha256'][7:]}.json",
            "quarantine evidence",
        )
        preserved = _read_regular_file(quarantine_path, "quarantine evidence")
        if len(preserved) != receipt["byte_length"] or "sha256:" + hashlib.sha256(preserved).hexdigest() != receipt["sha256"]:
            raise AgentGraphCliError("quarantine evidence conflicts with its receipt", code="quarantine_collision")
        if raw is not None:
            if "sha256:" + hashlib.sha256(raw).hexdigest() != receipt["sha256"]:
                raise AgentGraphCliError("candidate bytes conflict with the durable receipt", code="quarantine_collision")
            candidate_path.unlink()
        projection = journal.append(
            "attempt_result_quarantined", receipt, coordinator_generation=generation
        )
        return {"attempt_id": attempt_id, "quarantined": True, "idempotent": True, "recovered": True, "receipt": receipt, "state": projection}
    if raw is None:
        raise AgentGraphCliError("candidate is missing", code="candidate_missing")
    validation_error_code = _candidate_validation_error(raw, effective_task, attempt_id)
    if validation_error_code is None:
        raise AgentGraphCliError("candidate is a valid worker result", code="candidate_not_malformed")
    sha256 = "sha256:" + hashlib.sha256(raw).hexdigest()
    quarantine_relative = Path("artifacts") / "result-quarantine" / "sha256" / f"{sha256.removeprefix('sha256:')}.json"
    quarantine_path = _safe_run_file(
        directory, quarantine_relative, "quarantine", allow_missing_parents=True
    )
    receipt = {
        "task_id": task_id,
        "attempt_id": attempt_id,
        "idempotency_key": idempotency_key,
        "original_path": expected_original,
        "quarantine_path": f"{run_relative}/{quarantine_relative.as_posix()}",
        "sha256": sha256,
        "byte_length": len(raw),
        "validation_error_code": validation_error_code,
        "generation": generation,
        "revision": projection["last_sequence"] + 1,
        "receipt_path": expected_receipt_path,
    }
    quarantine_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    for parent, context in ((quarantine_path.parent, "quarantine"), (receipt_path.parent, "quarantine receipt")):
        if stat.S_ISLNK(parent.lstat().st_mode):
            raise AgentGraphCliError(f"{context} parent is unsafe", code="quarantine_path_unsafe")
    if quarantine_path.exists() or quarantine_path.is_symlink():
        preserved = _read_regular_file(quarantine_path, "quarantine evidence")
        if preserved != raw:
            raise AgentGraphCliError("content-addressed quarantine path collides", code="quarantine_collision")
        candidate_path.unlink()
    else:
        try:
            os.replace(candidate_path, quarantine_path)
        except OSError as error:
            raise AgentGraphCliError(f"cannot relocate candidate: {error}", code="quarantine_relocation_failed") from error
    if not receipt_path.exists():
        atomic_write_json(receipt_path, receipt)
    projection = journal.append(
        "attempt_result_quarantined",
        receipt,
        coordinator_generation=generation,
    )
    return {"attempt_id": attempt_id, "quarantined": True, "idempotent": False, "receipt": receipt, "state": projection}


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
    try:
        context = persisted_driver_context(attempt)
    except DriverError as error:
        raise AgentGraphCliError(str(error), code=error.code) from error
    refs = context["external_refs"]
    terminal = refs.get("terminal")
    result = {
        **attempt,
        **context,
        "attempt_id": attempt_id,
        "task": task.to_dict(),
        "dispatch_id": refs.get("dispatch_id"),
        "external_task_id": refs.get("task_id"),
        "terminal_handle": terminal.get("handle") if isinstance(terminal, Mapping) else None,
        "run_id": refs.get("run_id"),
    }
    return result


def _preserve_malformed_host_result(
    repository: Path,
    directory: Path,
    journal: EventJournal,
    projection: dict[str, Any],
    generation: int,
    attempt_id: str,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Quarantine an invalid host result before any lifecycle reconciliation."""

    attempt = projection["attempts"].get(attempt_id)
    if not isinstance(attempt, Mapping) or attempt.get("status") != "running":
        return projection, None
    _legacy_malformed_evidence(directory, attempt_id, attempt)
    saved_quarantine = attempt.get("result_quarantine")
    if isinstance(saved_quarantine, Mapping):
        return projection, dict(saved_quarantine)
    task = _task_from_state(projection, str(attempt["task_id"]))
    effective_scope = attempt.get("effective_scope")
    if not isinstance(effective_scope, Mapping) or not isinstance(effective_scope.get("paths"), list):
        raise AgentGraphCliError("attempt is missing its immutable effective scope", code="scope_drift")
    task = _task_for_effective_scope(task, effective_scope)
    result_path = _safe_run_file(
        directory,
        Path("results") / f"{require_identifier(attempt_id, 'attempt_id')}.json",
        "candidate",
    )
    legacy_path = _safe_run_file(
        directory,
        Path("artifacts") / "malformed-provider-results" / f"{attempt_id}.json",
        "malformed candidate evidence",
        allow_missing_parents=True,
    )
    raw = _read_regular_file(result_path, "candidate") if (result_path.exists() or result_path.is_symlink()) else None
    legacy_raw = _read_regular_file(legacy_path, "malformed candidate evidence") if (legacy_path.exists() or legacy_path.is_symlink()) else None
    if raw is not None and legacy_raw is not None and raw != legacy_raw:
        raise AgentGraphCliError(
            "malformed candidate evidence already differs",
            code="malformed_candidate_collision",
        )
    raw = raw or legacy_raw
    if raw is None:
        return projection, None
    if _candidate_validation_error(raw, task, attempt_id) is None:
        return projection, None
    if legacy_raw is None:
        legacy_path.parent.mkdir(parents=True, exist_ok=True)
        if stat.S_ISLNK(legacy_path.parent.lstat().st_mode):
            raise AgentGraphCliError(
                "malformed candidate evidence parent is unsafe",
                code="quarantine_path_unsafe",
            )
        try:
            with legacy_path.open("xb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError:
            if _read_regular_file(legacy_path, "malformed candidate evidence") != raw:
                raise AgentGraphCliError(
                    "malformed candidate evidence already differs",
                    code="malformed_candidate_collision",
                )
        legacy_raw = raw
    if not result_path.exists():
        try:
            with result_path.open("xb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError:
            if _read_regular_file(result_path, "candidate") != raw:
                raise AgentGraphCliError(
                    "malformed candidate evidence already differs",
                    code="malformed_candidate_collision",
                )
    run_relative = directory.relative_to(repository).as_posix()
    quarantined = command_quarantine_result(
        argparse.Namespace(
            repo=repository,
            change=projection["change"],
            run_id=projection["run_id"],
            generation=generation,
            task=task.id,
            attempt=attempt_id,
            candidate=f"{run_relative}/results/{attempt_id}.json",
            idempotency_key=f"host-result-{attempt_id}",
        )
    )
    projection = journal.verify_projection()
    if projection != quarantined["state"]:
        raise AgentGraphCliError(
            "quarantine projection differs from journal replay",
            code="result_slot_integrity",
        )
    attempt = projection["attempts"][attempt_id]
    if legacy_raw is not None and attempt.get("provider_result_rejection") is None:
        evidence_ref = (
            f"file:{directory.relative_to(repository).as_posix()}/artifacts/"
            f"malformed-provider-results/{attempt_id}.json"
        )
        projection = journal.append(
            "attempt_provider_result_rejected",
            {
                "task_id": task.id,
                "attempt_id": attempt_id,
                "candidate": {
                    "evidence_ref": evidence_ref,
                    "sha256": "sha256:" + hashlib.sha256(legacy_raw).hexdigest(),
                    "byte_length": len(legacy_raw),
                    "reason": "malformed provider result candidate",
                },
            },
            coordinator_generation=generation,
        )
    return projection, quarantined["receipt"]


def _reconcile_rejected_host_attempt(
    repository: Path,
    directory: Path,
    journal: EventJournal,
    projection: dict[str, Any],
    generation: int,
    attempt_id: str,
    driver: HostDriver,
    malformed_candidate: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Reconcile a quarantined result before an otherwise-safe abandonment."""

    attempt = projection["attempts"][attempt_id]
    pending_cleanup = pending_cleanup_ids_for_attempt(projection, attempt_id)
    if pending_cleanup:
        return projection, {
            "attempt_id": attempt_id,
            "malformed_candidate": dict(malformed_candidate),
            "cleanup_pending": pending_cleanup,
        }
    task = _task_from_state(projection, str(attempt["task_id"]))
    driver_attempt = _driver_attempt(attempt, attempt_id, task)
    reconciled = driver.reconcile([driver_attempt])
    reconcile_id, reconcile_path = _driver_receipt(repository, directory, reconciled)
    released = driver.release(driver_attempt)
    release_id, release_path = _driver_receipt(repository, directory, released)
    projection = journal.append(
        "attempt_abandoned",
        {
            "attempt_id": attempt_id,
            "task_id": task.id,
            "reason": "malformed provider result candidate",
            "malformed_candidate": dict(malformed_candidate),
            "reconciliation": {
                "receipt_id": reconcile_id,
                "receipt_path": reconcile_path,
            },
            "cleanup_receipt": {
                "receipt_id": release_id,
                "receipt_path": release_path,
            },
        },
        coordinator_generation=generation,
    )
    return projection, {
        "attempt_id": attempt_id,
        "malformed_candidate": dict(malformed_candidate),
        "abandoned": True,
    }


def _provider_worker_result_candidate(
    message: Mapping[str, Any],
    task: TaskContract,
    attempt_id: str,
    attempt: Mapping[str, Any] | None = None,
    *,
    delivery_id: str | None = None,
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
    # The immutable worker completion payload is the result source. Do not
    # merge it with transport-envelope fields from a different delivery.
    files = payload.get("filesModified") or payload.get("files_modified") or []
    if isinstance(files, str):
        files = [item.strip() for item in files.split(",") if item.strip()]
    if not isinstance(files, list):
        files = []
    checks = payload.get("checksRun") or payload.get("checks_run") or []
    if isinstance(checks, str):
        checks = [checks]
    if not isinstance(checks, list):
        checks = []
    message_id = str(message.get("messageId") or message.get("message_id") or message.get("id") or "")
    external_refs: dict[str, str | None] = {
        "provider": "orca",
        "message_id": message_id,
        "task_id": payload.get("taskId") or payload.get("task_id"),
        "dispatch_id": payload.get("dispatchId") or payload.get("dispatch_id"),
        "provider_outcome": message.get("outcome") or payload.get("outcome"),
    }
    if delivery_id is not None:
        external_refs["delivery_id"] = delivery_id
    return {
        "task_id": task.id,
        "attempt_id": attempt_id,
        "outcome": "reported",
        "summary": str(message.get("body") or message.get("subject") or "Orca worker completed."),
        "files_changed": files,
        "checks_run": checks,
        "evidence_refs": [],
        "questions": [],
        "external_refs": external_refs,
    }


def _provider_worker_result(
    message: Mapping[str, Any],
    task: TaskContract,
    attempt_id: str,
    attempt: Mapping[str, Any] | None = None,
    *,
    delivery_id: str | None = None,
) -> dict[str, Any]:
    candidate = _provider_worker_result_candidate(
        message,
        task,
        attempt_id,
        attempt,
        delivery_id=delivery_id,
    )
    return validate_worker_result(candidate, task, attempt_id)


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
    cleanup_id: str | None = None,
    *,
    allow_running: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    attempt = projection["attempts"].get(attempt_id)
    if not isinstance(attempt, Mapping):
        raise AgentGraphCliError(f"unknown attempt: {attempt_id}", code="unknown_attempt")
    cleanup_id = cleanup_id or attempt.get("cleanup_id")
    cleanup = projection["cleanup"].get(cleanup_id) if cleanup_id else None
    if not isinstance(cleanup, Mapping):
        raise AgentGraphCliError(
            f"attempt has no driver-owned cleanup: {attempt_id}",
            code="cleanup_not_owned",
        )
    owner = cleanup.get("owner")
    if not isinstance(owner, Mapping) or owner.get("attempt_id") != attempt_id:
        raise AgentGraphCliError(
            f"cleanup owner does not match attempt: {attempt_id}",
            code="cleanup_owner_mismatch",
        )
    if cleanup_is_terminal(cleanup):
        return projection, {
            "attempt_id": attempt_id,
            "cleanup_id": cleanup_id,
            "finished": True,
            "idempotent": True,
        }
    failed_owned_attempt = (
        attempt.get("status") == "interrupted"
        and attempt.get("post_start_unresolved") is True
    )
    cleanup_eligible = {"reported", "audit-rejected"}
    if allow_running:
        cleanup_eligible.add("running")
    if attempt.get("status") not in cleanup_eligible and not failed_owned_attempt:
        raise AgentGraphCliError(
            "driver cleanup recovery requires a reported or audit-rejected attempt, "
            f"got {attempt.get('status')}",
            code="cleanup_not_recoverable",
        )
    cleanup_refs = cleanup.get("external_refs")
    if not isinstance(cleanup_refs, Mapping):
        raise AgentGraphCliError("cleanup lacks immutable authoritative external references", code="cleanup_unproven")
    task = _task_from_state(projection, attempt["task_id"])
    release_attempt = _driver_attempt(attempt, attempt_id, task)
    terminal = cleanup_refs.get("terminal")
    release_attempt.update(
        {
            "external_refs": json.loads(json.dumps(dict(cleanup_refs), sort_keys=True)),
            "dispatch_id": cleanup_refs.get("dispatch_id"),
            "external_task_id": cleanup_refs.get("task_id"),
            "terminal_handle": (
                terminal.get("handle") if isinstance(terminal, Mapping) else None
            ),
            "run_id": cleanup_refs.get("run_id"),
        }
    )
    release_attempt["resource_owner"] = dict(owner)
    expected_ids = {
        "dispatch_id": cleanup_refs.get("dispatch_id"),
        "external_task_id": cleanup_refs.get("task_id"),
        "run_id": cleanup_refs.get("run_id"),
    }
    expected_ids["terminal_handle"] = terminal.get("handle") if isinstance(terminal, Mapping) else None
    if any(release_attempt.get(field) != value for field, value in expected_ids.items()):
        raise AgentGraphCliError("cleanup release identity diverges from its selected references", code="cleanup_unproven")
    try:
        released = driver.release(release_attempt)
    except DriverError as error:
        projection = journal.append(
            "cleanup_unverifiable",
            {
                "cleanup_id": cleanup_id,
                "receipt": {"reason": error.code, "driver_receipt": error.receipt},
            },
            coordinator_generation=generation,
        )
        return projection, {
            "attempt_id": attempt_id,
            "cleanup_id": cleanup_id,
            "finished": False,
            "outcome": "unverifiable",
        }
    receipt_id, receipt_path = _driver_receipt(repository, directory, released)
    release_refs = released.external_refs if isinstance(released.external_refs, Mapping) else {}
    if owner.get("terminal_id") is None:
        start_refs = cleanup_refs
        dispatch_id = start_refs.get("dispatch_id")
        runtime_id = start_refs.get("runtime_id")
        worktree_id = start_refs.get("worktree_id")
        run_id = start_refs.get("run_id")
        release_state = _supervised_release_state(released)
        authoritative = (
            release_refs.get("tier") == "supervised"
            and release_refs.get("dispatch_id") == dispatch_id == cleanup.get("target")
            and isinstance(dispatch_id, str)
            and all(isinstance(value, str) and value for value in (runtime_id, worktree_id, run_id))
            and all(
                getattr(driver, attribute, None) == value
                for attribute, value in (("runtime_id", runtime_id), ("run_id", run_id))
            )
            and owner.get("provenance") == f"orca-supervised:{runtime_id}:{worktree_id}:{run_id}:{dispatch_id}"
            and release_state in {"released", "already_released"}
        )
    else:
        release_owner = (
            _resource_owner_from_receipt(release_refs, attempt_id, attempt["workspace_scope"])
            if release_refs.get("tier") == "tracked-terminal" and isinstance(attempt.get("workspace_scope"), Mapping)
            else None
        )
        authoritative = release_owner == owner
    receipt = {
        "receipt_id": receipt_id,
        "receipt_path": receipt_path,
        "driver": released.to_dict(),
    }
    if not authoritative:
        projection = journal.append(
            "cleanup_unverifiable",
            {"cleanup_id": cleanup_id, "receipt": receipt},
            coordinator_generation=generation,
        )
        return projection, {
            "attempt_id": attempt_id,
            "cleanup_id": cleanup_id,
            "finished": False,
            "outcome": "unverifiable",
            "receipt_id": receipt_id,
            "receipt_path": receipt_path,
        }
    terminal_receipt = (
        {
            "kind": "provider-dispatch",
            "owner": owner,
            "dispatch_id": cleanup["target"],
            "runtime_id": start_refs["runtime_id"],
            "worktree_id": start_refs["worktree_id"],
            "run_id": start_refs["run_id"],
            "status": _supervised_release_state(released),
        }
        if owner["terminal_id"] is None
        else {
            "kind": "terminal",
            "owner": owner,
            "terminal_id": owner["terminal_id"],
            "incarnation_id": owner["incarnation_id"],
            "status": "verified",
        }
    )
    projection = journal.append(
        "cleanup_finished",
        {
            "cleanup_id": cleanup_id,
            "receipt": terminal_receipt,
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


def _release_reduction_surplus(
    repository: Path,
    directory: Path,
    journal: EventJournal,
    projection: dict[str, Any],
    generation: int,
    reduction: Mapping[str, Any],
) -> tuple[dict[str, list[dict[str, str]]], dict[str, Any]]:
    """Release only active owners excluded by an already-recorded reduction."""

    retained = set(reduction.get("retained_task_ids", []))
    active = [
        (attempt_id, attempt)
        for attempt_id, attempt in projection["attempts"].items()
        if isinstance(attempt, Mapping)
        and attempt.get("status") in {"reserved", "running", "interrupted"}
        and attempt.get("task_id") not in retained
    ]
    released: list[dict[str, str]] = []
    pending: list[dict[str, str]] = []
    driver: HostDriver | OrcaDriver | None = None
    for attempt_id, attempt in active:
        task_id = str(attempt["task_id"])
        cleanup_id = attempt.get("cleanup_id")
        if not isinstance(cleanup_id, str):
            pending.append({"attempt_id": attempt_id, "task_id": task_id, "status": "cleanup_pending"})
            continue
        if driver is None:
            try:
                driver = _driver_for_state(repository, directory, projection)
            except AgentGraphCliError:
                pending.append({"attempt_id": attempt_id, "task_id": task_id, "status": "cleanup_pending"})
                continue
        try:
            projection, outcome = _finish_driver_cleanup(
                repository,
                directory,
                journal,
                projection,
                generation,
                attempt_id,
                driver,
                cleanup_id,
                allow_running=True,
            )
        except AgentGraphCliError:
            pending.append({"attempt_id": attempt_id, "task_id": task_id, "status": "cleanup_pending"})
            continue
        if outcome.get("finished") is not True:
            pending.append({"attempt_id": attempt_id, "task_id": task_id, "status": "cleanup_pending"})
            continue
        projection = journal.append(
            "attempt_abandoned",
            {
                "attempt_id": attempt_id,
                "task_id": task_id,
                "reason": "single_writer reduction released this surplus owner",
                "cleanup_receipt": {
                    key: outcome[key]
                    for key in ("receipt_id", "receipt_path")
                    if key in outcome
                },
            },
            coordinator_generation=generation,
        )
        released.append({"attempt_id": attempt_id, "task_id": task_id, "status": "abandoned"})
    return {
        "released": released[:WATCH_MAX_DELTAS],
        "pending": pending[:WATCH_MAX_DELTAS],
    }, projection


def command_sync(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    projection = journal.verify_projection()
    generation = _generation(arguments, projection)
    for attempt_id, attempt in projection["attempts"].items():
        if not isinstance(attempt, Mapping):
            continue
        if attempt.get("status") not in {"running", "reported", "audit-rejected", "interrupted"}:
            continue
        _driver_attempt(attempt, attempt_id, _task_from_state(projection, attempt["task_id"]))
    driver = _driver_for_state(arguments.repo, directory, projection)
    if isinstance(driver, HostDriver):
        for attempt_id, attempt in projection["attempts"].items():
            if not isinstance(attempt, Mapping):
                continue
            _raise_active_host_quarantine(directory, attempt_id, attempt)
            if attempt.get("status") == "reported":
                _verify_reported_result_slot(directory, attempt_id, attempt)
    observed: list[dict[str, Any]] = []
    for attempt_id, attempt in list(projection["attempts"].items()):
        if not isinstance(attempt, Mapping):
            continue
        failed_owned_attempt = (
            attempt.get("status") == "interrupted"
            and attempt.get("post_start_unresolved") is True
        )
        if attempt.get("status") not in {"reported", "audit-rejected"} and not failed_owned_attempt:
            continue
        cleanup_ids = pending_cleanup_ids_for_attempt(projection, attempt_id)
        primary_cleanup_id = attempt.get("cleanup_id")
        secondary_cleanup_ids = [
            cleanup_id for cleanup_id in cleanup_ids if cleanup_id != primary_cleanup_id
        ]
        if secondary_cleanup_ids:
            observed.append({
                "attempt_id": attempt_id,
                "cleanup_pending": secondary_cleanup_ids,
            })
            continue
        for cleanup_id in cleanup_ids:
            projection, recovered = _finish_driver_cleanup(
                arguments.repo,
                directory,
                journal,
                projection,
                generation,
                attempt_id,
                driver,
                cleanup_id,
            )
            observed.append({"cleanup_recovery": recovered})
    running: list[tuple[str, Mapping[str, Any], TaskContract, dict[str, Any]]] = []
    for attempt_id, attempt in list(projection["attempts"].items()):
        if attempt.get("status") != "running":
            continue
        task = _task_from_state(projection, attempt["task_id"])
        poll_attempt = _driver_attempt(attempt, attempt_id, task)
        running.append((attempt_id, attempt, task, poll_attempt))
        if isinstance(driver, HostDriver):
            projection, malformed_candidate = _preserve_malformed_host_result(
                arguments.repo,
                directory,
                journal,
                projection,
                generation,
                attempt_id,
            )
            if malformed_candidate is not None:
                projection, reconciled = _reconcile_rejected_host_attempt(
                    arguments.repo,
                    directory,
                    journal,
                    projection,
                    generation,
                    attempt_id,
                    driver,
                    malformed_candidate,
                )
                observed.append({"malformed_result_reconciliation": reconciled})
                continue
        try:
            if isinstance(driver, OrcaDriver):
                receipt = driver.poll(
                    poll_attempt,
                    cursor=attempt.get("cursor"),
                    include_delivery=False,
                )
            else:
                receipt = driver.poll(poll_attempt, cursor=attempt.get("cursor"))
        except DriverError:
            if not isinstance(driver, HostDriver):
                raise
            projection, malformed_candidate = _preserve_malformed_host_result(
                arguments.repo,
                directory,
                journal,
                projection,
                generation,
                attempt_id,
            )
            if malformed_candidate is None:
                raise
            projection, reconciled = _reconcile_rejected_host_attempt(
                arguments.repo,
                directory,
                journal,
                projection,
                generation,
                attempt_id,
                driver,
                malformed_candidate,
            )
            observed.append({"malformed_result_reconciliation": reconciled})
            continue
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
        quarantine_required = False
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
                message_id = str(
                    item.get("messageId") or item.get("message_id") or item.get("id") or ""
                )
                if not message_id or not delivery_id:
                    raise AgentGraphCliError(
                        "Orca completion omitted its message or delivery identity",
                        code="provider_identity_missing",
                    )
                quarantine_key = _orca_quarantine_idempotency_key(
                    attempt_id, message_id, delivery_id
                )
                # An explicitly acknowledged, abandoned predecessor can still
                # be included in a later delivery. It is historical evidence,
                # not a fence on a valid successor in this sync.
                if attempt.get("status") == "abandoned":
                    continue
                saved_quarantine = attempt.get("result_quarantine")
                if isinstance(saved_quarantine, Mapping):
                    if saved_quarantine.get("idempotency_key") != quarantine_key:
                        raise AgentGraphCliError(
                            "Orca quarantined completion identity does not match its delivery",
                            code="provider_delivery_identity_mismatch",
                        )
                    continue
                if attempt.get("status") in {"reported", "audit-rejected"}:
                    continue
                if attempt.get("status") != "running":
                    raise AgentGraphCliError(
                        f"Orca completion targets attempt in {attempt.get('status')}",
                        code="provider_state_mismatch",
                    )
                candidate = _provider_worker_result_candidate(
                    item,
                    task,
                    attempt_id,
                    poll_attempt,
                    delivery_id=delivery_id,
                )
                candidate_bytes = _canonical_worker_result_bytes(candidate)
                validation_error_code = _candidate_validation_error(
                    candidate_bytes, task, attempt_id
                )
                if validation_error_code is not None:
                    candidate_path = _materialize_write_once_result_candidate(
                        directory, attempt_id, candidate_bytes
                    )
                    digest = f"sha256:{hashlib.sha256(candidate_bytes).hexdigest()}"
                    observed.append(
                        {
                            "quarantine_required": {
                                "task_id": task.id,
                                "attempt_id": attempt_id,
                                "message_id": message_id,
                                "delivery_id": delivery_id,
                                "candidate_path": (
                                    directory.relative_to(arguments.repo).as_posix()
                                    + "/"
                                    + candidate_path.relative_to(directory).as_posix()
                                ),
                                "sha256": digest,
                                "byte_length": len(candidate_bytes),
                                "validation_error_code": validation_error_code,
                                "idempotency_key": quarantine_key,
                            }
                        }
                    )
                    quarantine_required = True
                    continue
                result = validate_worker_result(candidate, task, attempt_id)
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
                cleanup_id = attempt.get("cleanup_id")
                cleanup = projection["cleanup"].get(cleanup_id) if cleanup_id else None
                if isinstance(cleanup, Mapping) and cleanup.get("status") == "pending":
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
        delivery_observation = {
            "delivery_id": delivery_id,
            "receipt_id": delivery_receipt_id,
            "receipt_path": delivery_receipt_path,
        }
        for item in observed:
            quarantine = item.get("quarantine_required") if isinstance(item, Mapping) else None
            if not isinstance(quarantine, Mapping):
                continue
            quarantined = command_quarantine_result(
                argparse.Namespace(
                    repo=arguments.repo,
                    change=projection["change"],
                    run_id=projection["run_id"],
                    generation=generation,
                    task=quarantine["task_id"],
                    attempt=quarantine["attempt_id"],
                    candidate=quarantine["candidate_path"],
                    idempotency_key=quarantine["idempotency_key"],
                )
            )
            projection = journal.verify_projection()
            item["quarantine"] = quarantined["receipt"]
        if delivery_id and not has_open_question and not quarantine_required:
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
    attempt = projection["attempts"].get(arguments.attempt)
    if not isinstance(attempt, Mapping):
        raise AgentGraphCliError(f"unknown attempt: {arguments.attempt}", code="unknown_attempt")
    requested_cleanup = getattr(arguments, "cleanup_id", None)
    owned_pending = [
        cleanup_id
        for cleanup_id, cleanup in projection["cleanup"].items()
        if isinstance(cleanup_id, str)
        and isinstance(cleanup, Mapping)
        and isinstance(cleanup.get("owner"), Mapping)
        and cleanup["owner"].get("attempt_id") == arguments.attempt
        and not cleanup_is_terminal(cleanup)
    ]
    if requested_cleanup is None:
        if len(owned_pending) != 1:
            raise AgentGraphCliError(
                "recover-cleanup requires --cleanup-id when an attempt has multiple or no pending obligations",
                code="cleanup_ambiguous",
            )
        requested_cleanup = owned_pending[0]
    else:
        requested = projection["cleanup"].get(requested_cleanup)
        if (
            not isinstance(requested, Mapping)
            or not isinstance(requested.get("owner"), Mapping)
            or requested["owner"].get("attempt_id") != arguments.attempt
        ):
            raise AgentGraphCliError("requested cleanup is not an attempt obligation", code="cleanup_not_owned")
    selected_cleanup = projection["cleanup"][requested_cleanup]
    if cleanup_is_terminal(selected_cleanup):
        return {
            "attempt_id": arguments.attempt,
            "cleanup_id": requested_cleanup,
            "finished": True,
            "idempotent": True,
            "state": projection,
        }
    _driver_attempt(
        attempt,
        arguments.attempt,
        _task_from_state(projection, attempt["task_id"]),
    )
    driver = _driver_for_state(arguments.repo, directory, projection)
    projection, recovery = _finish_driver_cleanup(
        arguments.repo,
        directory,
        journal,
        projection,
        generation,
        arguments.attempt,
        driver,
        requested_cleanup,
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


def _check_execution_binding(
    execution: Any, consumer_ref: str
) -> dict[str, Any]:
    """Build the public immutable execution binding from one durable record."""

    return {
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


def command_run_check(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    projection = journal.verify_projection()
    generation = _generation(arguments, projection)
    _require_current_execution_scope(arguments.repo, projection["workspace_scope"])
    task = _task_from_state(projection, arguments.task)
    task_state = projection["tasks"][task.id]
    attempt_ids = task_state["attempt_ids"]
    if not attempt_ids:
        raise AgentGraphCliError(
            "run-check requires a reported worker attempt", code="worker_report_required"
        )
    attempt_id = attempt_ids[-1]
    attempt = projection["attempts"][attempt_id]
    if attempt.get("status") != "reported":
        raise AgentGraphCliError(
            "run-check requires the latest reported worker attempt",
            code="worker_report_required",
        )
    command = task.check
    if command.casefold() == "missing validation evidence":
        raise AgentGraphCliError(
            f"task {task.id} has Check: missing validation evidence; grade it unobserved",
            code="missing_check",
        )
    executable = direct_command_arguments(command)
    consumer_ref = f"attempt:{task.id}:{attempt_id}"

    def record_running(record: Mapping[str, Any]) -> None:
        execution = type("RunningExecution", (), record)()
        journal.append(
            "check_execution_recorded",
            _check_execution_binding(execution, consumer_ref),
            coordinator_generation=generation,
        )

    try:
        execution = run_shared_check(
            executable,
            repository=arguments.repo,
            workspace=arguments.repo,
            run_directory=directory,
            workspace_scope=projection["workspace_scope"],
            base_revision=projection["base_commit"],
            owner_generation=generation,
            timeout_seconds=arguments.timeout,
            output_cap_bytes=arguments.output_cap,
            consumer_ref=consumer_ref,
            on_running=record_running,
        )
    except CheckExecutionError as error:
        raise AgentGraphCliError(str(error), code="check_execution_blocked") from error
    completed = execution.completed
    exit_code = completed.exit_code
    duration_ms = execution.duration_ms
    binding = _check_execution_binding(execution, consumer_ref)
    projection = journal.replay()
    recorded = projection.get("check_executions", {}).get(execution.execution_id)
    if (
        not isinstance(recorded, Mapping)
        or binding["consumer_ref"] not in recorded.get("consumer_refs", [])
        or binding["lifecycle"] != recorded.get("lifecycle")
    ):
        try:
            projection = journal.append("check_execution_recorded", binding, coordinator_generation=generation)
        except StaleRevisionError:
            projection = journal.replay()
            recorded = projection.get("check_executions", {}).get(execution.execution_id)
            if (
                not isinstance(recorded, Mapping)
                or binding["consumer_ref"] not in recorded.get("consumer_refs", [])
                or binding["lifecycle"] != recorded.get("lifecycle")
            ):
                projection = journal.append("check_execution_recorded", binding, coordinator_generation=generation)
    if execution.lifecycle == "blocked" and completed.timed_out:
        try:
            prepared = recover_shared_check(
                repository=arguments.repo,
                run_directory=directory,
                execution_id=execution.execution_id,
            )
            projection = journal.append(
                "check_execution_recovered",
                {
                    "execution_id": prepared.execution_id,
                    "owner_generation": prepared.owner_generation,
                    "lifecycle": prepared.lifecycle,
                    "cleanup_ref": prepared.cleanup_ref,
                    "cleanup_id": prepared.cleanup_id,
                },
                coordinator_generation=generation,
            )
            execution = finalize_shared_check_recovery(
                repository=arguments.repo,
                run_directory=directory,
                prepared=prepared,
            )
            projection = journal.verify_projection()
        except CheckExecutionError as error:
            raise AgentGraphCliError(
                f"{error}; run recover-check-execution --change {projection['change']} "
                f"--run-id {projection['run_id']} --generation {generation} "
                f"--execution-id {execution.execution_id}",
                code="check_execution_blocked",
            ) from error
    task_state = projection["tasks"][task.id]
    saved = task_state.get("check")
    if isinstance(saved, Mapping) and saved.get("attempt_id") == attempt_id and saved.get("execution_id") == execution.execution_id:
        return {"task_id": task.id, "check": dict(saved), "idempotent": True, "state": projection}
    historical_checks = [
        saved_attempt.get("check")
        for saved_attempt in projection["attempts"].values()
        if isinstance(saved_attempt, Mapping)
        and saved_attempt.get("task_id") == task.id
        and isinstance(saved_attempt.get("check"), Mapping)
    ]
    prior_attempts = max(
        (int(check.get("attempts", 0)) for check in historical_checks),
        default=0,
    )
    prior_duration = max(
        (int(check.get("total_duration_ms", 0)) for check in historical_checks),
        default=0,
    )
    attempt_number = prior_attempts + 1
    data = {
        "task_id": task.id,
        "attempt_id": attempt_id,
        "command": command,
        "status": "passed" if exit_code == 0 else "failed",
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "attempts": attempt_number,
        "total_duration_ms": prior_duration + duration_ms,
        "artifact": execution.artifact_ref,
        "timed_out": completed.timed_out,
        "residue_unverifiable": completed.residue_unverifiable,
        "execution_id": execution.execution_id,
        "command_digest": execution.command_digest,
        "source_snapshot_digest": execution.source_snapshot_digest,
        "execution_policy_digest": execution.execution_policy_digest,
        "timeout_seconds": execution.timeout_seconds,
        "output_cap_bytes": execution.output_cap_bytes,
        "owner_generation": execution.owner_generation,
        "cleanup_ref": execution.cleanup_ref,
    }
    try:
        projection = journal.append("check_recorded", data, coordinator_generation=generation)
    except StaleRevisionError:
        projection = journal.replay()
        saved = projection["tasks"][task.id].get("check")
        if not isinstance(saved, Mapping) or saved.get("attempt_id") != attempt_id or saved.get("execution_id") != execution.execution_id:
            projection = journal.append("check_recorded", data, coordinator_generation=generation)
    if execution.lifecycle == "blocked":
        raise AgentGraphCliError(
            f"task {task.id} check requires recovery; run recover-check-execution "
            f"--change {projection['change']} --run-id {projection['run_id']} "
            f"--generation {generation} --execution-id {execution.execution_id}; "
            f"output: {execution.artifact_ref}",
            code="check_execution_blocked",
        )
    if exit_code != 0:
        raise AgentGraphCliError(
            f"task {task.id} check failed with exit code {exit_code}; output: {data['artifact']}",
            code="check_failed",
        )
    return {"task_id": task.id, "check": data, "state": projection}


def command_import_checked_task(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    projection = journal.verify_projection()
    generation = _generation(arguments, projection)
    _require_current_execution_scope(arguments.repo, projection["workspace_scope"])
    projection = journal.import_checked_task(
        arguments.task,
        import_id=arguments.import_id,
        coordinator_generation=generation,
        note=arguments.note,
        timeout_seconds=arguments.timeout,
        output_cap_bytes=arguments.output_cap,
    )
    task = projection["tasks"][arguments.task]
    return {
        "task_id": arguments.task,
        "import_id": arguments.import_id,
        "grade": task["grade"],
        "check": task["check"],
        "import_receipt": task["import_receipt"],
        "state": projection,
    }


def command_recover_check(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    # A prior recovery can have been interrupted between its journal event and
    # side-record convergence. Replay remains readable so this public command
    # can finish that exact staged transition; verify_projection reconciles it
    # before exposing any terminal result to other commands.
    projection = journal.replay()
    generation = _generation(arguments, projection)
    _require_current_execution_scope(arguments.repo, projection["workspace_scope"])
    try:
        execution = recover_shared_check(
            repository=arguments.repo,
            run_directory=directory,
            execution_id=arguments.execution_id,
        )
    except CheckExecutionError as error:
        raise AgentGraphCliError(str(error), code="check_recovery_blocked") from error
    current = projection.get("check_executions", {}).get(execution.execution_id)
    record = load_shared_check_record(
        run_directory=directory, execution_id=execution.execution_id
    )
    consumers = record.get("consumer_refs")
    if not isinstance(consumers, list) or not consumers or not isinstance(consumers[0], str):
        raise AgentGraphCliError("check recovery has no durable consumer", code="check_recovery_invalid")
    if not isinstance(current, Mapping):
        running = _check_execution_binding(
            type("RunningExecution", (), {**record, "lifecycle": "running"})(), consumers[0]
        )
        projection = journal.append(
            "check_execution_recorded", running, coordinator_generation=generation
        )
        current = projection["check_executions"][execution.execution_id]
    if current.get("lifecycle") == "running":
        blocked = _check_execution_binding(
            type("BlockedExecution", (), {**record, "lifecycle": "blocked"})(), consumers[0]
        )
        projection = journal.append(
            "check_execution_recorded", blocked, coordinator_generation=generation
        )
        current = projection["check_executions"][execution.execution_id]
    if current.get("lifecycle") == "blocked":
        projection = journal.append(
            "check_execution_recovered",
            {
                "execution_id": execution.execution_id,
                "owner_generation": execution.owner_generation,
                "lifecycle": execution.lifecycle,
                "cleanup_ref": execution.cleanup_ref,
                "cleanup_id": execution.cleanup_id,
            },
            coordinator_generation=generation,
        )
    elif current.get("lifecycle") != "failed_verified":
        raise AgentGraphCliError("check recovery has an incompatible public lifecycle", code="check_recovery_invalid")
    try:
        execution = finalize_shared_check_recovery(
            repository=arguments.repo,
            run_directory=directory,
            prepared=execution,
        )
    except CheckExecutionError as error:
        raise AgentGraphCliError(str(error), code="check_recovery_blocked") from error
    projection = journal.verify_projection()
    return {
        "execution_id": execution.execution_id,
        "lifecycle": execution.lifecycle,
        "cleanup_ref": execution.cleanup_ref,
        "state": projection,
    }


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
    checked_import = task.checked and isinstance(state.get("import_receipt"), Mapping)
    attempts = [projection["attempts"][attempt_id] for attempt_id in state["attempt_ids"]]
    active_attempt_ids = [
        attempt_id
        for attempt_id in state["attempt_ids"]
        if projection["attempts"][attempt_id].get("status")
        in {"reserved", "running", "interrupted"}
    ]
    if active_attempt_ids:
        raise AgentGraphCliError(
            f"task {task.id} has active attempts: {', '.join(active_attempt_ids)}",
            code="attempt_active",
        )
    if arguments.grade in {"blocked", "unobserved"}:
        pending_cleanup = pending_cleanup_ids_for_task(projection, task.id)
        if pending_cleanup:
            raise AgentGraphCliError(
                f"terminal cleanup is required before {arguments.grade}: {', '.join(pending_cleanup)}",
                code="cleanup_pending",
            )
    latest_attempt = attempts[-1] if attempts else {}
    check = (
        state.get("check") or {}
        if checked_import
        else latest_attempt.get("check") or {}
    )
    if arguments.grade == "pass" and check.get("status") != "passed":
        raise AgentGraphCliError("grade pass requires a recorded passing check", code="evidence_required")
    if arguments.grade == "fail" and check.get("status") != "failed":
        raise AgentGraphCliError("grade fail requires a recorded failing check", code="evidence_required")
    if arguments.grade in {"pass", "fail"} and not checked_import:
        if (
            not attempts
            or latest_attempt.get("status") != "reported"
            or not isinstance(latest_attempt.get("report"), Mapping)
        ):
            raise AgentGraphCliError("evidence grade requires a terminal worker report", code="worker_report_required")
    if arguments.grade == "pass" and attempts:
        unresolved = sorted(
            finding_id
            for finding_id, finding in projection.get("findings", {}).items()
            if isinstance(finding, Mapping)
            and finding.get("task_id") == task.id
            and finding.get("attempt_id") == state["attempt_ids"][-1]
            and finding.get("classification") in BLOCKING_FINDING_CLASSIFICATIONS
        )
        if unresolved:
            raise AgentGraphCliError(
                "grade pass requires an explicit decision for blocking findings: "
                + ", ".join(unresolved),
                code="finding_decision_required",
            )
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
    task = _task_from_state(projection, arguments.task)
    state = projection["tasks"][task.id]
    hypothesis = " ".join(arguments.hypothesis.split())
    if not hypothesis:
        raise AgentGraphCliError(
            "repair hypothesis must not be empty", code="repair_invalid"
        )
    attempt_ids = state["attempt_ids"]
    if not attempt_ids:
        raise AgentGraphCliError(
            "record-repair requires a reported worker attempt",
            code="worker_report_required",
        )
    attempt_id = attempt_ids[-1]
    attempt = projection["attempts"][attempt_id]
    compact_rejection = {"hypothesis": hypothesis}
    if attempt.get("status") == "check-rejected":
        if attempt.get("check_rejection") == compact_rejection:
            return {
                "task_id": task.id,
                "attempt_id": attempt_id,
                "hypotheses": state["hypotheses"],
                "idempotent": True,
                "state": projection,
            }
        raise AgentGraphCliError(
            "failed check was already rejected with another hypothesis",
            code="repair_conflict",
        )
    if state["grade"] is not None:
        raise AgentGraphCliError(
            f"cannot repair graded task {task.id}", code="task_already_graded"
        )
    if attempt.get("status") != "reported":
        raise AgentGraphCliError(
            "record-repair requires the latest reported attempt",
            code="worker_report_required",
        )
    check = attempt.get("check")
    if (
        not isinstance(check, Mapping)
        or check.get("attempt_id") != attempt_id
        or check.get("status") != "failed"
        or check.get("exit_code") == 0
    ):
        raise AgentGraphCliError(
            "record-repair requires the latest attempt's failed check",
            code="evidence_required",
        )
    pending_cleanup = pending_cleanup_ids_for_attempt(projection, attempt_id)
    if pending_cleanup:
        raise AgentGraphCliError(
            "record-repair requires settled attempt cleanup: "
            + ", ".join(pending_cleanup),
            code="cleanup_pending",
        )
    try:
        projection = journal.append(
            "attempt_check_rejected",
            {"task_id": task.id, "attempt_id": attempt_id, "hypothesis": hypothesis},
            coordinator_generation=generation,
        )
    except JournalError as error:
        code = "repair_cap_reached" if "hypothesis" in str(error) else "repair_invalid"
        raise AgentGraphCliError(str(error), code=code) from error
    return {
        "task_id": task.id,
        "attempt_id": attempt_id,
        "hypotheses": projection["tasks"][task.id]["hypotheses"],
        "idempotent": False,
        "state": projection,
    }


def _canonical_audit_finding_refs(
    repository: Path, references: Sequence[str], *, require_exists: bool
) -> list[str]:
    canonical: list[str] = []
    seen: set[str] = set()
    for raw_reference in references:
        reference = raw_reference.strip()
        if reference.startswith("file:"):
            value = reference.removeprefix("file:").strip()
            try:
                path, normalized = repository_relative_path(
                    repository, value, "audit finding reference"
                )
            except CliValidationError as error:
                raise AgentGraphCliError(
                    str(error), code="audit_rejection_invalid"
                ) from error
            if require_exists and not path.is_file():
                raise AgentGraphCliError(
                    f"audit finding reference does not exist: {normalized}",
                    code="audit_rejection_invalid",
                )
            normalized_reference = f"file:{normalized}"
        elif reference.startswith("commit:"):
            revision = reference.removeprefix("commit:").strip().lower()
            if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", revision):
                raise AgentGraphCliError(
                    "audit commit reference must use a full SHA",
                    code="audit_rejection_invalid",
                )
            if require_exists:
                exists = subprocess.run(
                    ["git", "-C", str(repository), "cat-file", "-e", f"{revision}^{{commit}}"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if exists.returncode != 0:
                    raise AgentGraphCliError(
                        f"audit commit reference does not exist: {revision}",
                        code="audit_rejection_invalid",
                    )
            normalized_reference = f"commit:{revision}"
        else:
            raise AgentGraphCliError(
                "audit finding references must use file: or commit:",
                code="audit_rejection_invalid",
            )
        if normalized_reference not in seen:
            seen.add(normalized_reference)
            canonical.append(normalized_reference)
    if not canonical:
        raise AgentGraphCliError(
            "audit rejection requires at least one finding reference",
            code="audit_rejection_invalid",
        )
    return canonical


def command_reject_attempt(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    projection = journal.verify_projection()
    generation = _generation(arguments, projection)
    rejection_id = require_identifier(arguments.rejection_id, "rejection_id")
    attempt = projection["attempts"].get(arguments.attempt)
    if not isinstance(attempt, Mapping):
        raise AgentGraphCliError(
            f"unknown attempt: {arguments.attempt}", code="unknown_attempt"
        )
    task_id = str(attempt["task_id"])
    task = projection["tasks"][task_id]
    finding_refs = _canonical_audit_finding_refs(
        arguments.repo, list(arguments.finding_ref), require_exists=False
    )
    hypothesis = " ".join(arguments.hypothesis.split())
    if not hypothesis:
        raise AgentGraphCliError(
            "audit rejection hypothesis must not be empty",
            code="audit_rejection_invalid",
        )
    compact_transition = {
        "rejection_id": rejection_id,
        "finding_refs": finding_refs,
        "hypothesis": hypothesis,
    }
    for existing_attempt_id, existing_attempt in projection["attempts"].items():
        for field, result_field in (
            ("audit_rejection", "rejected"),
            ("audit_exhaustion", "exhausted"),
        ):
            existing = existing_attempt.get(field, {})
            if not isinstance(existing, Mapping) or existing.get("rejection_id") != rejection_id:
                continue
            if existing_attempt_id == arguments.attempt and existing == compact_transition:
                return {
                    "attempt_id": arguments.attempt,
                    "rejection_id": rejection_id,
                    result_field: True,
                    "idempotent": True,
                    "state": projection,
                }
            raise AgentGraphCliError(
                f"audit transition ID was already used differently: {rejection_id}",
                code="audit_rejection_conflict",
            )
    if attempt.get("audit_rejection") is not None:
        raise AgentGraphCliError(
            f"attempt already has another audit rejection: {arguments.attempt}",
            code="audit_rejection_conflict",
        )
    _canonical_audit_finding_refs(
        arguments.repo, list(arguments.finding_ref), require_exists=True
    )
    registered_findings = projection.get("findings", {})
    for finding_ref in finding_refs:
        if not finding_ref.startswith("file:"):
            raise AgentGraphCliError("audit rejection requires a structured finding file reference", code="audit_finding_invalid")
        finding_path, _ = repository_relative_path(
            arguments.repo, finding_ref.removeprefix("file:"), "audit finding reference"
        )
        try:
            raw_candidate = load_json_object(finding_path, "audit finding")
            canonical_ref = f"file:{finding_path.relative_to(arguments.repo).as_posix()}"
            candidate = validate_finding({**raw_candidate, "evidence_ref": canonical_ref})
        except (GraphError, AgentGraphCliError) as error:
            raise AgentGraphCliError(str(error), code="audit_finding_invalid") from error
        registered = registered_findings.get(candidate["finding_id"]) if isinstance(registered_findings, Mapping) else None
        if not isinstance(registered, Mapping):
            raise AgentGraphCliError(
                "audit rejection requires a registered finding",
                code="audit_finding_unregistered",
            )
        if candidate.get("evidence_ref") != canonical_ref or registered != candidate:
            raise AgentGraphCliError(
                "audit rejection evidence_ref or registered finding does not match",
                code="audit_finding_mismatch",
            )
        if candidate["task_id"] != task_id or candidate["attempt_id"] != arguments.attempt:
            raise AgentGraphCliError(
                "audit rejection finding does not match task and attempt",
                code="audit_finding_mismatch",
            )
        if candidate["classification"] not in BLOCKING_FINDING_CLASSIFICATIONS:
            raise AgentGraphCliError(
                "audit rejection requires a blocking registered finding",
                code="audit_finding_nonblocking",
            )
    if task["grade"] is not None:
        raise AgentGraphCliError(
            f"cannot reject graded task {task_id}", code="task_already_graded"
        )
    if attempt.get("status") != "reported":
        raise AgentGraphCliError(
            "audit rejection requires a reported attempt",
            code="attempt_not_rejectable",
        )
    if not task["attempt_ids"] or task["attempt_ids"][-1] != arguments.attempt:
        raise AgentGraphCliError(
            "audit rejection requires the latest task attempt",
            code="attempt_not_rejectable",
        )
    check = attempt.get("check")
    if (
        not isinstance(check, Mapping)
        or check.get("attempt_id") != arguments.attempt
        or check.get("status") != "passed"
        or check.get("exit_code") != 0
        or task.get("check") != check
    ):
        raise AgentGraphCliError(
            "audit rejection requires the latest attempt's passing check",
            code="evidence_required",
        )
    exhausted = hypothesis in task["hypotheses"] or len(task["hypotheses"]) >= 2
    pending_cleanup = pending_cleanup_ids_for_attempt(projection, arguments.attempt)
    if pending_cleanup:
        raise AgentGraphCliError(
            "audit rejection requires settled attempt cleanup: "
            + ", ".join(pending_cleanup),
            code="cleanup_pending",
        )
    event_type = "attempt_audit_exhausted" if exhausted else "attempt_audit_rejected"
    try:
        projection = journal.append(
            event_type,
            {
                "rejection_id": rejection_id,
                "task_id": task_id,
                "attempt_id": arguments.attempt,
                "finding_refs": finding_refs,
                "hypothesis": hypothesis,
            },
            coordinator_generation=generation,
        )
    except JournalError as error:
        code = "repair_cap_reached" if "hypothesis" in str(error) else "audit_rejection_invalid"
        raise AgentGraphCliError(str(error), code=code) from error
    return {
        "attempt_id": arguments.attempt,
        "rejection_id": rejection_id,
        "exhausted" if exhausted else "rejected": True,
        "idempotent": False,
        "state": projection,
    }


def command_record_finding(arguments: argparse.Namespace) -> dict[str, Any]:
    if (arguments.finding is None) == (arguments.finding_json is None):
        raise AgentGraphCliError(
            "record-finding requires exactly one of --finding or --finding-json",
            code="finding_invalid",
        )
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    projection = journal.verify_projection()
    generation = _generation(arguments, projection)
    if arguments.finding_json is not None:
        try:
            finding = json.loads(arguments.finding_json)
        except json.JSONDecodeError as error:
            raise AgentGraphCliError(f"finding JSON is invalid: {error.msg}", code="finding_invalid") from error
    else:
        path, _ = repository_relative_path(arguments.repo, arguments.finding, "finding")
        finding = load_json_object(path, "finding")
        finding = {**finding, "evidence_ref": f"file:{path.relative_to(arguments.repo).as_posix()}"}
    try:
        finding = validate_finding(finding)
    except GraphError as error:
        raise AgentGraphCliError(str(error), code="finding_invalid") from error
    attempt = projection["attempts"].get(finding["attempt_id"])
    if not isinstance(attempt, Mapping) or attempt.get("task_id") != finding["task_id"]:
        raise AgentGraphCliError("finding attempt does not match its task", code="finding_invalid")
    existing = projection.get("findings", {}).get(finding["finding_id"]) if isinstance(projection.get("findings"), Mapping) else None
    if existing is not None:
        if existing != finding:
            raise AgentGraphCliError("finding ID was reused with different content", code="finding_conflict")
        return {"finding_id": finding["finding_id"], "recorded": True, "idempotent": True, "state": projection}
    projection = journal.append("finding_recorded", finding, coordinator_generation=generation)
    return {"finding_id": finding["finding_id"], "recorded": True, "idempotent": False, "state": projection}


def command_record_decision(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    projection = journal.verify_projection()
    generation = _generation(arguments, projection)
    task = _task_from_state(projection, arguments.task)
    decision = {
        "decision_id": require_identifier(arguments.decision_id, "decision_id"),
        "task_id": task.id,
        "action": arguments.action,
        "note": " ".join(arguments.note.split()),
    }
    if not decision["note"]:
        raise AgentGraphCliError("decision note must not be empty", code="decision_invalid")
    existing = projection.get("coordinator_decisions", {}).get(decision["decision_id"]) if isinstance(projection.get("coordinator_decisions"), Mapping) else None
    if existing is not None:
        if existing != decision:
            raise AgentGraphCliError("decision ID was reused with different content", code="decision_conflict")
        return {"decision_id": decision["decision_id"], "decided": True, "idempotent": True, "state": projection}
    attempt_ids = projection["tasks"][task.id]["attempt_ids"]
    technical_attempts = sum(
        1 for attempt_id in attempt_ids
        for candidate in [projection["attempts"].get(attempt_id)]
        if isinstance(candidate, Mapping)
        and (isinstance(candidate.get("report"), Mapping)
             or isinstance(candidate.get("check"), Mapping)
             or candidate.get("status") in {"reported", "audit-rejected", "check-rejected", "audit-exhausted"})
    )
    if technical_attempts < 2:
        raise AgentGraphCliError("coordinator decision requires two technical attempts", code="decision_invalid")
    latest = projection["attempts"].get(attempt_ids[-1])
    if not isinstance(latest, Mapping) or latest.get("status") not in {
        "reported", "check-rejected", "audit-rejected", "audit-exhausted",
    }:
        raise AgentGraphCliError("coordinator decision requires the latest reported or audit-exhausted attempt", code="decision_invalid")
    if decision["action"] == "accept_check" and latest.get("status") != "reported":
        raise AgentGraphCliError("accept_check requires the latest reported attempt", code="decision_invalid")
    latest_check = latest.get("check")
    if not isinstance(latest_check, Mapping) or latest_check.get("attempt_id") != attempt_ids[-1]:
        raise AgentGraphCliError("coordinator decision requires the latest attempt's own check", code="decision_invalid")
    pending_cleanup = pending_cleanup_ids_for_attempt(projection, attempt_ids[-1])
    if pending_cleanup:
        raise AgentGraphCliError("coordinator decision requires settled attempt cleanup: " + ", ".join(pending_cleanup), code="cleanup_pending")
    projection = journal.append("coordinator_decision_recorded", decision, coordinator_generation=generation)
    return {"decision_id": decision["decision_id"], "decided": True, "idempotent": False, "state": projection}


def command_recover_attempt(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    projection = journal.verify_projection()
    generation = _generation(arguments, projection)
    attempt = projection["attempts"].get(arguments.attempt)
    if not isinstance(attempt, Mapping):
        raise AgentGraphCliError(f"unknown attempt: {arguments.attempt}", code="unknown_attempt")
    if isinstance(attempt.get("result_quarantine"), Mapping):
        _raise_result_slot_quarantined(arguments.attempt, attempt["result_quarantine"])
    if projection.get("driver") == "host" and attempt.get("status") == "reported":
        _verify_reported_result_slot(directory, arguments.attempt, attempt)
    workspace_scope = attempt.get("workspace_scope")
    execution_profile = attempt.get("execution_profile")
    routing_decision = attempt.get("routing_decision")
    routing_summary = attempt.get("routing_summary")
    if projection["driver"] == "orca":
        if (
            not isinstance(execution_profile, Mapping)
            or not isinstance(routing_decision, Mapping)
            or not isinstance(routing_summary, Mapping)
        ):
            raise AgentGraphCliError("attempt is missing its persisted routing decision", code="attempt_identity_missing")
        _verify_persisted_routing_decision(
            arguments.repo,
            attempt.get("routing_decision_ref"),
            routing_decision,
            execution_profile,
            routing_summary=routing_summary,
        )
    if attempt.get("status") == "running":
        owner = attempt.get("resource_owner")
        cleanup = projection["cleanup"].get(attempt.get("cleanup_id"))
        registration = attempt.get("cleanup_registration")
        if isinstance(owner, Mapping) and (
            not isinstance(cleanup, Mapping)
            or not isinstance(registration, Mapping)
            or cleanup.get("owner") != owner
            or cleanup.get("target") != registration.get("target")
            or cleanup.get("kind") != registration.get("kind")
        ):
            raise AgentGraphCliError(
                "running owned attempt has no exact persisted cleanup", code="cleanup_unproven"
            )
        pending_cleanup = pending_cleanup_ids_for_attempt(projection, arguments.attempt)
        if pending_cleanup:
            raise AgentGraphCliError(
                "attempt cleanup remains unsettled: " + ", ".join(pending_cleanup),
                code="cleanup_pending",
            )
        return {"attempt_id": arguments.attempt, "recovered": True, "idempotent": True, "state": projection}
    if attempt.get("status") not in {"reserved", "interrupted"}:
        raise AgentGraphCliError(
            f"attempt cannot be recovered from {attempt.get('status')}",
            code="attempt_not_recoverable",
        )
    if attempt.get("post_start_unresolved") is True:
        pending_cleanup = pending_cleanup_ids_for_attempt(projection, arguments.attempt)
        if pending_cleanup:
            raise AgentGraphCliError(
                "post-start cleanup is unresolved: " + ", ".join(pending_cleanup),
                code="post_start_cleanup_unresolved",
            )
        if not isinstance(attempt.get("resource_owner"), Mapping):
            raise AgentGraphCliError(
                "post-start identity is unresolved; cleanup cannot be verified",
                code="post_start_identity_unresolved",
            )
        raise AgentGraphCliError(
            "post-start attempt ID is burned; abandon it and dispatch a fresh attempt",
            code="post_start_attempt_burned",
        )
    task = _task_from_state(projection, attempt["task_id"])
    resource_owner = attempt.get("resource_owner")
    try:
        context = persisted_driver_context(attempt)
    except DriverError as error:
        raise AgentGraphCliError(str(error), code=error.code) from error
    workspace_scope = context["workspace_scope"]
    execution_profile = context["execution_profile"]
    external_refs = context["external_refs"]
    request = {
        **_driver_attempt(attempt, arguments.attempt, task),
        "task_id": task.id,
        "attempt_id": arguments.attempt,
        "recover": True,
        "task": task.to_dict(),
        "effective_scope": attempt.get("effective_scope"),
        "dependency_digest": attempt.get("dependency_digest", []),
        "worker_handle": external_refs.get("worker_handle"),
        "local": attempt.get("worker") == "local",
        **context,
        **({"routing_decision": dict(routing_decision)} if isinstance(routing_decision, Mapping) else {}),
        **({"routing_summary": dict(routing_summary)} if isinstance(routing_summary, Mapping) else {}),
        **({"resource_owner": dict(resource_owner)} if isinstance(resource_owner, Mapping) else {}),
    }
    if attempt.get("scope_frozen") is not True:
        projection = journal.append(
            "attempt_scope_frozen",
            {"attempt_id": arguments.attempt, "effective_scope": attempt.get("effective_scope")},
            coordinator_generation=generation,
        )
        attempt = projection["attempts"][arguments.attempt]
        request["effective_scope"] = attempt["effective_scope"]
    driver = _driver_for_state(arguments.repo, directory, projection)
    receipt = driver.start_attempt(request)
    receipt_id, receipt_path = _driver_receipt(arguments.repo, directory, receipt)
    refs = dict(receipt.external_refs)
    if projection["driver"] == "orca" and refs.get("tier") == "supervised":
        runtime_id = getattr(driver, "runtime_id", None)
        if not isinstance(runtime_id, str) or not runtime_id:
            _rollback_post_start_failure(arguments.repo, directory, journal, generation, driver, task, arguments.attempt, workspace_scope, execution_profile, refs, receipt, "missing recovery runtime identity")
            raise AgentGraphCliError(
                "supervised Orca recovery lacks its authoritative runtime identity", code="cleanup_unproven"
            )
        refs["runtime_id"] = runtime_id
    if projection["driver"] == "orca":
        try:
            started_owner, receipt_cleanup_id = _orca_lifecycle_from_receipt(
                refs, arguments.attempt, workspace_scope
            )
        except AgentGraphCliError as error:
            _rollback_post_start_failure(arguments.repo, directory, journal, generation, driver, task, arguments.attempt, workspace_scope, execution_profile, refs, receipt, str(error))
            raise
    else:
        started_owner, receipt_cleanup_id = None, None
    if isinstance(resource_owner, Mapping):
        if started_owner != resource_owner:
            _rollback_post_start_failure(arguments.repo, directory, journal, generation, driver, task, arguments.attempt, workspace_scope, execution_profile, refs, receipt, "recovery owner mismatch")
            raise AgentGraphCliError("recovery receipt does not match its persisted resource owner", code="cleanup_unproven")
    elif started_owner is not None and attempt.get("cleanup_id") is not None:
        raise AgentGraphCliError("recovery receipt changed cleanup ownership", code="cleanup_unproven")
    cleanup_id = attempt.get("cleanup_id") or receipt_cleanup_id
    cleanup_registration = (
        {
            "cleanup_id": cleanup_id,
            "kind": "terminal" if started_owner["terminal_id"] is not None else "other",
            "target": started_owner["terminal_id"] or refs["dispatch_id"],
            "owner": started_owner,
            "external_refs": dict(refs),
        }
        if cleanup_id and started_owner is not None
        else None
    )
    try:
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
            "effective_scope": attempt.get("effective_scope"),
            "dependency_digest": attempt.get("dependency_digest", []),
            "workspace_scope": dict(workspace_scope),
            "execution_profile": dict(execution_profile),
            **({"routing_decision": dict(routing_decision)} if isinstance(routing_decision, Mapping) else {}),
            **({"routing_summary": dict(routing_summary)} if isinstance(routing_summary, Mapping) else {}),
            **({"resource_owner": started_owner} if started_owner is not None else {}),
            "cleanup_id": cleanup_id,
            **({"cleanup_registration": cleanup_registration} if cleanup_registration is not None else {}),
            },
            coordinator_generation=generation,
        )
    except JournalError as error:
        _rollback_post_start_failure(arguments.repo, directory, journal, generation, driver, task, arguments.attempt, workspace_scope, execution_profile, refs, receipt, str(error))
        raise
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
    if attempt.get("post_start_unresolved") is True:
        pending_cleanup = pending_cleanup_ids_for_attempt(projection, arguments.attempt)
        if pending_cleanup:
            raise AgentGraphCliError(
                "post-start cleanup must be verified or retained before abandonment: "
                + ", ".join(pending_cleanup),
                code="post_start_cleanup_unresolved",
            )
        if not isinstance(attempt.get("resource_owner"), Mapping):
            raise AgentGraphCliError(
                "post-start identity is unresolved; attempt cannot be abandoned",
                code="post_start_identity_unresolved",
            )
    pending_cleanup = pending_cleanup_ids_for_attempt(projection, arguments.attempt)
    if pending_cleanup:
        raise AgentGraphCliError(
            "external cleanup remains unsettled for "
            f"{arguments.attempt}: {', '.join(pending_cleanup)}",
            code="cleanup_pending",
        )
    if not projection.get("driver"):
        raise AgentGraphCliError("driver selection must be recovered first", code="driver_not_selected")
    task = _task_from_state(projection, attempt["task_id"])
    driver_attempt = _driver_attempt(attempt, arguments.attempt, task)
    driver = _driver_for_state(arguments.repo, directory, projection)
    malformed_candidate = None
    if isinstance(driver, HostDriver):
        projection, malformed_candidate = _preserve_malformed_host_result(
            arguments.repo,
            directory,
            journal,
            projection,
            generation,
            arguments.attempt,
        )
        attempt = projection["attempts"][arguments.attempt]
        task = _task_from_state(projection, attempt["task_id"])
        driver_attempt = _driver_attempt(attempt, arguments.attempt, task)
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
    projection = journal.append(
        "attempt_abandoned",
        {
            "attempt_id": arguments.attempt,
            "task_id": attempt["task_id"],
            "reason": arguments.reason,
            **(
                {"malformed_candidate": malformed_candidate}
                if malformed_candidate is not None
                else {}
            ),
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
    typed_identity = arguments.kind in {"process", "terminal"}
    if typed_identity:
        try:
            owner_value = json.loads(arguments.owner)
            if not isinstance(owner_value, Mapping):
                raise ValueError("owner must be an object")
            owner = validate_cleanup_owner(owner_value)
            target_value: Any = arguments.target
            if arguments.kind == "process":
                target_value = json.loads(arguments.target)
            target = validate_cleanup_target(arguments.kind, target_value)
        except (GraphError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise AgentGraphCliError(
                f"typed cleanup identity is invalid: {error}", code="invalid_cleanup"
            ) from error
        if arguments.kind == "terminal" and "attempt_id" in owner:
            attempt = projection["attempts"].get(owner["attempt_id"])
            recorded_owner = attempt.get("resource_owner") if isinstance(attempt, Mapping) else None
            if not isinstance(recorded_owner, Mapping) or owner != recorded_owner:
                raise AgentGraphCliError(
                    "typed terminal cleanup owner is not anchored to the persisted attempt",
                    code="cleanup_authority_unproven",
                )
        expected: dict[str, Any] = {
            "cleanup_id": cleanup_id,
            "kind": arguments.kind,
            "target": target,
            "owner": owner,
            "identity_version": 1,
        }
    else:
        expected = {
            "cleanup_id": cleanup_id,
            "kind": arguments.kind,
            "target": arguments.target,
            "owner": arguments.owner,
        }
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
        target: Any = arguments.target
        try:
            target_value = json.loads(arguments.target)
            if isinstance(target_value, Mapping):
                target = target_value
        except json.JSONDecodeError:
            pass
        matches = [key for key, value in projection["cleanup"].items() if value.get("target") == target]
        if len(matches) != 1:
            raise AgentGraphCliError("cleanup target is missing or ambiguous", code="unknown_cleanup")
        cleanup_id = matches[0]
    if cleanup_id not in projection["cleanup"]:
        raise AgentGraphCliError(f"unknown cleanup: {cleanup_id}", code="unknown_cleanup")
    cleanup = projection["cleanup"][cleanup_id]
    receipt: Any = arguments.receipt
    if receipt:
        try:
            receipt = json.loads(receipt)
        except json.JSONDecodeError:
            pass
    if cleanup["status"] in {"done", "verified"}:
        if cleanup.get("receipt") != receipt:
            raise AgentGraphCliError(
                f"cleanup {cleanup_id} was finished with another receipt",
                code="duplicate_cleanup",
            )
        return {"cleanup_id": cleanup_id, "finished": True, "idempotent": True, "state": projection}
    if cleanup["status"] == "retained":
        raise AgentGraphCliError(
            f"cleanup {cleanup_id} was retained, not finished",
            code="cleanup_already_terminal",
        )
    cleanup_owner = cleanup.get("owner")
    owner_attempt_id = (
        cleanup_owner if isinstance(cleanup_owner, str)
        else cleanup_owner.get("attempt_id") if isinstance(cleanup_owner, Mapping)
        else None
    )
    owner = projection["attempts"].get(owner_attempt_id) if isinstance(owner_attempt_id, str) else None
    if isinstance(owner, Mapping) and owner.get("cleanup_id") == cleanup_id:
        raise AgentGraphCliError(
            f"cleanup {cleanup_id} is driver-owned; use recover-cleanup for attempt {cleanup['owner']}",
            code="driver_cleanup_requires_recovery",
        )
    if cleanup_target_exists(arguments.repo, cleanup["kind"], cleanup["target"]):
        raise AgentGraphCliError(f"cleanup target still exists: {cleanup['target']}", code="cleanup_pending")
    if cleanup["kind"] in {"terminal", "other"} and not receipt:
        raise AgentGraphCliError(f"cleanup kind {cleanup['kind']} requires --receipt", code="cleanup_receipt_required")
    if cleanup.get("identity_version") == 1 and not receipt:
        raise AgentGraphCliError(
            f"typed cleanup kind {cleanup['kind']} requires --receipt",
            code="cleanup_receipt_required",
        )
    if cleanup["kind"] == "terminal" and not isinstance(cleanup.get("owner"), Mapping):
        projection = journal.append(
            "cleanup_unverifiable",
            {
                "cleanup_id": cleanup_id,
                "receipt": {
                    "kind": "terminal",
                    "claimed_receipt": receipt,
                    "reason": "terminal cleanup requires owner-matching driver evidence",
                },
            },
            coordinator_generation=generation,
        )
        return {
            "cleanup_id": cleanup_id,
            "finished": False,
            "outcome": "unverifiable",
            "state": projection,
        }
    projection = journal.append(
        "cleanup_finished",
        {"cleanup_id": cleanup_id, "receipt": receipt},
        coordinator_generation=generation,
    )
    return {"cleanup_id": cleanup_id, "finished": True, "idempotent": False, "state": projection}


def command_cleanup_retain(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    projection = journal.verify_projection()
    generation = _generation(arguments, projection)
    cleanup = projection["cleanup"].get(arguments.cleanup_id)
    if not isinstance(cleanup, Mapping):
        raise AgentGraphCliError(
            f"unknown cleanup: {arguments.cleanup_id}", code="unknown_cleanup"
        )
    receipt: Any = arguments.receipt
    try:
        receipt = json.loads(receipt)
    except json.JSONDecodeError:
        pass
    if receipt is None or receipt == "":
        raise AgentGraphCliError(
            "cleanup retention requires --receipt", code="cleanup_receipt_required"
        )
    if cleanup.get("identity_version") is None and (
        arguments.reason is not None or arguments.replacement_cleanup_id is not None
    ):
        if not arguments.reason or not arguments.replacement_cleanup_id:
            raise AgentGraphCliError(
                "legacy cleanup retention requires both --reason and --replacement-cleanup-id",
                code="cleanup_retention_invalid",
            )
        if len(arguments.reason.encode("utf-8")) > 4096:
            raise AgentGraphCliError(
                "legacy cleanup retention reason exceeds 4096 bytes",
                code="cleanup_retention_invalid",
            )
        require_identifier(arguments.replacement_cleanup_id, "replacement_cleanup_id")
        receipt = {
            "kind": "legacy-retention",
            "reason": arguments.reason,
            "replacement_cleanup_id": arguments.replacement_cleanup_id,
        }
    if cleanup.get("status") == "retained":
        if cleanup.get("receipt") != receipt:
            raise AgentGraphCliError(
                f"cleanup was retained with another receipt: {arguments.cleanup_id}",
                code="cleanup_retention_conflict",
            )
        return {
            "cleanup_id": arguments.cleanup_id,
            "retained": True,
            "idempotent": True,
            "state": projection,
        }
    if cleanup.get("status") in {"done", "verified"}:
        raise AgentGraphCliError(
            f"cleanup is already terminal: {arguments.cleanup_id}",
            code="cleanup_already_terminal",
        )
    projection = journal.append(
        "cleanup_retained",
        {"cleanup_id": arguments.cleanup_id, "receipt": receipt},
        coordinator_generation=generation,
    )
    return {
        "cleanup_id": arguments.cleanup_id,
        "retained": True,
        "idempotent": False,
        "state": projection,
    }


def _status_result(
    projection: Mapping[str, Any], *, last_event: Mapping[str, Any] | None = None, events: list[Mapping[str, Any]] | None = None
) -> dict[str, Any]:
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
                "routing": attempt.get("routing_summary"),
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
        "cleanup": [
            {
                "cleanup_id": cleanup_id,
                "kind": cleanup.get("kind"),
                "status": cleanup.get("status"),
                "owner": cleanup.get("owner") if isinstance(cleanup.get("owner"), str) else None,
            }
            for cleanup_id, cleanup in projection["cleanup"].items()
            if isinstance(cleanup, Mapping)
        ],
        "degradations": [
            {key: value for key, value in degradation.items() if key not in {"receipt", "raw"}}
            for degradation in projection["degradations"]
            if isinstance(degradation, Mapping)
        ],
        "last_sequence": projection["last_sequence"],
        "progress": _run_progress_summary(projection, last_event=last_event, events=events),
    }


def _watch_delta(cursor: int, progress: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "kind": "delta",
        "cursor": cursor,
        "event": "progress_aggregate",
        "changes": {},
        "progress": dict(progress),
    }


def _watch_updates(
    journal: EventJournal,
    cursor: int | None,
) -> tuple[list[dict[str, Any]], int]:
    watch_replay = getattr(journal, "watch_replay_snapshot", journal.replay_snapshot)
    events, projection = watch_replay()
    retained_events = events[-WATCH_RETENTION:]
    current = projection.get("last_sequence")
    if not isinstance(current, int) or current < 0:
        raise JournalError("saved projection has an invalid cursor")
    earliest = retained_events[0]["sequence"] if retained_events else current + 1
    last_event = events[-1] if events else None
    progress = _run_progress_summary(projection, last_event=last_event, events=events)
    if cursor is None:
        return [{"kind": "snapshot", "cursor": current, "state": _status_result(projection, last_event=last_event, events=events)}], current
    if cursor > current:
        return [{"kind": "reset", "reason": "cursor_ahead", "cursor": current, "retained_from": earliest, "progress": progress}], current
    if cursor < current and (
        not retained_events
        or cursor < earliest - 1
    ):
        return [
            {
                "kind": "reset",
                "reason": "cursor_expired",
                "cursor": current,
                "retained_from": earliest,
                "progress": progress,
            }
        ], current
    if cursor == current:
        return [], current
    return [_watch_delta(current, progress)], current


def command_status(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    if not arguments.watch:
        journal = _journal(directory)
        events, projection = journal.watch_snapshot(1)
        return _status_result(projection, last_event=events[-1] if events else None)
    raise AgentGraphCliError("watch mode must stream through the CLI entrypoint", code="watch_stream_required")


def command_stop_hook(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    events, projection = journal.watch_snapshot(1)
    progress = _run_progress_summary(
        projection, last_event=events[-1] if events else None, events=events
    )
    task_counts = progress["task_counts"]
    pending = task_counts["pending"]
    running = task_counts["running"]
    if pending or running:
        return {
            "decision": "block",
            "reason": f"Agent Graph has {pending} pending and {running} running tasks.",
            "progress": progress,
        }
    return {"decision": "allow", "progress": progress}


def _browser_surface_view(view: Mapping[str, Any], projection: Mapping[str, Any]) -> dict[str, Any]:
    """Add bounded semantic browser-surface nodes without exposing browser data."""

    result = json.loads(json.dumps(view))
    surfaces = projection.get("browser_surfaces")
    if not isinstance(surfaces, Mapping):
        return validate_agent_graph_view(result)
    nodes = result["nodes"]
    edges = result["edges"]
    for request_id, record in sorted(surfaces.items(), key=lambda item: str(item[0])):
        if not isinstance(record, Mapping) or not isinstance(record.get("request"), Mapping):
            continue
        request = record["request"]
        digest = hashlib.sha256(str(request_id).encode("utf-8")).hexdigest()[:16]
        surface_id = f"browser-surface-{digest}"
        status = str(record.get("status", "requested"))
        nodes.append({"id": surface_id, "type": "browser-surface", "status": status, "summary": f"Browser surface {request.get('mode', 'unknown')}: {status}.", "task_id": request.get("task_id"), "attempt_id": request.get("attempt_id")})
        task_id, attempt_id = request.get("task_id"), request.get("attempt_id")
        if isinstance(task_id, str) and any(node.get("id") == f"task-{task_id}" for node in nodes):
            edges.append({"id": f"edge-browser-task-{digest}", "type": "uses", "source_id": f"task-{task_id}", "target_id": surface_id})
        if isinstance(attempt_id, str) and any(node.get("id") == f"attempt-{attempt_id}" for node in nodes):
            edges.append({"id": f"edge-browser-attempt-{digest}", "type": "uses", "source_id": f"attempt-{attempt_id}", "target_id": surface_id})
        receipts = record.get("receipts")
        captured = receipts.get("capture") if isinstance(receipts, Mapping) else None
        evidence = captured.get("capture") if isinstance(captured, Mapping) else None
        if isinstance(evidence, Mapping) and evidence.get("artifact_hash") and evidence.get("vision_review_ref"):
            evidence_id = f"evidence-browser-surface-{digest}"
            nodes.append({"id": evidence_id, "type": "evidence", "status": str(evidence.get("vision_outcome", "pending")), "summary": "Bounded browser-surface visual evidence."})
            edges.append({"id": f"edge-browser-evidence-{digest}", "type": "produces", "source_id": surface_id, "target_id": evidence_id})
    result["nodes"] = sorted(nodes, key=lambda item: item["id"])
    result["edges"] = sorted(edges, key=lambda item: item["id"])
    return validate_agent_graph_view(result)


def command_browser_surface(arguments: argparse.Namespace) -> dict[str, Any]:
    """Fence and persist one compact browser-surface lifecycle operation."""

    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    projection = journal.verify_projection()
    generation = _generation(arguments, projection)
    request_path, _ = repository_relative_path(arguments.repo, arguments.request, "browser surface request")
    try:
        request = validate_browser_surface_request(load_json_object(request_path, "browser surface request"))
    except BrowserSurfaceError as error:
        raise AgentGraphCliError(str(error), code="browser_surface_invalid") from error
    existing = projection.get("browser_surfaces", {}).get(request["request_id"])
    if isinstance(existing, Mapping):
        if existing.get("request") != request:
            raise AgentGraphCliError("browser surface request ID has different content", code="duplicate_browser_surface")
    else:
        projection = journal.append("browser_surface_requested", request, coordinator_generation=generation)
        existing = projection["browser_surfaces"][request["request_id"]]
    receipts = existing.get("receipts", {}) if isinstance(existing, Mapping) else {}
    saved = receipts.get(arguments.operation) if isinstance(receipts, Mapping) else None
    if isinstance(saved, Mapping):
        return {"request_id": request["request_id"], "operation": arguments.operation, "receipt": public_receipt(saved), "idempotent": True, "cursor": projection["last_sequence"], "revision": projection["last_sequence"]}
    driver = _driver_for_state(arguments.repo, directory, projection)
    method = getattr(driver, f"{arguments.operation}_browser_surface")
    receipt = method(request)
    browser_receipt = receipt.external_refs.get("browser_surface") if isinstance(receipt.external_refs, Mapping) else None
    if not isinstance(browser_receipt, Mapping):
        raise AgentGraphCliError("driver omitted browser-surface receipt", code="browser_surface_unproven")
    if (
        browser_receipt.get("status") in {"unsupported", "unavailable", "outcome_unknown", "unverifiable"}
        and arguments.operation != "reserve"
        and isinstance(receipts.get("bind"), Mapping)
        and isinstance(receipts["bind"].get("surface"), Mapping)
        and receipts["bind"]["surface"].get("page_binding") is not None
    ):
        browser_receipt = json.loads(json.dumps(browser_receipt))
        browser_receipt["surface"] = json.loads(json.dumps(receipts["bind"]["surface"]))
    projection = journal.append("browser_surface_receipt", {"receipt": public_receipt(browser_receipt)}, coordinator_generation=generation)
    return {"request_id": request["request_id"], "operation": arguments.operation, "receipt": public_receipt(browser_receipt), "idempotent": False, "cursor": projection["last_sequence"], "revision": projection["last_sequence"]}


def command_maestro_view(arguments: argparse.Namespace) -> dict[str, Any]:
    """Expose a bounded journal-derived view without exposing report bodies."""

    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    events, projection = journal.replay_snapshot()
    last_event = events[-1] if events else None
    progress = _run_progress_summary(projection, last_event=last_event, events=events)
    inbox = CoordinatorInbox(directory)
    capabilities = inbox.require_handshake(
        run_id=projection["run_id"], coordinator_id=projection["coordinator"].get("id"), generation=projection["coordinator"]["generation"]
    )
    if not isinstance(capabilities, Mapping):
        raise AgentGraphCliError(
            "AgentGraphView capabilities were not negotiated and persisted",
            code="capabilities_unavailable",
        )
    current = _browser_surface_view(build_snapshot(projection, change=arguments.change, capabilities=capabilities, stream_id=projection["run_id"], visual_state=inbox.read_visual_state(), last_event=last_event, progress=progress), projection)
    if arguments.kind == "snapshot":
        return current
    if not arguments.from_view:
        raise AgentGraphCliError("delta/reset view requires --from-view", code="invalid_cursor")
    previous_path, _ = repository_relative_path(arguments.repo, arguments.from_view, "previous Maestro view")
    previous = load_json_object(previous_path, "previous Maestro view")
    try:
        previous = validate_agent_graph_view(previous)
    except GraphError as error:
        raise AgentGraphCliError(f"previous Maestro view is invalid: {error}", code="invalid_cursor") from error
    context_fields = ("workspace_scope", "change", "run_id", "coordinator", "capabilities")
    if previous.get("kind") != "snapshot" or any(previous.get(field) != current.get(field) for field in context_fields):
        raise AgentGraphCliError("previous Maestro view does not match the current run context", code="invalid_cursor")
    if (
        not isinstance(previous.get("cursor"), Mapping)
        or previous["cursor"].get("sequence") != previous["cursor"].get("revision")
        or previous["cursor"].get("revision") != previous.get("revision")
    ):
        raise AgentGraphCliError("previous Maestro view cursor does not match its revision", code="invalid_cursor")
    if arguments.kind == "delta":
        view = build_delta(previous, current, change=arguments.change, from_cursor=previous.get("cursor"), capabilities=capabilities, stream_id=projection["run_id"])
    else:
        view = build_reset(current, change=arguments.change, from_cursor=previous.get("cursor"), capabilities=capabilities, stream_id=projection["run_id"])
    return view


def command_maestro_submit(arguments: argparse.Namespace) -> dict[str, Any]:
    """Validate and enqueue Canvas traffic for the current coordinator."""

    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    projection = _projection(directory)
    _generation(arguments, projection)
    CoordinatorInbox(directory).require_handshake(
        run_id=projection["run_id"], coordinator_id=projection["coordinator"].get("id"), generation=projection["coordinator"]["generation"]
    )
    request_path, _ = repository_relative_path(arguments.repo, arguments.request, "Maestro request")
    request = load_json_object(request_path, "Maestro request")
    inbox = CoordinatorInbox(directory)
    try:
        return inbox.submit(
            request,
            kind=arguments.kind,
            workspace_scope=projection["workspace_scope"],
            current_revision=projection["last_sequence"],
        )
    except MaestroBridgeError as error:
        raise AgentGraphCliError(str(error), code=error.code, details=error.details) from error


def _maestro_receipt(
    record: Mapping[str, Any], *, idempotent: bool
) -> dict[str, Any]:
    payload = record.get("payload")
    payload = payload if isinstance(payload, Mapping) else {}
    receipt: dict[str, Any] = {
        "request_id": payload.get("mutation_id") or payload.get("intent_id"),
        "kind": record.get("kind"),
        "status": "acked",
        "idempotent": idempotent,
        "revision": record.get("applied_revision"),
        "affected_entity_ids": list(record.get("affected_node_ids", []))[:32],
        "affected_event_ids": list(record.get("affected_event_ids", []))[:32],
        "warnings": [],
    }
    if isinstance(payload.get("mutation_id"), str):
        receipt["mutation_id"] = payload["mutation_id"]
    if isinstance(payload.get("intent_id"), str):
        receipt["intent_id"] = payload["intent_id"]
    return receipt


def _maestro_affected_nodes(record: Mapping[str, Any]) -> list[str]:
    payload = record.get("payload")
    payload = payload if isinstance(payload, Mapping) else {}
    operation = payload.get("operation")
    if not isinstance(operation, Mapping):
        return []
    if operation.get("kind") == "move-node" and isinstance(operation.get("node_id"), str):
        return [operation["node_id"]]
    if operation.get("kind") == "pin-note-snapshot" and isinstance(operation.get("snapshot"), Mapping):
        note_id = operation["snapshot"].get("note_id")
        if isinstance(note_id, str):
            return [f"note-{note_id}"]
    return []


def _acked_maestro_replay(
    inbox: CoordinatorInbox, request_id: str, *, coordinator_id: str, generation: int
) -> dict[str, Any] | None:
    record = inbox.get(request_id)
    if not isinstance(record, Mapping) or record.get("status") != "acked":
        return None
    if record.get("consumed_by") != coordinator_id or record.get("consumed_generation") != generation:
        raise AgentGraphCliError("request is owned by another coordinator", code="request_fenced")
    return _maestro_receipt(record, idempotent=True)


def _validate_maestro_record(record: Mapping[str, Any], workspace_scope: Mapping[str, Any]) -> None:
    if record.get("kind") != "mutation" or not isinstance(record.get("payload"), Mapping):
        return
    try:
        validate_maestro_mutation(record["payload"], workspace_scope)
    except GraphError as error:
        raise AgentGraphCliError(f"mutation is not valid for the current workspace: {error}", code="request_fenced") from error


def command_maestro_negotiate(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    projection = _projection(directory)
    generation = _generation(arguments, projection)
    local_path, _ = repository_relative_path(arguments.repo, arguments.local_capabilities, "local capabilities")
    remote_path, _ = repository_relative_path(arguments.repo, arguments.remote_capabilities, "remote capabilities")
    local = load_json_object(local_path, "local capabilities")
    remote = load_json_object(remote_path, "remote capabilities")
    capabilities = negotiate_capabilities(local, remote)
    if capabilities.get("protocol_major") != 1:
        raise AgentGraphCliError("Maestro v1 requires protocol major 1", code="unsupported_major")
    return CoordinatorInbox(directory).persist_capabilities(
        capabilities,
        coordinator_id=projection["coordinator"]["id"],
        generation=generation,
        workspace_scope=projection["workspace_scope"],
    )


def command_maestro_consume(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    events, projection = journal.watch_snapshot(1)
    last_event = events[-1] if events else None
    progress = _run_progress_summary(projection, last_event=last_event)
    generation = _generation(arguments, projection)
    if arguments.coordinator_id != projection["coordinator"].get("id"):
        raise AgentGraphCliError("consumer is not the active coordinator", code="stale_coordinator")
    inbox = CoordinatorInbox(directory)
    capabilities = inbox.require_handshake(run_id=projection["run_id"], coordinator_id=arguments.coordinator_id, generation=generation)
    replay = _acked_maestro_replay(inbox, arguments.request_id, coordinator_id=arguments.coordinator_id, generation=generation)
    if replay is not None:
        return replay
    valid_node_ids = None
    operation = None
    record = inbox.preflight(
        arguments.request_id,
        generation=generation,
        workspace_scope=projection["workspace_scope"],
        current_revision=projection["last_sequence"],
    )
    if isinstance(record, Mapping) and record.get("kind") == "mutation":
        payload = record.get("payload")
        operation = payload.get("operation") if isinstance(payload, Mapping) else None
        if isinstance(operation, Mapping) and operation.get("kind") == "move-node":
            snapshot = build_snapshot(projection, change=arguments.change, capabilities=capabilities, stream_id=projection["run_id"], visual_state=inbox.read_visual_state(), last_event=last_event, progress=progress)
            valid_node_ids = {node["id"] for node in snapshot["nodes"]}
    consumed = inbox.consume(
        arguments.request_id,
        coordinator_id=arguments.coordinator_id,
        generation=generation,
        workspace_scope=projection["workspace_scope"],
        current_revision=projection["last_sequence"],
        valid_node_ids=valid_node_ids,
    )
    applied_revision = int(consumed["payload"].get("expected_revision", projection["last_sequence"]))
    affected_event_ids: list[str] = []
    if consumed.get("kind") == "intent":
        intent_id = consumed["payload"]["intent_id"]
        existing = projection.get("delegations", {}).get(intent_id)
        if existing is not None and existing.get("intent") != consumed["payload"]:
            raise AgentGraphCliError("intent ID has divergent canonical content", code="replay_divergence")
        if existing is None:
            if consumed["payload"]["expected_revision"] != projection["last_sequence"]:
                raise AgentGraphCliError("intent cannot be appended at the current revision", code="stale_revision")
            appended_projection = journal.append("delegation_requested", {"intent": consumed["payload"]}, coordinator_generation=generation)
            if appended_projection["last_sequence"] != int(consumed["payload"]["expected_revision"]) + 1 or appended_projection.get("delegations", {}).get(intent_id, {}).get("intent") != consumed["payload"]:
                raise AgentGraphCliError("canonical delegation append cannot be proven", code="canonical_event_missing")
            applied_revision = int(consumed["payload"]["expected_revision"]) + 1
            affected_event_ids = [f"event-{applied_revision:06d}"]
        else:
            applied_revision = int(consumed["payload"]["expected_revision"]) + 1
            if projection["last_sequence"] < applied_revision:
                raise AgentGraphCliError("canonical delegation event cannot be proven", code="canonical_event_missing")
            affected_event_ids = [f"event-{applied_revision:06d}"]
    acked = inbox.ack(arguments.request_id, coordinator_id=arguments.coordinator_id, generation=generation, valid_node_ids=valid_node_ids, applied_revision=applied_revision, affected_node_ids=_maestro_affected_nodes(inbox.get(arguments.request_id) or {}), affected_event_ids=affected_event_ids)
    record = inbox.get(arguments.request_id)
    return _maestro_receipt(record or {}, idempotent=bool(acked.get("idempotent")))


def command_maestro_ack(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    events, projection = journal.watch_snapshot(1)
    last_event = events[-1] if events else None
    progress = _run_progress_summary(projection, last_event=last_event)
    generation = _generation(arguments, projection)
    if arguments.coordinator_id != projection["coordinator"].get("id"):
        raise AgentGraphCliError("acknowledger is not the active coordinator", code="stale_coordinator")
    inbox = CoordinatorInbox(directory)
    capabilities = inbox.require_handshake(run_id=projection["run_id"], coordinator_id=arguments.coordinator_id, generation=generation)
    record = inbox.get(arguments.request_id)
    replay = _acked_maestro_replay(inbox, arguments.request_id, coordinator_id=arguments.coordinator_id, generation=generation)
    if replay is not None:
        return replay
    valid_node_ids = None
    if isinstance(record, Mapping) and record.get("kind") == "mutation":
        _validate_maestro_record(record, projection["workspace_scope"])
        payload = record.get("payload")
        operation = payload.get("operation") if isinstance(payload, Mapping) else None
        if isinstance(operation, Mapping) and operation.get("kind") == "move-node":
            snapshot = build_snapshot(projection, change=arguments.change, capabilities=capabilities, stream_id=projection["run_id"], visual_state=inbox.read_visual_state(), last_event=last_event, progress=progress)
            valid_node_ids = {node["id"] for node in snapshot["nodes"]}
    if isinstance(record, Mapping) and record.get("kind") == "intent":
        payload = record.get("payload")
        canonical = projection.get("delegations", {}).get(payload.get("intent_id")) if isinstance(payload, Mapping) else None
        if not isinstance(canonical, Mapping) or canonical.get("intent") != payload:
            raise AgentGraphCliError("cannot ack intent before canonical delegation event", code="canonical_event_missing")
    applied_revision = projection["last_sequence"]
    affected_event_ids: list[str] = []
    if isinstance(record, Mapping) and record.get("kind") == "intent":
        payload = record.get("payload")
        expected_revision = payload.get("expected_revision") if isinstance(payload, Mapping) else None
        if not isinstance(expected_revision, int) or projection["last_sequence"] < expected_revision + 1:
            raise AgentGraphCliError("canonical delegation event cannot be proven", code="canonical_event_missing")
        applied_revision = expected_revision + 1
        affected_event_ids = [f"event-{applied_revision:06d}"]
    elif isinstance(record, Mapping) and isinstance(record.get("payload"), Mapping):
        applied_revision = record["payload"]["expected_revision"]
    acked = inbox.ack(arguments.request_id, coordinator_id=arguments.coordinator_id, generation=generation, valid_node_ids=valid_node_ids, applied_revision=applied_revision, affected_node_ids=_maestro_affected_nodes(record or {}), affected_event_ids=affected_event_ids)
    final_record = inbox.get(arguments.request_id)
    return _maestro_receipt(final_record or {}, idempotent=bool(acked.get("idempotent")))


def _stream_status_watch(arguments: argparse.Namespace) -> int:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    cursor = arguments.cursor
    iterations = arguments.iterations
    count = 0
    while iterations is None or count < iterations:
        updates, cursor = _watch_updates(journal, cursor)
        for update in updates:
            print(json.dumps(update, sort_keys=True), flush=True)
        count += 1
        if iterations is None or count < iterations:
            time.sleep(arguments.interval)
    return 0


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
        "pending_cleanup": [
            value
            for value in projection["cleanup"].values()
            if not cleanup_is_terminal(value)
        ],
        "degradations": projection["degradations"],
    }


def command_complete(arguments: argparse.Namespace) -> dict[str, Any]:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    control_runtime = verify_control_runtime(load_run_control_runtime(directory))
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
    pending_cleanup = unresolved_cleanup_ids(projection)
    if pending_cleanup:
        raise AgentGraphCliError(f"finish cleanup first: {', '.join(pending_cleanup)}", code="cleanup_pending")
    if arguments.outcome == "pass":
        if any(
            isinstance(item, Mapping) and item.get("status") == "carry_forward"
            for item in projection.get("degradations", [])
        ):
            raise AgentGraphCliError(
                "pass outcome cannot include carry-forward findings",
                code="carry_forward_findings",
            )
        ungraded = [task_id for task_id, task in projection["tasks"].items() if task["grade"] != "pass"]
        if ungraded:
            raise AgentGraphCliError(f"pass outcome requires every task to pass: {', '.join(ungraded)}", code="ungraded_tasks")
        base_commit = projection.get("base_commit")
        if isinstance(base_commit, str) and base_commit:
            owned_paths, unowned_paths = _completion_provenance(
                arguments.repo,
                directory,
                projection,
                _changed_paths_since(arguments.repo, base_commit),
            )
            if unowned_paths:
                raise AgentGraphCliError(
                    "post-bootstrap changes are not owned by a reported task attempt: "
                    + ", ".join(unowned_paths),
                    code="changed_path_unproven",
                )
            changed_frontend = _frontend_paths(owned_paths)
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
    release_control_runtime(control_runtime, run_terminal=projection["status"] == "complete")
    return {
        "completed": True,
        "idempotent": False,
        "control_runtime_released": True,
        "state": projection,
    }


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


def _matching_probe_result(
    result_path: Path, probe_attempt_id: str
) -> dict[str, Any] | None:
    if not result_path.is_file():
        return None
    try:
        candidate = load_json_object(result_path, "Orca probe result")
    except (CliValidationError, OSError):
        return None
    if candidate.get("probe_attempt_id") != probe_attempt_id:
        return None
    return candidate


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


def _probe_attempt(
    receipt: DriverReceipt,
    attempt_id: str,
    workspace_scope: Mapping[str, Any],
    execution_profile: Mapping[str, Any],
) -> dict[str, Any]:
    refs = dict(receipt.external_refs)
    try:
        context = persisted_driver_context(
            {
                "workspace_scope": workspace_scope,
                "execution_profile": execution_profile,
                "resolved_placement": execution_profile.get("resolved_placement"),
                "external_refs": refs,
            }
        )
    except DriverError as error:
        raise AgentGraphCliError(str(error), code=error.code) from error
    terminal = refs.get("terminal")
    return {
        **context,
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
    probe_attempt_id = session.get("probe_attempt_id")
    if not isinstance(probe_attempt_id, str) or not probe_attempt_id:
        raise AgentGraphCliError(
            "probe session omitted its result identity", code="probe_session_mismatch"
        )
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
    route_input = session.get("route_input")
    routing_decision = session.get("routing_decision")
    execution_profile = session.get("execution_profile")
    routing_ref = session.get("routing_decision_ref")
    launch_argv = session.get("launch_argv")
    routing_summary = session.get("routing_summary")
    if (
        not all(isinstance(value, Mapping) for value in (route_input, routing_decision, execution_profile, routing_ref))
        or not isinstance(launch_argv, list)
        or not isinstance(routing_summary, Mapping)
    ):
        raise AgentGraphCliError("probe session is missing its frozen routing decision", code="probe_profile_missing")
    authority = routing_ref.get("authority")
    if (
        not isinstance(authority, Mapping)
        or authority.get("coordinator_id") != coordinator_id
        or authority.get("coordinator_generation") != generation
    ):
        raise AgentGraphCliError("probe routing receipt does not bind the fresh coordinator", code="probe_profile_missing")
    _verify_persisted_routing_decision(
        repository, routing_ref, routing_decision, execution_profile,
        launch_argv=launch_argv, routing_summary=routing_summary,
    )
    receipts: dict[str, Any] = {}
    active_attempts: list[dict[str, Any]] = []
    cleanup_receipts: list[dict[str, Any]] = []
    driver = OrcaDriver(repository)
    tasks = _probe_tasks()
    graph = TaskGraph(tasks)
    workspace_scope = session.get("workspace_scope")
    if not isinstance(workspace_scope, Mapping):
        raise AgentGraphCliError("probe session is missing workspace scope", code="probe_profile_missing")
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
            try:
                probe_context = persisted_driver_context(
                    {
                        "workspace_scope": workspace_scope,
                        "execution_profile": execution_profile,
                        "resolved_placement": execution_profile.get("resolved_placement"),
                        "external_refs": {},
                    }
                )
            except DriverError as error:
                raise AgentGraphCliError(str(error), code=error.code) from error
            started_attempt = driver.start_attempt(
                {
                    "task_id": task.id,
                    "attempt_id": attempt_id,
                    "task": task.to_dict(),
                    "dependency_digest": {},
                    **probe_context,
                    "routing_decision": routing_decision,
                    "routing_decision_ref": routing_ref,
                    "routing_summary": routing_summary,
                    "external_refs": {},
                }
            )
            refs = dict(started_attempt.external_refs)
            attempt = _probe_attempt(
                DriverReceipt("start_attempt", "started", external_refs=refs),
                attempt_id,
                workspace_scope,
                execution_profile,
            )
            if refs.get("tier") == "supervised":
                if not isinstance(driver.runtime_id, str) or not driver.runtime_id:
                    try:
                        driver.release(attempt)
                    except DriverError:
                        pass
                    raise AgentGraphCliError("probe supervised receipt lacks runtime identity", code="cleanup_unproven")
                refs["runtime_id"] = driver.runtime_id
                attempt = _probe_attempt(
                    DriverReceipt("start_attempt", "started", external_refs=refs),
                    attempt_id,
                    workspace_scope,
                    execution_profile,
                )
            try:
                resource_owner, cleanup_id = _orca_lifecycle_from_receipt(refs, attempt_id, workspace_scope)
            except AgentGraphCliError:
                if refs.get("tier") == "supervised" and refs.get("dispatch_id"):
                    try:
                        driver.release(attempt)
                    except DriverError:
                        pass
                raise
            cleanup_registration = {
                "cleanup_id": cleanup_id,
                "kind": "terminal" if resource_owner and resource_owner["terminal_id"] is not None else "other",
                "target": resource_owner["terminal_id"] if resource_owner and resource_owner["terminal_id"] is not None else refs["dispatch_id"],
                "owner": resource_owner,
                "external_refs": dict(refs),
            }
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
                    "external_refs": refs,
                    "receipt_id": canonical_receipt_id(started_attempt.to_dict()),
                    "receipt_path": "inline:orca-live.json",
                    "task": task.to_dict(),
                    "effective_scope": attempt.get("effective_scope"),
                    "dependency_digest": {},
                    "workspace_scope": workspace_scope,
                    "execution_profile": execution_profile,
                    "routing_decision": routing_decision,
                    "routing_decision_ref": routing_ref,
                    "resource_owner": resource_owner,
                    "cleanup_id": cleanup_id,
                    "cleanup_registration": cleanup_registration,
                },
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
                "attempt_id": attempt_id,
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
            if resource_owner["terminal_id"] is None:
                release_state = _supervised_release_state(released)
                if release_state is None:
                    projection = journal.append(
                        "cleanup_unverifiable",
                        {"cleanup_id": cleanup_id, "receipt": {"driver": released.to_dict()}},
                        coordinator_generation=generation,
                    )
                    raise AgentGraphCliError("probe worker release is not authoritative", code="cleanup_unproven")
                cleanup_receipt = {
                    "kind": "provider-dispatch",
                    "owner": resource_owner,
                    "dispatch_id": refs["dispatch_id"],
                    "runtime_id": refs["runtime_id"],
                    "worktree_id": refs["worktree_id"],
                    "run_id": refs["run_id"],
                    "status": release_state,
                }
            else:
                cleanup_receipt = {"kind": "terminal", "owner": resource_owner, "terminal_id": resource_owner["terminal_id"], "incarnation_id": resource_owner["incarnation_id"], "status": "verified"}
            projection = journal.append(
                "cleanup_finished",
                {"cleanup_id": cleanup_id, "receipt": cleanup_receipt},
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
            "probe_attempt_id": probe_attempt_id,
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
    if not arguments.route_input:
        raise AgentGraphCliError("Orca probe requires --route-input", code="routing_catalog_missing")
    _, route_input_path = repository_relative_path(arguments.repo, arguments.route_input, "route input")
    supplied_route_input = load_json_object(arguments.repo / route_input_path, "route input")
    supplied_authority = supplied_route_input.get("authority")
    if (
        not isinstance(supplied_authority, Mapping)
        or not isinstance(supplied_authority.get("coordinator_id"), str)
        or not supplied_authority["coordinator_id"]
        or supplied_authority.get("coordinator_generation") != 1
        or not isinstance(supplied_authority.get("source"), str)
        or not supplied_authority["source"]
    ):
        raise AgentGraphCliError("probe route input requires an invoking bootstrap authority", code="routing_invalid")
    artifact_path, artifact_relative = repository_relative_path(arguments.repo, arguments.artifact, "Orca evidence artifact")
    source_before = _probe_source_fingerprint(arguments.repo, artifact_relative)
    run_id = f"orca-probe-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{os.getpid()}"
    tasks = _probe_tasks()
    bootstrap_id = supplied_authority["coordinator_id"]
    workspace_receipt = _automatic_host_workspace_receipt(arguments.repo, run_id)
    anticipated_directory = arguments.repo / "openspec" / "runs" / arguments.change / run_id
    anticipated_receipt = (anticipated_directory / WORKSPACE_BOOTSTRAP_RECEIPT_FILE).relative_to(arguments.repo).as_posix()
    workspace_scope = validate_workspace_scope(
        {
            "schema_version": SCHEMA_VERSION,
            "repository_id": workspace_receipt["repository_id"],
            "canonical_root": workspace_receipt["canonical_root"],
            "execution_host": workspace_receipt["execution_host"],
            "orchestration_home": workspace_receipt["orchestration_home"],
            "execution_workspace": workspace_receipt["execution_workspace"],
            "base_revision": workspace_receipt["base_revision"],
            "dirty_paths": workspace_receipt["dirty_paths"],
            "run_id": run_id,
            "coordinator_generation": 1,
            "binding_receipt_ref": f"artifact:{anticipated_receipt}",
            "binding_receipt_hash": _workspace_receipt_hash(workspace_receipt),
        }
    )
    frozen_route_input, frozen_route_path, frozen_route_sha256 = _route_input(
        arguments.repo,
        route_input_path,
        {"coordinator": {"id": bootstrap_id, "generation": 1}},
    )
    frozen_profile, frozen_decision = _routing_for_task(
        tasks[0], workspace_scope, driver_name="orca", route_input=frozen_route_input
    )
    frozen_routing_summary = _routing_summary(frozen_decision, frozen_route_input)
    launch_argv = _probe_launch_argv(frozen_decision, frozen_route_input)
    launch_command = _probe_launch_command_text(launch_argv)
    _preflight_probe_launch(launch_argv)
    driver = OrcaDriver(arguments.repo)
    detected = driver.detect()
    run_directory = _new_run_directory(arguments.repo, arguments.change, run_id)
    journal = _journal(run_directory)
    persisted_scope = _persist_workspace_scope(
        arguments.repo, run_directory, workspace_receipt,
        run_id=run_id, coordinator_generation=1,
    )
    if persisted_scope != workspace_scope:
        raise AgentGraphCliError("probe workspace scope changed after route preflight", code="probe_profile_missing")
    journal.append(
        "run_started",
        {"change": arguments.change, "run_id": run_id, "coordinator_id": bootstrap_id, "coordinator_generation": 1, "base_commit": _current_commit(arguments.repo), "dirty_paths": _dirty_paths(arguments.repo), "workspace_scope": workspace_scope, "tasks": [task.to_dict() for task in tasks]},
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
    probe_attempt_id = f"orca-probe-{uuid.uuid4()}"
    capsule_path = run_directory / "capsules" / "coordinator-generation-2.json"
    final_terminal_list: Mapping[str, Any] | None = None
    try:
        created = driver._call(
            "terminal", "create", "--worktree", f"id:{driver.worktree_id}", "--title", f"agent-graph-probe-coordinator-{run_id}", "--command", launch_command, "--json"
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
        child_authority = {
            "coordinator_id": f"orca-terminal:{coordinator_identity['handle']}",
            "coordinator_generation": 2,
            "source": "bootstrap-to-fresh-orca-terminal",
        }
        frozen_route_ref = _persist_routing_decision(
            arguments.repo,
            run_directory,
            route_input=frozen_route_input,
            route_input_path=frozen_route_path,
            route_input_sha256=frozen_route_sha256,
            decision=frozen_decision,
            execution_profile=frozen_profile,
            routing_summary=frozen_routing_summary,
            authority=child_authority,
            authority_transfer={"from": dict(frozen_route_input["authority"]), "to": child_authority},
            launch_argv=launch_argv,
        )
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
            "probe_attempt_id": probe_attempt_id,
            "capsule_path": capsule_path.relative_to(arguments.repo).as_posix(),
            "coordinator_generation": 2,
            "coordinator_identity": coordinator_identity,
            "workspace_scope": workspace_scope,
            "route_input": frozen_route_input,
            "routing_decision": frozen_decision,
            "execution_profile": frozen_profile,
            "routing_decision_ref": frozen_route_ref,
            "routing_summary": frozen_routing_summary,
            "launch_argv": launch_argv,
            "launch_command": launch_command,
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
        child_result: dict[str, Any] | None = None
        while time.monotonic() < deadline and child_result is None:
            child_result = _matching_probe_result(result_path, probe_attempt_id)
            if child_result is not None:
                break
            current_session = load_json_object(session_path, "Orca probe session")
            if current_session.get("status") == "failed":
                error = current_session.get("error", {})
                raise AgentGraphCliError(f"fresh Orca coordinator failed: {error}", code="live_probe_failed")
            time.sleep(2)
        if child_result is None:
            raise AgentGraphCliError("fresh Orca coordinator did not finish within 720 seconds", code="probe_timeout")
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
        parser.set_defaults(binding_preflight=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a durable repository-owned agent task graph.")
    add_runtime_arguments(parser)
    parser.add_argument("--json", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)

    intake = commands.add_parser("intake")
    _add_common(intake, run=False)
    request_source = intake.add_mutually_exclusive_group(required=True)
    request_source.add_argument("--request")
    request_source.add_argument("--request-file")
    signals_source = intake.add_mutually_exclusive_group()
    signals_source.add_argument("--signals-json")
    signals_source.add_argument("--signals-file")
    intake.add_argument("--check", required=True)
    intake.add_argument("--use-safe-defaults", action="store_true")
    intake.set_defaults(handler=command_intake)

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
    initialize.add_argument("--workspace-receipt")
    initialize.add_argument("--process-decision")
    initialize.set_defaults(handler=command_init)

    bootstrap = commands.add_parser("bootstrap")
    _add_common(bootstrap, run=False)
    bootstrap.add_argument("--change", required=True)
    bootstrap.add_argument("--run-id", required=True)
    bootstrap.add_argument("--bootstrap-id")
    bootstrap.add_argument("--driver", choices=sorted(DRIVERS), default="auto")
    bootstrap.add_argument("--workspace-receipt")
    bootstrap.add_argument("--process-decision")
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

    amend_decision = commands.add_parser("amend-decision")
    _add_common(amend_decision, mutate=True)
    amend_decision.add_argument("--decision", required=True)
    amend_decision.add_argument("--reduction-json")
    amend_decision.set_defaults(handler=command_amend_decision)

    request_delegation = commands.add_parser("request-delegation")
    _add_common(request_delegation, mutate=True)
    request_delegation.add_argument("--intent", required=True)
    request_delegation.set_defaults(handler=command_request_delegation)

    amend_graph = commands.add_parser("amend-graph")
    _add_common(amend_graph, mutate=True)
    amend_graph.add_argument("--amendment-id", required=True)
    amend_graph.add_argument("--parent-task", required=True)
    amend_graph.add_argument("--parent-attempt", required=True)
    amend_graph.add_argument("--path", action="append", required=True)
    amend_graph.add_argument("--reason", required=True)
    amend_graph.set_defaults(handler=command_amend_graph)

    approve_delegation = commands.add_parser("approve-delegation")
    _add_common(approve_delegation, mutate=True)
    approve_delegation.add_argument("--delegation", required=True)
    approve_delegation.add_argument("--execution-profile", required=True)
    approve_delegation.add_argument("--context-revision", required=True)
    approve_delegation.add_argument("--path", action="append", default=[])
    approve_delegation.add_argument("--context-ref", action="append", default=[])
    approve_delegation.add_argument("--amendment-id")
    approve_delegation.set_defaults(handler=command_approve_delegation)

    reject_delegation = commands.add_parser("reject-delegation")
    _add_common(reject_delegation, mutate=True)
    reject_delegation.add_argument("--delegation", required=True)
    reject_delegation.add_argument("--reason", required=True)
    reject_delegation.set_defaults(handler=command_reject_delegation)

    start_delegation = commands.add_parser("start-delegation")
    _add_common(start_delegation, mutate=True)
    start_delegation.add_argument("--delegation", required=True)
    start_delegation.add_argument("--child-attempt", required=True)
    start_delegation.add_argument("--resource-owner", required=True)
    start_delegation.add_argument("--receipt-id", required=True)
    start_delegation.add_argument("--receipt-path", required=True)
    start_delegation.set_defaults(handler=command_start_delegation)

    report_delegation = commands.add_parser("report-delegation")
    _add_common(report_delegation, mutate=True)
    report_delegation.add_argument("--delegation", required=True)
    report_delegation.add_argument("--result", required=True)
    report_delegation.add_argument("--receipt-id", required=True)
    report_delegation.add_argument("--receipt-path", required=True)
    report_delegation.set_defaults(handler=command_report_delegation)

    release_delegation = commands.add_parser("release-delegation")
    _add_common(release_delegation, mutate=True)
    release_delegation.add_argument("--delegation", required=True)
    release_delegation.add_argument("--cleanup-id", required=True)
    release_delegation.add_argument("--receipt-id", required=True)
    release_delegation.add_argument("--receipt-path", required=True)
    release_delegation.set_defaults(handler=command_release_delegation)

    register_delegation_cleanup = commands.add_parser("register-delegation-cleanup")
    _add_common(register_delegation_cleanup, mutate=True)
    register_delegation_cleanup.add_argument("--delegation", required=True)
    register_delegation_cleanup.add_argument("--cleanup-id", required=True)
    register_delegation_cleanup.add_argument("--kind", choices=sorted(CLEANUP_KINDS), required=True)
    register_delegation_cleanup.add_argument("--target", required=True)
    register_delegation_cleanup.set_defaults(handler=command_register_delegation_cleanup)

    dispatch = commands.add_parser("dispatch")
    _add_common(dispatch, mutate=True)
    dispatch.add_argument("--task", required=True)
    dispatch.add_argument("--attempt-id")
    dispatch.add_argument("--worker")
    dispatch.add_argument("--local", action="store_true")
    dispatch.add_argument("--route-input")
    dispatch.add_argument("--defer-launch", action="store_true")
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

    quarantine = commands.add_parser("quarantine-result")
    _add_common(quarantine, mutate=True)
    quarantine.add_argument("--task", required=True)
    quarantine.add_argument("--attempt", "--attempt-id", dest="attempt", required=True)
    quarantine.add_argument("--candidate", required=True)
    quarantine.add_argument("--idempotency-key", required=True)
    quarantine.set_defaults(handler=command_quarantine_result)

    reply = commands.add_parser("reply")
    _add_common(reply, mutate=True)
    reply.add_argument("--question", "--question-id", dest="question", required=True)
    reply.add_argument("--body", required=True)
    reply.set_defaults(handler=command_reply)

    check = commands.add_parser("run-check")
    _add_common(check, mutate=True)
    check.add_argument("--task", required=True)
    check.add_argument("--timeout", type=float, default=CHECK_TIMEOUT_SECONDS)
    check.add_argument("--output-cap", type=int, default=65_536)
    check.set_defaults(handler=command_run_check)

    checked_import = commands.add_parser("import-checked-task")
    _add_common(checked_import, mutate=True)
    checked_import.add_argument("--task", required=True)
    checked_import.add_argument("--import-id", required=True)
    checked_import.add_argument("--note", required=True)
    checked_import.add_argument("--timeout", type=float, default=CHECK_TIMEOUT_SECONDS)
    checked_import.add_argument("--output-cap", type=int, default=65_536)
    checked_import.set_defaults(handler=command_import_checked_task)

    recover_check = commands.add_parser("recover-check-execution")
    _add_common(recover_check, mutate=True)
    recover_check.add_argument("--execution-id", required=True)
    recover_check.set_defaults(handler=command_recover_check)

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

    reject = commands.add_parser("audit-reject-attempt")
    _add_common(reject, mutate=True)
    reject.add_argument("--attempt", "--attempt-id", dest="attempt", required=True)
    reject.add_argument("--rejection-id", required=True)
    reject.add_argument("--finding-ref", action="append", required=True)
    reject.add_argument("--hypothesis", required=True)
    reject.set_defaults(handler=command_reject_attempt)

    finding = commands.add_parser("record-finding", aliases=["finding-record"])
    _add_common(finding, mutate=True)
    finding_input = finding.add_mutually_exclusive_group(required=True)
    finding_input.add_argument("--finding")
    finding_input.add_argument("--finding-json")
    finding.set_defaults(handler=command_record_finding)

    decision = commands.add_parser("record-decision", aliases=["coordinator-decision", "finding-decision"])
    _add_common(decision, mutate=True)
    decision.add_argument("--task", required=True)
    decision.add_argument("--decision-id", required=True)
    decision.add_argument("--action", choices=["amend_acceptance", "amend_paths", "regroup", "accept_check", "input_required", "blocked"], required=True)
    decision.add_argument("--note", required=True)
    decision.set_defaults(handler=command_record_decision)

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
    recover_cleanup.add_argument("--cleanup-id")
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

    retain = commands.add_parser("cleanup-retain")
    _add_common(retain, mutate=True)
    retain.add_argument("--cleanup-id", required=True)
    retain.add_argument("--receipt", required=True)
    retain.add_argument("--reason")
    retain.add_argument("--replacement-cleanup-id")
    retain.set_defaults(handler=command_cleanup_retain)

    status = commands.add_parser("status")
    _add_common(status)
    status.add_argument("--watch", action="store_true")
    status.add_argument("--cursor", type=int)
    status.add_argument("--interval", type=float, default=1.0)
    status.add_argument("--iterations", type=int)
    status.set_defaults(handler=command_status)

    stop_hook = commands.add_parser("stop-hook")
    _add_common(stop_hook)
    stop_hook.set_defaults(handler=command_stop_hook)

    maestro_view = commands.add_parser("maestro-view")
    _add_common(maestro_view)
    maestro_view.add_argument("--kind", choices=("snapshot", "delta", "reset"), default="snapshot")
    maestro_view.add_argument("--from-view")
    maestro_view.set_defaults(handler=command_maestro_view)

    for operation in ("reserve", "bind", "capture", "release"):
        browser_surface = commands.add_parser(f"browser-surface-{operation}")
        _add_common(browser_surface, mutate=True)
        browser_surface.add_argument("--request", required=True)
        browser_surface.set_defaults(handler=command_browser_surface, operation=operation)

    maestro_submit = commands.add_parser("maestro-submit")
    _add_common(maestro_submit, mutate=True)
    maestro_submit.add_argument("--kind", choices=("mutation", "intent"), required=True)
    maestro_submit.add_argument("--request", required=True)
    maestro_submit.set_defaults(handler=command_maestro_submit)

    maestro_negotiate = commands.add_parser("maestro-negotiate")
    _add_common(maestro_negotiate, mutate=True)
    maestro_negotiate.add_argument("--local-capabilities", required=True)
    maestro_negotiate.add_argument("--remote-capabilities", required=True)
    maestro_negotiate.set_defaults(handler=command_maestro_negotiate)

    maestro_consume = commands.add_parser("maestro-consume")
    _add_common(maestro_consume, mutate=True)
    maestro_consume.add_argument("--request-id", required=True)
    maestro_consume.add_argument("--coordinator-id", required=True)
    maestro_consume.set_defaults(handler=command_maestro_consume)

    maestro_ack = commands.add_parser("maestro-ack")
    _add_common(maestro_ack, mutate=True)
    maestro_ack.add_argument("--request-id", required=True)
    maestro_ack.add_argument("--coordinator-id", required=True)
    maestro_ack.set_defaults(handler=command_maestro_ack)

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
    probe.add_argument("--route-input", required=True)
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
    pending = [
        item["cleanup_id"]
        for item in result["cleanup"]
        if not cleanup_is_terminal(item)
    ]
    lines.append(f"Pending cleanup: {', '.join(pending) or 'none'}")
    return "\n".join(lines)


_MUTATION_DETAIL_FIELDS = frozenset(
    {
        "body",
        "context",
        "contexts",
        "raw",
        "report",
        "reports",
        "result",
        "results",
        "state",
        "task",
        "terminal_output",
        "transcript",
    }
)


def _compact_mutation_value(value: Any, *, depth: int = 0) -> Any:
    if depth >= 4:
        return "[bounded]"
    if isinstance(value, str):
        return value[:1024]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, Mapping):
        return {
            str(key): _compact_mutation_value(item, depth=depth + 1)
            for key, item in list(value.items())[:32]
            if str(key).casefold() not in _MUTATION_DETAIL_FIELDS
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_compact_mutation_value(item, depth=depth + 1) for item in value[:32]]
    return str(value)[:1024]


def _compact_mutation_receipt(
    command: str, result: Mapping[str, Any], *, progress: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    state = result.get("state")
    revision = state.get("last_sequence") if isinstance(state, Mapping) else None
    receipt = {
        key: value
        for key, value in result.items()
        if key != "state" and key.casefold() not in _MUTATION_DETAIL_FIELDS
    }
    compact = _compact_mutation_value(receipt)
    if not isinstance(compact, dict):
        compact = {}
    compact["operation"] = command
    if progress is not None:
        compact["progress"] = dict(progress)
    if isinstance(revision, int):
        compact["revision"] = revision
    return compact


def _invocation_run_directory(arguments: argparse.Namespace) -> Path:
    change = require_identifier(arguments.change, "change")
    if arguments.run_id is not None:
        run_id = require_identifier(arguments.run_id, "run_id")
        directory = arguments.repo / RUNS_DIRECTORY / change / run_id
        if not directory.is_dir():
            raise ControlRuntimeError(f"run does not exist: {change}/{run_id}")
        return directory
    root = arguments.repo / RUNS_DIRECTORY / change
    candidates: list[Path] = []
    for directory in sorted(root.iterdir()) if root.is_dir() else []:
        if not (directory / CONTROL_RUNTIME_REF_FILE).is_file():
            continue
        try:
            state = load_json_object(directory / "state.json", "run state")
        except (CliValidationError, OSError):
            candidates.append(directory)
            continue
        if state.get("status") == "active":
            candidates.append(directory)
    if len(candidates) != 1:
        detail = "no active run" if not candidates else "multiple active runs"
        raise ControlRuntimeError(f"{detail} can supply a pinned control runtime for {change}")
    return candidates[0]


def _invocation_control_runtime(arguments: argparse.Namespace) -> dict[str, Any] | None:
    if arguments.command == "claim-coordinator":
        path, _ = repository_relative_path(
            arguments.repo, arguments.capsule, "coordinator capsule"
        )
        capsule = load_json_object(path, "coordinator capsule")
        scope = capsule.get("workspace_scope", {})
        repository = Path(str(scope.get("canonical_root", ""))) if isinstance(scope, Mapping) else Path()
        if not repository.is_absolute() or repository.resolve() != arguments.repo:
            raise ControlRuntimeError("coordinator capsule belongs to another repository")
        change = require_identifier(capsule.get("change"), "change")
        run_id = require_identifier(capsule.get("run_id"), "run_id")
        directory = arguments.repo / RUNS_DIRECTORY / change / run_id
        saved = verify_control_runtime(load_run_control_runtime(directory))
        supplied = verify_control_runtime(capsule.get("control_runtime", {}))
        if supplied != saved:
            raise ControlRuntimeError("coordinator capsule control runtime does not match the run")
        return saved
    commands_without_existing_run = {
        "validate",
        "init",
        "bootstrap",
        "probe-orca",
        "probe-orca-child",
    }
    if arguments.command in commands_without_existing_run:
        return None
    if not hasattr(arguments, "change"):
        return None
    return verify_control_runtime(
        load_run_control_runtime(_invocation_run_directory(arguments))
    )


def _enter_pinned_runtime(
    arguments: argparse.Namespace,
    argv: Sequence[str] | None,
) -> None:
    reference = _invocation_control_runtime(arguments)
    if reference is None:
        return
    entrypoint = Path(reference["entrypoint"])
    if Path(__file__).resolve() == entrypoint:
        return
    if argv is not None:
        raise ControlRuntimeError(
            "run command must execute through its pinned control runtime entrypoint"
        )
    os.execv(
        sys.executable,
        [sys.executable, str(entrypoint), *sys.argv[1:]],
    )


def _mutation_binding_preflight(arguments: argparse.Namespace) -> None:
    directory = _run_directory(arguments.repo, arguments.change, arguments.run_id)
    journal = _journal(directory)
    events, _ = journal._read_complete_events()
    projection = replay_events(events)
    _verify_workspace_binding(arguments.repo, directory, projection)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        arguments.repo = runtime_from_arguments(arguments).project_directory
        _enter_pinned_runtime(arguments, argv)
        if getattr(arguments, "binding_preflight", False):
            _mutation_binding_preflight(arguments)
        if arguments.command == "status" and arguments.watch:
            return _stream_status_watch(arguments)
        result = arguments.handler(arguments)
        if arguments.command == "stop-hook":
            if result.get("decision") == "block":
                print(json.dumps({"decision": "block", "reason": result["reason"]}, sort_keys=True))
        elif arguments.command == "status" and not arguments.json:
            print(_human_status(result))
        else:
            if arguments.command not in {"intake", "validate", "status", "digest", "probe-orca", "maestro-view", "maestro-consume", "maestro-ack"}:
                progress = None
                if getattr(arguments, "change", None) and getattr(arguments, "run_id", None):
                    progress = _run_progress_from_journal(
                        _journal(_run_directory(arguments.repo, arguments.change, arguments.run_id))
                    )
                result = _compact_mutation_receipt(arguments.command, result, progress=progress)
            print(json.dumps({"ok": True, "command": arguments.command, "result": result}, indent=2, sort_keys=True))
        return 0
    except (
        AgentGraphCliError,
        CliValidationError,
        ControlRuntimeError,
        DriverError,
        GraphError,
        RuntimeConfigError,
        OSError,
    ) as error:
        code = getattr(error, "code", None) or (
            "stale_coordinator" if isinstance(error, StaleCoordinatorError) else "invalid_graph"
        )
        error_fields = {"code": code, "message": str(error), "command": getattr(arguments, "command", None)}
        details = getattr(error, "details", None)
        if isinstance(details, Mapping):
            error_fields.update(details)
        payload = {"ok": False, "error": error_fields}
        print(json.dumps(payload, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
