#!/usr/bin/env python3
"""Repository-first adaptive process intake with no graph side effects."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from validation import CliValidationError, direct_command_arguments, validate_process_decision


PROCESS_MODES = frozenset({"direct", "verified_single", "light_spec", "graph"})
OBSERVATION_VALUES = {
    "cohesion": frozenset({"cohesive", "mixed", "independent"}),
    "architecture_uncertainty": frozenset({"known", "material"}),
    "reversibility": frozenset({"reversible", "costly", "irreversible"}),
    "blast_radius": frozenset({"local", "multi_surface", "external"}),
    "oracle_strength": frozenset({"strong", "weak", "absent"}),
    "context_pressure": frozenset({"low", "medium", "high"}),
    "external_effects": frozenset({"none", "reversible", "irreversible"}),
}
DECISION_EFFECTS = frozenset({"behavior", "scope", "risk", "acceptance", "mode"})
INSTRUCTION_FILES = ("AGENTS.md", "CLAUDE.md", "README.md", "CONTRIBUTING.md")
READ_LIMIT_BYTES = 262_144


def _read_bounded(path: Path) -> str:
    try:
        with path.open("rb") as stream:
            return stream.read(READ_LIMIT_BYTES).decode("utf-8", errors="replace")
    except OSError:
        return ""


def inspect_repository(repository: Path) -> dict[str, Any]:
    """Return bounded facts established from repository-owned files."""

    root = repository.resolve()
    instructions: list[str] = []
    compatibility: dict[str, str] | None = None
    for name in INSTRUCTION_FILES:
        path = root / name
        if not path.is_file():
            continue
        instructions.append(name)
        text = _read_bounded(path).casefold()
        if compatibility is None and (
            "breaking changes are allowed" in text
            or "prefer a clean breaking change" in text
        ):
            compatibility = {"value": "not_required", "evidence_ref": f"file:{name}"}
        if (
            "backward compatibility is required" in text
            or "backwards compatibility is required" in text
        ):
            compatibility = {"value": "required", "evidence_ref": f"file:{name}"}

    return {
        "canonical_root": str(root),
        "git_repository": (root / ".git").exists(),
        "openspec_available": (root / "openspec" / "changes").is_dir(),
        "instruction_files": instructions,
        "compatibility": compatibility,
    }


def _enum_signal(signals: Mapping[str, Any], name: str, default: str) -> str:
    value = signals.get(name, default)
    if value not in OBSERVATION_VALUES[name]:
        choices = ", ".join(sorted(OBSERVATION_VALUES[name]))
        raise CliValidationError(f"adaptive intake {name} must be one of: {choices}")
    return str(value)


def _boolean_signal(signals: Mapping[str, Any], name: str, default: bool) -> bool:
    value = signals.get(name, default)
    if not isinstance(value, bool):
        raise CliValidationError(f"adaptive intake {name} must be boolean")
    return value


def _repository_paths(value: Any, context: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise CliValidationError(f"{context} must be a non-empty list of repository paths")
    return list(dict.fromkeys(value))


def _normalized_packets(value: Any) -> tuple[list[dict[str, Any]], list[str]]:
    if value is None:
        return [], []
    if not isinstance(value, list):
        raise CliValidationError("adaptive intake independent_packets must be a list")
    packets: list[dict[str, Any]] = []
    blockers: list[str] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, Mapping):
            blockers.append(f"packet {index} is not an object")
            continue
        packet_id = item.get("packet_id")
        paths = item.get("paths")
        selected_check = item.get("check")
        if not isinstance(packet_id, str) or not packet_id:
            blockers.append(f"packet {index} has no stable identity")
            continue
        try:
            normalized_paths = _repository_paths(paths, f"packet {packet_id} paths")
        except CliValidationError as error:
            blockers.append(str(error))
            continue
        if not isinstance(selected_check, Mapping):
            blockers.append(f"packet {packet_id} has no individual check")
            continue
        command = selected_check.get("command")
        oracle = selected_check.get("oracle")
        if not isinstance(command, str) or not isinstance(oracle, str) or not command or not oracle:
            blockers.append(f"packet {packet_id} has no individual check")
            continue
        direct_command_arguments(command)
        packets.append(
            {
                "packet_id": packet_id,
                "paths": normalized_paths,
                "check": {"command": command, "oracle": oracle},
            }
        )
    return packets, blockers


def _integration_check(value: Any, fallback: Mapping[str, str]) -> dict[str, str]:
    """Normalize the graph-wide integration oracle independently of packets."""

    candidate = fallback if value is None else value
    if not isinstance(candidate, Mapping):
        raise CliValidationError("adaptive intake integration_check must be an object")
    command = candidate.get("command")
    oracle = candidate.get("oracle")
    if not isinstance(command, str) or not command or not isinstance(oracle, str) or not oracle:
        raise CliValidationError("adaptive intake integration_check requires command and oracle")
    direct_command_arguments(command)
    return {"command": command, "oracle": oracle}


def _paths_overlap(left: str, right: str) -> bool:
    left_path = left.rstrip("/")
    right_path = right.rstrip("/")
    return (
        left_path == right_path
        or left_path.startswith(right_path + "/")
        or right_path.startswith(left_path + "/")
    )


def _ownership_blockers(packets: Sequence[Mapping[str, Any]]) -> list[str]:
    blockers: list[str] = []
    for index, left in enumerate(packets):
        for right in packets[index + 1 :]:
            if any(
                _paths_overlap(left_path, right_path)
                for left_path in left["paths"]
                for right_path in right["paths"]
            ):
                blockers.append(
                    f"packets {left['packet_id']} and {right['packet_id']} have shared-write ownership"
                )
    return blockers


def _material_questions(
    ambiguities: Any,
    facts: Mapping[str, Any],
    *,
    use_safe_defaults: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if ambiguities is None:
        return [], [], []
    if not isinstance(ambiguities, list):
        raise CliValidationError("adaptive intake ambiguities must be a list")
    answered: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    assumptions: list[dict[str, Any]] = []
    for index, ambiguity in enumerate(ambiguities, start=1):
        if not isinstance(ambiguity, Mapping):
            raise CliValidationError(f"adaptive intake ambiguity {index} must be an object")
        question_id = ambiguity.get("question_id")
        question = ambiguity.get("question")
        effects = ambiguity.get("decision_effects")
        fact_name = ambiguity.get("repository_fact")
        if (
            not isinstance(question_id, str)
            or not question_id
            or not isinstance(question, str)
            or not question
            or not isinstance(effects, list)
            or not effects
            or not set(effects) <= DECISION_EFFECTS
        ):
            raise CliValidationError(f"adaptive intake ambiguity {index} is not decision-changing")
        repository_fact = facts.get(fact_name) if isinstance(fact_name, str) else None
        if isinstance(repository_fact, Mapping) and repository_fact.get("value") is not None:
            assumptions.append(
                {
                    "assumption_id": f"repository-{question_id}",
                    "statement": f"Repository fact {fact_name} is {repository_fact['value']}.",
                    "basis": "repository",
                    "evidence_ref": repository_fact.get("evidence_ref", "repository:inspection"),
                }
            )
            continue
        answer = ambiguity.get("answer")
        provenance = "owner"
        safe_default_selected = False
        if answer is None and use_safe_defaults:
            answer = ambiguity.get("safe_default")
            provenance = "safe_default"
            safe_default_selected = True
        if isinstance(answer, str) and answer:
            answered.append(
                {
                    "question_id": question_id,
                    "question": question,
                    "answer": answer,
                    "decision_effects": list(dict.fromkeys(effects)),
                    "provenance": provenance,
                    "safe_default_selected": safe_default_selected,
                }
            )
        else:
            pending.append(
                {
                    "question_id": question_id,
                    "question": question,
                    "decision_effects": list(dict.fromkeys(effects)),
                    "safe_default": ambiguity.get("safe_default"),
                }
            )
    return answered, pending, assumptions


def _select_mode(
    signals: Mapping[str, Any],
    observations: Mapping[str, Any],
    packets: Sequence[Mapping[str, Any]],
    packet_blockers: Sequence[str],
    budget_limits: Sequence[Mapping[str, Any]],
) -> tuple[str, list[str]]:
    graph_requested = _boolean_signal(signals, "graph_requested", False)
    blockers = list(packet_blockers)
    if graph_requested:
        if len(packets) < 2:
            blockers.append("graph mode requires at least two independently useful packets")
        blockers.extend(_ownership_blockers(packets))
        if observations["shared_write_coupling"]:
            blockers.append("graph mode cannot dispatch shared-write coupled work")
        integrator = signals.get("integrator")
        if not isinstance(integrator, str) or not integrator:
            blockers.append("graph mode requires a declared integration owner")
        if not budget_limits:
            blockers.append("graph mode requires a task-local budget")
        cleanup_plan = signals.get("cleanup_plan")
        if not isinstance(cleanup_plan, str) or not cleanup_plan:
            blockers.append("graph mode requires a lifecycle cleanup plan")
        if not _boolean_signal(signals, "permission_observed", False):
            blockers.append("graph mode requires observed permission for its declared scope")
        if not blockers:
            return "graph", []
        return "light_spec", list(dict.fromkeys(blockers))

    if (
        observations["architecture_uncertainty"] == "material"
        or observations["reversibility"] == "irreversible"
        or observations["blast_radius"] in {"multi_surface", "external"}
        or observations["oracle_strength"] in {"weak", "absent"}
        or observations["external_effects"] == "irreversible"
        or not _boolean_signal(signals, "known_scope", False)
    ):
        return "light_spec", []
    if (
        _boolean_signal(signals, "needs_iteration", False)
        or observations["context_pressure"] in {"medium", "high"}
        or observations["cohesion"] != "cohesive"
        or not _boolean_signal(signals, "small_change", False)
    ):
        return "verified_single", []
    return "direct", []


def decide_process(
    repository: Path,
    *,
    request: str,
    check_command: str,
    signals: Mapping[str, Any] | None = None,
    use_safe_defaults: bool = False,
) -> dict[str, Any]:
    """Inspect repository facts, ask only material questions, then select one mode."""

    if not isinstance(request, str) or not request.strip():
        raise CliValidationError("adaptive intake request must be non-empty")
    direct_command_arguments(check_command)
    selected_signals = dict(signals or {})
    facts = inspect_repository(repository)
    answered, pending, fact_assumptions = _material_questions(
        selected_signals.get("ambiguities"), facts, use_safe_defaults=use_safe_defaults
    )
    if pending:
        return {
            "operation": "adaptive_intake",
            "status": "questions",
            "repository_facts": facts,
            "questions": pending,
            "decision": None,
            "graph_artifacts_created": False,
        }

    selected_check = {
        "command": check_command,
        "oracle": str(
            selected_signals.get(
                "oracle", "The task-local acceptance command exits successfully."
            )
        ),
    }
    integration_check = _integration_check(selected_signals.get("integration_check"), selected_check)
    packets, packet_blockers = _normalized_packets(
        selected_signals.get("independent_packets")
    )
    observations = {
        "cohesion": _enum_signal(selected_signals, "cohesion", "cohesive"),
        "architecture_uncertainty": _enum_signal(
            selected_signals, "architecture_uncertainty", "known"
        ),
        "reversibility": _enum_signal(selected_signals, "reversibility", "reversible"),
        "blast_radius": _enum_signal(selected_signals, "blast_radius", "local"),
        "oracle_strength": _enum_signal(selected_signals, "oracle_strength", "strong"),
        "independent_packets": packets,
        "shared_write_coupling": _boolean_signal(
            selected_signals, "shared_write_coupling", False
        ),
        "context_pressure": _enum_signal(selected_signals, "context_pressure", "low"),
        "external_effects": _enum_signal(selected_signals, "external_effects", "none"),
        "unattended_execution": _boolean_signal(
            selected_signals, "unattended_execution", False
        ),
    }
    budget_limits = selected_signals.get("budget_limits", [])
    if not isinstance(budget_limits, list):
        raise CliValidationError("adaptive intake budget_limits must be a list")
    mode, graph_blockers = _select_mode(
        selected_signals, observations, packets, packet_blockers, budget_limits
    )
    request_digest = hashlib.sha256(request.strip().encode("utf-8")).hexdigest()
    scope = _repository_paths(
        selected_signals.get("repository_scope", ["."]), "adaptive intake repository_scope"
    )
    assumptions = [*fact_assumptions]
    declared_assumptions = selected_signals.get("assumptions", [])
    if not isinstance(declared_assumptions, list):
        raise CliValidationError("adaptive intake assumptions must be a list")
    assumptions.extend(declared_assumptions)
    stop_conditions = selected_signals.get(
        "stop_conditions",
        ["The selected check passes.", "No new verifiable hypothesis remains."],
    )
    decision = validate_process_decision(
        {
            "schema_version": 1,
            "decision_id": f"decision-{request_digest[:16]}",
            "request_digest": f"sha256:{request_digest}",
            "repository_scope": scope,
            "initial_mode": mode,
            "mode": mode,
            "revision": 1,
            "observations": observations,
            "assumptions": assumptions,
            "material_questions": answered,
            "selected_check": selected_check,
            "budget": {
                "policy": "task_local",
                "limits": budget_limits,
                "stop_conditions": stop_conditions,
            },
            "triggers": {
                "escalate": selected_signals.get(
                    "escalation_triggers",
                    ["New evidence changes scope, risk, acceptance, or independent ownership."],
                ),
                "deescalate": selected_signals.get(
                    "deescalation_triggers",
                    ["Evidence proves the work is cohesive and one writer preserves context."],
                ),
                "stop": stop_conditions,
            },
            "amendments": [],
        }
    )
    graph_contract = (
        {
            "decision_revision": decision["revision"],
            "packets": packets,
            "integrator": selected_signals["integrator"],
            "cleanup_plan": selected_signals["cleanup_plan"],
            "permission_observed": selected_signals["permission_observed"],
            "integration_check": integration_check,
        }
        if mode == "graph"
        else None
    )
    return {
        "operation": "adaptive_intake",
        "status": "selected",
        "repository_facts": facts,
        "questions": [],
        "decision": decision,
        "graph_contract": graph_contract,
        "graph_blockers": graph_blockers,
        "graph_artifacts_created": False,
    }


def amend_process_decision(
    decision: Mapping[str, Any],
    *,
    amendment_id: str,
    changed_evidence: Sequence[str],
    reason: str,
    mode: str,
    replacement_check: Mapping[str, str],
) -> dict[str, Any]:
    """Append one evidence-backed amendment without mutating the prior decision."""

    current = validate_process_decision(decision)
    if mode not in PROCESS_MODES:
        raise CliValidationError("process amendment mode is invalid")
    if not changed_evidence or not all(
        isinstance(item, str) and item for item in changed_evidence
    ):
        raise CliValidationError("process amendment requires changed evidence")
    if not isinstance(reason, str) or not reason:
        raise CliValidationError("process amendment requires a reason")
    command = replacement_check.get("command")
    oracle = replacement_check.get("oracle")
    if not isinstance(command, str) or not isinstance(oracle, str) or not command or not oracle:
        raise CliValidationError("process amendment requires a replacement check")
    direct_command_arguments(command)
    amended = json.loads(json.dumps(current))
    next_revision = current["revision"] + 1
    amended["mode"] = mode
    amended["revision"] = next_revision
    amended["selected_check"] = {"command": command, "oracle": oracle}
    amended["amendments"].append(
        {
            "amendment_id": amendment_id,
            "from_revision": current["revision"],
            "to_revision": next_revision,
            "from_mode": current["mode"],
            "to_mode": mode,
            "changed_evidence": list(changed_evidence),
            "reason": reason,
            "replacement_check": amended["selected_check"],
        }
    )
    return validate_process_decision(amended)


def evaluate_stop_conditions(
    decision: Mapping[str, Any],
    *,
    permission_observed: bool,
    usage: Mapping[str, float] | None = None,
) -> list[str]:
    """Return observable reasons that forbid more autonomous work."""

    current = validate_process_decision(decision)
    reasons: list[str] = []
    if not permission_observed:
        reasons.append("missing_permission")
    observations = current["observations"]
    if observations["oracle_strength"] in {"weak", "absent"} and (
        observations["blast_radius"] != "local"
        or observations["external_effects"] != "none"
    ):
        reasons.append("insufficient_oracle_for_blast_radius")
    measured = dict(usage or {})
    for limit in current["budget"]["limits"]:
        value = measured.get(limit["resource"])
        if isinstance(value, (int, float)) and value >= limit["value"]:
            reasons.append(f"budget_exhausted:{limit['resource']}")
    return reasons


def authorize_external_retry(
    decision: Mapping[str, Any], *, postcondition_observed: bool
) -> tuple[bool, str | None]:
    """Require a post-condition observation before repeating an external effect."""

    current = validate_process_decision(decision)
    if current["observations"]["external_effects"] == "none":
        return True, None
    if not postcondition_observed:
        return False, "external retry requires post-condition observation"
    return True, None


def validate_graph_transition(
    payload: Mapping[str, Any], tasks: Sequence[Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate one current decision and its explicit graph packet contracts."""

    raw_decision = payload.get("decision", payload)
    decision = validate_process_decision(raw_decision)
    if decision["mode"] != "graph":
        raise CliValidationError("durable graph bootstrap requires a graph-mode decision")
    contract = payload.get("graph_contract")
    if not isinstance(contract, Mapping):
        raise CliValidationError("durable graph bootstrap requires an explicit graph contract")
    if contract.get("decision_revision") != decision["revision"]:
        raise CliValidationError("graph contract references a stale process decision")
    if contract.get("permission_observed") is not True:
        raise CliValidationError("graph contract lacks observed permission")
    for field in ("integrator", "cleanup_plan"):
        if not isinstance(contract.get(field), str) or not contract[field]:
            raise CliValidationError(f"graph contract requires {field}")
    if not decision["budget"]["limits"]:
        raise CliValidationError("graph contract requires a task-local budget")
    packets = contract.get("packets")
    if packets != decision["observations"]["independent_packets"] or len(packets or []) < 2:
        raise CliValidationError("graph contract packets do not match the current decision")
    if decision["observations"]["shared_write_coupling"]:
        raise CliValidationError("graph contract has shared-write coupling")

    task_by_id: dict[str, Any] = {}
    for task in tasks:
        task_id = getattr(task, "id", None) or task.get("id")
        task_by_id[str(task_id)] = task
    for packet in packets:
        task = task_by_id.get(packet["packet_id"])
        if task is None:
            raise CliValidationError(f"graph packet has no task: {packet['packet_id']}")
        task_paths = list(getattr(task, "paths", None) or task.get("paths", []))
        task_check = getattr(task, "check", None) or task.get("check")
        if packet["paths"] != task_paths or packet["check"]["command"] != task_check:
            raise CliValidationError(
                f"graph packet contract diverges from task: {packet['packet_id']}"
            )
    return decision, json.loads(json.dumps(dict(contract)))


def load_signals(value: str | None, path: Path | None = None) -> dict[str, Any]:
    if value is not None and path is not None:
        raise CliValidationError("use only one adaptive intake signals source")
    try:
        payload = json.loads(value) if value is not None else json.loads(path.read_text(encoding="utf-8")) if path else {}
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CliValidationError(f"cannot read adaptive intake signals: {error}") from error
    if not isinstance(payload, dict):
        raise CliValidationError("adaptive intake signals must contain one JSON object")
    return payload
