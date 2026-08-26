#!/usr/bin/env python3
"""Bounded, journal-derived run-progress projection."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Mapping


SUMMARY_SCHEMA_VERSION = 1
TASK_COUNT_KEYS = ("approved", "running", "input_required", "blocked", "pending", "failed")
CLEANUP_STATUS_KEYS = ("pending", "unverifiable", "failed", "retained")
RUN_STATES = frozenset({"active", "input_required", "blocked", "partial", "complete", "failed", "outcome_unknown"})
MAX_TASK_REFS = 3
MAX_CLEANUP_IDS = 5
MAX_REFERENCES = 5


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _identity(*, task_id: Any = None, attempt_id: Any = None, finding_ref: Any = None, cleanup_id: Any = None) -> dict[str, str | None]:
    return {
        "task_id": task_id if isinstance(task_id, str) else None,
        "attempt_id": attempt_id if isinstance(attempt_id, str) else None,
        "finding_ref": finding_ref if isinstance(finding_ref, str) else None,
        "cleanup_id": cleanup_id if isinstance(cleanup_id, str) else None,
    }


def _identity_sort_key(identity: Mapping[str, str | None]) -> str:
    return json.dumps(
        [identity["task_id"], identity["attempt_id"], identity["finding_ref"], identity["cleanup_id"]],
        separators=(",", ":"),
    )


def _latest_attempt_id(task: Mapping[str, Any]) -> str | None:
    attempt_ids = task.get("attempt_ids")
    if not isinstance(attempt_ids, list):
        return None
    for attempt_id in reversed(attempt_ids):
        if isinstance(attempt_id, str):
            return attempt_id
    return None


def _task_category(task: Mapping[str, Any], *, input_required: bool) -> str:
    grade = task.get("grade")
    if grade == "pass":
        return "approved"
    if grade == "fail":
        return "failed"
    if grade in {"blocked", "unobserved"} or task.get("status") == "blocked":
        return "blocked"
    if input_required:
        return "input_required"
    if task.get("status") in {"reserved", "running", "reported", "interrupted"}:
        return "running"
    return "pending"


def _open_question_attempt_ids(projection: Mapping[str, Any]) -> set[str]:
    questions = _mapping(projection.get("questions"))
    return {
        str(question.get("attempt_id"))
        for question in questions.values()
        if isinstance(question, Mapping)
        and question.get("status") == "open"
        and isinstance(question.get("attempt_id"), str)
    }


def _task_refs(tasks: Mapping[str, Any], attempts: Mapping[str, Any], categories: Mapping[str, str], selected: set[str]) -> list[dict[str, str | None]]:
    refs: list[dict[str, str | None]] = []
    for task_id in sorted(task_id for task_id in tasks if isinstance(task_id, str)):
        if categories.get(task_id) not in selected:
            continue
        task = _mapping(tasks[task_id])
        attempt_id = _latest_attempt_id(task)
        if attempt_id is not None and attempt_id not in attempts:
            attempt_id = None
        refs.append({"task_id": task_id, "attempt_id": attempt_id, "status": categories[task_id]})
    return refs[:MAX_TASK_REFS]


def _cleanup_summary(projection: Mapping[str, Any]) -> tuple[dict[str, dict[str, Any]], list[dict[str, str | None]]]:
    cleanup = _mapping(projection.get("cleanup"))
    groups = {status: [] for status in CLEANUP_STATUS_KEYS}
    blockers: list[dict[str, str | None]] = []
    for cleanup_id in sorted(cleanup_id for cleanup_id in cleanup if isinstance(cleanup_id, str)):
        record = cleanup[cleanup_id]
        value = _mapping(record)
        status = value.get("status") if isinstance(record, Mapping) else "failed"
        if status in {"done", "verified"}:
            continue
        group = status if status in groups else "failed"
        groups[group].append(cleanup_id)
        if group in {"pending", "unverifiable", "failed"}:
            owner = _mapping(value.get("owner"))
            blockers.append(_identity(task_id=value.get("task_id"), attempt_id=value.get("attempt_id") or owner.get("attempt_id"), cleanup_id=cleanup_id))
    return (
        {
            status: {"count": len(ids), "ids": ids[:MAX_CLEANUP_IDS], "truncated": len(ids) > MAX_CLEANUP_IDS}
            for status, ids in groups.items()
        },
        blockers,
    )


def _finding_refs(projection: Mapping[str, Any], tasks: Mapping[str, Any], attempts: Mapping[str, Any]) -> tuple[list[dict[str, str | None]], bool, bool]:
    findings: list[dict[str, str | None]] = []
    material_blocker = False
    carry_forward = False
    for attempt_id in sorted(attempt_id for attempt_id in attempts if isinstance(attempt_id, str)):
        attempt = _mapping(attempts[attempt_id])
        task_id = attempt.get("task_id")
        task = _mapping(tasks.get(task_id))
        latest = _latest_attempt_id(task)
        audit = attempt.get("audit_exhaustion")
        if isinstance(audit, Mapping):
            material_blocker = True
        if not isinstance(audit, Mapping) and latest == attempt_id and task.get("grade") is None:
            audit = attempt.get("audit_rejection")
        if isinstance(audit, Mapping):
            references = audit.get("finding_refs")
            if isinstance(references, list):
                findings.extend(_identity(task_id=task_id, attempt_id=attempt_id, finding_ref=reference) for reference in references if isinstance(reference, str))
    for degradation in projection.get("degradations", []):
        degradation = _mapping(degradation)
        if degradation.get("status") != "carry_forward":
            continue
        carry_forward = True
        references = degradation.get("finding_refs")
        if isinstance(references, list):
            findings.extend(_identity(task_id=degradation.get("task_id"), attempt_id=degradation.get("attempt_id"), finding_ref=reference, cleanup_id=degradation.get("cleanup_id")) for reference in references if isinstance(reference, str))
        elif any(isinstance(degradation.get(key), str) for key in ("task_id", "attempt_id", "cleanup_id")):
            findings.append(_identity(task_id=degradation.get("task_id"), attempt_id=degradation.get("attempt_id"), cleanup_id=degradation.get("cleanup_id")))
    unique = {_identity_sort_key(item): item for item in findings}
    return [unique[key] for key in sorted(unique)][:MAX_REFERENCES], material_blocker, carry_forward


def _has_canonical_uncertainty(projection: Mapping[str, Any]) -> bool:
    tasks = _mapping(projection.get("tasks"))
    cleanup = _mapping(projection.get("cleanup"))
    return any(_mapping(task).get("grade") == "unobserved" for task in tasks.values()) or any(
        _mapping(record).get("status") == "unverifiable" for record in cleanup.values()
    )


def _last_activity(event: Mapping[str, Any] | None, projection: Mapping[str, Any]) -> dict[str, Any] | None:
    if not isinstance(event, Mapping):
        return None
    sequence = event.get("sequence")
    timestamp = event.get("timestamp")
    event_type = event.get("type")
    if (
        not isinstance(sequence, int)
        or isinstance(sequence, bool)
        or sequence != projection.get("last_sequence")
    ):
        return None
    if not isinstance(timestamp, str) or not isinstance(event_type, str):
        return None
    return {"sequence": sequence, "timestamp": timestamp, "type": event_type}


def _event_timestamp(event: Mapping[str, Any]) -> datetime | None:
    value = event.get("timestamp")
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _coordination_metrics(projection: Mapping[str, Any], events: list[Mapping[str, Any]]) -> dict[str, Any]:
    attempts = _mapping(projection.get("attempts"))
    checks = [attempt.get("check") for attempt in attempts.values() if isinstance(attempt, Mapping) and isinstance(attempt.get("check"), Mapping)]
    check_wall = sum(check.get("duration_ms", 0) for check in checks if isinstance(check.get("duration_ms"), int) and not isinstance(check.get("duration_ms"), bool))
    starts = {str(event.get("data", {}).get("attempt_id")): _event_timestamp(event) for event in events if event.get("type") == "attempt_started" and isinstance(event.get("data"), Mapping)}
    ends: dict[str, datetime | None] = {}
    reported: set[str] = set()
    for event in events:
        if event.get("type") not in {"worker_reported", "attempt_abandoned"} or not isinstance(event.get("data"), Mapping):
            continue
        attempt_id = str(event["data"].get("attempt_id"))
        if attempt_id not in ends:
            ends[attempt_id] = _event_timestamp(event)
        if event.get("type") == "worker_reported":
            reported.add(attempt_id)
    implementation = [int((ends[key] - start).total_seconds() * 1000) for key, start in starts.items() if start is not None and ends.get(key) is not None and ends[key] >= start]
    check_started: dict[str, tuple[str, datetime]] = {}
    audit_intervals: list[int] = []
    for event in events:
        data = _mapping(event.get("data"))
        timestamp = _event_timestamp(event)
        if timestamp is None:
            continue
        if event.get("type") == "check_recorded":
            task_id, attempt_id = data.get("task_id"), data.get("attempt_id")
            if isinstance(task_id, str) and isinstance(attempt_id, str):
                check_started[task_id] = (attempt_id, timestamp)
            continue
        task_id = data.get("task_id")
        attempt_id = data.get("attempt_id")
        if event.get("type") == "task_graded" and isinstance(task_id, str) and task_id in check_started:
            attempt_id = check_started[task_id][0]
        if event.get("type") not in {"attempt_audit_rejected", "attempt_audit_exhausted", "task_graded"} or not isinstance(task_id, str) or task_id not in check_started:
            continue
        checked_attempt, started = check_started[task_id]
        if attempt_id == checked_attempt and timestamp >= started:
            audit_intervals.append(int((timestamp - started).total_seconds() * 1000))
            del check_started[task_id]
    event_types = [event.get("type") for event in events]
    return {
        "execution_mode": projection.get("execution_mode", "single_writer"),
        "latest_transition_reason": _mapping(projection.get("reduction")).get("reason"),
        "implementation_wall_time_ms": sum(implementation) if implementation else "unavailable",
        "check_wall_time_ms": check_wall,
        "coordinator_wait_for_worker_wall_time_ms": sum(implementation) if implementation else "unavailable",
        "audit_wall_time_ms": sum(audit_intervals) if audit_intervals else "unavailable",
        "dispatch_count": sum(kind == "attempt_started" for kind in event_types),
        "operational_start_failures": sum(kind == "attempt_start_failed" for kind in event_types) + sum(event.get("type") == "attempt_abandoned" and str(_mapping(event.get("data")).get("attempt_id")) not in reported and not isinstance(_mapping(attempts.get(str(_mapping(event.get("data")).get("attempt_id")))).get("check"), Mapping) for event in events),
        "technical_attempts": sum(1 for attempt in attempts.values() if isinstance(attempt, Mapping) and (isinstance(attempt.get("report"), Mapping) or isinstance(attempt.get("check"), Mapping))),
        "token_input": "unavailable", "token_output": "unavailable", "token_cache": "unavailable",
        "approved_tasks": 0, "blocking_findings": 0, "carry_forward_findings": 0,
        "durations_diagnostic": True,
    }


def build_run_progress_summary(projection: Mapping[str, Any], *, last_event: Mapping[str, Any] | None = None, events: list[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Project stable progress only from reducer state and the latest journal envelope."""

    tasks = _mapping(projection.get("tasks"))
    attempts = _mapping(projection.get("attempts"))
    open_attempts = _open_question_attempt_ids(projection)
    categories: dict[str, str] = {}
    counts = {key: 0 for key in TASK_COUNT_KEYS}
    for task_id in sorted(task_id for task_id in tasks if isinstance(task_id, str)):
        task = _mapping(tasks[task_id])
        category = _task_category(task, input_required=_latest_attempt_id(task) in open_attempts)
        categories[task_id] = category
        counts[category] += 1
    cleanup, cleanup_blockers = _cleanup_summary(projection)
    findings, material_blocker, carry_forward = _finding_refs(projection, tasks, attempts)
    task_blockers = [
        _identity(task_id=task_id, attempt_id=_latest_attempt_id(_mapping(tasks[task_id])))
        for task_id in sorted(categories)
        if categories[task_id] in {"blocked", "failed", "input_required"}
    ]
    blocker_map = {_identity_sort_key(item): item for item in task_blockers + cleanup_blockers}
    blockers = [blocker_map[key] for key in sorted(blocker_map)][:MAX_REFERENCES]
    unresolved_cleanup = sum(cleanup[key]["count"] for key in ("pending", "unverifiable", "failed"))
    has_material_finding = bool(findings)
    outcome = projection.get("outcome")
    status = projection.get("status")
    clean_terminal_pass = (
        status == "complete"
        and outcome == "pass"
        and counts["approved"] == len(tasks)
        and not counts["blocked"]
        and not counts["failed"]
        and not counts["input_required"]
        and not unresolved_cleanup
        and not has_material_finding
        and not carry_forward
    )
    if clean_terminal_pass:
        state = "complete"
    elif status == "complete" and counts["failed"]:
        state = "failed"
    elif status == "complete" and (outcome == "partial" or carry_forward):
        state = "partial"
    elif _has_canonical_uncertainty(projection):
        state = "outcome_unknown"
    elif counts["blocked"] or counts["failed"] or material_blocker or cleanup["failed"]["count"] or outcome == "blocked":
        state = "blocked"
    elif counts["input_required"]:
        state = "input_required"
    else:
        state = "active"
    approved = counts["approved"]
    percent = (approved * 100 // len(tasks)) if tasks else 0
    if state != "complete":
        percent = min(percent, 99)
    coordination = _coordination_metrics(projection, events or [])
    coordination.update({"approved_tasks": approved, "blocking_findings": len(findings), "carry_forward_findings": int(carry_forward)})
    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "state": state,
        "progress_percent": percent,
        "task_counts": counts,
        "current_tasks": _task_refs(tasks, attempts, categories, {"running", "input_required", "blocked", "failed"}),
        "next_tasks": _task_refs(tasks, attempts, categories, {"pending"}),
        "cleanup": cleanup,
        "last_activity": _last_activity(last_event, projection),
        "blockers": blockers,
        "material_findings": findings,
        "coordination": coordination,
    }


def validate_run_progress_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    """Reject unbounded or non-deterministic public progress summaries."""

    required = {"schema_version", "state", "progress_percent", "task_counts", "current_tasks", "next_tasks", "cleanup", "last_activity", "blockers", "material_findings"}
    allowed = required | {"coordination"}
    if not isinstance(summary, Mapping) or (set(summary) != required and set(summary) != allowed):
        raise ValueError("run progress summary has an invalid shape")
    if (
        not isinstance(summary["schema_version"], int)
        or isinstance(summary["schema_version"], bool)
        or summary["schema_version"] != SUMMARY_SCHEMA_VERSION
        or summary["state"] not in RUN_STATES
    ):
        raise ValueError("run progress summary has an unsupported version or state")
    if (
        not isinstance(summary["progress_percent"], int)
        or isinstance(summary["progress_percent"], bool)
        or not 0 <= summary["progress_percent"] <= 100
    ):
        raise ValueError("run progress summary progress_percent is invalid")
    if summary["state"] != "complete" and summary["progress_percent"] == 100:
        raise ValueError("only a complete run may display 100 percent")
    counts = summary["task_counts"]
    if not isinstance(counts, Mapping) or set(counts) != set(TASK_COUNT_KEYS) or any(
        not isinstance(counts[key], int)
        or isinstance(counts[key], bool)
        or counts[key] < 0
        for key in TASK_COUNT_KEYS
    ):
        raise ValueError("run progress summary task counts are invalid")
    for field, limit in (("current_tasks", MAX_TASK_REFS), ("next_tasks", MAX_TASK_REFS), ("blockers", MAX_REFERENCES), ("material_findings", MAX_REFERENCES)):
        values = summary[field]
        if not isinstance(values, list) or len(values) > limit:
            raise ValueError(f"run progress summary {field} exceeds its bound")
        for value in values:
            if not isinstance(value, Mapping):
                raise ValueError(f"run progress summary {field} contains an invalid reference")
            if field in {"current_tasks", "next_tasks"}:
                if set(value) != {"task_id", "attempt_id", "status"}:
                    raise ValueError("run progress task reference has an invalid shape")
                if not isinstance(value.get("task_id"), str) or value.get("attempt_id") is not None and not isinstance(value.get("attempt_id"), str) or value.get("status") not in {"running", "input_required", "blocked", "pending", "failed"}:
                    raise ValueError("run progress task reference has invalid values")
            elif set(value) != {"task_id", "attempt_id", "finding_ref", "cleanup_id"}:
                raise ValueError("run progress identity reference has an invalid shape")
            elif not any(isinstance(value.get(key), str) for key in ("task_id", "attempt_id", "finding_ref", "cleanup_id")) or any(value.get(key) is not None and not isinstance(value.get(key), str) for key in ("task_id", "attempt_id", "finding_ref", "cleanup_id")):
                raise ValueError("run progress identity reference has invalid values")
    cleanup = summary["cleanup"]
    if not isinstance(cleanup, Mapping) or set(cleanup) != set(CLEANUP_STATUS_KEYS):
        raise ValueError("run progress cleanup summary is invalid")
    for value in cleanup.values():
        if not isinstance(value, Mapping) or set(value) != {"count", "ids", "truncated"} or not isinstance(value["count"], int) or isinstance(value["count"], bool) or value["count"] < 0 or not isinstance(value["ids"], list) or len(value["ids"]) > MAX_CLEANUP_IDS or any(not isinstance(item, str) for item in value["ids"]) or len(set(value["ids"])) != len(value["ids"]) or value["count"] < len(value["ids"]) or not isinstance(value["truncated"], bool) or value["truncated"] != (value["count"] > len(value["ids"])):
            raise ValueError("run progress cleanup group is invalid")
    coordination = summary.get("coordination")
    if coordination is None:
        return json.loads(json.dumps(dict(summary), sort_keys=True))
    coordination_fields = {
        "execution_mode", "latest_transition_reason", "implementation_wall_time_ms",
        "check_wall_time_ms", "coordinator_wait_for_worker_wall_time_ms",
        "audit_wall_time_ms", "dispatch_count", "operational_start_failures",
        "technical_attempts", "token_input", "token_output", "token_cache",
        "approved_tasks", "blocking_findings", "carry_forward_findings",
        "durations_diagnostic",
    }
    if not isinstance(coordination, Mapping) or set(coordination) != coordination_fields:
        raise ValueError("run progress coordination is invalid")
    if coordination["execution_mode"] not in {"single_writer", "parallel"} or coordination["latest_transition_reason"] is not None and not isinstance(coordination["latest_transition_reason"], str):
        raise ValueError("run progress coordination mode is invalid")
    duration_fields = ("implementation_wall_time_ms", "check_wall_time_ms", "coordinator_wait_for_worker_wall_time_ms", "audit_wall_time_ms")
    if any(coordination[field] != "unavailable" and (not isinstance(coordination[field], int) or isinstance(coordination[field], bool) or coordination[field] < 0) for field in duration_fields) or any(coordination[field] != "unavailable" for field in ("token_input", "token_output", "token_cache")):
        raise ValueError("run progress coordination availability is invalid")
    if any(not isinstance(coordination[field], int) or isinstance(coordination[field], bool) or coordination[field] < 0 for field in ("dispatch_count", "operational_start_failures", "technical_attempts", "approved_tasks", "blocking_findings", "carry_forward_findings")) or coordination["durations_diagnostic"] is not True:
        raise ValueError("run progress coordination metrics are invalid")
    activity = summary["last_activity"]
    if activity is not None and (not isinstance(activity, Mapping) or set(activity) != {"sequence", "timestamp", "type"} or not isinstance(activity.get("sequence"), int) or isinstance(activity.get("sequence"), bool) or activity["sequence"] < 1 or not isinstance(activity.get("timestamp"), str) or not isinstance(activity.get("type"), str)):
        raise ValueError("run progress last activity is invalid")
    return json.loads(json.dumps(dict(summary), sort_keys=True))
