from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from jsonschema import Draft202012Validator, ValidationError


SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from browser_surfaces import (  # noqa: E402
    BrowserSurfaceError,
    unavailable_receipt,
    validate_browser_surface_request,
    validate_receipt_for_request,
    visible_paint_proven,
)
import agent_graph  # noqa: E402
from graph_core import (  # noqa: E402
    GraphValidationError,
    JournalError,
    TaskContract,
    apply_event,
    empty_projection,
    validate_worker_result,
)
from maestro_bridge import build_delta, build_snapshot  # noqa: E402


FIXTURES = Path(__file__).parents[1] / "fixtures" / "maestro-protocol-v1"


def request(*, mode: str = "visible", page_binding: dict | None = None) -> dict:
    return {
        "schema_version": 1,
        "request_id": "surface-request-1",
        "task_id": "MLK-07B",
        "attempt_id": "attempt-1",
        "idempotency_key": "surface-key-1",
        "mode": mode,
        "retention": "release",
        "execution_host_id": "host-local",
        "workspace_key": "folder:workspace-1",
        "page_binding": page_binding,
        "binding": {"kind": "initial_url", "value": "https://example.test/preview"},
        "viewport": {"width": 1280, "height": 720},
        "source_revision": "commit-123",
    }


def receipt(
    requested: dict,
    *,
    operation: str,
    status: str,
    visibility: str = "visible",
    focus: str = "focused",
    paint: str = "painted",
    page_binding: dict | None = None,
    unavailable: dict | None = None,
) -> dict:
    page_binding = page_binding if page_binding is not None else {"browser_page_id": "page-1", "browser_profile_id": "profile-1"}
    capture = {key: None for key in ("artifact_ref", "artifact_hash", "width", "height", "device_scale", "route_or_component", "state", "theme", "source_revision", "capture_mode", "vision_review_ref", "vision_outcome")}
    if operation == "capture" and status == "captured":
        capture.update({"artifact_ref": "artifact:.visual-evidence/surface.png", "artifact_hash": "sha256:" + "a" * 64, "width": 1280, "height": 720, "device_scale": 1, "route_or_component": "Preview", "state": "populated", "theme": "light", "source_revision": requested["source_revision"], "capture_mode": "browser-surface", "vision_review_ref": "artifact:.visual-evidence/surface-review.json", "vision_outcome": "pending"})
    return {
        "schema_version": 1,
        "receipt_id": f"receipt-{operation}-{status}",
        "request_id": requested["request_id"],
        "task_id": requested["task_id"],
        "attempt_id": requested["attempt_id"],
        "operation": operation,
        "status": status,
        "idempotency_key": requested["idempotency_key"],
        "surface": {"surface_id": "surface-1", "execution_host_id": requested["execution_host_id"], "workspace_key": requested["workspace_key"], "page_binding": page_binding, "binding": requested["binding"], "viewport": requested["viewport"], "source_revision": requested["source_revision"], "harness_owned": True},
        "observation": {"visibility": visibility, "focus": focus, "paint": paint, "native_pane_ref": "pane-1" if paint == "painted" else None},
        "capture": capture,
        "unavailability": unavailable,
    }


class BrowserSurfaceContracts(unittest.TestCase):
    def test_distinguishes_a_visible_request_from_unsupported_hidden_and_offscreen_observations(self) -> None:
        requested = request()
        for visibility, status, unavailable in (("unsupported", "unsupported", {"code": "unsupported", "detail": None}), ("hidden", "bound", None), ("offscreen", "bound", None)):
            observed = receipt(requested, operation="bind", status=status, visibility=visibility, focus="unavailable", paint="unavailable", unavailable=unavailable)
            self.assertEqual(validate_receipt_for_request(observed, requested)["observation"]["visibility"], visibility)
            self.assertFalse(visible_paint_proven(observed, requested))

    def test_requires_painted_native_pane_for_visible_proof(self) -> None:
        requested = request()
        bound = receipt(requested, operation="bind", status="bound")
        self.assertTrue(visible_paint_proven(bound, requested))
        no_focus = copy.deepcopy(bound)
        no_focus["observation"]["focus"] = "unfocused"
        self.assertFalse(visible_paint_proven(no_focus, requested))

    def test_binds_a_created_page_only_after_reservation(self) -> None:
        requested = request(page_binding=None)
        reserved = receipt(requested, operation="reserve", status="reserved", visibility="unavailable", focus="unavailable", paint="unavailable", page_binding=None)
        reserved["surface"]["page_binding"] = None
        self.assertIsNone(validate_receipt_for_request(reserved, requested)["surface"]["page_binding"])
        bound = receipt(requested, operation="bind", status="bound")
        self.assertEqual(validate_receipt_for_request(bound, requested)["surface"]["page_binding"]["browser_page_id"], "page-1")

    def test_rejects_adopted_page_identity_drift(self) -> None:
        requested = request(page_binding={"browser_page_id": "page-expected", "browser_profile_id": "profile-expected"})
        observed = receipt(requested, operation="bind", status="bound")
        with self.assertRaisesRegex(BrowserSurfaceError, "page_binding"):
            validate_receipt_for_request(observed, requested)

    def test_rejects_offscreen_focus_or_paint(self) -> None:
        requested = request(mode="offscreen")
        for focus, paint in (("focused", "unpainted"), ("unfocused", "painted")):
            observed = receipt(requested, operation="bind", status="bound", visibility="offscreen", focus=focus, paint=paint)
            with self.assertRaises(BrowserSurfaceError):
                validate_receipt_for_request(observed, requested)

    def test_preserves_typed_capture_and_release_uncertainty(self) -> None:
        requested = request()
        for operation, status, code in (("capture", "outcome_unknown", "outcome-unknown"), ("release", "unverifiable", "unverifiable")):
            observed = receipt(requested, operation=operation, status=status, visibility="unavailable", focus="unavailable", paint="unavailable", page_binding=None, unavailable={"code": code, "detail": "provider-state-missing"})
            self.assertEqual(validate_receipt_for_request(observed, requested)["status"], status)

    def test_rejects_authorization_urls_fragments_unconfined_refs_and_invalid_hashes(self) -> None:
        for url in ("https://user:password@example.test/", "https://example.test/?access_token=value", "https://example.test/#token"):
            invalid = request()
            invalid["binding"]["value"] = url
            with self.assertRaises(BrowserSurfaceError):
                validate_browser_surface_request(invalid)
        requested = request()
        captured = receipt(requested, operation="capture", status="captured")
        captured["capture"]["artifact_ref"] = "../surface.png"
        with self.assertRaises(BrowserSurfaceError):
            validate_receipt_for_request(captured, requested)

        for route in ("../preview", "/preview", "https://example.test/preview", "preview?token=value", "preview#token"):
            invalid = request()
            invalid["binding"] = {"kind": "artifact_route", "value": route}
            with self.assertRaises(BrowserSurfaceError):
                validate_browser_surface_request(invalid)
        valid = request()
        valid["binding"] = {"kind": "artifact_route", "value": "previews/current"}
        self.assertEqual(validate_browser_surface_request(valid)["binding"]["value"], "previews/current")

    def test_rejects_browser_contents_in_worker_result_external_refs_and_schema(self) -> None:
        task = TaskContract("MLK-07B", "Browser", (), ("skills/agent-graph/",), "write", "auto", "Bounded", "python3 -m unittest named")
        result = {"task_id": "MLK-07B", "attempt_id": "attempt-1", "outcome": "reported", "summary": "Done.", "files_changed": [], "checks_run": ["python3 -m unittest named"], "evidence_refs": [], "questions": [], "external_refs": {"screenshot": "artifact:private.png"}}
        with self.assertRaisesRegex(GraphValidationError, "browser contents"):
            validate_worker_result(result, task, "attempt-1")
        worker_schema = json.loads((Path(__file__).parents[1] / "references" / "worker-result.schema.json").read_text())
        with self.assertRaises(ValidationError):
            Draft202012Validator(worker_schema).validate(result)

    def test_releases_only_a_reported_owned_exact_captured_binding(self) -> None:
        requested = request(page_binding=None)
        state = empty_projection()
        state.update({
            "status": "active",
            "tasks": {requested["task_id"]: {}},
            "attempts": {
                requested["attempt_id"]: {
                    "task_id": requested["task_id"],
                    "status": "running",
                    "execution_profile": {
                        "resolved_placement": {
                            "execution_host_id": requested["execution_host_id"],
                            "workspace_key": requested["workspace_key"],
                        }
                    },
                }
            },
        })
        sequence = 1
        def apply(event_type: str, data: dict) -> None:
            nonlocal state, sequence
            state = apply_event(state, {"type": event_type, "data": data, "sequence": sequence})
            sequence += 1
        apply("browser_surface_requested", requested)
        reserved = receipt(requested, operation="reserve", status="reserved", visibility="unavailable", focus="unavailable", paint="unavailable")
        reserved["surface"]["page_binding"] = None
        apply("browser_surface_receipt", {"receipt": reserved})
        bound = receipt(requested, operation="bind", status="bound")
        apply("browser_surface_receipt", {"receipt": bound})
        captured = receipt(requested, operation="capture", status="captured")
        apply("browser_surface_receipt", {"receipt": captured})
        released = receipt(requested, operation="release", status="released")
        with self.assertRaisesRegex(JournalError, "reported attempt"):
            apply("browser_surface_receipt", {"receipt": released})
        state["attempts"][requested["attempt_id"]]["status"] = "reported"
        apply("browser_surface_receipt", {"receipt": released})
        self.assertEqual(state["browser_surfaces"][requested["request_id"]]["status"], "released")

        user_requested = copy.deepcopy(requested)
        user_requested["request_id"] = "surface-request-user"
        user_requested["idempotency_key"] = "surface-key-user"
        user_state = empty_projection()
        user_state.update({
            "status": "active",
            "tasks": {user_requested["task_id"]: {}},
            "attempts": {user_requested["attempt_id"]: {"task_id": user_requested["task_id"], "status": "reported", "execution_profile": {"resolved_placement": {"execution_host_id": user_requested["execution_host_id"], "workspace_key": user_requested["workspace_key"]}}}},
        })
        user_sequence = 1

        def apply_user(event_type: str, data: dict) -> None:
            nonlocal user_state, user_sequence
            user_state = apply_event(user_state, {"type": event_type, "data": data, "sequence": user_sequence})
            user_sequence += 1

        apply_user("browser_surface_requested", user_requested)
        for operation, status in (("bind", "bound"), ("capture", "captured"), ("release", "retained")):
            observed = receipt(user_requested, operation=operation, status=status)
            observed["surface"]["harness_owned"] = False
            apply_user("browser_surface_receipt", {"receipt": observed})
        self.assertEqual(user_state["browser_surfaces"][user_requested["request_id"]]["status"], "retained")

    def test_rejects_page_binding_drift_after_the_first_successful_bind(self) -> None:
        requested = request(page_binding=None)
        state = empty_projection()
        state.update({
            "status": "active",
            "tasks": {requested["task_id"]: {}},
            "attempts": {
                requested["attempt_id"]: {
                    "task_id": requested["task_id"],
                    "status": "reported",
                    "execution_profile": {
                        "resolved_placement": {
                            "execution_host_id": requested["execution_host_id"],
                            "workspace_key": requested["workspace_key"],
                        }
                    },
                }
            },
        })
        sequence = 1
        def apply(event_type: str, data: dict) -> None:
            nonlocal state, sequence
            state = apply_event(state, {"type": event_type, "data": data, "sequence": sequence})
            sequence += 1
        apply("browser_surface_requested", requested)
        reserved = receipt(requested, operation="reserve", status="reserved", visibility="unavailable", focus="unavailable", paint="unavailable")
        reserved["surface"]["page_binding"] = None
        apply("browser_surface_receipt", {"receipt": reserved})
        apply("browser_surface_receipt", {"receipt": receipt(requested, operation="bind", status="bound")})
        drifted = receipt(requested, operation="capture", status="captured", page_binding={"browser_page_id": "page-2", "browser_profile_id": "profile-1"})
        with self.assertRaisesRegex(JournalError, "page binding drifted"):
            apply("browser_surface_receipt", {"receipt": drifted})

    def test_replays_fenced_operations_and_preserves_pinned_identity_for_unavailable_release(self) -> None:
        requested = request(page_binding=None)
        state = empty_projection()
        state.update({
            "status": "active",
            "coordinator": {"id": "coordinator-1", "generation": 1},
            "tasks": {requested["task_id"]: {}},
            "attempts": {requested["attempt_id"]: {"task_id": requested["task_id"], "status": "reported", "execution_profile": {"resolved_placement": {"execution_host_id": requested["execution_host_id"], "workspace_key": requested["workspace_key"]}}}},
        })

        class Journal:
            def __init__(self, projection: dict) -> None:
                self.projection = projection
                self.sequence = 1

            def verify_projection(self) -> dict:
                return self.projection

            def append(self, event_type: str, data: dict, *, coordinator_generation: int) -> dict:
                self.projection = apply_event(self.projection, {"type": event_type, "data": data, "sequence": self.sequence})
                self.sequence += 1
                return self.projection

        bound = receipt(requested, operation="bind", status="bound")
        captured = receipt(requested, operation="capture", status="captured")
        unavailable = unavailable_receipt(requested, operation="release", code="remote-unreachable")

        class Driver:
            def bind_browser_surface(self, _request: dict) -> SimpleNamespace:
                return SimpleNamespace(external_refs={"browser_surface": bound})

            def capture_browser_surface(self, _request: dict) -> SimpleNamespace:
                return SimpleNamespace(external_refs={"browser_surface": captured})

            def release_browser_surface(self, _request: dict) -> SimpleNamespace:
                return SimpleNamespace(external_refs={"browser_surface": unavailable})

        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            request_path = repository / "surface.json"
            request_path.write_text(json.dumps(requested), encoding="utf-8")
            journal = Journal(state)
            arguments = SimpleNamespace(repo=repository, change="change", run_id="run-1", generation=1, request="surface.json")
            with patch.object(agent_graph, "_run_directory", return_value=repository), patch.object(agent_graph, "_journal", return_value=journal), patch.object(agent_graph, "_generation", return_value=1), patch.object(agent_graph, "_driver_for_state", return_value=Driver()):
                arguments.operation = "bind"
                agent_graph.command_browser_surface(arguments)
                arguments.operation = "capture"
                agent_graph.command_browser_surface(arguments)
                capture_replay = agent_graph.command_browser_surface(arguments)
                arguments.operation = "release"
                release = agent_graph.command_browser_surface(arguments)
                release_replay = agent_graph.command_browser_surface(arguments)

        self.assertTrue(capture_replay["idempotent"])
        self.assertTrue(release_replay["idempotent"])
        self.assertEqual(release["receipt"]["surface"], bound["surface"])
        self.assertEqual(journal.projection["browser_surfaces"][requested["request_id"]]["status"], "unavailable")

    def test_preserves_pinned_surface_for_each_post_bind_uncertainty(self) -> None:
        for operation, status, code in (("capture", "unavailable", "remote-unreachable"), ("capture", "outcome_unknown", "outcome-unknown"), ("release", "unverifiable", "unverifiable")):
            with self.subTest(code=code):
                requested = request(page_binding=None)
                state = empty_projection()
                state.update({"status": "active", "tasks": {requested["task_id"]: {}}, "attempts": {requested["attempt_id"]: {"task_id": requested["task_id"], "status": "reported", "execution_profile": {"resolved_placement": {"execution_host_id": requested["execution_host_id"], "workspace_key": requested["workspace_key"]}}}}})
                sequence = 1

                def apply(event_type: str, data: dict) -> None:
                    nonlocal state, sequence
                    state = apply_event(state, {"type": event_type, "data": data, "sequence": sequence})
                    sequence += 1

                apply("browser_surface_requested", requested)
                bound = receipt(requested, operation="bind", status="bound")
                apply("browser_surface_receipt", {"receipt": bound})
                if operation == "release":
                    apply("browser_surface_receipt", {"receipt": receipt(requested, operation="capture", status="captured")})
                uncertain = unavailable_receipt(requested, operation=operation, code=code)
                uncertain["surface"] = copy.deepcopy(bound["surface"])
                apply("browser_surface_receipt", {"receipt": uncertain})
                self.assertEqual(state["browser_surfaces"][requested["request_id"]]["status"], status)

    def test_projects_fixture_capture_into_snapshot_and_delta_without_browser_contents(self) -> None:
        fixture = json.loads((FIXTURES / "browser-surfaces.json").read_text())
        requested = validate_browser_surface_request(fixture["request"])
        self.assertEqual(requested["binding"], fixture["request"]["binding"])
        self.assertEqual(requested["viewport"], fixture["request"]["viewport"])
        self.assertEqual(requested["source_revision"], fixture["request"]["source_revision"])
        self.assertEqual(requested["retention"], fixture["request"]["retention"])
        captured = receipt(requested, operation="capture", status="captured")
        captured["receipt_id"] = fixture["resume"]["capture_receipt_id"]
        captured["capture"] = fixture["capture"]
        validate_receipt_for_request(captured, requested)
        self.assertEqual(captured["capture"]["artifact_hash"], fixture["capture"]["artifact_hash"])
        self.assertEqual(captured["capture"]["vision_review_ref"], fixture["capture"]["vision_review_ref"])

        profile = json.loads((FIXTURES / "execution-profiles.json").read_text())["current_folder"]
        scope = json.loads((FIXTURES / "workspace-scopes.json").read_text())["folder_local"]
        projection = {
            "workspace_scope": scope,
            "coordinator": {"id": "coordinator-1", "generation": 3},
            "run_id": scope["run_id"],
            "last_sequence": 1,
            "tasks": {requested["task_id"]: {"status": "reported", "contract": {"title": "Browser", "depends": []}, "attempt_ids": [requested["attempt_id"]]}},
            "attempts": {requested["attempt_id"]: {"status": "reported", "execution_profile": profile}},
            "cleanup": {},
            "delegations": {},
            "browser_surfaces": {requested["request_id"]: {"request": requested, "status": "captured", "receipts": {"capture": captured}}},
        }
        capabilities = {"agents": ["codex"], "efforts": ["medium"], "placement_kinds": ["current-workspace"], "watch_deltas": True}
        first = agent_graph._browser_surface_view(build_snapshot(projection, change="change", capabilities=capabilities, last_event={"sequence": 1, "timestamp": "2026-08-22T09:04:01Z", "type": "browser_surface_captured"}), projection)
        surface_node = next(node for node in first["nodes"] if node["type"] == "browser-surface")
        evidence_node = next(node for node in first["nodes"] if node["summary"] == "Bounded browser-surface visual evidence.")
        self.assertEqual(surface_node["status"], "captured")
        self.assertEqual(evidence_node["status"], fixture["capture"]["vision_outcome"])
        self.assertTrue(any(edge["type"] == "uses" and edge["target_id"] == surface_node["id"] for edge in first["edges"]))
        self.assertTrue(any(edge["type"] == "produces" and edge["source_id"] == surface_node["id"] and edge["target_id"] == evidence_node["id"] for edge in first["edges"]))
        self.assertNotIn("browser_page_id", json.dumps(first))
        projection["last_sequence"] = 2
        projection["browser_surfaces"][requested["request_id"]]["status"] = "retained"
        second = agent_graph._browser_surface_view(build_snapshot(projection, change="change", capabilities=capabilities, last_event={"sequence": 2, "timestamp": "2026-08-22T09:04:02Z", "type": "browser_surface_released"}), projection)
        delta = build_delta(first, second, change="change", from_cursor=first["cursor"], capabilities=capabilities)
        self.assertTrue(any(node["type"] == "browser-surface" and node["status"] == "retained" for node in delta["nodes"]))
        resume_state = empty_projection()
        resume_state.update({"status": "active", "tasks": {requested["task_id"]: {}}, "attempts": {requested["attempt_id"]: {"task_id": requested["task_id"], "status": "reported", "execution_profile": {"resolved_placement": {"execution_host_id": requested["execution_host_id"], "workspace_key": requested["workspace_key"]}}}}})
        resume_sequence = 1

        def apply_resume(event_type: str, data: dict) -> None:
            nonlocal resume_state, resume_sequence
            resume_state = apply_event(resume_state, {"type": event_type, "data": data, "sequence": resume_sequence})
            resume_sequence += 1

        apply_resume("browser_surface_requested", requested)
        apply_resume("browser_surface_receipt", {"receipt": receipt(requested, operation="bind", status="bound")})
        apply_resume("browser_surface_receipt", {"receipt": captured})
        apply_resume("browser_surface_receipt", {"receipt": captured})
        resumed_release = receipt(requested, operation="release", status="released")
        resumed_release["receipt_id"] = fixture["resume"]["release_receipt_id"]
        apply_resume("browser_surface_receipt", {"receipt": resumed_release})
        apply_resume("browser_surface_receipt", {"receipt": resumed_release})
        self.assertTrue(fixture["resume"]["idempotent"])
        self.assertEqual(fixture["resume"]["release_receipt_id"], "receipt-release-1")
        self.assertEqual(resume_state["browser_surfaces"][requested["request_id"]]["status"], "released")

    def test_validates_local_request_and_receipt_schema_references(self) -> None:
        references = Path(__file__).parents[1] / "references"
        request_schema = json.loads((references / "browser-surface-request.schema.json").read_text())
        receipt_schema = json.loads((references / "browser-surface-receipt.schema.json").read_text())
        Draft202012Validator.check_schema(request_schema)
        Draft202012Validator.check_schema(receipt_schema)
        Draft202012Validator(request_schema).validate(request())
        Draft202012Validator(receipt_schema).validate(receipt(request(), operation="capture", status="captured"))
        requested = request()
        captured = receipt(requested, operation="capture", status="captured")
        captured["capture"]["artifact_hash"] = "sha256:abc"
        with self.assertRaises(BrowserSurfaceError):
            validate_receipt_for_request(captured, requested)
