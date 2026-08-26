import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from skills.impl.scripts.learning import LearningError, lifecycle_fact, lifecycle_facts


class LearningReceiptNormalizationTests(unittest.TestCase):
    def _fixture_state(self):
        return __import__("json").loads((Path(__file__).parent / "fixtures/learning/cleanup-aborted-import-process-1368425.json").read_text())

    def _terminal_fixture_state(self):
        return __import__("json").loads((Path(__file__).parent / "fixtures/learning/coordinator-terminal-cleanup.json").read_text())

    def _process_with_terminal_identity_fixture_state(self):
        return __import__("json").loads(
            (Path(__file__).parent / "fixtures/learning/coordinator-process-cleanup-with-terminal-identity.json").read_text()
        )

    def test_reads_execution_workspace_and_keeps_coordinator_cleanup_run_level(self) -> None:
        state = self._fixture_state()
        fixture = state["cleanup"]["cleanup-aborted-import-process-1368425"]
        tasks, run_lifecycle = lifecycle_facts(state, repo=Path("."), run_root=Path("openspec/runs/change/run"))
        self.assertEqual(tasks, {})
        self.assertEqual(run_lifecycle[0]["target"], fixture["target"])
        self.assertEqual(run_lifecycle[0]["owner"], fixture["owner"])
        self.assertEqual(fixture["receipt"]["descendant_pids"], [1369539, 1369540, 1369541, 1376657])
        self.assertIsNone(fixture["owner"]["terminal_id"])
        self.assertIsNone(fixture["owner"]["incarnation_id"])
        self.assertEqual(fixture["receipt"]["owner"], fixture["owner"])
        self.assertEqual(fixture["receipt"]["target"], fixture["target"])
        self.assertIsNone(run_lifecycle[0]["attempt_id"])
        for field in ("receipt_id", "receipt_path", "sha256", "byte_length"):
            self.assertIsNone(run_lifecycle[0][field])

    def test_normalizes_attempt_cleanup_without_coordinator_fields(self) -> None:
        state = {
            "attempts": {
                "attempt-1": {"task_id": "MLK-10", "status": "complete"},
            },
            "cleanup": {
                "cleanup-attempt-1": {
                    "attempt_id": "attempt-1",
                    "kind": "process",
                    "status": "verified",
                },
            },
        }

        tasks, run_lifecycle = lifecycle_facts(
            state, repo=Path("."), run_root=Path("openspec/runs/change/run")
        )

        self.assertEqual(run_lifecycle, [])
        cleanup_fact = next(fact for fact in tasks["MLK-10"] if fact["kind"] == "cleanup")
        self.assertEqual(cleanup_fact["attempt_id"], "attempt-1")
        self.assertEqual(cleanup_fact["entity_id"], "cleanup-attempt-1")

    def test_normalizes_verified_and_retained_terminal_cleanup_from_real_receipts(self) -> None:
        state = self._terminal_fixture_state()
        _, run_lifecycle = lifecycle_facts(state, repo=Path("."), run_root=Path("openspec/runs/change/run"))

        self.assertEqual(len(run_lifecycle), 2)
        for fact in run_lifecycle:
            fixture = state["cleanup"][fact["entity_id"]]
            self.assertEqual(fact["target"], fixture["owner"]["terminal_id"])
            self.assertEqual(fact["owner"], fixture["owner"])
            self.assertIsNone(fact["owner"]["process_root"])
            self.assertEqual(fact["status"], fixture["status"])

    def test_preserves_process_cleanup_terminal_identity_from_real_receipt(self) -> None:
        state = self._process_with_terminal_identity_fixture_state()
        _, run_lifecycle = lifecycle_facts(state, repo=Path("."), run_root=Path("openspec/runs/change/run"))

        self.assertEqual(len(run_lifecycle), 1)
        fact = run_lifecycle[0]
        fixture = state["cleanup"][fact["entity_id"]]
        self.assertEqual(fact["target"], fixture["target"])
        self.assertEqual(fact["owner"], fixture["owner"])
        self.assertIsInstance(fact["owner"]["process_root"], int)
        self.assertIsInstance(fact["owner"]["terminal_id"], str)
        self.assertIsInstance(fact["owner"]["incarnation_id"], str)

    def test_rejects_invalid_terminal_cleanup_bindings(self) -> None:
        cases = {
            "null terminal identity": lambda c: c["owner"].update({"terminal_id": None}),
            "null incarnation identity": lambda c: c["owner"].update({"incarnation_id": None}),
            "target mismatch": lambda c: c.update({"target": "term-other"}),
            "receipt terminal mismatch": lambda c: c["receipt"].update({"terminal_id": "term-other"}),
            "receipt incarnation mismatch": lambda c: c["receipt"].update({"incarnation_id": "incarnation-other"}),
            "process-shaped terminal target": lambda c: c.update({"target": {"kind": "process", "root_pid": 7}}),
            "verified retention receipt": lambda c: c["receipt"].update({"kind": "terminal-retention"}),
            "retained verified receipt": lambda c: c["receipt"].update({"kind": "terminal"}),
            "extra owner field": lambda c: c["owner"].update({"extra": True}),
        }
        for label, mutate in cases.items():
            with self.subTest(label=label):
                state = self._terminal_fixture_state()
                cleanup_id = (
                    "cleanup-coordinator-generation-3-terminal"
                    if label == "retained verified receipt"
                    else "cleanup-coordinator-generation-2-terminal"
                )
                cleanup = state["cleanup"][cleanup_id]
                mutate(cleanup)
                with self.assertRaises(LearningError):
                    lifecycle_facts(state, repo=Path("."), run_root=Path("openspec/runs/change/run"))

    def test_rejects_coordinator_receipt_owner_mismatch(self) -> None:
        state = self._fixture_state()
        fixture = state["cleanup"]["cleanup-aborted-import-process-1368425"]
        fixture["receipt"]["owner"]["process_root"] = 999
        with self.assertRaisesRegex(LearningError, "receipt owner"):
            lifecycle_facts(state, repo=Path("."), run_root=Path("openspec/runs/change/run"))

    def test_rejects_fabricated_coordinator_resource_statuses_at_runtime(self) -> None:
        cases = (
            ("process retained", self._fixture_state(), "cleanup-aborted-import-process-1368425", "retained"),
            ("terminal unverifiable", self._terminal_fixture_state(), "cleanup-coordinator-generation-2-terminal", "unverifiable"),
        )
        for label, state, cleanup_id, status in cases:
            with self.subTest(label=label):
                state["cleanup"][cleanup_id]["status"] = status
                state["cleanup"][cleanup_id]["receipt"]["status"] = status
                with self.assertRaises(LearningError):
                    lifecycle_facts(state, repo=Path("."), run_root=Path("openspec/runs/change/run"))

    def test_receipt_schema_rejects_arbitrary_fields(self) -> None:
        import jsonschema

        schema = json.loads((Path(__file__).parents[2] / "skills/impl/references/learning-run.schema.json").read_text())
        run_receipt = lifecycle_facts(self._fixture_state(), repo=Path("."), run_root=Path("openspec/runs/change/run"))[1][0]
        process_with_terminal_identity = lifecycle_facts(
            self._process_with_terminal_identity_fixture_state(), repo=Path("."), run_root=Path("openspec/runs/change/run")
        )[1][0]
        terminal_receipts = lifecycle_facts(self._terminal_fixture_state(), repo=Path("."), run_root=Path("openspec/runs/change/run"))[1]
        task_receipt = {key: run_receipt[key] for key in ("kind", "entity_id", "attempt_id", "phase", "status", "receipt_id", "receipt_path", "sha256", "byte_length")}
        jsonschema.validate(task_receipt, {"$ref": "#/$defs/lifecycleReceipt", "$defs": schema["$defs"]}, format_checker=jsonschema.FormatChecker())
        jsonschema.validate(run_receipt, {"$ref": "#/$defs/runLifecycleReceipt", "$defs": schema["$defs"]}, format_checker=jsonschema.FormatChecker())
        jsonschema.validate(process_with_terminal_identity, {"$ref": "#/$defs/runLifecycleReceipt", "$defs": schema["$defs"]}, format_checker=jsonschema.FormatChecker())
        for terminal_receipt in terminal_receipts:
            jsonschema.validate(terminal_receipt, {"$ref": "#/$defs/runLifecycleReceipt", "$defs": schema["$defs"]}, format_checker=jsonschema.FormatChecker())
        for definition, value in (("lifecycleReceipt", task_receipt), ("runLifecycleReceipt", run_receipt)):
            with self.subTest(definition=definition):
                invalid = dict(value)
                invalid["extra"] = True
                validator = jsonschema.Draft202012Validator({"$ref": f"#/$defs/{definition}", "$defs": schema["$defs"]})
                self.assertTrue(list(validator.iter_errors(invalid)))
        mixed_target = dict(terminal_receipts[0])
        mixed_target["target"] = {"kind": "process", "root_pid": 7}
        validator = jsonschema.Draft202012Validator({"$ref": "#/$defs/runLifecycleReceipt", "$defs": schema["$defs"]})
        self.assertTrue(list(validator.iter_errors(mixed_target)))

        fabricated_terminal_status = dict(terminal_receipts[0])
        fabricated_terminal_status["status"] = "unverifiable"
        self.assertTrue(list(validator.iter_errors(fabricated_terminal_status)))

        fabricated_process_status = dict(run_receipt)
        fabricated_process_status["status"] = "retained"
        self.assertTrue(list(validator.iter_errors(fabricated_process_status)))

    def test_rejects_invalid_cleanup_owner_and_receipt_bindings(self) -> None:
        cases = {
            "missing generation": lambda s, c: c["owner"].pop("coordinator_generation"),
            "malformed owner fields": lambda s, c: c["owner"].update({"extra": True}),
            "generation out of range": lambda s, c: c["owner"].update({"coordinator_generation": 4}),
            "boolean generation": lambda s, c: c["owner"].update({"coordinator_generation": True}),
            "non integer generation": lambda s, c: c["owner"].update({"coordinator_generation": "2"}),
            "mixed ownership": lambda s, c: c["owner"].update({"attempt_id": "attempt-1"}),
            "top-level attempt ownership": lambda s, c: c.update({"attempt_id": "attempt-1"}),
            "host mismatch": lambda s, c: c["owner"].update({"execution_host_id": "other"}),
            "workspace mismatch": lambda s, c: c["owner"].update({"workspace_key": "folder:other"}),
            "target owner mismatch": lambda s, c: (c["target"].update({"root_pid": 7}), c["receipt"]["target"].update({"root_pid": 7})),
            "receipt status mismatch": lambda s, c: c["receipt"].update({"status": "retained"}),
            "receipt kind mismatch": lambda s, c: c["receipt"].update({"kind": "terminal"}),
            "receipt owner mismatch": lambda s, c: c["receipt"]["owner"].update({"process_root": 7}),
            "receipt target mismatch": lambda s, c: c["receipt"]["target"].update({"root_pid": 7}),
            "fabricated untyped owner": lambda s, c: s["cleanup"].update({c["cleanup_id"]: {**c, "owner": "coordinator"}}),
        }
        for label, mutate in cases.items():
            with self.subTest(label=label):
                state = self._fixture_state()
                cleanup = state["cleanup"]["cleanup-aborted-import-process-1368425"]
                mutate(state, cleanup)
                with self.assertRaises(LearningError):
                    lifecycle_facts(state, repo=Path("."), run_root=Path("openspec/runs/change/run"))

    def test_normalizes_pathless_unverifiable_cleanup_to_null_artifact_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fact = lifecycle_fact(
                kind="cleanup",
                entity_id="cleanup-terminal",
                attempt_id="attempt-1",
                phase="cleanup",
                status="unverifiable",
                receipt={"reason": "terminal provider did not return a receipt"},
                repo=Path(directory),
                run_root=Path(directory) / "openspec/runs/change/run-1",
                expected_receipt_kind="terminal",
            )

        self.assertEqual(fact["status"], "unverifiable")
        self.assertIsNone(fact["receipt_id"])
        self.assertIsNone(fact["receipt_path"])
        self.assertIsNone(fact["sha256"])
        self.assertIsNone(fact["byte_length"])

    def test_accepts_matching_kind_for_pathless_verified_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fact = lifecycle_fact(
                kind="cleanup",
                entity_id="cleanup-terminal",
                attempt_id="attempt-1",
                phase="cleanup",
                status="verified",
                receipt={"kind": "terminal", "reason": "verified by provider"},
                repo=Path(directory),
                run_root=Path(directory) / "openspec/runs/change/run-1",
                expected_receipt_kind="terminal",
            )

        self.assertEqual(fact["kind"], "cleanup")
        self.assertEqual(fact["status"], "verified")
        self.assertIsNone(fact["receipt_path"])

    def test_rejects_mismatched_cleanup_kind(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(LearningError, "does not match cleanup kind"):
                lifecycle_fact(
                    kind="cleanup",
                    entity_id="cleanup-terminal",
                    attempt_id="attempt-1",
                    phase="cleanup",
                    status="unverifiable",
                    receipt={"kind": "process"},
                    repo=Path(directory),
                    run_root=Path(directory) / "openspec/runs/change/run-1",
                    expected_receipt_kind="terminal",
                )

    def test_derives_confined_receipt_metadata_and_rejects_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            artifacts = repository / "openspec/runs/change/run-1/artifacts"
            artifacts.mkdir(parents=True)
            content = b"terminal receipt"
            receipt_path = "openspec/runs/change/run-1/artifacts/terminal.json"
            (artifacts / "terminal.json").write_bytes(content)
            fact = lifecycle_fact(
                kind="cleanup",
                entity_id="cleanup-terminal",
                attempt_id="attempt-1",
                phase="cleanup",
                status="verified",
                receipt={
                    "kind": "terminal",
                    "receipt_path": receipt_path,
                    "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
                    "byte_length": len(content),
                },
                repo=repository,
                run_root=repository / "openspec/runs/change/run-1",
                expected_receipt_kind="terminal",
            )
            self.assertEqual(fact["receipt_path"], receipt_path)
            self.assertEqual(fact["byte_length"], len(content))

            with self.assertRaisesRegex(LearningError, "metadata does not match"):
                lifecycle_fact(
                    kind="cleanup",
                    entity_id="cleanup-terminal-2",
                    attempt_id="attempt-1",
                    phase="cleanup",
                    status="verified",
                    receipt={
                        "kind": "terminal",
                        "receipt_path": receipt_path,
                        "sha256": "sha256:" + "0" * 64,
                        "byte_length": len(content),
                    },
                    repo=repository,
                    run_root=repository / "openspec/runs/change/run-1",
                    expected_receipt_kind="terminal",
                )


if __name__ == "__main__":
    unittest.main()
