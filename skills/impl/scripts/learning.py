#!/usr/bin/env python3
"""Validate impl runs and compile verified project-local learning artifacts."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

from runtime_config import RuntimeConfigError, add_runtime_arguments, runtime_from_arguments


SCHEMA_VERSION = 3
PROMOTION_MIN_DISTINCT_CHANGES = 2
LEARNING_ROOT = Path("openspec/impl-learning")
RUNS_DIRECTORY = LEARNING_ROOT / "runs"
ACTIVE_RULES_FILE = LEARNING_ROOT / "ACTIVE_RULES.md"
GATE_CANDIDATES_FILE = LEARNING_ROOT / "GATE_CANDIDATES.md"
QUALITY_SIGNALS_FILE = LEARNING_ROOT / "QUALITY_SIGNALS.md"
SKILL_INDEX_FILE = LEARNING_ROOT / "SKILLS.md"
SKILLS_DIRECTORY = LEARNING_ROOT / "skills"
ALLOWED_OUTCOMES = {"pass", "partial", "blocked"}
ALLOWED_GRADES = {"pass", "fail", "unobserved", "blocked"}
ALLOWED_LEARNING_KINDS = {"rule", "gate_candidate", "skill"}
ALLOWED_INCIDENT_KINDS = {
    "defect",
    "conflict",
    "retry",
    "resource_denial",
    "stale_process",
    "crash_recovery",
}
ALLOWED_INCIDENT_STATUSES = {"open", "verified", "rejected", "inconclusive"}
KEY_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*$")
COMMIT_PATTERN = re.compile(r"^(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$")
EXTERNAL_EVIDENCE_KINDS = {"file", "commit"}
INTERNAL_EVIDENCE_KINDS = {"task", "incident"}


class LearningError(ValueError):
    """Reports invalid or inconsistent learning state."""


@dataclass(frozen=True)
class TaskGrade:
    task_id: str
    grade: str
    evidence: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class Incident:
    key: str
    kind: str
    status: str
    symptom: str
    hypothesis: str
    proposed_fix: str
    verification_plan: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class Learning:
    key: str
    kind: str
    scopes: tuple[str, ...]
    rule: str
    evidence: str
    evidence_refs: tuple[str, ...]
    supersedes: tuple[str, ...]
    skill_name: str | None
    skill_description: str | None


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    change: str
    completed_at: str
    outcome: str
    tasks: tuple[TaskGrade, ...]
    incidents: tuple[Incident, ...]
    learnings: tuple[Learning, ...]


@dataclass(frozen=True)
class LearningOccurrence:
    run_id: str
    change: str
    learning: Learning


def require_object(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LearningError(f"{context} must be an object")
    return value


def require_list(value: Any, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise LearningError(f"{context} must be an array")
    return value


def require_string(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LearningError(f"{context} must be a non-empty string")
    return value.strip()


def require_keys(
    value: dict[str, Any],
    context: str,
    *,
    required: set[str],
    optional: set[str] | None = None,
) -> None:
    optional = optional or set()
    missing = required - value.keys()
    if missing:
        raise LearningError(f"{context} is missing: {', '.join(sorted(missing))}")
    unknown = value.keys() - required - optional
    if unknown:
        raise LearningError(f"{context} has unknown fields: {', '.join(sorted(unknown))}")


def require_datetime(value: Any, context: str) -> str:
    timestamp = require_string(value, context)
    iso_timestamp = f"{timestamp[:-1]}+00:00" if timestamp.endswith("Z") else timestamp
    try:
        parsed = datetime.fromisoformat(iso_timestamp)
    except ValueError as error:
        raise LearningError(f"{context} must be an ISO 8601 date-time") from error
    if parsed.tzinfo is None:
        raise LearningError(f"{context} must include a timezone")
    return timestamp


def require_string_list(
    value: Any,
    context: str,
    *,
    allow_empty: bool,
) -> tuple[str, ...]:
    entries = require_list(value, context)
    if not allow_empty and not entries:
        raise LearningError(f"{context} must contain at least one entry")
    strings = tuple(require_string(entry, f"{context}[]") for entry in entries)
    if len(strings) != len(set(strings)):
        raise LearningError(f"{context} must not contain duplicates")
    return tuple(sorted(strings))


def require_enum(value: Any, context: str, allowed: set[str]) -> str:
    entry = require_string(value, context)
    if entry not in allowed:
        choices = ", ".join(sorted(allowed))
        raise LearningError(f"{context} must be one of: {choices}")
    return entry


def require_key(value: Any, context: str) -> str:
    key = require_string(value, context)
    if not KEY_PATTERN.fullmatch(key):
        raise LearningError(
            f"{context} must use lowercase letters, numbers, dots, underscores, or hyphens"
        )
    return key


def require_identifier(value: Any, context: str) -> str:
    identifier = require_string(value, context)
    if not IDENTIFIER_PATTERN.fullmatch(identifier):
        raise LearningError(f"{context} must be a path-safe identifier")
    return identifier


def parse_task(value: Any, context: str) -> TaskGrade:
    task = require_object(value, context)
    require_keys(
        task,
        context,
        required={"id", "grade", "evidence", "evidence_refs"},
    )
    return TaskGrade(
        task_id=require_identifier(task.get("id"), f"{context}.id"),
        grade=require_enum(task.get("grade"), f"{context}.grade", ALLOWED_GRADES),
        evidence=require_string(task.get("evidence"), f"{context}.evidence"),
        evidence_refs=require_string_list(
            task.get("evidence_refs"),
            f"{context}.evidence_refs",
            allow_empty=True,
        ),
    )


def parse_incident(value: Any, context: str) -> Incident:
    incident = require_object(value, context)
    require_keys(
        incident,
        context,
        required={
            "key",
            "kind",
            "status",
            "symptom",
            "hypothesis",
            "proposed_fix",
            "verification_plan",
            "evidence_refs",
        },
    )
    return Incident(
        key=require_key(incident.get("key"), f"{context}.key"),
        kind=require_enum(
            incident.get("kind"),
            f"{context}.kind",
            ALLOWED_INCIDENT_KINDS,
        ),
        status=require_enum(
            incident.get("status"),
            f"{context}.status",
            ALLOWED_INCIDENT_STATUSES,
        ),
        symptom=require_string(incident.get("symptom"), f"{context}.symptom"),
        hypothesis=require_string(incident.get("hypothesis"), f"{context}.hypothesis"),
        proposed_fix=require_string(
            incident.get("proposed_fix"),
            f"{context}.proposed_fix",
        ),
        verification_plan=require_string(
            incident.get("verification_plan"),
            f"{context}.verification_plan",
        ),
        evidence_refs=require_string_list(
            incident.get("evidence_refs"),
            f"{context}.evidence_refs",
            allow_empty=True,
        ),
    )


def parse_learning(value: Any, context: str) -> Learning:
    learning = require_object(value, context)
    require_keys(
        learning,
        context,
        required={
            "key",
            "kind",
            "scopes",
            "rule",
            "evidence",
            "evidence_refs",
        },
        optional={"supersedes", "skill_name", "skill_description"},
    )
    key = require_key(learning.get("key"), f"{context}.key")
    supersedes = require_string_list(
        learning.get("supersedes", []),
        f"{context}.supersedes",
        allow_empty=True,
    )
    if key in supersedes:
        raise LearningError(f"{context}.supersedes cannot contain its own key")
    kind = require_enum(
        learning.get("kind"),
        f"{context}.kind",
        ALLOWED_LEARNING_KINDS,
    )
    if kind == "gate_candidate" and supersedes:
        raise LearningError(f"{context}: gate candidates cannot supersede active rules")
    if kind == "skill" and supersedes:
        raise LearningError(f"{context}: skill learnings cannot supersede active rules")
    skill_name = learning.get("skill_name")
    skill_description = learning.get("skill_description")
    if kind == "skill":
        skill_name = require_string(skill_name, f"{context}.skill_name")
        if not SKILL_NAME_PATTERN.fullmatch(skill_name):
            raise LearningError(
                f"{context}.skill_name must use lowercase letters, numbers, and hyphens"
            )
        skill_description = require_string(
            skill_description,
            f"{context}.skill_description",
        )
    elif skill_name is not None or skill_description is not None:
        raise LearningError(f"{context}: skill fields require kind skill")
    scopes = require_string_list(
        learning.get("scopes"),
        f"{context}.scopes",
        allow_empty=False,
    )
    for scope in scopes:
        require_key(scope, f"{context}.scopes[]")
    return Learning(
        key=key,
        kind=kind,
        scopes=scopes,
        rule=require_string(learning.get("rule"), f"{context}.rule"),
        evidence=require_string(learning.get("evidence"), f"{context}.evidence"),
        evidence_refs=require_string_list(
            learning.get("evidence_refs"),
            f"{context}.evidence_refs",
            allow_empty=False,
        ),
        supersedes=supersedes,
        skill_name=skill_name,
        skill_description=skill_description,
    )


def parse_run_file(path: Path) -> RunRecord:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise LearningError(f"{path}: invalid JSON: {error.msg}") from error

    run = require_object(raw, str(path))
    require_keys(
        run,
        str(path),
        required={
            "schema_version",
            "run_id",
            "change",
            "completed_at",
            "outcome",
            "tasks",
            "incidents",
            "learnings",
        },
    )
    if run.get("schema_version") != SCHEMA_VERSION:
        raise LearningError(f"{path}: schema_version must be {SCHEMA_VERSION}")

    tasks = tuple(
        parse_task(task, f"{path}.tasks[{index}]")
        for index, task in enumerate(require_list(run.get("tasks"), f"{path}.tasks"))
    )
    incidents = tuple(
        parse_incident(incident, f"{path}.incidents[{index}]")
        for index, incident in enumerate(
            require_list(run.get("incidents"), f"{path}.incidents")
        )
    )
    learnings = tuple(
        parse_learning(learning, f"{path}.learnings[{index}]")
        for index, learning in enumerate(
            require_list(run.get("learnings"), f"{path}.learnings")
        )
    )
    reject_duplicates((task.task_id for task in tasks), f"{path}.tasks", "ids")
    reject_duplicates((incident.key for incident in incidents), f"{path}.incidents", "keys")
    reject_duplicates((learning.key for learning in learnings), f"{path}.learnings", "keys")
    return RunRecord(
        run_id=require_identifier(run.get("run_id"), f"{path}.run_id"),
        change=require_identifier(run.get("change"), f"{path}.change"),
        completed_at=require_datetime(run.get("completed_at"), f"{path}.completed_at"),
        outcome=require_enum(run.get("outcome"), f"{path}.outcome", ALLOWED_OUTCOMES),
        tasks=tasks,
        incidents=incidents,
        learnings=learnings,
    )


def reject_duplicates(values: Iterable[str], context: str, noun: str) -> None:
    entries = list(values)
    if len(entries) != len(set(entries)):
        raise LearningError(f"{context} contains duplicate {noun}")


def split_evidence_ref(reference: str, context: str) -> tuple[str, str]:
    kind, separator, target = reference.partition(":")
    if not separator or not target.strip():
        raise LearningError(f"{context} has invalid evidence ref {reference!r}")
    allowed = EXTERNAL_EVIDENCE_KINDS | INTERNAL_EVIDENCE_KINDS
    if kind not in allowed:
        choices = ", ".join(sorted(allowed))
        raise LearningError(f"{context} evidence refs must use: {choices}")
    return kind, target.strip()


def validate_external_evidence_ref(repo: Path, reference: str, context: str) -> None:
    kind, target = split_evidence_ref(reference, context)
    if kind not in EXTERNAL_EVIDENCE_KINDS:
        raise LearningError(f"{context} only accepts file: or commit: evidence")
    if kind == "file":
        relative_path = Path(target)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise LearningError(f"{context} file evidence must stay inside the repository")
        repository_root = repo.resolve()
        evidence_path = (repository_root / relative_path).resolve()
        try:
            evidence_path.relative_to(repository_root)
        except ValueError as error:
            raise LearningError(
                f"{context} file evidence must stay inside the repository"
            ) from error
        if not evidence_path.is_file():
            raise LearningError(f"{context} evidence file does not exist: {target}")
        return

    if not COMMIT_PATTERN.fullmatch(target):
        raise LearningError(f"{context} commit evidence must use a full immutable SHA")
    result = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", f"{target}^{{commit}}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise LearningError(f"{context} evidence commit does not exist: {target}")


def validate_run_references(repo: Path, run: RunRecord) -> None:
    tasks = {task.task_id: task for task in run.tasks}
    incidents = {incident.key: incident for incident in run.incidents}

    for task in run.tasks:
        context = f"run {run.run_id} task {task.task_id}"
        if task.grade in {"pass", "fail"} and not task.evidence_refs:
            raise LearningError(f"{context} requires evidence_refs for grade {task.grade}")
        for reference in task.evidence_refs:
            validate_external_evidence_ref(repo, reference, context)

    for incident in run.incidents:
        context = f"run {run.run_id} incident {incident.key}"
        if incident.status in {"verified", "rejected"} and not incident.evidence_refs:
            raise LearningError(f"{context} requires evidence_refs for status {incident.status}")
        for reference in incident.evidence_refs:
            kind, target = split_evidence_ref(reference, context)
            if kind in EXTERNAL_EVIDENCE_KINDS:
                validate_external_evidence_ref(repo, reference, context)
                continue
            if kind != "task" or target not in tasks:
                raise LearningError(f"{context} references unknown task: {target}")
            if incident.status == "verified" and tasks[target].grade != "pass":
                raise LearningError(f"{context} verified evidence task must have grade pass")

    for learning in run.learnings:
        context = f"run {run.run_id} learning {learning.key}"
        for reference in learning.evidence_refs:
            kind, target = split_evidence_ref(reference, context)
            if kind in EXTERNAL_EVIDENCE_KINDS:
                validate_external_evidence_ref(repo, reference, context)
                continue
            if kind == "task":
                if target not in tasks:
                    raise LearningError(f"{context} references unknown task: {target}")
                if tasks[target].grade != "pass":
                    raise LearningError(f"{context} evidence task must have grade pass")
                continue
            if target not in incidents:
                raise LearningError(f"{context} references unknown incident: {target}")
            if incidents[target].status != "verified":
                raise LearningError(f"{context} evidence incident must be verified")


def load_runs(repo: Path) -> tuple[RunRecord, ...]:
    runs_directory = repo / RUNS_DIRECTORY
    if not runs_directory.exists():
        return ()
    run_files = sorted(runs_directory.glob("*.json"))
    runs = tuple(parse_run_file(path) for path in run_files)
    reject_duplicates((run.run_id for run in runs), str(runs_directory), "run_ids")
    for run in runs:
        validate_run_references(repo, run)
    return runs


def normalize_rule(rule: str) -> str:
    return " ".join(rule.split())


def learning_signature(
    learning: Learning,
) -> tuple[str, str, tuple[str, ...], tuple[str, ...], str | None, str | None]:
    return (
        learning.kind,
        normalize_rule(learning.rule),
        learning.scopes,
        learning.supersedes,
        learning.skill_name,
        learning.skill_description,
    )


def collect_promoted_occurrences(
    runs: Sequence[RunRecord],
) -> dict[str, tuple[LearningOccurrence, ...]]:
    occurrences_by_key: dict[str, list[LearningOccurrence]] = {}
    for run in runs:
        for learning in run.learnings:
            occurrences_by_key.setdefault(learning.key, []).append(
                LearningOccurrence(run.run_id, run.change, learning)
            )

    promoted: dict[str, tuple[LearningOccurrence, ...]] = {}
    for key, occurrences in occurrences_by_key.items():
        signatures = {learning_signature(occurrence.learning) for occurrence in occurrences}
        if len(signatures) > 1:
            raise LearningError(
                f"learning {key!r} has conflicting kind, content, scopes, or supersedes"
            )
        if (
            len({occurrence.change for occurrence in occurrences})
            >= PROMOTION_MIN_DISTINCT_CHANGES
        ):
            promoted[key] = tuple(occurrences)

    superseded_keys = {
        superseded_key
        for occurrences in promoted.values()
        for superseded_key in occurrences[0].learning.supersedes
    }
    return {
        key: occurrences
        for key, occurrences in promoted.items()
        if key not in superseded_keys
    }


def render_promoted(
    promoted: dict[str, tuple[LearningOccurrence, ...]],
    *,
    kind: str,
    heading: str,
    introduction: tuple[str, ...],
) -> str:
    lines = [
        "<!-- Generated by impl/scripts/learning.py. Do not edit by hand. -->",
        f"# {heading}",
        "",
        *introduction,
        "",
    ]
    selected = {
        key: occurrences
        for key, occurrences in promoted.items()
        if occurrences[0].learning.kind == kind
    }
    if not selected:
        lines.extend([f"No {heading.lower()}.", ""])
        return "\n".join(lines)

    for key in sorted(selected):
        occurrences = selected[key]
        learning = occurrences[0].learning
        scopes = ", ".join(f"`{scope}`" for scope in learning.scopes)
        lines.extend([f"## {key}", "", f"Scopes: {scopes}", "", learning.rule, "", "Evidence:", ""])
        for occurrence in occurrences:
            references = ", ".join(
                f"`{reference}`" for reference in occurrence.learning.evidence_refs
            )
            lines.append(
                f"- `{occurrence.run_id}` (`{occurrence.change}`): "
                f"{occurrence.learning.evidence} [{references}]"
            )
        lines.append("")
    return "\n".join(lines)


def render_active_rules(runs: Sequence[RunRecord]) -> str:
    return render_promoted(
        collect_promoted_occurrences(runs),
        kind="rule",
        heading="Active impl rules",
        introduction=(
            "> The impl harness loads these project-local rules before dispatching work.",
            "> A rule appears only after verified recurrence across distinct changes.",
        ),
    )


def render_gate_candidates(runs: Sequence[RunRecord]) -> str:
    return render_promoted(
        collect_promoted_occurrences(runs),
        kind="gate_candidate",
        heading="Impl gate candidates",
        introduction=(
            "> These recurring lessons may become tests, guards, linters, or scripts.",
            "> They require a normal reviewed OpenSpec change. This file never edits code.",
        ),
    )


def promoted_skills(
    runs: Sequence[RunRecord],
) -> dict[str, tuple[LearningOccurrence, ...]]:
    skills: dict[str, tuple[LearningOccurrence, ...]] = {}
    for occurrences in collect_promoted_occurrences(runs).values():
        learning = occurrences[0].learning
        if learning.kind != "skill" or learning.skill_name is None:
            continue
        if learning.skill_name in skills:
            raise LearningError(f"duplicate promoted skill name: {learning.skill_name}")
        skills[learning.skill_name] = occurrences
    return skills


def render_skill(learning: Learning) -> str:
    if learning.skill_name is None or learning.skill_description is None:
        raise LearningError(f"learning {learning.key!r} is missing skill metadata")
    title = " ".join(part.capitalize() for part in learning.skill_name.split("-"))
    return "\n".join(
        [
            "---",
            f"name: {learning.skill_name}",
            f"description: {json.dumps(learning.skill_description)}",
            "---",
            "<!-- Generated by impl/scripts/learning.py. Do not edit by hand. -->",
            f"# {title}",
            "",
            learning.rule,
            "",
        ]
    )


def render_skill_index(runs: Sequence[RunRecord]) -> str:
    skills = promoted_skills(runs)
    lines = [
        "<!-- Generated by impl/scripts/learning.py. Do not edit by hand. -->",
        "# Generated project skills",
        "",
        "> Each skill requires verified recurrence across distinct changes.",
        "> Review it before copying it into a discovered skill directory or publishing it.",
        "",
    ]
    if not skills:
        lines.extend(["No generated project skills.", ""])
        return "\n".join(lines)
    for skill_name, occurrences in sorted(skills.items()):
        learning = occurrences[0].learning
        lines.extend(
            [
                f"## {skill_name}",
                "",
                f"Path: `skills/{skill_name}/SKILL.md`",
                "",
                f"{learning.skill_description}",
                "",
                "Evidence:",
                "",
            ]
        )
        for occurrence in occurrences:
            references = ", ".join(
                f"`{reference}`" for reference in occurrence.learning.evidence_refs
            )
            lines.append(
                f"- `{occurrence.run_id}` (`{occurrence.change}`): "
                f"{occurrence.learning.evidence} [{references}]"
            )
        lines.append("")
    return "\n".join(lines)


def render_quality_signals(runs: Sequence[RunRecord]) -> str:
    outcomes = Counter(run.outcome for run in runs)
    grades = Counter(task.grade for run in runs for task in run.tasks)
    incident_kinds = Counter(incident.kind for run in runs for incident in run.incidents)
    incident_statuses = Counter(incident.status for run in runs for incident in run.incidents)
    lines = [
        "<!-- Generated by impl/scripts/learning.py. Do not edit by hand. -->",
        "# Impl quality and safety signals",
        "",
        "> Counts come only from validated project-local run records. PR volume is excluded.",
        "",
        "## Run outcomes",
        "",
    ]
    lines.extend(f"- {outcome}: {outcomes[outcome]}" for outcome in sorted(ALLOWED_OUTCOMES))
    lines.extend(["", "## Task evidence grades", ""])
    lines.extend(f"- {grade}: {grades[grade]}" for grade in sorted(ALLOWED_GRADES))
    lines.extend(["", "## Incident kinds", ""])
    lines.extend(f"- {kind}: {incident_kinds[kind]}" for kind in sorted(ALLOWED_INCIDENT_KINDS))
    lines.extend(["", "## Incident verification", ""])
    lines.extend(
        f"- {status}: {incident_statuses[status]}"
        for status in sorted(ALLOWED_INCIDENT_STATUSES)
    )
    lines.append("")
    return "\n".join(lines)


def generated_artifacts(runs: Sequence[RunRecord]) -> dict[Path, str]:
    artifacts = {
        ACTIVE_RULES_FILE: render_active_rules(runs),
        GATE_CANDIDATES_FILE: render_gate_candidates(runs),
        QUALITY_SIGNALS_FILE: render_quality_signals(runs),
        SKILL_INDEX_FILE: render_skill_index(runs),
    }
    for skill_name, occurrences in promoted_skills(runs).items():
        artifacts[SKILLS_DIRECTORY / skill_name / "SKILL.md"] = render_skill(
            occurrences[0].learning
        )
    return artifacts


def existing_generated_skill_files(repo: Path) -> set[Path]:
    skills_root = repo / SKILLS_DIRECTORY
    if not skills_root.exists():
        return set()
    return {
        path.relative_to(repo)
        for path in skills_root.glob("*/SKILL.md")
        if "Generated by impl/scripts/learning.py" in path.read_text(encoding="utf-8")
    }


def skill_artifact_paths(artifacts: dict[Path, str]) -> set[Path]:
    return {
        path
        for path in artifacts
        if path.parent.parent == SKILLS_DIRECTORY
    }


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as temporary_file:
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
        os.chmod(temporary_name, mode)
        os.replace(temporary_name, path)
        if hasattr(os, "O_DIRECTORY"):
            directory_descriptor = os.open(path.parent, os.O_DIRECTORY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def refresh(repo: Path) -> tuple[Path, ...]:
    artifacts = generated_artifacts(load_runs(repo))
    expected_skill_files = skill_artifact_paths(artifacts)
    for stale_path in existing_generated_skill_files(repo) - expected_skill_files:
        absolute_path = repo / stale_path
        absolute_path.unlink()
        absolute_path.parent.rmdir()
    paths: list[Path] = []
    for relative_path, content in artifacts.items():
        path = repo / relative_path
        atomic_write_text(path, content)
        paths.append(path)
    return tuple(paths)


def check(repo: Path) -> tuple[Path, ...]:
    artifacts = generated_artifacts(load_runs(repo))
    unexpected_skill_files = existing_generated_skill_files(repo) - skill_artifact_paths(
        artifacts
    )
    if unexpected_skill_files:
        unexpected = ", ".join(str(path) for path in sorted(unexpected_skill_files))
        raise LearningError(f"generated skill files are stale: {unexpected}; run refresh")
    paths: list[Path] = []
    for relative_path, expected in artifacts.items():
        path = repo / relative_path
        if not path.exists():
            raise LearningError(f"{path} is missing; run refresh")
        if path.read_text(encoding="utf-8") != expected:
            raise LearningError(f"{path} is stale; run refresh")
        paths.append(path)
    return tuple(paths)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compile verified impl lessons into project-local artifacts."
    )
    parser.add_argument("command", choices=("refresh", "check"))
    add_runtime_arguments(parser)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        repo = runtime_from_arguments(arguments).project_directory
        paths = refresh(repo) if arguments.command == "refresh" else check(repo)
        for path in paths:
            print(path)
    except (LearningError, OSError, RuntimeConfigError) as error:
        print(f"learning: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
