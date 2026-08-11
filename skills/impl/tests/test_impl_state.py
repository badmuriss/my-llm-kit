import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "impl_state.py"


class ImplStateBehavior(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary_directory.name)
        self.change = "verify-harness"
        self.change_directory = self.repo / "openspec" / "changes" / self.change
        self.change_directory.mkdir(parents=True)
        self.tasks_file = self.change_directory / "tasks.md"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def writes_task(self, check: str | None) -> None:
        check_line = "" if check is None else f"\n  Check: {check}"
        self.tasks_file.write_text(
            f"# Tasks\n\n- [ ] 1.1 Verify the harness{check_line}\n",
            encoding="utf-8",
        )

    def run_state(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(self.repo), *arguments],
            check=False,
            capture_output=True,
            text=True,
        )

    def initializes(self) -> subprocess.CompletedProcess[str]:
        return self.run_state(
            "init",
            "--change",
            self.change,
            "--run-id",
            "run-1",
        )

    def reads_state(self) -> dict[str, object]:
        state_path = self.repo / "openspec" / "impl-state" / f"{self.change}.json"
        return json.loads(state_path.read_text(encoding="utf-8"))

    def records_task(self, status: str, note: str) -> subprocess.CompletedProcess[str]:
        return self.run_state(
            "update-task",
            "--change",
            self.change,
            "--task",
            "1.1",
            "--status",
            status,
            "--note",
            note,
        )


class ValidationContractBehavior(ImplStateBehavior):
    def test_parses_a_runnable_check(self) -> None:
        self.writes_task(f'"{sys.executable}" -c "raise SystemExit(0)"')

        result = self.initializes()

        self.assertEqual(result.returncode, 0, result.stderr)
        check = self.reads_state()["tasks"][0]["check"]
        self.assertEqual(check["status"], "pending")
        self.assertIn("raise SystemExit(0)", check["command"])

    def test_rejects_a_task_without_a_check(self) -> None:
        self.writes_task(None)

        result = self.initializes()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("needs exactly one Check: line", result.stderr)

    def test_keeps_missing_evidence_unobserved(self) -> None:
        self.writes_task("missing validation evidence")
        self.assertEqual(self.initializes().returncode, 0)

        check_result = self.run_state(
            "run-check",
            "--change",
            self.change,
            "--task",
            "1.1",
        )
        pass_result = self.records_task("pass", "No validation command exists.")

        self.assertNotEqual(check_result.returncode, 0)
        self.assertIn("grade it unobserved", check_result.stderr)
        self.assertNotEqual(pass_result.returncode, 0)
        self.assertIn("requires a recorded passing check", pass_result.stderr)
        check = self.reads_state()["tasks"][0]["check"]
        self.assertEqual(check["status"], "unobserved")


class CheckExecutionBehavior(ImplStateBehavior):
    def test_records_a_passing_check_before_acceptance(self) -> None:
        self.writes_task(f'"{sys.executable}" -c "raise SystemExit(0)"')
        self.assertEqual(self.initializes().returncode, 0)

        premature = self.records_task("pass", "The command passed.")
        checked = self.run_state(
            "run-check",
            "--change",
            self.change,
            "--task",
            "1.1",
        )
        accepted = self.records_task("pass", "The recorded command passed.")

        self.assertNotEqual(premature.returncode, 0)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        check = self.reads_state()["tasks"][0]["check"]
        self.assertEqual(check["status"], "passed")
        self.assertEqual(check["exit_code"], 0)
        self.assertEqual(check["attempts"], 1)
        self.assertGreaterEqual(check["duration_ms"], 0)
        self.assertEqual(check["total_duration_ms"], check["duration_ms"])

    def test_records_failure_and_recovery_across_attempts(self) -> None:
        command = (
            f'"{sys.executable}" -c "from pathlib import Path; '
            "raise SystemExit(0 if Path('proof.txt').exists() else 1)\""
        )
        self.writes_task(command)
        self.assertEqual(self.initializes().returncode, 0)

        failed = self.run_state(
            "run-check",
            "--change",
            self.change,
            "--task",
            "1.1",
        )
        failed_grade = self.records_task("fail", "The proof file was absent.")
        (self.repo / "proof.txt").write_text("observed\n", encoding="utf-8")
        passed = self.run_state(
            "run-check",
            "--change",
            self.change,
            "--task",
            "1.1",
        )
        passed_grade = self.records_task("pass", "The proof file was observed.")

        self.assertNotEqual(failed.returncode, 0)
        self.assertEqual(failed_grade.returncode, 0, failed_grade.stderr)
        self.assertEqual(passed.returncode, 0, passed.stderr)
        self.assertEqual(passed_grade.returncode, 0, passed_grade.stderr)
        check = self.reads_state()["tasks"][0]["check"]
        self.assertEqual(check["status"], "passed")
        self.assertEqual(check["attempts"], 2)
        self.assertGreaterEqual(check["total_duration_ms"], check["duration_ms"])


class CompletionBehavior(ImplStateBehavior):
    def test_marks_running_work_interrupted_on_resume(self) -> None:
        self.writes_task(f'"{sys.executable}" -c "raise SystemExit(0)"')
        self.assertEqual(self.initializes().returncode, 0)
        running = self.run_state(
            "update-task",
            "--change",
            self.change,
            "--task",
            "1.1",
            "--status",
            "running",
            "--worker",
            "local",
        )
        self.assertEqual(running.returncode, 0, running.stderr)

        resumed = self.run_state("resume", "--change", self.change)

        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        summary = json.loads(resumed.stdout)
        self.assertEqual(summary["interrupted_tasks"], ["1.1"])
        task = self.reads_state()["tasks"][0]
        self.assertEqual(task["status"], "interrupted")
        self.assertIsNone(task["worker"])

    def test_blocks_completion_with_pending_cleanup(self) -> None:
        self.writes_task(f'"{sys.executable}" -c "raise SystemExit(0)"')
        self.assertEqual(self.initializes().returncode, 0)
        self.assertEqual(
            self.run_state(
                "add-cleanup",
                "--change",
                self.change,
                "--kind",
                "process",
                "--target",
                "999999",
                "--owner",
                "run-1",
            ).returncode,
            0,
        )

        result = self.run_state(
            "complete",
            "--change",
            self.change,
            "--outcome",
            "partial",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("finish cleanup first", result.stderr)

    def test_completes_without_a_generated_learning_run(self) -> None:
        self.writes_task(f'"{sys.executable}" -c "raise SystemExit(0)"')
        self.assertEqual(self.initializes().returncode, 0)
        self.assertEqual(
            self.run_state(
                "run-check",
                "--change",
                self.change,
                "--task",
                "1.1",
            ).returncode,
            0,
        )
        self.assertEqual(
            self.records_task("pass", "The contract passed.").returncode,
            0,
        )

        result = self.run_state(
            "complete",
            "--change",
            self.change,
            "--outcome",
            "pass",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.reads_state()["status"], "complete")
        self.assertFalse((self.repo / "openspec" / "impl-learning").exists())


if __name__ == "__main__":
    unittest.main()
