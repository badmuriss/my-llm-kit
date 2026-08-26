import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


SCRIPT = Path(__file__).parents[1] / "scripts" / "graph_core.py"
REFERENCES = Path(__file__).parents[1] / "references"
FIXTURES = Path(__file__).parents[1] / "fixtures" / "maestro-protocol-v1"
SPEC = importlib.util.spec_from_file_location("graph_core", SCRIPT)
assert SPEC and SPEC.loader
graph_core = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = graph_core
SPEC.loader.exec_module(graph_core)

from adaptive_intake import (  # noqa: E402
    amend_process_decision,
    authorize_external_retry,
    decide_process,
    evaluate_stop_conditions,
    validate_graph_transition,
)
import validation  # noqa: E402


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


WORKSPACE_SCOPES = load_json(FIXTURES / "workspace-scopes.json")
WORKSPACE_RECEIPTS = load_json(FIXTURES / "workspace-bootstrap-receipts.json")
EXECUTION_PROFILES = load_json(FIXTURES / "execution-profiles.json")
OPAQUE_WORKSPACE_KEY = "folder:folder-local-01"
CONTROL_RUNTIME = {
    "schema_version": 1,
    "entrypoint": "/tmp/control/scripts/agent_graph.py",
    "directory": "/tmp/control",
    "directory_digest": "sha256:" + "a" * 64,
    "protocol_version": 1,
    "source_revision": "0123456789abcdef0123456789abcdef01234567",
    "creation_receipt": {
        "method": "atomic-directory-rename",
        "created_at": "2026-08-20T12:00:00Z",
        "file_count": 8,
        "byte_count": 1024,
    },
}


def workspace_scope(*, run_id: str = "run-1", generation: int = 1) -> dict:
    scope = copy.deepcopy(WORKSPACE_SCOPES["folder_local"])
    scope["run_id"] = run_id
    scope["coordinator_generation"] = generation
    return scope


def cleanup_owner(attempt_id: str = "attempt-01") -> dict:
    return {
        "execution_host_id": "host-local",
        "workspace_key": OPAQUE_WORKSPACE_KEY,
        "attempt_id": attempt_id,
        "terminal_id": "terminal-01",
        "incarnation_id": "pty-9",
        "process_root": 4242,
        "provenance": "driver-start-receipt",
    }


def attempt_data(attempt_id: str = "attempt-01") -> dict:
    return {
        "task_id": "ROOT-01",
        "attempt_id": attempt_id,
        "driver": "host",
        "workspace_scope": workspace_scope(),
        "execution_profile": copy.deepcopy(EXECUTION_PROFILES["current_folder"]),
    }


VALID_TASKS = """# Tasks

- [ ] ROOT-01 Build the domain
  Depends: []
  Paths: [src/domain/, tests/test_domain.py]
  Mode: write
  Isolation: auto
  Context: Keep the implementation bounded.
  Acceptance: The domain behavior is available.
  Check: python3 -m unittest tests.test_domain

- [ ] API-02 Expose the domain
  Depends: [ROOT-01]
  Paths: [src/api/]
  Mode: write
  Isolation: worktree
  Acceptance: The API exposes the domain behavior.
  Check: python3 -m unittest tests.test_api
"""


def graph_intake(*, shared_write_coupling: bool = False, packet_count: int = 2) -> dict:
    check_domain = {
        "command": "python3 -m unittest tests.test_domain",
        "oracle": "The domain check passes.",
    }
    check_api = {
        "command": "python3 -m unittest tests.test_api",
        "oracle": "The API check passes.",
    }
    return decide_process(
        Path.cwd(),
        request="Implement the two bounded graph packets.",
        check_command=check_domain["command"],
        signals={
            "known_scope": True,
            "graph_requested": True,
            "cohesion": "independent",
            "independent_packets": [
                {
                    "packet_id": "ROOT-01",
                    "paths": ["src/domain/", "tests/test_domain.py"],
                    "check": check_domain,
                },
                {
                    "packet_id": "API-02",
                    "paths": ["src/api/"],
                    "check": check_api,
                },
            ][:packet_count],
            "shared_write_coupling": shared_write_coupling,
            "integrator": "coordinator-1",
            "permission_observed": True,
            "budget_limits": [
                {
                    "resource": "workers",
                    "value": 2,
                    "unit": "workers",
                    "rationale": "The graph contains two declared packets.",
                }
            ],
            "cleanup_plan": "Verify or retain every owned resource before reduction.",
        },
    )


class GraphParsingBehavior(unittest.TestCase):
    def test_scopes_amendments_to_their_exact_parent_attempt(self) -> None:
        task = graph_core.parse_task_graph(VALID_TASKS).tasks[0]
        projection = {
            "graph_amendments": {
                "amend-own": {
                    "parent_task_id": "ROOT-01",
                    "parent_attempt_id": "attempt-own",
                    "paths": ["src/own.py"],
                },
                "amend-sibling": {
                    "parent_task_id": "ROOT-01",
                    "parent_attempt_id": "attempt-sibling",
                    "paths": ["src/sibling.py"],
                },
            }
        }

        scope = graph_core.effective_attempt_scope(task, "attempt-own", projection)

        self.assertEqual(scope["paths"], ["src/domain/", "tests/test_domain.py", "src/own.py"])
        self.assertEqual(scope["amendment_ids"], ["amend-own"])

    def test_approves_child_paths_from_the_parent_effective_amendment_union(self) -> None:
        task = graph_core.parse_task_graph(VALID_TASKS).tasks[0]
        state = graph_core.empty_projection()
        state["status"] = "active"
        state["workspace_scope"] = workspace_scope()
        state["tasks"][task.id] = {
            "contract": task.to_dict(),
            "status": "running",
            "grade": None,
            "attempt_ids": ["attempt-parent"],
        }
        state["attempts"]["attempt-parent"] = {
            "task_id": task.id,
            "status": "running",
            "scope_frozen": True,
        }
        state["graph_amendments"] = {
            "amend-first": {
                "parent_task_id": task.id,
                "parent_attempt_id": "attempt-parent",
                "paths": ["src/first.py"],
            },
            "amend-second": {
                "parent_task_id": task.id,
                "parent_attempt_id": "attempt-parent",
                "paths": ["src/second.py"],
            },
        }
        state["delegations"]["delegation-child"] = {
            "delegation_id": "delegation-child",
            "parent_task_id": task.id,
            "parent_attempt_id": "attempt-parent",
            "intent": {"paths": ["src/first.py"], "context_refs": ["context-parent"]},
            "status": "requested",
        }

        with mock.patch.object(
            graph_core,
            "validate_execution_profile",
            return_value={"profile": "validated"},
        ):
            approved = graph_core.apply_event(
                state,
                {
                    "sequence": 1,
                    "type": "delegation_approved",
                    "data": {
                        "delegation_id": "delegation-child",
                        "paths": ["src/first.py"],
                        "context_refs": ["context-parent"],
                        "context_revision": "context-revision-1",
                        "execution_profile": {"ignored": "by this focused boundary test"},
                        "amendment_id": "amend-second",
                    },
                },
            )

        self.assertEqual(
            approved["delegations"]["delegation-child"]["paths"], ["src/first.py"]
        )

    def test_parses_the_complete_task_contract(self) -> None:
        graph = graph_core.parse_task_graph(VALID_TASKS)

        self.assertEqual([task.id for task in graph.tasks], ["ROOT-01", "API-02"])
        self.assertEqual(graph.tasks[0].paths, ("src/domain/", "tests/test_domain.py"))
        self.assertEqual(graph.tasks[1].depends, ("ROOT-01",))
        self.assertEqual(graph.tasks[1].isolation, "worktree")

    def test_rejects_missing_and_duplicate_fields(self) -> None:
        missing = VALID_TASKS.replace("  Mode: write\n", "", 1)
        duplicate = VALID_TASKS.replace(
            "  Mode: write\n", "  Mode: write\n  Mode: read\n", 1
        )

        with self.assertRaisesRegex(graph_core.GraphValidationError, "missing fields: mode"):
            graph_core.parse_task_graph(missing)
        with self.assertRaisesRegex(graph_core.GraphValidationError, "duplicate field mode"):
            graph_core.parse_task_graph(duplicate)

    def test_rejects_unsafe_paths(self) -> None:
        unsafe_paths = ["/tmp/file", "../secret", "src/**", "src\\file.py", "src//file.py"]

        for unsafe_path in unsafe_paths:
            with self.subTest(path=unsafe_path):
                source = VALID_TASKS.replace("src/domain/", unsafe_path, 1)
                with self.assertRaises(graph_core.GraphValidationError):
                    graph_core.parse_task_graph(source)

    def test_rejects_unknown_self_and_cyclic_dependencies(self) -> None:
        unknown = VALID_TASKS.replace("Depends: []", "Depends: [MISSING-99]", 1)
        self_dependency = VALID_TASKS.replace("Depends: []", "Depends: [ROOT-01]", 1)
        cycle = VALID_TASKS.replace("Depends: []", "Depends: [API-02]", 1)

        with self.assertRaisesRegex(graph_core.GraphValidationError, "unknown dependencies"):
            graph_core.parse_task_graph(unknown)
        with self.assertRaisesRegex(graph_core.GraphValidationError, "depend on itself"):
            graph_core.parse_task_graph(self_dependency)
        with self.assertRaisesRegex(graph_core.GraphValidationError, "dependency cycle"):
            graph_core.parse_task_graph(cycle)

    def test_rejects_duplicate_task_ids(self) -> None:
        duplicate = VALID_TASKS.replace("API-02 Expose", "ROOT-01 Expose")

        with self.assertRaisesRegex(graph_core.GraphValidationError, "duplicate task ID"):
            graph_core.parse_task_graph(duplicate)

    def test_parses_checked_tasks_structurally_without_grading_them(self) -> None:
        checked = VALID_TASKS.replace("- [ ] ROOT-01", "- [x] ROOT-01")

        parsed = graph_core.parse_task_graph(checked)

        self.assertTrue(parsed.tasks[0].checked)


class SchedulerBehavior(unittest.TestCase):
    def test_requires_passing_dependency_grades(self) -> None:
        graph = graph_core.parse_task_graph(VALID_TASKS)
        projection = {
            "tasks": {
                "ROOT-01": {"grade": None, "status": "pending"},
                "API-02": {"grade": None, "status": "pending"},
            }
        }

        self.assertEqual([task.id for task in graph_core.ready_tasks(graph, projection)], ["ROOT-01"])
        projection["tasks"]["ROOT-01"]["status"] = "reported"
        self.assertEqual([task.id for task in graph_core.ready_tasks(graph, projection)], [])
        projection["tasks"]["ROOT-01"].update(status="pass", grade="pass")
        self.assertEqual([task.id for task in graph_core.ready_tasks(graph, projection)], ["API-02"])

    def test_serializes_overlapping_write_prefixes(self) -> None:
        graph = graph_core.parse_task_graph(
            VALID_TASKS.replace("Depends: [ROOT-01]", "Depends: []").replace(
                "Paths: [src/api/]", "Paths: [src/domain/models.py]"
            )
        )
        projection = {"tasks": {task.id: {"grade": None, "status": "pending"} for task in graph.tasks}}

        ready = graph_core.ready_tasks(graph, projection)

        self.assertEqual([task.id for task in ready], ["ROOT-01"])
        self.assertTrue(graph_core.path_scopes_overlap("src/domain/", "src/domain/models.py"))
        self.assertFalse(graph_core.path_scopes_overlap("src/domain.py", "src/domain/models.py"))

    def test_allows_nonconflicting_write_and_read_tasks(self) -> None:
        source = VALID_TASKS.replace("Depends: [ROOT-01]", "Depends: []")
        graph = graph_core.parse_task_graph(source)
        projection = {"tasks": {task.id: {"grade": None, "status": "pending"} for task in graph.tasks}}

        self.assertEqual(
            [task.id for task in graph_core.ready_tasks(graph, projection)],
            ["ROOT-01", "API-02"],
        )

    def test_blocks_every_owned_or_missing_attempt_cleanup_until_terminal(self) -> None:
        graph = graph_core.parse_task_graph(VALID_TASKS)
        projection = {
            "tasks": {
                "ROOT-01": {
                    "grade": None,
                    "status": "pending",
                    "attempt_ids": ["attempt-01"],
                },
                "API-02": {"grade": None, "status": "pending", "attempt_ids": []},
            },
            "attempts": {
                "attempt-01": {
                    "task_id": "ROOT-01",
                    "status": "audit-rejected",
                    "cleanup_id": "cleanup-missing",
                }
            },
            "cleanup": {
                "cleanup-owner-string": {"owner": "attempt-01", "status": "pending"},
                "cleanup-owner-object": {
                    "owner": {"attempt_id": "attempt-01"},
                    "status": "failed",
                },
                "cleanup-attempt-field": {
                    "attempt_id": "attempt-01",
                    "owner": "coordinator-1",
                    "status": "unverifiable",
                },
                "cleanup-terminal": {"owner": "attempt-01", "status": "retained"},
            },
        }

        self.assertEqual(
            graph_core.pending_cleanup_ids_for_task(projection, "ROOT-01"),
            [
                "cleanup-attempt-field",
                "cleanup-missing",
                "cleanup-owner-object",
                "cleanup-owner-string",
            ],
        )
        self.assertEqual(graph_core.ready_tasks(graph, projection), [])


class AdaptiveTransitionBehavior(unittest.TestCase):
    def test_promotes_only_after_an_emerging_independent_packet_has_its_own_contract(self) -> None:
        incomplete = graph_intake(packet_count=1)
        selected = graph_intake()

        self.assertEqual(incomplete["decision"]["mode"], "light_spec")
        self.assertTrue(
            any("two independently useful" in item for item in incomplete["graph_blockers"])
        )
        self.assertEqual(selected["decision"]["mode"], "graph")
        self.assertEqual(len(selected["graph_contract"]["packets"]), 2)
        self.assertEqual(
            selected["graph_contract"]["packets"][1]["paths"], ["src/api/"]
        )

    def test_prevents_dispatch_when_new_evidence_reveals_shared_write_coupling(self) -> None:
        result = graph_intake(shared_write_coupling=True)

        self.assertEqual(result["decision"]["mode"], "light_spec")
        self.assertIsNone(result["graph_contract"])
        self.assertTrue(any("shared-write" in item for item in result["graph_blockers"]))

    def test_rejects_a_stale_graph_contract_after_material_amendment(self) -> None:
        graph = graph_core.parse_task_graph(VALID_TASKS)
        selected = graph_intake()
        amended = amend_process_decision(
            selected["decision"],
            amendment_id="amendment-oracle",
            changed_evidence=["The acceptance oracle now covers the public interface."],
            reason="The material evidence changed the acceptance boundary.",
            mode="graph",
            replacement_check={
                "command": "python3 -m unittest tests.test_domain",
                "oracle": "The amended domain check passes.",
            },
        )
        stale = {"decision": amended, "graph_contract": selected["graph_contract"]}

        with self.assertRaisesRegex(Exception, "stale process decision"):
            validate_graph_transition(stale, graph.tasks)

    def test_preserves_pending_tasks_accepted_evidence_and_cleanup_during_graph_reduction(self) -> None:
        graph = graph_core.parse_task_graph(VALID_TASKS)
        selected = graph_intake()
        state = graph_core.apply_event(
            graph_core.empty_projection(),
            {
                "type": "run_started",
                "sequence": 1,
                "data": {
                    "change": "adaptive",
                    "run_id": "run-1",
                    "coordinator_id": "coordinator-1",
                    "coordinator_generation": 1,
                    "process_decision": selected["decision"],
                    "graph_contract": selected["graph_contract"],
                    "tasks": [task.to_dict() for task in graph.tasks],
                },
            },
        )
        accepted = state["tasks"]["ROOT-01"]
        accepted.update(
            {
                "status": "pass",
                "grade": "pass",
                "evidence_refs": ["file:artifacts/root-check.json"],
                "note": "Accepted root evidence.",
            }
        )
        amended = amend_process_decision(
            selected["decision"],
            amendment_id="amendment-coupling",
            changed_evidence=["The remaining writes share one integration boundary."],
            reason="One writer now preserves the coupled decision context.",
            mode="verified_single",
            replacement_check={
                "command": "python3 -m unittest tests.test_api",
                "oracle": "The integrated API check passes.",
            },
        )
        reduced = graph_core.apply_event(
            state,
            {
                "type": "process_decision_amended",
                "sequence": 2,
                "data": {
                    "decision": amended,
                    "graph_contract": None,
                    "reduction": {
                        "integrator": "coordinator-1",
                        "reason": "The remaining work is coupled.",
                        "cleanup_plan": "No owned resource remains unresolved.",
                        "retained_task_ids": ["ROOT-01"],
                    },
                },
            },
        )

        self.assertEqual(reduced["tasks"]["ROOT-01"]["grade"], "pass")
        self.assertEqual(
            reduced["tasks"]["ROOT-01"]["evidence_refs"],
            ["file:artifacts/root-check.json"],
        )
        self.assertEqual(reduced["tasks"]["API-02"]["status"], "pending")
        self.assertEqual(graph_core.unresolved_cleanup_ids(reduced), [])
        self.assertEqual(reduced["reduction"]["integrator"], "coordinator-1")
        self.assertEqual(graph_core.ready_tasks(graph, reduced), [])
        self.assertFalse(
            graph_core.task_is_dispatchable(graph, reduced, graph.tasks[1])
        )

    def test_stops_on_missing_permission_weak_oracle_and_exhausted_task_budget(self) -> None:
        result = decide_process(
            Path.cwd(),
            request="Change the external interface.",
            check_command="python3 -m unittest tests.test_api",
            signals={
                "known_scope": True,
                "architecture_uncertainty": "material",
                "blast_radius": "external",
                "oracle_strength": "weak",
                "budget_limits": [
                    {
                        "resource": "attempts",
                        "value": 2,
                        "unit": "attempts",
                        "rationale": "Only two distinct hypotheses have useful checks.",
                    }
                ],
            },
        )

        reasons = evaluate_stop_conditions(
            result["decision"], permission_observed=False, usage={"attempts": 2}
        )

        self.assertEqual(
            reasons,
            [
                "missing_permission",
                "insufficient_oracle_for_blast_radius",
                "budget_exhausted:attempts",
            ],
        )

    def test_requires_postcondition_observation_before_external_retry(self) -> None:
        result = decide_process(
            Path.cwd(),
            request="Retry the reversible external effect.",
            check_command="python3 -m unittest tests.test_api",
            signals={
                "small_change": False,
                "known_scope": True,
                "external_effects": "reversible",
                "needs_iteration": True,
            },
        )

        self.assertEqual(
            authorize_external_retry(
                result["decision"], postcondition_observed=False
            ),
            (False, "external retry requires post-condition observation"),
        )
        self.assertEqual(
            authorize_external_retry(result["decision"], postcondition_observed=True),
            (True, None),
        )

    def test_never_creates_work_from_role_labels_alone(self) -> None:
        result = decide_process(
            Path.cwd(),
            request="Use research and review roles.",
            check_command="python3 -m unittest tests.test_domain",
            signals={
                "known_scope": True,
                "graph_requested": True,
                "roles": ["research", "review", "integration"],
                "integrator": "coordinator-1",
                "permission_observed": True,
                "budget_limits": [
                    {
                        "resource": "workers",
                        "value": 3,
                        "unit": "workers",
                        "rationale": "This limit alone cannot create work.",
                    }
                ],
                "cleanup_plan": "No work means no owned cleanup.",
            },
        )

        self.assertEqual(result["decision"]["mode"], "light_spec")
        self.assertEqual(result["decision"]["observations"]["independent_packets"], [])
        self.assertFalse(result["graph_artifacts_created"])


class StructuredArtifactBehavior(unittest.TestCase):
    def test_validates_a_scoped_worker_report_without_grading(self) -> None:
        task = graph_core.parse_task_graph(VALID_TASKS).tasks[0]
        result = {
            "task_id": "ROOT-01",
            "attempt_id": "attempt-01",
            "outcome": "reported",
            "summary": "Implemented the bounded domain change.",
            "files_changed": ["src/domain/model.py"],
            "checks_run": ["python3 -m unittest tests.test_domain"],
            "evidence_refs": ["file:openspec/runs/change/run/artifacts/check.txt"],
            "questions": [],
            "external_refs": {"worker": "worker-1"},
        }

        validated = graph_core.validate_worker_result(result, task, "attempt-01")

        self.assertEqual(validated["outcome"], "reported")
        self.assertNotIn("grade", validated)

    def test_rejects_mismatched_and_out_of_scope_worker_reports(self) -> None:
        task = graph_core.parse_task_graph(VALID_TASKS).tasks[0]
        result = {
            "task_id": "ROOT-01",
            "attempt_id": "wrong-attempt",
            "outcome": "reported",
            "summary": "Changed an unrelated file.",
            "files_changed": ["src/api/handler.py"],
            "checks_run": [],
            "evidence_refs": [],
            "questions": [],
            "external_refs": {},
        }

        with self.assertRaisesRegex(graph_core.GraphValidationError, "attempt_id"):
            graph_core.validate_worker_result(result, task, "attempt-01")
        result["attempt_id"] = "attempt-01"
        with self.assertRaisesRegex(graph_core.GraphValidationError, "outside task Paths"):
            graph_core.validate_worker_result(result, task, "attempt-01")

    def test_accepts_a_no_change_worker_audit_without_checks(self) -> None:
        task = graph_core.parse_task_graph(VALID_TASKS).tasks[0]
        result = {
            "task_id": "ROOT-01",
            "attempt_id": "attempt-01",
            "outcome": "reported",
            "summary": "The source contract blocks the requested change.",
            "files_changed": [],
            "checks_run": [],
            "evidence_refs": [],
            "questions": [{"kind": "blocker", "detail": "The source contract is incomplete."}],
            "external_refs": {},
        }

        validated = graph_core.validate_worker_result(result, task, "attempt-01")

        self.assertEqual(validated["checks_run"], [])

    def test_requires_a_check_when_a_worker_reports_changed_files(self) -> None:
        task = graph_core.parse_task_graph(VALID_TASKS).tasks[0]
        result = {
            "task_id": "ROOT-01",
            "attempt_id": "attempt-01",
            "outcome": "reported",
            "summary": "Changed the bounded domain model.",
            "files_changed": ["src/domain/model.py"],
            "checks_run": [],
            "evidence_refs": [],
            "questions": [],
            "external_refs": {},
        }

        with self.assertRaisesRegex(graph_core.GraphValidationError, "at least one check"):
            graph_core.validate_worker_result(result, task, "attempt-01")

    def test_names_the_invalid_external_reference_type(self) -> None:
        task = graph_core.parse_task_graph(VALID_TASKS).tasks[0]
        result = {
            "task_id": "ROOT-01",
            "attempt_id": "attempt-01",
            "outcome": "reported",
            "summary": "Recorded bounded verification metadata.",
            "files_changed": [],
            "checks_run": [],
            "evidence_refs": [],
            "questions": [],
            "external_refs": {"duration_seconds": 493.48},
        }

        with self.assertRaisesRegex(
            graph_core.GraphValidationError,
            r"external_refs\['duration_seconds'\] has unsupported type float",
        ):
            graph_core.validate_worker_result(result, task, "attempt-01")

    def test_keeps_worker_result_schema_and_validator_in_parity(self) -> None:
        task = graph_core.parse_task_graph(VALID_TASKS).tasks[0]
        validator = Draft202012Validator(load_json(REFERENCES / "worker-result.schema.json"))
        valid_no_change = {
            "task_id": "ROOT-01",
            "attempt_id": "attempt-01",
            "outcome": "reported",
            "summary": "Recorded a source-contract blocker.",
            "files_changed": [],
            "checks_run": [],
            "evidence_refs": [],
            "questions": [],
            "external_refs": {},
        }
        invalid_changed_without_check = {
            **valid_no_change,
            "files_changed": ["src/domain/model.py"],
        }
        invalid_outcome = {**valid_no_change, "outcome": "passed"}
        invalid_external_refs = {**valid_no_change, "external_refs": []}

        for result, accepted in (
            (valid_no_change, True),
            (invalid_changed_without_check, False),
            (invalid_outcome, False),
            (invalid_external_refs, False),
        ):
            with self.subTest(result=result, accepted=accepted):
                schema_errors = list(validator.iter_errors(result))
                if accepted:
                    self.assertEqual(schema_errors, [])
                    graph_core.validate_worker_result(result, task, "attempt-01")
                else:
                    self.assertTrue(schema_errors)
                    with self.assertRaises(graph_core.GraphValidationError):
                        graph_core.validate_worker_result(result, task, "attempt-01")

    def test_validates_a_transcript_free_coordinator_capsule(self) -> None:
        capsule = {
            "schema_version": 1,
            "protocol_version": 1,
            "workspace_scope": workspace_scope(run_id="run-1", generation=2),
            "change": "portable-graph",
            "run_id": "run-1",
            "driver": "auto",
            "capability_summary": {"agents": ["codex"]},
            "routing_overrides": {},
            "coordinator_generation": 2,
            "resume_command": "$impl --coordinator-capsule openspec/runs/run/capsule.json",
            "control_runtime": CONTROL_RUNTIME,
        }

        self.assertEqual(graph_core.validate_coordinator_capsule(capsule), capsule)
        with self.assertRaisesRegex(graph_core.GraphValidationError, "unknown fields"):
            graph_core.validate_coordinator_capsule({**capsule, "transcript": "forbidden"})


class OrchestrationContractBehavior(unittest.TestCase):
    def test_validates_authoritative_workspace_bootstrap_receipts(self) -> None:
        host = graph_core.validate_workspace_bootstrap_receipt(
            WORKSPACE_RECEIPTS["host_run"]
        )
        remote = graph_core.validate_workspace_bootstrap_receipt(
            WORKSPACE_RECEIPTS["orca_remote"]
        )

        self.assertEqual(host["authority"]["kind"], "host-run")
        self.assertEqual(remote["execution_host"]["id"], "ssh:build-host-01")
        self.assertEqual(remote["orchestration_home"]["execution_host_id"], "runtime:orca-local-01")
        self.assertEqual(remote["base_revision"], "fedcba9876543210fedcba9876543210fedcba98")
        self.assertEqual(remote["dirty_paths"], ["remote/source.py"])
        validator = Draft202012Validator(
            load_json(REFERENCES / "placement.schema.json"),
            registry=SchemaBehavior.registry(),
        )
        validator.validate(host)
        validator.validate(remote)

        for field in ("base_revision", "dirty_paths"):
            with self.subTest(missing=field):
                invalid = copy.deepcopy(host)
                invalid.pop(field)
                with self.assertRaisesRegex(
                    graph_core.GraphValidationError, f"missing fields: {field}"
                ):
                    graph_core.validate_workspace_bootstrap_receipt(invalid)

    def test_enforces_host_run_semantics_in_code_and_schema(self) -> None:
        host = copy.deepcopy(WORKSPACE_RECEIPTS["host_run"])
        repository = Path(host["canonical_root"])
        graph_core.validate_workspace_bootstrap_receipt(
            host,
            expected_run_id=host["authority"]["issued_for_run_id"],
            expected_repository=repository,
        )
        validator = Draft202012Validator(
            load_json(REFERENCES / "placement.schema.json"),
            registry=SchemaBehavior.registry(),
        )
        divergences = {
            "repository_id": lambda value: value.update(repository_id="host-run-not-a-uuid"),
            "remote_boundary": lambda value: value["execution_host"].update(boundary="remote"),
            "different_identity": lambda value: value["execution_workspace"].update(
                workspace_key="folder:another-host-run"
            ),
            "worktree": lambda value: value["execution_workspace"].update(
                kind="git-worktree", worktree_path=value["canonical_root"]
            ),
            "workspace_key": lambda value: value["orchestration_home"].update(
                workspace_key="folder:another-host-run"
            ),
        }
        for name, mutate in divergences.items():
            with self.subTest(name=name):
                invalid = copy.deepcopy(host)
                mutate(invalid)
                with self.assertRaises(graph_core.GraphValidationError):
                    graph_core.validate_workspace_bootstrap_receipt(invalid)
                self.assertTrue(list(validator.iter_errors(invalid)))

        wrong_run = copy.deepcopy(host)
        with self.assertRaisesRegex(graph_core.GraphValidationError, "another run"):
            graph_core.validate_workspace_bootstrap_receipt(
                wrong_run,
                expected_run_id="run-other",
                expected_repository=repository,
            )
        aliased = copy.deepcopy(host)
        aliased_root = host["canonical_root"] + "/."
        aliased["canonical_root"] = aliased_root
        aliased["orchestration_home"]["path"] = aliased_root
        aliased["execution_workspace"]["path"] = aliased_root
        with self.assertRaisesRegex(graph_core.GraphValidationError, "repository"):
            graph_core.validate_workspace_bootstrap_receipt(
                aliased,
                expected_run_id=host["authority"]["issued_for_run_id"],
                expected_repository=repository,
            )

        opaque_local = copy.deepcopy(host)
        opaque_local["execution_host"]["id"] = "runtime:opaque-local"
        opaque_local["orchestration_home"]["execution_host_id"] = "runtime:opaque-local"
        opaque_local["execution_workspace"]["execution_host_id"] = "runtime:opaque-local"
        graph_core.validate_workspace_bootstrap_receipt(opaque_local)

    def test_accepts_folder_worktree_local_remote_and_opaque_workspace_keys(self) -> None:
        folder = graph_core.validate_workspace_scope(WORKSPACE_SCOPES["folder_local"])
        worktree = graph_core.validate_workspace_scope(WORKSPACE_SCOPES["worktree_remote"])

        self.assertEqual(folder["execution_workspace"]["workspace_key"], OPAQUE_WORKSPACE_KEY)
        self.assertEqual(worktree["execution_host"]["boundary"], "remote")
        self.assertEqual(worktree["execution_workspace"]["kind"], "git-worktree")
        expected_worktree_key = (
            f"worktree:{worktree['repository_id']}::"
            f"{worktree['execution_workspace']['path']}"
        )
        self.assertEqual(
            worktree["execution_workspace"]["workspace_key"], expected_worktree_key
        )
        self.assertNotEqual(
            worktree["execution_workspace"]["workspace_key"], "worktree:worktree-mlk-01"
        )

    def test_accepts_remote_windows_paths_lexically_and_rejects_relative_paths(self) -> None:
        windows = copy.deepcopy(WORKSPACE_SCOPES["worktree_remote"])
        windows["canonical_root"] = "C:\\repos\\my-llm-kit"
        windows["execution_host"] = {"id": "host-windows", "boundary": "remote"}
        windows["orchestration_home"] = {
            "execution_host_id": "host-windows",
            "workspace_key": "folder:windows-folder-01",
            "kind": "folder",
            "path": "C:\\repos\\my-llm-kit",
        }
        windows["execution_workspace"] = {
            "execution_host_id": "host-windows",
            "workspace_key": (
                "worktree:fb2a9411-f3cb-46d4-94f7-067f40719b71::"
                "C:\\worktrees\\mlk-01"
            ),
            "kind": "git-worktree",
            "path": "C:\\worktrees\\mlk-01",
            "worktree_path": "C:\\worktrees\\mlk-01",
        }

        validated = graph_core.validate_workspace_scope(windows)
        self.assertEqual(
            validated["execution_workspace"]["path"], "C:\\worktrees\\mlk-01"
        )
        Draft202012Validator(
            load_json(REFERENCES / "placement.schema.json"),
            registry=SchemaBehavior.registry(),
        ).validate(windows)

        relative = copy.deepcopy(windows)
        relative["execution_workspace"]["path"] = "worktrees\\mlk-01"
        relative["execution_workspace"]["worktree_path"] = "worktrees\\mlk-01"
        with self.assertRaisesRegex(graph_core.GraphValidationError, "must be absolute"):
            graph_core.validate_workspace_scope(relative)

    def test_rejects_invalid_and_cross_host_workspace_identities(self) -> None:
        invalid = copy.deepcopy(WORKSPACE_SCOPES["folder_local"])
        invalid["execution_workspace"]["workspace_key"] = "bad\nkey"
        with self.assertRaisesRegex(graph_core.GraphValidationError, "opaque identity"):
            graph_core.validate_workspace_scope(invalid)

        cross_host = copy.deepcopy(WORKSPACE_SCOPES["folder_local"])
        cross_host["execution_workspace"]["execution_host_id"] = "host-remote"
        with self.assertRaisesRegex(graph_core.GraphValidationError, "execution_host"):
            graph_core.validate_workspace_scope(cross_host)

    def test_validates_current_existing_and_child_attempt_placements(self) -> None:
        graph_core.validate_execution_profile(
            EXECUTION_PROFILES["current_folder"], WORKSPACE_SCOPES["folder_local"]
        )
        graph_core.validate_execution_profile(
            EXECUTION_PROFILES["existing_remote_with_fallback"],
            WORKSPACE_SCOPES["worktree_remote"],
        )
        graph_core.validate_execution_profile(
            EXECUTION_PROFILES["child_worktree"], WORKSPACE_SCOPES["folder_local"]
        )
        child = EXECUTION_PROFILES["child_worktree"]["resolved_placement"]
        self.assertEqual(
            child["workspace_key"],
            (
                f"worktree:{WORKSPACE_SCOPES['folder_local']['repository_id']}::"
                f"{child['path']}"
            ),
        )

    def test_rejects_cross_workspace_placement_and_hidden_fallback(self) -> None:
        mismatch = copy.deepcopy(EXECUTION_PROFILES["current_folder"])
        mismatch["resolved_placement"]["workspace_key"] = (
            "fb2a9411-f3cb-46d4-94f7-067f40719b71::/other/worktree"
        )
        with self.assertRaisesRegex(graph_core.GraphValidationError, "does not match the pin"):
            graph_core.validate_execution_profile(mismatch, WORKSPACE_SCOPES["folder_local"])

        fallback = copy.deepcopy(EXECUTION_PROFILES["existing_remote_with_fallback"])
        fallback["fallback_reason"] = None
        with self.assertRaisesRegex(graph_core.GraphValidationError, "fallback_reason"):
            graph_core.validate_execution_profile(fallback, WORKSPACE_SCOPES["worktree_remote"])

    def test_validates_three_authenticated_transcript_free_protocol_objects(self) -> None:
        scope = WORKSPACE_SCOPES["folder_local"]
        view = load_json(FIXTURES / "agent-graph-view.json")
        mutation = load_json(FIXTURES / "maestro-mutation.json")
        intent = load_json(FIXTURES / "delegation-intent.json")

        graph_core.validate_agent_graph_view(view)
        graph_core.validate_maestro_mutation(mutation, scope)
        graph_core.validate_delegation_intent(intent, scope)

        transcript_view = copy.deepcopy(view)
        transcript_view["nodes"][0]["transcript"] = "forbidden"
        with self.assertRaisesRegex(graph_core.GraphValidationError, "unknown fields"):
            graph_core.validate_agent_graph_view(transcript_view)

    def test_rejects_cross_workspace_and_stale_maestro_mutations(self) -> None:
        scope = WORKSPACE_SCOPES["folder_local"]
        with self.assertRaisesRegex(graph_core.GraphValidationError, "pinned scope"):
            graph_core.validate_maestro_mutation(
                load_json(FIXTURES / "invalid" / "cross-workspace-mutation.json"), scope
            )
        with self.assertRaisesRegex(graph_core.GraphValidationError, "stale"):
            graph_core.validate_maestro_mutation(
                load_json(FIXTURES / "invalid" / "stale-generation-mutation.json"), scope
            )


class JournalBehavior(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary_directory.name)
        self.journal = graph_core.EventJournal(self.directory / "events.jsonl")
        self.graph = graph_core.parse_task_graph(VALID_TASKS)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def starts_run(self) -> None:
        self.journal.append(
            "run_started",
            {
                "change": "portable-graph",
                "run_id": "run-1",
                "coordinator_id": "coordinator-1",
                "coordinator_generation": 1,
                "workspace_scope": workspace_scope(),
                "control_runtime": CONTROL_RUNTIME,
                "tasks": [task.to_dict() for task in self.graph.tasks],
            },
            coordinator_generation=1,
            timestamp="2026-08-20T12:00:00Z",
        )

    def reserves_attempt(self, data: dict | None = None) -> dict:
        reserved = copy.deepcopy(data or attempt_data())
        projection = self.journal.verify_projection()
        reserved["workspace_scope"] = projection["workspace_scope"]
        self.journal.append(
            "attempt_reserved",
            reserved,
            coordinator_generation=projection["coordinator"]["generation"],
        )
        return reserved

    def freezes_attempt(self, data: dict | None = None) -> dict:
        reserved = self.reserves_attempt(data)
        projection = self.journal.verify_projection()
        projection = self.journal.append(
            "attempt_scope_frozen",
            {
                "attempt_id": reserved["attempt_id"],
                "effective_scope": projection["attempts"][reserved["attempt_id"]]["effective_scope"],
            },
            coordinator_generation=projection["coordinator"]["generation"],
        )
        reserved["effective_scope"] = projection["attempts"][reserved["attempt_id"]][
            "effective_scope"
        ]
        return reserved

    def starts_attempt(self, data: dict | None = None) -> dict:
        started = self.freezes_attempt(data)
        return self.journal.append(
            "attempt_started",
            started,
            coordinator_generation=self.journal.verify_projection()["coordinator"]["generation"],
        )

    def report_data(self, attempt_id: str = "attempt-01") -> dict:
        projection = self.journal.verify_projection()
        return {
            "task_id": "ROOT-01",
            "attempt_id": attempt_id,
            "outcome": "reported",
            "effective_scope": projection["attempts"][attempt_id]["effective_scope"],
        }

    def test_replays_the_saved_projection(self) -> None:
        self.starts_run()
        started = self.freezes_attempt()
        self.journal.append("attempt_started", started, coordinator_generation=1, timestamp="2026-08-20T12:01:00Z")
        reported = self.journal.append(
            "worker_reported",
            self.report_data(),
            coordinator_generation=1,
            timestamp="2026-08-20T12:02:00Z",
        )

        self.assertEqual(reported["tasks"]["ROOT-01"]["status"], "reported")
        self.assertIsNone(reported["tasks"]["ROOT-01"]["grade"])
        verified = self.journal.verify_projection()
        self.assertEqual(verified, reported)

    def test_rejects_completion_when_attempt_cleanup_was_not_registered(self) -> None:
        self.starts_run()
        self.starts_attempt()
        projection = self.journal.append(
            "cleanup_registered",
            {
                "cleanup_id": "cleanup-attempt-01",
                "kind": "other",
                "target": "resource-01",
                "owner": "attempt-01",
            },
            coordinator_generation=1,
        )

        self.assertEqual(
            graph_core.unresolved_cleanup_ids(projection),
            ["cleanup-attempt-01"],
        )
        with self.assertRaisesRegex(
            graph_core.JournalError,
            "run_completed requires terminal cleanup: cleanup-attempt-01",
        ):
            self.journal.append(
                "run_completed",
                {"outcome": "partial"},
                coordinator_generation=1,
            )

    def test_blocks_terminal_grade_until_attempt_and_cleanup_settle(self) -> None:
        self.starts_run()
        self.starts_attempt()
        self.journal.append(
            "cleanup_registered",
            {
                "cleanup_id": "cleanup-attempt-01",
                "kind": "other",
                "target": "resource-01",
                "owner": "attempt-01",
            },
            coordinator_generation=1,
        )
        journal_before = self.journal.path.read_bytes()
        state_before = self.journal.projection_path.read_bytes()

        with self.assertRaisesRegex(graph_core.JournalError, "no active attempts"):
            self.journal.append(
                "task_graded",
                {
                    "task_id": "ROOT-01",
                    "grade": "blocked",
                    "note": "Waiting for external lifecycle reconciliation.",
                    "evidence_refs": [],
                },
                coordinator_generation=1,
            )

        self.assertEqual(self.journal.path.read_bytes(), journal_before)
        self.assertEqual(self.journal.projection_path.read_bytes(), state_before)
        self.journal.append(
            "cleanup_retained",
            {"cleanup_id": "cleanup-attempt-01", "receipt": {"reason": "absent"}},
            coordinator_generation=1,
        )
        self.journal.append(
            "attempt_abandoned",
            {
                "task_id": "ROOT-01",
                "attempt_id": "attempt-01",
                "reason": "External lifecycle reconciled absent.",
            },
            coordinator_generation=1,
        )
        graded = self.journal.append(
            "task_graded",
            {
                "task_id": "ROOT-01",
                "grade": "blocked",
                "note": "External lifecycle reconciliation prevented execution.",
                "evidence_refs": [],
            },
            coordinator_generation=1,
        )

        self.assertEqual(graded["tasks"]["ROOT-01"]["grade"], "blocked")

    def test_preserves_attempt_checks_across_audit_rejection_and_retry(self) -> None:
        self.starts_run()
        self.starts_attempt()
        projection = self.journal.append(
            "worker_reported",
            self.report_data(),
            coordinator_generation=1,
        )
        first_check = {
            "task_id": "ROOT-01",
            "attempt_id": "attempt-01",
            "command": self.graph.by_id()["ROOT-01"].check,
            "status": "passed",
            "exit_code": 0,
            "duration_ms": 1,
            "attempts": 1,
            "total_duration_ms": 1,
            "artifact": "artifacts/checks/ROOT-01-001.json",
        }
        projection = self.journal.append(
            "check_recorded", first_check, coordinator_generation=1
        )
        self.assertEqual(projection["attempts"]["attempt-01"]["check"], first_check)
        self.journal.append(
            "cleanup_registered",
            {
                "cleanup_id": "cleanup-attempt-01",
                "kind": "other",
                "target": "resource-01",
                "owner": "attempt-01",
            },
            coordinator_generation=1,
        )
        self.journal.append(
            "cleanup_retained",
            {"cleanup_id": "cleanup-attempt-01", "receipt": {"reason": "reviewed"}},
            coordinator_generation=1,
        )
        self.journal.append(
            "finding_recorded",
            {
                "schema_version": 1,
                "finding_id": "finding-rejection-01",
                "classification": "acceptance_violation",
                "task_id": "ROOT-01",
                "attempt_id": "attempt-01",
                "acceptance_reference": "ROOT-01 acceptance",
                "evidence_ref": "file:artifacts/audit/rejection-01.json",
                "affected": [{"file": "src/root.py", "identity": "root implementation"}],
                "reproduction": {
                    "steps": ["Inspect the reported implementation."],
                    "observed": "The acceptance is violated.",
                    "expected": "The acceptance is satisfied.",
                },
                "smallest_repair_hypothesis": "Bind the retry to its own check.",
                "why_current_check_does_not_detect": "The focused Check does not inspect this invariant.",
            },
            coordinator_generation=1,
        )
        rejected = self.journal.append(
            "attempt_audit_rejected",
            {
                "rejection_id": "rejection-01",
                "task_id": "ROOT-01",
                "attempt_id": "attempt-01",
                "finding_refs": ["file:artifacts/audit/rejection-01.json"],
                "hypothesis": "Bind the retry to its own check.",
            },
            coordinator_generation=1,
        )

        self.assertEqual(rejected["attempts"]["attempt-01"]["status"], "audit-rejected")
        self.assertEqual(rejected["attempts"]["attempt-01"]["check"], first_check)
        self.assertEqual(
            rejected["attempts"]["attempt-01"]["audit_rejection"],
            {
                "rejection_id": "rejection-01",
                "finding_refs": ["file:artifacts/audit/rejection-01.json"],
                "hypothesis": "Bind the retry to its own check.",
            },
        )
        self.assertIsNone(rejected["tasks"]["ROOT-01"]["check"])
        self.assertEqual(rejected["tasks"]["ROOT-01"]["status"], "pending")
        self.assertEqual(
            [task.id for task in graph_core.ready_tasks(self.graph, rejected)],
            ["ROOT-01"],
        )
        self.starts_attempt(attempt_data("attempt-02"))
        self.journal.append(
            "worker_reported",
            self.report_data("attempt-02"),
            coordinator_generation=1,
        )
        second_check = {
            **first_check,
            "attempt_id": "attempt-02",
            "attempts": 2,
            "total_duration_ms": 2,
            "artifact": "artifacts/checks/ROOT-01-002.json",
        }
        retried = self.journal.append(
            "check_recorded", second_check, coordinator_generation=1
        )
        self.assertEqual(retried["attempts"]["attempt-01"]["check"], first_check)
        self.assertEqual(retried["attempts"]["attempt-02"]["check"], second_check)
        self.assertEqual(retried["tasks"]["ROOT-01"]["check"], second_check)
        Draft202012Validator(
            load_json(REFERENCES / "run-state.schema.json"),
            registry=SchemaBehavior.registry(),
        ).validate(retried)

    def test_requires_check_recorded_to_name_the_latest_reported_attempt(self) -> None:
        self.starts_run()
        self.starts_attempt()
        self.journal.append(
            "worker_reported",
            self.report_data(),
            coordinator_generation=1,
        )
        with self.assertRaisesRegex(graph_core.GraphValidationError, "attempt_id"):
            self.journal.append(
                "check_recorded",
                {
                    "task_id": "ROOT-01",
                    "command": self.graph.by_id()["ROOT-01"].check,
                    "status": "passed",
                    "exit_code": 0,
                },
                coordinator_generation=1,
            )

    def test_fences_a_stale_coordinator_after_transfer(self) -> None:
        self.starts_run()
        self.journal.append(
            "coordinator_transferred",
            {"coordinator_id": None, "coordinator_generation": 2},
            coordinator_generation=1,
        )

        with self.assertRaises(graph_core.StaleCoordinatorError):
            self.journal.append(
                "coordinator_claimed",
                {"coordinator_id": "stale"},
                coordinator_generation=1,
            )
        claimed = self.journal.append(
            "coordinator_claimed",
            {"coordinator_id": "coordinator-2"},
            coordinator_generation=2,
        )
        self.assertEqual(claimed["coordinator"], {"id": "coordinator-2", "generation": 2})
        self.assertEqual(claimed["workspace_scope"]["coordinator_generation"], 2)

    def test_recovers_only_a_partial_final_line(self) -> None:
        self.starts_run()
        with self.journal.path.open("ab") as handle:
            handle.write(b'{"schema_version":1,"event_id":"event-000002"')
        artifact = self.directory / "artifacts" / "partial.bin"

        with self.assertRaisesRegex(graph_core.JournalError, "partial final line"):
            self.journal.replay()
        repaired = self.journal.recover_partial_line(
            artifact,
            coordinator_generation=1,
        )

        self.assertTrue(artifact.read_bytes().startswith(b'{"schema_version"'))
        self.assertEqual(repaired["last_sequence"], 2)
        self.assertEqual(self.journal.verify_projection(), repaired)

    def test_blocks_corruption_on_a_complete_line(self) -> None:
        self.starts_run()
        with self.journal.path.open("ab") as handle:
            handle.write(b"not-json\n")

        with self.assertRaisesRegex(graph_core.JournalError, "corruption at line 2"):
            self.journal.replay()
        with self.assertRaisesRegex(graph_core.JournalError, "corruption at line 2"):
            self.journal.recover_partial_line(
                self.directory / "partial.bin",
                coordinator_generation=1,
            )

    def test_detects_a_tampered_saved_projection(self) -> None:
        self.starts_run()
        saved = json.loads(self.journal.projection_path.read_text(encoding="utf-8"))
        saved["status"] = "complete"
        self.journal.projection_path.write_text(json.dumps(saved), encoding="utf-8")

        with self.assertRaisesRegex(graph_core.JournalError, "does not match"):
            self.journal.verify_projection()

    def test_types_attempt_questions_and_cleanup_ownership(self) -> None:
        self.starts_run()
        self.starts_attempt()
        observed = self.journal.append(
            "attempt_observed",
            {
                "attempt_id": "attempt-01",
                "cursor": {"stream_id": "attempt-01", "sequence": 4, "revision": 4},
                "receipt_path": "openspec/runs/change/run/artifacts/poll.json",
            },
            coordinator_generation=1,
        )
        opened = self.journal.append(
            "question_opened",
            {
                "question_id": "question-01",
                "attempt_id": "attempt-01",
                "prompt": "Which workspace owns this terminal?",
                "actor": {
                    "actor_id": "worker-1",
                    "kind": "worker",
                    "authenticated": True,
                    "session_id": "session-1",
                },
            },
            coordinator_generation=1,
        )
        with self.assertRaisesRegex(graph_core.JournalError, "anchored attempt"):
            self.journal.append(
                "cleanup_registered",
                {
                    "cleanup_id": "cleanup-unanchored",
                    "attempt_id": "attempt-01",
                    "owner": cleanup_owner(),
                },
                coordinator_generation=1,
            )
        registered = self.journal.append(
            "cleanup_registered",
            {
                "cleanup_id": "cleanup-01",
                "kind": "other",
                "target": "manual-resource-01",
                "owner": "attempt-01",
            },
            coordinator_generation=1,
        )

        self.assertEqual(opened["questions"]["question-01"]["status"], "open")
        self.assertEqual(observed["attempts"]["attempt-01"]["cursor"]["revision"], 4)
        self.assertEqual(
            registered["cleanup"]["cleanup-01"]["owner"],
            "attempt-01",
        )

    def test_rejects_reserved_attempt_identity_divergence(self) -> None:
        self.starts_run()
        reserved = self.freezes_attempt()
        divergent = copy.deepcopy(reserved)
        divergent["execution_profile"]["resolved"]["model"] = "other-model"

        with self.assertRaisesRegex(graph_core.JournalError, "diverges"):
            self.journal.append(
                "attempt_started", divergent, coordinator_generation=1
            )

    def test_rejects_missing_or_divergent_workspace_scope_during_reservation_and_start(self) -> None:
        self.starts_run()
        missing_scope = attempt_data()
        missing_scope.pop("workspace_scope")
        with self.assertRaisesRegex(graph_core.JournalError, "identity is invalid"):
            self.journal.append("attempt_reserved", missing_scope, coordinator_generation=1)

        missing_profile = attempt_data()
        missing_profile.pop("execution_profile")
        with self.assertRaisesRegex(graph_core.JournalError, "identity is invalid"):
            self.journal.append("attempt_reserved", missing_profile, coordinator_generation=1)

        cross_workspace = attempt_data()
        cross_workspace["workspace_scope"]["execution_workspace"]["workspace_key"] = "folder:other-workspace"
        with self.assertRaisesRegex(graph_core.JournalError, "diverges from the pinned"):
            self.journal.append("attempt_reserved", cross_workspace, coordinator_generation=1)

        reserved = self.freezes_attempt()
        divergent_start = copy.deepcopy(reserved)
        divergent_start["workspace_scope"]["binding_receipt_hash"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(graph_core.JournalError, "workspace_scope diverges"):
            self.journal.append("attempt_started", divergent_start, coordinator_generation=1)

        with self.assertRaisesRegex(graph_core.JournalError, "requires a reserved attempt"):
            self.journal.append(
                "attempt_started", attempt_data("attempt-unreserved"), coordinator_generation=1
            )

    def test_requires_the_current_scope_for_reservations_after_takeover(self) -> None:
        self.starts_run()
        original_scope = workspace_scope()
        self.journal.append(
            "coordinator_taken_over",
            {"coordinator_id": "coordinator-2", "coordinator_generation": 2},
            coordinator_generation=1,
        )

        with self.assertRaisesRegex(graph_core.JournalError, "diverges from the pinned"):
            self.journal.append(
                "attempt_reserved", attempt_data(), coordinator_generation=2
            )

        current_scope = self.journal.verify_projection()["workspace_scope"]
        self.assertNotEqual(original_scope, current_scope)
        reserved = attempt_data()
        reserved["workspace_scope"] = current_scope
        reserved = self.freezes_attempt(reserved)
        started = self.journal.append("attempt_started", reserved, coordinator_generation=2)
        self.assertEqual(started["attempts"]["attempt-01"]["workspace_scope"], current_scope)

    def test_replays_and_schema_validates_the_exact_legacy_question_shape(self) -> None:
        self.starts_run()
        self.starts_attempt()
        projected = self.journal.append(
            "question_opened",
            {
                "question_id": "question-legacy-01",
                "attempt_id": "attempt-01",
                "body": "May I continue with the bounded repair?",
                "receipt_path": "openspec/runs/change/run/artifacts/question.json",
                "delivery_id": None,
            },
            coordinator_generation=1,
        )

        question = projected["questions"]["question-legacy-01"]
        self.assertEqual(question["body"], "May I continue with the bounded repair?")
        self.assertNotIn("actor", question)
        replayed = self.journal.verify_projection()
        Draft202012Validator(
            load_json(REFERENCES / "run-state.schema.json"),
            registry=SchemaBehavior.registry(),
        ).validate(replayed)

        with self.assertRaisesRegex(graph_core.JournalError, "missing fields: actor"):
            self.journal.append(
                "question_opened",
                {
                    "question_id": "question-versioned-invalid",
                    "attempt_id": "attempt-01",
                    "prompt": "This versioned payload omitted its actor.",
                },
                coordinator_generation=1,
            )

    def test_imports_a_checked_task_only_with_real_check_evidence(self) -> None:
        check_command = f'"{sys.executable}" -c "print(\'checked-import\')"'
        checked_source = VALID_TASKS.replace("- [ ] ROOT-01", "- [x] ROOT-01").replace(
            "python3 -m unittest tests.test_domain", check_command
        )
        checked_graph = graph_core.parse_task_graph(checked_source)
        source_file = self.directory / "src" / "domain.py"
        source_file.parent.mkdir()
        source_file.write_text("VALUE = 'checked-import'\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(self.directory)], check=True)
        subprocess.run(
            ["git", "-C", str(self.directory), "config", "user.email", "test@example.com"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(self.directory), "config", "user.name", "Test"],
            check=True,
        )
        subprocess.run(["git", "-C", str(self.directory), "add", "src/domain.py"], check=True)
        subprocess.run(
            ["git", "-C", str(self.directory), "commit", "-qm", "checked import fixture"],
            check=True,
        )
        self.journal = graph_core.EventJournal(
            self.directory
            / "openspec"
            / "runs"
            / "portable-graph"
            / "run-1"
            / "events.jsonl"
        )
        scope = workspace_scope()
        scope["canonical_root"] = str(self.directory)
        scope["orchestration_home"]["path"] = str(self.directory)
        scope["execution_workspace"]["path"] = str(self.directory)
        base_commit = subprocess.run(
            ["git", "-C", str(self.directory), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        self.journal.append(
            "run_started",
            {
                "change": "portable-graph",
                "run_id": "run-1",
                "coordinator_id": "coordinator-1",
                "coordinator_generation": 1,
                "workspace_scope": scope,
                "control_runtime": CONTROL_RUNTIME,
                "tasks": [task.to_dict() for task in checked_graph.tasks],
                "base_commit": base_commit,
            },
            coordinator_generation=1,
        )

        with self.assertRaisesRegex(graph_core.JournalError, "check-backed import"):
            self.journal.append(
                "task_graded",
                {
                    "task_id": "ROOT-01",
                    "grade": "pass",
                    "note": "Unchecked source box.",
                    "evidence_refs": [],
                },
                coordinator_generation=1,
            )

        original_append = self.journal.append

        def interrupt_after_evidence(event_type, *args, **kwargs):
            if event_type == "checked_task_imported":
                raise graph_core.JournalError("simulated interruption before import commit")
            return original_append(event_type, *args, **kwargs)

        self.journal.append = interrupt_after_evidence
        with self.assertRaisesRegex(graph_core.JournalError, "simulated interruption"):
            self.journal.import_checked_task(
                "ROOT-01",
                import_id="import-root-01",
                coordinator_generation=1,
                note="Imported after coordinator verification.",
            )
        self.journal.append = original_append

        execution = next(
            iter(self.journal.verify_projection()["check_executions"].values())
        )
        artifact = self.directory / execution["artifact_ref"]
        evidence = load_json(artifact)
        self.assertEqual(evidence["execution_id"], execution["execution_id"])
        self.assertEqual(
            evidence["source_snapshot_digest"], execution["source_snapshot_digest"]
        )
        self.assertEqual(evidence["exit_code"], 0)
        self.assertIn("checked-import", evidence["stdout"])

        with mock.patch.object(
            validation,
            "run_bounded_command",
            side_effect=AssertionError("retry must verify persisted evidence"),
        ):
            imported = self.journal.import_checked_task(
                "ROOT-01",
                import_id="import-root-01",
                coordinator_generation=1,
                note="Imported after coordinator verification.",
            )
            repeated = self.journal.import_checked_task(
                "ROOT-01",
                import_id="import-root-01",
                coordinator_generation=1,
                note="Imported after coordinator verification.",
            )

        self.assertEqual(imported["tasks"]["ROOT-01"]["grade"], "pass")
        self.assertEqual(imported["tasks"]["ROOT-01"]["check"]["status"], "passed")
        self.assertEqual(repeated, imported)
        self.assertTrue(artifact.is_file())
        Draft202012Validator(
            load_json(REFERENCES / "run-state.schema.json"),
            registry=SchemaBehavior.registry(),
        ).validate(imported)
        event_types = [
            json.loads(line)["type"]
            for line in self.journal.path.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(event_types.count("checked_task_imported"), 1)
        self.assertNotIn("check_recorded", event_types)
        self.assertNotIn("task_graded", event_types)
        artifact.unlink()
        with self.assertRaisesRegex(graph_core.JournalError, "evidence is missing"):
            self.journal.import_checked_task(
                "ROOT-01",
                import_id="import-root-01",
                coordinator_generation=1,
                note="Imported after coordinator verification.",
            )

    def test_rejects_shell_composition_during_checked_import(self) -> None:
        checked_source = VALID_TASKS.replace("- [ ] ROOT-01", "- [x] ROOT-01").replace(
            "python3 -m unittest tests.test_domain", "true && false"
        )
        checked_graph = graph_core.parse_task_graph(checked_source)
        scope = workspace_scope()
        scope["canonical_root"] = str(self.directory)
        scope["orchestration_home"]["path"] = str(self.directory)
        scope["execution_workspace"]["path"] = str(self.directory)
        self.journal.append(
            "run_started",
            {
                "change": "portable-graph",
                "run_id": "run-1",
                "coordinator_id": "coordinator-1",
                "coordinator_generation": 1,
                "workspace_scope": scope,
                "control_runtime": CONTROL_RUNTIME,
                "tasks": [task.to_dict() for task in checked_graph.tasks],
            },
            coordinator_generation=1,
        )

        with self.assertRaisesRegex(ValueError, "shell operator"):
            self.journal.import_checked_task(
                "ROOT-01",
                import_id="import-root-01",
                coordinator_generation=1,
                note="Reject shell composition.",
            )

        projection = self.journal.verify_projection()
        self.assertIsNone(projection["tasks"]["ROOT-01"]["grade"])
        self.assertIsNone(projection["tasks"]["ROOT-01"]["check"])


class CurrentProducerCompatibilityBehavior(unittest.TestCase):
    def test_keeps_validate_bootstrap_dispatch_check_and_cleanup_operational(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory)
            change = repository / "openspec" / "changes" / "producer-compat"
            change.mkdir(parents=True)
            checked_tasks = VALID_TASKS.replace("- [ ] ROOT-01", "- [x] ROOT-01").replace(
                "python3 -m unittest tests.test_domain",
                f'"{sys.executable}" -c "raise SystemExit(0)"',
            )
            (change / "proposal.md").write_text("# Proposal\n", encoding="utf-8")
            (change / "design.md").write_text("# Design\n", encoding="utf-8")
            (change / "tasks.md").write_text(checked_tasks, encoding="utf-8")
            parsed = graph_core.parse_task_graph(checked_tasks)
            transition = decide_process(
                repository,
                request="Exercise the current graph producers.",
                check_command=parsed.tasks[0].check,
                signals={
                    "known_scope": True,
                    "graph_requested": True,
                    "cohesion": "independent",
                    "independent_packets": [
                        {
                            "packet_id": task.id,
                            "paths": list(task.paths),
                            "check": {
                                "command": task.check,
                                "oracle": f"{task.id} check passes.",
                            },
                        }
                        for task in parsed.tasks
                    ],
                    "integrator": "coordinator-init",
                    "permission_observed": True,
                    "budget_limits": [
                        {
                            "resource": "workers",
                            "value": len(parsed.tasks),
                            "unit": "workers",
                            "rationale": "The fixture declares one limit per graph packet.",
                        }
                    ],
                    "cleanup_plan": "The producer verifies all graph cleanup.",
                },
            )
            (change / "process-decision.json").write_text(
                json.dumps(transition), encoding="utf-8"
            )
            subprocess.run(["git", "init", "-q", str(repository)], check=True)
            subprocess.run(
                ["git", "-C", str(repository), "config", "user.email", "test@example.com"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(repository), "config", "user.name", "Test"],
                check=True,
            )
            subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
            subprocess.run(
                ["git", "-C", str(repository), "commit", "-qm", "test fixture"],
                check=True,
            )

            script = Path(__file__).parents[1] / "scripts" / "agent_graph.py"

            def run(command: str, *arguments: str) -> dict:
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(script),
                        command,
                        "--repo",
                        str(repository),
                        "--json",
                        *arguments,
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                result = json.loads(completed.stdout)["result"]
                run_id = "run-init" if command == "init" else "run-1"
                state_path = (
                    repository
                    / "openspec"
                    / "runs"
                    / "producer-compat"
                    / run_id
                    / "state.json"
                )
                if state_path.is_file() and "state" not in result:
                    result["state"] = load_json(state_path)
                return result

            validated = run("validate", "--change", "producer-compat")
            initialized = run(
                "init",
                "--change",
                "producer-compat",
                "--run-id",
                "run-init",
                "--coordinator-id",
                "coordinator-init",
                "--driver",
                "host",
            )
            bootstrap = run(
                "bootstrap",
                "--change",
                "producer-compat",
                "--run-id",
                "run-1",
                "--bootstrap-id",
                "bootstrap-1",
                "--driver",
                "host",
            )
            Draft202012Validator(
                load_json(REFERENCES / "coordinator-capsule.schema.json"),
                registry=SchemaBehavior.registry(),
            ).validate(load_json(repository / bootstrap["capsule_path"]))
            run(
                "claim-coordinator",
                "--capsule",
                bootstrap["capsule_path"],
                "--coordinator-id",
                "coordinator-1",
            )
            dispatched = run(
                "dispatch",
                "--change",
                "producer-compat",
                "--run-id",
                "run-1",
                "--generation",
                "2",
                "--task",
                "ROOT-01",
                "--local",
            )
            run(
                "record-result",
                "--change",
                "producer-compat",
                "--run-id",
                "run-1",
                "--generation",
                "2",
                "--attempt",
                dispatched["attempt_id"],
                "--result-json",
                json.dumps(
                    {
                        "task_id": "ROOT-01",
                        "attempt_id": dispatched["attempt_id"],
                        "outcome": "reported",
                        "summary": "Reported the compatibility task.",
                        "files_changed": ["src/domain/model.py"],
                        "checks_run": ["python3 -m unittest tests.test_domain"],
                        "evidence_refs": [],
                        "questions": [],
                        "external_refs": {},
                    }
                ),
            )
            checked = run(
                "run-check",
                "--change",
                "producer-compat",
                "--run-id",
                "run-1",
                "--generation",
                "2",
                "--task",
                "ROOT-01",
            )
            run(
                "cleanup-register",
                "--change",
                "producer-compat",
                "--run-id",
                "run-1",
                "--generation",
                "2",
                "--cleanup-id",
                "cleanup-manual",
                "--kind",
                "other",
                "--target",
                "missing-target",
                "--owner",
                dispatched["attempt_id"],
            )
            finished = run(
                "cleanup-finish",
                "--change",
                "producer-compat",
                "--run-id",
                "run-1",
                "--generation",
                "2",
                "--cleanup-id",
                "cleanup-manual",
                "--receipt",
                "target-absent",
            )

            self.assertTrue(validated["tasks"][0]["checked"])
            self.assertIsNotNone(initialized["state"]["workspace_scope"])
            self.assertIsNone(bootstrap["state"]["tasks"]["ROOT-01"]["grade"])
            self.assertEqual(
                bootstrap["state"]["workspace_scope"],
                load_json(repository / bootstrap["capsule_path"])["workspace_scope"],
            )
            self.assertEqual(checked["check"]["status"], "passed")
            self.assertTrue(finished["finished"])
            state = load_json(
                repository
                / "openspec"
                / "runs"
                / "producer-compat"
                / "run-1"
                / "state.json"
            )
            Draft202012Validator(
                load_json(REFERENCES / "run-state.schema.json"),
                registry=SchemaBehavior.registry(),
            ).validate(state)


class SchemaBehavior(unittest.TestCase):
    SCHEMA_NAMES = (
            "run-state.schema.json",
            "worker-result.schema.json",
            "coordinator-capsule.schema.json",
            "control-runtime-ref.schema.json",
            "execution-profile.schema.json",
            "placement.schema.json",
            "context-capsule.schema.json",
            "agent-graph-view.schema.json",
            "run-progress-summary.schema.json",
            "maestro-mutation.schema.json",
            "delegation-intent.schema.json",
    )
    CANONICAL_SCHEMA_IDS = {
        "control-runtime-ref.schema.json": "https://github.com/badmuriss/my-llm-kit/schemas/control-runtime-ref.json",
        "placement.schema.json": "https://github.com/badmuriss/my-llm-kit/schemas/agent-graph-placement.json",
        "execution-profile.schema.json": "https://github.com/badmuriss/my-llm-kit/schemas/agent-graph-execution-profile.json",
        "context-capsule.schema.json": "https://github.com/badmuriss/my-llm-kit/schemas/agent-graph-context-capsule.json",
        "agent-graph-view.schema.json": "https://github.com/badmuriss/my-llm-kit/schemas/agent-graph-view-v1.json",
        "run-progress-summary.schema.json": "https://github.com/badmuriss/my-llm-kit/schemas/run-progress-summary-v1.json",
        "maestro-mutation.schema.json": "https://github.com/badmuriss/my-llm-kit/schemas/maestro-mutation-v1.json",
        "delegation-intent.schema.json": "https://github.com/badmuriss/my-llm-kit/schemas/delegation-intent-v1.json",
    }

    @classmethod
    def registry(cls) -> Registry:
        resources = []
        for name in cls.SCHEMA_NAMES:
            schema = load_json(REFERENCES / name)
            resources.append((schema["$id"], Resource.from_contents(schema)))
        return Registry().with_resources(resources)

    def test_keeps_all_declared_schemas_valid_draft_2020_12(self) -> None:
        for name in self.SCHEMA_NAMES:
            with self.subTest(schema=name):
                schema = load_json(REFERENCES / name)
                self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
                Draft202012Validator.check_schema(schema)

    def test_resolves_exact_absolute_schema_ids_without_relative_fallback(self) -> None:
        registry = self.registry()

        for name, schema_id in self.CANONICAL_SCHEMA_IDS.items():
            with self.subTest(schema=name):
                schema = load_json(REFERENCES / name)
                self.assertEqual(schema["$id"], schema_id)
                resource = registry.get(schema_id)
                self.assertIsNotNone(resource)
                self.assertEqual(resource.contents["$id"], schema_id)

        for name in self.SCHEMA_NAMES:
            schema = load_json(REFERENCES / name)
            for reference in self.schema_references(schema):
                self.assertTrue(
                    reference.startswith("#") or reference.startswith("https://"),
                    f"{name} contains a non-absolute external ref: {reference}",
                )

    @classmethod
    def schema_references(cls, value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "$ref":
                    yield item
                else:
                    yield from cls.schema_references(item)
        elif isinstance(value, list):
            for item in value:
                yield from cls.schema_references(item)

    def test_validates_all_protocol_and_placement_fixtures(self) -> None:
        registry = self.registry()
        cases = [
            ("placement.schema.json", WORKSPACE_SCOPES["folder_local"]),
            ("placement.schema.json", WORKSPACE_SCOPES["worktree_remote"]),
            ("execution-profile.schema.json", EXECUTION_PROFILES["current_folder"]),
            ("execution-profile.schema.json", EXECUTION_PROFILES["existing_remote_with_fallback"]),
            ("execution-profile.schema.json", EXECUTION_PROFILES["child_worktree"]),
            ("agent-graph-view.schema.json", load_json(FIXTURES / "agent-graph-view.json")),
            ("agent-graph-view.schema.json", load_json(FIXTURES / "agent-graph-view-delta.json")),
            ("maestro-mutation.schema.json", load_json(FIXTURES / "maestro-mutation.json")),
            ("delegation-intent.schema.json", load_json(FIXTURES / "delegation-intent.json")),
        ]

        for schema_name, fixture in cases:
            with self.subTest(schema=schema_name):
                Draft202012Validator(
                    load_json(REFERENCES / schema_name), registry=registry
                ).validate(fixture)


if __name__ == "__main__":
    unittest.main()
