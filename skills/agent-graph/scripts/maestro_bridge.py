#!/usr/bin/env python3
"""Bounded AgentGraphView projection and coordinator-fenced Maestro inbox.

This module deliberately has no driver imports.  Canvas traffic is validated and
persisted as a coordinator inbox request; only the coordinator may turn a request
into canonical journal state.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Mapping

from graph_core import (
    GraphError,
    GraphValidationError,
    validate_agent_graph_view,
    validate_delegation_intent,
    validate_maestro_mutation,
)
from run_progress import build_run_progress_summary


MAX_NODES = 1000
MAX_EDGES = 3000
MAX_SUMMARY = 2048
INBOX_DIRECTORY = Path("artifacts/maestro-inbox")


class MaestroBridgeError(GraphError):
    """A visible protocol, fencing, or inbox error."""

    def __init__(self, message: str, *, code: str = "maestro_error", details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = dict(details or {})


def canonical_bytes(value: Mapping[str, Any]) -> bytes:
    """Serialize a protocol object in the byte-stable form used for replay."""

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def negotiate_major(
    local: Iterable[str | int], remote: Iterable[str | int], *, protocol: str = "agent-graph-view"
) -> int:
    """Return the greatest mutually supported major, or fail visibly."""

    def major(value: str | int) -> int:
        if isinstance(value, bool):
            raise MaestroBridgeError("protocol major must be an integer", code="invalid_capability")
        if isinstance(value, int):
            result = value
        elif isinstance(value, str) and value.startswith(f"{protocol}/v"):
            try:
                result = int(value.rsplit("/v", 1)[1])
            except ValueError as error:
                raise MaestroBridgeError("invalid protocol capability", code="invalid_capability") from error
        else:
            raise MaestroBridgeError("invalid protocol capability", code="invalid_capability")
        if result < 1:
            raise MaestroBridgeError("protocol major must be positive", code="invalid_capability")
        return result

    mutual = {major(value) for value in local} & {major(value) for value in remote}
    if not mutual:
        raise MaestroBridgeError(
            f"no mutually supported {protocol} major version", code="unsupported_major"
        )
    return max(mutual)


def negotiate_capabilities(local: Mapping[str, Any], remote: Mapping[str, Any]) -> dict[str, Any]:
    """Negotiate a persisted view capability set from two explicit advertisements."""

    protocols = local.get("protocol_majors")
    remote_protocols = remote.get("protocol_majors")
    if not isinstance(protocols, list) or not isinstance(remote_protocols, list):
        raise MaestroBridgeError("capability advertisements must include protocol_majors", code="invalid_capability")
    major = negotiate_major(protocols, remote_protocols)
    result: dict[str, Any] = {"protocol_major": major}
    for field in ("agents", "efforts", "placement_kinds"):
        left = local.get(field)
        right = remote.get(field)
        if not isinstance(left, list) or not isinstance(right, list):
            raise MaestroBridgeError(f"capability advertisements must include {field}", code="invalid_capability")
        if any(not isinstance(item, str) or not item for item in left + right):
            raise MaestroBridgeError(f"capability advertisements {field} must contain non-empty strings", code="invalid_capability")
        max_items = {"agents": 32, "efforts": 5, "placement_kinds": 3}[field]
        if len(left) > max_items or len(right) > max_items or len(set(left)) != len(left) or len(set(right)) != len(right):
            raise MaestroBridgeError(f"capability advertisements {field} are duplicated or oversized", code="invalid_capability")
        if field == "efforts" and any(item not in {"low", "medium", "high", "xhigh", "max"} for item in left + right):
            raise MaestroBridgeError("capability advertisements contain an invalid effort", code="invalid_capability")
        if field == "placement_kinds" and any(item not in {"current-workspace", "existing-workspace", "create-child-worktree"} for item in left + right):
            raise MaestroBridgeError("capability advertisements contain an invalid placement", code="invalid_capability")
        result[field] = sorted(set(left) & set(right))
    if not isinstance(local.get("watch_deltas"), bool) or not isinstance(remote.get("watch_deltas"), bool):
        raise MaestroBridgeError("capability advertisements must include watch_deltas", code="invalid_capability")
    result["watch_deltas"] = local["watch_deltas"] and remote["watch_deltas"]
    return result


def _summary(value: Any, fallback: str) -> str:
    text = " ".join(str(value or fallback).split())
    bounded = text.encode("utf-8")[:MAX_SUMMARY].decode("utf-8", errors="ignore")
    return bounded or fallback


def _sorted_dict_items(value: Any) -> list[tuple[str, Mapping[str, Any]]]:
    if not isinstance(value, Mapping):
        return []
    return [(str(key), item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0])) if isinstance(item, Mapping)]


def _node(node_id: str, node_type: str, status: str, summary: str, **extra: Any) -> dict[str, Any]:
    return {"id": node_id, "type": node_type, "status": status, "summary": _summary(summary, node_id), **extra}


def _view_base(
    projection: Mapping[str, Any], *, change: str, kind: str, capabilities: Mapping[str, Any],
    revision: int, cursor: Mapping[str, Any] | None, from_cursor: Mapping[str, Any] | None,
    nodes: list[dict[str, Any]], edges: list[dict[str, Any]], removed_node_ids: list[str] | None = None,
    removed_edge_ids: list[str] | None = None, reset_required: bool = False,
    progress: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    scope = projection.get("workspace_scope")
    coordinator = projection.get("coordinator")
    if not isinstance(scope, Mapping) or not isinstance(coordinator, Mapping):
        raise MaestroBridgeError("run has no pinned workspace scope", code="invalid_state")
    if not isinstance(capabilities, Mapping):
        raise MaestroBridgeError("AgentGraphView requires negotiated persisted capabilities", code="capabilities_unavailable")
    if not isinstance(progress, Mapping):
        raise MaestroBridgeError("AgentGraphView requires a journal-derived progress summary", code="invalid_progress")
    sorted_nodes = sorted(nodes, key=lambda item: item["id"])
    sorted_edges = sorted(edges, key=lambda item: item["id"])
    sorted_removed_nodes = sorted(removed_node_ids or [])
    sorted_removed_edges = sorted(removed_edge_ids or [])
    if any((len(sorted_nodes) > MAX_NODES, len(sorted_edges) > MAX_EDGES, len(sorted_removed_nodes) > MAX_NODES, len(sorted_removed_edges) > MAX_EDGES)):
        raise MaestroBridgeError("AgentGraphView exceeds its bounded capacity; request a fresh smaller view", code="capacity_exceeded")
    view = {
        "schema_version": 1,
        "protocol": "agent-graph-view/v1",
        "kind": kind,
        "workspace_scope": scope,
        "change": change,
        "run_id": scope["run_id"],
        "coordinator": {"id": coordinator["id"], "generation": scope["coordinator_generation"]},
        "capabilities": dict(capabilities),
        "nodes": sorted_nodes,
        "edges": sorted_edges,
        "removed_node_ids": sorted_removed_nodes,
        "removed_edge_ids": sorted_removed_edges,
        "revision": revision,
        "cursor": cursor,
        "from_cursor": from_cursor,
        "reset_required": reset_required,
        "progress": dict(progress),
    }
    try:
        return validate_agent_graph_view(view)
    except GraphValidationError as error:
        raise MaestroBridgeError(f"invalid projected AgentGraphView: {error}", code="invalid_view") from error


def build_snapshot(
    projection: Mapping[str, Any], *, change: str, capabilities: Mapping[str, Any] | None = None,
    stream_id: str | None = None, visual_state: Mapping[str, Any] | None = None,
    last_event: Mapping[str, Any] | None = None, progress: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a stable, bounded snapshot from journal-derived projection state."""

    revision = int(projection.get("last_sequence", 0))
    stream = stream_id or str(projection.get("run_id") or "run")
    caps = capabilities
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    tasks = projection.get("tasks", {})
    attempts = projection.get("attempts", {})
    cleanup = projection.get("cleanup", {})
    delegations = projection.get("delegations", {})
    # Layout, note documents, and provider resource identities remain in the
    # Orca-owned visual state. AgentGraphView is the portable semantic view.

    for task_id, task in _sorted_dict_items(tasks):
        contract = task.get("contract", {})
        blockers: list[str] = []
        dependencies = contract.get("depends", []) if isinstance(contract, Mapping) else []
        if isinstance(dependencies, list):
            for dependency in dependencies:
                dependency_state = tasks.get(dependency, {}) if isinstance(tasks, Mapping) else {}
                if isinstance(dependency_state, Mapping) and dependency_state.get("grade") != "pass":
                    blockers.append(dependency)
        task_extra: dict[str, Any] = {"task_id": task_id, "blockers": blockers[:64]}
        nodes.append(_node(f"task-{task_id}", "task", str(task.get("status", "pending")), contract.get("title", task_id), **task_extra))
        for attempt_id in task.get("attempt_ids", []) if isinstance(task.get("attempt_ids"), list) else []:
            attempt = attempts.get(attempt_id, {}) if isinstance(attempts, Mapping) else {}
            if not isinstance(attempt, Mapping):
                continue
            profile = attempt.get("execution_profile")
            if not isinstance(profile, Mapping):
                continue
            nodes.append(_node(f"attempt-{attempt_id}", "attempt", str(attempt.get("status", "unknown")), f"Attempt for {task_id}.", task_id=task_id, attempt_id=attempt_id, profile=profile))
            edges.append({"id": f"edge-reports-{attempt_id}", "type": "reports_to", "source_id": f"attempt-{attempt_id}", "target_id": f"task-{task_id}"})
            check = attempt.get("check")
            if isinstance(check, Mapping):
                evidence_node = f"evidence-{attempt_id}"
                nodes.append(_node(evidence_node, "evidence", str(check.get("status", "recorded")), "Bounded check evidence."))
                edges.append({"id": f"edge-produces-{attempt_id}", "type": "produces", "source_id": f"attempt-{attempt_id}", "target_id": evidence_node})
            report = attempt.get("report")
            refs = report.get("evidence_refs", []) if isinstance(report, Mapping) else []
            if isinstance(refs, list):
                for index, reference in enumerate(sorted(str(item) for item in refs)[:16]):
                    evidence_node = f"evidence-{attempt_id}-{index}"
                    nodes.append(_node(evidence_node, "evidence", "recorded", reference))
                    edges.append({"id": f"edge-produces-{attempt_id}-{index}", "type": "produces", "source_id": f"attempt-{attempt_id}", "target_id": evidence_node})

        for dependency in contract.get("depends", []) if isinstance(contract, Mapping) and isinstance(contract.get("depends"), list) else []:
            if dependency in tasks:
                edges.append({"id": f"edge-depends-{task_id}-{dependency}", "type": "depends_on", "source_id": f"task-{task_id}", "target_id": f"task-{dependency}"})

    if not isinstance(cleanup, Mapping):
        raise MaestroBridgeError("journal cleanup projection is invalid", code="invalid_cleanup")

    for delegation_id, delegation in _sorted_dict_items(delegations):
        child = delegation.get("child_attempt_id")
        if isinstance(child, str) and child:
            parent = delegation.get("parent_attempt_id")
            profile = delegation.get("execution_profile")
            child_node_id = f"attempt-{child}"
            if isinstance(profile, Mapping) and not any(node.get("id") == child_node_id for node in nodes):
                nodes.append(_node(child_node_id, "attempt", str(delegation.get("status", "started")), "Delegated child attempt.", task_id=delegation.get("parent_task_id", "delegated-task"), attempt_id=child, profile=profile))
            if isinstance(parent, str) and any(node.get("id") == child_node_id for node in nodes) and any(node.get("id") == f"attempt-{parent}" for node in nodes):
                edges.append({"id": f"edge-spawned-{delegation_id}", "type": "spawned_by", "source_id": f"attempt-{child}", "target_id": f"attempt-{parent}"})

    cursor = {"stream_id": stream, "sequence": revision, "revision": revision}
    summary = progress if progress is not None else build_run_progress_summary(projection, last_event=last_event)
    return _view_base(projection, change=change, kind="snapshot", capabilities=caps, revision=revision, cursor=cursor, from_cursor=None, nodes=nodes, edges=edges, progress=summary)


def build_delta(previous: Mapping[str, Any], current: Mapping[str, Any], *, change: str, from_cursor: Mapping[str, Any], capabilities: Mapping[str, Any] | None = None, stream_id: str | None = None) -> dict[str, Any]:
    """Return only changed entities with deterministic removals."""
    current_cursor = current.get("cursor")
    if not isinstance(current_cursor, Mapping) or not isinstance(from_cursor, Mapping):
        raise MaestroBridgeError("delta requires explicit cursors", code="invalid_cursor")
    stream = stream_id or current_cursor.get("stream_id")
    if current_cursor.get("stream_id") != stream or from_cursor.get("stream_id") != stream:
        raise MaestroBridgeError("delta cursor stream does not match the view", code="invalid_cursor")
    for cursor, label in ((from_cursor, "from_cursor"), (current_cursor, "cursor")):
        if any(not isinstance(cursor.get(field), int) or cursor[field] < 0 or cursor[field] != cursor.get("revision") for field in ("sequence", "revision")):
            raise MaestroBridgeError(f"{label} has an invalid sequence/revision", code="invalid_cursor")
    if from_cursor["revision"] > current_cursor["revision"]:
        raise MaestroBridgeError("delta cursor is ahead of current revision", code="invalid_cursor")
    old_nodes = {item["id"]: item for item in previous.get("nodes", []) if isinstance(item, Mapping) and "id" in item}
    new_nodes = {item["id"]: item for item in current.get("nodes", []) if isinstance(item, Mapping) and "id" in item}
    old_edges = {item["id"]: item for item in previous.get("edges", []) if isinstance(item, Mapping) and "id" in item}
    new_edges = {item["id"]: item for item in current.get("edges", []) if isinstance(item, Mapping) and "id" in item}
    changed_edges = [new_edges[key] for key in sorted(new_edges) if old_edges.get(key) != new_edges[key]]
    if any(edge["source_id"] not in new_nodes or edge["target_id"] not in new_nodes for edge in changed_edges):
        raise MaestroBridgeError("delta contains an edge to an absent node", code="invalid_view")
    changed_nodes = {key for key in new_nodes if old_nodes.get(key) != new_nodes[key]}
    for edge in changed_edges:
        changed_nodes.update({edge["source_id"], edge["target_id"]})
    return _view_base(current, change=change, kind="delta", capabilities=capabilities or current.get("capabilities"), revision=current_cursor["revision"], cursor=dict(current_cursor), from_cursor=dict(from_cursor), nodes=[new_nodes[key] for key in sorted(changed_nodes) if key in new_nodes], edges=changed_edges, removed_node_ids=sorted(set(old_nodes) - set(new_nodes)), removed_edge_ids=sorted(set(old_edges) - set(new_edges)), progress=current.get("progress"))


def build_reset(current: Mapping[str, Any], *, change: str, from_cursor: Mapping[str, Any], capabilities: Mapping[str, Any] | None = None, stream_id: str | None = None) -> dict[str, Any]:
    """Return a compact reset marker after a cursor gap or expired retention."""

    cursor = current.get("cursor")
    if not isinstance(cursor, Mapping) or not isinstance(from_cursor, Mapping):
        raise MaestroBridgeError("reset requires explicit cursors", code="invalid_cursor")
    stream = stream_id or cursor.get("stream_id")
    if cursor.get("stream_id") != stream or from_cursor.get("stream_id") != stream:
        raise MaestroBridgeError("reset cursor stream does not match the view", code="invalid_cursor")
    for candidate, label in ((cursor, "cursor"), (from_cursor, "from_cursor")):
        if any(not isinstance(candidate.get(field), int) or candidate[field] < 0 or candidate[field] != candidate.get("revision") for field in ("sequence", "revision")):
            raise MaestroBridgeError(f"{label} has an invalid sequence/revision", code="invalid_cursor")
    if from_cursor["revision"] > cursor["revision"]:
        raise MaestroBridgeError("reset cursor is ahead of current revision", code="invalid_cursor")
    return _view_base(current, change=change, kind="delta", capabilities=capabilities or current.get("capabilities"), revision=cursor["revision"], cursor=dict(cursor), from_cursor=dict(from_cursor), nodes=[], edges=[], reset_required=True, progress=current.get("progress"))


class CoordinatorInbox:
    """One run-owned, atomic request inbox. It never appends the canonical journal."""

    def __init__(self, run_directory: Path) -> None:
        self.directory = Path(run_directory) / INBOX_DIRECTORY
        self.path = self.directory / "requests.json"
        self.lock_path = self.directory / "requests.json.lock"

    @contextmanager
    def _lock(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+b") as handle:
            if os.name == "nt":
                import msvcrt
                if self.lock_path.stat().st_size == 0:
                    handle.seek(0)
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise MaestroBridgeError(f"cannot read coordinator inbox: {error}", code="inbox_corrupt") from error
        if not isinstance(value, dict):
            raise MaestroBridgeError("coordinator inbox must be an object", code="inbox_corrupt")
        for request_id, record in value.items():
            if not isinstance(record, Mapping) or not isinstance(record.get("payload"), Mapping):
                raise MaestroBridgeError(f"inbox record is invalid: {request_id}", code="inbox_corrupt")
            if record.get("payload_sha256") != canonical_sha256(record["payload"]):
                raise MaestroBridgeError(f"inbox record digest mismatch: {request_id}", code="inbox_corrupt")
            if record.get("record_sha256") != self._record_digest(record):
                raise MaestroBridgeError(f"inbox record integrity mismatch: {request_id}", code="inbox_corrupt")
            if record.get("status") == "acked":
                if not isinstance(record.get("applied_revision"), int) or record["applied_revision"] < 0:
                    raise MaestroBridgeError(f"acked inbox record has no applied revision: {request_id}", code="inbox_corrupt")
                for field in ("affected_node_ids", "affected_event_ids"):
                    values = record.get(field)
                    if not isinstance(values, list) or len(values) > 32 or any(not isinstance(item, str) for item in values):
                        raise MaestroBridgeError(f"acked inbox record has invalid {field}: {request_id}", code="inbox_corrupt")
        return value

    @staticmethod
    def _record_digest(record: Mapping[str, Any]) -> str:
        return canonical_sha256({key: value for key, value in record.items() if key != "record_sha256"})

    @classmethod
    def _with_integrity(cls, record: Mapping[str, Any]) -> dict[str, Any]:
        value = dict(record)
        value["record_sha256"] = cls._record_digest(value)
        return value

    def _write(self, value: Mapping[str, Any]) -> None:
        descriptor, temporary = tempfile.mkstemp(prefix=".requests.", dir=self.directory)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            if hasattr(os, "O_DIRECTORY"):
                directory_fd = os.open(self.directory, os.O_DIRECTORY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise

    def _visual_state(self) -> dict[str, Any]:
        path = self.directory / "visual-state.json"
        if not path.exists():
            return {"positions": {}, "notes": {}}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise MaestroBridgeError(f"cannot read visual state: {error}", code="visual_state_corrupt") from error
        if not isinstance(value, Mapping) or set(value) != {"state", "sha256"}:
            raise MaestroBridgeError("visual state envelope is invalid", code="visual_state_corrupt")
        state = value.get("state")
        if not isinstance(state, Mapping) or value.get("sha256") != canonical_sha256(state):
            raise MaestroBridgeError("visual state digest mismatch", code="visual_state_corrupt")
        value = state
        if not isinstance(value, dict) or not isinstance(value.get("positions", {}), dict) or not isinstance(value.get("notes", {}), dict):
            raise MaestroBridgeError("visual state is invalid", code="visual_state_corrupt")
        return value

    def _write_visual_state(self, value: Mapping[str, Any]) -> None:
        path = self.directory / "visual-state.json"
        descriptor, temporary = tempfile.mkstemp(prefix=".visual-state.", dir=self.directory)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                envelope = {"state": dict(value), "sha256": canonical_sha256(value)}
                json.dump(envelope, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            if hasattr(os, "O_DIRECTORY"):
                directory_fd = os.open(self.directory, os.O_DIRECTORY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise

    def read_visual_state(self) -> dict[str, Any]:
        with self._lock():
            return self._visual_state()

    def persist_capabilities(self, capabilities: Mapping[str, Any], *, coordinator_id: str, generation: int, workspace_scope: Mapping[str, Any]) -> dict[str, Any]:
        required = {"protocol_major", "agents", "efforts", "placement_kinds", "watch_deltas"}
        if set(capabilities) != required or not isinstance(capabilities.get("protocol_major"), int) or capabilities["protocol_major"] < 1:
            raise MaestroBridgeError("negotiated capabilities are incomplete", code="invalid_capability")
        if not coordinator_id or generation != workspace_scope.get("coordinator_generation"):
            raise MaestroBridgeError("capabilities are not bound to the active coordinator", code="stale_generation")
        record = {"capabilities": dict(capabilities), "capabilities_sha256": canonical_sha256(capabilities), "coordinator_id": coordinator_id, "generation": generation, "run_id": workspace_scope["run_id"]}
        with self._lock():
            existing_path = self.directory / "capabilities.json"
            if existing_path.exists():
                existing = json.loads(existing_path.read_text(encoding="utf-8"))
                if isinstance(existing, Mapping) and existing.get("generation") != generation:
                    self._write_named(existing_path, record)
                    return {"persisted": True, "idempotent": False, **record}
                if existing != record:
                    raise MaestroBridgeError("persisted capabilities cannot change for this coordinator", code="capability_divergence")
                return {"persisted": True, "idempotent": True, **record}
            self._write_named(existing_path, record)
            return {"persisted": True, "idempotent": False, **record}

    def read_capabilities(self, *, run_id: str | None = None, coordinator_id: str | None = None, generation: int | None = None) -> dict[str, Any] | None:
        with self._lock():
            path = self.directory / "capabilities.json"
            if not path.exists():
                return None
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, Mapping) or not isinstance(value.get("capabilities"), Mapping):
                return None
            if run_id is not None and value.get("run_id") != run_id:
                return None
            if coordinator_id is not None and value.get("coordinator_id") != coordinator_id:
                return None
            if generation is not None and value.get("generation") != generation:
                return None
            if value.get("capabilities_sha256") != canonical_sha256(value["capabilities"]):
                return None
            return {key: item for key, item in value["capabilities"].items() if key != "protocol_major"}

    def require_handshake(self, *, run_id: str, coordinator_id: str, generation: int) -> dict[str, Any]:
        with self._lock():
            path = self.directory / "capabilities.json"
            if not path.exists():
                raise MaestroBridgeError("current Maestro v1 handshake is missing", code="capabilities_unavailable")
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, Mapping) or value.get("run_id") != run_id or value.get("coordinator_id") != coordinator_id or value.get("generation") != generation:
                raise MaestroBridgeError("Maestro handshake is not bound to the current coordinator", code="stale_generation")
            capabilities = value.get("capabilities")
            if not isinstance(capabilities, Mapping) or value.get("capabilities_sha256") != canonical_sha256(capabilities):
                raise MaestroBridgeError("Maestro handshake digest is invalid", code="capabilities_corrupt")
            if capabilities.get("protocol_major") != 1:
                raise MaestroBridgeError("Maestro handshake has no mutually supported v1 major", code="unsupported_major")
            return {key: item for key, item in capabilities.items() if key != "protocol_major"}

    def get(self, request_id: str) -> dict[str, Any] | None:
        with self._lock():
            record = self._read().get(request_id)
            return dict(record) if isinstance(record, Mapping) else None

    def _write_named(self, path: Path, value: Mapping[str, Any]) -> None:
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            if hasattr(os, "O_DIRECTORY"):
                directory_fd = os.open(path.parent, os.O_DIRECTORY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise

    def submit(self, request: Mapping[str, Any], *, kind: str, workspace_scope: Mapping[str, Any], current_revision: int) -> dict[str, Any]:
        if kind not in {"mutation", "intent"}:
            raise MaestroBridgeError("unsupported inbox request kind", code="invalid_request")
        try:
            validated = validate_maestro_mutation(request, workspace_scope) if kind == "mutation" else validate_delegation_intent(request, workspace_scope)
        except GraphValidationError as error:
            raise MaestroBridgeError(str(error), code="invalid_request") from error
        request_id = validated["mutation_id"] if kind == "mutation" else validated["intent_id"]
        digest = canonical_sha256(validated)
        with self._lock():
            records = self._read()
            existing = records.get(request_id)
            if isinstance(existing, Mapping):
                if existing.get("kind") != kind or existing.get("payload_sha256") != digest or existing.get("payload") != validated:
                    raise MaestroBridgeError("request ID was reused with divergent payload", code="replay_divergence")
                return {"request_id": request_id, "kind": kind, "status": "accepted", "idempotent": True, "payload_sha256": digest}
            expected_revision = int(validated["expected_revision"])
            if expected_revision != current_revision:
                raise MaestroBridgeError(
                    "Maestro request revision is stale",
                    code="stale_revision",
                    details={"current_revision": current_revision, "reset_required": True, "guidance": "request a fresh AgentGraphView snapshot"},
                )
            records[request_id] = self._with_integrity({"kind": kind, "payload": validated, "payload_sha256": digest, "status": "pending"})
            self._write(records)
            return {"request_id": request_id, "kind": kind, "status": "pending", "idempotent": False, "payload_sha256": digest}

    def _validated_record(
        self,
        records: Mapping[str, Any],
        request_id: str,
        *,
        generation: int,
        workspace_scope: Mapping[str, Any],
        current_revision: int,
    ) -> tuple[dict[str, Any], Mapping[str, Any]]:
        record = records.get(request_id)
        if not isinstance(record, Mapping):
            raise MaestroBridgeError("unknown coordinator inbox request", code="unknown_request")
        payload = record.get("payload")
        if not isinstance(payload, Mapping) or payload.get("coordinator_generation") != generation:
            raise MaestroBridgeError("request generation is stale", code="stale_generation")
        try:
            if record.get("kind") == "mutation":
                validate_maestro_mutation(payload, workspace_scope)
            elif record.get("kind") == "intent":
                validate_delegation_intent(payload, workspace_scope)
            else:
                raise GraphValidationError("inbox request kind is invalid")
        except GraphValidationError as error:
            raise MaestroBridgeError(str(error), code="request_fenced") from error
        if record.get("status") == "pending" and int(payload.get("expected_revision", -1)) != current_revision:
            raise MaestroBridgeError(
                "Maestro request revision is stale",
                code="stale_revision",
                details={"current_revision": current_revision, "reset_required": True, "guidance": "request a fresh AgentGraphView snapshot"},
            )
        return dict(record), payload

    def preflight(
        self,
        request_id: str,
        *,
        generation: int,
        workspace_scope: Mapping[str, Any],
        current_revision: int,
    ) -> dict[str, Any]:
        with self._lock():
            record, _ = self._validated_record(
                self._read(), request_id, generation=generation, workspace_scope=workspace_scope, current_revision=current_revision
            )
            return record

    def consume(self, request_id: str, *, coordinator_id: str, generation: int, workspace_scope: Mapping[str, Any], current_revision: int, valid_node_ids: set[str] | None = None) -> dict[str, Any]:
        with self._lock():
            records = self._read()
            record, payload = self._validated_record(
                records, request_id, generation=generation, workspace_scope=workspace_scope, current_revision=current_revision
            )
            if record.get("status") == "pending":
                operation = payload.get("operation", {})
                if record.get("kind") == "mutation" and operation.get("kind") == "move-node" and (valid_node_ids is None or operation.get("node_id") not in valid_node_ids):
                    raise MaestroBridgeError("move-node references no exact node in the consumed view", code="unknown_node")
                updated = dict(record)
                updated.update({"status": "consumed", "consumed_by": coordinator_id, "consumed_generation": generation})
                records[request_id] = self._with_integrity(updated)
                self._write(records)
                return {"request_id": request_id, "status": "consumed", "idempotent": False, "kind": record.get("kind"), "payload": payload}
            if record.get("consumed_by") == coordinator_id and record.get("consumed_generation") == generation:
                return {"request_id": request_id, "status": str(record.get("status")), "idempotent": True, "kind": record.get("kind"), "payload": payload}
            raise MaestroBridgeError("request is owned by another coordinator", code="request_fenced")

    def ack(
        self,
        request_id: str,
        *,
        coordinator_id: str,
        generation: int,
        valid_node_ids: set[str] | None = None,
        applied_revision: int | None = None,
        affected_node_ids: list[str] | None = None,
        affected_event_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        with self._lock():
            records = self._read()
            record = records.get(request_id)
            if not isinstance(record, Mapping):
                raise MaestroBridgeError("unknown coordinator inbox request", code="unknown_request")
            if record.get("consumed_by") != coordinator_id or record.get("consumed_generation") != generation:
                raise MaestroBridgeError("ack is not fenced to the consuming coordinator", code="request_fenced")
            if record.get("status") == "acked":
                return {"request_id": request_id, "status": "acked", "idempotent": True, "applied_revision": record["applied_revision"], "affected_node_ids": list(record["affected_node_ids"]), "affected_event_ids": list(record["affected_event_ids"])}
            if not isinstance(applied_revision, int) or applied_revision < 0:
                raise MaestroBridgeError("ack requires an applied revision", code="invalid_ack")
            affected_node_ids = list(affected_node_ids or [])[:32]
            affected_event_ids = list(affected_event_ids or [])[:32]
            if record.get("kind") == "mutation":
                visual = self._visual_state()
                operation = record.get("payload", {}).get("operation", {})
                if operation.get("kind") == "move-node":
                    if valid_node_ids is None or operation.get("node_id") not in valid_node_ids:
                        raise MaestroBridgeError("move-node references no exact node in the consumed view", code="unknown_node")
                    visual["positions"][operation["node_id"]] = dict(operation["position"])
                elif operation.get("kind") == "pin-note-snapshot":
                    snapshot = dict(operation["snapshot"])
                    visual["notes"][snapshot["note_id"]] = {"snapshot": snapshot, "task_id": operation["task_id"]}
            if record.get("kind") == "mutation":
                self._write_visual_state(visual)
            updated = dict(record)
            updated["status"] = "acked"
            updated["acked_by"] = coordinator_id
            updated["acked_generation"] = generation
            updated["applied_revision"] = applied_revision
            updated["affected_node_ids"] = affected_node_ids
            updated["affected_event_ids"] = affected_event_ids
            records[request_id] = self._with_integrity(updated)
            self._write(records)
            return {"request_id": request_id, "status": "acked", "idempotent": False}

    def pending(self) -> list[dict[str, Any]]:
        with self._lock():
            return [dict(record, request_id=request_id) for request_id, record in sorted(self._read().items()) if isinstance(record, Mapping) and record.get("status") == "pending"]
