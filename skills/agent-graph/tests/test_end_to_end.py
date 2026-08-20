import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


CLI = Path(__file__).parents[1] / "scripts" / "agent_graph.py"


class PortableHostExecutionBehavior(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repository = Path(self.temporary_directory.name)
        change = self.repository / "openspec" / "changes" / "portable"
        change.mkdir(parents=True)
        (change / "proposal.md").write_text("# Proposal\n", encoding="utf-8")
        (change / "design.md").write_text("# Design\n", encoding="utf-8")
        passing = f'"{sys.executable}" -c "raise SystemExit(0)"'
        failing = f'"{sys.executable}" -c "raise SystemExit(7)"'
        (change / "tasks.md").write_text(
            f'''# Tasks

- [ ] ROOT-01 Establish evidence
  Depends: []
  Paths: [src/root.py]
  Mode: write
  Isolation: auto
  Acceptance: The root result passes local evidence.
  Check: {passing}

- [ ] WAVE-02 Write the first independent scope
  Depends: [ROOT-01]
  Paths: [src/a/]
  Mode: write
  Isolation: auto
  Acceptance: The first scope passes.
  Check: {passing}

- [ ] WAVE-03 Write the second independent scope
  Depends: [ROOT-01]
  Paths: [src/b/]
  Mode: write
  Isolation: auto
  Acceptance: The second scope passes.
  Check: {passing}

- [ ] CONFLICT-04 Serialize an overlapping scope
  Depends: [ROOT-01]
  Paths: [src/a/nested.py]
  Mode: write
  Isolation: auto
  Acceptance: The overlap waits for its owner.
  Check: {passing}

- [ ] FAIL-05 Preserve failing evidence
  Depends: [ROOT-01]
  Paths: [src/fail.py]
  Mode: write
  Isolation: auto
  Acceptance: The failing executable is recorded without becoming pass.
  Check: {failing}
''',
            encoding="utf-8",
        )
        subprocess.run(["git", "init", "-q", str(self.repository)], check=True)
        subprocess.run(["git", "-C", str(self.repository), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(self.repository), "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "-C", str(self.repository), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.repository), "commit", "-qm", "fixture"], check=True)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def run_cli(self, command: str, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CLI), command, "--repo", str(self.repository), "--json", *arguments],
            check=False,
            capture_output=True,
            text=True,
        )

    def result(self, completed: subprocess.CompletedProcess[str]):
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)["result"]

    def run_args(self, generation: int = 2) -> tuple[str, ...]:
        return ("--change", "portable", "--run-id", "run-1", "--generation", str(generation))

    def dispatch_report_grade(self, task_id: str, changed_file: str, *, generation: int = 2) -> str:
        dispatched = self.result(
            self.run_cli("dispatch", *self.run_args(generation), "--task", task_id, "--local")
        )
        report = {
            "task_id": task_id,
            "attempt_id": dispatched["attempt_id"],
            "outcome": "reported",
            "summary": f"Reported {task_id} through the host contract.",
            "files_changed": [changed_file],
            "checks_run": [],
            "evidence_refs": [],
            "questions": [],
            "external_refs": {},
        }
        arguments = (*self.run_args(generation), "--attempt", dispatched["attempt_id"], "--result-json", json.dumps(report))
        first = self.result(self.run_cli("record-result", *arguments))
        repeated = self.result(self.run_cli("record-result", *arguments))
        self.assertFalse(first["idempotent"])
        self.assertTrue(repeated["idempotent"])
        checked = self.run_cli("run-check", *self.run_args(generation), "--task", task_id)
        if task_id == "FAIL-05":
            self.assertNotEqual(checked.returncode, 0)
            self.assertEqual(json.loads(checked.stderr)["error"]["code"], "check_failed")
            grade = "fail"
        else:
            self.result(checked)
            grade = "pass"
        self.result(
            self.run_cli(
                "grade", *self.run_args(generation), "--task", task_id, "--grade", grade,
                "--note", f"The recorded check produced grade {grade}.",
            )
        )
        return dispatched["attempt_id"]

    def test_executes_and_recovers_a_complete_host_graph_without_orca(self) -> None:
        bootstrap = self.result(
            self.run_cli(
                "bootstrap", "--change", "portable", "--run-id", "run-1",
                "--bootstrap-id", "bootstrap-1", "--driver", "host",
            )
        )
        self.assertIsNone(bootstrap["state"]["driver"])
        claimed = self.result(
            self.run_cli(
                "claim-coordinator", "--capsule", bootstrap["capsule_path"],
                "--coordinator-id", "coordinator-1",
            )
        )
        self.assertEqual(claimed["state"]["driver"], "host")

        self.dispatch_report_grade("ROOT-01", "src/root.py")
        ready = self.result(self.run_cli("ready", "--change", "portable", "--run-id", "run-1"))
        self.assertEqual([item["id"] for item in ready["ready"]], ["WAVE-02", "WAVE-03", "FAIL-05"])

        wave_a = self.result(self.run_cli("dispatch", *self.run_args(), "--task", "WAVE-02", "--local"))
        conflict = self.run_cli("dispatch", *self.run_args(), "--task", "CONFLICT-04", "--local")
        self.assertNotEqual(conflict.returncode, 0)
        self.assertEqual(json.loads(conflict.stderr)["error"]["code"], "task_not_ready")
        wave_b = self.result(self.run_cli("dispatch", *self.run_args(), "--task", "WAVE-03", "--local"))
        for task_id, attempt, changed in (
            ("WAVE-02", wave_a["attempt_id"], "src/a/one.py"),
            ("WAVE-03", wave_b["attempt_id"], "src/b/two.py"),
        ):
            report = {
                "task_id": task_id, "attempt_id": attempt, "outcome": "reported",
                "summary": f"Reported {task_id}.", "files_changed": [changed],
                "checks_run": [], "evidence_refs": [], "questions": [], "external_refs": {},
            }
            self.result(self.run_cli("record-result", *self.run_args(), "--attempt", attempt, "--result-json", json.dumps(report)))
            self.result(self.run_cli("run-check", *self.run_args(), "--task", task_id))
            self.result(self.run_cli("grade", *self.run_args(), "--task", task_id, "--grade", "pass", "--note", "The report and check passed."))

        self.dispatch_report_grade("CONFLICT-04", "src/a/nested.py")
        self.dispatch_report_grade("FAIL-05", "src/fail.py")

        cleanup_path = self.repository / "owned-temp"
        cleanup_path.mkdir()
        registered = self.result(
            self.run_cli(
                "cleanup-register", *self.run_args(), "--kind", "temp_path",
                "--target", str(cleanup_path), "--owner", "coordinator-1",
            )
        )
        cleanup_path.rmdir()
        self.result(
            self.run_cli(
                "cleanup-finish", *self.run_args(), "--cleanup-id", registered["cleanup_id"]
            )
        )

        resumed = self.result(self.run_cli("resume", *self.run_args()))
        self.assertEqual(resumed["running_attempts"], [])
        takeover = self.result(
            self.run_cli(
                "takeover", *self.run_args(), "--coordinator-id", "coordinator-2"
            )
        )
        self.assertEqual(takeover["coordinator_generation"], 3)
        stale = self.run_cli("dispatch", *self.run_args(), "--task", "ROOT-01", "--local")
        self.assertEqual(json.loads(stale.stderr)["error"]["code"], "stale_coordinator")

        completed = self.result(
            self.run_cli("complete", *self.run_args(3), "--outcome", "partial")
        )
        self.assertEqual(completed["state"]["status"], "complete")
        self.assertFalse(any(item["status"] == "pending" for item in completed["state"]["cleanup"].values()))
        self.assertEqual(completed["state"]["driver"], "host")
        self.assertEqual(completed["state"]["degradations"], [])


if __name__ == "__main__":
    unittest.main()
