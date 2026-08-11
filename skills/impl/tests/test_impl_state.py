import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "impl_state.py"
PLATFORM_VIEWPORTS = {
    "desktop": (1920, 1080),
    "notebook": (1366, 768),
    "tablet": (810, 1080),
    "mobile": (390, 664),
}
PLATFORM_BROWSERS = {
    "desktop": "chromium",
    "notebook": "chromium",
    "tablet": "webkit",
    "mobile": "webkit",
}


def visual_expectations(state: str = "populated") -> list[str]:
    return [
        f"home-{platform}-{state} | / | {platform} | {width}x{height} | {state}"
        for platform, (width, height) in PLATFORM_VIEWPORTS.items()
    ]


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

    def writes_task(self, check: str | None, visuals: list[str] | None = None) -> None:
        check_line = "" if check is None else f"\n  Check: {check}"
        visual_lines = "".join(f"\n  Visual: {visual}" for visual in visuals or [])
        self.tasks_file.write_text(
            f"# Tasks\n\n- [ ] 1.1 Verify the harness{check_line}{visual_lines}\n",
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

    def records_task(
        self,
        status: str,
        note: str,
        *evidence_refs: str,
    ) -> subprocess.CompletedProcess[str]:
        arguments = [
            "update-task",
            "--change",
            self.change,
            "--task",
            "1.1",
            "--status",
            status,
            "--note",
            note,
        ]
        for reference in evidence_refs:
            arguments.extend(["--evidence-ref", reference])
        return self.run_state(*arguments)

    def initializes_git(self) -> None:
        commands = [
            ["git", "init", "-q"],
            ["git", "config", "user.email", "test@example.com"],
            ["git", "config", "user.name", "Test"],
            ["git", "add", "."],
            ["git", "commit", "-qm", "test fixture"],
        ]
        for command in commands:
            subprocess.run(command, cwd=self.repo, check=True, capture_output=True)

    def writes_visual_evidence(
        self,
        expectations: list[str],
        *,
        reviewed_with: str = "view_image",
    ) -> str:
        evidence_directory = self.repo / ".visual-evidence" / self.change
        evidence_directory.mkdir(parents=True, exist_ok=True)

        def chunk(kind: bytes, content: bytes) -> bytes:
            checksum = zlib.crc32(kind + content) & 0xFFFFFFFF
            return struct.pack(">I", len(content)) + kind + content + struct.pack(">I", checksum)

        results = []
        for expectation in expectations:
            identifier, _, platform, viewport, _ = [
                part.strip() for part in expectation.split("|")
            ]
            width, height = (int(value) for value in viewport.split("x"))
            screenshot = evidence_directory / f"{identifier}.png"
            row = bytearray([0])
            for x in range(width):
                row.extend((x % 256, (x // 2) % 256, (x // 3) % 256))
            screenshot.write_bytes(
                b"\x89PNG\r\n\x1a\n"
                + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(bytes(row) * height))
                + chunk(b"IEND", b"")
            )
            results.append(
                {
                    "expectation": expectation,
                    "browser": PLATFORM_BROWSERS[platform],
                    "screenshot": screenshot.relative_to(self.repo).as_posix(),
                    "sha256": hashlib.sha256(screenshot.read_bytes()).hexdigest(),
                    "status": "pass",
                    "observation": "The page has visible content without clipping or horizontal overflow.",
                }
            )

        manifest = evidence_directory / "task-1.1.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "change": self.change,
                    "task": "1.1",
                    "reviewed_with": reviewed_with,
                    "reviewed_at": "2026-08-11T12:00:00Z",
                    "results": results,
                }
            ),
            encoding="utf-8",
        )
        return f"file:{manifest.relative_to(self.repo).as_posix()}"


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


class VisualEvidenceBehavior(ImplStateBehavior):
    expectations = visual_expectations()

    def prepares_passing_task(self, *, visuals: list[str] | None = None) -> None:
        self.writes_task(f'"{sys.executable}" -c "raise SystemExit(0)"', visuals)
        self.assertEqual(self.initializes().returncode, 0)
        self.assertEqual(
            self.run_state("run-check", "--change", self.change, "--task", "1.1").returncode,
            0,
        )

    def test_rejects_an_incomplete_platform_matrix(self) -> None:
        self.writes_task(
            f'"{sys.executable}" -c "raise SystemExit(0)"',
            self.expectations[:-1],
        )

        result = self.initializes()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("is missing: mobile", result.stderr)

    def test_rejects_a_noncanonical_platform_viewport(self) -> None:
        invalid = [
            expectation.replace("notebook | 1366x768", "notebook | 1280x720")
            for expectation in self.expectations
        ]
        self.writes_task(f'"{sys.executable}" -c "raise SystemExit(0)"', invalid)

        result = self.initializes()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("platform notebook requires 1366x768", result.stderr)

    def test_requires_a_manifest_before_a_visual_task_passes(self) -> None:
        self.prepares_passing_task(visuals=self.expectations)

        missing = self.records_task("pass", "The code check passed.")
        evidence_ref = self.writes_visual_evidence(self.expectations)
        accepted = self.records_task("pass", "The code and visual checks passed.", evidence_ref)

        self.assertNotEqual(missing.returncode, 0)
        self.assertIn("requires a valid vision-reviewed manifest", missing.stderr)
        self.assertEqual(accepted.returncode, 0, accepted.stderr)

    def test_rejects_a_manifest_without_a_vision_review(self) -> None:
        self.prepares_passing_task(visuals=self.expectations)
        evidence_ref = self.writes_visual_evidence(
            self.expectations,
            reviewed_with="playwright",
        )

        result = self.records_task("pass", "The browser check passed.", evidence_ref)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("reviewed_with must be computer-use or view_image", result.stderr)

    def test_rejects_a_visual_manifest_outside_the_evidence_directory(self) -> None:
        self.prepares_passing_task(visuals=self.expectations)
        evidence_ref = self.writes_visual_evidence(self.expectations)
        source = self.repo / evidence_ref.removeprefix("file:")
        misplaced = self.repo / "visual-result.json"
        misplaced.write_bytes(source.read_bytes())

        result = self.records_task(
            "pass",
            "The browser check passed.",
            "file:visual-result.json",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("manifest must be stored under", result.stderr)

    def test_rejects_a_corrupt_visual_screenshot(self) -> None:
        self.prepares_passing_task(visuals=self.expectations)
        evidence_ref = self.writes_visual_evidence(self.expectations)
        manifest_path = self.repo / evidence_ref.removeprefix("file:")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        screenshot = self.repo / manifest["results"][0]["screenshot"]
        screenshot.write_bytes(b"not a png")
        manifest["results"][0]["sha256"] = hashlib.sha256(screenshot.read_bytes()).hexdigest()
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        result = self.records_task(
            "pass",
            "The browser check passed.",
            evidence_ref,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("screenshot is not a PNG", result.stderr)

    def test_rejects_the_wrong_browser_engine_for_a_platform(self) -> None:
        self.prepares_passing_task(visuals=self.expectations)
        evidence_ref = self.writes_visual_evidence(self.expectations)
        manifest_path = self.repo / evidence_ref.removeprefix("file:")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["results"][0]["browser"] = "webkit"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        result = self.records_task(
            "pass",
            "The browser check passed.",
            evidence_ref,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires browser chromium", result.stderr)

    def test_requires_every_declared_visual_state(self) -> None:
        loading = visual_expectations("loading")
        self.prepares_passing_task(visuals=self.expectations + loading)
        evidence_ref = self.writes_visual_evidence(self.expectations)

        result = self.records_task(
            "pass",
            "The populated state passed.",
            evidence_ref,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing visual results", result.stderr)

    def test_blocks_frontend_completion_when_the_plan_omits_visuals(self) -> None:
        self.writes_task(f'"{sys.executable}" -c "raise SystemExit(0)"')
        self.initializes_git()
        self.assertEqual(self.initializes().returncode, 0)
        self.assertEqual(
            self.run_state("run-check", "--change", self.change, "--task", "1.1").returncode,
            0,
        )
        self.assertEqual(self.records_task("pass", "The code check passed.").returncode, 0)
        source = self.repo / "src" / "App.tsx"
        source.parent.mkdir()
        source.write_text(
            "export function App() { return <main>Changed</main>; }\n",
            encoding="utf-8",
        )

        result = self.run_state("complete", "--change", self.change, "--outcome", "pass")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("frontend changes require Visual entries", result.stderr)

    def test_completes_frontend_work_with_vision_reviewed_evidence(self) -> None:
        self.writes_task(
            f'"{sys.executable}" -c "raise SystemExit(0)"',
            self.expectations,
        )
        self.initializes_git()
        self.assertEqual(self.initializes().returncode, 0)
        self.assertEqual(
            self.run_state("run-check", "--change", self.change, "--task", "1.1").returncode,
            0,
        )
        evidence_ref = self.writes_visual_evidence(self.expectations)
        self.assertEqual(
            self.records_task("pass", "Vision confirmed the rendered UI.", evidence_ref).returncode,
            0,
        )
        source = self.repo / "src" / "App.tsx"
        source.parent.mkdir()
        source.write_text(
            "export function App() { return <main>Changed</main>; }\n",
            encoding="utf-8",
        )

        result = self.run_state("complete", "--change", self.change, "--outcome", "pass")

        self.assertEqual(result.returncode, 0, result.stderr)


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
