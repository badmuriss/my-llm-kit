import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "learning.py"


class LearningBehavior(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary_directory.name)
        self.state_directory = self.repo / "openspec" / "impl-state"
        self.state_directory.mkdir(parents=True)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def run_learning(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(self.repo), *arguments],
            check=False,
            capture_output=True,
            text=True,
        )

    def writes_state(
        self,
        change: str,
        run_id: str,
        *,
        status: str = "complete",
        task_status: str = "pass",
        attempts: int = 1,
        command: str = "python -m unittest",
    ) -> Path:
        path = self.state_directory / f"{change}.json"
        state = {
            "schema_version": 2,
            "change": change,
            "run_id": run_id,
            "status": status,
            "outcome": "pass" if status == "complete" else None,
            "started_at": "2026-08-10T10:00:00Z",
            "updated_at": "2026-08-10T10:01:00Z",
            "base_commit": "unborn",
            "last_observed_commit": "unborn",
            "tasks": [
                {
                    "id": "1.1",
                    "text": "Verify behavior",
                    "status": task_status,
                    "worker": None,
                    "hypotheses": ["The first attempt missed the contract"] if attempts > 1 else [],
                    "evidence_refs": [],
                    "check": {
                        "command": command,
                        "status": "passed" if task_status == "pass" else "failed",
                        "exit_code": 0 if task_status == "pass" else 1,
                        "duration_ms": 20,
                        "total_duration_ms": attempts * 20,
                        "attempts": attempts,
                    },
                    "note": "Observed by the task check.",
                }
            ],
            "cleanup": [],
            "digest": [],
        }
        path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        return path

    def snapshots(self, change: str) -> subprocess.CompletedProcess[str]:
        return self.run_learning("snapshot", "--change", change)

    def adds_candidate(
        self,
        run_id: str,
        *,
        stance: str = "support",
        statement: str = "Run the focused check before the full suite.",
    ) -> subprocess.CompletedProcess[str]:
        return self.run_learning(
            "add-candidate",
            "--run-id",
            run_id,
            "--key",
            "checks.focused-first",
            "--kind",
            "gate",
            "--scope",
            "tests",
            "--statement",
            statement,
            "--stance",
            stance,
            "--origin",
            "check",
            "--evidence",
            "The focused check exposed the failure before integration.",
            "--task-ref",
            "1.1",
        )


class ObservationCaptureBehavior(LearningBehavior):
    def test_snapshots_completed_state_as_facts_without_candidates(self) -> None:
        state_path = self.writes_state("change-one", "run-1", attempts=2)

        result = self.snapshots("change-one")

        self.assertEqual(result.returncode, 0, result.stderr)
        record_path = self.repo / "openspec" / "impl-learning" / "runs" / "run-1.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        self.assertEqual(record["state_sha256"], hashlib.sha256(state_path.read_bytes()).hexdigest())
        self.assertEqual(record["state_ref"], "openspec/impl-learning/evidence/run-1.state.json")
        self.assertEqual(record["facts"][0]["check_attempts"], 2)
        self.assertEqual(record["candidates"], [])

    def test_rejects_tampered_state_evidence(self) -> None:
        self.writes_state("change-one", "run-1")
        self.assertEqual(self.snapshots("change-one").returncode, 0)
        evidence_path = (
            self.repo / "openspec" / "impl-learning" / "evidence" / "run-1.state.json"
        )
        evidence_path.write_text("{}\n", encoding="utf-8")

        result = self.run_learning("compile")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("state evidence is missing or has changed", result.stderr)

    def test_rejects_snapshot_before_normal_completion(self) -> None:
        self.writes_state("change-one", "run-1", status="active")

        result = self.snapshots("change-one")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must be a completed impl state", result.stderr)

    def test_rejects_candidate_without_observed_task(self) -> None:
        self.writes_state("change-one", "run-1")
        self.assertEqual(self.snapshots("change-one").returncode, 0)

        result = self.run_learning(
            "add-candidate",
            "--run-id",
            "run-1",
            "--key",
            "checks.focused-first",
            "--kind",
            "gate",
            "--scope",
            "tests",
            "--statement",
            "Run the focused check first.",
            "--stance",
            "support",
            "--origin",
            "check",
            "--evidence",
            "Observed failure.",
            "--task-ref",
            "9.9",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown tasks: 9.9", result.stderr)


class DraftCompilationBehavior(LearningBehavior):
    def test_keeps_single_observation_as_weak_draft(self) -> None:
        self.writes_state("change-one", "run-1")
        self.assertEqual(self.snapshots("change-one").returncode, 0)
        self.assertEqual(self.adds_candidate("run-1").returncode, 0)

        compiled = self.run_learning("compile")
        checked = self.run_learning("check")

        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        drafts = (self.repo / "openspec" / "impl-learning" / "DRAFT_CANDIDATES.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Status: `weak-sample`", drafts)
        self.assertIn("Activation: prohibited", drafts)
        self.assertFalse((self.repo / "openspec" / "impl-learning" / "ACTIVE_RULES.md").exists())
        self.assertFalse((self.repo / "openspec" / "impl-learning" / "skills").exists())

    def test_marks_five_independent_changes_recurring_without_activation(self) -> None:
        for index in range(5):
            change = f"change-{index}"
            run_id = f"run-{index}"
            self.writes_state(change, run_id)
            self.assertEqual(self.snapshots(change).returncode, 0)
            self.assertEqual(self.adds_candidate(run_id).returncode, 0)

        result = self.run_learning("compile")

        self.assertEqual(result.returncode, 0, result.stderr)
        drafts = (self.repo / "openspec" / "impl-learning" / "DRAFT_CANDIDATES.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Status: `recurring-draft`", drafts)
        self.assertIn("Independent support changes: 5", drafts)
        self.assertNotIn("Active impl rules", drafts)

    def test_preserves_opposition_as_a_contested_draft(self) -> None:
        for index, stance in enumerate(("support", "oppose")):
            change = f"change-{index}"
            run_id = f"run-{index}"
            self.writes_state(change, run_id)
            self.assertEqual(self.snapshots(change).returncode, 0)
            self.assertEqual(self.adds_candidate(run_id, stance=stance).returncode, 0)

        result = self.run_learning("compile")

        self.assertEqual(result.returncode, 0, result.stderr)
        drafts = (self.repo / "openspec" / "impl-learning" / "DRAFT_CANDIDATES.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Status: `contested`", drafts)
        self.assertIn("opposition changes: 1", drafts)


class PairedEvaluationBehavior(LearningBehavior):
    def test_compares_identical_contracts_without_automatic_verdict(self) -> None:
        self.writes_state("memory-off", "run-off", attempts=2)
        self.writes_state("memory-on", "run-on", attempts=1)

        result = self.run_learning(
            "compare",
            "--candidate",
            "checks.focused-first",
            "--off-state",
            "openspec/impl-state/memory-off.json",
            "--on-state",
            "openspec/impl-state/memory-on.json",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        comparison = json.loads(result.stdout)
        self.assertEqual(comparison["delta_on_minus_off"]["check_attempts"], -1)
        self.assertEqual(comparison["delta_on_minus_off"]["check_total_duration_ms"], -20)
        self.assertIn("No automatic verdict", comparison["interpretation"])

    def test_rejects_comparison_with_different_task_checks(self) -> None:
        self.writes_state("memory-off", "run-off", command="python -m unittest")
        self.writes_state("memory-on", "run-on", command="python -m pytest")

        result = self.run_learning(
            "compare",
            "--candidate",
            "checks.focused-first",
            "--off-state",
            "openspec/impl-state/memory-off.json",
            "--on-state",
            "openspec/impl-state/memory-on.json",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("identical task checks", result.stderr)


if __name__ == "__main__":
    unittest.main()
