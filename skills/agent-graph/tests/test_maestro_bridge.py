from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import copy
import contextlib
import io
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from graph_core import GraphValidationError, validate_agent_graph_view
from graph_core import EventJournal
import agent_graph
from maestro_bridge import (
    CoordinatorInbox,
    MaestroBridgeError,
    canonical_sha256,
    build_delta,
    build_reset,
    build_snapshot as _build_snapshot,
    negotiate_major,
    negotiate_capabilities,
)


ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "skills/agent-graph/fixtures/maestro-protocol-v1"


def _scope() -> dict:
    return json.loads((FIXTURES / "workspace-scopes.json").read_text())["folder_local"]


def _mutation(scope: dict, *, revision: int = 12, mutation_id: str = "mutation-test") -> dict:
    return {
        "schema_version": 1,
        "protocol": "maestro-mutation/v1",
        "mutation_id": mutation_id,
        "workspace": {
            "repository_id": scope["repository_id"],
            "execution_host_id": scope["orchestration_home"]["execution_host_id"],
            "workspace_key": scope["orchestration_home"]["workspace_key"],
            "run_id": scope["run_id"],
        },
        "actor": {"actor_id": "user-17", "kind": "user", "authenticated": True, "session_id": "session-42"},
        "coordinator_generation": scope["coordinator_generation"],
        "expected_revision": revision,
        "operation": {"kind": "move-node", "node_id": "task-MLK-01", "position": {"x": 10, "y": 20}},
    }


def _run(repository: Path, *, bound: bool = False) -> tuple[dict, Path, EventJournal]:
    scope = copy.deepcopy(_scope())
    scope["run_id"] = "run-mlk-01"
    run_directory = repository / "openspec/runs/change/run-mlk-01"
    if bound:
        scope["canonical_root"] = str(repository.resolve())
        scope["orchestration_home"]["path"] = str(repository.resolve())
        scope["execution_workspace"]["path"] = str(repository.resolve())
        scope["repository_id"] = "fb2a9411-f3cb-46d4-94f7-067f40719b71"
        receipt = {
            "schema_version": 1, "repository_id": scope["repository_id"], "canonical_root": scope["canonical_root"],
            "execution_host": scope["execution_host"], "orchestration_home": scope["orchestration_home"],
            "execution_workspace": scope["execution_workspace"], "base_revision": scope["base_revision"],
            "dirty_paths": scope["dirty_paths"], "authority": {"kind": "orca", "scope": "run", "issued_for_run_id": scope["run_id"]},
        }
        receipt_path = run_directory / "artifacts/workspace-bootstrap-receipt-v1.json"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, sort_keys=True))
        scope["binding_receipt_ref"] = "artifact:openspec/runs/change/run-mlk-01/artifacts/workspace-bootstrap-receipt-v1.json"
        scope["binding_receipt_hash"] = agent_graph._workspace_receipt_hash(receipt)
    journal = EventJournal(run_directory / "events.jsonl", run_directory / "state.json")
    journal.append("run_started", {"change": "change", "run_id": scope["run_id"], "coordinator_id": "coordinator-3", "coordinator_generation": 3, "workspace_scope": scope, "tasks": [{"id": "MLK-01", "title": "Build", "depends": [], "paths": ["src/"], "mode": "write", "isolation": "auto", "acceptance": "Build", "check": "python3 -c pass"}]}, coordinator_generation=3)
    return scope, run_directory, journal


def _synthetic_last_event(projection: dict) -> dict | None:
    sequence = projection.get("last_sequence")
    if not isinstance(sequence, int) or sequence == 0:
        return None
    return {
        "sequence": sequence,
        "timestamp": "2026-08-22T09:04:01Z",
        "type": "synthetic_projection",
    }


def build_snapshot(projection: dict, **kwargs: object) -> dict:
    kwargs.setdefault("last_event", _synthetic_last_event(projection))
    return _build_snapshot(projection, **kwargs)


class MaestroBridgeTests(unittest.TestCase):
    def test_fixtures_round_trip_and_negotiate_highest_mutual_major(self) -> None:
        view = json.loads((FIXTURES / "agent-graph-view.json").read_text())
        self.assertEqual(validate_agent_graph_view(view), view)
        private_view = copy.deepcopy(view)
        private_view["nodes"][-1]["position"] = {"x": 1, "y": 2}
        with self.assertRaises(GraphValidationError):
            validate_agent_graph_view(private_view)
        self.assertEqual(negotiate_major(["agent-graph-view/v1", 2], [1, 2]), 2)
        with self.assertRaisesRegex(MaestroBridgeError, "no mutually supported"):
            negotiate_major([1], [2])

    def test_protocol_fixtures_use_canonical_entity_order_and_serialization(self) -> None:
        for fixture_name in ("agent-graph-view.json", "agent-graph-view-delta.json"):
            view = json.loads((FIXTURES / fixture_name).read_text())
            self.assertEqual([node["id"] for node in view["nodes"]], sorted(node["id"] for node in view["nodes"]))
            self.assertEqual([edge["id"] for edge in view["edges"]], sorted(edge["id"] for edge in view["edges"]))
            self.assertEqual(view["removed_node_ids"], sorted(view["removed_node_ids"]))
            self.assertEqual(view["removed_edge_ids"], sorted(view["removed_edge_ids"]))
            for field in ("agents", "efforts", "placement_kinds"):
                self.assertEqual(view["capabilities"][field], sorted(view["capabilities"][field]))
            canonical = json.dumps(view, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            self.assertEqual((FIXTURES / fixture_name).read_bytes(), canonical.encode("utf-8"))

    def test_projection_bounds_body_length_and_orders_entities(self) -> None:
        scope = _scope()
        profile = json.loads((FIXTURES / "execution-profiles.json").read_text())["current_folder"]
        projection = {
            "workspace_scope": scope,
            "coordinator": {"id": "coordinator-3", "generation": scope["coordinator_generation"]},
            "run_id": scope["run_id"],
            "last_sequence": 12,
            "tasks": {
                "MLK-01": {"status": "reported", "contract": {"title": "A" * 100000, "depends": []}, "attempt_ids": ["attempt-1"]},
                "MLK-00": {"status": "pending", "contract": {"title": "B", "depends": []}, "attempt_ids": []},
            },
            "attempts": {"attempt-1": {"status": "reported", "execution_profile": profile}},
            "cleanup": {},
            "delegations": {},
        }
        capabilities = {"agents": ["codex"], "efforts": ["medium"], "placement_kinds": ["current-workspace"], "watch_deltas": True}
        view = build_snapshot(projection, change="maestro-harness-orchestration", capabilities=capabilities)
        projection["tasks"]["MLK-01"]["contract"]["title"] = "A" * 2048
        view = build_snapshot(projection, change="maestro-harness-orchestration", capabilities=capabilities)
        self.assertEqual([node["id"] for node in view["nodes"]], sorted(node["id"] for node in view["nodes"]))
        self.assertLess(len(json.dumps(view)), 20000)
        self.assertLessEqual(len(next(node for node in view["nodes"] if node["id"] == "task-MLK-01")["summary"].encode()), 2048)
        self.assertEqual(validate_agent_graph_view(view), view)
        projection["tasks"]["MLK-02"] = {"status": "pending", "grade": None, "contract": {"title": "Dependent", "depends": ["MLK-01"]}, "attempt_ids": []}
        projection["tasks"]["MLK-01"]["grade"] = "fail"
        blocked_view = build_snapshot(projection, change="maestro-harness-orchestration", capabilities=capabilities)
        self.assertEqual(next(node for node in blocked_view["nodes"] if node["id"] == "task-MLK-02")["blockers"], ["MLK-01"])
        many = copy.deepcopy(projection)
        many["tasks"] = {f"T-{index:02d}": {"status": "pending", "contract": {"title": "T", "depends": []}, "attempt_ids": []} for index in range(40)}
        self.assertEqual(len(build_snapshot(many, change="maestro-harness-orchestration", capabilities=capabilities)["nodes"]), 40)
        many["tasks"] = {f"T-{index}": {"status": "pending", "contract": {"title": "T", "depends": []}, "attempt_ids": []} for index in range(1001)}
        with self.assertRaisesRegex(MaestroBridgeError, "bounded capacity"):
            build_snapshot(many, change="maestro-harness-orchestration", capabilities=capabilities)

        projection["attempts"]["attempt-1"]["resource_owner"] = {
            "execution_host_id": "host-local", "workspace_key": "folder:folder-local-01", "attempt_id": "attempt-1",
            "terminal_id": "terminal-1", "incarnation_id": "pty-1", "process_root": 1, "provenance": "test",
        }
        portable_view = build_snapshot(projection, change="maestro-harness-orchestration", capabilities=capabilities, visual_state={"positions": {"task-MLK-01": {"x": 7, "y": 8}}, "notes": {}})
        self.assertFalse(any("resource" in node or "position" in node for node in portable_view["nodes"]))
        self.assertNotIn("terminal", json.dumps(portable_view).casefold())

    def test_delta_and_reset_fence_stream_revision_and_truncated_edges(self) -> None:
        scope = _scope()
        profile = json.loads((FIXTURES / "execution-profiles.json").read_text())["current_folder"]
        projection = {"workspace_scope": scope, "coordinator": {"id": "coordinator-3", "generation": 3}, "run_id": scope["run_id"], "last_sequence": 12, "tasks": {"MLK-01": {"status": "running", "contract": {"title": "A", "depends": []}, "attempt_ids": ["attempt-1"]}}, "attempts": {"attempt-1": {"status": "running", "execution_profile": profile}}, "cleanup": {}, "delegations": {}}
        caps = {"agents": ["codex"], "efforts": ["high"], "placement_kinds": ["current-workspace"], "watch_deltas": True}
        previous = build_snapshot(projection, change="maestro-harness-orchestration", capabilities=caps)
        current = json.loads(json.dumps(previous))
        current["revision"] = 13
        current["cursor"] = {"stream_id": scope["run_id"], "sequence": 13, "revision": 13}
        current["progress"]["last_activity"] = {
            "sequence": 13,
            "timestamp": "2026-08-22T09:04:02Z",
            "type": "task_ready",
        }
        current["nodes"] = current["nodes"][:1]
        delta = build_delta(previous, current, change="maestro-harness-orchestration", from_cursor=previous["cursor"], capabilities=caps)
        self.assertFalse(any(edge["source_id"] not in {node["id"] for node in delta["nodes"]} or edge["target_id"] not in {node["id"] for node in delta["nodes"]} for edge in delta["edges"]))
        reset = build_reset(current, change="maestro-harness-orchestration", from_cursor=previous["cursor"], capabilities=caps)
        self.assertTrue(reset["reset_required"])
        with self.assertRaisesRegex(MaestroBridgeError, "stream"):
            build_delta(previous, current, change="maestro-harness-orchestration", from_cursor={**previous["cursor"], "stream_id": "other"}, capabilities=caps)
        with self.assertRaisesRegex(MaestroBridgeError, "sequence/revision"):
            build_reset(current, change="maestro-harness-orchestration", from_cursor={**previous["cursor"], "sequence": 11}, capabilities=caps)

    def test_view_snapshot_delta_and_reset_publish_the_same_progress_without_orca(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            scope, run_directory, journal = _run(repository)
            inbox = CoordinatorInbox(run_directory)
            capabilities = {"protocol_major": 1, "agents": ["host-native"], "efforts": ["medium"], "placement_kinds": ["current-workspace"], "watch_deltas": True}
            inbox.persist_capabilities(capabilities, coordinator_id="coordinator-3", generation=3, workspace_scope=scope)
            arguments = SimpleNamespace(repo=repository, change="change", run_id=scope["run_id"], kind="snapshot", from_view=None)
            snapshot = agent_graph.command_maestro_view(arguments)
            self.assertEqual(snapshot["progress"]["state"], "active")
            self.assertNotIn("terminal", json.dumps(snapshot).casefold())
            previous_path = repository / "previous-view.json"
            previous_path.write_text(json.dumps(snapshot), encoding="utf-8")
            journal.append("task_ready", {"task_id": "MLK-01"}, coordinator_generation=3)
            delta = agent_graph.command_maestro_view(SimpleNamespace(**{**arguments.__dict__, "kind": "delta", "from_view": previous_path.name}))
            reset = agent_graph.command_maestro_view(SimpleNamespace(**{**arguments.__dict__, "kind": "reset", "from_view": previous_path.name}))
            self.assertEqual(delta["progress"], reset["progress"])
            self.assertEqual(delta["progress"]["last_activity"]["type"], "task_ready")
            self.assertTrue(reset["reset_required"])
            self.assertEqual(validate_agent_graph_view(snapshot), snapshot)
            self.assertEqual(validate_agent_graph_view(delta), delta)
            self.assertEqual(validate_agent_graph_view(reset), reset)

    def test_rejects_progress_activity_from_a_different_view_observation(self) -> None:
        view = json.loads((FIXTURES / "agent-graph-view.json").read_text())
        view["progress"]["last_activity"]["sequence"] = view["revision"] + 1
        with self.assertRaisesRegex(GraphValidationError, "activity sequence"):
            validate_agent_graph_view(view)
        view["progress"]["last_activity"] = None
        with self.assertRaisesRegex(GraphValidationError, "requires progress last_activity"):
            validate_agent_graph_view(view)

    def test_inbox_replay_is_idempotent_and_divergence_is_rejected(self) -> None:
        scope = _scope()
        with tempfile.TemporaryDirectory() as directory:
            inbox = CoordinatorInbox(Path(directory))
            mutation = _mutation(scope)
            first = inbox.submit(mutation, kind="mutation", workspace_scope=scope, current_revision=12)
            second = inbox.submit(mutation, kind="mutation", workspace_scope=scope, current_revision=12)
            self.assertFalse(first["idempotent"])
            self.assertTrue(second["idempotent"])
            self.assertTrue(inbox.submit(mutation, kind="mutation", workspace_scope=scope, current_revision=13)["idempotent"])
            changed = json.loads(json.dumps(mutation))
            changed["operation"]["position"]["x"] = 99
            with self.assertRaisesRegex(MaestroBridgeError, "divergent payload"):
                inbox.submit(changed, kind="mutation", workspace_scope=scope, current_revision=12)
            self.assertEqual(len(inbox.pending()), 1)

    def test_inbox_rejects_stale_revision_without_writing(self) -> None:
        scope = _scope()
        with tempfile.TemporaryDirectory() as directory:
            inbox = CoordinatorInbox(Path(directory))
            with self.assertRaises(MaestroBridgeError) as context:
                inbox.submit(_mutation(scope, revision=11), kind="mutation", workspace_scope=scope, current_revision=12)
            self.assertEqual(context.exception.code, "stale_revision")
            self.assertEqual(context.exception.details, {"current_revision": 12, "reset_required": True, "guidance": "request a fresh AgentGraphView snapshot"})
            self.assertFalse(inbox.path.exists())

    def test_public_stale_submit_emits_structured_error_without_inbox_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            scope, run_directory, _ = _run(repository, bound=True)
            inbox_directory = run_directory / "artifacts" / "maestro-inbox"
            inbox = CoordinatorInbox(run_directory)
            inbox.persist_capabilities({"protocol_major": 1, "agents": ["codex"], "efforts": ["medium"], "placement_kinds": ["current-workspace"], "watch_deltas": True}, coordinator_id="coordinator-3", generation=3, workspace_scope=scope)
            inbox_before = tuple((p.relative_to(inbox_directory).as_posix(), p.read_bytes()) for p in sorted(inbox_directory.rglob("*")) if p.is_file())
            request = _mutation(scope, revision=0, mutation_id="mutation-stale-public")
            request_path = repository / "stale.json"
            request_path.write_text(json.dumps(request))
            stdout = io.StringIO()
            stderr = io.StringIO()
            with patch.object(agent_graph, "_invocation_control_runtime", return_value=None), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = agent_graph.main(["maestro-submit", "--repo", str(repository), "--change", "change", "--run-id", scope["run_id"], "--generation", "3", "--kind", "mutation", "--request", request_path.name])
            error = json.loads(stderr.getvalue())["error"]
            self.assertEqual(code, 1)
            self.assertEqual(error["code"], "stale_revision")
            self.assertEqual(error["current_revision"], 1)
            self.assertTrue(error["reset_required"])
            self.assertEqual(error["guidance"], "request a fresh AgentGraphView snapshot")
            self.assertEqual(inbox_before, tuple((p.relative_to(inbox_directory).as_posix(), p.read_bytes()) for p in sorted(inbox_directory.rglob("*")) if p.is_file()))
            self.assertFalse((inbox_directory / "requests.json").exists())

    def test_public_consume_receipt_is_uncompacted_and_stable_through_main(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            scope, run_directory, journal = _run(repository, bound=True)
            inbox = CoordinatorInbox(run_directory)
            inbox.persist_capabilities({"protocol_major": 1, "agents": ["codex"], "efforts": ["medium"], "placement_kinds": ["current-workspace"], "watch_deltas": True}, coordinator_id="coordinator-3", generation=3, workspace_scope=scope)
            mutation = _mutation(scope, revision=1, mutation_id="mutation-main-receipt")
            inbox.submit(mutation, kind="mutation", workspace_scope=scope, current_revision=1)
            argv = ["maestro-consume", "--repo", str(repository), "--change", "change", "--run-id", scope["run_id"], "--generation", "3", "--request-id", "mutation-main-receipt", "--coordinator-id", "coordinator-3"]
            def run_main() -> dict:
                output = io.StringIO()
                with patch.object(agent_graph, "_invocation_control_runtime", return_value=None), contextlib.redirect_stdout(output):
                    self.assertEqual(agent_graph.main(argv), 0)
                return json.loads(output.getvalue())["result"]
            first = run_main()
            journal.append("coordinator_claimed", {"coordinator_id": "coordinator-3"}, coordinator_generation=3)
            replay = run_main()
            ack_output = io.StringIO()
            ack_argv = ["maestro-ack", "--repo", str(repository), "--change", "change", "--run-id", scope["run_id"], "--generation", "3", "--request-id", "mutation-main-receipt", "--coordinator-id", "coordinator-3"]
            with patch.object(agent_graph, "_invocation_control_runtime", return_value=None), contextlib.redirect_stdout(ack_output):
                self.assertEqual(agent_graph.main(ack_argv), 0)
            ack_first = json.loads(ack_output.getvalue())["result"]
            ack_output = io.StringIO()
            with patch.object(agent_graph, "_invocation_control_runtime", return_value=None), contextlib.redirect_stdout(ack_output):
                self.assertEqual(agent_graph.main(ack_argv), 0)
            ack_replay = json.loads(ack_output.getvalue())["result"]
            expected = {"request_id", "kind", "status", "idempotent", "revision", "affected_entity_ids", "affected_event_ids", "warnings", "mutation_id"}
            self.assertEqual(set(first), expected)
            self.assertEqual(set(replay), expected)
            self.assertFalse(set(first) & {"operation", "payload", "body", "applied_revision", "affected_node_ids"})
            for field in ("request_id", "kind", "status", "revision", "affected_entity_ids", "affected_event_ids", "warnings", "mutation_id"):
                self.assertEqual(first[field], replay[field])
            self.assertFalse(first["idempotent"])
            self.assertTrue(replay["idempotent"])
            self.assertEqual(set(ack_first), expected)
            self.assertEqual(set(ack_replay), expected)
            for field in ("request_id", "kind", "status", "revision", "affected_entity_ids", "affected_event_ids", "warnings", "mutation_id"):
                self.assertEqual(ack_first[field], ack_replay[field])
            self.assertTrue(ack_first["idempotent"])
            self.assertTrue(ack_replay["idempotent"])

    def test_public_consume_stale_revision_is_structured_and_byte_preserving(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            scope, run_directory, journal = _run(repository, bound=True)
            inbox = CoordinatorInbox(run_directory)
            inbox.persist_capabilities({"protocol_major": 1, "agents": ["codex"], "efforts": ["medium"], "placement_kinds": ["current-workspace"], "watch_deltas": True}, coordinator_id="coordinator-3", generation=3, workspace_scope=scope)
            inbox.submit(_mutation(scope, revision=1, mutation_id="mutation-consume-stale"), kind="mutation", workspace_scope=scope, current_revision=1)
            journal.append("coordinator_claimed", {"coordinator_id": "coordinator-3"}, coordinator_generation=3)
            requests_before = inbox.path.read_bytes()
            events_before = (run_directory / "events.jsonl").read_bytes()
            state_before = (run_directory / "state.json").read_bytes()
            visual_path = inbox.directory / "visual-state.json"
            visual_before = visual_path.read_bytes() if visual_path.exists() else None
            stdout = io.StringIO()
            stderr = io.StringIO()
            argv = ["maestro-consume", "--repo", str(repository), "--change", "change", "--run-id", scope["run_id"], "--generation", "3", "--request-id", "mutation-consume-stale", "--coordinator-id", "coordinator-3"]
            with patch.object(agent_graph, "_invocation_control_runtime", return_value=None), patch.object(agent_graph, "build_snapshot", side_effect=AssertionError("stale consume must not build a snapshot")), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = agent_graph.main(argv)
            error = json.loads(stderr.getvalue())["error"]
            self.assertEqual(code, 1)
            self.assertEqual(error["code"], "stale_revision")
            self.assertEqual(error["current_revision"], 2)
            self.assertTrue(error["reset_required"])
            self.assertEqual(error["guidance"], "request a fresh AgentGraphView snapshot")
            self.assertEqual(requests_before, inbox.path.read_bytes())
            self.assertEqual(events_before, (run_directory / "events.jsonl").read_bytes())
            self.assertEqual(state_before, (run_directory / "state.json").read_bytes())
            self.assertEqual(visual_before, visual_path.read_bytes() if visual_path.exists() else None)

    def test_inbox_integrity_covers_transition_envelope(self) -> None:
        scope = _scope()
        with tempfile.TemporaryDirectory() as directory:
            inbox = CoordinatorInbox(Path(directory))
            inbox.submit(_mutation(scope), kind="mutation", workspace_scope=scope, current_revision=12)
            records = json.loads(inbox.path.read_text())
            records["mutation-test"]["status"] = "acked"
            inbox.path.write_text(json.dumps(records))
            with self.assertRaisesRegex(MaestroBridgeError, "integrity mismatch"):
                inbox.pending()

    def test_capabilities_are_negotiated_and_persisted_without_defaults(self) -> None:
        scope = _scope()
        local = {"protocol_majors": [1, 2], "agents": ["codex"], "efforts": ["medium", "high"], "placement_kinds": ["current-workspace"], "watch_deltas": True}
        remote = {"protocol_majors": [2], "agents": ["codex"], "efforts": ["high"], "placement_kinds": ["current-workspace"], "watch_deltas": True}
        capabilities = negotiate_capabilities(local, remote)
        self.assertEqual(capabilities["protocol_major"], 2)
        max_capabilities = negotiate_capabilities(
            {**local, "efforts": ["low", "medium", "high", "xhigh", "max"]},
            {**remote, "efforts": ["max"]},
        )
        self.assertEqual(max_capabilities["efforts"], ["max"])
        empty = negotiate_capabilities({**local, "agents": []}, {**remote, "agents": ["codex"]})
        self.assertEqual(empty["agents"], [])
        with tempfile.TemporaryDirectory() as directory:
            inbox = CoordinatorInbox(Path(directory))
            inbox.persist_capabilities(capabilities, coordinator_id="coordinator-3", generation=3, workspace_scope=scope)
            self.assertEqual(inbox.read_capabilities(), {key: value for key, value in capabilities.items() if key != "protocol_major"})
            next_scope = copy.deepcopy(scope)
            next_scope["coordinator_generation"] = 4
            inbox.persist_capabilities(capabilities, coordinator_id="coordinator-4", generation=4, workspace_scope=next_scope)
            self.assertEqual(inbox.read_capabilities(generation=3), None)
            self.assertIsNotNone(inbox.read_capabilities(generation=4))
        with self.assertRaisesRegex(MaestroBridgeError, "non-empty strings"):
            negotiate_capabilities({**local, "agents": [1]}, remote)
        with self.assertRaisesRegex(MaestroBridgeError, "invalid effort"):
            negotiate_capabilities({**local, "efforts": ["bogus"]}, remote)
        with self.assertRaisesRegex(MaestroBridgeError, "duplicated"):
            negotiate_capabilities({**local, "agents": ["codex", "codex"]}, remote)
        self.assertEqual(negotiate_capabilities({**local, "protocol_majors": [2]}, {**remote, "protocol_majors": [2]})["protocol_major"], 2)
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            scope, run_directory, _ = _run(repository, bound=True)
            (repository / "local-v2.json").write_text(json.dumps({**local, "protocol_majors": [2]}))
            (repository / "remote-v2.json").write_text(json.dumps({**remote, "protocol_majors": [2]}))
            stderr = io.StringIO()
            with patch.object(agent_graph, "_invocation_control_runtime", return_value=None), contextlib.redirect_stderr(stderr):
                code = agent_graph.main(["maestro-negotiate", "--repo", str(repository), "--change", "change", "--run-id", scope["run_id"], "--generation", "3", "--local-capabilities", "local-v2.json", "--remote-capabilities", "remote-v2.json"])
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(stderr.getvalue())["error"]["code"], "unsupported_major")
            self.assertFalse((run_directory / "artifacts/maestro-inbox/capabilities.json").exists())

    def test_schema_registry_validates_portable_core_without_maestro_dependency(self) -> None:
        ids = {
            "agent-graph-view.schema.json": "https://github.com/badmuriss/my-llm-kit/schemas/agent-graph-view-v1.json",
            "run-progress-summary.schema.json": "https://github.com/badmuriss/my-llm-kit/schemas/run-progress-summary-v1.json",
            "maestro-mutation.schema.json": "https://github.com/badmuriss/my-llm-kit/schemas/maestro-mutation-v1.json",
            "delegation-intent.schema.json": "https://github.com/badmuriss/my-llm-kit/schemas/delegation-intent-v1.json",
            "placement.schema.json": "https://github.com/badmuriss/my-llm-kit/schemas/agent-graph-placement.json",
            "execution-profile.schema.json": "https://github.com/badmuriss/my-llm-kit/schemas/agent-graph-execution-profile.json",
            "context-capsule.schema.json": "https://github.com/badmuriss/my-llm-kit/schemas/agent-graph-context-capsule.json",
        }
        resources = []
        schemas = {}
        for name, schema_id in ids.items():
            schema = json.loads((ROOT / "skills/agent-graph/references" / name).read_text())
            schemas[name] = schema
            resources.append((schema_id, Resource.from_contents(schema)))
        registry = Registry().with_resources(resources)
        cases = [
            ("agent-graph-view.schema.json", "agent-graph-view.json"),
            ("run-progress-summary.schema.json", "run-progress-summary.json"),
            ("maestro-mutation.schema.json", "maestro-mutation.json"),
            ("delegation-intent.schema.json", "delegation-intent.json"),
        ]
        for schema_name, fixture_name in cases:
            Draft202012Validator(schemas[schema_name], registry=registry).validate(json.loads((FIXTURES / fixture_name).read_text()))
        core_contracts = json.dumps({
            "view": schemas["agent-graph-view.schema.json"],
            "intent": schemas["delegation-intent.schema.json"],
        }).casefold()
        for private_term in ("maestro-mutation", "terminal_id", "incarnation_id", "process_root", "position", "orca"):
            self.assertNotIn(private_term, core_contracts)

    def test_started_delegated_child_projects_semantics_without_provider_owner(self) -> None:
        scope = _scope()
        profile = json.loads((FIXTURES / "execution-profiles.json").read_text())["current_folder"]
        owner = {"execution_host_id": "host-local", "workspace_key": "folder:folder-local-01", "attempt_id": "child-1", "terminal_id": None, "incarnation_id": None, "process_root": None, "provenance": "orca-supervised:runtime:worktree:run:dispatch"}
        projection = {"workspace_scope": scope, "coordinator": {"id": "coordinator-3", "generation": 3}, "run_id": scope["run_id"], "last_sequence": 12, "tasks": {"MLK-01": {"status": "running", "contract": {"title": "A", "depends": []}, "attempt_ids": ["parent-1"]}}, "attempts": {"parent-1": {"status": "running", "execution_profile": profile}}, "cleanup": {"cleanup-child": {"cleanup_id": "cleanup-child", "attempt_id": "child-1", "owner": owner, "status": "pending"}}, "delegations": {"intent-1": {"status": "started", "parent_task_id": "MLK-01", "parent_attempt_id": "parent-1", "child_attempt_id": "child-1", "execution_profile": profile, "resource_owner": owner, "lifecycle_receipts": {"started": {"receipt_id": "receipt-1"}}}}}
        view = build_snapshot(projection, change="change", capabilities={"agents": ["codex"], "efforts": ["high"], "placement_kinds": ["current-workspace"], "watch_deltas": True})
        node_ids = {node["id"] for node in view["nodes"]}
        self.assertIn("attempt-child-1", node_ids)
        self.assertTrue(all(edge["source_id"] in node_ids and edge["target_id"] in node_ids for edge in view["edges"]))
        self.assertIn({"id": "edge-spawned-intent-1", "type": "spawned_by", "source_id": "attempt-child-1", "target_id": "attempt-parent-1"}, view["edges"])
        self.assertNotIn("terminal", json.dumps(view).casefold())
        self.assertFalse(any("resource" in node for node in view["nodes"]))

    def test_cleanup_provider_records_do_not_enter_the_portable_view(self) -> None:
        scope = _scope()
        profile = json.loads((FIXTURES / "execution-profiles.json").read_text())["current_folder"]
        owner_a = {"execution_host_id": "host-local", "workspace_key": "folder:folder-local-01", "attempt_id": "cleanup-attempt-a", "terminal_id": None, "incarnation_id": None, "process_root": None, "provenance": "provider-receipt-a"}
        owner_b = {"execution_host_id": "host-local", "workspace_key": "folder:folder-local-01", "attempt_id": "cleanup-attempt-b", "terminal_id": "terminal-b", "incarnation_id": "pty-b", "process_root": 11, "provenance": "terminal-receipt-b"}
        projection = {"workspace_scope": scope, "coordinator": {"id": "coordinator-3", "generation": 3}, "run_id": scope["run_id"], "last_sequence": 12, "tasks": {"MLK-01": {"status": "running", "contract": {"title": "A", "depends": []}, "attempt_ids": []}}, "attempts": {}, "cleanup": {"cleanup-a": {"cleanup_id": "cleanup-a", "attempt_id": "cleanup-attempt-a", "owner": owner_a, "status": "pending"}, "cleanup-b": {"cleanup_id": "cleanup-b", "attempt_id": "cleanup-attempt-b", "owner": owner_b, "status": "verified"}}, "delegations": {}}
        view = build_snapshot(projection, change="change", capabilities={"agents": ["codex"], "efforts": ["high"], "placement_kinds": ["current-workspace"], "watch_deltas": True})
        self.assertFalse(any(node["type"] == "cleanup" for node in view["nodes"]))
        self.assertNotIn("terminal-b", json.dumps(view))
        projection["cleanup"] = []
        with self.assertRaisesRegex(MaestroBridgeError, "cleanup projection"):
            build_snapshot(projection, change="change", capabilities={"agents": ["codex"], "efforts": ["high"], "placement_kinds": ["current-workspace"], "watch_deltas": True})

    def test_two_process_submits_preserve_distinct_inbox_requests(self) -> None:
        scope = _scope()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scope_path = root / "scope.json"
            scope_path.write_text(json.dumps(scope))
            code = """
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[3])
from maestro_bridge import CoordinatorInbox
scope=json.loads(Path(sys.argv[1]).read_text())
request={"schema_version":1,"protocol":"maestro-mutation/v1","mutation_id":sys.argv[4],"workspace":{"repository_id":scope["repository_id"],"execution_host_id":scope["orchestration_home"]["execution_host_id"],"workspace_key":scope["orchestration_home"]["workspace_key"],"run_id":scope["run_id"]},"actor":{"actor_id":"user-17","kind":"user","authenticated":True,"session_id":"session-42"},"coordinator_generation":scope["coordinator_generation"],"expected_revision":12,"operation":{"kind":"move-node","node_id":"task-mlk-01","position":{"x":int(sys.argv[5]),"y":20}}}
CoordinatorInbox(Path(sys.argv[2])).submit(request, kind="mutation", workspace_scope=scope, current_revision=12)
"""
            env = dict(os.environ)
            env["PYTHONPATH"] = str(ROOT / "skills/agent-graph/scripts")
            processes = [subprocess.Popen([sys.executable, "-c", code, str(scope_path), str(root), str(ROOT / "skills/agent-graph/scripts"), f"mutation-{index}", str(index)], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for index in (1, 2)]
            results = [process.communicate(timeout=10) for process in processes]
            self.assertTrue(all(process.returncode == 0 for process in processes), results)
            self.assertEqual({item["request_id"] for item in CoordinatorInbox(root).pending()}, {"mutation-1", "mutation-2"})

    def test_public_commands_recover_consume_ack_windows_and_do_not_append_visual_events(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            scope, run_directory, journal = _run(repository)
            mutation = _mutation(scope, revision=1, mutation_id="mutation-crash")
            mutation["workspace"]["run_id"] = scope["run_id"]
            mutation_path = repository / "mutation.json"
            mutation_path.write_text(json.dumps(mutation))
            submit_args = SimpleNamespace(repo=repository, change="change", run_id=scope["run_id"], request=mutation_path.name, kind="mutation", generation=3)
            inbox = CoordinatorInbox(run_directory)
            inbox.persist_capabilities({"protocol_major": 1, "agents": ["codex"], "efforts": ["medium"], "placement_kinds": ["current-workspace"], "watch_deltas": True}, coordinator_id="coordinator-3", generation=3, workspace_scope=scope)
            agent_graph.command_maestro_submit(submit_args)
            with self.assertRaisesRegex(Exception, "active coordinator"):
                agent_graph.command_maestro_consume(SimpleNamespace(repo=repository, change="change", run_id=scope["run_id"], request_id="mutation-crash", coordinator_id="coordinator-other", generation=3))
            inbox.consume("mutation-crash", coordinator_id="coordinator-3", generation=3, workspace_scope=scope, current_revision=1, valid_node_ids={"task-MLK-01"})
            consume_args = SimpleNamespace(repo=repository, change="change", run_id=scope["run_id"], request_id="mutation-crash", coordinator_id="coordinator-3", generation=3)
            first_receipt = agent_graph.command_maestro_consume(consume_args)
            self.assertEqual(first_receipt["status"], "acked")
            self.assertEqual(first_receipt["mutation_id"], "mutation-crash")
            self.assertEqual(set(first_receipt), {"request_id", "kind", "status", "idempotent", "revision", "affected_entity_ids", "affected_event_ids", "warnings", "mutation_id"})
            self.assertEqual(first_receipt["revision"], 1)
            self.assertEqual(first_receipt["affected_entity_ids"], ["task-MLK-01"])
            self.assertEqual(first_receipt["warnings"], [])
            self.assertNotIn("payload", first_receipt)
            self.assertNotIn("body", first_receipt)
            self.assertNotIn("applied_revision", first_receipt)
            self.assertNotIn("affected_node_ids", first_receipt)
            agent_graph.command_maestro_ack(SimpleNamespace(repo=repository, change="change", run_id=scope["run_id"], request_id="mutation-crash", coordinator_id="coordinator-3", generation=3))
            self.assertEqual(journal.verify_projection()["last_sequence"], 1)
            self.assertEqual(inbox.get("mutation-crash")["status"], "acked")
            journal.append("coordinator_claimed", {"coordinator_id": "coordinator-3"}, coordinator_generation=3)
            replay_events = (run_directory / "events.jsonl").read_bytes()
            replay_state = (run_directory / "state.json").read_bytes()
            replay_requests = inbox.path.read_bytes()
            replay_visual = (inbox.directory / "visual-state.json").read_bytes()
            with patch.object(agent_graph, "build_snapshot", side_effect=AssertionError("acked replay must not snapshot")):
                replay_receipt = agent_graph.command_maestro_consume(consume_args)
                ack_replay = agent_graph.command_maestro_ack(SimpleNamespace(repo=repository, change="change", run_id=scope["run_id"], request_id="mutation-crash", coordinator_id="coordinator-3", generation=3))
            self.assertTrue(replay_receipt["idempotent"])
            self.assertEqual(set(replay_receipt), set(first_receipt))
            self.assertEqual(replay_receipt["revision"], first_receipt["revision"])
            self.assertEqual(replay_receipt["affected_entity_ids"], first_receipt["affected_entity_ids"])
            self.assertEqual(replay_receipt["affected_event_ids"], first_receipt["affected_event_ids"])
            self.assertEqual(replay_receipt["warnings"], first_receipt["warnings"])
            self.assertTrue(ack_replay["idempotent"])
            self.assertEqual(replay_events, (run_directory / "events.jsonl").read_bytes())
            self.assertEqual(replay_state, (run_directory / "state.json").read_bytes())
            self.assertEqual(replay_requests, inbox.path.read_bytes())
            self.assertEqual(replay_visual, (inbox.directory / "visual-state.json").read_bytes())
            note = json.loads((FIXTURES / "maestro-mutation.json").read_text())
            note["workspace"]["run_id"] = scope["run_id"]
            note["expected_revision"] = 2
            note["mutation_id"] = "mutation-note-crash"
            note_path = repository / "note.json"
            note_path.write_text(json.dumps(note))
            agent_graph.command_maestro_submit(SimpleNamespace(repo=repository, change="change", run_id=scope["run_id"], request=note_path.name, kind="mutation", generation=3))
            agent_graph.command_maestro_consume(SimpleNamespace(repo=repository, change="change", run_id=scope["run_id"], request_id="mutation-note-crash", coordinator_id="coordinator-3", generation=3))
            visual_state = inbox.read_visual_state()
            view = build_snapshot(journal.verify_projection(), change="change", capabilities={"agents": ["codex"], "efforts": ["medium"], "placement_kinds": ["current-workspace"], "watch_deltas": True}, visual_state=visual_state)
            self.assertEqual(visual_state["positions"]["task-MLK-01"], {"x": 10, "y": 20})
            self.assertTrue(visual_state["notes"])
            self.assertFalse(any("position" in node for node in view["nodes"]))
            self.assertFalse(any(node["type"] == "note-reference" for node in view["nodes"]))
            bad = _mutation(scope, revision=2, mutation_id="mutation-opaque-bad")
            bad["operation"]["node_id"] = "task-mlk-01"
            bad_path = repository / "bad.json"
            bad_path.write_text(json.dumps(bad))
            agent_graph.command_maestro_submit(SimpleNamespace(repo=repository, change="change", run_id=scope["run_id"], request=bad_path.name, kind="mutation", generation=3))
            requests_before = inbox.path.read_bytes()
            visual_before = (inbox.directory / "visual-state.json").read_bytes()
            events_before = (run_directory / "events.jsonl").read_bytes()
            state_before = (run_directory / "state.json").read_bytes()
            with self.assertRaisesRegex(Exception, "exact node"):
                agent_graph.command_maestro_consume(SimpleNamespace(repo=repository, change="change", run_id=scope["run_id"], request_id="mutation-opaque-bad", coordinator_id="coordinator-3", generation=3))
            self.assertEqual(requests_before, inbox.path.read_bytes())
            self.assertEqual(visual_before, (inbox.directory / "visual-state.json").read_bytes())
            self.assertEqual(events_before, (run_directory / "events.jsonl").read_bytes())
            self.assertEqual(state_before, (run_directory / "state.json").read_bytes())
            self.assertNotIn("task-mlk-01", inbox.read_visual_state()["positions"])

    def test_public_ack_rejects_workspace_divergence_before_visual_effect(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            scope, run_directory, _ = _run(repository)
            inbox = CoordinatorInbox(run_directory)
            inbox.persist_capabilities({"protocol_major": 1, "agents": ["codex"], "efforts": ["medium"], "placement_kinds": ["current-workspace"], "watch_deltas": True}, coordinator_id="coordinator-3", generation=3, workspace_scope=scope)
            mutation = _mutation(scope, revision=1, mutation_id="mutation-workspace-divergence")
            path = repository / "mutation.json"
            path.write_text(json.dumps(mutation))
            agent_graph.command_maestro_submit(SimpleNamespace(repo=repository, change="change", run_id=scope["run_id"], request=path.name, kind="mutation", generation=3))
            inbox.consume("mutation-workspace-divergence", coordinator_id="coordinator-3", generation=3, workspace_scope=scope, current_revision=1, valid_node_ids={"task-MLK-01"})
            records = json.loads(inbox.path.read_text())
            records["mutation-workspace-divergence"]["payload"]["workspace"]["workspace_key"] = "folder:other"
            records["mutation-workspace-divergence"]["payload_sha256"] = canonical_sha256(records["mutation-workspace-divergence"]["payload"])
            records["mutation-workspace-divergence"] = inbox._with_integrity(records["mutation-workspace-divergence"])
            inbox._write(records)
            visual_before = (inbox.directory / "visual-state.json").read_bytes() if (inbox.directory / "visual-state.json").exists() else None
            with self.assertRaisesRegex(Exception, "current workspace"):
                agent_graph.command_maestro_ack(SimpleNamespace(repo=repository, change="change", run_id=scope["run_id"], request_id="mutation-workspace-divergence", coordinator_id="coordinator-3", generation=3))
            visual_after = (inbox.directory / "visual-state.json").read_bytes() if (inbox.directory / "visual-state.json").exists() else None
            self.assertEqual(visual_before, visual_after)

    def test_public_submit_fences_other_checkout_before_creating_inbox(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            scope, run_directory, _ = _run(repository)
            request = _mutation(scope, revision=1, mutation_id="mutation-other-checkout")
            request_path = repository / "request.json"
            request_path.write_text(json.dumps(request))
            inbox_directory = run_directory / "artifacts" / "maestro-inbox"
            def inbox_snapshot() -> tuple[bool, tuple[tuple[str, bytes], ...]]:
                if not inbox_directory.exists():
                    return False, ()
                return True, tuple(
                    (path.relative_to(inbox_directory).as_posix(), path.read_bytes())
                    for path in sorted(inbox_directory.rglob("*"))
                    if path.is_file()
                )
            inbox_before = inbox_snapshot()
            output = io.StringIO()
            error = io.StringIO()
            with patch.object(agent_graph, "_invocation_control_runtime", return_value=None), contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
                code = agent_graph.main(["maestro-submit", "--repo", str(repository), "--change", "change", "--run-id", scope["run_id"], "--generation", "3", "--kind", "mutation", "--request", request_path.name])
            self.assertEqual(code, 1)
            error_payload = json.loads(error.getvalue())
            self.assertEqual(error_payload["error"]["code"], "workspace_binding_invalid")
            self.assertEqual(inbox_snapshot(), inbox_before)
            self.assertFalse(inbox_directory.exists())

    def test_real_cli_argv_and_stdout_emit_schema_valid_uncompacted_view(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            scope, run_directory, _ = _run(repository)
            CoordinatorInbox(run_directory).persist_capabilities(
                {"protocol_major": 1, "agents": ["codex"], "efforts": ["medium"], "placement_kinds": ["current-workspace"], "watch_deltas": True},
                coordinator_id="coordinator-3", generation=3, workspace_scope=scope,
            )
            output = io.StringIO()
            with patch.object(agent_graph, "_invocation_control_runtime", return_value=None), contextlib.redirect_stdout(output):
                self.assertEqual(agent_graph.main(["maestro-view", "--repo", str(repository), "--change", "change", "--run-id", scope["run_id"], "--kind", "snapshot"]), 0)
            envelope = json.loads(output.getvalue())
            view = envelope["result"]
            self.assertEqual(validate_agent_graph_view(view), view)
            self.assertEqual(envelope["command"], "maestro-view")

    def test_public_intent_retry_acks_only_after_canonical_event_exists(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            scope, run_directory, journal = _run(repository)
            profile = json.loads((FIXTURES / "execution-profiles.json").read_text())["current_folder"]
            journal.append(
                "attempt_reserved",
                {
                    "task_id": "MLK-01",
                    "attempt_id": "attempt-1",
                    "workspace_scope": scope,
                    "execution_profile": profile,
                },
                coordinator_generation=3,
            )
            effective_scope = journal.verify_projection()["attempts"]["attempt-1"]["effective_scope"]
            journal.append(
                "attempt_scope_frozen",
                {"attempt_id": "attempt-1", "effective_scope": effective_scope},
                coordinator_generation=3,
            )
            journal.append(
                "attempt_started",
                {
                    "task_id": "MLK-01",
                    "attempt_id": "attempt-1",
                    "execution_profile": profile,
                    "workspace_scope": scope,
                    "effective_scope": effective_scope,
                },
                coordinator_generation=3,
            )
            CoordinatorInbox(run_directory).persist_capabilities({"protocol_major": 1, "agents": ["codex"], "efforts": ["medium"], "placement_kinds": ["current-workspace"], "watch_deltas": True}, coordinator_id="coordinator-3", generation=3, workspace_scope=scope)
            intent = json.loads((FIXTURES / "delegation-intent.json").read_text())
            intent["workspace"]["run_id"] = scope["run_id"]
            intent["parent_attempt_id"] = "attempt-1"
            intent["expected_revision"] = 4
            path = repository / "intent.json"
            path.write_text(json.dumps(intent))
            agent_graph.command_maestro_submit(SimpleNamespace(repo=repository, change="change", run_id=scope["run_id"], request=path.name, kind="intent", generation=3))
            with self.assertRaisesRegex(Exception, "canonical delegation event"):
                agent_graph.command_maestro_ack(SimpleNamespace(repo=repository, change="change", run_id=scope["run_id"], request_id=intent["intent_id"], coordinator_id="coordinator-3", generation=3))
            inbox = CoordinatorInbox(run_directory)
            inbox.consume(intent["intent_id"], coordinator_id="coordinator-3", generation=3, workspace_scope=scope, current_revision=4)
            consume_args = SimpleNamespace(repo=repository, change="change", run_id=scope["run_id"], request_id=intent["intent_id"], coordinator_id="coordinator-3", generation=3)
            first_receipt = agent_graph.command_maestro_consume(consume_args)
            self.assertEqual(inbox.get(intent["intent_id"])["status"], "acked")
            self.assertEqual(set(first_receipt), {"request_id", "kind", "status", "idempotent", "revision", "affected_entity_ids", "affected_event_ids", "warnings", "intent_id"})
            self.assertEqual(first_receipt["revision"], 5)
            self.assertEqual(first_receipt["affected_event_ids"], ["event-000005"])
            self.assertEqual(first_receipt["warnings"], [])
            self.assertEqual(journal.verify_projection()["delegations"][intent["intent_id"]]["intent"], intent)
            ack_args = SimpleNamespace(repo=repository, change="change", run_id=scope["run_id"], request_id=intent["intent_id"], coordinator_id="coordinator-3", generation=3)
            journal.append("coordinator_claimed", {"coordinator_id": "coordinator-3"}, coordinator_generation=3)
            replay = agent_graph.command_maestro_consume(consume_args)
            self.assertTrue(replay["idempotent"])
            self.assertEqual(set(replay), set(first_receipt))
            self.assertEqual(replay["revision"], first_receipt["revision"])
            self.assertEqual(replay["affected_entity_ids"], first_receipt["affected_entity_ids"])
            self.assertEqual(replay["affected_event_ids"], first_receipt["affected_event_ids"])
            self.assertEqual(replay["warnings"], first_receipt["warnings"])
            self.assertTrue(agent_graph.command_maestro_ack(ack_args)["idempotent"])

    def test_public_negotiation_and_view_delta_reset_use_persisted_capabilities(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            scope, run_directory, journal = _run(repository)
            local = {"protocol_majors": [1], "agents": ["codex"], "efforts": ["medium"], "placement_kinds": ["current-workspace"], "watch_deltas": True}
            remote = dict(local)
            (repository / "local.json").write_text(json.dumps(local))
            (repository / "remote.json").write_text(json.dumps(remote))
            args = SimpleNamespace(repo=repository, change="change", run_id=scope["run_id"], generation=3, local_capabilities="local.json", remote_capabilities="remote.json")
            agent_graph.command_maestro_negotiate(args)
            view_args = SimpleNamespace(repo=repository, change="change", run_id=scope["run_id"], kind="snapshot", from_view=None)
            snapshot = agent_graph.command_maestro_view(view_args)
            view_path = repository / "view.json"
            view_path.write_text(json.dumps(snapshot))
            delta = agent_graph.command_maestro_view(SimpleNamespace(repo=repository, change="change", run_id=scope["run_id"], kind="delta", from_view="view.json"))
            reset = agent_graph.command_maestro_view(SimpleNamespace(repo=repository, change="change", run_id=scope["run_id"], kind="reset", from_view="view.json"))
            self.assertEqual(delta["capabilities"]["agents"], ["codex"])
            self.assertTrue(reset["reset_required"])
            journal_bytes = (run_directory / "events.jsonl").read_bytes()
            state_bytes = (run_directory / "state.json").read_bytes()
            (repository / "malformed.json").write_text("{}")
            with self.assertRaises(Exception):
                agent_graph.command_maestro_view(SimpleNamespace(repo=repository, change="change", run_id=scope["run_id"], kind="delta", from_view="malformed.json"))
            cross_context = json.loads(view_path.read_text())
            cross_context["change"] = "other-change"
            (repository / "cross.json").write_text(json.dumps(cross_context))
            with self.assertRaises(Exception):
                agent_graph.command_maestro_view(SimpleNamespace(repo=repository, change="change", run_id=scope["run_id"], kind="delta", from_view="cross.json"))
            self.assertEqual(journal_bytes, (run_directory / "events.jsonl").read_bytes())
            self.assertEqual(state_bytes, (run_directory / "state.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
