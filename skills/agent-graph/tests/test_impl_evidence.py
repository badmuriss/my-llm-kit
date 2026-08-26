import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path


ROOT = Path(__file__).parents[3]
CLI = Path(__file__).parents[1] / "scripts" / "agent_graph.py"
LEARNING = ROOT / "skills" / "impl" / "scripts" / "learning.py"
EXPECTATION = "home-mobile | / | mobile | 390x664 | populated"
sys.path.insert(0, str(CLI.parent))

import adaptive_intake  # noqa: E402
import agent_graph as runtime  # noqa: E402


def png_bytes(width: int, height: int) -> bytes:
    def chunk(kind: bytes, content: bytes) -> bytes:
        checksum = zlib.crc32(kind + content) & 0xFFFFFFFF
        return struct.pack(">I", len(content)) + kind + content + struct.pack(">I", checksum)

    row = bytearray([0])
    for x in range(width):
        row.extend((x % 256, (x // 2) % 256, (x // 3) % 256))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(row) * height))
        + chunk(b"IEND", b"")
    )


class ImplEvidenceBehavior(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repository = Path(self.temporary_directory.name)
        change = self.repository / "openspec" / "changes" / "evidence"
        change.mkdir(parents=True)
        (change / "proposal.md").write_text("# Proposal\n", encoding="utf-8")
        (change / "design.md").write_text("# Design\n", encoding="utf-8")
        (change / "tasks.md").write_text(
            f'''# Tasks

- [ ] UI-01 Verify the visual surface
  Depends: []
  Paths: [src/ui.py]
  Mode: write
  Isolation: auto
  Acceptance: The visible state is evidence-reviewed.
  Check: "{sys.executable}" -c "import pathlib; raise SystemExit(1 if pathlib.Path('.repair-fixture-fail').is_file() else 0)"
  Visual-Scope: / | populated | mobile | This fixture supports only the declared mobile surface.
  Visual: {EXPECTATION}

- [ ] AUX-02 Verify an independent evidence packet
  Depends: []
  Paths: [src/aux.py]
  Mode: read
  Isolation: auto
  Acceptance: The auxiliary packet passes its bounded check.
  Check: "{sys.executable}" -c "raise SystemExit(0)"
''',
            encoding="utf-8",
        )
        self.graph = runtime.parse_task_graph(change / "tasks.md")
        transition = adaptive_intake.decide_process(
            self.repository,
            request="Verify independent evidence packets.",
            check_command=self.graph.tasks[0].check,
            signals={
                "known_scope": True,
                "graph_requested": True,
                "cohesion": "independent",
                "independent_packets": [
                    {"packet_id": task.id, "paths": list(task.paths), "check": {"command": task.check, "oracle": f"{task.id} passes."}}
                    for task in self.graph.tasks
                ],
                "integrator": "coordinator-1",
                "permission_observed": True,
                "budget_limits": [{"resource": "workers", "value": 2, "unit": "workers", "rationale": "Two independent fixture packets."}],
                "cleanup_plan": "Verify all evidence and owned resources before completion.",
            },
        )
        (change / "process-decision.json").write_text(json.dumps(transition), encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(self.repository)], check=True)
        subprocess.run(["git", "-C", str(self.repository), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(self.repository), "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "-C", str(self.repository), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.repository), "commit", "-qm", "fixture"], check=True)
        unrelated_frontend = self.repository / "research/mocks/preexisting.html"
        unrelated_frontend.parent.mkdir(parents=True)
        unrelated_frontend.write_text("<p>preexisting untracked mock</p>\n", encoding="utf-8")
        self.bootstrap()

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
        result = json.loads(completed.stdout)["result"]
        state_path = self.repository / "openspec/runs/evidence/run-1/state.json"
        if "state" not in result and state_path.is_file():
            result["state"] = json.loads(state_path.read_text(encoding="utf-8"))
        return result

    def common(self) -> tuple[str, ...]:
        return ("--change", "evidence", "--run-id", "run-1", "--generation", "2")

    def bootstrap(self) -> None:
        boot = self.result(
            self.run_cli(
                "bootstrap", "--change", "evidence", "--run-id", "run-1",
                "--bootstrap-id", "bootstrap-1", "--driver", "host",
            )
        )
        self.result(
            self.run_cli(
                "claim-coordinator", "--capsule", boot["capsule_path"],
                "--coordinator-id", "coordinator-1",
            )
        )

    def report_and_check(self) -> None:
        dispatched = self.result(self.run_cli("dispatch", *self.common(), "--task", "UI-01", "--local"))
        report = {
            "task_id": "UI-01",
            "attempt_id": dispatched["attempt_id"],
            "outcome": "reported",
            "summary": "Verified the bounded UI change.",
            "files_changed": ["src/ui.py"],
            "checks_run": [next(task.check for task in self.graph.tasks if task.id == "UI-01")],
            "evidence_refs": [],
            "questions": [],
            "external_refs": {},
        }
        self.result(
            self.run_cli(
                "record-result", *self.common(), "--attempt", dispatched["attempt_id"],
                "--result-json", json.dumps(report),
            )
        )
        self.result(self.run_cli("run-check", *self.common(), "--task", "UI-01"))

    def finish_auxiliary_task(self) -> None:
        dispatched = self.result(self.run_cli("dispatch", *self.common(), "--task", "AUX-02", "--local"))
        check = next(task.check for task in self.graph.tasks if task.id == "AUX-02")
        report = {
            "task_id": "AUX-02",
            "attempt_id": dispatched["attempt_id"],
            "outcome": "reported",
            "summary": "Verified the auxiliary evidence packet.",
            "files_changed": [],
            "checks_run": [check],
            "evidence_refs": [],
            "questions": [],
            "external_refs": {},
        }
        self.result(self.run_cli("record-result", *self.common(), "--attempt", dispatched["attempt_id"], "--result-json", json.dumps(report)))
        self.result(self.run_cli("run-check", *self.common(), "--task", "AUX-02"))
        self.result(self.run_cli("grade", *self.common(), "--task", "AUX-02", "--grade", "pass", "--note", "The auxiliary check passed."))

    def write_manifest(self) -> str:
        directory = self.repository / ".visual-evidence" / "evidence"
        directory.mkdir(parents=True)
        screenshot = directory / "home-mobile.png"
        screenshot.write_bytes(png_bytes(390, 664))
        relative_screenshot = screenshot.relative_to(self.repository).as_posix()
        manifest = directory / "UI-01.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "change": "evidence",
                    "task": "UI-01",
                    "reviewed_with": "view_image",
                    "reviewed_at": "2026-08-20T12:00:00Z",
                    "results": [
                        {
                            "expectation": EXPECTATION,
                            "browser": "webkit",
                            "screenshot": relative_screenshot,
                            "sha256": hashlib.sha256(screenshot.read_bytes()).hexdigest(),
                            "status": "pass",
                            "observation": "The mobile surface is visible without clipping, overlap, or horizontal overflow.",
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return manifest.relative_to(self.repository).as_posix()

    def test_requires_and_validates_vision_reviewed_evidence_before_pass(self) -> None:
        self.report_and_check()

        missing = self.run_cli(
            "grade", *self.common(), "--task", "UI-01", "--grade", "pass",
            "--note", "The check passed but visual evidence is absent.",
        )
        self.assertNotEqual(missing.returncode, 0)
        self.assertEqual(json.loads(missing.stderr)["error"]["code"], "visual_evidence_required")

        manifest = self.write_manifest()
        passed = self.result(
            self.run_cli(
                "grade", *self.common(), "--task", "UI-01", "--grade", "pass",
                "--note", "The check and reviewed visual evidence passed.",
                "--evidence-ref", f"file:{manifest}",
            )
        )
        self.assertEqual(passed["state"]["tasks"]["UI-01"]["evidence_refs"], [f"file:{manifest}"])

    def test_caps_distinct_repair_hypotheses(self) -> None:
        (self.repository / ".repair-fixture-fail").touch()
        check = next(task.check for task in self.graph.tasks if task.id == "UI-01")
        for value in ("The first implementation missed the contract.", "The repair preserved the wrong invariant."):
            dispatched = self.result(self.run_cli("dispatch", *self.common(), "--task", "UI-01", "--local"))
            report = {
                "task_id": "UI-01",
                "attempt_id": dispatched["attempt_id"],
                "outcome": "reported",
                "summary": "The bounded repair attempt was reported for evidence review.",
                "files_changed": [],
                "checks_run": [check],
                "evidence_refs": [],
                "questions": [],
                "external_refs": {},
            }
            self.result(self.run_cli(
                "record-result", *self.common(), "--attempt", dispatched["attempt_id"],
                "--result-json", json.dumps(report),
            ))
            failed = self.run_cli("run-check", *self.common(), "--task", "UI-01")
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual(json.loads(failed.stderr)["error"]["code"], "check_failed")
            self.result(self.run_cli(
                "record-repair", *self.common(), "--task", "UI-01", "--hypothesis", value,
            ))

        fenced = self.run_cli("dispatch", *self.common(), "--task", "UI-01", "--local")
        self.assertNotEqual(fenced.returncode, 0)
        self.assertEqual(json.loads(fenced.stderr)["error"]["code"], "task_not_ready")
        self.result(self.run_cli(
            "record-decision", *self.common(), "--task", "UI-01",
            "--decision-id", "ui-repair-amendment", "--action", "amend_acceptance",
            "--note", "Authorize one bounded third attempt after two technical failures.",
        ))
        dispatched = self.result(self.run_cli("dispatch", *self.common(), "--task", "UI-01", "--local"))
        report = {
            "task_id": "UI-01",
            "attempt_id": dispatched["attempt_id"],
            "outcome": "reported",
            "summary": "The bounded repair attempt was reported for evidence review.",
            "files_changed": [],
            "checks_run": [check],
            "evidence_refs": [],
            "questions": [],
            "external_refs": {},
        }
        self.result(self.run_cli(
            "record-result", *self.common(), "--attempt", dispatched["attempt_id"],
            "--result-json", json.dumps(report),
        ))
        failed = self.run_cli("run-check", *self.common(), "--task", "UI-01")
        self.assertNotEqual(failed.returncode, 0)
        self.assertEqual(json.loads(failed.stderr)["error"]["code"], "check_failed")
        capped = self.run_cli(
            "record-repair", *self.common(), "--task", "UI-01",
            "--hypothesis", "A third independent repair would exceed the cap.",
        )
        self.assertNotEqual(capped.returncode, 0)
        self.assertEqual(json.loads(capped.stderr)["error"]["code"], "repair_cap_reached")

    def test_snapshots_a_completed_graph_projection_without_transcripts(self) -> None:
        self.report_and_check()
        manifest = self.write_manifest()
        self.result(
            self.run_cli(
                "grade", *self.common(), "--task", "UI-01", "--grade", "pass",
                "--note", "All recorded evidence passed.", "--evidence-ref", f"file:{manifest}",
            )
        )
        self.finish_auxiliary_task()
        self.result(self.run_cli("complete", *self.common(), "--outcome", "pass"))

        snapshot = subprocess.run(
            [sys.executable, str(LEARNING), "--repo", str(self.repository), "snapshot", "--change", "evidence", "--run-id", "run-1"],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(snapshot.returncode, 0, snapshot.stderr)
        record = json.loads((self.repository / "openspec/impl-learning/runs/run-1.json").read_text())
        ui_fact = next(fact for fact in record["facts"] if fact["task_id"] == "UI-01")
        self.assertEqual(ui_fact["status"], "pass")
        self.assertEqual(ui_fact["visual_expectations"], [EXPECTATION])
        self.assertNotIn("transcript", json.dumps(record).casefold())

    def test_removes_the_obsolete_flat_runtime(self) -> None:
        self.assertEqual(
            sorted(path.name for path in (ROOT / "skills/impl/scripts").glob("*.py")),
            ["learning.py"],
        )
        self.assertTrue((ROOT / "skills/agent-graph/scripts/visual_evidence.py").is_file())


if __name__ == "__main__":
    unittest.main()
