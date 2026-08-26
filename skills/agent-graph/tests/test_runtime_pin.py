import hashlib
import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SOURCE_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(SOURCE_ROOT / "scripts"))

import adaptive_intake  # noqa: E402
import agent_graph as runtime  # noqa: E402


TASKS = f"""# Tasks

- [ ] PIN-01 Exercise the pinned runtime
  Depends: []
  Paths: [src/pin.py]
  Mode: write
  Isolation: auto
  Acceptance: The pinned runtime remains authoritative.
  Check: \"{sys.executable}\" -c \"raise SystemExit(0)\"

- [ ] PIN-02 Exercise an independent pinned packet
  Depends: []
  Paths: [src/pin_aux.py]
  Mode: write
  Isolation: auto
  Acceptance: The second packet remains independent.
  Check: \"{sys.executable}\" -c \"raise SystemExit(0)\"
"""


class ControlRuntimePinBehavior(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repository = Path(self.temporary_directory.name)
        self.runtime_root = self.repository / "skills" / "agent-graph"
        shutil.copytree(
            SOURCE_ROOT,
            self.runtime_root,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        self.live_policy = self.repository / "skills" / "impl" / "references" / "routing-policy.seed.json"
        self.live_policy.parent.mkdir(parents=True)
        shutil.copyfile(
            SOURCE_ROOT.parent / "impl" / "references" / "routing-policy.seed.json",
            self.live_policy,
        )
        change = self.repository / "openspec" / "changes" / "pinning"
        change.mkdir(parents=True)
        (change / "proposal.md").write_text("# Proposal\n", encoding="utf-8")
        (change / "design.md").write_text("# Design\n", encoding="utf-8")
        (change / "tasks.md").write_text(TASKS, encoding="utf-8")
        self.graph = runtime.parse_task_graph(change / "tasks.md")
        transition = adaptive_intake.decide_process(
            self.repository,
            request="Exercise the pinned runtime with independent packets.",
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
                "cleanup_plan": "Release the immutable runtime after terminal completion.",
            },
        )
        (change / "process-decision.json").write_text(json.dumps(transition), encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(self.repository)], check=True)
        subprocess.run(
            ["git", "-C", str(self.repository), "config", "user.email", "test@example.com"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(self.repository), "config", "user.name", "Test"],
            check=True,
        )
        subprocess.run(["git", "-C", str(self.repository), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(self.repository), "commit", "-qm", "test fixture"],
            check=True,
        )
        self.live_entrypoint = self.runtime_root / "scripts" / "agent_graph.py"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def run_cli(self, entrypoint: Path, command: str, *arguments: str):
        return subprocess.run(
            [
                sys.executable,
                str(entrypoint),
                command,
                "--repo",
                str(self.repository),
                "--json",
                *arguments,
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    def result(self, completed: subprocess.CompletedProcess[str]):
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)["result"]
        if "state" not in result:
            states = sorted((self.repository / "openspec/runs/pinning").glob("*/state.json"))
            if len(states) == 1:
                result["state"] = json.loads(states[0].read_text(encoding="utf-8"))
        return result

    def run_emitted_command(self, command: str):
        arguments: str | list[str]
        if os.name == "nt":
            arguments = command
        else:
            arguments = shlex.split(command)
        return subprocess.run(
            arguments,
            cwd=self.repository,
            check=False,
            capture_output=True,
            text=True,
        )

    def bootstrap(self, run_id: str = "run-1"):
        result = self.result(
            self.run_cli(
                self.live_entrypoint,
                "bootstrap",
                "--change",
                "pinning",
                "--run-id",
                run_id,
                "--bootstrap-id",
                "bootstrap-1",
                "--driver",
                "host",
            )
        )
        return result, Path(result["control_runtime"]["entrypoint"])

    def claim(self, entrypoint: Path, capsule_path: str):
        return self.result(
            self.run_cli(
                entrypoint,
                "claim-coordinator",
                "--coordinator-capsule",
                capsule_path,
                "--coordinator-id",
                "coordinator-1",
            )
        )

    def finish_task(self, entrypoint: Path, task_id: str, changed_path: str) -> None:
        dispatched = self.result(
            self.run_cli(
                entrypoint, "dispatch", "--change", "pinning", "--run-id", "run-1",
                "--generation", "2", "--task", task_id, "--local",
            )
        )
        check = next(task.check for task in self.graph.tasks if task.id == task_id)
        report = {
            "task_id": task_id,
            "attempt_id": dispatched["attempt_id"],
            "outcome": "reported",
            "summary": f"The pinned runtime exercised {task_id}.",
            "files_changed": [changed_path],
            "checks_run": [check],
            "evidence_refs": [],
            "questions": [],
            "external_refs": {},
        }
        self.result(self.run_cli(entrypoint, "record-result", "--change", "pinning", "--run-id", "run-1", "--generation", "2", "--attempt", dispatched["attempt_id"], "--result-json", json.dumps(report)))
        self.result(self.run_cli(entrypoint, "run-check", "--change", "pinning", "--run-id", "run-1", "--generation", "2", "--task", task_id))
        self.result(self.run_cli(entrypoint, "grade", "--change", "pinning", "--run-id", "run-1", "--generation", "2", "--task", task_id, "--grade", "pass", "--note", "The focused runtime check passed."))

    def test_creates_the_snapshot_before_the_journal_and_excludes_run_content(self) -> None:
        bootstrap, entrypoint = self.bootstrap()
        run_directory = self.repository / "openspec" / "runs" / "pinning" / "run-1"
        reference = bootstrap["control_runtime"]
        capsule = json.loads(
            (self.repository / bootstrap["capsule_path"]).read_text(encoding="utf-8")
        )
        first_event = json.loads(
            (run_directory / "events.jsonl").read_text(encoding="utf-8").splitlines()[0]
        )

        self.assertTrue(entrypoint.is_absolute())
        self.assertTrue(entrypoint.is_file())
        self.assertEqual(capsule["control_runtime"], reference)
        self.assertEqual(first_event["data"]["control_runtime"], reference)
        self.assertIn(str(entrypoint), capsule["resume_command"])
        self.assertLessEqual(reference["creation_receipt"]["created_at"], first_event["timestamp"])
        snapshot_files = {
            path.relative_to(Path(reference["directory"])).as_posix()
            for path in Path(reference["directory"]).rglob("*")
            if path.is_file()
        }
        self.assertNotIn("openspec/changes/pinning/tasks.md", snapshot_files)
        self.assertFalse(any("terminal" in path for path in snapshot_files))
        self.assertFalse(os.stat(entrypoint).st_mode & stat.S_IWUSR)

    def test_executes_the_emitted_handoff_with_the_pinned_parser(self) -> None:
        bootstrap, entrypoint = self.bootstrap()
        capsule = json.loads(
            (self.repository / bootstrap["capsule_path"]).read_text(encoding="utf-8")
        )
        coordinator_id = f"coordinator-generation-{capsule['coordinator_generation']}"

        claimed = self.result(self.run_emitted_command(capsule["resume_command"]))

        self.assertIn(str(entrypoint), capsule["resume_command"])
        self.assertIn(f"--coordinator-id {coordinator_id}", capsule["resume_command"])
        self.assertEqual(claimed["state"]["coordinator"]["id"], coordinator_id)

    def test_uses_the_snapshot_after_live_modules_are_deleted_or_partially_written(self) -> None:
        bootstrap, entrypoint = self.bootstrap()
        self.live_entrypoint.unlink()
        (self.runtime_root / "scripts" / "runtime_config.py").write_text(
            "def partial_write(\n", encoding="utf-8"
        )

        claimed = self.claim(entrypoint, bootstrap["capsule_path"])
        takeover = self.result(
            self.run_cli(
                entrypoint,
                "takeover",
                "--change",
                "pinning",
                "--run-id",
                "run-1",
                "--generation",
                "2",
                "--coordinator-id",
                "coordinator-2",
            )
        )

        self.assertEqual(claimed["state"]["driver"], "host")
        self.assertEqual(takeover["coordinator_generation"], 3)

    def test_dispatches_from_the_pinned_policy_after_the_source_changes(self) -> None:
        bootstrap, entrypoint = self.bootstrap()
        self.claim(entrypoint, bootstrap["capsule_path"])
        runtime_policy = Path(bootstrap["control_runtime"]["directory"]) / "references" / "routing-policy.seed.json"
        original_policy = self.live_policy.read_bytes()

        self.assertEqual(runtime_policy.read_bytes(), original_policy)
        self.live_policy.write_text("{}\n", encoding="utf-8")
        dispatched = self.result(
            self.run_cli(
                entrypoint,
                "dispatch",
                "--change",
                "pinning",
                "--run-id",
                "run-1",
                "--generation",
                "2",
                "--task",
                "PIN-01",
                "--local",
            )
        )

        attempt = dispatched["state"]["attempts"][dispatched["attempt_id"]]
        self.assertEqual(
            attempt["routing_summary"]["policy_source"],
            "skills/impl/references/routing-policy.seed.json",
        )
        self.assertEqual(
            attempt["routing_summary"]["policy_digest"],
            "sha256:" + hashlib.sha256(
                json.dumps(json.loads(original_policy), separators=(",", ":"), sort_keys=True).encode("utf-8")
            ).hexdigest(),
        )

    def test_rejects_digest_protocol_source_revision_and_entrypoint_divergence(self) -> None:
        for field in ("digest", "protocol", "source", "entrypoint"):
            with self.subTest(field=field):
                run_id = f"run-{field}"
                bootstrap, entrypoint = self.bootstrap(run_id)
                run_directory = self.repository / "openspec" / "runs" / "pinning" / run_id
                reference_path = run_directory / "control-runtime-ref.json"
                reference = json.loads(reference_path.read_text(encoding="utf-8"))
                if field == "digest":
                    target = Path(reference["directory"]) / "references" / "run-state.schema.json"
                    target.chmod(stat.S_IMODE(target.stat().st_mode) | stat.S_IWUSR)
                    target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")
                elif field == "protocol":
                    reference["protocol_version"] = 2
                    reference_path.write_text(json.dumps(reference), encoding="utf-8")
                elif field == "source":
                    reference["source_revision"] = "divergent-revision"
                    reference_path.write_text(json.dumps(reference), encoding="utf-8")
                else:
                    reference["entrypoint"] = str(self.live_entrypoint.resolve())
                    reference_path.write_text(json.dumps(reference), encoding="utf-8")

                resumed = self.run_cli(
                    entrypoint,
                    "resume",
                    "--change",
                    "pinning",
                    "--run-id",
                    run_id,
                    "--generation",
                    "2",
                )

                self.assertNotEqual(resumed.returncode, 0)
                error = json.loads(resumed.stderr)["error"]
                self.assertEqual(error["code"], "control_runtime_invalid")

    def test_releases_the_snapshot_only_after_the_run_is_terminal(self) -> None:
        bootstrap, entrypoint = self.bootstrap()
        self.claim(entrypoint, bootstrap["capsule_path"])
        run_directory = self.repository / "openspec" / "runs" / "pinning" / "run-1"
        snapshot = run_directory / "control-runtime"
        self.assertTrue(snapshot.is_dir())

        self.finish_task(entrypoint, "PIN-01", "src/pin.py")
        self.finish_task(entrypoint, "PIN-02", "src/pin_aux.py")
        self.assertTrue(snapshot.is_dir())

        completed = self.result(
            self.run_cli(
                entrypoint,
                "complete",
                "--change",
                "pinning",
                "--run-id",
                "run-1",
                "--generation",
                "2",
                "--outcome",
                "pass",
            )
        )

        self.assertTrue(completed["control_runtime_released"])
        self.assertFalse(snapshot.exists())


if __name__ == "__main__":
    unittest.main()
