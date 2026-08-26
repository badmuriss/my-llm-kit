import hashlib
import importlib.util
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
CLI = ROOT / "scripts" / "agent_graph.py"
FIXTURE = Path(__file__).parent / "fixtures" / "maestro-host-run" / "scenario.json"
SPEC = importlib.util.spec_from_file_location("host_run_context", ROOT / "scripts" / "context_capsules.py")
assert SPEC and SPEC.loader
context_capsules = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = context_capsules
SPEC.loader.exec_module(context_capsules)
sys.path.insert(0, str(ROOT / "scripts"))
import adaptive_intake  # noqa: E402
import agent_graph as runtime  # noqa: E402
import routing  # noqa: E402
from drivers.base import resolve_capability_request  # noqa: E402
from drivers.host import HostDriver  # noqa: E402


class PortableHostRunBehavior(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.temp = tempfile.TemporaryDirectory()
        self.repository = Path(self.temp.name).resolve()
        change = self.repository / "openspec/changes/host-run"
        change.mkdir(parents=True)
        prebootstrap_frontend_path = self.repository / "frontend/prebootstrap.tsx"
        prebootstrap_frontend_path.parent.mkdir(parents=True)
        prebootstrap_frontend_path.write_text(
            "export const prebootstrap = 'initial';\n", encoding="utf-8"
        )
        for name in ("proposal.md", "design.md"):
            (change / name).write_text("# Host run\n", encoding="utf-8")
        (change / "tasks.md").write_text(self.fixture["tasks_markdown"], encoding="utf-8")
        graph = runtime.parse_task_graph(change / "tasks.md")
        transition = adaptive_intake.decide_process(
            self.repository,
            request="Execute the portable Host graph fixture.",
            check_command=graph.tasks[0].check,
            signals={
                "known_scope": True,
                "graph_requested": True,
                "cohesion": "independent",
                "independent_packets": [
                    {
                        "packet_id": task.id,
                        "paths": list(task.paths),
                        "check": {"command": task.check, "oracle": f"{task.id} passes."},
                    }
                    for task in graph.tasks
                    if task.id != "CONFLICT-04"
                ],
                "integrator": "coordinator-host-1",
                "permission_observed": True,
                "budget_limits": [{"resource": "workers", "value": len(graph.tasks), "unit": "workers", "rationale": "Fixture packet count."}],
                "cleanup_plan": "The Host fixture verifies every owned process and cleanup receipt.",
            },
        )
        self.assertEqual(transition["decision"]["mode"], "graph")
        (change / "process-decision.json").write_text(json.dumps(transition), encoding="utf-8")
        for relative in (
            "context/.gitkeep",
            "fixtures/.gitkeep",
            "markers/.gitkeep",
            "processes/.gitkeep",
        ):
            path = self.repository / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture input\n", encoding="utf-8")
        for command in (
            ["git", "init", "-q", str(self.repository)],
            ["git", "-C", str(self.repository), "config", "user.email", "test@example.com"],
            ["git", "-C", str(self.repository), "config", "user.name", "Test"],
            ["git", "-C", str(self.repository), "add", "."],
            ["git", "-C", str(self.repository), "commit", "-qm", "fixture"],
        ):
            subprocess.run(command, check=True)
        self.prebootstrap_frontend_path = self.repository / "frontend/prebootstrap.tsx"
        self.prebootstrap_frontend_path.write_text(
            "export const prebootstrap = 'modified-before-bootstrap';\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def cli(self, command: str, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(CLI), command, "--repo", str(self.repository), "--json", *arguments], capture_output=True, text=True)

    def result(self, completed: subprocess.CompletedProcess[str]) -> dict:
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)["result"]
        if "state" not in result:
            state_path = self.repository / "openspec/runs/host-run/host-run-1/state.json"
            if state_path.is_file():
                result["state"] = json.loads(state_path.read_text(encoding="utf-8"))
        return result

    def error(self, completed: subprocess.CompletedProcess[str]) -> str:
        self.assertNotEqual(completed.returncode, 0)
        return json.loads(completed.stderr)["error"]["code"]

    def args(self, generation: int = 2) -> tuple[str, ...]:
        return ("--change", "host-run", "--run-id", "host-run-1", "--generation", str(generation))

    def write_json(self, relative: str, body: object) -> str:
        path = self.repository / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body, sort_keys=True), encoding="utf-8")
        return relative

    def run_bytes(self) -> dict[str, bytes]:
        run = self.repository / "openspec/runs/host-run/host-run-1"
        return {
            "events": (run / "events.jsonl").read_bytes(),
            "state": (run / "state.json").read_bytes(),
        }

    def cleanup_owner(self, scope: dict, process_root: int) -> dict:
        workspace = scope["execution_workspace"]
        return {
            "execution_host_id": workspace["execution_host_id"],
            "workspace_key": workspace["workspace_key"],
            "coordinator_generation": 2,
            "terminal_id": None,
            "incarnation_id": None,
            "process_root": process_root,
            "provenance": "fixture process receipt",
        }

    def report_only(self, task: str, attempt: str, path: str) -> None:
        report = {
            "task_id": task,
            "attempt_id": attempt,
            "outcome": "reported",
            "summary": f"Bounded evidence for {task}.",
            "files_changed": [path],
            "checks_run": [self.fixture["child_check"]],
            "evidence_refs": ["file:openspec/changes/host-run/evidence.json"],
            "questions": [],
            "external_refs": {},
        }
        self.result(self.cli("record-result", *self.args(), "--attempt", attempt, "--result-json", json.dumps(report)))

    def assert_pids_gone(self, pids: list[int]) -> None:
        for pid in pids:
            for _ in range(30):
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    break
                except PermissionError:
                    self.fail(f"process {pid} remained unverifiable")
                time.sleep(0.02)
            else:
                self.fail(f"process {pid} remained alive")

    def report_grade(self, task: str, attempt: str, path: str, grade: str = "pass") -> None:
        report = {"task_id": task, "attempt_id": attempt, "outcome": "reported", "summary": f"Bounded evidence for {task}.", "files_changed": [path], "checks_run": [self.fixture["child_check"]], "evidence_refs": ["file:openspec/changes/host-run/evidence.json"], "questions": [], "external_refs": {}}
        recorded = self.result(self.cli("record-result", *self.args(), "--attempt", attempt, "--result-json", json.dumps(report)))
        replayed = self.result(self.cli("record-result", *self.args(), "--attempt", attempt, "--result-json", json.dumps(report)))
        self.assertFalse(recorded["idempotent"])
        self.assertTrue(replayed["idempotent"])
        check = self.cli("run-check", *self.args(), "--task", task)
        if grade == "fail":
            self.assertEqual(self.error(check), "check_failed")
        else:
            self.result(check)
        self.result(self.cli("grade", *self.args(), "--task", task, "--grade", grade, "--note", f"Recorded local check graded {grade}.", "--evidence-ref", "file:openspec/changes/host-run/evidence.json"))

    def compose_context(self, scope: dict) -> tuple[dict, dict]:
        directory = self.repository / "context"
        directory.mkdir(exist_ok=True)
        bodies = {"task.md": "Host root contract.", "note-r1.md": "First note revision.", "note-r2.md": "Second note revision."}
        for name, body in bodies.items():
            (directory / name).write_text(body, encoding="utf-8")
        digest = lambda text: f"sha256:{hashlib.sha256(text.encode()).hexdigest()}"
        task = {"id": "ROOT-01", "kind": "task", "origin": "fixture:task", "snapshot_path": "context/task.md", "content_hash": digest(bodies["task.md"]), "revision": "r1", "media_type": "text/markdown", "title": "Root"}
        capsules = []
        replay_edges = []
        replay_references = []
        for revision in ("r1", "r2"):
            note = {"id": f"note-{revision}", "kind": "user-note", "origin": "fixture:note", "snapshot_path": f"context/note-{revision}.md", "content_hash": digest(bodies[f"note-{revision}.md"]), "revision": revision, "media_type": "text/markdown", "title": "Host note"}
            edge = {"id": f"note-{revision}-for-root", "type": "context_for", "source_id": note["id"], "target_id": "ROOT-01"}
            if revision == "r1":
                replay_edges = [edge]
                replay_references = [task, note]
            capsule = context_capsules.compose_context_capsule(
                repository_root=self.repository,
                task_id="ROOT-01",
                attempt_id=f"attempt-root-01-00{len(capsules) + 1}",
                workspace_scope=scope,
                references=[task, note],
                edges=[edge],
                budget={"max_items": 4, "max_bytes": 1024, "max_tokens": 256},
            )
            context_capsules.write_context_capsule_once(self.repository, f"openspec/runs/host-run/host-run-1/capsules/root-{revision}.json", capsule)
            capsules.append(capsule)
        self.assertNotEqual(capsules[0]["capsule_id"], capsules[1]["capsule_id"])
        self.assertEqual(capsules[0]["items"][1]["revision"], "r1")
        self.assertEqual(capsules[1]["items"][1]["revision"], "r2")
        divergent = context_capsules.compose_context_capsule(
            repository_root=self.repository,
            task_id="ROOT-01",
            attempt_id="attempt-root-01-001",
            workspace_scope=scope,
            references=replay_references,
            edges=replay_edges,
            budget={"max_items": 4, "max_bytes": 1024, "max_tokens": 257},
        )
        existing_path = self.repository / "openspec/runs/host-run/host-run-1/capsules/root-r1.json"
        existing_bytes = existing_path.read_bytes()
        with self.assertRaises(context_capsules.CapsuleAlreadyExistsError):
            context_capsules.write_context_capsule_once(
                self.repository,
                "openspec/runs/host-run/host-run-1/capsules/root-r1.json",
                divergent,
            )
        self.assertEqual(existing_bytes, existing_path.read_bytes())
        return tuple(capsules)

    def test_executes_a_deterministic_no_orca_lifecycle(self) -> None:
        host = HostDriver(self.repository, self.repository / "openspec/runs/host-run/host-run-1")
        capabilities = host.detect().external_refs["capabilities"]
        visual_request = resolve_capability_request(
            capabilities,
            ["browser_surface"],
            operation="render-graph-canvas",
        )
        self.assertEqual(visual_request["outcome"], "blocked")
        self.assertEqual(visual_request["missing_capabilities"], ["browser_surface"])
        bootstrap = self.result(self.cli("bootstrap", "--change", "host-run", "--run-id", "host-run-1", "--bootstrap-id", "bootstrap-host-1", "--driver", "host"))
        claimed = self.result(self.cli("claim-coordinator", "--capsule", bootstrap["capsule_path"], "--coordinator-id", "coordinator-host-1"))
        scope = claimed["state"]["workspace_scope"]
        self.assertEqual(claimed["state"]["driver"], "host")
        self.assertTrue(scope["repository_id"].startswith("host-run-"))
        self.assertEqual(scope["dirty_paths"], ["frontend/prebootstrap.tsx"])
        route = routing.plan_route(self.fixture["capability_catalog"], role="coordinator")
        reordered_route = routing.plan_route(
            {"profiles": list(reversed(self.fixture["capability_catalog"]["profiles"]))},
            role="coordinator",
        )
        self.assertEqual(route.to_dict(), reordered_route.to_dict())
        self.assertEqual(route.requested, {"lane": "balanced", "agent": None, "model": None, "effort": "high"})
        self.assertEqual(route.resolved, {"agent": "host-agent", "model": "host-balanced", "effort": "high"})
        self.assertIsNone(route.fallback_reason)
        child_route = routing.plan_route(self.fixture["capability_catalog"], role="verification")
        reordered_child_route = routing.plan_route(
            {"profiles": list(reversed(self.fixture["capability_catalog"]["profiles"]))},
            role="verification",
        )
        self.assertEqual(child_route.to_dict(), reordered_child_route.to_dict())
        self.assertEqual(child_route.resolved, {"agent": "host-agent", "model": "host-fast", "effort": "low"})
        first_context, second_context = self.compose_context(scope)

        root = self.result(self.cli("dispatch", *self.args(), "--task", "ROOT-01", "--local"))
        self.assertEqual(root["state"]["attempts"][root["attempt_id"]]["execution_profile"]["resolved"]["model"], "host-native")
        run_directory = self.repository / "openspec/runs/host-run/host-run-1"
        malformed_result = b'{"task_id":"ROOT-01"'
        candidate = run_directory / "results" / f"{root['attempt_id']}.json"
        candidate.write_bytes(malformed_result)
        quarantined = self.result(self.cli(
            "quarantine-result", *self.args(), "--task", "ROOT-01", "--attempt", root["attempt_id"],
            "--candidate", f"openspec/runs/host-run/host-run-1/results/{root['attempt_id']}.json",
            "--idempotency-key", "quarantine-root-1",
        ))
        quarantine_receipt = quarantined["receipt"]
        self.assertFalse(candidate.exists())
        self.assertEqual(quarantine_receipt["sha256"], "sha256:" + hashlib.sha256(malformed_result).hexdigest())
        self.assertEqual(
            (run_directory / "artifacts/result-quarantine/sha256" / f"{quarantine_receipt['sha256'][7:]}.json").read_bytes(),
            malformed_result,
        )
        quarantine_pid_file = self.repository / "processes/quarantine-root-child.pid"
        quarantine_child_code = "import time; time.sleep(30)"
        quarantine_root_code = f"import pathlib, subprocess, sys, time; child = subprocess.Popen([sys.executable, '-c', {quarantine_child_code!r}]); pathlib.Path({str(quarantine_pid_file)!r}).write_text(str(child.pid)); time.sleep(30)"
        quarantine_root = subprocess.Popen(
            [sys.executable, "-c", quarantine_root_code], start_new_session=True
        )
        quarantine_child_pid = None
        quarantine_owner = {
            "execution_host_id": scope["execution_workspace"]["execution_host_id"],
            "workspace_key": scope["execution_workspace"]["workspace_key"],
            "attempt_id": root["attempt_id"],
            "terminal_id": None,
            "incarnation_id": None,
            "process_root": quarantine_root.pid,
            "provenance": "fixture quarantine process receipt",
        }
        quarantine_target = {"kind": "process", "root_pid": quarantine_root.pid}
        try:
            for _ in range(50):
                if quarantine_pid_file.is_file():
                    break
                time.sleep(0.02)
            self.assertTrue(quarantine_pid_file.is_file())
            quarantine_child_pid = int(quarantine_pid_file.read_text())
            self.result(self.cli(
                "cleanup-register", *self.args(),
                "--cleanup-id", "cleanup-quarantine-root-1",
                "--kind", "process",
                "--target", json.dumps(quarantine_target),
                "--owner", json.dumps(quarantine_owner),
            ))
            before_pending_abandon = self.run_bytes()
            self.assertEqual(
                self.error(self.cli(
                    "abandon-attempt", *self.args(), "--attempt", root["attempt_id"],
                    "--reason", "Malformed result was quarantined; cleanup is pending.",
                )),
                "cleanup_pending",
            )
            self.assertEqual(before_pending_abandon, self.run_bytes())
        finally:
            try:
                os.killpg(quarantine_root.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                quarantine_root.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(quarantine_root.pid, signal.SIGKILL)
                quarantine_root.wait(timeout=5)
            self.assert_pids_gone(
                [quarantine_root.pid]
                + ([quarantine_child_pid] if quarantine_child_pid is not None else [])
            )
        quarantine_receipt = {
            "kind": "process",
            "owner": quarantine_owner,
            "target": quarantine_target,
            "descendant_pids": [quarantine_child_pid],
            "status": "verified",
        }
        finished_quarantine_cleanup = self.result(self.cli(
            "cleanup-finish", *self.args(),
            "--cleanup-id", "cleanup-quarantine-root-1",
            "--receipt", json.dumps(quarantine_receipt),
        ))
        self.assertEqual(
            finished_quarantine_cleanup["state"]["cleanup"]["cleanup-quarantine-root-1"]["receipt"],
            quarantine_receipt,
        )
        self.result(self.cli(
            "abandon-attempt", *self.args(), "--attempt", root["attempt_id"],
            "--reason", "Malformed result was quarantined after verified cleanup.",
        ))
        root = self.result(self.cli("dispatch", *self.args(), "--task", "ROOT-01", "--local"))
        progress = self.result(self.cli("status", "--change", "host-run", "--run-id", "host-run-1"))["progress"]
        self.assertEqual(progress["state"], "active")
        self.assertEqual(progress["task_counts"]["running"], 1)
        intent = {"schema_version": 1, "protocol": "delegation-intent/v1", "intent_id": "delegate-child-1", "workspace": {"repository_id": scope["repository_id"], "execution_host_id": scope["orchestration_home"]["execution_host_id"], "workspace_key": scope["orchestration_home"]["workspace_key"], "run_id": "host-run-1"}, "actor": {"actor_id": "worker-root-1", "kind": "worker", "authenticated": True, "session_id": "session-root-1"}, "coordinator_generation": 2, "expected_revision": root["state"]["last_sequence"], "parent_task_id": "ROOT-01", "parent_attempt_id": root["attempt_id"], "purpose": "Verify the bounded child path.", "role": "verification", "requested": {"lane": "fast", "agent": None, "model": None, "effort": "low"}, "placement_request": {"kind": "current-workspace"}, "context_refs": [first_context["capsule_id"]], "paths": ["src/root.py"], "check": self.fixture["child_check"]}
        intent_path = self.write_json("fixtures/delegation-intent.json", intent)
        requested = self.result(self.cli("request-delegation", *self.args(), "--intent", intent_path))
        self.assertFalse(requested["idempotent"])
        self.assertTrue(self.result(self.cli("request-delegation", *self.args(), "--intent", intent_path))["idempotent"])
        profile = {**child_route.execution_profile(), "placement_request": {"kind": "current-workspace"}, "resolved_placement": {"execution_host_id": scope["execution_workspace"]["execution_host_id"], "workspace_key": scope["execution_workspace"]["workspace_key"], "kind": "folder", "path": str(self.repository), "receipt_ref": scope["binding_receipt_ref"]}}
        profile_path = self.write_json("fixtures/delegation-profile.json", profile)
        self.result(self.cli("approve-delegation", *self.args(), "--delegation", "delegate-child-1", "--execution-profile", profile_path, "--context-revision", second_context["capsule_id"], "--path", "src/root.py", "--context-ref", first_context["capsule_id"]))
        pid_file = self.repository / "processes/owned-child.pid"
        child_code = "import time; time.sleep(30)"
        root_code = f"import pathlib, subprocess, sys, time; child = subprocess.Popen([sys.executable, '-c', {child_code!r}]); pathlib.Path({str(pid_file)!r}).write_text(str(child.pid)); time.sleep(30)"
        owned_root = None
        child_pid = None
        owner = None
        try:
            owned_root = subprocess.Popen([sys.executable, "-c", root_code], start_new_session=True)
            for _ in range(50):
                if pid_file.is_file():
                    break
                time.sleep(0.02)
            self.assertTrue(pid_file.is_file())
            child_pid = int(pid_file.read_text())
            owner = self.cleanup_owner(scope, owned_root.pid)
            owner["attempt_id"] = "child-attempt-1"
            owner.pop("coordinator_generation")
            start = self.write_json("openspec/runs/host-run/host-run-1/artifacts/child-start.json", {"child": "child-attempt-1"})
            self.result(self.cli("start-delegation", *self.args(), "--delegation", "delegate-child-1", "--child-attempt", "child-attempt-1", "--resource-owner", json.dumps(owner), "--receipt-id", "child-start-1", "--receipt-path", start))
            nested = {**intent, "intent_id": "delegate-grandchild-1", "parent_attempt_id": "child-attempt-1", "expected_revision": self.result(self.cli("status", "--change", "host-run", "--run-id", "host-run-1"))["last_sequence"]}
            nested_path = self.write_json("fixtures/nested-intent.json", nested)
            before_nested = self.run_bytes()
            self.assertEqual(self.error(self.cli("request-delegation", *self.args(), "--intent", nested_path)), "invalid_graph")
            self.assertEqual(before_nested, self.run_bytes())
            process_target = {"kind": "process", "root_pid": owned_root.pid}
            self.result(self.cli(
                "register-delegation-cleanup", *self.args(),
                "--delegation", "delegate-child-1", "--cleanup-id", "cleanup-child-1",
                "--kind", "process", "--target", json.dumps(process_target),
            ))
            registered = self.result(self.cli("status", "--change", "host-run", "--run-id", "host-run-1"))
            registered_cleanup = registered["state"]["cleanup"]["cleanup-child-1"]
            self.assertEqual(registered_cleanup["kind"], "process")
            self.assertEqual(registered_cleanup["target"], process_target)
            self.assertIsNone(registered_cleanup["owner"]["terminal_id"])
            self.assertIsNone(registered_cleanup["owner"]["incarnation_id"])
            process_owner = registered_cleanup["owner"]
            child = {"delegation_id": "delegate-child-1", "task_id": "ROOT-01", "attempt_id": "child-attempt-1", "outcome": "reported", "summary": "Child evidence is bounded.", "files_changed": [], "checks_run": [self.fixture["child_check"]], "evidence_refs": ["file:src/root.py"], "questions": [], "external_refs": {}}
            child_result = self.write_json("fixtures/child-result.json", child)
            reported = self.write_json("openspec/runs/host-run/host-run-1/artifacts/child-report.json", {"child": "child-attempt-1"})
            self.result(self.cli("report-delegation", *self.args(), "--delegation", "delegate-child-1", "--result", child_result, "--receipt-id", "child-report-1", "--receipt-path", reported))
            release_receipt = self.write_json("openspec/runs/host-run/host-run-1/artifacts/child-release-rejected.json", {"child": "child-attempt-1"})
            before_rejected_release = self.run_bytes()
            first_rejection = self.error(self.cli("release-delegation", *self.args(), "--delegation", "delegate-child-1", "--cleanup-id", "cleanup-child-1", "--receipt-id", "child-release-rejected-1", "--receipt-path", release_receipt))
            after_first_rejection = self.run_bytes()
            second_rejection = self.error(self.cli("release-delegation", *self.args(), "--delegation", "delegate-child-1", "--cleanup-id", "cleanup-child-1", "--receipt-id", "child-release-rejected-1", "--receipt-path", release_receipt))
            self.assertEqual(first_rejection, second_rejection)
            self.assertEqual(before_rejected_release, after_first_rejection)
            self.assertEqual(after_first_rejection, self.run_bytes())
        finally:
            if owned_root is not None:
                try:
                    os.killpg(owned_root.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            if owned_root is not None:
                try:
                    owned_root.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(owned_root.pid, signal.SIGKILL)
                    owned_root.wait(timeout=5)
            if owned_root is not None:
                self.assert_pids_gone([owned_root.pid] + ([child_pid] if child_pid is not None else []))
        descendant_pids = [child_pid]
        process_finished = self.result(self.cli(
            "cleanup-finish", *self.args(), "--cleanup-id", "cleanup-child-1",
            "--receipt", json.dumps({"kind": "process", "owner": process_owner, "target": process_target, "descendant_pids": descendant_pids, "status": "verified"}),
        ))
        self.assertEqual(process_finished["state"]["cleanup"]["cleanup-child-1"]["status"], "verified")
        self.assertEqual(process_finished["state"]["cleanup"]["cleanup-child-1"]["target"], process_target)
        self.assertEqual(process_finished["state"]["cleanup"]["cleanup-child-1"]["receipt"]["descendant_pids"], descendant_pids)
        self.assert_pids_gone([owned_root.pid, child_pid])
        released = self.result(self.cli("release-delegation", *self.args(), "--delegation", "delegate-child-1", "--cleanup-id", "cleanup-child-1", "--receipt-id", "child-release-1", "--receipt-path", self.write_json("openspec/runs/host-run/host-run-1/artifacts/child-release.json", {"child": "child-attempt-1"})))
        delegation = released["state"]["delegations"]["delegate-child-1"]
        self.assertEqual(delegation["cleanup_id"], "cleanup-child-1")
        self.assertEqual((delegation["status"], delegation["spawned_by"]), ("released", root["attempt_id"]))
        self.assertEqual(set(delegation["lifecycle_receipts"]), {"started", "reported", "released"})

        self.report_grade("ROOT-01", root["attempt_id"], "src/root.py")
        ready = self.result(self.cli("ready", "--change", "host-run", "--run-id", "host-run-1"))
        self.assertEqual([task["id"] for task in ready["ready"]], ["WAVE-02"])
        wave = self.result(self.cli("dispatch", *self.args(), "--task", "WAVE-02", "--local"))
        before_conflict = self.run_bytes()
        self.assertEqual(self.error(self.cli("dispatch", *self.args(), "--task", "CONFLICT-04", "--local")), "task_not_ready")
        self.assertEqual(self.error(self.cli("dispatch", *self.args(), "--task", "WAVE-03", "--local")), "task_not_ready")
        self.assertEqual(before_conflict, self.run_bytes())
        self.report_grade("WAVE-02", wave["attempt_id"], "src/a/one.py")
        ready = self.result(self.cli("ready", "--change", "host-run", "--run-id", "host-run-1"))
        self.assertEqual([task["id"] for task in ready["ready"]], ["WAVE-03"])
        second_wave = self.result(self.cli("dispatch", *self.args(), "--task", "WAVE-03", "--local"))
        self.report_grade("WAVE-03", second_wave["attempt_id"], "src/b/two.py")
        conflict = self.result(self.cli("dispatch", *self.args(), "--task", "CONFLICT-04", "--local"))
        self.report_grade("CONFLICT-04", conflict["attempt_id"], "src/a/nested.py")
        failed = self.result(self.cli("dispatch", *self.args(), "--task", "FAIL-05", "--local"))
        self.report_only("FAIL-05", failed["attempt_id"], "src/fail.py")
        first_check = self.cli("run-check", *self.args(), "--task", "FAIL-05")
        self.assertEqual(self.error(first_check), "check_failed")
        first_state = self.result(self.cli("status", "--change", "host-run", "--run-id", "host-run-1"))
        first_artifact = first_state["state"]["attempts"][failed["attempt_id"]]["check"]["artifact"]
        self.assertEqual(first_state["state"]["attempts"][failed["attempt_id"]]["check"]["status"], "failed")
        saved_scope = first_state["state"]["workspace_scope"]
        failed_artifact_bytes = (self.repository / first_artifact).read_bytes()
        resumed = self.result(self.cli("resume", *self.args()))
        self.assertEqual((resumed["state"]["workspace_scope"], resumed["running_attempts"]), (saved_scope, []))
        self.assertEqual(failed_artifact_bytes, (self.repository / first_artifact).read_bytes())
        marker = self.repository / "markers/fail-05"
        marker.parent.mkdir(exist_ok=True)
        marker.write_text("ready", encoding="utf-8")
        self.result(self.cli("run-check", *self.args(), "--task", "FAIL-05"))
        passed_state = self.result(self.cli("status", "--change", "host-run", "--run-id", "host-run-1"))
        passed_check = passed_state["state"]["attempts"][failed["attempt_id"]]["check"]
        self.assertEqual((passed_check["status"], passed_check["attempts"]), ("passed", 2))
        self.assertNotEqual(first_artifact, passed_check["artifact"])
        self.result(self.cli("grade", *self.args(), "--task", "FAIL-05", "--grade", "pass", "--note", "Marker-gated check passed after retained failure evidence.", "--evidence-ref", "file:openspec/changes/host-run/evidence.json"))

        pre_watch = self.result(self.cli("status", "--change", "host-run", "--run-id", "host-run-1"))
        current_revision = pre_watch["state"]["last_sequence"]
        cursor = resumed["state"]["last_sequence"] - 1
        watched = self.cli("status", "--change", "host-run", "--run-id", "host-run-1", "--watch", "--cursor", str(cursor), "--iterations", "1")
        self.assertEqual(watched.returncode, 0, watched.stderr)
        watch_updates = [json.loads(line) for line in watched.stdout.splitlines() if line.strip()]
        self.assertEqual([set(item) for item in watch_updates], [{"kind", "cursor", "event", "changes", "progress"}])
        self.assertEqual([item["cursor"] for item in watch_updates], [current_revision])
        self.assertEqual(watch_updates[-1]["cursor"], current_revision)
        self.assertEqual(watch_updates[-1]["progress"]["state"], "active")
        for item in watch_updates:
            for field in ("stdout", "stderr", "transcript", "body", "payload"):
                self.assertNotIn(field, json.dumps(item).casefold())
        takeover = self.result(self.cli("takeover", *self.args(), "--coordinator-id", "coordinator-host-2"))
        self.assertEqual(takeover["coordinator_generation"], 3)
        before_stale_dispatch = self.run_bytes()
        self.assertEqual(self.error(self.cli("dispatch", *self.args(), "--task", "FAIL-05", "--local")), "stale_coordinator")
        self.assertEqual(before_stale_dispatch, self.run_bytes())
        takeover_revision = takeover["state"]["last_sequence"]
        stale_worker = {**intent, "intent_id": "delegate-stale-worker-1", "coordinator_generation": 2, "expected_revision": takeover_revision}
        stale_worker_path = self.write_json("fixtures/stale-worker-intent.json", stale_worker)
        before_stale_worker = self.run_bytes()
        worker_rejection = self.error(self.cli("request-delegation", *self.args(3), "--intent", stale_worker_path))
        self.assertEqual(before_stale_worker, self.run_bytes())
        stale_canvas = {**intent, "intent_id": "canvas-stale-intent-1", "coordinator_generation": 2, "expected_revision": takeover_revision, "actor": {"actor_id": "canvas-user-1", "kind": "user", "authenticated": True, "session_id": "canvas-session-1"}}
        stale_canvas_path = self.write_json("fixtures/stale-canvas-intent.json", stale_canvas)
        before_stale_canvas = self.run_bytes()
        canvas_rejection = self.error(self.cli("request-delegation", *self.args(3), "--intent", stale_canvas_path))
        self.assertEqual(canvas_rejection, worker_rejection)
        self.assertEqual(before_stale_canvas, self.run_bytes())
        for path in self.repository.joinpath("context").glob("*.md"):
            path.unlink()
        for path in self.repository.joinpath("fixtures").glob("*.json"):
            path.unlink()
        for path in (
            self.repository / "markers/fail-05",
            self.repository / "processes/owned-child.pid",
            self.repository / "processes/quarantine-root-child.pid",
        ):
            if path.exists():
                path.unlink()
        unowned_frontend_path = self.repository / "frontend/unowned.tsx"
        unowned_frontend_path.parent.mkdir(exist_ok=True)
        unowned_frontend_path.write_text("export const unowned = true;\n", encoding="utf-8")
        before_unowned_completion = self.run_bytes()
        self.assertEqual(self.error(self.cli("complete", *self.args(3), "--outcome", "pass")), "changed_path_unproven")
        self.assertEqual(before_unowned_completion, self.run_bytes())
        unowned_frontend_path.unlink()
        completed = self.result(self.cli("complete", *self.args(3), "--outcome", "pass"))["state"]
        self.assertEqual(completed["status"], "complete")
        self.assertTrue(all(item["grade"] == "pass" for item in completed["tasks"].values()))
        self.assertTrue(all(item["status"] in {"done", "verified", "retained"} for item in completed["cleanup"].values()))
        self.assertEqual(completed["cleanup"]["cleanup-child-1"]["status"], "verified")
        self.assertNotIn("orca", json.dumps(completed).casefold())
        golden = {
            "route": {"requested": route.requested, "resolved": route.resolved, "fallback": route.fallback_reason},
            "context": {"revisions": [first_context["items"][1]["revision"], second_context["items"][1]["revision"]], "replay_rejected": True},
            "watch": {"from_cursor": cursor, "final_cursor": watch_updates[-1]["cursor"], "current_revision": current_revision, "update_count": len(watch_updates), "fields": ["kind", "cursor", "event", "changes", "progress"], "transcript_free": all(field not in json.dumps(item).casefold() for item in watch_updates for field in ("stdout", "stderr", "transcript", "body", "payload"))},
            "delegation": {"lifecycle": ["started", "reported", "released"], "spawned_by": delegation["spawned_by"], "recursive_fence": "invalid_graph"},
            "child_route": {"requested": child_route.requested, "resolved": child_route.resolved, "fallback": child_route.fallback_reason},
            "checks": {"failed_then_passed": ["failed", "passed"], "same_command": first_state["state"]["attempts"][failed["attempt_id"]]["check"]["command"] == passed_check["command"], "failed_evidence_retained": Path(self.repository / first_artifact).is_file()},
            "quarantine": {"content_addressed": True, "cleanup_gate": "cleanup_pending", "pending_rejection_immutable": True, "receipt_status": "verified", "fresh_retry": True},
            "takeover": {"generation": takeover["coordinator_generation"], "stale_calls_rejected": ["coordinator", "worker", "canvas"], "stale_intent_rejection": worker_rejection},
            "cleanup": {"statuses": sorted({item["status"] for item in completed["cleanup"].values()}), "pending": sum(item["status"] == "pending" for item in completed["cleanup"].values()), "unverifiable": sum(item["status"] == "unverifiable" for item in completed["cleanup"].values()), "descendant_pids_gone": True, "exact_descendant_receipt": True, "registered_via_public_api": True, "released_by_verified_process_cleanup": True, "terminal_observation": "unobserved"},
        }
        evidence = json.loads((ROOT.parent.parent / "openspec/changes/maestro-harness-orchestration/evidence/host-run.json").read_text(encoding="utf-8"))
        expected = json.loads(json.dumps(evidence["golden_summary"]))
        for counter in ("from_cursor", "final_cursor", "current_revision"):
            golden["watch"][counter] = "<variable>"
            expected["watch"][counter] = "<variable>"
        self.assertEqual(golden, expected)


if __name__ == "__main__":
    unittest.main()
