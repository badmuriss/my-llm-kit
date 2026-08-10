import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "impl_state.py"


class ImplStateTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary_directory.name)
        self.change = "improve-harness"
        self.change_directory = self.repo / "openspec" / "changes" / self.change
        self.change_directory.mkdir(parents=True)
        self.tasks_file = self.change_directory / "tasks.md"
        self.tasks_file.write_text(
            "# Tasks\n\n- [ ] 1.1 Add state\n- [x] 1.2 Existing work\n",
            encoding="utf-8",
        )
        (self.repo / "proof.txt").write_text("observed\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def run_state(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(self.repo), *arguments],
            check=False,
            capture_output=True,
            text=True,
        )

    def init(self) -> subprocess.CompletedProcess[str]:
        return self.run_state(
            "init",
            "--change",
            self.change,
            "--run-id",
            "run-1",
        )

    def state(self) -> dict[str, object]:
        path = self.repo / "openspec" / "impl-state" / f"{self.change}.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def pass_task(self) -> subprocess.CompletedProcess[str]:
        return self.run_state(
            "update-task",
            "--change",
            self.change,
            "--task",
            "1.1",
            "--status",
            "pass",
            "--evidence-ref",
            "file:proof.txt",
            "--note",
            "The fixture passed.",
        )


class InitializationBehavior(ImplStateTestCase):
    def test_initializes_only_unchecked_tasks(self) -> None:
        result = self.init()

        self.assertEqual(result.returncode, 0, result.stderr)
        state = self.state()
        self.assertEqual([task["id"] for task in state["tasks"]], ["1.1"])
        self.assertEqual(state["status"], "active")
        self.assertEqual(state["base_commit"], "unborn")

    def test_stops_when_no_unchecked_tasks_remain(self) -> None:
        self.tasks_file.write_text("- [x] 1.1 Finished\n", encoding="utf-8")

        result = self.init()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("stop instead of inventing work", result.stderr)

    def test_rejects_tasks_without_stable_ids(self) -> None:
        self.tasks_file.write_text("- [ ] Add state without an id\n", encoding="utf-8")

        result = self.init()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("task needs a stable leading id", result.stderr)


class CheckpointBehavior(ImplStateTestCase):
    def test_requires_evidence_before_a_pass(self) -> None:
        self.assertEqual(self.init().returncode, 0)

        result = self.run_state(
            "update-task",
            "--change",
            self.change,
            "--task",
            "1.1",
            "--status",
            "pass",
            "--note",
            "The state fixture passed.",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires evidence refs", result.stderr)

    def test_caps_distinct_repair_hypotheses(self) -> None:
        self.assertEqual(self.init().returncode, 0)
        for hypothesis in ("The parser skipped the task.", "The writer lost the update."):
            result = self.run_state(
                "update-task",
                "--change",
                self.change,
                "--task",
                "1.1",
                "--status",
                "pending",
                "--hypothesis",
                hypothesis,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

        result = self.run_state(
            "update-task",
            "--change",
            self.change,
            "--task",
            "1.1",
            "--status",
            "pending",
            "--hypothesis",
            "The evidence path was stale.",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("hypothesis cap reached", result.stderr)


class ResumeBehavior(ImplStateTestCase):
    def test_marks_running_tasks_interrupted_before_resume(self) -> None:
        self.assertEqual(self.init().returncode, 0)
        running = self.run_state(
            "update-task",
            "--change",
            self.change,
            "--task",
            "1.1",
            "--status",
            "running",
            "--worker",
            "worker-7",
        )
        self.assertEqual(running.returncode, 0, running.stderr)

        result = self.run_state("resume", "--change", self.change)

        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        self.assertEqual(summary["interrupted_tasks"], ["1.1"])
        self.assertIn("Inspect diffs", summary["instruction"])
        task = self.state()["tasks"][0]
        self.assertEqual(task["status"], "interrupted")
        self.assertIsNone(task["worker"])

    def test_blocks_completion_until_cleanup_finishes(self) -> None:
        self.assertEqual(self.init().returncode, 0)
        passed = self.pass_task()
        self.assertEqual(passed.returncode, 0, passed.stderr)
        cleanup = self.run_state(
            "add-cleanup",
            "--change",
            self.change,
            "--kind",
            "process",
            "--target",
            "999999",
            "--owner",
            "run-1",
        )
        self.assertEqual(cleanup.returncode, 0, cleanup.stderr)

        blocked = self.run_state(
            "complete",
            "--change",
            self.change,
            "--outcome",
            "pass",
        )
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("finish cleanup first", blocked.stderr)

        finished = self.run_state(
            "finish-cleanup",
            "--change",
            self.change,
            "--target",
            "999999",
        )
        self.assertEqual(finished.returncode, 0, finished.stderr)
        exported = self.run_state(
            "export-run",
            "--change",
            self.change,
            "--outcome",
            "pass",
        )
        self.assertEqual(exported.returncode, 0, exported.stderr)
        refreshed = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).parents[1] / "scripts" / "learning.py"),
                "refresh",
                "--repo",
                str(self.repo),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(refreshed.returncode, 0, refreshed.stderr)
        completed = self.run_state(
            "complete",
            "--change",
            self.change,
            "--outcome",
            "pass",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(self.state()["status"], "complete")

    def test_refuses_to_finish_a_live_process_cleanup(self) -> None:
        self.assertEqual(self.init().returncode, 0)
        process_id = str(os.getpid())
        cleanup = self.run_state(
            "add-cleanup",
            "--change",
            self.change,
            "--kind",
            "process",
            "--target",
            process_id,
            "--owner",
            "run-1",
        )
        self.assertEqual(cleanup.returncode, 0, cleanup.stderr)

        result = self.run_state(
            "finish-cleanup",
            "--change",
            self.change,
            "--target",
            process_id,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cleanup target still exists", result.stderr)

    def test_exports_final_grades_without_retyping_them(self) -> None:
        self.assertEqual(self.init().returncode, 0)
        passed = self.pass_task()
        self.assertEqual(passed.returncode, 0, passed.stderr)

        result = self.run_state(
            "export-run",
            "--change",
            self.change,
            "--outcome",
            "pass",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        run_record = self.repo / "openspec" / "impl-learning" / "runs" / "run-1.json"
        record = json.loads(run_record.read_text(encoding="utf-8"))
        self.assertEqual(record["schema_version"], 2)
        self.assertEqual(record["tasks"][0]["grade"], "pass")
        self.assertEqual(record["tasks"][0]["evidence_refs"], ["file:proof.txt"])
        self.assertEqual(record["incidents"], [])
        self.assertEqual(record["learnings"], [])

    def test_blocks_completion_before_learning_refresh(self) -> None:
        self.assertEqual(self.init().returncode, 0)
        self.assertEqual(self.pass_task().returncode, 0)
        exported = self.run_state(
            "export-run",
            "--change",
            self.change,
            "--outcome",
            "pass",
        )
        self.assertEqual(exported.returncode, 0, exported.stderr)

        completion = self.run_state(
            "complete",
            "--change",
            self.change,
            "--outcome",
            "pass",
        )
        self.assertNotEqual(completion.returncode, 0)
        self.assertIn("ACTIVE_RULES.md is missing", completion.stderr)


if __name__ == "__main__":
    unittest.main()
