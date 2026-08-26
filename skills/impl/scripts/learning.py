#!/usr/bin/env python3
"""Record evidence-backed impl observations without activating rules."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
import tempfile
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

AGENT_GRAPH_SCRIPTS = Path(__file__).resolve().parents[2] / "agent-graph" / "scripts"
if str(AGENT_GRAPH_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(AGENT_GRAPH_SCRIPTS))

from runtime_config import RuntimeConfigError, add_runtime_arguments, runtime_from_arguments  # noqa: E402
from visual_evidence import parse_visual_scope  # noqa: E402


PROCESS_LEARNING_PATH = AGENT_GRAPH_SCRIPTS / "learning.py"
PROCESS_LEARNING_SPEC = importlib.util.spec_from_file_location(
    "agent_graph_process_learning", PROCESS_LEARNING_PATH
)
if PROCESS_LEARNING_SPEC is None or PROCESS_LEARNING_SPEC.loader is None:
    raise RuntimeError(f"cannot load process learning module: {PROCESS_LEARNING_PATH}")
process_learning = importlib.util.module_from_spec(PROCESS_LEARNING_SPEC)
PROCESS_LEARNING_SPEC.loader.exec_module(process_learning)


SCHEMA_VERSION = 1
MIN_RECURRING_CHANGES = 5
GRAPH_RUNS_DIRECTORY = Path("openspec/runs")
LEARNING_ROOT = Path("openspec/impl-learning")
RUNS_DIRECTORY = LEARNING_ROOT / "runs"
EVIDENCE_DIRECTORY = LEARNING_ROOT / "evidence"
DRAFTS_FILE = LEARNING_ROOT / "DRAFT_CANDIDATES.md"
KEY_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*$")
KINDS = {"rule", "gate", "skill"}
STANCES = {"support", "oppose"}
ORIGINS = {"check", "diff", "repair", "review"}
TASK_STATUSES = {"pass", "fail", "unobserved", "blocked"}
MAX_TASKS = 256
MAX_LIST_ENTRIES = 32
MAX_LIFECYCLE_ENTRIES = 64
MAX_VALUE_LENGTH = 512
MAX_CHECK_BYTES = 4096
RECEIPT_PATH_PATTERN = re.compile(r"^openspec/runs/[^/]+/[^/]+/artifacts/.+$")
RECEIPT_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
COORDINATOR_OWNER_FIELDS = {
    "execution_host_id",
    "workspace_key",
    "coordinator_generation",
    "terminal_id",
    "incarnation_id",
    "process_root",
    "provenance",
}


class LearningError(ValueError):
    """Reports an invalid observation record or unsafe transition."""


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
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def require_identifier(value: Any, context: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER_PATTERN.fullmatch(value):
        raise LearningError(f"{context} must be a path-safe identifier")
    return value


def require_key(value: Any, context: str) -> str:
    if not isinstance(value, str) or not KEY_PATTERN.fullmatch(value):
        raise LearningError(
            f"{context} must use lowercase letters, numbers, dots, underscores, or hyphens"
        )
    return value


def require_string(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LearningError(f"{context} must be a non-empty string")
    return value.strip()


def bounded_string(value: Any, context: str) -> str:
    result = require_string(value, context)
    if len(result) > MAX_VALUE_LENGTH:
        raise LearningError(f"{context} exceeds the bounded learning record limit")
    return result


def require_string_list(value: Any, context: str, *, allow_empty: bool) -> list[str]:
    if not isinstance(value, list):
        raise LearningError(f"{context} must be an array")
    if not allow_empty and not value:
        raise LearningError(f"{context} must not be empty")
    entries = [require_string(entry, f"{context}[]") for entry in value]
    if len(entries) != len(set(entries)):
        raise LearningError(f"{context} must not contain duplicates")
    return entries


def bounded_string_list(value: Any, context: str, *, allow_empty: bool) -> list[str]:
    entries = require_string_list(value, context, allow_empty=allow_empty)
    if len(entries) > MAX_LIST_ENTRIES:
        raise LearningError(f"{context} exceeds the bounded learning record limit")
    return [bounded_string(entry, f"{context}[]") for entry in entries]


def bounded_optional_string(value: Any, context: str) -> str | None:
    if value is None:
        return None
    return bounded_string(value, context)


def validate_bounded_check(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LearningError(f"{context} must be an object")
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > MAX_CHECK_BYTES:
        raise LearningError(f"{context} exceeds the bounded learning record limit")
    for key, entry in value.items():
        if isinstance(entry, str):
            bounded_string(entry, f"{context}.{key}")
            continue
        if entry is not None and not isinstance(entry, (bool, int, float)):
            raise LearningError(f"{context}.{key} has an unsupported value")
    return value


def bounded_visual_scopes(value: Any, context: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > MAX_LIST_ENTRIES:
        raise LearningError(f"{context} exceeds the bounded learning record limit")
    scopes: list[dict[str, Any]] = []
    for index, raw_scope in enumerate(value):
        if not isinstance(raw_scope, str):
            raise LearningError(f"{context}[{index}] must be a string")
        scope = parse_visual_scope(raw_scope)
        for field in ("surface", "state", "reason"):
            bounded_string(scope[field], f"{context}[{index}].{field}")
        bounded_string_list(scope["platforms"], f"{context}[{index}].platforms", allow_empty=False)
        scopes.append(scope)
    return scopes


def validate_check_number(value: Any, context: str, *, positive: bool = False) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0 or (positive and value == 0):
        qualifier = "positive" if positive else "non-negative"
        raise LearningError(f"{context} must be a {qualifier} integer or null")
    return value


def validate_exit_code(value: Any, context: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise LearningError(f"{context} must be an integer or null")
    return value


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise LearningError(f"file does not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise LearningError(f"{path}: invalid JSON: {error.msg}") from error


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def repo_path(repo: Path, relative: str, context: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise LearningError(f"{context} must stay inside the repository")
    root = repo.resolve()
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise LearningError(f"{context} must stay inside the repository") from error
    return resolved


def validate_completed_state(state: Any, path: Path) -> dict[str, Any]:
    if not isinstance(state, dict):
        raise LearningError(f"{path} must contain an object")
    if state.get("status") != "complete":
        raise LearningError(f"{path} must be a completed impl state")
    require_identifier(state.get("change"), f"{path}.change")
    require_identifier(state.get("run_id"), f"{path}.run_id")
    tasks = state.get("tasks")
    if not isinstance(tasks, dict) or not tasks:
        raise LearningError(f"{path}.tasks must be a non-empty graph projection")
    if len(tasks) > MAX_TASKS:
        raise LearningError(f"{path}.tasks exceeds the bounded learning record limit")
    normalized_tasks: list[dict[str, Any]] = []
    for task_id, task in tasks.items():
        context = f"{path}.tasks[{task_id}]"
        if not isinstance(task, dict):
            raise LearningError(f"{context} must be an object")
        bounded_string(task_id, f"{context}.id")
        grade = task.get("grade")
        if grade not in TASK_STATUSES:
            raise LearningError(f"{context}.grade must be terminal")
        check = validate_bounded_check(task.get("check"), f"{context}.check")
        if validate_check_number(check.get("attempts"), f"{context}.check.attempts") is None:
            raise LearningError(f"{context}.check.attempts must be present")
        contract = task.get("contract")
        if not isinstance(contract, dict):
            raise LearningError(f"{context}.contract must be an object")
        raw_scopes = contract.get("visual_scope", [])
        try:
            visual_scopes = bounded_visual_scopes(raw_scopes, f"{context}.visual_scope")
        except (TypeError, ValueError) as error:
            raise LearningError(f"{context}.visual_scope is invalid: {error}") from error
        normalized_tasks.append(
            {
                "id": task_id,
                "status": grade,
                "check": check,
                "hypotheses": bounded_string_list(task.get("hypotheses", []), f"{context}.hypotheses", allow_empty=True),
                "evidence_refs": bounded_string_list(task.get("evidence_refs", []), f"{context}.evidence_refs", allow_empty=True),
                "visual_expectations": bounded_string_list(contract.get("visual", []), f"{context}.visual", allow_empty=True),
                "visual_scopes": visual_scopes,
            }
        )
    normalized = dict(state)
    normalized["tasks"] = normalized_tasks
    return normalized


def task_fact(
    task: dict[str, Any],
    routing_decisions: list[dict[str, Any]] | None = None,
    lifecycle_receipts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    check = task["check"]
    validate_bounded_check(check, "task.check")
    check_command = check.get("command")
    if check_command is not None:
        bounded_string(check_command, "task.check.command")
    return {
        "task_id": bounded_string(task["id"], "task_id"),
        "status": task["status"],
        "check_command": bounded_optional_string(check_command, "task.check.command"),
        "check_status": check.get("status"),
        "check_attempts": check["attempts"],
        "check_exit_code": validate_exit_code(check.get("exit_code"), "task.check.exit_code"),
        "check_duration_ms": validate_check_number(check.get("duration_ms"), "task.check.duration_ms"),
        "check_total_duration_ms": validate_check_number(check.get("total_duration_ms", check.get("duration_ms")), "task.check.total_duration_ms"),
        "hypotheses": list(task.get("hypotheses", []))[:MAX_LIST_ENTRIES],
        "evidence_refs": list(task.get("evidence_refs", []))[:MAX_LIST_ENTRIES],
        "visual_expectations": list(task.get("visual_expectations", []))[:MAX_LIST_ENTRIES],
        "visual_scopes": list(task.get("visual_scopes", [])),
        "routing_decisions": list(routing_decisions or []),
        "lifecycle_receipts": list(lifecycle_receipts or []),
    }


def profile_choice(profile: Any, context: str) -> dict[str, Any] | None:
    if profile is None:
        return None
    if not isinstance(profile, dict):
        raise LearningError(f"{context} must be an object")
    field_limits = {"lane": 64, "agent": 128, "model": 256, "effort": 32}
    choice = {}
    for field, limit in field_limits.items():
        entry = bounded_optional_string(profile.get(field), f"{context}.{field}")
        if entry is not None and len(entry) > limit:
            raise LearningError(f"{context}.{field} exceeds its schema limit")
        choice[field] = entry
    return choice


def routing_fact(attempt: dict[str, Any], *, repo: Path, run_root: Path) -> dict[str, Any]:
    summary = attempt.get("routing_summary")
    if not isinstance(summary, dict):
        raise LearningError("attempt routing_summary must be an object")
    profile = attempt.get("execution_profile") or {}
    if not isinstance(profile, dict):
        raise LearningError("attempt execution_profile must be an object")
    decision = attempt.get("routing_decision")
    if decision is not None and not isinstance(decision, dict):
        raise LearningError("attempt routing_decision must be an object")
    attempt_id = bounded_string(attempt.get("attempt_id"), "attempt.attempt_id")
    task_id = bounded_string(attempt.get("task_id"), "attempt.task_id")
    role = bounded_string(summary.get("role", profile.get("role")), "attempt.routing_summary.role")
    risk = bounded_optional_string(summary.get("risk"), "attempt.routing_summary.risk")
    rationale_value = summary.get("risk_rationale")
    rationale = None
    if rationale_value is not None:
        if not isinstance(rationale_value, dict):
            raise LearningError("attempt.routing_summary.risk_rationale must be an object")
        rationale = bounded_string(json.dumps(rationale_value, sort_keys=True), "attempt.rationale")
    cost_rank = summary.get("cost_rank")
    if cost_rank is not None and (not isinstance(cost_rank, int) or isinstance(cost_rank, bool) or cost_rank < 0):
        raise LearningError("attempt.cost_rank must be a non-negative integer or null")
    reference = attempt.get("routing_decision_ref")
    if reference is not None:
        if not isinstance(reference, dict):
            raise LearningError("attempt.routing_decision_ref must be an object")
        reference = resolve_receipt_metadata(
            reference,
            receipt_id=reference.get("receipt_id"),
            repo=repo,
            run_root=run_root,
            context="routing reference",
            producer="routing",
        )
        reference = {key: reference[key] for key in ("receipt_id", "receipt_path", "sha256")}
    return {
        "attempt_id": attempt_id,
        "task_id": task_id,
        "role": role,
        "risk": risk,
        "requested": profile_choice(summary.get("requested", profile.get("requested")), "attempt.requested"),
        "resolved": profile_choice(summary.get("resolved", profile.get("resolved")), "attempt.resolved"),
        "fallback_reason": bounded_optional_string(summary.get("fallback_reason"), "attempt.fallback_reason"),
        "outcome": bounded_optional_string(decision.get("outcome") if isinstance(decision, dict) else None, "attempt.routing_decision.outcome"),
        "blocked_reason": bounded_optional_string(decision.get("blocked_reason") if isinstance(decision, dict) else None, "attempt.routing_decision.blocked_reason"),
        "rationale": rationale,
        "cost_rank": cost_rank,
        "reference": reference,
    }


def resolve_receipt_metadata(
    receipt: Any, *, receipt_id: Any, repo: Path, run_root: Path, context: str,
    producer: str = "attempt", expected_kind: str | None = None,
    cleanup_status: str | None = None,
) -> dict[str, Any] | None:
    if receipt is None:
        return None
    provided_sha256 = None
    provided_byte_length = None
    receipt_is_mapping = isinstance(receipt, dict)
    if isinstance(receipt, str):
        receipt_path = receipt
    elif receipt_is_mapping:
        receipt_path = receipt.get("receipt_path")
        if receipt_id is None:
            receipt_id = receipt.get("receipt_id")
        provided_sha256 = receipt.get("sha256")
        provided_byte_length = receipt.get("byte_length")
        if producer == "cleanup" and receipt_path is None:
            receipt_kind = receipt.get("kind")
            if receipt_kind is not None and expected_kind is not None and receipt_kind != expected_kind:
                raise LearningError(f"{context}.kind does not match cleanup kind")
            if cleanup_status != "unverifiable" and expected_kind is not None and receipt_kind != expected_kind:
                raise LearningError(f"{context}.kind is required for a verified typed cleanup")
            if provided_sha256 is not None or provided_byte_length is not None:
                raise LearningError(
                    f"{context} without receipt_path cannot provide artifact metadata"
                )
            return None
        if producer in {"routing", "delegation"} and provided_sha256 is None:
            raise LearningError(f"{context} mappings must provide sha256")
        if producer == "delegation" and provided_byte_length is None:
            raise LearningError(f"{context} mappings must provide byte_length")
    else:
        raise LearningError(f"{context} must be a repository-relative receipt path or object")
    receipt_path = bounded_string(receipt_path, f"{context}.receipt_path")
    if producer == "cleanup" and receipt_is_mapping:
        receipt_kind = receipt.get("kind")
        if expected_kind is not None and receipt_kind != expected_kind:
            raise LearningError(f"{context}.kind does not match cleanup kind")
    if not RECEIPT_PATH_PATTERN.fullmatch(receipt_path):
        raise LearningError(f"{context}.receipt_path must be an artifact-relative path")
    candidate = Path(receipt_path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise LearningError(f"{context}.receipt_path escapes the repository")
    resolved = (repo / candidate).resolve()
    try:
        resolved.relative_to(run_root.resolve() / "artifacts")
    except ValueError as error:
        raise LearningError(f"{context}.receipt_path is outside the selected run artifacts") from error
    if not resolved.is_file():
        raise LearningError(f"{context}.receipt_path does not exist")
    content = resolved.read_bytes()
    if not content:
        raise LearningError(f"{context}.receipt_path must contain bytes")
    computed_sha256 = f"sha256:{hashlib.sha256(content).hexdigest()}"
    computed_byte_length = len(content)
    if receipt_is_mapping:
        if producer in {"routing", "delegation"} and (
            not isinstance(provided_sha256, str) or not RECEIPT_HASH_PATTERN.fullmatch(provided_sha256)
        ):
            raise LearningError(f"{context}.sha256 is malformed")
        if provided_byte_length is not None and (
            not isinstance(provided_byte_length, int)
            or isinstance(provided_byte_length, bool)
            or provided_byte_length <= 0
        ):
            raise LearningError(f"{context}.byte_length must be a positive integer")
        if (
            provided_sha256 is not None and provided_sha256 != computed_sha256
        ) or (
            provided_byte_length is not None and provided_byte_length != computed_byte_length
        ):
            raise LearningError(f"{context} metadata does not match receipt bytes")
    elif producer == "delegation":
        raise LearningError(f"{context} delegation receipts must be objects")
    return {
        "receipt_id": bounded_optional_string(receipt_id, f"{context}.receipt_id"),
        "receipt_path": receipt_path,
        "sha256": computed_sha256,
        "byte_length": computed_byte_length,
    }


def lifecycle_fact(
    *, kind: str, entity_id: str, attempt_id: str | None, phase: str, status: str,
    receipt: Any = None, receipt_id: Any = None, repo: Path, run_root: Path,
    expected_receipt_kind: str | None = None,
) -> dict[str, Any]:
    if kind not in {"attempt", "cleanup", "delegation"}:
        raise LearningError("unsupported lifecycle kind")
    result = {
        "kind": kind,
        "entity_id": bounded_string(entity_id, "lifecycle.entity_id"),
        "attempt_id": bounded_optional_string(attempt_id, "lifecycle.attempt_id"),
        "phase": bounded_string(phase, "lifecycle.phase"),
        "status": bounded_string(status, "lifecycle.status"),
        "receipt_id": None,
        "receipt_path": None,
        "sha256": None,
        "byte_length": None,
    }
    producer = kind
    metadata = resolve_receipt_metadata(
        receipt,
        receipt_id=receipt_id,
        repo=repo,
        run_root=run_root,
        context="lifecycle receipt",
        producer=producer,
        expected_kind=expected_receipt_kind,
        cleanup_status=status if kind == "cleanup" else None,
    )
    if metadata:
        result.update(metadata)
    return result


def lifecycle_facts(state: dict[str, Any], *, repo: Path, run_root: Path) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    receipt_ids: set[str] = set()
    receipt_paths: set[str] = set()
    receipt_bindings: set[tuple[str, str]] = set()
    attempts = state.get("attempts", {})
    if not isinstance(attempts, dict):
        raise LearningError("state.attempts must be an object")
    for attempt_id, attempt in sorted(attempts.items()):
        if not isinstance(attempt, dict):
            raise LearningError("state.attempts entries must be objects")
        task_id = bounded_string(attempt.get("task_id"), "attempt.task_id")
        fact = lifecycle_fact(
                kind="attempt", entity_id=bounded_string(attempt_id, "attempt id"),
                attempt_id=attempt_id, phase="attempt", status=bounded_string(attempt.get("status"), "attempt.status"),
                receipt=attempt.get("receipt_path"), receipt_id=attempt.get("receipt_id"), repo=repo, run_root=run_root,
            )
        register_receipt_binding(fact, receipt_ids, receipt_paths, receipt_bindings)
        by_task[task_id].append(fact)
    cleanup = state.get("cleanup", {})
    if not isinstance(cleanup, dict):
        raise LearningError("state.cleanup must be an object")
    run_lifecycle: list[dict[str, Any]] = []
    for cleanup_id, record in sorted(cleanup.items()):
        if not isinstance(record, dict):
            raise LearningError("state.cleanup entries must be objects")
        owner = record.get("owner")
        owner_attempt = owner.get("attempt_id") if isinstance(owner, dict) else owner if isinstance(owner, str) else None
        if isinstance(owner, dict) and "coordinator_generation" in owner and ("attempt_id" in owner or "attempt_id" in record):
            raise LearningError(f"cleanup {cleanup_id} mixes attempt and coordinator ownership")
        attempt_id = record.get("attempt_id", owner_attempt)
        if attempt_id is not None:
            attempt_id = bounded_string(attempt_id, "cleanup.attempt_id")
        task_id = None
        if attempt_id is not None and isinstance(attempts.get(attempt_id), dict):
            task_id = attempts[attempt_id].get("task_id")
        if task_id is None and isinstance(owner, dict):
            scope = state.get("workspace_scope")
            coordinator = state.get("coordinator")
            if not isinstance(scope, dict) or not isinstance(coordinator, dict):
                raise LearningError("state workspace scope and coordinator are required")
            execution_workspace = scope.get("execution_workspace")
            if not isinstance(execution_workspace, dict):
                raise LearningError("state.workspace_scope.execution_workspace is required")
            expected_host = execution_workspace.get("execution_host_id")
            expected_workspace = execution_workspace.get("workspace_key")
            expected_generation = coordinator.get("generation")
            if set(owner) != COORDINATOR_OWNER_FIELDS:
                raise LearningError(f"cleanup {cleanup_id} has malformed coordinator owner")
            if owner["execution_host_id"] != expected_host or owner["workspace_key"] != expected_workspace:
                raise LearningError(f"cleanup {cleanup_id} coordinator owner scope does not match run")
            if any(not isinstance(owner[field], str) or not owner[field].strip() for field in ("execution_host_id", "workspace_key", "provenance")):
                raise LearningError(f"cleanup {cleanup_id} coordinator owner has invalid string fields")
            if any(owner[field] is not None and (not isinstance(owner[field], str) or not owner[field].strip()) for field in ("terminal_id", "incarnation_id")):
                raise LearningError(f"cleanup {cleanup_id} coordinator owner has invalid identity fields")
            if not isinstance(owner["coordinator_generation"], int) or isinstance(owner["coordinator_generation"], bool) or owner["coordinator_generation"] < 1 or owner["coordinator_generation"] > expected_generation:
                raise LearningError(f"cleanup {cleanup_id} coordinator generation is invalid")
            target = record.get("target")
            receipt = record.get("receipt")
            if not isinstance(receipt, dict):
                raise LearningError(f"cleanup {cleanup_id} requires a typed receipt")
            if receipt.get("status") != record.get("status"):
                raise LearningError(f"cleanup {cleanup_id} receipt status does not match cleanup status")
            cleanup_kind, expected_receipt_kind = coordinator_resource_status(
                owner, target, record.get("status"), f"cleanup {cleanup_id}", record.get("kind")
            )
            if receipt.get("kind") != expected_receipt_kind:
                raise LearningError(f"cleanup {cleanup_id} receipt kind does not match cleanup kind")
            if receipt.get("owner") != owner:
                raise LearningError(f"cleanup {cleanup_id} receipt owner does not match cleanup owner")
            if cleanup_kind == "process" and receipt.get("target") != target:
                raise LearningError(f"cleanup {cleanup_id} receipt target does not match cleanup target")
            if cleanup_kind == "terminal" and (
                receipt.get("terminal_id") != owner["terminal_id"]
                or receipt.get("incarnation_id") != owner["incarnation_id"]
            ):
                raise LearningError(f"cleanup {cleanup_id} receipt terminal identity does not match cleanup owner")
            fact = lifecycle_fact(
                kind="cleanup", entity_id=bounded_string(cleanup_id, "cleanup id"), attempt_id=None,
                phase="cleanup", status=bounded_string(record.get("status"), "cleanup.status"),
                receipt=record.get("receipt"), receipt_id=record.get("receipt_id"), repo=repo, run_root=run_root,
                expected_receipt_kind=expected_receipt_kind,
            )
            fact["owner"] = owner
            fact["target"] = target
            register_receipt_binding(fact, receipt_ids, receipt_paths, receipt_bindings)
            run_lifecycle.append(fact)
            continue
        if task_id is None:
            raise LearningError(f"cleanup {cleanup_id} is not linked to an attempt task")
        fact = lifecycle_fact(
                kind="cleanup", entity_id=bounded_string(cleanup_id, "cleanup id"),
            attempt_id=attempt_id, phase="cleanup", status=bounded_string(record.get("status"), "cleanup.status"),
            receipt=record.get("receipt"), receipt_id=record.get("receipt_id"), repo=repo, run_root=run_root,
            expected_receipt_kind={
                "process": "process",
                "terminal": "terminal",
                "other": "provider-dispatch",
            }.get(record.get("kind")),
        )
        register_receipt_binding(fact, receipt_ids, receipt_paths, receipt_bindings)
        by_task[bounded_string(task_id, "cleanup.task_id")].append(fact)
    delegations = state.get("delegations", {})
    if isinstance(delegations, dict):
        for delegation_id, delegation in sorted(delegations.items()):
            if not isinstance(delegation, dict):
                raise LearningError("state.delegations entries must be objects")
            task_id = delegation.get("parent_task_id")
            if not isinstance(task_id, str):
                raise LearningError(f"delegation {delegation_id} is not linked to a parent task")
            for phase, receipt in sorted((delegation.get("lifecycle_receipts") or {}).items()):
                fact = lifecycle_fact(
                        kind="delegation", entity_id=bounded_string(delegation_id, "delegation id"),
                        attempt_id=delegation.get("child_attempt_id"), phase=phase,
                        status=bounded_string(delegation.get("status"), "delegation.status"), receipt=receipt,
                        repo=repo, run_root=run_root,
                    )
                register_receipt_binding(fact, receipt_ids, receipt_paths, receipt_bindings)
                by_task[task_id].append(fact)
    for task_id in by_task:
        if len(by_task[task_id]) > MAX_LIFECYCLE_ENTRIES:
            raise LearningError(f"task {task_id} exceeds lifecycle evidence limit")
        by_task[task_id] = sorted(by_task[task_id], key=lambda value: (value["kind"], value["entity_id"], value["phase"]))
    return by_task, run_lifecycle


def register_receipt_binding(
    fact: dict[str, Any], receipt_ids: set[str], receipt_paths: set[str], receipt_bindings: set[tuple[str, str]]
) -> None:
    receipt_id = fact["receipt_id"]
    receipt_path = fact["receipt_path"]
    receipt_hash = fact["sha256"]
    if receipt_path is None:
        return
    if receipt_id is not None and receipt_id in receipt_ids:
        raise LearningError("receipt_id is reused across lifecycle bindings")
    binding = (receipt_path, receipt_hash)
    if receipt_path in receipt_paths or binding in receipt_bindings:
        raise LearningError("receipt path or hash binding is reused")
    if receipt_id is not None:
        receipt_ids.add(receipt_id)
    receipt_paths.add(receipt_path)
    receipt_bindings.add(binding)


def routing_facts(state: dict[str, Any], *, repo: Path, run_root: Path) -> dict[str, list[dict[str, Any]]]:
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    attempts = state.get("attempts", {})
    if not isinstance(attempts, dict):
        raise LearningError("state.attempts must be an object")
    for attempt_id, attempt in sorted(attempts.items()):
        if not isinstance(attempt, dict):
            raise LearningError("state.attempts entries must be objects")
        if "routing_summary" not in attempt:
            continue
        fact = routing_fact({**attempt, "attempt_id": attempt_id}, repo=repo, run_root=run_root)
        by_task[fact["task_id"]].append(fact)
    for task_id in by_task:
        if len(by_task[task_id]) > MAX_LIST_ENTRIES:
            raise LearningError(f"task {task_id} exceeds routing evidence limit")
        by_task[task_id] = sorted(by_task[task_id], key=lambda value: value["attempt_id"])
    return by_task


def validate_profile_choice_record(value: Any, context: str, *, allow_none: bool = False) -> None:
    if value is None and allow_none:
        return
    if not isinstance(value, dict) or set(value) != {"lane", "agent", "model", "effort"}:
        raise LearningError(f"{context} has invalid fields")
    field_limits = {"lane": 64, "agent": 128, "model": 256, "effort": 32}
    for field, limit in field_limits.items():
        entry = bounded_optional_string(value[field], f"{context}.{field}")
        if entry is not None and len(entry) > limit:
            raise LearningError(f"{context}.{field} exceeds its schema limit")


def validate_routing_record(value: Any, context: str) -> None:
    expected = {"attempt_id", "task_id", "role", "risk", "requested", "resolved", "fallback_reason", "outcome", "blocked_reason", "rationale", "cost_rank", "reference"}
    if not isinstance(value, dict) or set(value) != expected:
        raise LearningError(f"{context} has invalid fields")
    bounded_string(value["attempt_id"], f"{context}.attempt_id")
    bounded_string(value["task_id"], f"{context}.task_id")
    bounded_string(value["role"], f"{context}.role")
    bounded_optional_string(value["risk"], f"{context}.risk")
    validate_profile_choice_record(value["requested"], f"{context}.requested")
    validate_profile_choice_record(value["resolved"], f"{context}.resolved", allow_none=True)
    for field in ("fallback_reason", "outcome", "blocked_reason", "rationale"):
        bounded_optional_string(value[field], f"{context}.{field}")
    validate_check_number(value["cost_rank"], f"{context}.cost_rank")
    reference = value["reference"]
    if reference is not None:
        if not isinstance(reference, dict) or set(reference) != {"receipt_id", "receipt_path", "sha256"}:
            raise LearningError(f"{context}.reference has invalid fields")
        bounded_string(reference["receipt_id"], f"{context}.reference.receipt_id")
        receipt_path = bounded_string(reference["receipt_path"], f"{context}.reference.receipt_path")
        receipt_hash = bounded_string(reference["sha256"], f"{context}.reference.sha256")
        if not RECEIPT_PATH_PATTERN.fullmatch(receipt_path) or not RECEIPT_HASH_PATTERN.fullmatch(receipt_hash):
            raise LearningError(f"{context}.reference has malformed receipt metadata")


def coordinator_receipt_kind(cleanup_kind: Any, status: Any) -> str:
    if cleanup_kind == "process" and status == "verified":
        return "process"
    if cleanup_kind == "terminal" and status == "verified":
        return "terminal"
    if cleanup_kind == "terminal" and status == "retained":
        return "terminal-retention"
    raise LearningError("coordinator cleanup has an unsupported resource kind or status")


def validate_coordinator_owner(owner: Any, target: Any, cleanup_kind: Any, context: str) -> None:
    if not isinstance(owner, dict) or set(owner) != COORDINATOR_OWNER_FIELDS:
        raise LearningError(f"{context}.owner is not a typed coordinator owner")
    for field in ("execution_host_id", "workspace_key", "provenance"):
        if not isinstance(owner[field], str) or not owner[field].strip():
            raise LearningError(f"{context}.owner.{field} is invalid")
    for field in ("terminal_id", "incarnation_id"):
        if owner[field] is not None and (not isinstance(owner[field], str) or not owner[field].strip()):
            raise LearningError(f"{context}.owner.{field} is invalid")
    if not isinstance(owner["coordinator_generation"], int) or isinstance(owner["coordinator_generation"], bool) or owner["coordinator_generation"] < 1:
        raise LearningError(f"{context}.owner.coordinator_generation is invalid")
    if cleanup_kind == "process":
        if not isinstance(owner["process_root"], int) or isinstance(owner["process_root"], bool) or owner["process_root"] < 1:
            raise LearningError(f"{context}.owner.process_root is invalid")
        if not isinstance(target, dict) or set(target) != {"kind", "root_pid"} or target.get("kind") != "process" or not isinstance(target.get("root_pid"), int) or isinstance(target.get("root_pid"), bool) or target["root_pid"] < 1 or target["root_pid"] != owner["process_root"]:
            raise LearningError(f"{context}.target does not match owner process")
        return
    if cleanup_kind != "terminal":
        raise LearningError(f"{context}.kind is invalid")
    if not isinstance(owner["terminal_id"], str) or not owner["terminal_id"].strip():
        raise LearningError(f"{context}.owner.terminal_id is invalid")
    if not isinstance(owner["incarnation_id"], str) or not owner["incarnation_id"].strip():
        raise LearningError(f"{context}.owner.incarnation_id is invalid")
    if owner["process_root"] is not None and (
        not isinstance(owner["process_root"], int)
        or isinstance(owner["process_root"], bool)
        or owner["process_root"] < 1
    ):
        raise LearningError(f"{context}.owner.process_root is invalid")
    if target != owner["terminal_id"]:
        raise LearningError(f"{context}.target does not match owner terminal")


def coordinator_resource_status(
    owner: Any, target: Any, status: Any, context: str, declared_kind: Any = None
) -> tuple[str, str]:
    """Discriminate and validate one coordinator cleanup resource/status union."""

    if isinstance(target, dict):
        cleanup_kind = "process"
    elif isinstance(target, str):
        cleanup_kind = "terminal"
    else:
        raise LearningError(f"{context}.target has an unsupported coordinator resource shape")
    if declared_kind is not None and declared_kind != cleanup_kind:
        raise LearningError(f"{context}.kind does not match coordinator resource shape")
    validate_coordinator_owner(owner, target, cleanup_kind, context)
    return cleanup_kind, coordinator_receipt_kind(cleanup_kind, status)


def validate_lifecycle_record(value: Any, context: str) -> tuple[str, str, str] | None:
    expected = {"kind", "entity_id", "attempt_id", "phase", "status", "receipt_id", "receipt_path", "sha256", "byte_length"}
    if not isinstance(value, dict) or set(value) != expected:
        raise LearningError(f"{context} has invalid fields")
    if value["kind"] not in {"attempt", "cleanup", "delegation"}:
        raise LearningError(f"{context}.kind is invalid")
    bounded_string(value["entity_id"], f"{context}.entity_id")
    bounded_optional_string(value["attempt_id"], f"{context}.attempt_id")
    bounded_string(value["phase"], f"{context}.phase")
    bounded_string(value["status"], f"{context}.status")
    receipt_values = [value["receipt_id"], value["receipt_path"], value["sha256"], value["byte_length"]]
    if all(entry is None for entry in receipt_values):
        return None
    receipt_id = bounded_optional_string(value["receipt_id"], f"{context}.receipt_id")
    receipt_path = bounded_string(value["receipt_path"], f"{context}.receipt_path")
    receipt_hash = bounded_string(value["sha256"], f"{context}.sha256")
    if not RECEIPT_PATH_PATTERN.fullmatch(receipt_path) or not RECEIPT_HASH_PATTERN.fullmatch(receipt_hash):
        raise LearningError(f"{context} has malformed receipt metadata")
    byte_length = validate_check_number(value["byte_length"], f"{context}.byte_length", positive=True)
    if byte_length is None:
        raise LearningError(f"{context}.byte_length is required")
    return receipt_id, receipt_path, receipt_hash


def validate_visual_scope_record(value: Any, context: str) -> None:
    if not isinstance(value, dict) or set(value) != {"surface", "state", "platforms", "reason"}:
        raise LearningError(f"{context} has invalid fields")
    surface = bounded_string(value["surface"], f"{context}.surface")
    state = bounded_string(value["state"], f"{context}.state")
    platforms = bounded_string_list(value["platforms"], f"{context}.platforms", allow_empty=False)
    reason = bounded_string(value["reason"], f"{context}.reason")
    parse_visual_scope(" | ".join((surface, state, ",".join(platforms), reason)))


def validate_record(record: Any, path: Path) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise LearningError(f"{path} must contain an object")
    required = {
        "schema_version",
        "run_id",
        "change",
        "observed_at",
        "state_ref",
        "state_sha256",
        "outcome",
        "process_telemetry",
        "facts",
        "run_lifecycle_receipts",
        "candidates",
    }
    if record.keys() != required:
        missing = required - record.keys()
        unknown = record.keys() - required
        details = []
        if missing:
            details.append(f"missing {', '.join(sorted(missing))}")
        if unknown:
            details.append(f"unknown {', '.join(sorted(unknown))}")
        raise LearningError(f"{path}: {'; '.join(details)}")
    if record["schema_version"] != SCHEMA_VERSION:
        raise LearningError(f"{path}.schema_version must be {SCHEMA_VERSION}")
    require_identifier(record["run_id"], f"{path}.run_id")
    require_identifier(record["change"], f"{path}.change")
    observed_at = require_string(record["observed_at"], f"{path}.observed_at")
    try:
        parsed_observed_at = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise LearningError(f"{path}.observed_at must be RFC3339") from error
    if parsed_observed_at.tzinfo is None:
        raise LearningError(f"{path}.observed_at must include a timezone")
    require_string(record["state_ref"], f"{path}.state_ref")
    digest = require_string(record["state_sha256"], f"{path}.state_sha256")
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise LearningError(f"{path}.state_sha256 must be a SHA-256 digest")
    if record["outcome"] not in {"pass", "partial", "blocked"}:
        raise LearningError(f"{path}.outcome is invalid")
    process_learning.validate_process_telemetry(record["process_telemetry"])
    facts = record["facts"]
    if not isinstance(facts, list) or not facts or len(facts) > MAX_TASKS:
        raise LearningError(f"{path}.facts must be a non-empty array")
    task_ids: set[str] = set()
    receipt_ids: set[str] = set()
    receipt_paths: set[str] = set()
    receipt_bindings: set[tuple[str, str, str]] = set()
    for index, fact in enumerate(facts):
        context = f"{path}.facts[{index}]"
        if not isinstance(fact, dict):
            raise LearningError(f"{context} must be an object")
        expected_fact_fields = {
            "task_id",
            "status",
            "check_command",
            "check_status",
            "check_attempts",
            "check_exit_code",
            "check_duration_ms",
            "check_total_duration_ms",
            "hypotheses",
            "evidence_refs",
            "visual_expectations",
            "visual_scopes",
            "routing_decisions",
            "lifecycle_receipts",
        }
        if fact.keys() != expected_fact_fields:
            raise LearningError(f"{context} has missing or unknown fields")
        task_id = require_string(fact.get("task_id"), f"{context}.task_id")
        bounded_string(fact.get("task_id"), f"{context}.task_id")
        if task_id in task_ids:
            raise LearningError(f"{path}.facts contains duplicate task ids")
        task_ids.add(task_id)
        if fact.get("status") not in TASK_STATUSES:
            raise LearningError(f"{context}.status is invalid")
        check_command = fact.get("check_command")
        if check_command is not None:
            bounded_string(check_command, f"{context}.check_command")
        if fact.get("check_status") not in {"passed", "failed", "unobserved"}:
            raise LearningError(f"{context}.check_status is invalid")
        attempts = fact.get("check_attempts")
        if validate_check_number(attempts, f"{context}.check_attempts") is None:
            raise LearningError(f"{context}.check_attempts must not be null")
        for field in ("check_exit_code", "check_duration_ms", "check_total_duration_ms"):
            if field == "check_exit_code":
                validate_exit_code(fact[field], f"{context}.{field}")
            else:
                validate_check_number(fact[field], f"{context}.{field}")
        bounded_string_list(fact.get("hypotheses"), f"{context}.hypotheses", allow_empty=True)
        bounded_string_list(fact.get("evidence_refs"), f"{context}.evidence_refs", allow_empty=True)
        bounded_string_list(fact.get("visual_expectations"), f"{context}.visual_expectations", allow_empty=True)
        visual_scopes = fact.get("visual_scopes")
        if not isinstance(visual_scopes, list) or len(visual_scopes) > MAX_LIST_ENTRIES:
            raise LearningError(f"{context}.visual_scopes exceeds the bounded learning record limit")
        for scope_index, scope in enumerate(visual_scopes):
            validate_visual_scope_record(scope, f"{context}.visual_scopes[{scope_index}]")
        routing_decisions = fact["routing_decisions"]
        if not isinstance(routing_decisions, list) or len(routing_decisions) > MAX_LIST_ENTRIES:
            raise LearningError(f"{context}.routing_decisions exceeds the bounded learning record limit")
        for routing_index, routing in enumerate(routing_decisions):
            validate_routing_record(routing, f"{context}.routing_decisions[{routing_index}]")
        lifecycle_receipts = fact["lifecycle_receipts"]
        if not isinstance(lifecycle_receipts, list) or len(lifecycle_receipts) > MAX_LIFECYCLE_ENTRIES:
            raise LearningError(f"{context}.lifecycle_receipts exceeds the bounded learning record limit")
        for lifecycle_index, lifecycle in enumerate(lifecycle_receipts):
            binding = validate_lifecycle_record(lifecycle, f"{context}.lifecycle_receipts[{lifecycle_index}]")
            if binding is not None:
                binding_id, binding_path, binding_hash = binding
                if binding_id is not None and binding_id in receipt_ids:
                    raise LearningError(f"{path} reuses a lifecycle receipt ID")
                if binding_path in receipt_paths or (binding_path, binding_hash) in {(entry[0], entry[1]) for entry in receipt_bindings}:
                    raise LearningError(f"{path} contains duplicate lifecycle receipt binding")
                if binding_id is not None:
                    receipt_ids.add(binding_id)
                receipt_paths.add(binding_path)
                receipt_bindings.add(binding)
    candidates = record["candidates"]
    run_lifecycle = record["run_lifecycle_receipts"]
    if not isinstance(run_lifecycle, list) or len(run_lifecycle) > MAX_LIFECYCLE_ENTRIES:
        raise LearningError(f"{path}.run_lifecycle_receipts exceeds the bounded learning record limit")
    for index, lifecycle in enumerate(run_lifecycle):
        if not isinstance(lifecycle, dict) or set(lifecycle) != {"kind", "entity_id", "attempt_id", "phase", "status", "receipt_id", "receipt_path", "sha256", "byte_length", "owner", "target"}:
            raise LearningError(f"{path}.run_lifecycle_receipts[{index}] has invalid fields")
        if lifecycle["kind"] != "cleanup" or lifecycle["attempt_id"] is not None:
            raise LearningError(f"{path}.run_lifecycle_receipts[{index}] must be run-level cleanup")
        validate_lifecycle_record({key: lifecycle[key] for key in ("kind", "entity_id", "attempt_id", "phase", "status", "receipt_id", "receipt_path", "sha256", "byte_length")}, f"{path}.run_lifecycle_receipts[{index}]")
        owner = lifecycle["owner"]
        target = lifecycle["target"]
        if not isinstance(owner, dict) or set(owner) != COORDINATOR_OWNER_FIELDS:
            raise LearningError(f"{path}.run_lifecycle_receipts[{index}] owner and target are required")
        coordinator_resource_status(
            owner,
            target,
            lifecycle["status"],
            f"{path}.run_lifecycle_receipts[{index}]",
        )
    if not isinstance(candidates, list) or len(candidates) > MAX_LIST_ENTRIES:
        raise LearningError(f"{path}.candidates must be an array")
    seen_keys: set[tuple[str, str]] = set()
    for index, candidate in enumerate(candidates):
        context = f"{path}.candidates[{index}]"
        if not isinstance(candidate, dict):
            raise LearningError(f"{context} must be an object")
        expected = {
            "key",
            "kind",
            "scopes",
            "statement",
            "stance",
            "origin",
            "evidence",
            "task_refs",
        }
        if candidate.keys() != expected:
            raise LearningError(f"{context} has missing or unknown fields")
        key = require_key(candidate["key"], f"{context}.key")
        stance = candidate["stance"]
        if stance not in STANCES:
            raise LearningError(f"{context}.stance is invalid")
        if (key, stance) in seen_keys:
            raise LearningError(f"{path}.candidates repeats {stance} for {key}")
        seen_keys.add((key, stance))
        if candidate["kind"] not in KINDS:
            raise LearningError(f"{context}.kind is invalid")
        scopes = bounded_string_list(candidate["scopes"], f"{context}.scopes", allow_empty=False)
        for scope in scopes:
            require_key(scope, f"{context}.scopes[]")
        bounded_string(candidate["statement"], f"{context}.statement")
        if candidate["origin"] not in ORIGINS:
            raise LearningError(f"{context}.origin is invalid")
        bounded_string(candidate["evidence"], f"{context}.evidence")
        refs = bounded_string_list(candidate["task_refs"], f"{context}.task_refs", allow_empty=False)
        unknown_refs = set(refs) - task_ids
        if unknown_refs:
            raise LearningError(
                f"{context}.task_refs references unknown tasks: {', '.join(sorted(unknown_refs))}"
            )
    return record


def load_records(repo: Path) -> list[tuple[Path, dict[str, Any]]]:
    directory = repo / RUNS_DIRECTORY
    if not directory.exists():
        return []
    records = [(path, validate_record(read_json(path), path)) for path in sorted(directory.glob("*.json"))]
    run_ids = [record["run_id"] for _, record in records]
    if len(run_ids) != len(set(run_ids)):
        raise LearningError(f"{directory} contains duplicate run ids")
    for path, record in records:
        evidence_path = repo_path(repo, record["state_ref"], f"{path}.state_ref")
        if not evidence_path.is_file() or sha256(evidence_path) != record["state_sha256"]:
            raise LearningError(f"{path}: state evidence is missing or has changed")
    return records


def candidate_signature(candidate: dict[str, Any]) -> tuple[str, tuple[str, ...], str]:
    return (
        candidate["kind"],
        tuple(sorted(candidate["scopes"])),
        " ".join(candidate["statement"].split()),
    )


def render_drafts(records: Iterable[tuple[Path, dict[str, Any]]]) -> str:
    grouped: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    for _, record in records:
        for candidate in record["candidates"]:
            grouped[candidate["key"]].append((record, candidate))
    lines = [
        "<!-- Generated by learning.py. Draft evidence only; never loaded by impl. -->",
        "# Draft learning candidates",
        "",
        "> Recurrence is not activation. Every entry requires a reviewed change or a validated executable gate.",
        "> Five independent changes mark a weak recurring sample, not causal proof.",
        "",
    ]
    if not grouped:
        return "\n".join([*lines, "No draft candidates.", ""])
    for key in sorted(grouped):
        occurrences = grouped[key]
        signatures = {candidate_signature(candidate) for _, candidate in occurrences}
        support_changes = {record["change"] for record, candidate in occurrences if candidate["stance"] == "support"}
        oppose_changes = {record["change"] for record, candidate in occurrences if candidate["stance"] == "oppose"}
        if len(signatures) > 1:
            status = "conflicting-definitions"
        elif oppose_changes:
            status = "contested"
        elif len(support_changes) >= MIN_RECURRING_CHANGES:
            status = "recurring-draft"
        else:
            status = "weak-sample"
        first = occurrences[0][1]
        lines.extend(
            [
                f"## {key}",
                "",
                f"Status: `{status}`",
                "",
                f"Kind: `{first['kind']}`",
                "",
                f"Scopes: {', '.join(f'`{scope}`' for scope in sorted(first['scopes']))}",
                "",
                first["statement"],
                "",
                f"Independent support changes: {len(support_changes)}; opposition changes: {len(oppose_changes)}.",
                "",
                "Evidence:",
                "",
            ]
        )
        for record, candidate in sorted(occurrences, key=lambda item: (item[0]["change"], item[0]["run_id"], item[1]["stance"])):
            refs = ", ".join(f"`task:{task_id}`" for task_id in candidate["task_refs"])
            lines.append(
                f"- `{candidate['stance']}` in `{record['change']}` / `{record['run_id']}` "
                f"from `{candidate['origin']}`: {candidate['evidence']} [{refs}]"
            )
        lines.extend(["", "Activation: prohibited in this file.", ""])
    return "\n".join(lines)


def command_snapshot(arguments: argparse.Namespace) -> dict[str, Any]:
    repo = arguments.repo.resolve()
    change = require_identifier(arguments.change, "change")
    change_runs = repo / GRAPH_RUNS_DIRECTORY / change
    if arguments.run_id:
        run_id = require_identifier(arguments.run_id, "run-id")
        state_path = change_runs / run_id / "state.json"
    else:
        candidates = [
            path
            for path in sorted(change_runs.glob("*/state.json"))
            if isinstance((candidate := read_json(path)), dict)
            and candidate.get("status") == "complete"
        ]
        if not candidates:
            raise LearningError(f"no completed graph run exists for {change}")
        if len(candidates) > 1:
            raise LearningError(f"multiple completed graph runs exist for {change}; pass --run-id")
        state_path = candidates[0]
    state = validate_completed_state(read_json(state_path), state_path)
    output = repo / RUNS_DIRECTORY / f"{state['run_id']}.json"
    evidence_path = repo / EVIDENCE_DIRECTORY / f"{state['run_id']}.state.json"
    if output.exists() or evidence_path.exists():
        raise LearningError(f"observation evidence already exists for run {state['run_id']}")
    # Preserve only the bounded, canonical graph facts. The source projection can
    # contain prompts, reports, terminal output, and note bodies; none belongs in
    # shadow learning evidence.
    routing_by_task = routing_facts(state, repo=repo, run_root=state_path.parent)
    lifecycle_by_task, run_lifecycle_receipts = lifecycle_facts(state, repo=repo, run_root=state_path.parent)
    canonical_facts = [
        task_fact(task, routing_by_task.get(task["id"]), lifecycle_by_task.get(task["id"]))
        for task in sorted(state["tasks"], key=lambda value: value["id"])
    ]
    canonical_state = {
        "schema_version": 1,
        "change": state["change"],
        "run_id": state["run_id"],
        "outcome": state["outcome"],
        "process_telemetry": process_learning.build_process_telemetry(state),
        "tasks": canonical_facts,
        "run_lifecycle_receipts": run_lifecycle_receipts,
    }
    state_content = json.dumps(canonical_state, indent=2, sort_keys=True) + "\n"
    atomic_write_text(evidence_path, state_content)
    record = {
        "schema_version": SCHEMA_VERSION,
        "run_id": state["run_id"],
        "change": state["change"],
        "observed_at": now(),
        "state_ref": evidence_path.relative_to(repo).as_posix(),
        "state_sha256": sha256(evidence_path),
        "outcome": state["outcome"],
        "process_telemetry": canonical_state["process_telemetry"],
        "facts": canonical_facts,
        "run_lifecycle_receipts": canonical_state["run_lifecycle_receipts"],
        "candidates": [],
    }
    try:
        validate_record(record, output)
        atomic_write_text(output, json.dumps(record, indent=2) + "\n")
    except BaseException:
        evidence_path.unlink(missing_ok=True)
        raise
    return {
        "record": output.relative_to(repo).as_posix(),
        "evidence": evidence_path.relative_to(repo).as_posix(),
        "candidate_count": 0,
    }


def find_record(repo: Path, run_id: str) -> tuple[Path, dict[str, Any]]:
    path = repo / RUNS_DIRECTORY / f"{require_identifier(run_id, 'run-id')}.json"
    return path, validate_record(read_json(path), path)


def command_add_candidate(arguments: argparse.Namespace) -> dict[str, Any]:
    repo = arguments.repo.resolve()
    path, record = find_record(repo, arguments.run_id)
    candidate = {
        "key": arguments.key,
        "kind": arguments.kind,
        "scopes": sorted(set(arguments.scope)),
        "statement": arguments.statement,
        "stance": arguments.stance,
        "origin": arguments.origin,
        "evidence": arguments.evidence,
        "task_refs": sorted(set(arguments.task_ref)),
    }
    record["candidates"].append(candidate)
    validate_record(record, path)
    atomic_write_text(path, json.dumps(record, indent=2) + "\n")
    return {"record": path.relative_to(repo).as_posix(), "candidate": candidate}


def command_compile(arguments: argparse.Namespace) -> dict[str, Any]:
    repo = arguments.repo.resolve()
    records = load_records(repo)
    output = repo / DRAFTS_FILE
    content = render_drafts(records)
    atomic_write_text(output, content)
    return {"drafts": output.relative_to(repo).as_posix(), "records": len(records)}


def command_check(arguments: argparse.Namespace) -> dict[str, Any]:
    repo = arguments.repo.resolve()
    records = load_records(repo)
    output = repo / DRAFTS_FILE
    expected = render_drafts(records)
    if not output.is_file() or output.read_text(encoding="utf-8") != expected:
        raise LearningError("draft candidates are stale; run learning.py compile")
    return {"records": len(records), "drafts_current": True}


def metrics(state: dict[str, Any]) -> dict[str, int | None]:
    tasks = state["tasks"]
    durations = [
        task["check"].get("total_duration_ms", task["check"].get("duration_ms"))
        for task in tasks
    ]
    return {
        "tasks": len(tasks),
        "passed": sum(task["status"] == "pass" for task in tasks),
        "failed": sum(task["status"] == "fail" for task in tasks),
        "unobserved": sum(task["status"] == "unobserved" for task in tasks),
        "blocked": sum(task["status"] == "blocked" for task in tasks),
        "check_attempts": sum(task["check"]["attempts"] for task in tasks),
        "check_total_duration_ms": (
            sum(durations)
            if all(isinstance(value, int) and not isinstance(value, bool) for value in durations)
            else None
        ),
        "repair_hypotheses": sum(len(task.get("hypotheses", [])) for task in tasks),
    }


def command_compare(arguments: argparse.Namespace) -> dict[str, Any]:
    repo = arguments.repo.resolve()
    off_path = repo_path(repo, arguments.off_state, "off-state")
    on_path = repo_path(repo, arguments.on_state, "on-state")
    off = validate_completed_state(read_json(off_path), off_path)
    on = validate_completed_state(read_json(on_path), on_path)
    off_contracts = [(task["id"], task["check"].get("command")) for task in off["tasks"]]
    on_contracts = [(task["id"], task["check"].get("command")) for task in on["tasks"]]
    if off_contracts != on_contracts:
        raise LearningError("memory-off and memory-on states must use identical task checks")
    off_metrics = metrics(off)
    on_metrics = metrics(on)
    delta = {
        key: (
            on_metrics[key] - off_metrics[key]
            if isinstance(on_metrics[key], int) and isinstance(off_metrics[key], int)
            else None
        )
        for key in off_metrics
        if key != "tasks"
    }
    return {
        "candidate": require_key(arguments.candidate, "candidate"),
        "memory_off": off_metrics,
        "memory_on": on_metrics,
        "delta_on_minus_off": delta,
        "interpretation": "No automatic verdict. Reject on regression, no gain, or excess cost.",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage shadow-mode impl learning evidence.")
    add_runtime_arguments(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot = subparsers.add_parser("snapshot")
    snapshot.add_argument("--change", required=True)
    snapshot.add_argument("--run-id")
    snapshot.set_defaults(handler=command_snapshot)

    add_candidate = subparsers.add_parser("add-candidate")
    add_candidate.add_argument("--run-id", required=True)
    add_candidate.add_argument("--key", required=True)
    add_candidate.add_argument("--kind", choices=sorted(KINDS), required=True)
    add_candidate.add_argument("--scope", action="append", required=True)
    add_candidate.add_argument("--statement", required=True)
    add_candidate.add_argument("--stance", choices=sorted(STANCES), required=True)
    add_candidate.add_argument("--origin", choices=sorted(ORIGINS), required=True)
    add_candidate.add_argument("--evidence", required=True)
    add_candidate.add_argument("--task-ref", action="append", required=True)
    add_candidate.set_defaults(handler=command_add_candidate)

    compile_parser = subparsers.add_parser("compile")
    compile_parser.set_defaults(handler=command_compile)

    check = subparsers.add_parser("check")
    check.set_defaults(handler=command_check)

    compare = subparsers.add_parser("compare")
    compare.add_argument("--candidate", required=True)
    compare.add_argument("--off-state", required=True)
    compare.add_argument("--on-state", required=True)
    compare.set_defaults(handler=command_compare)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        runtime = runtime_from_arguments(arguments)
        arguments.repo = runtime.project_directory
        result = arguments.handler(arguments)
    except (LearningError, RuntimeConfigError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
