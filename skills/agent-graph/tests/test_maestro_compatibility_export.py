from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).parents[3]
SCRIPTS = ROOT / "skills" / "agent-graph" / "scripts"
SCRIPT = SCRIPTS / "export_maestro_compatibility.py"
CLI = SCRIPTS / "agent_graph.py"
REFERENCES = ROOT / "skills" / "agent-graph" / "references"
CHANGE = "compatibility-producer"
RUN_ID = "public-run"
CHECK = f'"{sys.executable}" -c "raise SystemExit(0)"'
CAPABILITY_TASKS = (
    "MLK-05", "MLK-05R", "MLK-06R", "MLK-06D", "MLK-06Q", "MLK-07", "MLK-07P", "MLK-20",
)
PRODUCER_TASKS = (*CAPABILITY_TASKS, "MLK-06QR", "MLK-15", "MLK-19")

sys.path.insert(0, str(SCRIPTS))
import agent_graph as runtime  # noqa: E402
import export_maestro_compatibility as exporter  # noqa: E402


def cli(repository: Path, command: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), command, "--repo", str(repository), "--json", *arguments],
        capture_output=True, text=True, check=False,
    )


def result(completed: subprocess.CompletedProcess[str]) -> dict[str, object]:
    if completed.returncode != 0:
        raise AssertionError(completed.stderr)
    return json.loads(completed.stdout)["result"]


def create_public_producer(parent: Path) -> Path:
    repository = parent / "producer"
    change = repository / "openspec" / "changes" / CHANGE
    change.mkdir(parents=True)
    task_sections = []
    for task_id in PRODUCER_TASKS:
        checked = " " if task_id == "MLK-20" else "x"
        relative = f"src/{task_id.lower()}.txt"
        task_sections.append(
            f"- [{checked}] {task_id} Produce {task_id} authority\n"
            "  Depends: []\n"
            f"  Paths: [{relative}]\n"
            "  Mode: write\n"
            "  Isolation: auto\n"
            f"  Acceptance: Public producer records {task_id}.\n"
            f"  Check: {CHECK}\n"
        )
        source = repository / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("initial\n", encoding="utf-8")
    (change / "tasks.md").write_text("# Tasks\n\n" + "\n".join(task_sections), encoding="utf-8")
    for name in ("proposal.md", "design.md"):
        (change / name).write_text("# Compatibility producer\n", encoding="utf-8")
    graph = runtime.parse_task_graph(change / "tasks.md")
    decision = runtime.decide_process(
        repository,
        request="Produce immutable compatibility authority through the public CLI.",
        check_command=CHECK,
        signals={
            "known_scope": True,
            "graph_requested": True,
            "cohesion": "independent",
            "independent_packets": [
                {"packet_id": task.id, "paths": list(task.paths), "check": {"command": task.check, "oracle": f"{task.id} passes."}}
                for task in graph.tasks
            ],
            "integrator": "coordinator-public",
            "permission_observed": True,
            "budget_limits": [{"resource": "workers", "value": 1, "unit": "workers", "rationale": "One public local producer."}],
            "cleanup_plan": "The public check runner verifies its owned process cleanup.",
        },
    )
    (change / "process-decision.json").write_text(json.dumps(decision), encoding="utf-8")
    for command in (
        ["git", "init", "-q", str(repository)],
        ["git", "-C", str(repository), "config", "user.email", "test@example.com"],
        ["git", "-C", str(repository), "config", "user.name", "Test"],
        ["git", "-C", str(repository), "add", "."],
        ["git", "-C", str(repository), "commit", "-qm", "fixture"],
    ):
        subprocess.run(command, check=True, capture_output=True, text=True)
    common = ("--change", CHANGE, "--run-id", RUN_ID)
    bootstrap = result(cli(repository, "bootstrap", *common, "--bootstrap-id", "bootstrap-public", "--driver", "host"))
    result(cli(repository, "claim-coordinator", "--capsule", str(bootstrap["capsule_path"]), "--coordinator-id", "coordinator-public"))
    authority = (*common, "--generation", "2")
    for task_id in PRODUCER_TASKS:
        if task_id != "MLK-20":
            result(cli(repository, "import-checked-task", *authority, "--task", task_id, "--import-id", f"import-{task_id}", "--note", f"Public checked producer for {task_id}."))
    dispatched = result(cli(repository, "dispatch", *authority, "--task", "MLK-20", "--local"))
    attempt_id = str(dispatched["attempt_id"])
    (repository / "src" / "mlk-20.txt").write_text("implemented\n", encoding="utf-8")
    policy_ref = f"file:openspec/runs/{CHANGE}/{RUN_ID}/artifacts/routing-policy-v1.json"
    report = {
        "task_id": "MLK-20", "attempt_id": attempt_id, "outcome": "reported",
        "summary": "The public producer pinned and exercised RoutingPolicy v1.",
        "files_changed": ["src/mlk-20.txt"], "checks_run": [CHECK], "evidence_refs": [policy_ref],
        "questions": [], "external_refs": {},
    }
    result(cli(repository, "record-result", *authority, "--attempt", attempt_id, "--result-json", json.dumps(report)))
    result(cli(repository, "run-check", *authority, "--task", "MLK-20"))
    result(cli(repository, "grade", *authority, "--task", "MLK-20", "--grade", "pass", "--note", "The public producer binds its pinned policy.", "--evidence-ref", policy_ref))
    result(cli(repository, "cleanup-register", *authority, "--cleanup-id", "fixture-cleanup", "--kind", "temp_path", "--target", str(repository / "missing-cleanup-target"), "--owner", "fixture-owner"))
    result(cli(repository, "cleanup-finish", *authority, "--cleanup-id", "fixture-cleanup"))
    result(cli(repository, "complete", *authority, "--outcome", "pass"))
    return repository


class MaestroCompatibilityExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.producer_temp = tempfile.TemporaryDirectory()
        cls.producer = create_public_producer(Path(cls.producer_temp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.producer_temp.cleanup()

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.repository = root / "producer"
        shutil.copytree(self.producer, self.repository)
        runtime_directory = self.run_directory / "control-runtime"
        if runtime_directory.exists():
            shutil.rmtree(runtime_directory)
        self.output = root / "consumer-output"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @property
    def run_directory(self) -> Path:
        return self.repository / "openspec" / "runs" / CHANGE / RUN_ID

    def export(self, *, output: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(self.repository), "--change", CHANGE, "--run-id", RUN_ID, "--output", str(output or self.output)],
            capture_output=True, text=True, check=False,
        )

    def state(self) -> dict[str, object]:
        return json.loads((self.run_directory / "state.json").read_text(encoding="utf-8"))

    def write_state(self, state: dict[str, object]) -> None:
        (self.run_directory / "state.json").write_text(json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

    def assert_rejected(self, completed: subprocess.CompletedProcess[str]) -> None:
        self.assertNotEqual(completed.returncode, 0, completed.stdout)
        self.assertFalse(self.output.exists())

    def exported_manifest(self) -> tuple[Path, dict[str, object]]:
        completed = self.export()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        reported = json.loads(completed.stdout)
        manifest = Path(reported["manifest"])
        self.assertEqual(manifest, Path(reported["bundle"]) / "manifest.json")
        return manifest, json.loads(manifest.read_text(encoding="utf-8"))

    def test_exports_eight_receipts_with_canonical_producer_sets(self) -> None:
        manifest_path, manifest = self.exported_manifest()
        self.assertEqual([entry["task_id"] for entry in manifest["receipts"]], list(CAPABILITY_TASKS))
        progress = json.loads((manifest_path.parent / "receipts" / "MLK-07P.json").read_text())
        quarantine = json.loads((manifest_path.parent / "receipts" / "MLK-06Q.json").read_text())
        routing = json.loads((manifest_path.parent / "receipts" / "MLK-20.json").read_text())
        self.assertEqual([item["task_id"] for item in progress["required_producers"]], ["MLK-07", "MLK-07P", "MLK-19"])
        self.assertEqual([item["task_id"] for item in quarantine["required_producers"]], ["MLK-06Q", "MLK-06QR", "MLK-15"])
        self.assertEqual(routing["routing_policy"]["policy_id"], json.loads((self.run_directory / "artifacts" / "routing-policy-v1.json").read_text())["policy_id"])

    def test_reuses_the_same_content_addressed_bundle(self) -> None:
        first, _manifest = self.exported_manifest()
        second = self.export()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(first, Path(json.loads(second.stdout)["manifest"]))

    def test_rejects_policy_bytes_and_routing_summary_tamper(self) -> None:
        policy_path = self.run_directory / "artifacts" / "routing-policy-v1.json"
        original_bytes = policy_path.read_bytes()
        policy = json.loads(original_bytes)
        policy["policy_id"] = "forged-policy"
        policy_path.write_text(json.dumps(policy, sort_keys=True, separators=(",", ":")) + "\n")
        self.assert_rejected(self.export())
        policy_path.write_bytes(original_bytes)
        state = self.state()
        attempt_id = state["tasks"]["MLK-20"]["check"]["attempt_id"]
        state["attempts"][attempt_id]["routing_summary"]["policy_digest"] = "sha256:" + "0" * 64
        self.write_state(state)
        self.assert_rejected(self.export())

    def test_rejects_forged_check_execution_authority(self) -> None:
        state = self.state()
        task = state["tasks"]["MLK-05"]
        artifact = self.repository / task["check"]["evidence_ref"].removeprefix("file:")
        original_document = json.loads(artifact.read_text())
        for field, value in (
            ("execution_id", "check-forged"),
            ("command_digest", "sha256:" + "0" * 64),
            ("source_snapshot_digest", "sha256:" + "1" * 64),
            ("exit_code", 1),
            ("timed_out", True),
        ):
            with self.subTest(field=field):
                artifact.write_text(json.dumps({**original_document, field: value}, sort_keys=True, separators=(",", ":")) + "\n")
                self.assert_rejected(self.export())
        artifact.write_text(json.dumps(original_document, sort_keys=True, separators=(",", ":")) + "\n")
        execution = next(item for item in state["check_executions"].values() if item["artifact_ref"] == task["check"]["artifact"])
        execution["consumer_refs"] = ["import:MLK-05:forged"]
        self.write_state(state)
        self.assert_rejected(self.export())

    def test_accepts_exact_legacy_ordinary_no_status_artifact(self) -> None:
        legacy = ROOT / "openspec" / "runs" / "maestro-harness-orchestration" / "maestro-harness-20260823T072820Z"
        state = json.loads((legacy / "state.json").read_text())
        check = state["tasks"]["MLK-15"]["check"]
        document = json.loads((ROOT / check["artifact"]).read_text())
        self.assertNotIn("status", document)
        evidence, execution = exporter._check_evidence(ROOT, state, {}, check, "MLK-15", exporter.CHECK_RECORDED, None)
        self.assertEqual(evidence["ref"], f"file:{check['artifact']}")
        self.assertIsNone(execution)

    def test_accepts_exact_legacy_done_cleanup_with_verified_receipt(self) -> None:
        legacy = ROOT / "openspec" / "runs" / "maestro-harness-orchestration" / "maestro-harness-20260823T121943Z"
        state = json.loads((legacy / "state.json").read_text())
        candidates = [item for item in state["cleanup"].values() if item.get("status") == "done" and item.get("receipt", {}).get("status") == "verified"]
        self.assertTrue(candidates)
        for cleanup in candidates:
            self.assertIsInstance(cleanup["owner"], str)
            self.assertNotIn("identity_version", cleanup)
            self.assertEqual(cleanup["receipt"]["status"], "verified")
        exporter._verify_cleanup(state)

    def test_rejects_incomplete_partial_and_unresolved_runs(self) -> None:
        journal = self.run_directory / "events.jsonl"
        original = journal.read_bytes()
        journal.write_bytes(original.rstrip(b"\n"))
        self.assert_rejected(self.export())
        journal.write_bytes(original)
        state = self.state()
        state["outcome"] = "partial"
        self.write_state(state)
        self.assert_rejected(self.export())
        state["outcome"] = "pass"
        next(iter(state["cleanup"].values()))["status"] = "retained"
        self.write_state(state)
        self.assert_rejected(self.export())

    def test_rejects_missing_producer_and_workspace_mismatch(self) -> None:
        state = self.state()
        del state["tasks"]["MLK-19"]
        self.write_state(state)
        self.assert_rejected(self.export())
        state = self.state()
        state["workspace_scope"]["execution_workspace"]["workspace_key"] = "folder:forged"
        self.write_state(state)
        self.assert_rejected(self.export())

    def test_rejects_symlink_traversal_and_partial_collision(self) -> None:
        linked_output = Path(self.temporary.name) / "linked-output"
        os.symlink(Path(self.temporary.name), linked_output)
        self.assertNotEqual(self.export(output=linked_output).returncode, 0)
        traversal = Path(self.temporary.name) / "nested" / ".." / "output"
        self.assertNotEqual(self.export(output=traversal).returncode, 0)
        manifest, _value = self.exported_manifest()
        manifest.write_text("{}\n")
        collision = self.export()
        self.assertNotEqual(collision.returncode, 0)
        self.assertIn("collision", collision.stderr)

    def test_validates_closed_schemas_and_strict_unions(self) -> None:
        manifest_path, manifest = self.exported_manifest()
        manifest_validator = Draft202012Validator(json.loads((REFERENCES / "maestro-compatibility-manifest.schema.json").read_text()))
        receipt_validator = Draft202012Validator(json.loads((REFERENCES / "maestro-capability-receipt.schema.json").read_text()))
        manifest_validator.validate(manifest)
        receipts = {task_id: json.loads((manifest_path.parent / "receipts" / f"{task_id}.json").read_text()) for task_id in ("MLK-05", "MLK-06Q", "MLK-07P", "MLK-20")}
        for receipt in receipts.values():
            receipt_validator.validate(receipt)
        forged = copy.deepcopy(receipts["MLK-05"])
        forged["routing_policy"] = receipts["MLK-20"]["routing_policy"]
        self.assertTrue(list(receipt_validator.iter_errors(forged)))
        wrong_group = copy.deepcopy(receipts["MLK-07P"])
        wrong_group["required_producers"] = receipts["MLK-06Q"]["required_producers"]
        self.assertTrue(list(receipt_validator.iter_errors(wrong_group)))
        short_manifest = copy.deepcopy(manifest)
        short_manifest["receipts"].pop()
        self.assertTrue(list(manifest_validator.iter_errors(short_manifest)))


if __name__ == "__main__":
    unittest.main()
