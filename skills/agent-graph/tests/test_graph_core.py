import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "graph_core.py"
SPEC = importlib.util.spec_from_file_location("graph_core", SCRIPT)
assert SPEC and SPEC.loader
graph_core = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = graph_core
SPEC.loader.exec_module(graph_core)


VALID_TASKS = """# Tasks

- [ ] ROOT-01 Build the domain
  Depends: []
  Paths: [src/domain/, tests/test_domain.py]
  Mode: write
  Isolation: auto
  Context: Keep the implementation bounded.
  Acceptance: The domain behavior is available.
  Check: python3 -m unittest tests.test_domain

- [ ] API-02 Expose the domain
  Depends: [ROOT-01]
  Paths: [src/api/]
  Mode: write
  Isolation: worktree
  Acceptance: The API exposes the domain behavior.
  Check: python3 -m unittest tests.test_api
"""


class GraphParsingBehavior(unittest.TestCase):
    def test_parses_the_complete_task_contract(self) -> None:
        graph = graph_core.parse_task_graph(VALID_TASKS)

        self.assertEqual([task.id for task in graph.tasks], ["ROOT-01", "API-02"])
        self.assertEqual(graph.tasks[0].paths, ("src/domain/", "tests/test_domain.py"))
        self.assertEqual(graph.tasks[1].depends, ("ROOT-01",))
        self.assertEqual(graph.tasks[1].isolation, "worktree")

    def test_rejects_missing_and_duplicate_fields(self) -> None:
        missing = VALID_TASKS.replace("  Mode: write\n", "", 1)
        duplicate = VALID_TASKS.replace(
            "  Mode: write\n", "  Mode: write\n  Mode: read\n", 1
        )

        with self.assertRaisesRegex(graph_core.GraphValidationError, "missing fields: mode"):
            graph_core.parse_task_graph(missing)
        with self.assertRaisesRegex(graph_core.GraphValidationError, "duplicate field mode"):
            graph_core.parse_task_graph(duplicate)

    def test_rejects_unsafe_paths(self) -> None:
        unsafe_paths = ["/tmp/file", "../secret", "src/**", "src\\file.py", "src//file.py"]

        for unsafe_path in unsafe_paths:
            with self.subTest(path=unsafe_path):
                source = VALID_TASKS.replace("src/domain/", unsafe_path, 1)
                with self.assertRaises(graph_core.GraphValidationError):
                    graph_core.parse_task_graph(source)

    def test_rejects_unknown_self_and_cyclic_dependencies(self) -> None:
        unknown = VALID_TASKS.replace("Depends: []", "Depends: [MISSING-99]", 1)
        self_dependency = VALID_TASKS.replace("Depends: []", "Depends: [ROOT-01]", 1)
        cycle = VALID_TASKS.replace("Depends: []", "Depends: [API-02]", 1)

        with self.assertRaisesRegex(graph_core.GraphValidationError, "unknown dependencies"):
            graph_core.parse_task_graph(unknown)
        with self.assertRaisesRegex(graph_core.GraphValidationError, "depend on itself"):
            graph_core.parse_task_graph(self_dependency)
        with self.assertRaisesRegex(graph_core.GraphValidationError, "dependency cycle"):
            graph_core.parse_task_graph(cycle)

    def test_rejects_duplicate_task_ids(self) -> None:
        duplicate = VALID_TASKS.replace("API-02 Expose", "ROOT-01 Expose")

        with self.assertRaisesRegex(graph_core.GraphValidationError, "duplicate task ID"):
            graph_core.parse_task_graph(duplicate)


class SchedulerBehavior(unittest.TestCase):
    def test_requires_passing_dependency_grades(self) -> None:
        graph = graph_core.parse_task_graph(VALID_TASKS)
        projection = {
            "tasks": {
                "ROOT-01": {"grade": None, "status": "pending"},
                "API-02": {"grade": None, "status": "pending"},
            }
        }

        self.assertEqual([task.id for task in graph_core.ready_tasks(graph, projection)], ["ROOT-01"])
        projection["tasks"]["ROOT-01"]["status"] = "reported"
        self.assertEqual([task.id for task in graph_core.ready_tasks(graph, projection)], [])
        projection["tasks"]["ROOT-01"].update(status="pass", grade="pass")
        self.assertEqual([task.id for task in graph_core.ready_tasks(graph, projection)], ["API-02"])

    def test_serializes_overlapping_write_prefixes(self) -> None:
        graph = graph_core.parse_task_graph(
            VALID_TASKS.replace("Depends: [ROOT-01]", "Depends: []").replace(
                "Paths: [src/api/]", "Paths: [src/domain/models.py]"
            )
        )
        projection = {"tasks": {task.id: {"grade": None, "status": "pending"} for task in graph.tasks}}

        ready = graph_core.ready_tasks(graph, projection)

        self.assertEqual([task.id for task in ready], ["ROOT-01"])
        self.assertTrue(graph_core.path_scopes_overlap("src/domain/", "src/domain/models.py"))
        self.assertFalse(graph_core.path_scopes_overlap("src/domain.py", "src/domain/models.py"))

    def test_allows_nonconflicting_write_and_read_tasks(self) -> None:
        source = VALID_TASKS.replace("Depends: [ROOT-01]", "Depends: []")
        graph = graph_core.parse_task_graph(source)
        projection = {"tasks": {task.id: {"grade": None, "status": "pending"} for task in graph.tasks}}

        self.assertEqual(
            [task.id for task in graph_core.ready_tasks(graph, projection)],
            ["ROOT-01", "API-02"],
        )


class StructuredArtifactBehavior(unittest.TestCase):
    def test_validates_a_scoped_worker_report_without_grading(self) -> None:
        task = graph_core.parse_task_graph(VALID_TASKS).tasks[0]
        result = {
            "task_id": "ROOT-01",
            "attempt_id": "attempt-01",
            "outcome": "reported",
            "summary": "Implemented the bounded domain change.",
            "files_changed": ["src/domain/model.py"],
            "checks_run": ["python3 -m unittest tests.test_domain"],
            "evidence_refs": ["file:openspec/runs/change/run/artifacts/check.txt"],
            "questions": [],
            "external_refs": {"worker": "worker-1"},
        }

        validated = graph_core.validate_worker_result(result, task, "attempt-01")

        self.assertEqual(validated["outcome"], "reported")
        self.assertNotIn("grade", validated)

    def test_rejects_mismatched_and_out_of_scope_worker_reports(self) -> None:
        task = graph_core.parse_task_graph(VALID_TASKS).tasks[0]
        result = {
            "task_id": "ROOT-01",
            "attempt_id": "wrong-attempt",
            "outcome": "reported",
            "summary": "Changed an unrelated file.",
            "files_changed": ["src/api/handler.py"],
            "checks_run": [],
            "evidence_refs": [],
            "questions": [],
            "external_refs": {},
        }

        with self.assertRaisesRegex(graph_core.GraphValidationError, "attempt_id"):
            graph_core.validate_worker_result(result, task, "attempt-01")
        result["attempt_id"] = "attempt-01"
        with self.assertRaisesRegex(graph_core.GraphValidationError, "outside task Paths"):
            graph_core.validate_worker_result(result, task, "attempt-01")

    def test_validates_a_transcript_free_coordinator_capsule(self) -> None:
        capsule = {
            "schema_version": 1,
            "repository": "/repo/project",
            "change": "portable-graph",
            "run_id": "run-1",
            "driver": "auto",
            "base_commit": "unborn",
            "dirty_paths": ["src/file.py"],
            "coordinator_generation": 2,
            "resume_command": "$impl --coordinator-capsule openspec/runs/run/capsule.json",
        }

        self.assertEqual(graph_core.validate_coordinator_capsule(capsule), capsule)
        with self.assertRaisesRegex(graph_core.GraphValidationError, "unknown fields"):
            graph_core.validate_coordinator_capsule({**capsule, "transcript": "forbidden"})


class JournalBehavior(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary_directory.name)
        self.journal = graph_core.EventJournal(self.directory / "events.jsonl")
        self.graph = graph_core.parse_task_graph(VALID_TASKS)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def starts_run(self) -> None:
        self.journal.append(
            "run_started",
            {
                "change": "portable-graph",
                "run_id": "run-1",
                "coordinator_id": "coordinator-1",
                "coordinator_generation": 1,
                "tasks": [task.to_dict() for task in self.graph.tasks],
            },
            coordinator_generation=1,
            timestamp="2026-08-20T12:00:00Z",
        )

    def test_replays_the_saved_projection(self) -> None:
        self.starts_run()
        self.journal.append(
            "attempt_started",
            {"task_id": "ROOT-01", "attempt_id": "attempt-01", "driver": "host"},
            coordinator_generation=1,
            timestamp="2026-08-20T12:01:00Z",
        )
        reported = self.journal.append(
            "worker_reported",
            {"task_id": "ROOT-01", "attempt_id": "attempt-01", "outcome": "reported"},
            coordinator_generation=1,
            timestamp="2026-08-20T12:02:00Z",
        )

        self.assertEqual(reported["tasks"]["ROOT-01"]["status"], "reported")
        self.assertIsNone(reported["tasks"]["ROOT-01"]["grade"])
        verified = self.journal.verify_projection()
        self.assertEqual(verified, reported)

    def test_fences_a_stale_coordinator_after_transfer(self) -> None:
        self.starts_run()
        self.journal.append(
            "coordinator_transferred",
            {"coordinator_id": None, "coordinator_generation": 2},
            coordinator_generation=1,
        )

        with self.assertRaises(graph_core.StaleCoordinatorError):
            self.journal.append(
                "coordinator_claimed",
                {"coordinator_id": "stale"},
                coordinator_generation=1,
            )
        claimed = self.journal.append(
            "coordinator_claimed",
            {"coordinator_id": "coordinator-2"},
            coordinator_generation=2,
        )
        self.assertEqual(claimed["coordinator"], {"id": "coordinator-2", "generation": 2})

    def test_recovers_only_a_partial_final_line(self) -> None:
        self.starts_run()
        with self.journal.path.open("ab") as handle:
            handle.write(b'{"schema_version":1,"event_id":"event-000002"')
        artifact = self.directory / "artifacts" / "partial.bin"

        with self.assertRaisesRegex(graph_core.JournalError, "partial final line"):
            self.journal.replay()
        repaired = self.journal.recover_partial_line(
            artifact,
            coordinator_generation=1,
        )

        self.assertTrue(artifact.read_bytes().startswith(b'{"schema_version"'))
        self.assertEqual(repaired["last_sequence"], 2)
        self.assertEqual(self.journal.verify_projection(), repaired)

    def test_blocks_corruption_on_a_complete_line(self) -> None:
        self.starts_run()
        with self.journal.path.open("ab") as handle:
            handle.write(b"not-json\n")

        with self.assertRaisesRegex(graph_core.JournalError, "corruption at line 2"):
            self.journal.replay()
        with self.assertRaisesRegex(graph_core.JournalError, "corruption at line 2"):
            self.journal.recover_partial_line(
                self.directory / "partial.bin",
                coordinator_generation=1,
            )

    def test_detects_a_tampered_saved_projection(self) -> None:
        self.starts_run()
        saved = json.loads(self.journal.projection_path.read_text(encoding="utf-8"))
        saved["status"] = "complete"
        self.journal.projection_path.write_text(json.dumps(saved), encoding="utf-8")

        with self.assertRaisesRegex(graph_core.JournalError, "does not match"):
            self.journal.verify_projection()


class SchemaBehavior(unittest.TestCase):
    def test_keeps_all_declared_schemas_valid_json(self) -> None:
        references = Path(__file__).parents[1] / "references"

        for name in (
            "run-state.schema.json",
            "worker-result.schema.json",
            "coordinator-capsule.schema.json",
        ):
            with self.subTest(schema=name):
                schema = json.loads((references / name).read_text(encoding="utf-8"))
                self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")


if __name__ == "__main__":
    unittest.main()
