import json
import hashlib
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
CLI = ROOT / "scripts" / "agent_graph.py"
sys.path.insert(0, str(CLI.parent))
import agent_graph as runtime  # noqa: E402
import validation  # noqa: E402


class CheckSingleflightBehavior(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repository = Path(self.temporary_directory.name)
        change = self.repository / "openspec/changes/singleflight"
        change.mkdir(parents=True)
        command = (
            f'"{sys.executable}" -c '
            '"from pathlib import Path; import time; '
            "Path('spawn-count').write_text(Path('spawn-count').read_text() + 'x' if Path('spawn-count').exists() else 'x'); "
            'time.sleep(0.3)"'
        )
        (change / "tasks.md").write_text(
            "# Tasks\n\n"
            "- [x] MLK-16 Preserve the checked predecessor order\n"
            "  Depends: []\n"
            "  Paths: [src/predecessor.py]\n"
            "  Mode: write\n"
            "  Isolation: auto\n"
            "  Acceptance: The checked predecessor is imported first.\n"
            f"  Check: {command}\n\n"
            "- [x] MLK-15 Require its checked predecessor\n"
            "  Depends: [MLK-16]\n"
            "  Paths: [src/dependent.py]\n"
            "  Mode: write\n"
            "  Isolation: auto\n"
            "  Acceptance: The dependent import has no side effects before readiness.\n"
            f"  Check: {command}\n\n"
            "- [x] CHECK-01 Execute one shared check\n"
            "  Depends: []\n"
            "  Paths: [src/check.py]\n"
            "  Mode: write\n"
            "  Isolation: auto\n"
            "  Acceptance: The public check is shared.\n"
            f"  Check: {command}\n\n"
            "- [x] OTHER-02 Keep the graph contract independent\n"
            "  Depends: []\n"
            "  Paths: [src/other.py]\n"
            "  Mode: write\n"
            "  Isolation: auto\n"
            "  Acceptance: The graph has a second independent packet.\n"
            f"  Check: {command}\n",
            encoding="utf-8",
        )
        for name in ("proposal.md", "design.md"):
            (change / name).write_text("# Singleflight\n", encoding="utf-8")
        source = self.repository / "src/check.py"
        source.parent.mkdir()
        source.write_text("initial\n", encoding="utf-8")
        (self.repository / ".gitignore").write_text("spawn-count\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(self.repository)], check=True)
        subprocess.run(["git", "-C", str(self.repository), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(self.repository), "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "-C", str(self.repository), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.repository), "commit", "-qm", "fixture"], check=True)
        self._write_process_decision(command)
        bootstrap = self._result(self._cli("bootstrap", "--change", "singleflight", "--run-id", "run-1", "--bootstrap-id", "bootstrap-1", "--driver", "host"))
        self._result(self._cli("claim-coordinator", "--capsule", bootstrap["capsule_path"], "--coordinator-id", "coordinator-1"))
        ready = self._result(self._cli("ready", "--change", "singleflight", "--run-id", "run-1"))
        self.assertEqual([task["id"] for task in ready["ready"]], ["MLK-16"])
        dispatched = self._result(self._cli("dispatch", "--change", "singleflight", "--run-id", "run-1", "--generation", "2", "--task", "CHECK-01", "--local"))
        attempt_id = dispatched["attempt_id"]
        report = {
            "task_id": "CHECK-01", "attempt_id": attempt_id, "outcome": "reported",
            "summary": "The worker is ready for its public check.", "files_changed": ["src/check.py"],
            "checks_run": ["python3 -m unittest"], "evidence_refs": [], "questions": [], "external_refs": {},
        }
        self._result(self._cli("record-result", "--change", "singleflight", "--run-id", "run-1", "--generation", "2", "--attempt", attempt_id, "--result-json", json.dumps(report)))

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _cli(self, command: str, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(CLI), command, "--repo", str(self.repository), "--json", *arguments], capture_output=True, text=True)

    def _result(self, completed: subprocess.CompletedProcess[str]) -> dict:
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)["result"]

    def _write_process_decision(self, command: str) -> None:
        graph = runtime.parse_task_graph(self.repository / "openspec/changes/singleflight/tasks.md")
        decision = runtime.decide_process(
            self.repository,
            request="Execute the single-flight check fixture.",
            check_command=command,
            signals={
                "known_scope": True,
                "graph_requested": True,
                "cohesion": "independent",
                "independent_packets": [
                    {"packet_id": "MLK-16", "paths": ["src/predecessor.py"], "check": {"command": command, "oracle": "The predecessor check passes."}},
                    {"packet_id": "MLK-15", "paths": ["src/dependent.py"], "check": {"command": command, "oracle": "The dependent check passes after MLK-16."}},
                    {"packet_id": "CHECK-01", "paths": ["src/check.py"], "check": {"command": command, "oracle": "The check passes."}},
                    {"packet_id": "OTHER-02", "paths": ["src/other.py"], "check": {"command": command, "oracle": "The second check passes."}},
                ],
                "integrator": "coordinator-1",
                "permission_observed": True,
                "budget_limits": [{"resource": "workers", "value": 1, "unit": "workers", "rationale": "One fixture worker."}],
                "cleanup_plan": "The fixture owns and cleans its local check process.",
            },
        )
        self.assertEqual(graph.tasks[0].check, command)
        (self.repository / "openspec/changes/singleflight/process-decision.json").write_text(json.dumps(decision), encoding="utf-8")

    def test_shares_one_public_check_execution_between_processes(self) -> None:
        arguments = [sys.executable, str(CLI), "run-check", "--repo", str(self.repository), "--json", "--change", "singleflight", "--run-id", "run-1", "--generation", "2", "--task", "CHECK-01"]
        first = subprocess.Popen(arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        second = subprocess.Popen(arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        _, first_error = first.communicate(timeout=20)
        _, second_error = second.communicate(timeout=20)
        self.assertEqual(first.returncode, 0, first_error)
        self.assertEqual(second.returncode, 0, second_error)
        self.assertEqual((self.repository / "spawn-count").read_text(encoding="utf-8"), "x")
        state = json.loads((self.repository / "openspec/runs/singleflight/run-1/state.json").read_text(encoding="utf-8"))
        self.assertEqual(len(state["check_executions"]), 1)
        execution = next(iter(state["check_executions"].values()))
        self.assertEqual(execution["lifecycle"], "passed")
        self.assertEqual(execution["consumer_refs"], ["attempt:CHECK-01:attempt-check-01-001"])
        check = state["tasks"]["CHECK-01"]["check"]
        self.assertEqual(check["execution_id"], execution["execution_id"])
        self.assertEqual(check["status"], "passed")
        events = [json.loads(line) for line in (self.repository / "openspec/runs/singleflight/run-1/events.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(sum(event["type"] == "check_recorded" for event in events), 1)

    def test_fences_an_independent_write_while_the_explicit_write_is_active(self) -> None:
        blocked = self._cli(
            "dispatch", "--change", "singleflight", "--run-id", "run-1",
            "--generation", "2", "--task", "OTHER-02", "--local",
        )
        self.assertNotEqual(blocked.returncode, 0)
        self.assertEqual(json.loads(blocked.stderr)["error"]["code"], "task_not_ready")

    def test_publishes_running_owner_and_cleanup_before_the_owner_waits(self) -> None:
        arguments = [sys.executable, str(CLI), "run-check", "--repo", str(self.repository), "--json", "--change", "singleflight", "--run-id", "run-1", "--generation", "2", "--task", "CHECK-01"]
        check = subprocess.Popen(arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        deadline = time.monotonic() + 10
        state_path = self.repository / "openspec/runs/singleflight/run-1/state.json"
        running = None
        while time.monotonic() < deadline:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            executions = list(state["check_executions"].values())
            if executions and executions[0]["lifecycle"] == "running":
                running = executions[0]
                break
            time.sleep(0.01)
        self.assertIsNotNone(running, "Check never published its running ownership")
        assert running is not None
        self.assertIsInstance(running["process_root"], int)
        self.assertEqual(running["process_group"], running["process_root"])
        self.assertTrue(running["process_start_identity"])
        self.assertEqual(running["cleanup_authority"], "process_group")
        self.assertTrue(running["cleanup_id"])
        cleanup = json.loads((self.repository / running["cleanup_ref"]).read_text(encoding="utf-8"))
        self.assertEqual(cleanup["status"], "registered")
        _, error = check.communicate(timeout=20)
        self.assertEqual(check.returncode, 0, error)

    def test_shares_one_checked_import_between_processes(self) -> None:
        arguments = [
            sys.executable, str(CLI), "import-checked-task", "--repo", str(self.repository), "--json",
            "--change", "singleflight", "--run-id", "run-1", "--generation", "2",
        ]
        first = subprocess.Popen(
            [*arguments, "--task", "CHECK-01", "--import-id", "import-1", "--note", "First import."],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        second = subprocess.Popen(
            [*arguments, "--task", "OTHER-02", "--import-id", "import-2", "--note", "Second import."],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        _, first_error = first.communicate(timeout=20)
        _, second_error = second.communicate(timeout=20)
        self.assertEqual(first.returncode, 0, first_error)
        self.assertEqual(second.returncode, 0, second_error)
        self.assertEqual((self.repository / "spawn-count").read_text(encoding="utf-8"), "x")
        state = json.loads((self.repository / "openspec/runs/singleflight/run-1/state.json").read_text(encoding="utf-8"))
        execution = next(iter(state["check_executions"].values()))
        self.assertEqual(execution["lifecycle"], "passed")
        self.assertEqual(
            set(execution["consumer_refs"]),
            {"import:CHECK-01:import-1", "import:OTHER-02:import-2"},
        )

    def test_does_not_join_a_running_check_after_source_mutation(self) -> None:
        arguments = [sys.executable, str(CLI), "run-check", "--repo", str(self.repository), "--json", "--change", "singleflight", "--run-id", "run-1", "--generation", "2", "--task", "CHECK-01"]
        first = subprocess.Popen(arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        deadline = time.monotonic() + 10
        while not (self.repository / "spawn-count").exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue((self.repository / "spawn-count").exists(), "first Check did not start")
        source = self.repository / "src" / "check.py"
        source.write_text("changed\n", encoding="utf-8")
        second = subprocess.Popen(arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        _, first_error = first.communicate(timeout=20)
        _, second_error = second.communicate(timeout=20)
        self.assertEqual(first.returncode, 0, first_error)
        self.assertEqual(second.returncode, 0, second_error)
        self.assertEqual((self.repository / "spawn-count").read_text(encoding="utf-8"), "xx")
        state = json.loads((self.repository / "openspec/runs/singleflight/run-1/state.json").read_text(encoding="utf-8"))
        self.assertEqual(len(state["check_executions"]), 2)

    def test_does_not_join_a_running_check_after_untracked_source_mutation(self) -> None:
        arguments = [sys.executable, str(CLI), "run-check", "--repo", str(self.repository), "--json", "--change", "singleflight", "--run-id", "run-1", "--generation", "2", "--task", "CHECK-01"]
        first = subprocess.Popen(arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        deadline = time.monotonic() + 10
        while not (self.repository / "spawn-count").exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue((self.repository / "spawn-count").exists(), "first Check did not start")
        (self.repository / "src/untracked.py").write_text("untracked\n", encoding="utf-8")
        second = subprocess.Popen(arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        _, first_error = first.communicate(timeout=20)
        _, second_error = second.communicate(timeout=20)
        self.assertEqual(first.returncode, 0, first_error)
        self.assertEqual(second.returncode, 0, second_error)
        self.assertEqual((self.repository / "spawn-count").read_text(encoding="utf-8"), "xx")
        state = json.loads((self.repository / "openspec/runs/singleflight/run-1/state.json").read_text(encoding="utf-8"))
        executions = list(state["check_executions"].values())
        self.assertEqual(len(executions), 2)
        self.assertEqual(len({execution["source_snapshot_digest"] for execution in executions}), 2)

    def test_rejects_the_frozen_mlk_15_import_before_mlk_16_without_side_effects(self) -> None:
        rejected = self._cli(
            "import-checked-task", "--change", "singleflight", "--run-id", "run-1",
            "--generation", "2", "--task", "MLK-15", "--import-id", "import-mlk-15",
            "--note", "MLK-15 waits for its frozen predecessor.",
        )
        self.assertNotEqual(rejected.returncode, 0)
        self.assertEqual(json.loads(rejected.stderr)["error"]["code"], "task_not_ready")
        self.assertFalse((self.repository / "spawn-count").exists())
        state = json.loads((self.repository / "openspec/runs/singleflight/run-1/state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["check_executions"], {})

        predecessor = self._result(self._cli(
            "import-checked-task", "--change", "singleflight", "--run-id", "run-1",
            "--generation", "2", "--task", "MLK-16", "--import-id", "import-mlk-16",
            "--note", "MLK-16 is imported before MLK-15.",
        ))
        self.assertEqual(predecessor["grade"], "pass")

    def test_replays_a_completed_public_check_without_a_second_child(self) -> None:
        first = self._result(self._cli(
            "run-check", "--change", "singleflight", "--run-id", "run-1",
            "--generation", "2", "--task", "CHECK-01",
        ))
        replay = self._result(self._cli(
            "run-check", "--change", "singleflight", "--run-id", "run-1",
            "--generation", "2", "--task", "CHECK-01",
        ))
        self.assertTrue(replay["idempotent"])
        self.assertEqual(replay["check"]["execution_id"], first["check"]["execution_id"])
        self.assertEqual((self.repository / "spawn-count").read_text(encoding="utf-8"), "x")

    def test_keeps_policy_executions_distinct_without_rewriting_the_first_artifact(self) -> None:
        first = self._result(self._cli(
            "import-checked-task", "--change", "singleflight", "--run-id", "run-1",
            "--generation", "2", "--task", "CHECK-01", "--import-id", "import-1",
            "--note", "The first policy is immutable.", "--timeout", "2", "--output-cap", "128",
        ))
        first_artifact = self.repository / first["check"]["artifact"]
        first_artifact_bytes = first_artifact.read_bytes()
        first_artifact_digest = hashlib.sha256(first_artifact_bytes).hexdigest()
        second = self._result(self._cli(
            "import-checked-task", "--change", "singleflight", "--run-id", "run-1",
            "--generation", "2", "--task", "OTHER-02", "--import-id", "import-2",
            "--note", "The changed policy receives a new execution.", "--timeout", "3", "--output-cap", "128",
        ))
        first_evidence = json.loads((self.repository / first["check"]["artifact"]).read_text(encoding="utf-8"))
        second_evidence = json.loads((self.repository / second["check"]["artifact"]).read_text(encoding="utf-8"))
        self.assertNotEqual(first_evidence["execution_id"], second_evidence["execution_id"])
        self.assertNotEqual(first_evidence["execution_policy_digest"], second_evidence["execution_policy_digest"])
        self.assertEqual(first_artifact.read_bytes(), first_artifact_bytes)
        self.assertEqual(hashlib.sha256(first_artifact.read_bytes()).hexdigest(), first_artifact_digest)
        self.assertEqual((self.repository / "spawn-count").read_text(encoding="utf-8"), "xx")

    def test_excludes_current_run_artifacts_from_an_identical_completed_import(self) -> None:
        first = self._result(self._cli(
            "import-checked-task", "--change", "singleflight", "--run-id", "run-1",
            "--generation", "2", "--task", "CHECK-01", "--import-id", "import-1",
            "--note", "The first import creates only run-owned artifacts.",
        ))
        second = self._result(self._cli(
            "import-checked-task", "--change", "singleflight", "--run-id", "run-1",
            "--generation", "2", "--task", "OTHER-02", "--import-id", "import-2",
            "--note", "The second import reuses the immutable execution.",
        ))
        first_evidence = json.loads((self.repository / first["check"]["artifact"]).read_text(encoding="utf-8"))
        second_evidence = json.loads((self.repository / second["check"]["artifact"]).read_text(encoding="utf-8"))
        self.assertEqual(first_evidence["execution_id"], second_evidence["execution_id"])
        self.assertEqual((self.repository / "spawn-count").read_text(encoding="utf-8"), "x")

    def test_rejects_a_stale_generation_before_starting_a_checked_import(self) -> None:
        rejected = self._cli(
            "import-checked-task", "--change", "singleflight", "--run-id", "run-1",
            "--generation", "1", "--task", "CHECK-01", "--import-id", "import-1",
            "--note", "A stale generation cannot create an execution.",
        )
        self.assertNotEqual(rejected.returncode, 0)
        self.assertEqual(json.loads(rejected.stderr)["error"]["code"], "stale_coordinator")
        self.assertFalse((self.repository / "spawn-count").exists())

    def test_reconciles_a_timeout_before_a_higher_timeout_retry(self) -> None:
        timed_out = self._cli(
            "run-check", "--change", "singleflight", "--run-id", "run-1", "--generation", "2",
            "--task", "CHECK-01", "--timeout", "0.05",
        )
        self.assertNotEqual(timed_out.returncode, 0)
        self.assertEqual(json.loads(timed_out.stderr)["error"]["code"], "check_failed")
        state = json.loads(
            (self.repository / "openspec/runs/singleflight/run-1/state.json").read_text(encoding="utf-8")
        )
        execution = next(iter(state["check_executions"].values()))
        self.assertEqual(execution["lifecycle"], "failed_verified")
        record = json.loads((self.repository / execution["artifact_ref"]).read_text(encoding="utf-8"))
        self.assertTrue(record["timed_out"])
        cleanup = json.loads((self.repository / execution["cleanup_ref"]).read_text(encoding="utf-8"))
        self.assertEqual(cleanup["status"], "verified_absent")

        retried = self._result(self._cli(
            "run-check", "--change", "singleflight", "--run-id", "run-1", "--generation", "2",
            "--task", "CHECK-01", "--timeout", "2",
        ))
        self.assertEqual(retried["check"]["status"], "passed")
        self.assertEqual((self.repository / "spawn-count").read_text(encoding="utf-8"), "xx")

    def test_imports_the_first_checked_task_from_policy_addressed_evidence(self) -> None:
        imported = self._result(self._cli(
            "import-checked-task",
            "--change", "singleflight",
            "--run-id", "run-1",
            "--generation", "2",
            "--task", "CHECK-01",
            "--import-id", "import-1",
            "--note", "Imported from the first CheckExecution v1 artifact.",
        ))
        self.assertEqual(imported["grade"], "pass")
        artifact = self.repository / imported["check"]["artifact"]
        evidence = json.loads(artifact.read_text(encoding="utf-8"))
        self.assertEqual(evidence["schema_version"], 1)
        self.assertIn("execution_policy_digest", evidence)
        self.assertIn("timeout_seconds", evidence)
        self.assertIn("output_cap_bytes", evidence)

        evidence["output_cap_bytes"] += 1
        artifact.write_text(json.dumps(evidence), encoding="utf-8")
        rejected = self._cli(
            "import-checked-task",
            "--change", "singleflight",
            "--run-id", "run-1",
            "--generation", "2",
            "--task", "CHECK-01",
            "--import-id", "import-1",
            "--note", "Imported from the first CheckExecution v1 artifact.",
        )
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("policy digest diverges", rejected.stderr)


if __name__ == "__main__":
    unittest.main()
