#!/usr/bin/env python3
"""Build bounded, shadow-only process telemetry from canonical run state."""

from __future__ import annotations

import json
from typing import Any, Mapping


MAX_PROVIDER_FIELDS = 32
MAX_TEXT = 512


class ProcessTelemetryError(ValueError):
    """Reports provider telemetry that is not safe to preserve."""


def unavailable(*, unit: str | None, reason: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "value": None,
        "unit": unit,
        "source": None,
        "reason": reason,
    }


def observed(value: Any, *, unit: str | None, source: str) -> dict[str, Any]:
    if value is None:
        raise ProcessTelemetryError("observed telemetry requires a value")
    return {
        "status": "observed",
        "value": value,
        "unit": unit,
        "source": source,
        "reason": None,
    }


def _validate_value(value: Any, context: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str, list, dict)):
        raise ProcessTelemetryError(f"{context} has an unsupported observed value")
    if isinstance(value, str) and (not value or len(value) > MAX_TEXT):
        raise ProcessTelemetryError(f"{context} exceeds its text bound")
    if isinstance(value, list):
        if len(value) > 256:
            raise ProcessTelemetryError(f"{context} exceeds its array bound")
        for index, item in enumerate(value):
            if not isinstance(item, Mapping) or len(item) > MAX_PROVIDER_FIELDS:
                raise ProcessTelemetryError(f"{context}[{index}] must be a bounded object")
            for key, entry in item.items():
                if not isinstance(key, str) or not key or len(key) > 64:
                    raise ProcessTelemetryError(f"{context}[{index}] has an invalid key")
                if isinstance(entry, Mapping):
                    _bounded_provider_fields(entry, f"{context}[{index}].{key}")
                elif entry is not None:
                    _validate_value(entry, f"{context}[{index}].{key}")
    if isinstance(value, dict):
        _bounded_provider_fields(value, context)


def validate_process_telemetry(value: Any) -> dict[str, Any]:
    required = {
        "policy",
        "mode",
        "result",
        "retry",
        "time",
        "rework",
        "coordination_overhead",
        "provider_usage",
        "provider_cache",
        "profiles",
    }
    if not isinstance(value, Mapping) or set(value) != required or value.get("policy") != "shadow_only":
        raise ProcessTelemetryError("process telemetry has missing or unknown fields")
    for field in required - {"policy"}:
        observation = value[field]
        if not isinstance(observation, Mapping) or set(observation) != {"status", "value", "unit", "source", "reason"}:
            raise ProcessTelemetryError(f"process telemetry {field} has invalid fields")
        status = observation["status"]
        if status == "unavailable":
            if observation["value"] is not None or observation["source"] is not None:
                raise ProcessTelemetryError(f"unavailable process telemetry {field} cannot carry a value or source")
            if not isinstance(observation["reason"], str) or not observation["reason"]:
                raise ProcessTelemetryError(f"unavailable process telemetry {field} requires a reason")
        elif status == "observed":
            if not isinstance(observation["source"], str) or not observation["source"] or observation["reason"] is not None:
                raise ProcessTelemetryError(f"observed process telemetry {field} requires a source and no reason")
            _validate_value(observation["value"], f"process telemetry {field}")
        else:
            raise ProcessTelemetryError(f"process telemetry {field} has an invalid status")
        if observation["unit"] is not None and (
            not isinstance(observation["unit"], str) or not observation["unit"]
        ):
            raise ProcessTelemetryError(f"process telemetry {field} has an invalid unit")
    return json.loads(json.dumps(dict(value), sort_keys=True))


def _bounded_provider_fields(value: Any, context: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping) or not value or len(value) > MAX_PROVIDER_FIELDS:
        raise ProcessTelemetryError(f"{context} must be a bounded non-empty object")
    result: dict[str, Any] = {}
    for key, entry in sorted(value.items()):
        if not isinstance(key, str) or not key or len(key) > 64:
            raise ProcessTelemetryError(f"{context} contains an invalid field name")
        if isinstance(entry, bool) or not isinstance(entry, (int, float, str)):
            raise ProcessTelemetryError(f"{context}.{key} must be a provider-reported scalar")
        if isinstance(entry, (int, float)) and entry < 0:
            raise ProcessTelemetryError(f"{context}.{key} must be non-negative")
        if isinstance(entry, str) and (not entry or len(entry) > MAX_TEXT):
            raise ProcessTelemetryError(f"{context}.{key} exceeds its text bound")
        result[key] = entry
    return result


def _provider_observation(
    attempts: Mapping[str, Any], field: str
) -> dict[str, Any]:
    reported: list[dict[str, Any]] = []
    for attempt_id, attempt in sorted(attempts.items()):
        telemetry = attempt.get("provider_telemetry") if isinstance(attempt, Mapping) else None
        value = telemetry.get(field) if isinstance(telemetry, Mapping) else None
        normalized = _bounded_provider_fields(value, f"attempt {attempt_id} {field}")
        if normalized is not None:
            reported.append({"attempt_id": str(attempt_id), "fields": normalized})
    if not reported:
        return unavailable(
            unit=None,
            reason=f"No provider exposed {field} telemetry for this run.",
        )
    return observed(reported, unit=None, source="provider_receipts")


def _profile_observation(attempts: Mapping[str, Any]) -> dict[str, Any]:
    profiles: list[dict[str, Any]] = []
    for attempt_id, attempt in sorted(attempts.items()):
        profile = attempt.get("execution_profile") if isinstance(attempt, Mapping) else None
        resolved = profile.get("resolved") if isinstance(profile, Mapping) else None
        if not isinstance(resolved, Mapping):
            continue
        fields = {
            key: resolved.get(key)
            for key in ("agent", "model", "effort")
            if resolved.get(key) is not None
        }
        if fields:
            profiles.append(
                {
                    "attempt_id": str(attempt_id),
                    "role": profile.get("role"),
                    "resolved": fields,
                }
            )
    if not profiles:
        return unavailable(unit=None, reason="No resolved execution profile was recorded.")
    return observed(profiles, unit=None, source="execution_profiles")


def build_process_telemetry(state: Mapping[str, Any]) -> dict[str, Any]:
    """Derive process facts and preserve only provider-reported optional metrics."""

    tasks = state.get("tasks")
    attempts = state.get("attempts", {})
    if not isinstance(tasks, list) or not isinstance(attempts, Mapping):
        raise ProcessTelemetryError("process telemetry requires normalized tasks and attempts")

    checks = [task.get("check", {}) for task in tasks if isinstance(task, Mapping)]
    attempt_counts = [check.get("attempts") for check in checks if isinstance(check, Mapping)]
    retry = (
        observed(sum(max(value - 1, 0) for value in attempt_counts), unit="attempts", source="task_checks")
        if len(attempt_counts) == len(tasks)
        and all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in attempt_counts)
        else unavailable(unit="attempts", reason="Check attempt counts were incomplete.")
    )
    durations = [check.get("total_duration_ms") for check in checks if isinstance(check, Mapping)]
    elapsed = (
        observed(sum(durations), unit="milliseconds", source="task_checks")
        if len(durations) == len(tasks)
        and all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in durations)
        else unavailable(unit="milliseconds", reason="Check duration telemetry was incomplete.")
    )
    hypotheses = [task.get("hypotheses") for task in tasks if isinstance(task, Mapping)]
    rework = (
        observed(sum(len(value) for value in hypotheses), unit="hypotheses", source="task_journal")
        if len(hypotheses) == len(tasks) and all(isinstance(value, list) for value in hypotheses)
        else unavailable(unit="hypotheses", reason="Repair hypothesis records were incomplete.")
    )
    sequence = state.get("last_sequence")
    coordination = (
        observed(sequence, unit="journal_events", source="event_journal")
        if isinstance(sequence, int) and not isinstance(sequence, bool) and sequence >= 0
        else unavailable(unit="journal_events", reason="The run did not expose a journal sequence.")
    )
    decision = state.get("process_decision")
    mode_value = decision.get("mode") if isinstance(decision, Mapping) else "graph"

    telemetry = {
        "policy": "shadow_only",
        "mode": observed(mode_value, unit=None, source="process_decision" if isinstance(decision, Mapping) else "graph_run"),
        "result": observed(state.get("outcome"), unit=None, source="run_projection"),
        "retry": retry,
        "time": elapsed,
        "rework": rework,
        "coordination_overhead": coordination,
        "provider_usage": _provider_observation(attempts, "usage"),
        "provider_cache": _provider_observation(attempts, "cache"),
        "profiles": _profile_observation(attempts),
    }
    return validate_process_telemetry(telemetry)
