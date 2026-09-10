#!/usr/bin/env python3
"""Admission budgets derived from journal facts, never guessed provider usage."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any, Mapping, Sequence


ACTIVE_STATUSES = frozenset({"reserved", "running", "interrupted"})
SETTLED_CLEANUP = frozenset({"done", "verified", "retained"})
TIME_UNITS = {"seconds": 1, "s": 1, "milliseconds": 1000, "ms": 1000, "minutes": 1 / 60, "min": 1 / 60}


def finite_nonnegative(value: Any) -> bool:
    return (
        isinstance(value, int) and not isinstance(value, bool) and value >= 0
    ) or (isinstance(value, float) and math.isfinite(value) and value >= 0)


def evaluate_limits(limits: Sequence[Mapping[str, Any]], usage: Mapping[str, Any]) -> dict[str, list[str]]:
    """Evaluate measurements already expressed in each declared limit's units.

    This is admission control, not a guarantee that an in-flight model request
    cannot exceed a monetary threshold. Missing usage never means zero.
    """

    result: dict[str, list[str]] = {"blocking": [], "advisory": [], "unavailable": []}
    seen: set[str] = set()
    for limit in limits:
        resource = limit["resource"]
        if resource in seen:
            raise ValueError("budget resources must be unique; units cannot be combined implicitly")
        seen.add(resource)
        maximum = limit["value"]
        if not finite_nonnegative(maximum) or maximum == 0:
            raise ValueError("budget limits must be finite and positive")
        enforcement = limit.get("enforcement", "legacy")
        if enforcement not in {"hard", "advisory", "legacy"}:
            raise ValueError("unsupported budget enforcement")
        value = usage.get(resource)
        if not finite_nonnegative(value):
            result["unavailable"].append(resource)
            reason = f"budget_unavailable:{resource}"
            result["blocking" if enforcement == "hard" else "advisory"].append(reason)
        elif value >= maximum:
            reason = f"budget_exhausted:{resource}"
            result["advisory" if enforcement == "advisory" else "blocking"].append(reason)
    return result


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return result if result.tzinfo is not None else None


def observe_admission(
    projection: Mapping[str, Any], events: Sequence[Mapping[str, Any]],
    *, now: datetime | None = None,
) -> dict[str, Any]:
    """Count total reservations and current worker obligations under the journal lock."""

    decision = projection.get("process_decision")
    if not isinstance(decision, Mapping):
        return {"blocking": [], "advisory": [], "unavailable": [], "usage": {}}
    attempts = projection.get("attempts", {})
    if not isinstance(attempts, Mapping):
        raise ValueError("budget observation requires an attempt mapping")
    active = {
        attempt_id for attempt_id, attempt in attempts.items()
        if isinstance(attempt, Mapping) and attempt.get("status") in ACTIVE_STATUSES
    }
    for obligation in projection.get("cleanup", {}).values():
        if not isinstance(obligation, Mapping) or obligation.get("status") in SETTLED_CLEANUP:
            continue
        owner = obligation.get("owner")
        attempt_id = obligation.get("attempt_id") or (owner.get("attempt_id") if isinstance(owner, Mapping) else owner)
        if attempt_id in attempts:
            active.add(attempt_id)
    started = _timestamp(events[0].get("timestamp")) if events else None
    current = now or datetime.now(UTC)
    elapsed = (current - started).total_seconds() if started is not None and current.tzinfo is not None and current >= started else None
    limits = decision["budget"]["limits"]
    usage: dict[str, Any] = {}
    for limit in limits:
        resource, unit = limit["resource"], limit["unit"]
        if resource == "attempts" and unit == "attempts":
            usage[resource] = len(attempts)
        elif resource == "workers" and unit == "workers":
            usage[resource] = len(active)
        elif resource == "wall_time" and unit in TIME_UNITS and elapsed is not None:
            usage[resource] = elapsed * TIME_UNITS[unit]
        # Provider tokens, cache, spend and tool costs are deliberately not
        # inferred from worker lifetime, event count, or a partial receipt.
    assessment = evaluate_limits(limits, usage)
    # Counters reserve one indivisible slot; reject fractional oversubscription.
    for limit in limits:
        resource = limit["resource"]
        value = usage.get(resource)
        if resource in {"attempts", "workers"} and finite_nonnegative(value) and value < limit["value"] < value + 1:
            bucket = "advisory" if limit.get("enforcement") == "advisory" else "blocking"
            assessment[bucket].append(f"budget_exhausted:{resource}")
    return {**assessment, "usage": usage}
