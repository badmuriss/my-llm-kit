#!/usr/bin/env python3
"""Record evidence-backed impl observations without activating rules."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

from runtime_config import RuntimeConfigError, add_runtime_arguments, runtime_from_arguments


SCHEMA_VERSION = 1
MIN_RECURRING_CHANGES = 5
STATE_DIRECTORY = Path("openspec/impl-state")
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


def require_string_list(value: Any, context: str, *, allow_empty: bool) -> list[str]:
    if not isinstance(value, list):
        raise LearningError(f"{context} must be an array")
    if not allow_empty and not value:
        raise LearningError(f"{context} must not be empty")
    entries = [require_string(entry, f"{context}[]") for entry in value]
    if len(entries) != len(set(entries)):
        raise LearningError(f"{context} must not contain duplicates")
    return entries


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
    if not isinstance(tasks, list) or not tasks:
        raise LearningError(f"{path}.tasks must be a non-empty array")
    for index, task in enumerate(tasks):
        context = f"{path}.tasks[{index}]"
        if not isinstance(task, dict):
            raise LearningError(f"{context} must be an object")
        require_string(task.get("id"), f"{context}.id")
        if task.get("status") not in TASK_STATUSES:
            raise LearningError(f"{context}.status must be terminal")
        check = task.get("check")
        if not isinstance(check, dict):
            raise LearningError(f"{context}.check must be an object")
        if not isinstance(check.get("attempts"), int) or check["attempts"] < 0:
            raise LearningError(f"{context}.check.attempts must be non-negative")
    return state


def task_fact(task: dict[str, Any]) -> dict[str, Any]:
    check = task["check"]
    return {
        "task_id": task["id"],
        "status": task["status"],
        "check_command": check.get("command"),
        "check_status": check.get("status"),
        "check_attempts": check["attempts"],
        "check_exit_code": check.get("exit_code"),
        "check_duration_ms": check.get("duration_ms"),
        "check_total_duration_ms": check.get("total_duration_ms", check.get("duration_ms") or 0),
        "hypotheses": list(task.get("hypotheses", [])),
        "evidence_refs": list(task.get("evidence_refs", [])),
        "visual_expectations": list(task.get("visual_expectations", [])),
        "visual_scopes": list(task.get("visual_scopes", [])),
    }


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
        "facts",
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
    require_string(record["observed_at"], f"{path}.observed_at")
    require_string(record["state_ref"], f"{path}.state_ref")
    digest = require_string(record["state_sha256"], f"{path}.state_sha256")
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise LearningError(f"{path}.state_sha256 must be a SHA-256 digest")
    if record["outcome"] not in {"pass", "partial", "blocked"}:
        raise LearningError(f"{path}.outcome is invalid")
    facts = record["facts"]
    if not isinstance(facts, list) or not facts:
        raise LearningError(f"{path}.facts must be a non-empty array")
    task_ids: set[str] = set()
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
        }
        if fact.keys() != expected_fact_fields:
            raise LearningError(f"{context} has missing or unknown fields")
        task_id = require_string(fact.get("task_id"), f"{context}.task_id")
        if task_id in task_ids:
            raise LearningError(f"{path}.facts contains duplicate task ids")
        task_ids.add(task_id)
        if fact.get("status") not in TASK_STATUSES:
            raise LearningError(f"{context}.status is invalid")
        attempts = fact.get("check_attempts")
        if not isinstance(attempts, int) or attempts < 0:
            raise LearningError(f"{context}.check_attempts must be non-negative")
    candidates = record["candidates"]
    if not isinstance(candidates, list):
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
        scopes = require_string_list(candidate["scopes"], f"{context}.scopes", allow_empty=False)
        for scope in scopes:
            require_key(scope, f"{context}.scopes[]")
        require_string(candidate["statement"], f"{context}.statement")
        if candidate["origin"] not in ORIGINS:
            raise LearningError(f"{context}.origin is invalid")
        require_string(candidate["evidence"], f"{context}.evidence")
        refs = require_string_list(candidate["task_refs"], f"{context}.task_refs", allow_empty=False)
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
    state_path = repo / STATE_DIRECTORY / f"{change}.json"
    state = validate_completed_state(read_json(state_path), state_path)
    output = repo / RUNS_DIRECTORY / f"{state['run_id']}.json"
    evidence_path = repo / EVIDENCE_DIRECTORY / f"{state['run_id']}.state.json"
    if output.exists() or evidence_path.exists():
        raise LearningError(f"observation evidence already exists for run {state['run_id']}")
    state_content = state_path.read_text(encoding="utf-8")
    atomic_write_text(evidence_path, state_content)
    record = {
        "schema_version": SCHEMA_VERSION,
        "run_id": state["run_id"],
        "change": state["change"],
        "observed_at": now(),
        "state_ref": evidence_path.relative_to(repo).as_posix(),
        "state_sha256": sha256(evidence_path),
        "outcome": state["outcome"],
        "facts": [task_fact(task) for task in state["tasks"]],
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


def metrics(state: dict[str, Any]) -> dict[str, int]:
    tasks = state["tasks"]
    return {
        "tasks": len(tasks),
        "passed": sum(task["status"] == "pass" for task in tasks),
        "failed": sum(task["status"] == "fail" for task in tasks),
        "unobserved": sum(task["status"] == "unobserved" for task in tasks),
        "blocked": sum(task["status"] == "blocked" for task in tasks),
        "check_attempts": sum(task["check"]["attempts"] for task in tasks),
        "check_total_duration_ms": sum(
            task["check"].get("total_duration_ms", task["check"].get("duration_ms") or 0)
            for task in tasks
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
    delta = {key: on_metrics[key] - off_metrics[key] for key in off_metrics if key != "tasks"}
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
