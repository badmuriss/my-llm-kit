import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

HOST_SCRIPT = SCRIPTS / "drivers" / "host.py"
SPEC = importlib.util.spec_from_file_location("host_driver", HOST_SCRIPT)
assert SPEC and SPEC.loader
host_driver = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = host_driver
SPEC.loader.exec_module(host_driver)

import graph_core


TASKS = """# Tasks

- [ ] DOMAIN-01 Build the domain
  Depends: []
  Paths: [src/domain/]
  Mode: write
  Isolation: auto
  Acceptance: The domain exists.
  Check: python3 -m unittest tests.test_domain

- [ ] API-02 Expose the domain
  Depends: [DOMAIN-01]
  Paths: [src/api/, tests/test_api.py]
  Mode: write
  Isolation: auto
  Context: Keep the API change bounded.
  Acceptance: The API exposes the domain.
  Check: python3 -m unittest tests.test_api
"""


class HostDriverBehavior(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repository = Path(self.temporary_directory.name)
        self.run_directory = self.repository / "openspec" / "runs" / "change" / "run-1"
        self.driver = host_driver.HostDriver(self.repository, self.run_directory)
        self.graph = graph_core.parse_task_graph(TASKS)
        self.root, self.api = self.graph.tasks
        self.projection = {
            "tasks": {
                "DOMAIN-01": {
                    "contract": self.root.to_dict(),
                    "status": "pass",
                    "grade": "pass",
                    "attempt_ids": ["attempt-root"],
                },
                "API-02": {
                    "contract": self.api.to_dict(),
                    "status": "ready",
                    "grade": None,
                    "attempt_ids": [],
                },
            },
            "attempts": {
                "attempt-root": {
                    "task_id": "DOMAIN-01",
                    "driver": "host",
                    "status": "reported",
                    "report": {
                        "summary": "Built the validated domain.",
                        "files_changed": ["src/domain/model.py"],
                        "evidence_refs": ["file:artifacts/domain-check.txt"],
                    },
                }
            },
        }

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_starts_a_ready_task_with_only_bounded_capsule_sections(self) -> None:
        receipt = self.driver.start_attempt(
            self.attempt(worker_handle="native-worker-7")
        )

        capsule = json.loads(
            (self.repository / receipt.raw["capsule_path"]).read_text()
        )
        self.assertEqual(set(capsule), host_driver.CAPSULE_FIELDS)
        self.assertEqual(capsule["task"]["id"], "API-02")
        self.assertNotIn("Built the validated domain.", json.dumps(capsule["task"]))
        self.assertEqual(
            capsule["dependency_digest"],
            [
                {
                    "task_id": "DOMAIN-01",
                    "grade": "pass",
                    "summary": "Built the validated domain.",
                    "files_changed": ["src/domain/model.py"],
                    "evidence_refs": ["file:artifacts/domain-check.txt"],
                }
            ],
        )
        self.assertFalse(capsule["driver_instructions"]["coordinator"])
        self.assertEqual(
            receipt.external_refs["worker_handle"], "native-worker-7"
        )

    def test_rejects_a_task_until_every_dependency_passes(self) -> None:
        with self.assertRaisesRegex(host_driver.HostDriverError, "not ready"):
            self.driver.start_attempt(
                self.attempt(
                    dependency_digest=[
                        {"task_id": "DOMAIN-01", "grade": "fail"}
                    ]
                )
            )

    def test_conforms_to_the_shared_driver_receipt_boundary(self) -> None:
        detected = self.driver.detect()
        run = self.driver.start_run(
            "Implement the portable graph",
            [self.root.to_dict(), self.api.to_dict()],
        )
        started = self.driver.start_attempt(self.attempt())
        pending = self.driver.poll(self.attempt())
        sent = self.driver.send(
            self.attempt(worker_handle="native-worker-7"),
            {"kind": "guidance", "body": "Keep the change bounded."},
        )
        released = self.driver.release(
            self.attempt(worker_handle="native-worker-7")
        )

        self.assertEqual(detected.status, "available")
        self.assertEqual(run.status, "started")
        self.assertEqual(started.external_refs["tier"], "host-native")
        self.assertEqual(pending.raw["events"], [])
        self.assertEqual(sent.status, "host-delivery-required")
        self.assertEqual(released.status, "released")

    def test_records_a_schema_valid_result_as_reported_without_grading(self) -> None:
        self.driver.start_attempt(self.attempt())

        receipt = self.driver.record_result(
            self.api,
            "attempt-api",
            self.valid_result(),
        )

        self.assertEqual(receipt.raw["event"], "worker_reported")
        self.assertEqual(receipt.status, "reported")
        self.assertNotIn("grade", receipt.to_dict())
        self.assertEqual(
            self.driver.read_result(self.api, "attempt-api")["summary"],
            "Implemented the API.",
        )

    def test_rejects_malformed_mismatched_and_out_of_scope_results(self) -> None:
        self.driver.start_attempt(self.attempt())
        malformed = self.valid_result()
        del malformed["summary"]
        mismatched = self.valid_result()
        mismatched["attempt_id"] = "attempt-other"
        out_of_scope = self.valid_result()
        out_of_scope["files_changed"] = ["README.md"]

        for result in (malformed, mismatched, out_of_scope):
            with self.subTest(result=result):
                with self.assertRaises(host_driver.HostDriverError):
                    self.driver.record_result(self.api, "attempt-api", result)

        self.assertFalse((self.run_directory / "results" / "attempt-api.json").exists())

    def test_rejects_a_duplicate_terminal_result(self) -> None:
        self.driver.start_attempt(self.attempt())
        self.driver.record_result(self.api, "attempt-api", self.valid_result())

        with self.assertRaises(host_driver.DuplicateResultError):
            self.driver.record_result(self.api, "attempt-api", self.valid_result())

    def test_applies_the_same_result_contract_to_local_execution(self) -> None:
        self.driver.start_attempt(self.attempt(attempt_id="attempt-local", local=True))
        invalid = self.valid_result(attempt_id="attempt-local")
        invalid["files_changed"] = ["outside.py"]

        with self.assertRaises(host_driver.HostDriverError):
            self.driver.record_local_result(self.api, "attempt-local", invalid)

        valid = self.valid_result(attempt_id="attempt-local")
        receipt = self.driver.record_local_result(self.api, "attempt-local", valid)
        self.assertEqual(receipt.status, "reported")

    def test_reconciles_repository_state_without_a_live_worker_handle(self) -> None:
        self.driver.start_attempt(self.attempt())
        result_path = self.run_directory / "results" / "attempt-api.json"
        result_path.parent.mkdir(parents=True)
        result_path.write_text(json.dumps(self.valid_result()), encoding="utf-8")
        resumed_attempt = {
            "task_id": "API-02",
            "driver": "host",
            "status": "running",
            "attempt_id": "attempt-api",
            "task": self.api.to_dict(),
            "dependency_digest": host_driver.dependency_digest_from_projection(
                self.api, self.projection
            ),
        }
        resumed_driver = host_driver.HostDriver(self.repository, self.run_directory)

        receipt = resumed_driver.reconcile([resumed_attempt])

        observation = next(
            item for item in receipt.raw if item["attempt_id"] == "attempt-api"
        )
        self.assertIsNone(observation["worker_handle"])
        self.assertEqual(observation["event"]["type"], "worker_reported")
        self.assertEqual(observation["event"]["result"]["outcome"], "reported")

    def test_returns_the_exact_manual_fresh_coordinator_invocation(self) -> None:
        path = "openspec/runs/change/run-1/capsules/coordinator.json"

        self.assertEqual(
            host_driver.coordinator_capsule_invocation(path),
            f"$impl --coordinator-capsule {path}",
        )
        receipt = self.driver.coordinator_handoff(
            path,
            visible_fresh_session_handoff=False,
        )
        self.assertEqual(receipt.status, "manual-handoff-required")
        self.assertFalse(receipt.raw["continue_in_bootstrap"])

    def attempt(
        self,
        *,
        attempt_id: str = "attempt-api",
        worker_handle: str | None = None,
        local: bool = False,
        dependency_digest=None,
    ) -> dict[str, object]:
        if dependency_digest is None:
            dependency_digest = host_driver.dependency_digest_from_projection(
                self.api, self.projection
            )
        return {
            "task_id": self.api.id,
            "attempt_id": attempt_id,
            "task": self.api.to_dict(),
            "dependency_digest": dependency_digest,
            "worker_handle": worker_handle,
            "local": local,
        }

    def valid_result(self, *, attempt_id: str = "attempt-api") -> dict[str, object]:
        return {
            "task_id": "API-02",
            "attempt_id": attempt_id,
            "outcome": "reported",
            "summary": "Implemented the API.",
            "files_changed": ["src/api/handler.py", "tests/test_api.py"],
            "checks_run": ["python3 -m unittest tests.test_api"],
            "evidence_refs": ["file:artifacts/api-check.txt"],
            "questions": [],
            "external_refs": {},
        }


if __name__ == "__main__":
    unittest.main()
