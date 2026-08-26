#!/usr/bin/env python3
"""Compose immutable, budgeted context capsules from typed references."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import stat
from collections import deque
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Protocol


SCHEMA_VERSION = 1
MAX_REFERENCES = 4096
MAX_EDGES = 8192
MAX_EXCERPT_BYTES = 2048
MAX_DIGEST_SOURCE_BYTES = 8192
MAX_NOTE_BYTES = 1_048_576
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*$")
CONTENT_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
CONTEXT_KINDS = frozenset(
    {"task", "user-note", "dependency", "decision", "source", "evidence"}
)
EDGE_TYPES = frozenset(
    {
        "depends_on",
        "context_for",
        "spawned_by",
        "executes",
        "reports_to",
        "produces",
        "portals_to",
    }
)
TRAVERSABLE_EDGE_TYPES = frozenset({"depends_on", "context_for", "produces"})
FORBIDDEN_TRANSCRIPT_FIELDS = frozenset(
    {"conversation", "messages", "prompt", "terminal_output", "transcript"}
)
FORBIDDEN_ORIGIN_PREFIXES = (
    "conversation:",
    "prompt:",
    "terminal:",
    "transcript:",
    "worker-report:",
)
SESSION_MEMORY_FIELDS = frozenset(
    {
        "decisions",
        "invariants",
        "central_files",
        "traps",
        "green_checks",
        "carry_forward_findings",
    }
)
KIND_PRIORITY = {
    "task": 1,
    "user-note": 2,
    "dependency": 3,
    "decision": 3,
    "source": 4,
    "evidence": 4,
}


class ContextCapsuleError(ValueError):
    """Base error for an invalid or unsafe context-capsule operation."""


class ContextValidationError(ContextCapsuleError):
    """Reports invalid context metadata or a path outside the repository."""


class ContentHashMismatchError(ContextCapsuleError):
    """Reports content that does not match its pinned hash."""


class NoteAuthorizationError(ContextCapsuleError):
    """Reports a note revision that the authenticated actor cannot read."""


class NoteRevisionExpiredError(ContextCapsuleError):
    """Reports a note revision that is no longer available."""


class CapsuleAlreadyExistsError(ContextCapsuleError):
    """Reports an attempted mutation of an existing immutable capsule."""


class MaestroNoteClient(Protocol):
    """Authenticated bridge used by the coordinator to lease note revisions."""

    def fetch_and_pin_revision(
        self,
        *,
        note_id: str,
        revision: str,
        expected_hash: str,
        run_id: str,
        actor: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Fetch and pin one exact revision in the same authenticated transaction."""

        ...

    def release_run_revisions(
        self, *, run_id: str, actor: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        """Release every note revision pinned by a terminal run."""

        ...


def _bounded_string(value: Any, context: str, *, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContextValidationError(f"{context} must be a non-empty string")
    normalized = value.strip()
    if len(normalized.encode("utf-8")) > maximum:
        raise ContextValidationError(f"{context} exceeds {maximum} bytes")
    if any(ord(character) < 32 for character in normalized):
        raise ContextValidationError(f"{context} contains a control character")
    return normalized


def _identifier(value: Any, context: str) -> str:
    identifier = _bounded_string(value, context, maximum=256)
    if not IDENTIFIER_PATTERN.fullmatch(identifier):
        raise ContextValidationError(f"{context} is invalid")
    return identifier


def _content_hash(value: Any, context: str) -> str:
    content_hash = _bounded_string(value, context, maximum=71)
    if not CONTENT_HASH_PATTERN.fullmatch(content_hash):
        raise ContextValidationError(f"{context} must be a lowercase sha256 digest")
    return content_hash


def _positive_integer(value: Any, context: str, *, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise ContextValidationError(f"{context} must be an integer from 1 through {maximum}")
    return value


def _exact_fields(
    value: Any,
    required: frozenset[str],
    optional: frozenset[str],
    context: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContextValidationError(f"{context} must be an object")
    unknown = sorted(set(value) - required - optional)
    missing = sorted(required - set(value))
    if unknown:
        raise ContextValidationError(f"{context} has unknown fields: {', '.join(unknown)}")
    if missing:
        raise ContextValidationError(f"{context} is missing fields: {', '.join(missing)}")
    return value


def _reject_transcript_fields(value: Any, context: str) -> None:
    if isinstance(value, Mapping):
        forbidden = sorted(
            key
            for key in value
            if isinstance(key, str) and key.casefold() in FORBIDDEN_TRANSCRIPT_FIELDS
        )
        if forbidden:
            raise ContextValidationError(
                f"{context} contains transcript fields: {', '.join(forbidden)}"
            )
        for key, item in value.items():
            _reject_transcript_fields(item, f"{context}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_transcript_fields(item, f"{context}[{index}]")


def _safe_relative_path(value: Any, context: str) -> str:
    raw_path = _bounded_string(value, context, maximum=4096)
    if raw_path.startswith("/") or "\\" in raw_path or "//" in raw_path:
        raise ContextValidationError(f"{context} must be a normalized repository-relative path")
    path = PurePosixPath(raw_path)
    if path.is_absolute() or raw_path != path.as_posix():
        raise ContextValidationError(f"{context} must be a normalized repository-relative path")
    if not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ContextValidationError(f"{context} escapes the repository")
    return raw_path


def _bounded_string_list(value: Any, context: str, *, maximum_items: int, maximum_bytes: int) -> list[str]:
    """Normalize compact session notes without admitting transcripts or reports."""

    if not isinstance(value, list) or len(value) > maximum_items:
        raise ContextValidationError(f"{context} must contain at most {maximum_items} strings")
    normalized: list[str] = []
    for index, item in enumerate(value):
        normalized.append(
            _bounded_string(item, f"{context}[{index}]", maximum=maximum_bytes)
        )
    if len(set(normalized)) != len(normalized):
        raise ContextValidationError(f"{context} must not contain duplicates")
    return normalized


def build_reused_session_handoff(
    *,
    task_id: str,
    acceptance: str,
    dependency_summaries: Iterable[Mapping[str, Any]],
    diff_since_previous_check: Iterable[str],
    unresolved_material_finding_refs: Iterable[str],
    allowed_paths: Iterable[str],
    check: str,
    session_memory: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the deliberately small follow-up payload for one reused writer.

    This is distinct from the initial worker capsule.  It contains only the
    current contract plus bounded deltas, never a projection, transcript, prior
    worker report, or complete task graph.
    """

    _reject_transcript_fields(session_memory, "session_memory")
    if not isinstance(session_memory, Mapping) or set(session_memory) != SESSION_MEMORY_FIELDS:
        raise ContextValidationError("session_memory must contain the bounded session-memory fields")
    normalized_task_id = _identifier(task_id, "session handoff task_id")
    normalized_acceptance = _bounded_string(
        acceptance, "session handoff acceptance", maximum=16_384
    )
    normalized_check = _bounded_string(check, "session handoff check", maximum=4_096)
    normalized_paths = _bounded_string_list(
        list(allowed_paths), "session handoff allowed_paths", maximum_items=128, maximum_bytes=4_096
    )
    if not normalized_paths:
        raise ContextValidationError("session handoff allowed_paths must not be empty")
    for path in normalized_paths:
        _safe_relative_path(path, "session handoff allowed_paths")
    normalized_diff = _bounded_string_list(
        list(diff_since_previous_check),
        "session handoff diff_since_previous_check",
        maximum_items=128,
        maximum_bytes=4_096,
    )
    for path in normalized_diff:
        _safe_relative_path(path, "session handoff diff_since_previous_check")
    finding_refs = _bounded_string_list(
        list(unresolved_material_finding_refs),
        "session handoff unresolved_material_finding_refs",
        maximum_items=32,
        maximum_bytes=4_096,
    )
    dependencies: list[dict[str, str]] = []
    for index, dependency in enumerate(dependency_summaries):
        if not isinstance(dependency, Mapping) or set(dependency) != {"task_id", "summary"}:
            raise ContextValidationError(
                "session handoff dependency summaries must contain only task_id and summary"
            )
        dependencies.append(
            {
                "task_id": _identifier(
                    dependency["task_id"], f"session handoff dependency_summaries[{index}].task_id"
                ),
                "summary": _bounded_string(
                    dependency["summary"],
                    f"session handoff dependency_summaries[{index}].summary",
                    maximum=2_048,
                ),
            }
        )
    if len(dependencies) > 64 or len({item["task_id"] for item in dependencies}) != len(dependencies):
        raise ContextValidationError("session handoff dependency summaries must be unique and bounded")
    memory = {
        field: _bounded_string_list(
            session_memory[field],
            f"session_memory.{field}",
            maximum_items=32,
            maximum_bytes=2_048,
        )
        for field in sorted(SESSION_MEMORY_FIELDS)
    }
    payload = {
        "task_id": normalized_task_id,
        "acceptance": normalized_acceptance,
        "dependency_summaries": dependencies,
        "diff_since_previous_check": normalized_diff,
        "unresolved_material_finding_refs": finding_refs,
        "allowed_paths": normalized_paths,
        "check": normalized_check,
        "session_memory": memory,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return {"schema_version": 1, "handoff_id": f"session-handoff-{digest[:24]}", **payload}


def _confined_path(repository_root: Path, relative_path: str, *, must_exist: bool) -> Path:
    root = repository_root.resolve(strict=True)
    candidate = root.joinpath(*PurePosixPath(relative_path).parts)
    try:
        resolved = candidate.resolve(strict=must_exist)
    except FileNotFoundError as error:
        raise ContextValidationError(f"snapshot does not exist: {relative_path}") from error
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ContextValidationError(f"path escapes the repository: {relative_path}") from error
    return resolved


def _sha256_bytes(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


@dataclass(frozen=True, slots=True)
class ContextBudget:
    """Hard limits for references and bounded digest material."""

    max_items: int
    max_bytes: int
    max_tokens: int

    @classmethod
    def from_value(cls, value: ContextBudget | Mapping[str, Any]) -> ContextBudget:
        if isinstance(value, cls):
            value = value.to_dict()
        budget = _exact_fields(
            value,
            frozenset({"max_items", "max_bytes", "max_tokens"}),
            frozenset(),
            "budget",
        )
        return cls(
            max_items=_positive_integer(budget["max_items"], "budget.max_items", maximum=256),
            max_bytes=_positive_integer(
                budget["max_bytes"], "budget.max_bytes", maximum=1_048_576
            ),
            max_tokens=_positive_integer(
                budget["max_tokens"], "budget.max_tokens", maximum=262_144
            ),
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "max_items": self.max_items,
            "max_bytes": self.max_bytes,
            "max_tokens": self.max_tokens,
        }


@dataclass(frozen=True, slots=True)
class ContextReference:
    """One immutable repository snapshot available to context traversal."""

    id: str
    kind: str
    origin: str
    snapshot_path: str
    content_hash: str
    revision: str
    media_type: str
    title: str
    priority: int

    @classmethod
    def from_value(
        cls, value: ContextReference | Mapping[str, Any], context: str = "reference"
    ) -> ContextReference:
        if isinstance(value, cls):
            value = {
                "id": value.id,
                "kind": value.kind,
                "origin": value.origin,
                "snapshot_path": value.snapshot_path,
                "content_hash": value.content_hash,
                "revision": value.revision,
                "media_type": value.media_type,
                "title": value.title,
                "priority": value.priority,
            }
        _reject_transcript_fields(value, context)
        reference = _exact_fields(
            value,
            frozenset(
                {
                    "id",
                    "kind",
                    "origin",
                    "snapshot_path",
                    "content_hash",
                    "revision",
                    "media_type",
                    "title",
                }
            ),
            frozenset({"priority"}),
            context,
        )
        kind = _bounded_string(reference["kind"], f"{context}.kind", maximum=32)
        if kind not in CONTEXT_KINDS:
            raise ContextValidationError(f"{context}.kind is not context material")
        origin = _bounded_string(reference["origin"], f"{context}.origin", maximum=512)
        if origin.casefold().startswith(FORBIDDEN_ORIGIN_PREFIXES):
            raise ContextValidationError(f"{context}.origin names automatic transcript material")
        priority_value = reference.get("priority", KIND_PRIORITY[kind])
        return cls(
            id=_identifier(reference["id"], f"{context}.id"),
            kind=kind,
            origin=origin,
            snapshot_path=_safe_relative_path(
                reference["snapshot_path"], f"{context}.snapshot_path"
            ),
            content_hash=_content_hash(reference["content_hash"], f"{context}.content_hash"),
            revision=_bounded_string(reference["revision"], f"{context}.revision", maximum=256),
            media_type=_bounded_string(
                reference["media_type"], f"{context}.media_type", maximum=128
            ),
            title=_bounded_string(reference["title"], f"{context}.title", maximum=512),
            priority=_positive_integer(priority_value, f"{context}.priority", maximum=5),
        )


@dataclass(frozen=True, slots=True)
class ContextEdge:
    """One deterministic semantic edge in the context graph."""

    id: str
    type: str
    source_id: str
    target_id: str

    @classmethod
    def from_value(
        cls, value: ContextEdge | Mapping[str, Any], context: str = "edge"
    ) -> ContextEdge:
        if isinstance(value, cls):
            value = {
                "id": value.id,
                "type": value.type,
                "source_id": value.source_id,
                "target_id": value.target_id,
            }
        _reject_transcript_fields(value, context)
        edge = _exact_fields(
            value,
            frozenset({"id", "type", "source_id", "target_id"}),
            frozenset(),
            context,
        )
        edge_type = _bounded_string(edge["type"], f"{context}.type", maximum=32)
        if edge_type not in EDGE_TYPES:
            raise ContextValidationError(f"{context}.type is unsupported")
        return cls(
            id=_identifier(edge["id"], f"{context}.id"),
            type=edge_type,
            source_id=_identifier(edge["source_id"], f"{context}.source_id"),
            target_id=_identifier(edge["target_id"], f"{context}.target_id"),
        )


@dataclass(frozen=True, slots=True)
class _Snapshot:
    byte_count: int
    prefix: bytes


def _read_snapshot(
    repository_root: Path, reference: ContextReference
) -> _Snapshot:
    path = _confined_path(repository_root, reference.snapshot_path, must_exist=True)
    if not path.is_file():
        raise ContextValidationError(f"snapshot is not a regular file: {reference.snapshot_path}")
    digest = hashlib.sha256()
    byte_count = 0
    prefix = bytearray()
    with path.open("rb") as handle:
        while chunk := handle.read(65_536):
            digest.update(chunk)
            byte_count += len(chunk)
            if len(prefix) < MAX_DIGEST_SOURCE_BYTES:
                remaining = MAX_DIGEST_SOURCE_BYTES - len(prefix)
                prefix.extend(chunk[:remaining])
    actual_hash = f"sha256:{digest.hexdigest()}"
    if actual_hash != reference.content_hash:
        raise ContentHashMismatchError(
            f"snapshot hash mismatch for {reference.snapshot_path}: "
            f"expected {reference.content_hash}, got {actual_hash}"
        )
    return _Snapshot(byte_count=byte_count, prefix=bytes(prefix))


def estimate_tokens(text: str) -> int:
    """Return a portable conservative token estimate for a bounded digest."""

    return len(text.encode("utf-8"))


def _truncate_utf8(text: str, maximum_bytes: int) -> str:
    if maximum_bytes <= 0:
        return ""
    encoded = text.encode("utf-8")
    if len(encoded) <= maximum_bytes:
        return text
    suffix = "..."
    if maximum_bytes <= len(suffix):
        return suffix[:maximum_bytes]
    prefix = encoded[: maximum_bytes - len(suffix)]
    while prefix:
        try:
            return prefix.decode("utf-8") + suffix
        except UnicodeDecodeError:
            prefix = prefix[:-1]
    return suffix[:maximum_bytes]


def _bounded_excerpt(
    snapshot: _Snapshot, media_type: str, maximum_bytes: int
) -> tuple[str | None, bool]:
    maximum_bytes = min(maximum_bytes, MAX_EXCERPT_BYTES)
    if maximum_bytes <= 0:
        return None, snapshot.byte_count > 0
    textual = media_type.startswith("text/") or media_type in {
        "application/json",
        "application/xml",
        "application/yaml",
    }
    if textual:
        try:
            text = snapshot.prefix.decode("utf-8")
        except UnicodeDecodeError:
            text = f"Text artifact with invalid UTF-8 and {snapshot.byte_count} bytes"
            complete = False
        else:
            complete = len(snapshot.prefix) == snapshot.byte_count
        if not text.strip():
            text = "Empty text artifact"
            complete = snapshot.byte_count == 0
    else:
        text = f"Binary artifact with {snapshot.byte_count} bytes"
        complete = snapshot.byte_count == 0
    excerpt = _truncate_utf8(text, maximum_bytes)
    return excerpt or None, not (complete and excerpt == text)


def _iter_values(
    values: Iterable[Any] | Mapping[str, Any], context: str
) -> list[Any]:
    if isinstance(values, Mapping):
        result = list(values.values())
    else:
        try:
            result = list(values)
        except TypeError as error:
            raise ContextValidationError(f"{context} must be iterable") from error
    return result


def _reachable_references(
    task_id: str,
    attempt_id: str,
    references: Mapping[str, ContextReference],
    edges: Iterable[ContextEdge],
) -> dict[str, int]:
    edges_by_node: dict[str, list[tuple[ContextEdge, str]]] = {}
    for edge in edges:
        if edge.type not in TRAVERSABLE_EDGE_TYPES:
            continue
        if edge.type == "context_for":
            anchor, neighbor = edge.target_id, edge.source_id
        else:
            anchor, neighbor = edge.source_id, edge.target_id
        edges_by_node.setdefault(anchor, []).append((edge, neighbor))
    for connections in edges_by_node.values():
        connections.sort(key=lambda connection: (connection[0].type, connection[0].id))

    anchor_ids = {task_id, attempt_id}
    depth_by_id = {task_id: 0}
    visited = set(anchor_ids)
    queue = deque((anchor_id, 0) for anchor_id in (task_id, attempt_id))
    while queue:
        current_id, current_depth = queue.popleft()
        for edge, neighbor_id in edges_by_node.get(current_id, []):
            if neighbor_id not in references and neighbor_id not in anchor_ids:
                raise ContextValidationError(
                    f"{edge.type} edge {edge.id} references missing context {neighbor_id}"
                )
            if neighbor_id in visited:
                continue
            visited.add(neighbor_id)
            depth_by_id[neighbor_id] = current_depth + 1
            queue.append((neighbor_id, current_depth + 1))
    return depth_by_id


def compose_context_capsule(
    *,
    repository_root: Path | str,
    task_id: str,
    attempt_id: str,
    workspace_scope: Mapping[str, Any],
    references: Iterable[ContextReference | Mapping[str, Any]] | Mapping[str, Any],
    edges: Iterable[ContextEdge | Mapping[str, Any]] | Mapping[str, Any],
    budget: ContextBudget | Mapping[str, Any],
) -> dict[str, Any]:
    """Compose a deterministic capsule without copying full artifacts or transcripts."""

    normalized_task_id = _identifier(task_id, "task_id")
    normalized_attempt_id = _identifier(attempt_id, "attempt_id")
    if not isinstance(workspace_scope, Mapping):
        raise ContextValidationError("workspace_scope must be an object")
    _reject_transcript_fields(workspace_scope, "workspace_scope")
    try:
        normalized_scope = copy.deepcopy(dict(workspace_scope))
        json.dumps(normalized_scope, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ContextValidationError("workspace_scope must contain JSON values") from error

    raw_references = _iter_values(references, "references")
    if not raw_references or len(raw_references) > MAX_REFERENCES:
        raise ContextValidationError(
            f"references must contain from 1 through {MAX_REFERENCES} items"
        )
    reference_by_id: dict[str, ContextReference] = {}
    for index, value in enumerate(raw_references):
        reference = ContextReference.from_value(value, f"references[{index}]")
        if reference.id in reference_by_id:
            raise ContextValidationError(f"duplicate context reference ID: {reference.id}")
        reference_by_id[reference.id] = reference
    root_reference = reference_by_id.get(normalized_task_id)
    if root_reference is None or root_reference.kind != "task":
        raise ContextValidationError("task_id must name one task context reference")

    raw_edges = _iter_values(edges, "edges")
    if len(raw_edges) > MAX_EDGES:
        raise ContextValidationError(f"edges cannot exceed {MAX_EDGES} items")
    normalized_edges: list[ContextEdge] = []
    edge_ids: set[str] = set()
    for index, value in enumerate(raw_edges):
        edge = ContextEdge.from_value(value, f"edges[{index}]")
        if edge.id in edge_ids:
            raise ContextValidationError(f"duplicate context edge ID: {edge.id}")
        edge_ids.add(edge.id)
        normalized_edges.append(edge)

    normalized_budget = ContextBudget.from_value(budget)
    depth_by_id = _reachable_references(
        normalized_task_id, normalized_attempt_id, reference_by_id, normalized_edges
    )
    ordered_ids = sorted(
        depth_by_id,
        key=lambda reference_id: (
            0
            if reference_id == normalized_task_id
            else KIND_PRIORITY[reference_by_id[reference_id].kind],
            reference_by_id[reference_id].priority,
            depth_by_id[reference_id],
            reference_id,
        ),
    )

    snapshots = {
        reference_id: _read_snapshot(Path(repository_root), reference_by_id[reference_id])
        for reference_id in ordered_ids
    }
    selected_ids = ordered_ids[: normalized_budget.max_items]
    items: list[dict[str, Any]] = []
    used_bytes = 0
    used_tokens = 0
    referenced_bytes = 0
    for reference_id in selected_ids:
        reference = reference_by_id[reference_id]
        snapshot = snapshots[reference_id]
        available = min(
            normalized_budget.max_bytes - used_bytes,
            normalized_budget.max_tokens - used_tokens,
            MAX_EXCERPT_BYTES,
        )
        excerpt, truncated = _bounded_excerpt(snapshot, reference.media_type, available)
        excerpt_bytes = len(excerpt.encode("utf-8")) if excerpt is not None else 0
        excerpt_tokens = estimate_tokens(excerpt) if excerpt is not None else 0
        used_bytes += excerpt_bytes
        used_tokens += excerpt_tokens
        referenced_bytes += snapshot.byte_count
        items.append(
            {
                "id": reference.id,
                "kind": reference.kind,
                "origin": reference.origin,
                "snapshot_path": reference.snapshot_path,
                "content_hash": reference.content_hash,
                "revision": reference.revision,
                "media_type": reference.media_type,
                "title": reference.title,
                "priority": reference.priority,
                "byte_count": snapshot.byte_count,
                "excerpt": excerpt,
                "excerpt_bytes": excerpt_bytes,
                "excerpt_tokens": excerpt_tokens,
                "truncated": truncated,
            }
        )

    payload = {
        "task_id": normalized_task_id,
        "attempt_id": normalized_attempt_id,
        "workspace_scope": normalized_scope,
        "budget": normalized_budget.to_dict(),
        "usage": {
            "item_count": len(items),
            "content_bytes": used_bytes,
            "content_tokens": used_tokens,
            "referenced_bytes": referenced_bytes,
            "omitted_items": len(ordered_ids) - len(items),
        },
        "items": items,
    }
    canonical_payload = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    capsule_id = f"capsule-{hashlib.sha256(canonical_payload).hexdigest()}"
    return {"schema_version": SCHEMA_VERSION, "capsule_id": capsule_id, **payload}


def _expected_capsule_id(capsule: Mapping[str, Any]) -> str:
    payload = {
        key: value
        for key, value in capsule.items()
        if key not in {"schema_version", "capsule_id"}
    }
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    return f"capsule-{hashlib.sha256(encoded).hexdigest()}"


def _write_new_file(path: Path, content: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o444)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.fchmod(descriptor, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    directory_descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)


def write_context_capsule_once(
    repository_root: Path | str,
    relative_path: str,
    capsule: Mapping[str, Any],
) -> Path:
    """Durably create one capsule and reject every overwrite attempt."""

    safe_path = _safe_relative_path(relative_path, "capsule path")
    path_parts = PurePosixPath(safe_path).parts
    if path_parts[:2] != ("openspec", "runs") or len(path_parts) < 5:
        raise ContextValidationError("capsule path must be inside an OpenSpec run")
    if not isinstance(capsule, Mapping):
        raise ContextValidationError("capsule must be an object")
    _reject_transcript_fields(capsule, "capsule")
    if capsule.get("schema_version") != SCHEMA_VERSION:
        raise ContextValidationError(f"capsule schema_version must be {SCHEMA_VERSION}")
    if capsule.get("capsule_id") != _expected_capsule_id(capsule):
        raise ContextValidationError("capsule_id does not match the canonical capsule payload")
    root = Path(repository_root).resolve(strict=True)
    parent_relative = PurePosixPath(safe_path).parent.as_posix()
    parent = _confined_path(root, parent_relative, must_exist=False)
    parent.mkdir(parents=True, exist_ok=True)
    parent = _confined_path(root, parent_relative, must_exist=True)
    destination = parent / PurePosixPath(safe_path).name
    content = (
        json.dumps(capsule, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    ).encode("utf-8")
    try:
        _write_new_file(destination, content)
    except FileExistsError as error:
        raise CapsuleAlreadyExistsError(f"capsule already exists: {safe_path}") from error
    return destination


def materialize_maestro_note_revision(
    *,
    repository_root: Path | str,
    run_directory: Path | str,
    note_id: str,
    revision: str,
    expected_hash: str,
    title: str,
    actor: Mapping[str, Any],
    client: MaestroNoteClient,
    priority: int = 2,
) -> ContextReference:
    """Fetch, verify, pin, and materialize one immutable Maestro note revision."""

    normalized_note_id = _identifier(note_id, "note_id")
    normalized_revision = _identifier(revision, "revision")
    normalized_hash = _content_hash(expected_hash, "expected_hash")
    normalized_title = _bounded_string(title, "title", maximum=512)
    normalized_priority = _positive_integer(priority, "priority", maximum=5)
    if not isinstance(actor, Mapping) or not actor:
        raise NoteAuthorizationError("actor must be an authenticated actor envelope")
    _reject_transcript_fields(actor, "actor")

    root = Path(repository_root).resolve(strict=True)
    run_path = Path(run_directory).resolve(strict=True)
    try:
        run_relative = run_path.relative_to(root)
    except ValueError as error:
        raise ContextValidationError("run_directory escapes the repository") from error
    if run_relative.parts[:2] != ("openspec", "runs") or len(run_relative.parts) < 4:
        raise ContextValidationError("run_directory must identify openspec/runs/<change>/<run-id>")
    run_id = _identifier(run_path.name, "run_id")

    try:
        response = client.fetch_and_pin_revision(
            note_id=normalized_note_id,
            revision=normalized_revision,
            expected_hash=normalized_hash,
            run_id=run_id,
            actor=copy.deepcopy(dict(actor)),
        )
    except PermissionError as error:
        raise NoteAuthorizationError("authenticated actor cannot read the note revision") from error
    if not isinstance(response, Mapping):
        raise ContextValidationError("Maestro note response must be an object")
    status = response.get("status")
    if status == "unauthorized":
        raise NoteAuthorizationError("authenticated actor cannot read the note revision")
    if status in {"expired", "missing"}:
        raise NoteRevisionExpiredError(
            f"Maestro note revision is unavailable: {normalized_note_id}@{normalized_revision}"
        )
    if status != "ok":
        raise ContextValidationError(f"Maestro note response has invalid status: {status!r}")
    if response.get("note_id") != normalized_note_id:
        raise ContextValidationError("Maestro returned a different note ID")
    if response.get("revision") != normalized_revision:
        raise ContextValidationError("Maestro returned a different note revision")
    if response.get("media_type") != "text/markdown":
        raise ContextValidationError("Maestro note revision must be Markdown")
    content = response.get("content")
    if not isinstance(content, str):
        raise ContextValidationError("Maestro note content must be text")
    encoded_content = content.encode("utf-8")
    if len(encoded_content) > MAX_NOTE_BYTES:
        raise ContextValidationError(
            f"Maestro note revision exceeds {MAX_NOTE_BYTES} bytes"
        )
    actual_hash = _sha256_bytes(encoded_content)
    returned_hash = _content_hash(response.get("content_hash"), "response.content_hash")
    if returned_hash != normalized_hash or actual_hash != normalized_hash:
        raise ContentHashMismatchError(
            f"Maestro note hash mismatch for {normalized_note_id}@{normalized_revision}"
        )

    note_relative = (
        run_relative
        / "artifacts"
        / "maestro-notes"
        / normalized_note_id
        / f"{normalized_revision}.md"
    ).as_posix()
    note_path = PurePosixPath(note_relative)
    destination_parent = _confined_path(
        root, note_path.parent.as_posix(), must_exist=False
    )
    destination_parent.mkdir(parents=True, exist_ok=True)
    destination_parent = _confined_path(
        root, note_path.parent.as_posix(), must_exist=True
    )
    destination = destination_parent / note_path.name
    if destination.exists():
        existing_snapshot = _confined_path(root, note_relative, must_exist=True)
        if existing_snapshot != destination or not existing_snapshot.is_file():
            raise ContextValidationError(
                f"immutable Maestro note snapshot is unsafe: {note_relative}"
            )
        if existing_snapshot.read_bytes() != encoded_content:
            raise ContentHashMismatchError(
                f"immutable Maestro note snapshot already differs: {note_relative}"
            )
    else:
        _write_new_file(destination, encoded_content)

    return ContextReference(
        id=_identifier(
            f"note-{normalized_note_id}-{normalized_revision}", "note reference ID"
        ),
        kind="user-note",
        origin=f"maestro-note:{normalized_note_id}",
        snapshot_path=note_relative,
        content_hash=actual_hash,
        revision=normalized_revision,
        media_type="text/markdown",
        title=normalized_title,
        priority=normalized_priority,
    )


def release_maestro_note_revisions(
    *, client: MaestroNoteClient, run_id: str, actor: Mapping[str, Any]
) -> Mapping[str, Any]:
    """Release note leases only when the coordinator releases the owning run."""

    normalized_run_id = _identifier(run_id, "run_id")
    if not isinstance(actor, Mapping) or not actor:
        raise NoteAuthorizationError("actor must be an authenticated actor envelope")
    try:
        response = client.release_run_revisions(
            run_id=normalized_run_id, actor=copy.deepcopy(dict(actor))
        )
    except PermissionError as error:
        raise NoteAuthorizationError("authenticated actor cannot release note revisions") from error
    if not isinstance(response, Mapping):
        raise ContextValidationError("Maestro release response must be an object")
    if response.get("status") == "unauthorized":
        raise NoteAuthorizationError("authenticated actor cannot release note revisions")
    if response.get("status") != "released":
        raise ContextValidationError("Maestro did not confirm note revision release")
    return copy.deepcopy(dict(response))
