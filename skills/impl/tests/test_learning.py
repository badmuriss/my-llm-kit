import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "learning.py"


class LearningTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary_directory.name)
        self.runs_directory = self.repo / "openspec" / "impl-learning" / "runs"
        self.runs_directory.mkdir(parents=True)
        (self.repo / "proof.txt").write_text("verified\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_run(
        self,
        filename: str,
        run_id: str,
        *,
        change: str | None = None,
        key: str = "testing.prove-negative",
        kind: str = "rule",
        rule: str = "Prove each new test fails against the known-bad behavior.",
        supersedes: list[str] | None = None,
        task_grade: str = "pass",
        task_evidence_refs: list[str] | None = None,
        learning_evidence_refs: list[str] | None = None,
        incidents: list[dict[str, object]] | None = None,
    ) -> Path:
        record = {
            "schema_version": 2,
            "run_id": run_id,
            "change": change or f"change-{run_id}",
            "completed_at": "2026-08-09T12:00:00Z",
            "outcome": "pass",
            "tasks": [
                {
                    "id": "task-1",
                    "grade": task_grade,
                    "evidence": "The focused check exercised the target behavior.",
                    "evidence_refs": task_evidence_refs
                    if task_evidence_refs is not None
                    else ["file:proof.txt"],
                }
            ],
            "incidents": incidents or [],
            "learnings": [
                {
                    "key": key,
                    "kind": kind,
                    "scopes": ["testing"],
                    "rule": rule,
                    "evidence": f"Observed during {run_id}.",
                    "evidence_refs": learning_evidence_refs or ["task:task-1"],
                    "supersedes": supersedes or [],
                }
            ],
        }
        path = self.runs_directory / filename
        path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        return path

    def run_learning(self, command: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), command, "--repo", str(self.repo)],
            check=False,
            capture_output=True,
            text=True,
        )

    def artifact(self, filename: str) -> str:
        return (self.repo / "openspec" / "impl-learning" / filename).read_text(
            encoding="utf-8"
        )


class PromotionBehavior(LearningTestCase):
    def test_keeps_a_single_observation_as_a_candidate(self) -> None:
        self.write_run("run-1.json", "run-1")

        result = self.run_learning("refresh")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("No active impl rules.", self.artifact("ACTIVE_RULES.md"))

    def test_promotes_a_rule_across_distinct_changes(self) -> None:
        self.write_run("run-1.json", "run-1", change="change-a")
        self.write_run("run-2.json", "run-2", change="change-b")

        result = self.run_learning("refresh")

        self.assertEqual(result.returncode, 0, result.stderr)
        active_rules = self.artifact("ACTIVE_RULES.md")
        self.assertIn("## testing.prove-negative", active_rules)
        self.assertIn("`change-a`", active_rules)
        self.assertIn("`change-b`", active_rules)

    def test_keeps_duplicate_observations_from_one_change_unpromoted(self) -> None:
        self.write_run("run-1.json", "run-1", change="same-change")
        self.write_run("run-2.json", "run-2", change="same-change")

        result = self.run_learning("refresh")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("## testing.prove-negative", self.artifact("ACTIVE_RULES.md"))

    def test_routes_gate_candidates_away_from_active_rules(self) -> None:
        self.write_run("run-1.json", "run-1", change="change-a", kind="gate_candidate")
        self.write_run("run-2.json", "run-2", change="change-b", kind="gate_candidate")

        result = self.run_learning("refresh")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("## testing.prove-negative", self.artifact("ACTIVE_RULES.md"))
        self.assertIn("## testing.prove-negative", self.artifact("GATE_CANDIDATES.md"))
        self.assertIn("never edits code", self.artifact("GATE_CANDIDATES.md"))

    def test_prevents_gate_candidates_from_superseding_active_rules(self) -> None:
        self.write_run(
            "run-1.json",
            "run-1",
            kind="gate_candidate",
            supersedes=["testing.old-rule"],
        )

        result = self.run_learning("refresh")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("gate candidates cannot supersede", result.stderr)

    def test_removes_a_rule_when_a_promoted_rule_supersedes_it(self) -> None:
        self.write_run("old-1.json", "old-1", change="old-a", key="worktree.old")
        self.write_run("old-2.json", "old-2", change="old-b", key="worktree.old")
        self.write_run(
            "new-1.json",
            "new-1",
            change="new-a",
            key="worktree.root-deps",
            rule="Keep dependencies isolated per worktree.",
            supersedes=["worktree.old"],
        )
        self.write_run(
            "new-2.json",
            "new-2",
            change="new-b",
            key="worktree.root-deps",
            rule="Keep dependencies isolated per worktree.",
            supersedes=["worktree.old"],
        )

        result = self.run_learning("refresh")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("## worktree.old", self.artifact("ACTIVE_RULES.md"))
        self.assertIn("## worktree.root-deps", self.artifact("ACTIVE_RULES.md"))


class EvidenceBehavior(LearningTestCase):
    def test_rejects_a_missing_evidence_file(self) -> None:
        self.write_run(
            "run-1.json",
            "run-1",
            task_evidence_refs=["file:missing.txt"],
        )

        result = self.run_learning("refresh")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("evidence file does not exist", result.stderr)

    def test_rejects_evidence_symlinks_that_escape_the_repository(self) -> None:
        (self.repo / "escaped.txt").symlink_to("/etc/hosts")
        self.write_run(
            "run-1.json",
            "run-1",
            task_evidence_refs=["file:escaped.txt"],
        )

        result = self.run_learning("refresh")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must stay inside the repository", result.stderr)

    def test_rejects_moving_commit_references(self) -> None:
        self.write_run(
            "run-1.json",
            "run-1",
            task_evidence_refs=["commit:HEAD"],
        )

        result = self.run_learning("refresh")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("full immutable SHA", result.stderr)

    def test_rejects_observed_grades_without_evidence_refs(self) -> None:
        self.write_run("run-1.json", "run-1", task_evidence_refs=[])

        result = self.run_learning("refresh")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires evidence_refs for grade pass", result.stderr)

    def test_rejects_a_learning_backed_by_an_unobserved_task(self) -> None:
        self.write_run(
            "run-1.json",
            "run-1",
            task_grade="unobserved",
            task_evidence_refs=[],
        )

        result = self.run_learning("refresh")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("evidence task must have grade pass", result.stderr)

    def test_accepts_a_learning_backed_by_a_verified_incident(self) -> None:
        incident = {
            "key": "crash.resume",
            "kind": "crash_recovery",
            "status": "verified",
            "symptom": "The desktop exited during integration.",
            "hypothesis": "Transient run state existed only in chat context.",
            "proposed_fix": "Persist task transitions atomically.",
            "verification_plan": "Resume a fixture after an interrupted task.",
            "evidence_refs": ["task:task-1"],
        }
        self.write_run(
            "run-1.json",
            "run-1",
            incidents=[incident],
            learning_evidence_refs=["incident:crash.resume"],
        )

        result = self.run_learning("refresh")

        self.assertEqual(result.returncode, 0, result.stderr)


class GeneratedArtifactsBehavior(LearningTestCase):
    def test_rejects_duplicate_run_ids(self) -> None:
        self.write_run("run-a.json", "same-run", change="change-a")
        self.write_run("run-b.json", "same-run", change="change-b")

        result = self.run_learning("refresh")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate run_ids", result.stderr)

    def test_rejects_conflicting_rule_meanings(self) -> None:
        self.write_run("run-1.json", "run-1", change="change-a")
        self.write_run(
            "run-2.json",
            "run-2",
            change="change-b",
            rule="Regenerate snapshots whenever a test fails.",
        )

        result = self.run_learning("refresh")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("conflicting kind, rule text", result.stderr)

    def test_detects_generated_artifact_drift(self) -> None:
        self.write_run("run-1.json", "run-1")
        self.assertEqual(self.run_learning("refresh").returncode, 0)
        gate_candidates = self.repo / "openspec" / "impl-learning" / "GATE_CANDIDATES.md"
        gate_candidates.write_text("hand edited\n", encoding="utf-8")

        result = self.run_learning("check")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("GATE_CANDIDATES.md is stale", result.stderr)

    def test_aggregates_quality_and_safety_signals(self) -> None:
        incident = {
            "key": "guard.denied",
            "kind": "resource_denial",
            "status": "verified",
            "symptom": "The resource guard denied a worker.",
            "hypothesis": "Machine-wide agent capacity was exhausted.",
            "proposed_fix": "Continue locally and retry after capacity returns.",
            "verification_plan": "Confirm the root agent finishes without a new worker.",
            "evidence_refs": ["task:task-1"],
        }
        self.write_run("run-1.json", "run-1", incidents=[incident])

        result = self.run_learning("refresh")

        self.assertEqual(result.returncode, 0, result.stderr)
        quality_signals = self.artifact("QUALITY_SIGNALS.md")
        self.assertIn("- pass: 1", quality_signals)
        self.assertIn("- resource_denial: 1", quality_signals)
        self.assertIn("PR volume is excluded", quality_signals)


if __name__ == "__main__":
    unittest.main()
