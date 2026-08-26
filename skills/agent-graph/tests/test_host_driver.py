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
            capsule["workspace_scope"]["execution_workspace"]["kind"],
            "folder",
        )
        self.assertEqual(
            capsule["execution_profile"]["resolved_placement"]["workspace_key"],
            "folder:repo-1",
        )
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

    def test_returns_typed_browser_surface_unavailable_without_guessing_a_browser(self) -> None:
        request = {
            "schema_version": 1, "request_id": "surface-request-1", "task_id": "API-02", "attempt_id": "attempt-api",
            "idempotency_key": "surface-key-1", "mode": "visible", "retention": "release",
            "execution_host_id": "host-local", "workspace_key": "folder:workspace-1", "page_binding": None,
            "binding": {"kind": "initial_url", "value": "https://example.test/preview"},
            "viewport": {"width": 1280, "height": 720}, "source_revision": "commit-123",
        }
        receipt = self.driver.reserve_browser_surface(request)
        surface = receipt.external_refs["browser_surface"]
        self.assertEqual(receipt.status, "unavailable")
        self.assertEqual(surface["unavailability"]["code"], "native-capability-unavailable")
        self.assertIsNone(surface["surface"]["page_binding"])

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

    def test_recovers_an_equivalent_canonical_result_idempotently(self) -> None:
        self.driver.start_attempt(self.attempt())
        self.driver.record_result(self.api, "attempt-api", self.valid_result())

        replay = self.driver.record_result(self.api, "attempt-api", self.valid_result())
        self.assertTrue(replay.raw["recovered_existing_file"])

    def test_validates_the_supplied_candidate_before_recovering_a_canonical_result(self) -> None:
        self.driver.start_attempt(self.attempt())
        self.driver.record_result(self.api, "attempt-api", self.valid_result())
        result_path = self.run_directory / "results" / "attempt-api.json"
        canonical_bytes = result_path.read_bytes()
        invalid_candidate = self.valid_result()
        invalid_candidate["files_changed"] = ["README.md"]

        with self.assertRaisesRegex(host_driver.HostDriverError, "outside task Paths"):
            self.driver.record_result(self.api, "attempt-api", invalid_candidate)

        self.assertEqual(result_path.read_bytes(), canonical_bytes)

    def test_rejects_distinct_or_malformed_canonical_candidates_with_both_digests(self) -> None:
        self.driver.start_attempt(self.attempt())
        result_path = self.run_directory / "results" / "attempt-api.json"
        result_path.parent.mkdir(parents=True)
        result_path.write_text(json.dumps({**self.valid_result(), "summary": "Different."}), encoding="utf-8")

        with self.assertRaisesRegex(host_driver.CanonicalResultConflictError, r"candidate_digest=sha256:[0-9a-f]{64} canonical_digest=sha256:[0-9a-f]{64}") as valid_conflict:
            self.driver.record_result(self.api, "attempt-api", self.valid_result())
        self.assertEqual(valid_conflict.exception.code, "canonical_result_conflict")
        self.assertIn("Different.", result_path.read_text(encoding="utf-8"))

        result_path.write_text("{malformed\n", encoding="utf-8")
        with self.assertRaisesRegex(host_driver.CanonicalResultConflictError, "canonical_result_conflict") as malformed_conflict:
            self.driver.record_result(self.api, "attempt-api", self.valid_result())
        self.assertEqual(malformed_conflict.exception.code, "canonical_result_conflict")
        self.assertEqual(result_path.read_text(encoding="utf-8"), "{malformed\n")

    def test_fails_closed_when_projection_scope_drifts_from_the_capsule(self) -> None:
        attempt = self.attempt()
        attempt["effective_scope"] = {
            "attempt_id": "attempt-api",
            "parent_task_id": "API-02",
            "paths": ["src/api/", "tests/test_api.py"],
            "amendment_ids": ["amend-api"],
        }
        attempt["effective_scope"]["digest"] = host_driver._effective_scope(
            self.api, "attempt-api", attempt["effective_scope"]
        )["digest"]
        self.driver.start_attempt(attempt)
        drifted_projection = {"attempts": {"attempt-api": {"task_id": "API-02", "status": "running", "effective_scope": {**attempt["effective_scope"], "digest": "sha256:" + "0" * 64}}}}

        with self.assertRaisesRegex(host_driver.HostDriverError, "effective_scope drift") as error:
            self.driver.record_result(self.api, "attempt-api", self.valid_result(), projection=drifted_projection)
        self.assertEqual(error.exception.code, "scope_drift")

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
        workspace_scope = {
            "schema_version": 1,
            "repository_id": "repo-1",
            "canonical_root": str(self.repository),
            "execution_host": {"id": "host-local", "boundary": "local"},
            "orchestration_home": {"execution_host_id": "host-local", "workspace_key": "folder:repo-1", "kind": "folder", "path": str(self.repository)},
            "execution_workspace": {"execution_host_id": "host-local", "workspace_key": "folder:repo-1", "kind": "folder", "path": str(self.repository)},
            "base_revision": "0123456789abcdef0123456789abcdef01234567",
            "dirty_paths": [],
            "run_id": "run-1",
            "coordinator_generation": 1,
            "binding_receipt_ref": "artifact:openspec/runs/change/run-1/artifacts/workspace.json",
            "binding_receipt_hash": "sha256:" + "a" * 64,
        }
        return {
            "task_id": self.api.id,
            "attempt_id": attempt_id,
            "task": self.api.to_dict(),
            "dependency_digest": dependency_digest,
            "worker_handle": worker_handle,
            "local": local,
            "workspace_scope": workspace_scope,
            "execution_profile": {
                "role": "implementation",
                "requested": {"lane": "fast", "agent": "codex", "model": "gpt-5.6", "effort": "medium"},
                "resolved": {"agent": "codex", "model": "gpt-5.6", "effort": "medium"},
                "fallback_reason": None,
                "placement_request": {"kind": "current-workspace"},
                "resolved_placement": {
                    "execution_host_id": "host-local",
                    "workspace_key": "folder:repo-1",
                    "kind": "folder",
                    "path": str(self.repository),
                    "receipt_ref": "artifact:openspec/runs/change/run-1/artifacts/current-placement.json",
                },
            },
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
