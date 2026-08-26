import copy
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


SOURCE_ROOT = Path(__file__).parents[1]
SCRIPT = SOURCE_ROOT / "scripts" / "context_capsules.py"
REFERENCES = SOURCE_ROOT / "references"
FIXTURES = SOURCE_ROOT / "fixtures" / "maestro-protocol-v1"
SPEC = importlib.util.spec_from_file_location("context_capsules", SCRIPT)
assert SPEC and SPEC.loader
context_capsules = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = context_capsules
SPEC.loader.exec_module(context_capsules)


def sha256(content: str) -> str:
    return f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


WORKSPACE_SCOPE = load_json(FIXTURES / "workspace-scopes.json")["folder_local"]


class FakeMaestroNoteClient:
    def __init__(self) -> None:
        self.revisions: dict[tuple[str, str], dict] = {}
        self.expired: set[tuple[str, str]] = set()
        self.pins: dict[str, set[tuple[str, str]]] = {}

    def add_revision(self, note_id: str, revision: str, content: str) -> str:
        content_hash = sha256(content)
        self.revisions[(note_id, revision)] = {
            "status": "ok",
            "note_id": note_id,
            "revision": revision,
            "content_hash": content_hash,
            "media_type": "text/markdown",
            "content": content,
        }
        return content_hash

    def fetch_and_pin_revision(
        self, *, note_id, revision, expected_hash, run_id, actor
    ):
        if actor.get("token") != "coordinator-secret":
            return {"status": "unauthorized"}
        key = (note_id, revision)
        if key in self.expired or key not in self.revisions:
            return {"status": "expired"}
        self.pins.setdefault(run_id, set()).add(key)
        return copy.deepcopy(self.revisions[key])

    def release_run_revisions(self, *, run_id, actor):
        if actor.get("token") != "coordinator-secret":
            return {"status": "unauthorized"}
        released = len(self.pins.pop(run_id, set()))
        return {"status": "released", "run_id": run_id, "released": released}


class ContextCapsuleFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repository = Path(self.temporary_directory.name).resolve()
        (self.repository / "context").mkdir()
        self.scope = copy.deepcopy(WORKSPACE_SCOPE)
        self.scope["canonical_root"] = str(self.repository)
        self.scope["orchestration_home"]["path"] = str(self.repository)
        self.scope["execution_workspace"]["path"] = str(self.repository)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def reference(
        self,
        reference_id: str,
        kind: str,
        content: str,
        *,
        priority: int | None = None,
        origin: str | None = None,
        path: str | None = None,
    ) -> dict:
        relative_path = path or f"context/{reference_id}.md"
        snapshot = self.repository.joinpath(*relative_path.split("/"))
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_text(content, encoding="utf-8")
        reference = {
            "id": reference_id,
            "kind": kind,
            "origin": origin or f"fixture:{reference_id}",
            "snapshot_path": relative_path,
            "content_hash": sha256(content),
            "revision": "rev-1",
            "media_type": "text/markdown",
            "title": reference_id,
        }
        if priority is not None:
            reference["priority"] = priority
        return reference

    def compose(self, references, edges=(), budget=None, attempt_id="attempt-1"):
        return context_capsules.compose_context_capsule(
            repository_root=self.repository,
            task_id="TASK-01",
            attempt_id=attempt_id,
            workspace_scope=self.scope,
            references=references,
            edges=edges,
            budget=budget or {"max_items": 16, "max_bytes": 8192, "max_tokens": 8192},
        )


class TraversalBehavior(ContextCapsuleFixture):
    def test_keeps_direct_task_context_first_and_terminates_cycles(self) -> None:
        task = self.reference("TASK-01", "task", "task contract", priority=5)
        note = self.reference("NOTE-01", "user-note", "direct instruction", priority=1)
        dependency = self.reference("DEP-01", "dependency", "dependency digest", priority=1)
        edges = [
            {
                "id": "edge-note",
                "type": "context_for",
                "source_id": "NOTE-01",
                "target_id": "TASK-01",
            },
            {
                "id": "edge-dependency",
                "type": "depends_on",
                "source_id": "TASK-01",
                "target_id": "DEP-01",
            },
            {
                "id": "edge-cycle",
                "type": "depends_on",
                "source_id": "DEP-01",
                "target_id": "TASK-01",
            },
        ]

        pressured = self.compose(
            [dependency, note, task],
            list(reversed(edges)),
            {"max_items": 1, "max_bytes": 4, "max_tokens": 4},
        )
        complete = self.compose([task, note, dependency], edges)
        reordered = self.compose(list(reversed([task, note, dependency])), list(reversed(edges)))

        self.assertEqual([item["id"] for item in pressured["items"]], ["TASK-01"])
        self.assertEqual(
            [item["id"] for item in complete["items"]],
            ["TASK-01", "NOTE-01", "DEP-01"],
        )
        self.assertEqual(complete, reordered)

    def test_excludes_lifecycle_edges_and_raw_terminal_material(self) -> None:
        raw_output = "RAW-TERMINAL-SECRET api-key=do-not-copy"
        (self.repository / "context" / "terminal.log").write_text(raw_output, encoding="utf-8")
        task = self.reference("TASK-01", "task", "bounded task contract")
        edges = [
            {
                "id": "edge-report",
                "type": "reports_to",
                "source_id": "attempt-1",
                "target_id": "TASK-01",
            },
            {
                "id": "edge-executes",
                "type": "executes",
                "source_id": "attempt-1",
                "target_id": "terminal-1",
            },
        ]

        capsule = self.compose([task], edges)
        serialized = json.dumps(capsule)

        self.assertNotIn(raw_output, serialized)
        self.assertNotIn("terminal.log", serialized)
        self.assertEqual([item["id"] for item in capsule["items"]], ["TASK-01"])

    def test_reaches_attempt_context_and_evidence_without_snapshotting_attempt(self) -> None:
        task = self.reference("TASK-01", "task", "task contract")
        note = self.reference("NOTE-ATTEMPT", "user-note", "attempt instruction")
        evidence = self.reference("EVIDENCE-ATTEMPT", "evidence", "attempt evidence")
        colliding_attempt = self.reference("attempt-1", "source", "attempt anchor collision")
        edges = [
            {
                "id": "edge-attempt-note",
                "type": "context_for",
                "source_id": "NOTE-ATTEMPT",
                "target_id": "attempt-1",
            },
            {
                "id": "edge-attempt-evidence",
                "type": "produces",
                "source_id": "attempt-1",
                "target_id": "EVIDENCE-ATTEMPT",
            },
        ]

        pressured = self.compose(
            [colliding_attempt, evidence, note, task],
            edges,
            {"max_items": 1, "max_bytes": 64, "max_tokens": 64},
        )
        complete = self.compose([colliding_attempt, evidence, note, task], edges)
        reordered = self.compose(
            [task, note, evidence, colliding_attempt], list(reversed(edges))
        )

        self.assertEqual([item["id"] for item in pressured["items"]], ["TASK-01"])
        self.assertEqual(
            [item["id"] for item in complete["items"]],
            ["TASK-01", "NOTE-ATTEMPT", "EVIDENCE-ATTEMPT"],
        )
        self.assertEqual(complete, reordered)
        self.assertNotIn("attempt-1", {item["id"] for item in complete["items"]})

    def test_rejects_transcript_fields_in_structured_inputs(self) -> None:
        task = self.reference("TASK-01", "task", "task contract")
        task["terminal_output"] = "must not enter"

        with self.assertRaisesRegex(
            context_capsules.ContextValidationError, "transcript fields"
        ):
            self.compose([task])


class SnapshotSafetyBehavior(ContextCapsuleFixture):
    def test_rejects_absolute_parent_and_symlink_escape_paths(self) -> None:
        task = self.reference("TASK-01", "task", "task contract")
        unsafe_paths = ["/tmp/secret.md", "../secret.md", "context\\secret.md"]
        for unsafe_path in unsafe_paths:
            with self.subTest(path=unsafe_path):
                changed = copy.deepcopy(task)
                changed["snapshot_path"] = unsafe_path
                with self.assertRaises(context_capsules.ContextValidationError):
                    self.compose([changed])

        outside = self.repository.parent / f"{self.repository.name}-outside.md"
        outside.write_text("outside", encoding="utf-8")
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        os.symlink(outside, self.repository / "context" / "escape.md")
        changed = copy.deepcopy(task)
        changed["snapshot_path"] = "context/escape.md"
        changed["content_hash"] = sha256("outside")
        with self.assertRaisesRegex(context_capsules.ContextValidationError, "escapes"):
            self.compose([changed])

    def test_rejects_a_hash_mismatch_even_when_the_item_budget_omits_it(self) -> None:
        task = self.reference("TASK-01", "task", "task contract")
        source = self.reference("SOURCE-01", "source", "trusted source")
        source["content_hash"] = "sha256:" + "0" * 64
        edge = {
            "id": "edge-source",
            "type": "context_for",
            "source_id": "SOURCE-01",
            "target_id": "TASK-01",
        }

        with self.assertRaisesRegex(
            context_capsules.ContentHashMismatchError, "hash mismatch"
        ):
            self.compose(
                [task, source],
                [edge],
                {"max_items": 1, "max_bytes": 32, "max_tokens": 32},
            )


class BudgetBehavior(ContextCapsuleFixture):
    def test_references_oversized_material_with_a_bounded_digest(self) -> None:
        task = self.reference("TASK-01", "task", "direct contract " * 2000)
        source = self.reference("SOURCE-01", "source", "supporting source")
        edge = {
            "id": "edge-source",
            "type": "context_for",
            "source_id": "SOURCE-01",
            "target_id": "TASK-01",
        }

        capsule = self.compose(
            [source, task],
            [edge],
            {"max_items": 2, "max_bytes": 32, "max_tokens": 32},
        )

        self.assertEqual(capsule["usage"]["content_bytes"], 32)
        self.assertLessEqual(capsule["usage"]["content_tokens"], 32)
        self.assertEqual(capsule["items"][0]["snapshot_path"], "context/TASK-01.md")
        self.assertTrue(capsule["items"][0]["truncated"])
        self.assertIsNotNone(capsule["items"][0]["excerpt"])
        self.assertIsNone(capsule["items"][1]["excerpt"])

    def test_schema_validates_a_composed_capsule(self) -> None:
        task = self.reference("TASK-01", "task", "task contract")
        capsule = self.compose([task])
        placement = load_json(REFERENCES / "placement.schema.json")
        context_schema = load_json(REFERENCES / "context-capsule.schema.json")
        registry = Registry().with_resource(
            placement["$id"], Resource.from_contents(placement)
        )

        Draft202012Validator(context_schema, registry=registry).validate(capsule)
        Draft202012Validator.check_schema(context_schema)

    def test_writes_a_capsule_once_without_allowing_replacement(self) -> None:
        task = self.reference("TASK-01", "task", "task contract")
        capsule = self.compose([task])
        relative_path = "openspec/runs/change/run-1/capsules/attempt-1.json"

        path = context_capsules.write_context_capsule_once(
            self.repository, relative_path, capsule
        )

        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), capsule)
        with self.assertRaises(context_capsules.CapsuleAlreadyExistsError):
            context_capsules.write_context_capsule_once(
                self.repository, relative_path, capsule
            )


class ReusedSessionHandoffBehavior(unittest.TestCase):
    def test_keeps_only_incremental_task_context(self) -> None:
        handoff = context_capsules.build_reused_session_handoff(
            task_id="TASK-02",
            acceptance="The next bounded task is accepted.",
            dependency_summaries=[{"task_id": "TASK-01", "summary": "The first task passed."}],
            diff_since_previous_check=["src/first.py"],
            unresolved_material_finding_refs=["file:findings/task-01.md"],
            allowed_paths=["src/second.py"],
            check="python3 -m unittest tests.test_second",
            session_memory={
                "decisions": ["Keep the public contract narrow."],
                "invariants": ["Every task remains independently graded."],
                "central_files": ["src/first.py"],
                "traps": ["Do not mutate the journal from a worker."],
                "green_checks": ["python3 -m unittest tests.test_first"],
                "carry_forward_findings": ["file:findings/task-01.md"],
            },
        )

        self.assertEqual(
            set(handoff),
            {
                "schema_version", "handoff_id", "task_id", "acceptance",
                "dependency_summaries", "diff_since_previous_check",
                "unresolved_material_finding_refs", "allowed_paths", "check",
                "session_memory",
            },
        )
        self.assertNotIn("report", json.dumps(handoff))
        self.assertNotIn("transcript", json.dumps(handoff))

    def test_rejects_transcript_or_unbounded_session_memory(self) -> None:
        memory = {
            "decisions": [], "invariants": [], "central_files": [], "traps": [],
            "green_checks": [], "carry_forward_findings": [],
        }
        with self.assertRaisesRegex(context_capsules.ContextValidationError, "transcript"):
            context_capsules.build_reused_session_handoff(
                task_id="TASK-02", acceptance="accepted", dependency_summaries=[],
                diff_since_previous_check=[], unresolved_material_finding_refs=[],
                allowed_paths=["src/second.py"], check="python3 -m unittest",
                session_memory={**memory, "traps": ["safe"], "transcript": ["unsafe"]},
            )


class MaestroNoteBehavior(ContextCapsuleFixture):
    def setUp(self) -> None:
        super().setUp()
        self.run_directory = self.repository / "openspec" / "runs" / "change" / "run-1"
        self.run_directory.mkdir(parents=True)
        self.client = FakeMaestroNoteClient()
        self.actor = {"actor_id": "coordinator-1", "token": "coordinator-secret"}

    def materialize(self, note_id, revision, expected_hash, actor=None):
        return context_capsules.materialize_maestro_note_revision(
            repository_root=self.repository,
            run_directory=self.run_directory,
            note_id=note_id,
            revision=revision,
            expected_hash=expected_hash,
            title="Selected user note",
            actor=actor or self.actor,
            client=self.client,
        )

    def test_rejects_unauthorized_expired_and_hash_mismatched_revisions(self) -> None:
        content_hash = self.client.add_revision("note-1", "rev-1", "first revision")

        with self.assertRaises(context_capsules.NoteAuthorizationError):
            self.materialize(
                "note-1", "rev-1", content_hash, {"actor_id": "stranger", "token": "wrong"}
            )

        self.client.expired.add(("note-1", "rev-1"))
        with self.assertRaises(context_capsules.NoteRevisionExpiredError):
            self.materialize("note-1", "rev-1", content_hash)

        self.client.expired.clear()
        with self.assertRaises(context_capsules.ContentHashMismatchError):
            self.materialize("note-1", "rev-1", "sha256:" + "0" * 64)

    def test_pins_new_revisions_without_mutating_a_dispatched_capsule(self) -> None:
        first_hash = self.client.add_revision("note-1", "rev-1", "first revision")
        first_note = self.materialize("note-1", "rev-1", first_hash)
        task = self.reference("TASK-01", "task", "task contract")
        first_capsule = self.compose(
            [task, first_note],
            [
                {
                    "id": "edge-note-1",
                    "type": "context_for",
                    "source_id": first_note.id,
                    "target_id": "TASK-01",
                }
            ],
        )
        capsule_path = context_capsules.write_context_capsule_once(
            self.repository,
            "openspec/runs/change/run-1/capsules/attempt-1.json",
            first_capsule,
        )
        original_capsule = capsule_path.read_bytes()
        original_snapshot = (self.repository / first_note.snapshot_path).read_bytes()

        second_hash = self.client.add_revision("note-1", "rev-2", "edited revision")
        second_note = self.materialize("note-1", "rev-2", second_hash)

        self.assertNotEqual(first_note.snapshot_path, second_note.snapshot_path)
        self.assertEqual(
            (self.repository / first_note.snapshot_path).read_bytes(), original_snapshot
        )
        self.assertEqual(capsule_path.read_bytes(), original_capsule)
        self.assertEqual(
            self.client.pins["run-1"], {("note-1", "rev-1"), ("note-1", "rev-2")}
        )

        receipt = context_capsules.release_maestro_note_revisions(
            client=self.client, run_id="run-1", actor=self.actor
        )
        self.assertEqual(receipt["released"], 2)
        self.assertNotIn("run-1", self.client.pins)

    def test_rejects_an_existing_note_snapshot_symlink_that_escapes_the_run(self) -> None:
        content_hash = self.client.add_revision("note-1", "rev-1", "first revision")
        outside = self.repository.parent / f"{self.repository.name}-note.md"
        outside.write_text("first revision", encoding="utf-8")
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        snapshot_directory = self.run_directory / "artifacts" / "maestro-notes" / "note-1"
        snapshot_directory.mkdir(parents=True)
        os.symlink(outside, snapshot_directory / "rev-1.md")

        with self.assertRaisesRegex(context_capsules.ContextValidationError, "escapes"):
            self.materialize("note-1", "rev-1", content_hash)


if __name__ == "__main__":
    unittest.main()
