"""Behavioral contract for adaptive single-writer execution sessions."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from adaptive_intake import decide_process  # noqa: E402
import agent_graph as runtime  # noqa: E402
from drivers.orca import OrcaDriver  # noqa: E402
from graph_core import EventJournal, apply_event, empty_projection, parse_task_graph, ready_tasks, validate_finding, task_is_dispatchable  # noqa: E402


ORCA_TESTS = Path(__file__).with_name("test_orca_driver.py")
ORCA_TEST_SPEC = importlib.util.spec_from_file_location("orca_driver_behavior", ORCA_TESTS)
assert ORCA_TEST_SPEC and ORCA_TEST_SPEC.loader
orca_driver_behavior = importlib.util.module_from_spec(ORCA_TEST_SPEC)
sys.modules[ORCA_TEST_SPEC.name] = orca_driver_behavior
ORCA_TEST_SPEC.loader.exec_module(orca_driver_behavior)


def check(command: str) -> dict[str, str]:
    return {"command": command, "oracle": "The exact bounded command passes."}


class AdaptiveExecutionBehavior(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repository = Path(self.temporary_directory.name)
        (self.repository / ".git").mkdir()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_validates_the_five_finding_classes_and_blocking_evidence(self) -> None:
        base = {
            "schema_version": 1, "finding_id": "finding-1", "classification": "advisory",
            "task_id": "ROOT-01", "attempt_id": "attempt-1", "acceptance_reference": "task#/acceptance",
            "evidence_ref": "file:findings/finding-1.json",
            "affected": [{"file": "src/root.py", "identity": "root"}],
            "reproduction": {"steps": ["run check"], "observed": "observed", "expected": "expected"},
            "smallest_repair_hypothesis": "smallest repair", "why_current_check_does_not_detect": "check scope",
        }
        for classification in ("acceptance_violation", "reproducible_regression", "security_or_integrity", "hardening", "advisory"):
            candidate = {**base, "classification": classification}
            self.assertEqual(validate_finding(candidate)["classification"], classification)
        with self.assertRaises(Exception):
            validate_finding({key: value for key, value in base.items() if key != "evidence_ref"})

    def test_reads_orca_completion_evidence_from_one_payload(self) -> None:
        task = parse_task_graph("""# Tasks

- [ ] ROOT-01 Payload evidence
  Depends: []
  Paths: [src/root.py]
  Mode: write
  Isolation: auto
  Acceptance: The worker result is internally consistent.
  Check: python3 -c pass
""").tasks[0]
        candidate = runtime._provider_worker_result_candidate(
            {
                "messageId": "message-r42",
                "filesModified": ["src/envelope.py"],
                "checksRun": ["envelope check"],
                "payload": json.dumps(
                    {
                        "taskId": "orca-root",
                        "dispatchId": "dispatch-r42",
                        "outcome": "succeeded",
                        "filesModified": ["src/root.py"],
                        "checksRun": ["payload check"],
                    }
                ),
            },
            task,
            "attempt-r42",
            delivery_id="delivery-r42",
        )

        self.assertEqual(candidate["files_changed"], ["src/root.py"])
        self.assertEqual(candidate["checks_run"], ["payload check"])
        self.assertEqual(
            runtime._orca_quarantine_idempotency_key(
                "attempt-r42", "message-r42", "delivery-r42"
            ),
            runtime._orca_quarantine_idempotency_key(
                "attempt-r42", candidate["external_refs"]["message_id"], candidate["external_refs"]["delivery_id"]
            ),
        )

    def test_fences_dispatch_after_two_technical_attempts_until_explicit_amendment(self) -> None:
        graph = parse_task_graph("""# Tasks\n\n- [ ] ROOT-01 Root\n  Depends: []\n  Paths: [src/root.py]\n  Mode: write\n  Isolation: auto\n  Acceptance: Root is complete.\n  Check: python3 -c pass\n""")
        state = apply_event(empty_projection(), {"type": "run_started", "sequence": 1, "data": {"change": "x", "run_id": "r", "coordinator_id": "c", "coordinator_generation": 1, "tasks": [task.to_dict() for task in graph.tasks]}})
        state["tasks"]["ROOT-01"]["attempt_ids"] = ["attempt-1", "attempt-2"]
        state["attempts"] = {
            "attempt-1": {"task_id": "ROOT-01", "status": "audit-rejected", "report": {}},
            "attempt-2": {"task_id": "ROOT-01", "status": "reported", "report": {}},
        }
        self.assertFalse(task_is_dispatchable(graph, state, graph.tasks[0]))
        state["tasks"]["ROOT-01"]["coordinator_decision"] = {"action": "amend_acceptance"}
        self.assertTrue(task_is_dispatchable(graph, state, graph.tasks[0]))
        state["tasks"]["ROOT-01"]["attempt_ids"].append("attempt-3")
        state["attempts"]["attempt-3"] = {"task_id": "ROOT-01", "status": "reported", "report": {}}
        state["tasks"]["ROOT-01"]["decision_consumed"] = True
        self.assertFalse(task_is_dispatchable(graph, state, graph.tasks[0]))

    def test_excludes_pre_resource_start_failure_from_technical_budget(self) -> None:
        graph = parse_task_graph("""# Tasks\n\n- [ ] ROOT-01 Root\n  Depends: []\n  Paths: [src/root.py]\n  Mode: write\n  Isolation: auto\n  Acceptance: Root is complete.\n  Check: python3 -c pass\n""")
        state = apply_event(empty_projection(), {"type": "run_started", "sequence": 1, "data": {"change": "x", "run_id": "r", "coordinator_id": "c", "coordinator_generation": 1, "tasks": [task.to_dict() for task in graph.tasks]}})
        state["tasks"]["ROOT-01"]["attempt_ids"] = ["attempt-operational", "attempt-technical"]
        state["attempts"] = {
            "attempt-operational": {"task_id": "ROOT-01", "status": "abandoned"},
            "attempt-technical": {"task_id": "ROOT-01", "status": "audit-rejected", "report": {}},
        }
        self.assertTrue(task_is_dispatchable(graph, state, graph.tasks[0]))

    def test_keeps_non_graph_intake_artifact_free(self) -> None:
        cases = (
            {"small_change": True, "known_scope": True, "cohesion": "cohesive"},
            {"small_change": False, "known_scope": True, "needs_iteration": True},
            {"known_scope": False, "architecture_uncertainty": "material"},
        )
        expected = ("direct", "verified_single", "light_spec")
        for signals, mode in zip(cases, expected):
            with self.subTest(mode=mode):
                result = decide_process(
                    self.repository,
                    request="Apply one bounded change.",
                    check_command="python3 -m compileall .",
                    signals=signals,
                )
                self.assertEqual(result["decision"]["mode"], mode)
                self.assertFalse(result["graph_artifacts_created"])
        self.assertFalse((self.repository / "openspec" / "runs").exists())

    def test_starts_a_valid_graph_with_one_writer_even_for_disjoint_writes(self) -> None:
        graph = parse_task_graph(
            """# Tasks

- [ ] FIRST-01 First packet
  Depends: []
  Paths: [src/first.py]
  Mode: write
  Isolation: auto
  Acceptance: First packet is complete.
  Check: python3 -m unittest tests.test_first

- [ ] SECOND-02 Second packet
  Depends: []
  Paths: [src/second.py]
  Mode: write
  Isolation: auto
  Acceptance: Second packet is complete.
  Check: python3 -m unittest tests.test_second
"""
        )
        decision = decide_process(
            self.repository,
            request="Implement two independent packets.",
            check_command="python3 -m unittest tests.test_integration",
            signals={
                "graph_requested": True,
                "cohesion": "independent",
                "independent_packets": [
                    {"packet_id": "first", "paths": ["src/first.py"], "check": check("python3 -m unittest tests.test_first")},
                    {"packet_id": "second", "paths": ["src/second.py"], "check": check("python3 -m unittest tests.test_second")},
                ],
                "integrator": "coordinator",
                "permission_observed": True,
                "budget_limits": [{"resource": "workers", "value": 2, "unit": "workers", "rationale": "Two isolated packets."}],
                "cleanup_plan": "The coordinator releases every owned resource.",
                "integration_check": check("python3 -m unittest tests.test_integration"),
            },
        )
        state = apply_event(
            empty_projection(),
            {
                "type": "run_started",
                "sequence": 1,
                "data": {
                    "change": "adaptive", "run_id": "run-1", "coordinator_id": "coordinator-1",
                    "coordinator_generation": 1, "process_decision": decision["decision"],
                    "graph_contract": decision["graph_contract"], "tasks": [task.to_dict() for task in graph.tasks],
                },
            },
        )

        self.assertEqual(state["execution_mode"], "single_writer")
        self.assertEqual([task.id for task in ready_tasks(graph, state)], ["FIRST-01"])
        self.assertEqual(decision["graph_contract"]["integration_check"]["command"], "python3 -m unittest tests.test_integration")

    def test_records_three_serial_task_attempts_checks_grades_and_cleanups_separately(self) -> None:
        graph = parse_task_graph(
            """# Tasks

- [ ] FIRST-01 First serial packet
  Depends: []
  Paths: [src/first.py]
  Mode: write
  Isolation: auto
  Acceptance: First packet is complete.
  Check: python3 -m unittest tests.test_first

- [ ] SECOND-02 Second serial packet
  Depends: [FIRST-01]
  Paths: [src/second.py]
  Mode: write
  Isolation: auto
  Acceptance: Second packet is complete.
  Check: python3 -m unittest tests.test_second

- [ ] THIRD-03 Third serial packet
  Depends: [SECOND-02]
  Paths: [src/third.py]
  Mode: write
  Isolation: auto
  Acceptance: Third packet is complete.
  Check: python3 -m unittest tests.test_third
"""
        )
        fixtures = Path(__file__).parents[1] / "fixtures" / "maestro-protocol-v1"
        workspace_scope = json.loads((fixtures / "workspace-scopes.json").read_text())["folder_local"]
        workspace_scope.update(run_id="run-serial", coordinator_generation=1)
        execution_profile = json.loads((fixtures / "execution-profiles.json").read_text())["current_folder"]
        journal = EventJournal(self.repository / "events.jsonl")
        journal.append(
            "run_started",
            {
                "change": "serial-session",
                "run_id": "run-serial",
                "coordinator_id": "coordinator-1",
                "coordinator_generation": 1,
                "workspace_scope": workspace_scope,
                "tasks": [task.to_dict() for task in graph.tasks],
            },
            coordinator_generation=1,
        )

        for index, task in enumerate(graph.tasks, start=1):
            attempt_id = f"attempt-{index}"
            terminal = "term-one"
            attempt = {
                "task_id": task.id,
                "attempt_id": attempt_id,
                "driver": "orca",
                "workspace_scope": workspace_scope,
                "execution_profile": copy.deepcopy(execution_profile),
                "external_refs": {
                    "terminal": terminal,
                    "capsule": "full-initial" if index == 1 else "incremental-handoff",
                },
            }
            journal.append("attempt_reserved", attempt, coordinator_generation=1)
            projection = journal.verify_projection()
            attempt["effective_scope"] = projection["attempts"][attempt_id]["effective_scope"]
            journal.append(
                "attempt_scope_frozen",
                {"attempt_id": attempt_id, "effective_scope": attempt["effective_scope"]},
                coordinator_generation=1,
            )
            journal.append("attempt_started", attempt, coordinator_generation=1)
            journal.append(
                "worker_reported",
                {"task_id": task.id, "attempt_id": attempt_id, "effective_scope": attempt["effective_scope"]},
                coordinator_generation=1,
            )
            journal.append(
                "check_recorded",
                {
                    "task_id": task.id,
                    "attempt_id": attempt_id,
                    "command": task.check,
                    "status": "passed",
                    "exit_code": 0,
                    "duration_ms": 1,
                    "attempts": 1,
                    "total_duration_ms": 1,
                    "artifact": f"artifacts/checks/{task.id}.json",
                },
                coordinator_generation=1,
            )
            cleanup_id = f"cleanup-{attempt_id}"
            journal.append(
                "cleanup_registered",
                {
                    "cleanup_id": cleanup_id,
                    "kind": "other",
                    "target": f"dispatch-{index}",
                    "owner": attempt_id,
                },
                coordinator_generation=1,
            )
            journal.append(
                "cleanup_finished",
                {"cleanup_id": cleanup_id, "receipt": {"state": "already_absent"}},
                coordinator_generation=1,
            )
            journal.append(
                "task_graded",
                {
                    "task_id": task.id,
                    "grade": "pass",
                    "note": "The serial task completed with its own evidence.",
                    "evidence_refs": [f"file:artifacts/checks/{task.id}.json"],
                },
                coordinator_generation=1,
            )

        projection = journal.verify_projection()
        self.assertEqual(set(projection["attempts"]), {"attempt-1", "attempt-2", "attempt-3"})
        self.assertEqual(
            [projection["attempts"][f"attempt-{index}"]["external_refs"]["terminal"] for index in range(1, 4)],
            ["term-one", "term-one", "term-one"],
        )
        self.assertEqual(projection["attempts"]["attempt-1"]["external_refs"]["capsule"], "full-initial")
        self.assertEqual(
            [projection["attempts"][f"attempt-{index}"]["check"]["attempt_id"] for index in range(1, 4)],
            ["attempt-1", "attempt-2", "attempt-3"],
        )
        self.assertEqual([projection["tasks"][task.id]["grade"] for task in graph.tasks], ["pass", "pass", "pass"])
        self.assertEqual(
            {cleanup["owner"] for cleanup in projection["cleanup"].values()},
            {"attempt-1", "attempt-2", "attempt-3"},
        )

    def test_reuses_one_terminal_only_after_exact_orca_readiness(self) -> None:
        fake = orca_driver_behavior.FakeOrca(self.repository, supervised_error="selector_not_found")
        fake.terminal_lease_capable = False
        driver = OrcaDriver(self.repository, runner=fake, environment={"ORCA_CLI_COMMAND": "fake-orca"})
        driver.detect()
        driver.start_run(
            "Probe",
            [
                {"id": "ROOT-01", "depends": [], "capsule": "full initial capsule"},
                {"id": "NEXT-02", "depends": ["ROOT-01"], "capsule": "second"},
                {"id": "LAST-03", "depends": ["NEXT-02"], "capsule": "third"},
            ],
        )
        first = driver.start_attempt(orca_driver_behavior.OrcaDriverBehavior.attempt(self, fake))
        fake.dynamic_dispatch = True
        second_attempt = orca_driver_behavior.OrcaDriverBehavior.attempt(self, fake)
        second_attempt.update(
            {
                "task_id": "NEXT-02", "attempt_id": "attempt-2",
                "session_terminal": orca_driver_behavior.active_session_terminal(first.external_refs, "tracked-terminal"),
                "session_handoff": orca_driver_behavior.session_handoff("NEXT-02"),
            }
        )

        second = driver.start_attempt(second_attempt)
        third_attempt = orca_driver_behavior.OrcaDriverBehavior.attempt(self, fake)
        third_attempt.update(
            {
                "task_id": "LAST-03", "attempt_id": "attempt-3",
                "session_terminal": orca_driver_behavior.active_session_terminal(second.external_refs, "tracked-terminal"),
                "session_handoff": orca_driver_behavior.session_handoff("LAST-03"),
            }
        )
        third = driver.start_attempt(third_attempt)

        self.assertTrue(second.external_refs["session_reused"])
        self.assertEqual(second.external_refs["terminal"]["handle"], first.external_refs["terminal"]["handle"])
        self.assertEqual(third.external_refs["terminal"]["handle"], first.external_refs["terminal"]["handle"])
        self.assertEqual(len([call for call in fake.calls if call[:2] == ["terminal", "create"]]), 1)
        worker_starts = [call for call in fake.calls if call[:2] == ["orchestration", "worker-start"]]
        self.assertEqual(len(worker_starts), 1)
        dispatches = [call for call in fake.calls if call[:2] == ["orchestration", "dispatch"]]
        self.assertEqual(len(dispatches), 3)
        self.assertEqual([call[call.index("--task") + 1] for call in dispatches], ["task-1", "task-2", "task-3"])
        task_specs = [call[call.index("--spec") + 1] for call in fake.calls if call[:2] == ["orchestration", "task-create"]]
        self.assertEqual(task_specs[0], "full initial capsule")
        ready_call = [call for call in fake.calls if call[:2] == ["orchestration", "task-update"]][-1]
        self.assertEqual(ready_call[ready_call.index("--id") + 1], "task-3")
        self.assertEqual(ready_call[ready_call.index("--status") + 1], "ready")
        delivered_handoffs = [
            call[call.index("--text") + 1]
            for call in fake.calls
            if call[:2] == ["terminal", "send"]
        ]
        self.assertEqual(len(delivered_handoffs), 2)
        self.assertTrue(all("full initial capsule" not in handoff for handoff in delivered_handoffs))
        self.assertTrue(all("transcript" not in handoff for handoff in delivered_handoffs))
        self.assertTrue(all("--lease-input" not in call for call in fake.calls if call[:2] == ["terminal", "send"]))

        def release_attempt(task_id: str, attempt_id: str, refs: dict) -> dict:
            return {
                "task_id": task_id,
                "attempt_id": attempt_id,
                "tier": "tracked-terminal",
                "dispatch_id": refs["dispatch_id"],
                "external_task_id": refs["task_id"],
                "run_id": refs["run_id"],
                "execution_profile": refs["execution_profile"],
                "workspace_scope": refs["workspace_scope"],
                "external_refs": refs,
            }

        newest = driver.release(release_attempt("LAST-03", "attempt-3", third.external_refs))
        middle = driver.release(release_attempt("NEXT-02", "attempt-2", second.external_refs))
        oldest = driver.release(release_attempt("ROOT-01", "attempt-1", first.external_refs))

        self.assertEqual(newest.status, "released")
        self.assertTrue(middle.external_refs["prior_cleanup"])
        self.assertTrue(oldest.external_refs["prior_cleanup"])
        self.assertEqual(len([call for call in fake.calls if call[:2] == ["terminal", "close"]]), 1)

    def test_reuses_one_provider_owned_terminal_across_three_supervised_tasks(self) -> None:
        fake = orca_driver_behavior.FakeOrca(self.repository)
        driver = OrcaDriver(self.repository, runner=fake, environment={"ORCA_CLI_COMMAND": "fake-orca"})
        driver.detect()
        driver.start_run(
            "Probe",
            [
                {"id": "ROOT-01", "depends": [], "capsule": "full initial capsule"},
                {"id": "NEXT-02", "depends": ["ROOT-01"], "capsule": "second"},
                {"id": "LAST-03", "depends": ["NEXT-02"], "capsule": "third"},
            ],
        )
        first = driver.start_attempt(orca_driver_behavior.OrcaDriverBehavior.attempt(self, fake))
        fake.dynamic_dispatch = True

        def reuse_attempt(task_id: str, attempt_id: str, previous: object) -> dict:
            assert hasattr(previous, "external_refs")
            refs = previous.external_refs
            candidate = orca_driver_behavior.OrcaDriverBehavior.attempt(self, fake)
            candidate.update(
                {
                    "task_id": task_id,
                    "attempt_id": attempt_id,
                    "session_terminal": orca_driver_behavior.active_session_terminal(refs, "supervised"),
                    "session_handoff": orca_driver_behavior.session_handoff(task_id),
                }
            )
            return candidate

        second = driver.start_attempt(reuse_attempt("NEXT-02", "attempt-2", first))
        third = driver.start_attempt(reuse_attempt("LAST-03", "attempt-3", second))

        refs = (first.external_refs, second.external_refs, third.external_refs)
        self.assertTrue(all(item["tier"] == "supervised" for item in refs))
        self.assertTrue(all("terminal" not in item for item in refs))
        self.assertEqual(
            {item["reusable_session_terminal"]["handle"] for item in refs},
            {"term-new"},
        )
        worker_starts = [call for call in fake.calls if call[:2] == ["orchestration", "worker-start"]]
        self.assertEqual(len(worker_starts), 3)
        self.assertNotIn("--terminal", worker_starts[0])
        self.assertTrue(all("--terminal" in call for call in worker_starts[1:]))
        self.assertFalse(any(call[:2] == ["orchestration", "dispatch"] for call in fake.calls))
        self.assertEqual(len([call for call in fake.calls if call[:2] == ["terminal", "create"]]), 0)
        self.assertEqual(len([call for call in fake.calls if call[:2] == ["terminal", "send"]]), 2)

        for task_id, attempt_id, attempt_refs in (
            ("LAST-03", "attempt-3", third.external_refs),
            ("NEXT-02", "attempt-2", second.external_refs),
            ("ROOT-01", "attempt-1", first.external_refs),
        ):
            released = driver.release(
                {
                    "tier": "supervised",
                    "task_id": task_id,
                    "attempt_id": attempt_id,
                    "dispatch_id": attempt_refs["dispatch_id"],
                }
            )
            self.assertEqual(released.status, "released")
        self.assertEqual(len([call for call in fake.calls if call[:2] == ["orchestration", "worker-release"]]), 3)
        self.assertFalse(any(call[:2] == ["terminal", "close"] for call in fake.calls))


if __name__ == "__main__":
    unittest.main()
