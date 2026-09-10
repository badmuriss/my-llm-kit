#!/usr/bin/env python3
"""Bounded provider synchronization without model-mediated empty polling."""

from __future__ import annotations

import hashlib
import json
import math
import time
from typing import Any, Callable, Mapping


def semantic_fingerprint(state: Mapping[str, Any]) -> str:
    """Ignore polling cursors/receipts, never contracts, findings or ownership."""

    payload = {key: state.get(key) for key in (
        "status", "outcome", "coordinator", "tasks", "questions", "cleanup",
        "process_decision", "degradations", "findings", "execution_mode", "reduction",
    )}
    payload["attempts"] = {
        key: {field: value for field, value in attempt.items()
              if field not in {"cursor", "receipt_path", "last_observed_at", "observation_receipts", "last_poll_receipt"}}
        for key, attempt in state.get("attempts", {}).items()
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def needs_attention(state: Mapping[str, Any]) -> bool:
    if state.get("status") != "active":
        return True
    if any(question.get("status") == "open" for question in state.get("questions", {}).values()):
        return True
    attempts = state.get("attempts", {})
    if any(attempt.get("status") in {"reserved", "interrupted"} for attempt in attempts.values()):
        return True
    if any(task.get("status") == "reported" and task.get("grade") is None for task in state.get("tasks", {}).values()):
        return True
    return not any(attempt.get("status") == "running" for attempt in attempts.values())


def wait_for_change(
    initial: Mapping[str, Any], sync: Callable[[], Mapping[str, Any]], *,
    timeout_seconds: float = 180, poll_interval: float = 2, max_polls: int = 60,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Return one receipt; no dispatch, grading, model calls or exception retries.

    The deadline prevents another poll from starting. A provider call already
    in flight retains that driver's timeout; this helper cannot preempt it.
    """

    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0
           for v in (timeout_seconds, poll_interval)):
        raise ValueError("wait durations must be finite and positive")
    if isinstance(max_polls, bool) or not isinstance(max_polls, int) or not 1 <= max_polls <= 1000:
        raise ValueError("max_polls must be an integer from 1 through 1000")
    if timeout_seconds > 3600:
        raise ValueError("wait timeout cannot exceed one hour")
    started = clock()
    baseline = semantic_fingerprint(initial)
    state = initial
    polls = empty = 0
    reason = "attention_required"
    if not needs_attention(initial):
        while polls < max_polls:
            if clock() - started >= timeout_seconds:
                reason = "timeout"
                break
            state = sync()
            polls += 1
            if semantic_fingerprint(state) != baseline:
                reason = "state_changed"
                break
            if needs_attention(state):
                reason = "attention_required"
                break
            empty += 1
            remaining = timeout_seconds - (clock() - started)
            if remaining <= 0:
                reason = "timeout"
                break
            if polls == max_polls:
                reason = "poll_limit"
                break
            sleep(min(poll_interval * min(2 ** min(empty - 1, 3), 5), remaining))
    return {
        "reason": reason, "poll_count": polls, "empty_polls": empty,
        "elapsed_ms": max(0, int((clock() - started) * 1000)),
        "model_calls_by_wait": 0, "state": state,
    }
