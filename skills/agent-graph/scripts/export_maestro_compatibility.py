#!/usr/bin/env python3
"""Export a portable Maestro compatibility bundle from immutable Harness evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

from graph_core import JournalError, replay_events


MANIFEST_VERSION = 1
RECEIPT_VERSION = 1
REQUIRED_TASKS = (
    ("MLK-05", "workspace-binding", 1),
    ("MLK-05R", "selected-placement-recovery", 1),
    ("MLK-06R", "typed-cleanup-lifecycle", 1),
    ("MLK-06D", "persisted-driver-context", 1),
    ("MLK-06Q", "result-quarantine", 1),
    ("MLK-07", "maestro-bridge", 1),
    ("MLK-07P", "run-progress", 1),
    ("MLK-20", "routing-policy", 1),
)
QUARANTINE_PRODUCER_TASKS = ("MLK-06Q", "MLK-06QR", "MLK-15")
GRAPH_PROGRESS_PRODUCER_TASKS = ("MLK-07", "MLK-07P", "MLK-19")
REQUIRED_PRODUCER_TASKS = tuple(task_id for task_id, _capability, _version in REQUIRED_TASKS) + (
    "MLK-06QR",
    "MLK-15",
    "MLK-19",
)
SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
CHECKED_IMPORT = "checked_import"
CHECK_RECORDED = "check_recorded"


class ExportError(RuntimeError):
    """Reports evidence that cannot establish compatibility authority."""


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _digest(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def _read_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise ExportError(f"{label} is missing or unsafe: {path}")
    try:
        content = path.read_bytes()
        value = json.loads(content)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExportError(f"{label} is unreadable: {error}") from error
    if not isinstance(value, dict):
        raise ExportError(f"{label} must be an object")
    return value, content


def _safe_relative(value: str) -> Path:
    path = Path(value)
    if not value or path.is_absolute() or "\\" in value or any(part in {"", ".", ".."} for part in path.parts):
        raise ExportError(f"unsafe evidence reference: {value!r}")
    return path


def _safe_external_directory(path: Path, label: str) -> Path:
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ExportError(f"{label} contains path traversal")
    if path.exists() and path.is_symlink():
        raise ExportError(f"{label} must not be a symbolic link")
    return path


def _evidence_digest(repo: Path, reference: Any) -> dict[str, str]:
    if not isinstance(reference, str) or not reference.startswith("file:"):
        raise ExportError("capability evidence must be a confined file reference")
    relative = _safe_relative(reference.removeprefix("file:"))
    path = repo / relative
    try:
        path.relative_to(repo)
    except ValueError as error:
        raise ExportError(f"evidence reference escapes repository: {reference}") from error
    if path.is_symlink() or not path.is_file():
        raise ExportError(f"evidence artifact is missing or unsafe: {reference}")
    return {"ref": reference, "digest": _digest(path.read_bytes())}


def _evidence_document(repo: Path, reference: Any, label: str) -> Mapping[str, Any]:
    evidence = _evidence_digest(repo, reference)
    path = repo / _safe_relative(evidence["ref"].removeprefix("file:"))
    try:
        document = json.loads(path.read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExportError(f"{label} is not immutable JSON evidence") from error
    if not isinstance(document, Mapping):
        raise ExportError(f"{label} must be an evidence object")
    return document


def _parse_events(content: bytes) -> list[dict[str, Any]]:
    if not content or not content.endswith(b"\n"):
        raise ExportError("events journal is incomplete")
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        try:
            event = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ExportError(f"events journal line {line_number} is invalid") from error
        if not isinstance(event, dict) or event.get("sequence") != line_number:
            raise ExportError(f"events journal sequence diverges at line {line_number}")
        events.append(event)
    if not events or events[-1].get("type") != "run_completed" or events[-1].get("data", {}).get("outcome") != "pass":
        raise ExportError("events journal does not end in a passing completed run")
    return events


def _require_completed_run(repo: Path, change: str, run_id: str) -> tuple[Path, dict[str, Any], dict[str, Any], dict[str, Any], dict[str, str]]:
    if not SAFE_COMPONENT.fullmatch(change) or not SAFE_COMPONENT.fullmatch(run_id):
        raise ExportError("change and run ID must be safe path components")
    run = repo / "openspec" / "runs" / change / run_id
    if run.is_symlink() or not run.is_dir():
        raise ExportError("producer run is missing or unsafe")
    state, state_bytes = _read_json(run / "state.json", "state projection")
    runtime, runtime_bytes = _read_json(run / "control-runtime-ref.json", "control-runtime reference")
    events_path = run / "events.jsonl"
    if events_path.is_symlink() or not events_path.is_file():
        raise ExportError("events journal is missing or unsafe")
    events_bytes = events_path.read_bytes()
    events = _parse_events(events_bytes)
    if state.get("schema_version") != 1 or state.get("change") != change or state.get("run_id") != run_id:
        raise ExportError("state projection identity diverges from requested producer run")
    if state.get("status") != "complete" or state.get("outcome") != "pass" or state.get("last_sequence") != events[-1]["sequence"]:
        raise ExportError("state projection is not the completed passing journal projection")
    if state.get("control_runtime") != runtime:
        raise ExportError("control-runtime reference diverges from the state projection")
    if runtime.get("schema_version") != 1 or runtime.get("protocol_version") != 1 or not SHA256.fullmatch(str(runtime.get("directory_digest", ""))):
        raise ExportError("control-runtime reference is invalid")
    # A released snapshot may no longer be present. Its persisted reference and digest are the authority.
    source_digests = {
        "events": _digest(events_bytes),
        "state": _digest(state_bytes),
        "control_runtime_ref": _digest(runtime_bytes),
    }
    return run, state, runtime, {"events": events, "source_digests": source_digests}, source_digests


def _verify_cleanup(state: Mapping[str, Any]) -> None:
    cleanup = state.get("cleanup")
    if not isinstance(cleanup, Mapping):
        raise ExportError("state cleanup projection is invalid")
    unresolved = []
    for cleanup_id, item in cleanup.items():
        if not isinstance(item, Mapping):
            unresolved.append(cleanup_id)
            continue
        status = item.get("status")
        if status == "verified":
            if item.get("identity_version") != 1 or not isinstance(item.get("owner"), Mapping):
                unresolved.append(cleanup_id)
            continue
        if status == "done":
            receipt = item.get("receipt")
            if not isinstance(item.get("owner"), str) or "identity_version" in item:
                unresolved.append(cleanup_id)
            elif receipt is not None and (
                not isinstance(receipt, Mapping) or receipt.get("status") != "verified"
            ):
                unresolved.append(cleanup_id)
            continue
        unresolved.append(cleanup_id)
    if unresolved:
        raise ExportError(f"producer run has unresolved owned cleanup: {', '.join(sorted(unresolved))}")


def _verify_projection_against_journal(
    state: Mapping[str, Any], events: list[Mapping[str, Any]]
) -> tuple[dict[str, str], Mapping[str, Any]]:
    started = events[0].get("data")
    if not isinstance(started, Mapping):
        raise ExportError("journal is missing its run-start evidence")
    started_scope = dict(started.get("workspace_scope", {}))
    state_scope = dict(state.get("workspace_scope", {}))
    # Coordinator generation changes during a fenced handoff; every execution identity is immutable.
    started_scope.pop("coordinator_generation", None)
    state_scope.pop("coordinator_generation", None)
    if started_scope != state_scope:
        raise ExportError("state workspace identity diverges from the journal")
    if started.get("control_runtime") != state.get("control_runtime"):
        raise ExportError("state control-runtime identity diverges from the journal")
    imported = {
        event.get("data", {}).get("task_id"): event.get("data")
        for event in events
        if event.get("type") == "checked_task_imported" and isinstance(event.get("data"), Mapping)
    }
    recorded_checks = {
        event.get("data", {}).get("task_id"): event.get("data")
        for event in events
        if event.get("type") == "check_recorded" and isinstance(event.get("data"), Mapping)
    }
    graded = {
        event.get("data", {}).get("task_id"): event.get("data")
        for event in events
        if event.get("type") == "task_graded" and isinstance(event.get("data"), Mapping)
    }
    tasks = state.get("tasks")
    if not isinstance(tasks, Mapping):
        raise ExportError("state task projection is invalid")
    check_authorities: dict[str, str] = {}
    for task_id in REQUIRED_PRODUCER_TASKS:
        task = tasks.get(task_id)
        if not isinstance(task, Mapping):
            raise ExportError(f"required capability task is absent from the state: {task_id}")
        imported_event = imported.get(task_id)
        if isinstance(imported_event, Mapping):
            task_import = task.get("import_receipt")
            if not isinstance(task_import, Mapping) or task.get("check") != imported_event.get("check") or task_import.get("import_id") != imported_event.get("import_id"):
                raise ExportError(f"state task evidence diverges from the checked import journal: {task_id}")
            check_authorities[task_id] = CHECKED_IMPORT
            continue
        check_event = recorded_checks.get(task_id)
        grade_event = graded.get(task_id)
        if not isinstance(check_event, Mapping) or not isinstance(grade_event, Mapping):
            raise ExportError(f"required capability task is absent from the grade/check journal: {task_id}")
        if task.get("import_receipt") is not None or task.get("check") != check_event or task.get("grade") != grade_event.get("grade") or task.get("evidence_refs") != grade_event.get("evidence_refs"):
            raise ExportError(f"state task evidence diverges from the ordinary grade journal: {task_id}")
        if check_event.get("status") != "passed":
            raise ExportError(f"ordinary check journal is not passing: {task_id}")
        check_authorities[task_id] = CHECK_RECORDED
    try:
        replayed = replay_events(events)
    except JournalError as error:
        raise ExportError(f"cleanup journal replay failed: {error}") from error
    replayed_cleanup = replayed.get("cleanup")
    state_cleanup = state.get("cleanup")
    if not isinstance(replayed_cleanup, Mapping) or not isinstance(state_cleanup, Mapping):
        raise ExportError("cleanup replay projection is invalid")
    if _canonical_bytes(dict(replayed_cleanup)) != _canonical_bytes(dict(state_cleanup)):
        raise ExportError("state cleanup projection diverges from canonical journal replay")
    replayed_tasks = replayed.get("tasks")
    if not isinstance(replayed_tasks, Mapping):
        raise ExportError("canonical journal replay has no task projection")
    for task_id in REQUIRED_PRODUCER_TASKS:
        replayed_task = replayed_tasks.get(task_id)
        state_task = tasks.get(task_id)
        if not isinstance(replayed_task, Mapping) or not isinstance(state_task, Mapping):
            raise ExportError(f"canonical journal replay has no producer task: {task_id}")
        for field in ("status", "grade", "check", "import_receipt", "evidence_refs"):
            if replayed_task.get(field) != state_task.get(field):
                raise ExportError(f"producer task diverges from canonical journal replay: {task_id}")
    return check_authorities, replayed


def _checked_execution_binding(
    state: Mapping[str, Any],
    replayed: Mapping[str, Any],
    check: Mapping[str, Any],
    task_id: str,
    import_receipt: Mapping[str, Any] | None,
    document: Mapping[str, Any],
) -> dict[str, str] | None:
    if document.get("schema_version") != 1 or not all(
        field in document
        for field in ("execution_id", "command_digest", "source_snapshot_digest")
    ):
        return None
    reference = check.get("evidence_ref")
    artifact_ref = reference.removeprefix("file:") if isinstance(reference, str) else check.get("artifact")
    executions = state.get("check_executions")
    if not isinstance(executions, Mapping):
        raise ExportError(f"checked import lacks CheckExecution projection: {task_id}")
    matches = [entry for entry in executions.values() if isinstance(entry, Mapping) and entry.get("artifact_ref") == artifact_ref]
    if isinstance(import_receipt, Mapping):
        consumer_ref = f"import:{task_id}:{import_receipt.get('import_id')}"
        matches = [entry for entry in matches if consumer_ref in entry.get("consumer_refs", ())]
    if len(matches) != 1:
        raise ExportError(f"checked import must resolve exactly one CheckExecution: {task_id}")
    execution = matches[0]
    replayed_executions = replayed.get("check_executions")
    replayed_execution = (
        replayed_executions.get(execution.get("execution_id"))
        if isinstance(replayed_executions, Mapping)
        else None
    )
    if (
        execution.get("lifecycle") != "passed"
        or replayed_execution != execution
        or document.get("execution_id") != execution.get("execution_id")
        or document.get("command_digest") != execution.get("command_digest")
        or document.get("source_snapshot_digest") != execution.get("source_snapshot_digest")
        or document.get("timeout_seconds") != execution.get("timeout_seconds")
        or document.get("output_cap_bytes") != execution.get("output_cap_bytes")
        or document.get("exit_code") != 0
        or check.get("exit_code") != 0
        or document.get("exit_code") != check.get("exit_code")
        or document.get("timed_out") is not False
        or ("execution_id" in check and check.get("execution_id") != execution.get("execution_id"))
        or ("command_digest" in check and check.get("command_digest") != execution.get("command_digest"))
        or (
            "source_snapshot_digest" in check
            and check.get("source_snapshot_digest") != execution.get("source_snapshot_digest")
        )
        or (
            "timeout_seconds" in check
            and check.get("timeout_seconds") != execution.get("timeout_seconds")
        )
        or (
            "output_cap_bytes" in check
            and check.get("output_cap_bytes") != execution.get("output_cap_bytes")
        )
    ):
        raise ExportError(f"CheckExecution evidence diverges from canonical authority: {task_id}")
    return {
        "execution_id": str(execution["execution_id"]),
        "command_digest": str(execution["command_digest"]),
        "source_snapshot_digest": str(execution["source_snapshot_digest"]),
    }


def _check_evidence(
    repo: Path,
    state: Mapping[str, Any],
    replayed: Mapping[str, Any],
    check: Mapping[str, Any],
    task_id: str,
    authority: str,
    import_receipt: Mapping[str, Any] | None,
) -> tuple[dict[str, str], dict[str, str] | None]:
    reference = check.get("evidence_ref")
    if reference is None:
        artifact = check.get("artifact")
        reference = f"file:{artifact}" if isinstance(artifact, str) else None
    document = _evidence_document(repo, reference, "check evidence")
    execution = _checked_execution_binding(
        state, replayed, check, task_id, import_receipt, document
    )
    if execution is not None:
        return _evidence_digest(repo, reference), execution
    if document.get("command") != check.get("command") or check.get("exit_code") != 0 or document.get("exit_code") != check.get("exit_code"):
        raise ExportError("check evidence diverges from the passing task check")
    if authority == CHECKED_IMPORT:
        if not isinstance(import_receipt, Mapping):
            raise ExportError(f"checked import receipt is absent: {task_id}")
        if (
            document.get("status") != "passed"
            or document.get("task_id") != task_id
            or document.get("import_id") != import_receipt.get("import_id")
            or document.get("command") != check.get("command")
            or document.get("exit_code") != 0
        ):
            raise ExportError("legacy checked import evidence is not passing")
        return _evidence_digest(repo, reference), None
    if authority != CHECK_RECORDED:
        raise ExportError("task check authority is invalid")
    if (
        check.get("status") != "passed"
        or check.get("task_id") != task_id
        or not isinstance(check.get("attempt_id"), str)
        or not check["attempt_id"]
        or check.get("exit_code") != 0
        or check.get("timed_out") is not False
        or document.get("timed_out") is not False
        or ("status" in document and document["status"] != "passed")
        or ("task_id" in document and document["task_id"] != task_id)
        or ("attempt_id" in document and document["attempt_id"] != check.get("attempt_id"))
    ):
        raise ExportError("ordinary check evidence diverges from the passing task check")
    return _evidence_digest(repo, reference), None


def _task_evidence(
    repo: Path,
    state: Mapping[str, Any],
    task_id: str,
    *,
    require_evidence_refs: bool,
    check_authorities: Mapping[str, str],
    replayed: Mapping[str, Any],
) -> dict[str, Any]:
    tasks = state.get("tasks")
    task = tasks.get(task_id) if isinstance(tasks, Mapping) else None
    if not isinstance(task, Mapping) or task.get("grade") != "pass" or task.get("status") != "pass":
        raise ExportError(f"required capability task is not passing: {task_id}")
    check = task.get("check")
    if not isinstance(check, Mapping) or check.get("status") != "passed":
        raise ExportError(f"required capability task lacks passing check evidence: {task_id}")
    authority = check_authorities.get(task_id)
    if authority not in {CHECKED_IMPORT, CHECK_RECORDED}:
        raise ExportError(f"required capability task lacks journal check authority: {task_id}")
    if authority == CHECK_RECORDED:
        attempt_ids = task.get("attempt_ids")
        if not isinstance(attempt_ids, list) or check.get("attempt_id") not in attempt_ids:
            raise ExportError(f"ordinary check attempt identity diverges from the state: {task_id}")
    references = task.get("evidence_refs")
    if not isinstance(references, list) or (require_evidence_refs and not references):
        raise ExportError(f"required capability task lacks immutable evidence refs: {task_id}")
    evidence = [_evidence_digest(repo, reference) for reference in references]
    import_receipt = task.get("import_receipt")
    if import_receipt is not None:
        if not isinstance(import_receipt, Mapping) or import_receipt.get("task_id") != task_id or import_receipt.get("source_checked") is not True:
            raise ExportError(f"checked import evidence diverges for {task_id}")
        if import_receipt.get("evidence_ref") != check.get("evidence_ref"):
            raise ExportError(f"checked import evidence reference diverges for {task_id}")
        evidence.append(_evidence_digest(repo, import_receipt.get("evidence_ref")))
    check_evidence, execution = _check_evidence(
        repo, state, replayed, check, task_id, authority, import_receipt
    )
    return {
        "task_id": task_id,
        "grade": "pass",
        "check": {
            "authority": authority,
            "command": check.get("command"),
            "evidence": check_evidence,
            "execution": execution,
        },
        "import": None if import_receipt is None else {"import_id": import_receipt.get("import_id"), "evidence": _evidence_digest(repo, import_receipt.get("evidence_ref"))},
        "evidence": [{"ref": reference, "digest": digest} for reference, digest in sorted({(entry["ref"], entry["digest"]) for entry in evidence})],
    }


def _routing_policy_binding(
    repo: Path,
    state: Mapping[str, Any],
    replayed: Mapping[str, Any],
    task_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    relative = Path("openspec") / "runs" / str(state["change"]) / str(state["run_id"]) / "artifacts" / "routing-policy-v1.json"
    reference = f"file:{relative.as_posix()}"
    policy, policy_bytes = _read_json(repo / relative, "pinned routing policy")
    policy_id = policy.get("policy_id")
    if not isinstance(policy_id, str) or not policy_id:
        raise ExportError("pinned routing policy has no policy ID")
    task = state.get("tasks", {}).get("MLK-20")
    check = task.get("check") if isinstance(task, Mapping) else None
    attempt_id = check.get("attempt_id") if isinstance(check, Mapping) else None
    attempts = state.get("attempts")
    attempt = attempts.get(attempt_id) if isinstance(attempts, Mapping) else None
    replayed_attempts = replayed.get("attempts")
    replayed_attempt = (
        replayed_attempts.get(attempt_id) if isinstance(replayed_attempts, Mapping) else None
    )
    routing_summary = attempt.get("routing_summary") if isinstance(attempt, Mapping) else None
    canonical_digest = _digest(
        json.dumps(policy, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    producer_refs = {
        entry.get("ref")
        for entry in task_evidence.get("evidence", ())
        if isinstance(entry, Mapping)
    }
    if (
        not isinstance(attempt, Mapping)
        or not isinstance(replayed_attempt, Mapping)
        or replayed_attempt.get("routing_summary") != routing_summary
        or not isinstance(routing_summary, Mapping)
        or routing_summary.get("policy_id") != policy_id
        or routing_summary.get("policy_digest") != canonical_digest
        or reference not in producer_refs
    ):
        raise ExportError("MLK-20 routing policy diverges from approved producer authority")
    return {
        "policy_id": policy_id,
        "path": relative.as_posix(),
        "digest": canonical_digest,
        "evidence": {"ref": reference, "digest": _digest(policy_bytes)},
    }


def _receipt_for_task(
    repo: Path,
    state: Mapping[str, Any],
    runtime: Mapping[str, Any],
    task_id: str,
    capability: str,
    version: int,
    source_digests: Mapping[str, str],
    check_authorities: Mapping[str, str],
    replayed: Mapping[str, Any],
) -> tuple[dict[str, Any], bytes]:
    task_evidence = _task_evidence(
        repo,
        state,
        task_id,
        require_evidence_refs=True,
        check_authorities=check_authorities,
        replayed=replayed,
    )
    receipt = {
        "schema_version": RECEIPT_VERSION,
        "producer": {
            "run_id": state["run_id"],
            "change": state["change"],
            "journal_digest": source_digests["events"],
            "state_digest": source_digests["state"],
            "control_runtime": {
                "reference_digest": source_digests["control_runtime_ref"],
                "directory_digest": runtime["directory_digest"],
                "source_revision": runtime["source_revision"],
            },
            "workspace_scope": state["workspace_scope"],
        },
        "task_id": task_id,
        "capability": {"name": capability, "version": version},
        **task_evidence,
    }
    if task_id == "MLK-06Q":
        receipt["required_producers"] = [
            _task_evidence(repo, state, producer_task_id, require_evidence_refs=False, check_authorities=check_authorities, replayed=replayed)
            for producer_task_id in QUARANTINE_PRODUCER_TASKS
        ]
    elif task_id == "MLK-07P":
        receipt["required_producers"] = [
            _task_evidence(repo, state, producer_task_id, require_evidence_refs=False, check_authorities=check_authorities, replayed=replayed)
            for producer_task_id in GRAPH_PROGRESS_PRODUCER_TASKS
        ]
    elif task_id == "MLK-20":
        receipt["routing_policy"] = _routing_policy_binding(
            repo, state, replayed, task_evidence
        )
    return receipt, _canonical_bytes(receipt)


def _assert_safe_directory(path: Path) -> None:
    current = path.anchor and Path(path.anchor) or Path()
    for part in path.parts[1:] if path.is_absolute() else path.parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise ExportError(f"symbolic links are forbidden in output path: {current}")


def _write_bundle(output: Path, manifest: Mapping[str, Any], receipts: Mapping[str, bytes]) -> Path:
    _assert_safe_directory(output)
    output.mkdir(parents=True, exist_ok=True)
    if output.is_symlink() or not output.is_dir():
        raise ExportError("output must be a real directory")
    digest = _digest(_canonical_bytes(manifest)).removeprefix("sha256:")
    parent = output / "sha256"
    _assert_safe_directory(parent)
    parent.mkdir(exist_ok=True)
    destination = parent / digest
    expected = {"manifest.json": _canonical_bytes(manifest), **{f"receipts/{task_id}.json": content for task_id, content in receipts.items()}}
    if destination.exists():
        if destination.is_symlink() or not destination.is_dir():
            raise ExportError("content-addressed output collision is unsafe")
        actual = {path.relative_to(destination).as_posix(): path.read_bytes() for path in destination.rglob("*") if path.is_file() and not path.is_symlink()}
        if actual != expected:
            raise ExportError("content-addressed output collision differs from immutable bundle")
        return destination
    staging = Path(tempfile.mkdtemp(prefix=".maestro-compatibility-", dir=parent))
    try:
        for relative, content in expected.items():
            path = staging / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        os.replace(staging, destination)
    except BaseException:
        if staging.exists():
            for path in sorted(staging.rglob("*"), reverse=True):
                if path.is_file() or path.is_symlink():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            staging.rmdir()
        raise
    return destination


def export_bundle(repo: Path, change: str, run_id: str, output: Path) -> Path:
    repo = _safe_external_directory(repo, "repository").resolve()
    output = _safe_external_directory(output, "output directory")
    run, state, runtime, details, source_digests = _require_completed_run(repo, change, run_id)
    _ = run
    check_authorities, replayed = _verify_projection_against_journal(state, details["events"])
    _verify_cleanup(state)
    receipts: dict[str, bytes] = {}
    receipt_entries: list[dict[str, Any]] = []
    for task_id, capability, version in REQUIRED_TASKS:
        receipt, content = _receipt_for_task(repo, state, runtime, task_id, capability, version, source_digests, check_authorities, replayed)
        receipts[task_id] = content
        receipt_entries.append({"task_id": task_id, "capability": receipt["capability"], "path": f"receipts/{task_id}.json", "digest": _digest(content)})
    manifest = {
        "schema_version": MANIFEST_VERSION,
        "producer": {
            "run_id": run_id,
            "change": change,
            "journal_digest": source_digests["events"],
            "state_digest": source_digests["state"],
            "control_runtime_reference_digest": source_digests["control_runtime_ref"],
            "control_runtime_directory_digest": runtime["directory_digest"],
            "workspace_scope": state["workspace_scope"],
        },
        "required_capabilities": [{"task_id": task_id, "name": capability, "version": version} for task_id, capability, version in REQUIRED_TASKS],
        "receipts": receipt_entries,
    }
    return _write_bundle(output, manifest, receipts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--change", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args(argv)
    try:
        destination = export_bundle(arguments.repo, arguments.change, arguments.run_id, arguments.output)
    except ExportError as error:
        print(f"export_maestro_compatibility: {error}", file=sys.stderr)
        return 2
    print(json.dumps({"bundle": str(destination), "manifest": str(destination / "manifest.json")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
