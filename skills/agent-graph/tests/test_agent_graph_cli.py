import argparse
import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "agent_graph.py"
sys.path.insert(0, str(SCRIPT.parent))
import agent_graph as runtime  # noqa: E402
from adaptive_intake import amend_process_decision  # noqa: E402


QUARANTINE_TESTS = Path(__file__).with_name("test_result_quarantine.py")
QUARANTINE_TEST_SPEC = importlib.util.spec_from_file_location(
    "result_quarantine_behavior", QUARANTINE_TESTS
)
assert QUARANTINE_TEST_SPEC and QUARANTINE_TEST_SPEC.loader
result_quarantine_behavior = importlib.util.module_from_spec(QUARANTINE_TEST_SPEC)
sys.modules[QUARANTINE_TEST_SPEC.name] = result_quarantine_behavior
QUARANTINE_TEST_SPEC.loader.exec_module(result_quarantine_behavior)


TASKS = f"""# Tasks

- [ ] ROOT-01 Build the root
  Depends: []
  Paths: [src/root.py]
  Mode: write
  Isolation: auto
  Acceptance: The root is reported and verified.
  Check: \"{sys.executable}\" -c \"raise SystemExit(0)\"

- [ ] NEXT-02 Build the dependent task
  Depends: [ROOT-01]
  Paths: [src/next.py]
  Mode: write
  Isolation: auto
  Acceptance: The dependent task is reported and verified.
  Check: \"{sys.executable}\" -c \"raise SystemExit(0)\"
"""


class AgentGraphCliBehavior(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repository = Path(self.temporary_directory.name)
        change = self.repository / "openspec" / "changes" / "portable"
        change.mkdir(parents=True)
        (change / "proposal.md").write_text("# Proposal\n", encoding="utf-8")
        (change / "design.md").write_text("# Design\n", encoding="utf-8")
        (change / "tasks.md").write_text(TASKS, encoding="utf-8")
        policy = SCRIPT.parents[2] / "impl" / "references" / "routing-policy.seed.json"
        policy_target = self.repository / "skills" / "impl" / "references" / "routing-policy.seed.json"
        policy_target.parent.mkdir(parents=True)
        policy_target.write_bytes(policy.read_bytes())
        self.write_process_decision()
        subprocess.run(["git", "init", "-q", str(self.repository)], check=True)
        subprocess.run(["git", "-C", str(self.repository), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(self.repository), "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "-C", str(self.repository), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.repository), "commit", "-qm", "test fixture"], check=True)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_process_decision(self, *, allow_unsafe_checks: bool = False) -> None:
        change = self.repository / "openspec/changes/portable"
        graph = runtime.parse_task_graph(change / "tasks.md")
        safe_command = f'"{sys.executable}" -c "raise SystemExit(0)"'
        transition = runtime.decide_process(
            self.repository,
            request="Execute the portable graph fixture.",
            check_command=safe_command if allow_unsafe_checks else graph.tasks[0].check,
            signals={
                "known_scope": True,
                "graph_requested": True,
                "cohesion": "independent",
                "independent_packets": [
                    {
                        "packet_id": task.id,
                        "paths": list(task.paths),
                        "check": {
                            "command": safe_command if allow_unsafe_checks else task.check,
                            "oracle": f"{task.id} check passes.",
                        },
                    }
                    for task in graph.tasks
                ],
                "integrator": "coordinator-1",
                "permission_observed": True,
                "budget_limits": [
                    {
                        "resource": "workers",
                        "value": len(graph.tasks),
                        "unit": "workers",
                        "rationale": "The fixture budget follows its declared packet count.",
                    }
                ],
                "cleanup_plan": "The fixture verifies every owned resource.",
            },
        )
        self.assertEqual(transition["decision"]["mode"], "graph")
        if allow_unsafe_checks:
            transition["decision"]["selected_check"]["command"] = graph.tasks[0].check
            for decision_packet, contract_packet, task in zip(
                transition["decision"]["observations"]["independent_packets"],
                transition["graph_contract"]["packets"],
                graph.tasks,
            ):
                decision_packet["check"]["command"] = task.check
                contract_packet["check"]["command"] = task.check
        (change / "process-decision.json").write_text(
            json.dumps(transition), encoding="utf-8"
        )

    def run_cli(self, command: str, *arguments: str):
        return subprocess.run(
            [sys.executable, str(SCRIPT), command, "--repo", str(self.repository), "--json", *arguments],
            check=False,
            capture_output=True,
            text=True,
        )

    def result(self, completed):
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)["result"]
        run_id = result.get("run_id", "run-1")
        state_path = self.repository / f"openspec/runs/portable/{run_id}/state.json"
        if not state_path.is_file():
            candidates = sorted((self.repository / "openspec/runs/portable").glob("*/state.json"))
            if len(candidates) == 1:
                state_path = candidates[0]
        if state_path.is_file() and "state" not in result:
            result["state"] = json.loads(state_path.read_text(encoding="utf-8"))
        return result

    def bootstrap_and_claim(self):
        bootstrap = self.result(
            self.run_cli(
                "bootstrap",
                "--change", "portable",
                "--run-id", "run-1",
                "--bootstrap-id", "bootstrap-1",
                "--driver", "host",
            )
        )
        claimed = self.result(
            self.run_cli(
                "claim-coordinator",
                "--capsule", bootstrap["capsule_path"],
                "--coordinator-id", "coordinator-1",
            )
        )
        return bootstrap, claimed

    def active_delegation_parent(self) -> tuple[dict, int]:
        bootstrap, _ = self.bootstrap_and_claim()
        dispatched = self.result(self.run_cli(
            "dispatch", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--task", "ROOT-01", "--local",
        ))
        return bootstrap["state"]["workspace_scope"], dispatched["state"]["last_sequence"]

    def delegation_intent(self, scope: dict, revision: int, *, intent_id: str = "intent-child", paths: list[str] | None = None) -> dict:
        workspace = scope["orchestration_home"]
        return {
            "schema_version": 1,
            "protocol": "delegation-intent/v1",
            "intent_id": intent_id,
            "workspace": {
                "repository_id": scope["repository_id"],
                "execution_host_id": workspace["execution_host_id"],
                "workspace_key": workspace["workspace_key"],
                "run_id": "run-1",
            },
            "actor": {"actor_id": "canvas-1", "kind": "user", "authenticated": True, "session_id": "session-1"},
            "coordinator_generation": 2,
            "expected_revision": revision,
            "parent_task_id": "ROOT-01",
            "parent_attempt_id": "attempt-root-01-001",
            "purpose": "Verify the child path.",
            "role": "verification",
            "requested": {"lane": "fast", "agent": None, "model": None, "effort": "low"},
            "placement_request": {"kind": "current-workspace"},
            "context_refs": ["context-root"],
            "paths": paths or ["src/root.py"],
            "check": f'"{sys.executable}" -c "raise SystemExit(0)"',
        }

    def delegation_profile(self, scope: dict) -> dict:
        workspace = scope["execution_workspace"]
        return {
            "role": "verification",
            "requested": {"lane": "fast", "agent": None, "model": None, "effort": "low"},
            "resolved": {"agent": "agent-local", "model": "model-local", "effort": "low"},
            "fallback_reason": None,
            "placement_request": {"kind": "current-workspace"},
            "resolved_placement": {
                "execution_host_id": workspace["execution_host_id"],
                "workspace_key": workspace["workspace_key"],
                "kind": workspace["kind"],
                "path": workspace["path"],
                "receipt_ref": "artifact:openspec/runs/portable/run-1/artifacts/profile-receipt.json",
            },
        }

    def write_delegation_artifact(self, name: str, payload: object) -> str:
        relative = f"openspec/runs/portable/run-1/artifacts/{name}"
        path = self.repository / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return relative

    def explicit_workspace_receipt(self, run_id: str) -> dict:
        root = str(self.repository.resolve())
        return {
            "schema_version": 1,
            "repository_id": "repository-orca-01",
            "canonical_root": root,
            "execution_host": {"id": "ssh:build-host-01", "boundary": "remote"},
            "orchestration_home": {
                "execution_host_id": "runtime:orca-local-01",
                "workspace_key": "folder:orca-home-01",
                "kind": "folder",
                "path": root,
            },
            "execution_workspace": {
                "execution_host_id": "ssh:build-host-01",
                "workspace_key": "worktree:repository-orca-01::/srv/worktrees/portable",
                "kind": "git-worktree",
                "path": "/srv/worktrees/portable",
                "worktree_path": "/srv/worktrees/portable",
            },
            "base_revision": "remote-revision-01",
            "dirty_paths": ["remote/source.py"],
            "authority": {
                "kind": "orca",
                "scope": "run",
                "issued_for_run_id": run_id,
            },
        }

    def explicit_host_workspace_receipt(self, run_id: str) -> dict:
        root = str(self.repository.resolve())
        repository_id = "host-run-11111111-1111-4111-8111-111111111111"
        workspace = {
            "execution_host_id": "runtime:opaque-local",
            "workspace_key": f"folder:{repository_id}",
            "kind": "folder",
            "path": root,
        }
        return {
            "schema_version": 1,
            "repository_id": repository_id,
            "canonical_root": root,
            "execution_host": {"id": "runtime:opaque-local", "boundary": "local"},
            "orchestration_home": copy.deepcopy(workspace),
            "execution_workspace": copy.deepcopy(workspace),
            "base_revision": subprocess.run(
                ["git", "-C", str(self.repository), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip(),
            "dirty_paths": [],
            "authority": {
                "kind": "host-run",
                "scope": "run",
                "issued_for_run_id": run_id,
            },
        }

    def run_directory_snapshot(self, run_id: str) -> dict[str, bytes]:
        directory = self.repository / f"openspec/runs/portable/{run_id}"
        return {
            path.relative_to(directory).as_posix(): path.read_bytes()
            for path in sorted(directory.rglob("*"))
            if path.is_file()
        }

    def test_bootstraps_a_transcript_free_capsule_and_claims_once(self) -> None:
        bootstrap, claimed = self.bootstrap_and_claim()

        capsule = json.loads((self.repository / bootstrap["capsule_path"]).read_text())
        self.assertEqual(capsule["coordinator_generation"], 2)
        self.assertNotIn("transcript", json.dumps(capsule).casefold())
        self.assertFalse(bootstrap["continue_in_bootstrap"])
        self.assertIsNone(bootstrap["state"]["driver"])
        self.assertEqual(claimed["state"]["coordinator"], {"id": "coordinator-1", "generation": 2})
        self.assertEqual(claimed["state"]["driver"], "host")
        repeated = self.result(
            self.run_cli(
                "claim-coordinator",
                "--capsule", bootstrap["capsule_path"],
                "--coordinator-id", "coordinator-1",
            )
        )
        self.assertTrue(repeated["idempotent"])

    def test_ignores_a_probe_result_for_another_attempt(self) -> None:
        result_path = self.repository / "probe-result.json"
        result_path.write_text(
            json.dumps({"probe_attempt_id": "scratch-attempt", "projection": {"outcome": "pass"}}),
            encoding="utf-8",
        )

        self.assertIsNone(runtime._matching_probe_result(result_path, "expected-attempt"))

        result_path.write_text(
            json.dumps({"probe_attempt_id": "expected-attempt", "projection": {"outcome": "pass"}}),
            encoding="utf-8",
        )
        matched = runtime._matching_probe_result(result_path, "expected-attempt")
        self.assertEqual(matched["projection"]["outcome"], "pass")

    def test_blocks_the_stop_hook_from_agent_graph_progress_without_plans_md(self) -> None:
        self.bootstrap_and_claim()

        completed = self.run_cli(
            "stop-hook", "--change", "portable", "--run-id", "run-1",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        stopped = json.loads(completed.stdout)

        self.assertEqual(stopped["decision"], "block")
        self.assertIn("pending", stopped["reason"])
        self.assertFalse((self.repository / "Plans.md").exists())

    def test_allows_an_amended_read_attempt_to_report_authorized_repairs(self) -> None:
        tasks = self.repository / "openspec/changes/portable/tasks.md"
        tasks.write_text(TASKS.replace("Mode: write", "Mode: read", 1), encoding="utf-8")
        self.write_process_decision()
        self.bootstrap_and_claim()
        reserved = self.result(self.run_cli(
            "dispatch", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--task", "ROOT-01", "--local", "--defer-launch",
        ))
        attempt_id = reserved["attempt_id"]
        self.result(self.run_cli(
            "amend-graph", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--amendment-id", "repair-read-gate",
            "--parent-task", "ROOT-01", "--parent-attempt", attempt_id,
            "--path", "src/repair.py", "--reason", "Authorize the bounded gate repair.",
        ))
        self.result(self.run_cli(
            "recover-attempt", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--attempt", attempt_id,
        ))
        report = {
            "task_id": "ROOT-01",
            "attempt_id": attempt_id,
            "outcome": "reported",
            "summary": "Applied the authorized gate repair.",
            "files_changed": ["src/repair.py"],
            "checks_run": ["python3 -m unittest tests.test_repair"],
            "evidence_refs": [],
            "questions": [],
            "external_refs": {},
        }

        recorded = self.result(self.run_cli(
            "record-result", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--attempt", attempt_id,
            "--result-json", json.dumps(report),
        ))

        self.assertTrue(recorded["reported"])
        self.assertEqual(recorded["state"]["attempts"][attempt_id]["report"]["files_changed"], ["src/repair.py"])

    def test_keeps_a_running_read_attempt_scope_and_mode_frozen(self) -> None:
        tasks = self.repository / "openspec/changes/portable/tasks.md"
        tasks.write_text(TASKS.replace("Mode: write", "Mode: read", 1), encoding="utf-8")
        self.write_process_decision()
        self.bootstrap_and_claim()
        launched = self.result(self.run_cli(
            "dispatch", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--task", "ROOT-01", "--local",
        ))
        attempt_id = launched["attempt_id"]
        before_scope = copy.deepcopy(launched["state"]["attempts"][attempt_id]["effective_scope"])

        rejected = self.run_cli(
            "amend-graph", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--amendment-id", "late-running-repair",
            "--parent-task", "ROOT-01", "--parent-attempt", attempt_id,
            "--path", "src/late.py", "--reason", "This authorization arrived after launch.",
        )

        self.assertNotEqual(rejected.returncode, 0)
        self.assertEqual(json.loads(rejected.stderr)["error"]["code"], "invalid_graph")
        state = json.loads(
            (self.repository / "openspec/runs/portable/run-1/state.json").read_text(encoding="utf-8")
        )
        after_scope = state["attempts"][attempt_id]["effective_scope"]
        self.assertEqual(after_scope, before_scope)
        self.assertEqual(after_scope["paths"], ["src/root.py"])
        self.assertEqual(after_scope["amendment_ids"], [])
        changed_report = {
            "task_id": "ROOT-01",
            "attempt_id": attempt_id,
            "outcome": "reported",
            "summary": "Tried to write after the rejected late amendment.",
            "files_changed": ["src/root.py"],
            "checks_run": ["python3 -m unittest tests.test_root"],
            "evidence_refs": [],
            "questions": [],
            "external_refs": {},
        }
        rejected_report = self.run_cli(
            "record-result", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--attempt", attempt_id,
            "--result-json", json.dumps(changed_report),
        )
        self.assertNotEqual(rejected_report.returncode, 0)
        self.assertIn("read tasks cannot report changed files", rejected_report.stderr)

    def test_reuses_host_session_with_an_imported_dependency_without_attempts(self) -> None:
        graph = runtime.parse_task_graph("""# Tasks

- [x] IMPORT-01 Imported
  Depends: []
  Paths: [src/imported.py]
  Mode: write
  Isolation: auto
  Acceptance: Imported evidence is accepted.
  Check: python3 -c pass

- [x] LOCAL-02 Local
  Depends: []
  Paths: [src/local.py]
  Mode: write
  Isolation: auto
  Acceptance: Local evidence is accepted.
  Check: python3 -c pass

- [ ] NEXT-03 Reused
  Depends: [IMPORT-01, LOCAL-02]
  Paths: [src/next.py]
  Mode: write
  Isolation: auto
  Acceptance: Reuse the compatible local worker.
  Check: python3 -c pass
""")
        profile = {"resolved": "profile"}
        workspace = {"workspace": "current"}
        projection = {
            "tasks": {
                "IMPORT-01": {"grade": "pass", "attempt_ids": [], "import_receipt": {"note": "Imported check passed."}},
                "LOCAL-02": {"grade": "pass", "attempt_ids": ["attempt-local"]},
            },
            "attempts": {
                "attempt-local": {
                    "status": "reported", "workspace_scope": workspace,
                    "execution_profile": profile,
                    "external_refs": {"tier": "host-native", "worker_handle": "worker-1"},
                    "report": {"summary": "Local check passed.", "files_changed": ["src/local.py"]},
                }
            },
        }
        handoff = runtime._reused_host_session_handoff(
            graph=graph, projection=projection, task=graph.tasks[2], worker_handle="worker-1",
            workspace_scope=workspace, execution_profile=profile,
        )
        self.assertIsNotNone(handoff)
        self.assertIn("Imported check passed.", str(handoff))

    def test_reuses_the_compatible_host_dependency_before_an_incompatible_predecessor(self) -> None:
        graph = runtime.parse_task_graph("""# Tasks

- [x] FIRST-01 Compatible predecessor
  Depends: []
  Paths: [src/first.py]
  Mode: write
  Isolation: auto
  Acceptance: First compatible evidence is accepted.
  Check: python3 -c pass

- [x] SECOND-02 Later predecessor
  Depends: []
  Paths: [src/second.py]
  Mode: write
  Isolation: auto
  Acceptance: Later evidence is accepted.
  Check: python3 -c pass

- [ ] NEXT-03 Reused
  Depends: [FIRST-01, SECOND-02]
  Paths: [src/next.py]
  Mode: write
  Isolation: auto
  Acceptance: Reuse the compatible local worker.
  Check: python3 -c pass
""")
        profile = {"resolved": "profile"}
        workspace = {"workspace": "current"}
        projection = {
            "tasks": {
                "FIRST-01": {"grade": "pass", "attempt_ids": ["attempt-first"]},
                "SECOND-02": {"grade": "pass", "attempt_ids": ["attempt-second"]},
            },
            "attempts": {
                "attempt-first": {
                    "status": "reported", "workspace_scope": workspace,
                    "execution_profile": profile,
                    "external_refs": {"tier": "host-native", "worker_handle": "worker-target"},
                    "report": {"summary": "First check passed.", "files_changed": ["src/first.py"]},
                },
                "attempt-second": {
                    "status": "reported", "workspace_scope": workspace,
                    "execution_profile": profile,
                    "external_refs": {"tier": "host-native", "worker_handle": "worker-other"},
                    "report": {"summary": "Second check passed.", "files_changed": ["src/second.py"]},
                },
            },
        }

        handoff = runtime._reused_host_session_handoff(
            graph=graph, projection=projection, task=graph.tasks[2], worker_handle="worker-target",
            workspace_scope=workspace, execution_profile=profile,
        )

        self.assertIsNotNone(handoff)
        self.assertIn("Task FIRST-01 passed", str(handoff))
        self.assertIn("src/first.py", str(handoff))
        self.assertNotIn("src/second.py", str(handoff))

    def test_keeps_an_acknowledged_quarantine_from_poisoning_successor_sync(self) -> None:
        behavior = result_quarantine_behavior.ResultQuarantineBehavior(
            "test_sync_acks_a_quarantined_delivery_then_accepts_a_corrected_fresh_attempt"
        )
        behavior.setUp()
        try:
            behavior.test_sync_acks_a_quarantined_delivery_then_accepts_a_corrected_fresh_attempt()
        finally:
            behavior.tearDown()

    def test_rejects_graph_bootstrap_before_a_current_process_decision(self) -> None:
        (self.repository / "openspec/changes/portable/process-decision.json").unlink()

        rejected = self.run_cli(
            "bootstrap",
            "--change",
            "portable",
            "--run-id",
            "run-without-decision",
            "--bootstrap-id",
            "bootstrap-without-decision",
            "--driver",
            "host",
        )

        self.assertNotEqual(rejected.returncode, 0)
        self.assertEqual(
            json.loads(rejected.stderr)["error"]["code"], "process_decision_required"
        )
        self.assertFalse(
            (
                self.repository
                / "openspec/runs/portable/run-without-decision/events.jsonl"
            ).exists()
        )

    def test_uses_the_same_source_decision_boundary_for_validate_and_bootstrap(self) -> None:
        decision_path = self.repository / "openspec/changes/portable/process-decision.json"
        original = json.loads(decision_path.read_text(encoding="utf-8"))

        def assert_rejected(name: str, mutate) -> None:
            payload = copy.deepcopy(original)
            mutate(payload)
            decision_path.write_text(json.dumps(payload), encoding="utf-8")

            validated = self.run_cli("validate", "--change", "portable")
            bootstrapped = self.run_cli(
                "bootstrap",
                "--change",
                "portable",
                "--run-id",
                f"rejected-{name}",
                "--bootstrap-id",
                f"bootstrap-{name}",
                "--driver",
                "host",
            )

            self.assertNotEqual(validated.returncode, 0)
            self.assertNotEqual(bootstrapped.returncode, 0)
            validation_error = json.loads(validated.stderr)["error"]
            bootstrap_error = json.loads(bootstrapped.stderr)["error"]
            self.assertEqual(validation_error["code"], "process_decision_invalid")
            self.assertEqual(bootstrap_error["code"], "process_decision_invalid")
            self.assertEqual(
                (validation_error["code"], validation_error["field_path"]),
                (bootstrap_error["code"], bootstrap_error["field_path"]),
            )
            self.assertFalse(
                (self.repository / f"openspec/runs/portable/rejected-{name}").exists()
            )

        assert_rejected(
            "observed-basis",
            lambda payload: payload["decision"]["assumptions"].append(
                {
                    "assumption_id": "observed-source",
                    "statement": "The source was observed.",
                    "basis": "observed",
                    "evidence_ref": "file:AGENTS.md",
                }
            ),
        )
        assert_rejected(
            "unknown-assumption-field",
            lambda payload: payload["decision"]["assumptions"].append(
                {
                    "assumption_id": "unknown-source",
                    "statement": "The source has an unknown field.",
                    "basis": "repository",
                    "evidence_ref": "file:AGENTS.md",
                    "unexpected": True,
                }
            ),
        )
        amended = copy.deepcopy(original)
        amended["decision"]["amendments"].append(
            {
                "amendment_id": "revision-gap",
                "from_revision": 1,
                "to_revision": 3,
                "from_mode": "graph",
                "to_mode": "graph",
                "changed_evidence": ["The source revision changed."],
                "reason": "Exercise amendment validation.",
                "replacement_check": copy.deepcopy(amended["decision"]["selected_check"]),
            }
        )
        amended["decision"]["revision"] = 2
        decision_path.write_text(json.dumps(amended), encoding="utf-8")
        revision_validated = self.run_cli("validate", "--change", "portable")
        revision_bootstrapped = self.run_cli(
            "bootstrap", "--change", "portable", "--run-id", "rejected-revision-gap",
            "--bootstrap-id", "bootstrap-revision-gap", "--driver", "host",
        )
        self.assertEqual(
            json.loads(revision_validated.stderr)["error"]["code"],
            "process_decision_invalid",
        )
        self.assertEqual(
            json.loads(revision_bootstrapped.stderr)["error"]["code"],
            "process_decision_invalid",
        )
        self.assertEqual(
            json.loads(revision_validated.stderr)["error"]["field_path"],
            json.loads(revision_bootstrapped.stderr)["error"]["field_path"],
        )
        self.assertFalse(
            (self.repository / "openspec/runs/portable/rejected-revision-gap").exists()
        )

        assert_rejected(
            "packet-drift",
            lambda payload: payload["graph_contract"]["packets"][0]["paths"].append("src/drift.py"),
        )
        assert_rejected(
            "invalid-budget",
            lambda payload: payload["decision"]["budget"]["limits"][0].update({"value": 0}),
        )

        decision_path.write_text(json.dumps(original), encoding="utf-8")
        accepted = self.result(self.run_cli("validate", "--change", "portable"))
        self.assertEqual(accepted["process_decision"]["mode"], "graph")
        self.assertEqual(accepted["graph_contract"]["packets"], original["graph_contract"]["packets"])

    def test_controls_delegation_lifecycle_with_confined_receipts_and_typed_cleanup(self) -> None:
        scope, revision = self.active_delegation_parent()
        intent = self.delegation_intent(scope, revision)
        intent_path = self.repository / "delegation-intent.json"
        intent_path.write_text(json.dumps(intent), encoding="utf-8")
        requested = self.result(self.run_cli(
            "request-delegation", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--intent", intent_path.name,
        ))
        self.assertFalse(requested["idempotent"])

        profile_path = self.repository / "delegation-profile.json"
        profile_path.write_text(json.dumps(self.delegation_profile(scope)), encoding="utf-8")
        approved_arguments = (
            "approve-delegation", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--delegation", "intent-child",
            "--execution-profile", profile_path.name, "--context-revision", "context-revision-1",
            "--path", "src/root.py", "--context-ref", "context-root",
        )
        self.result(self.run_cli(*approved_arguments))

        owner = {
            "execution_host_id": scope["execution_workspace"]["execution_host_id"],
            "workspace_key": scope["execution_workspace"]["workspace_key"],
            "attempt_id": "child-attempt-1",
            "terminal_id": "terminal-child-1",
            "incarnation_id": "incarnation-child-1",
            "process_root": None,
            "provenance": "driver receipt",
        }
        started_receipt = self.write_delegation_artifact("started-receipt.json", {"dispatch": "child-1"})
        outside_receipt = "outside-lifecycle-receipt.json"
        (self.repository / outside_receipt).write_text(json.dumps({"dispatch": "outside"}), encoding="utf-8")
        start_arguments = (
            "start-delegation", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--delegation", "intent-child", "--child-attempt", "child-attempt-1",
            "--resource-owner", json.dumps(owner), "--receipt-id", "receipt-start-1",
            "--receipt-path", started_receipt,
        )
        before = self.run_directory_snapshot("run-1")
        outside_start = self.run_cli(
            "start-delegation", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--delegation", "intent-child", "--child-attempt", "child-attempt-1",
            "--resource-owner", json.dumps(owner), "--receipt-id", "receipt-outside-1",
            "--receipt-path", outside_receipt,
        )
        self.assertNotEqual(outside_start.returncode, 0)
        self.assertEqual(self.run_directory_snapshot("run-1"), before)
        before = self.run_directory_snapshot("run-1")
        off_placement_start = self.run_cli(
            "start-delegation", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--delegation", "intent-child", "--child-attempt", "child-attempt-1",
            "--resource-owner", json.dumps({
                **owner,
                "execution_host_id": "remote:unapproved-host",
                "workspace_key": "folder:unapproved-workspace",
            }),
            "--receipt-id", "receipt-off-placement-1", "--receipt-path", started_receipt,
        )
        self.assertNotEqual(off_placement_start.returncode, 0)
        self.assertEqual(self.run_directory_snapshot("run-1"), before)
        started = self.result(self.run_cli(*start_arguments))
        self.assertNotIn("child-attempt-1", started["state"]["attempts"])
        started_projection = started["state"]["delegations"]["intent-child"]
        started_bytes = (self.repository / started_receipt).read_bytes()
        self.assertEqual(started_projection["lifecycle_receipts"]["started"], {
            "receipt_id": "receipt-start-1",
            "receipt_path": started_receipt,
            "sha256": f"sha256:{hashlib.sha256(started_bytes).hexdigest()}",
            "byte_length": len(started_bytes),
        })

        registered = self.result(self.run_cli(
            "register-delegation-cleanup", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--delegation", "intent-child", "--cleanup-id", "cleanup-child-1",
            "--kind", "terminal", "--target", "terminal-child-1",
        ))
        self.assertEqual(registered["state"]["delegations"]["intent-child"]["cleanup_id"], "cleanup-child-1")
        finished = self.result(self.run_cli(
            "cleanup-finish", "--change", "portable", "--run-id", "run-1", "--generation", "2",
            "--cleanup-id", "cleanup-child-1", "--receipt", json.dumps({
                "kind": "terminal", "owner": owner, "terminal_id": "terminal-child-1",
                "incarnation_id": "incarnation-child-1", "status": "verified",
            }),
        ))
        self.assertEqual(finished["state"]["cleanup"]["cleanup-child-1"]["status"], "verified")
        replayed_finish = self.result(self.run_cli(
            "cleanup-finish", "--change", "portable", "--run-id", "run-1", "--generation", "2",
            "--cleanup-id", "cleanup-child-1", "--receipt", json.dumps({
                "kind": "terminal", "owner": owner, "terminal_id": "terminal-child-1",
                "incarnation_id": "incarnation-child-1", "status": "verified",
            }),
        ))
        self.assertTrue(replayed_finish["idempotent"])

        result = {
            "delegation_id": "intent-child", "task_id": "ROOT-01", "attempt_id": "child-attempt-1",
            "outcome": "reported", "summary": "Child completed its bounded verification.",
            "files_changed": [], "checks_run": ["python3 -m unittest"],
            "evidence_refs": ["file:src/root.py"], "questions": [], "external_refs": {},
        }
        result_path = self.repository / "delegation-result.json"
        result_path.write_text(json.dumps(result), encoding="utf-8")
        reported_receipt = self.write_delegation_artifact("reported-receipt.json", {"result": "child-1"})
        unauthorized_result_path = self.repository / "unauthorized-delegation-result.json"
        unauthorized_result_path.write_text(json.dumps({
            **result,
            "grade": "pass",
            "approval": {"coordinator_generation": 2},
            "cleanup_id": "cleanup-child-1",
        }), encoding="utf-8")
        report_arguments = (
            "report-delegation", "--change", "portable", "--run-id", "run-1", "--generation", "2",
            "--delegation", "intent-child", "--result", result_path.name, "--receipt-id", "receipt-report-1",
            "--receipt-path", reported_receipt,
        )
        before = self.run_directory_snapshot("run-1")
        unauthorized_report = self.run_cli(
            "report-delegation", "--change", "portable", "--run-id", "run-1", "--generation", "2",
            "--delegation", "intent-child", "--result", unauthorized_result_path.name,
            "--receipt-id", "receipt-report-unauthorized", "--receipt-path", reported_receipt,
        )
        self.assertNotEqual(unauthorized_report.returncode, 0)
        self.assertIsNone(started["state"]["tasks"]["ROOT-01"]["grade"])
        self.assertEqual(self.run_directory_snapshot("run-1"), before)
        self.result(self.run_cli(*report_arguments))
        before = self.run_directory_snapshot("run-1")
        reused_stage_receipt = self.run_cli(
            "release-delegation", "--change", "portable", "--run-id", "run-1", "--generation", "2",
            "--delegation", "intent-child", "--cleanup-id", "cleanup-child-1", "--receipt-id", "receipt-report-1",
            "--receipt-path", reported_receipt,
        )
        self.assertNotEqual(reused_stage_receipt.returncode, 0)
        self.assertEqual(self.run_directory_snapshot("run-1"), before)
        release_receipt = self.write_delegation_artifact("released-receipt.json", {"release": "child-1"})
        release_arguments = (
            "release-delegation", "--change", "portable", "--run-id", "run-1", "--generation", "2",
            "--delegation", "intent-child", "--cleanup-id", "cleanup-child-1", "--receipt-id", "receipt-release-1",
            "--receipt-path", release_receipt,
        )
        released = self.result(self.run_cli(*release_arguments))
        delegation = released["state"]["delegations"]["intent-child"]
        self.assertEqual(delegation["status"], "released")
        self.assertEqual(delegation["parent_task_id"], "ROOT-01")
        self.assertEqual(delegation["parent_attempt_id"], "attempt-root-01-001")
        self.assertEqual(delegation["execution_profile"], self.delegation_profile(scope))
        self.assertEqual(delegation["context_revision"], "context-revision-1")
        self.assertEqual(delegation["context_refs"], ["context-root"])
        self.assertEqual(delegation["resource_owner"], owner)
        self.assertEqual(delegation["spawned_by"], "attempt-root-01-001")
        self.assertEqual(delegation["cleanup_id"], "cleanup-child-1")
        self.assertEqual(
            set(delegation["lifecycle_receipts"]), {"started", "reported", "released"}
        )
        self.assertEqual(delegation["lifecycle_receipts"]["started"]["receipt_id"], "receipt-start-1")
        self.assertEqual(delegation["lifecycle_receipts"]["reported"]["receipt_id"], "receipt-report-1")
        self.assertEqual(delegation["lifecycle_receipts"]["released"]["receipt_id"], "receipt-release-1")
        self.assertIsNone(released["state"]["tasks"]["ROOT-01"]["grade"])

        nested_intent = self.delegation_intent(scope, released["state"]["last_sequence"], intent_id="intent-nested")
        nested_intent["parent_attempt_id"] = "child-attempt-1"
        nested_intent_path = self.repository / "nested-intent.json"
        nested_intent_path.write_text(json.dumps(nested_intent), encoding="utf-8")
        before = self.run_directory_snapshot("run-1")
        nested = self.run_cli(
            "request-delegation", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--intent", nested_intent_path.name,
        )
        self.assertNotEqual(nested.returncode, 0)
        self.assertEqual(self.run_directory_snapshot("run-1"), before)

        for arguments in (approved_arguments, start_arguments, report_arguments, release_arguments):
            before = self.run_directory_snapshot("run-1")
            replayed = self.result(self.run_cli(*arguments))
            self.assertTrue(replayed["idempotent"])
            self.assertEqual(self.run_directory_snapshot("run-1"), before)

        before = self.run_directory_snapshot("run-1")
        divergent = self.run_cli(
            "start-delegation", "--change", "portable", "--run-id", "run-1", "--generation", "2",
            "--delegation", "intent-child", "--child-attempt", "child-attempt-1",
            "--resource-owner", json.dumps(owner), "--receipt-id", "receipt-start-1",
            "--receipt-path", reported_receipt,
        )
        self.assertNotEqual(divergent.returncode, 0)
        self.assertEqual(self.run_directory_snapshot("run-1"), before)

        second_intent = self.delegation_intent(
            scope, released["state"]["last_sequence"], intent_id="intent-child-2"
        )
        second_intent_path = self.repository / "delegation-intent-2.json"
        second_intent_path.write_text(json.dumps(second_intent), encoding="utf-8")
        self.result(self.run_cli(
            "request-delegation", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--intent", second_intent_path.name,
        ))
        self.result(self.run_cli(
            "approve-delegation", "--change", "portable", "--run-id", "run-1", "--generation", "2",
            "--delegation", "intent-child-2", "--execution-profile", profile_path.name,
            "--context-revision", "context-revision-1", "--path", "src/root.py", "--context-ref", "context-root",
        ))
        before = self.run_directory_snapshot("run-1")
        cross_delegation = self.run_cli(
            "start-delegation", "--change", "portable", "--run-id", "run-1", "--generation", "2",
            "--delegation", "intent-child-2", "--child-attempt", "child-attempt-2",
            "--resource-owner", json.dumps({**owner, "attempt_id": "child-attempt-2", "terminal_id": "terminal-child-2", "incarnation_id": "incarnation-child-2"}),
            "--receipt-id", "receipt-start-1", "--receipt-path", started_receipt,
        )
        self.assertNotEqual(cross_delegation.returncode, 0)
        self.assertEqual(self.run_directory_snapshot("run-1"), before)

        duplicate_intent = {**second_intent, "expected_revision": released["state"]["last_sequence"], "purpose": "Different payload."}
        second_intent_path.write_text(json.dumps(duplicate_intent), encoding="utf-8")
        duplicate = self.run_cli(
            "request-delegation", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--intent", second_intent_path.name,
        )
        self.assertNotEqual(duplicate.returncode, 0)
        self.assertEqual(self.run_directory_snapshot("run-1"), before)

    def test_fences_amendments_and_never_widens_the_original_intent(self) -> None:
        scope, revision = self.active_delegation_parent()
        intent = self.delegation_intent(scope, revision, intent_id="intent-outside", paths=["src/outside.py"])
        intent_path = self.repository / "outside-intent.json"
        intent_path.write_text(json.dumps(intent), encoding="utf-8")
        self.result(self.run_cli(
            "request-delegation", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--intent", intent_path.name,
        ))
        profile_path = self.repository / "outside-profile.json"
        profile_path.write_text(json.dumps(self.delegation_profile(scope)), encoding="utf-8")
        approval = (
            "approve-delegation", "--change", "portable", "--run-id", "run-1", "--generation", "2",
            "--delegation", "intent-outside", "--execution-profile", profile_path.name,
            "--context-revision", "context-revision-1", "--path", "src/outside.py", "--context-ref", "context-root",
        )
        before = self.run_directory_snapshot("run-1")
        rejected = self.run_cli(*approval)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertEqual(self.run_directory_snapshot("run-1"), before)
        widened_context = self.run_cli(
            "approve-delegation", "--change", "portable", "--run-id", "run-1", "--generation", "2",
            "--delegation", "intent-outside", "--execution-profile", profile_path.name,
            "--context-revision", "context-revision-1", "--path", "src/outside.py", "--context-ref", "context-other",
        )
        self.assertNotEqual(widened_context.returncode, 0)
        self.assertEqual(self.run_directory_snapshot("run-1"), before)

        before_amendment = self.run_directory_snapshot("run-1")
        amendment = self.run_cli(
            "amend-graph", "--change", "portable", "--run-id", "run-1", "--generation", "2",
            "--amendment-id", "amend-outside", "--parent-task", "ROOT-01", "--parent-attempt", "attempt-root-01-001", "--path", "src/outside.py",
            "--reason", "The bounded verifier needs the adjacent generated file.",
        )
        self.assertNotEqual(amendment.returncode, 0)
        self.assertEqual(json.loads(amendment.stderr)["error"]["code"], "invalid_graph")
        self.assertEqual(self.run_directory_snapshot("run-1"), before_amendment)

        stale_canvas_intent = self.delegation_intent(scope, revision, intent_id="intent-stale-canvas")
        stale_canvas_intent["actor"] = {
            "actor_id": "canvas-user-1", "kind": "user", "authenticated": True, "session_id": "canvas-session-1",
        }
        stale_path = self.repository / "stale-canvas-intent.json"
        stale_path.write_text(json.dumps(stale_canvas_intent), encoding="utf-8")
        before = self.run_directory_snapshot("run-1")
        stale_canvas = self.run_cli(
            "request-delegation", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--intent", stale_path.name,
        )
        self.assertNotEqual(stale_canvas.returncode, 0)
        self.assertEqual(self.run_directory_snapshot("run-1"), before)
        stale_worker_intent = self.delegation_intent(scope, revision, intent_id="intent-stale-worker")
        stale_worker_intent["actor"] = {
            "actor_id": "worker-stale-1", "kind": "worker", "authenticated": True, "session_id": "worker-session-1",
        }
        stale_worker_path = self.repository / "stale-worker-intent.json"
        stale_worker_path.write_text(json.dumps(stale_worker_intent), encoding="utf-8")
        stale_worker = self.run_cli(
            "request-delegation", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--intent", stale_worker_path.name,
        )
        self.assertNotEqual(stale_worker.returncode, 0)
        self.assertEqual(self.run_directory_snapshot("run-1"), before)
        stale_coordinator = self.run_cli(
            "amend-graph", "--change", "portable", "--run-id", "run-1", "--generation", "1",
            "--amendment-id", "amend-stale", "--parent-task", "ROOT-01", "--parent-attempt", "attempt-root-01-001", "--path", "src/next.py", "--reason", "Stale.",
        )
        self.assertNotEqual(stale_coordinator.returncode, 0)
        self.assertEqual(self.run_directory_snapshot("run-1"), before)

    def test_rejects_a_sibling_attempt_amendment_before_approving_a_delegation(self) -> None:
        scope, revision = self.active_delegation_parent()
        intent = self.delegation_intent(
            scope, revision, intent_id="intent-sibling-amendment", paths=["src/sibling.py"]
        )
        intent_path = self.repository / "sibling-amendment-intent.json"
        intent_path.write_text(json.dumps(intent), encoding="utf-8")
        self.result(self.run_cli(
            "request-delegation", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--intent", intent_path.name,
        ))
        self.result(self.run_cli(
            "abandon-attempt", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--attempt", "attempt-root-01-001",
            "--reason", "Reserve the sibling attempt fixture.",
        ))
        sibling = self.result(self.run_cli(
            "dispatch", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--task", "ROOT-01", "--attempt-id", "attempt-root-01-002",
            "--local", "--defer-launch",
        ))
        self.result(self.run_cli(
            "amend-graph", "--change", "portable", "--run-id", "run-1", "--generation", "2",
            "--amendment-id", "amend-sibling", "--parent-task", "ROOT-01",
            "--parent-attempt", sibling["attempt_id"], "--path", "src/sibling.py",
            "--reason", "The sibling attempt needs its generated file.",
        ))
        profile_path = self.repository / "sibling-amendment-profile.json"
        profile_path.write_text(json.dumps(self.delegation_profile(scope)), encoding="utf-8")
        before = self.run_directory_snapshot("run-1")

        rejected = self.run_cli(
            "approve-delegation", "--change", "portable", "--run-id", "run-1", "--generation", "2",
            "--delegation", "intent-sibling-amendment", "--execution-profile", profile_path.name,
            "--context-revision", "context-revision-1", "--path", "src/sibling.py",
            "--context-ref", "context-root", "--amendment-id", "amend-sibling",
        )

        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("another parent attempt", rejected.stderr)
        self.assertEqual(self.run_directory_snapshot("run-1"), before)

    def test_refuses_child_start_after_parent_abandonment_and_completion_with_active_delegation(self) -> None:
        scope, revision = self.active_delegation_parent()
        intent = self.delegation_intent(scope, revision, intent_id="intent-parent-ended")
        intent_path = self.repository / "ended-parent-intent.json"
        intent_path.write_text(json.dumps(intent), encoding="utf-8")
        self.result(self.run_cli(
            "request-delegation", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--intent", intent_path.name,
        ))
        profile_path = self.repository / "ended-parent-profile.json"
        profile_path.write_text(json.dumps(self.delegation_profile(scope)), encoding="utf-8")
        self.result(self.run_cli(
            "approve-delegation", "--change", "portable", "--run-id", "run-1", "--generation", "2",
            "--delegation", "intent-parent-ended", "--execution-profile", profile_path.name,
            "--context-revision", "context-revision-1", "--path", "src/root.py", "--context-ref", "context-root",
        ))
        self.result(self.run_cli(
            "abandon-attempt", "--change", "portable", "--run-id", "run-1", "--generation", "2",
            "--attempt", "attempt-root-01-001", "--reason", "The parent worker stopped.",
        ))
        before = self.run_directory_snapshot("run-1")
        incomplete = self.run_cli(
            "complete", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--outcome", "partial",
        )
        self.assertNotEqual(incomplete.returncode, 0)
        self.assertIn("terminal delegations", incomplete.stderr)
        self.assertEqual(self.run_directory_snapshot("run-1"), before)
        owner = {
            "execution_host_id": scope["execution_workspace"]["execution_host_id"],
            "workspace_key": scope["execution_workspace"]["workspace_key"],
            "attempt_id": "child-after-parent", "terminal_id": "terminal-after-parent",
            "incarnation_id": "incarnation-after-parent", "process_root": None, "provenance": "driver receipt",
        }
        receipt = self.write_delegation_artifact("parent-ended-start.json", {"dispatch": "child"})
        before = self.run_directory_snapshot("run-1")
        start = self.run_cli(
            "start-delegation", "--change", "portable", "--run-id", "run-1", "--generation", "2",
            "--delegation", "intent-parent-ended", "--child-attempt", "child-after-parent",
            "--resource-owner", json.dumps(owner), "--receipt-id", "receipt-parent-ended", "--receipt-path", receipt,
        )
        self.assertNotEqual(start.returncode, 0)
        self.assertEqual(self.run_directory_snapshot("run-1"), before)

    def test_issues_distinct_host_run_receipts_and_copies_the_scope_to_the_capsule(self) -> None:
        first, _ = self.bootstrap_and_claim()
        second = self.result(self.run_cli(
            "bootstrap", "--change", "portable", "--run-id", "run-2",
            "--bootstrap-id", "bootstrap-2", "--driver", "host",
        ))

        first_scope = first["state"]["workspace_scope"]
        second_scope = second["state"]["workspace_scope"]
        first_capsule = json.loads((self.repository / first["capsule_path"]).read_text())
        first_receipt = json.loads((
            self.repository
            / first_scope["binding_receipt_ref"].removeprefix("artifact:")
        ).read_text())

        self.assertNotEqual(first_scope["repository_id"], second_scope["repository_id"])
        self.assertRegex(first_scope["repository_id"], r"^host-run-[0-9a-f-]{36}$")
        self.assertEqual(
            first_scope["orchestration_home"]["workspace_key"],
            f"folder:{first_scope['repository_id']}",
        )
        self.assertEqual(first_scope, first_capsule["workspace_scope"])
        self.assertEqual(first_receipt["base_revision"], first_scope["base_revision"])
        self.assertEqual(first_receipt["dirty_paths"], first_scope["dirty_paths"])
        self.assertEqual(first_receipt["authority"]["issued_for_run_id"], "run-1")

    def test_requires_receipts_for_auto_and_orca_before_journal_creation(self) -> None:
        for driver, run_id in (("auto", "run-auto"), ("orca", "run-orca")):
            with self.subTest(driver=driver):
                rejected = self.run_cli(
                    "bootstrap", "--change", "portable", "--run-id", run_id,
                    "--bootstrap-id", f"bootstrap-{driver}", "--driver", driver,
                )
                self.assertNotEqual(rejected.returncode, 0)
                self.assertEqual(
                    json.loads(rejected.stderr)["error"]["code"],
                    "workspace_receipt_required",
                )
                self.assertFalse((
                    self.repository / f"openspec/runs/portable/{run_id}/events.jsonl"
                ).exists())

    def test_preserves_explicit_remote_receipt_identity_and_execution_snapshot(self) -> None:
        receipt = self.explicit_workspace_receipt("run-remote")
        receipt_path = self.repository / "workspace-receipt.json"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

        bootstrap = self.result(self.run_cli(
            "bootstrap", "--change", "portable", "--run-id", "run-remote",
            "--bootstrap-id", "bootstrap-remote", "--driver", "orca",
            "--workspace-receipt", "workspace-receipt.json",
        ))
        scope = bootstrap["state"]["workspace_scope"]

        self.assertEqual(scope["execution_host"]["id"], "ssh:build-host-01")
        self.assertEqual(
            scope["orchestration_home"]["execution_host_id"], "runtime:orca-local-01"
        )
        self.assertEqual(scope["base_revision"], "remote-revision-01")
        self.assertEqual(scope["dirty_paths"], ["remote/source.py"])

    def test_bootstraps_from_an_external_absolute_receipt_and_uses_the_saved_copy(self) -> None:
        receipt = self.explicit_host_workspace_receipt("run-external")
        with tempfile.TemporaryDirectory() as external_directory:
            receipt_path = Path(external_directory) / "workspace-receipt.json"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            bootstrap = self.result(self.run_cli(
                "bootstrap", "--change", "portable", "--run-id", "run-external",
                "--bootstrap-id", "bootstrap-external", "--driver", "host",
                "--workspace-receipt", str(receipt_path),
            ))
            receipt_path.unlink()
            claimed = self.result(self.run_cli(
                "claim-coordinator", "--capsule", bootstrap["capsule_path"],
                "--coordinator-id", "coordinator-external",
            ))

        saved = json.loads((
            self.repository
            / bootstrap["state"]["workspace_scope"]["binding_receipt_ref"].removeprefix("artifact:")
        ).read_text(encoding="utf-8"))
        self.assertEqual(saved, receipt)
        self.assertEqual(claimed["state"]["driver"], "host")
        self.assertNotIn(str(receipt_path), json.dumps(claimed))

    def test_fails_closed_before_executing_remote_or_different_workspaces(self) -> None:
        receipt = self.explicit_workspace_receipt("run-remote-guard")
        receipt_path = self.repository / "receipt-remote-guard.json"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        bootstrap = self.result(self.run_cli(
            "bootstrap", "--change", "portable", "--run-id", "run-remote-guard",
            "--bootstrap-id", "bootstrap-remote-guard", "--driver", "orca",
            "--workspace-receipt", receipt_path.name,
        ))
        before_claim = self.run_directory_snapshot("run-remote-guard")
        claim = self.run_cli(
            "claim-coordinator", "--capsule", bootstrap["capsule_path"],
            "--coordinator-id", "coordinator-remote",
        )
        self.assertNotEqual(claim.returncode, 0)
        self.assertEqual(
            json.loads(claim.stderr)["error"]["code"], "execution_scope_unsupported"
        )
        self.assertEqual(self.run_directory_snapshot("run-remote-guard"), before_claim)

        directory = self.repository / "openspec/runs/portable/run-remote-guard"
        journal = runtime._journal(directory)
        journal.append(
            "coordinator_claimed",
            {"coordinator_id": "coordinator-remote", "capsule_path": bootstrap["capsule_path"]},
            coordinator_generation=2,
        )
        journal.append("driver_selected", {"driver": "host"}, coordinator_generation=2)
        guarded_commands = [
            ("dispatch", "--task", "ROOT-01", "--local"),
            ("run-check", "--task", "ROOT-01"),
            (
                "import-checked-task", "--task", "ROOT-01", "--import-id", "import-remote",
                "--note", "Do not execute a remote check locally.",
            ),
        ]
        before_guarded = self.run_directory_snapshot("run-remote-guard")
        for command, *extra in guarded_commands:
            with self.subTest(command=command):
                rejected = self.run_cli(
                    command, "--change", "portable", "--run-id", "run-remote-guard",
                    "--generation", "2", *extra,
                )
                self.assertNotEqual(rejected.returncode, 0)
                self.assertEqual(
                    json.loads(rejected.stderr)["error"]["code"],
                    "execution_scope_unsupported",
                )
                self.assertEqual(
                    self.run_directory_snapshot("run-remote-guard"), before_guarded
                )

        takeover_receipt = self.explicit_workspace_receipt("run-remote-takeover")
        takeover_path = self.repository / "receipt-remote-takeover.json"
        takeover_path.write_text(json.dumps(takeover_receipt), encoding="utf-8")
        self.result(self.run_cli(
            "bootstrap", "--change", "portable", "--run-id", "run-remote-takeover",
            "--bootstrap-id", "bootstrap-remote-takeover", "--driver", "orca",
            "--workspace-receipt", takeover_path.name,
        ))
        before_takeover = self.run_directory_snapshot("run-remote-takeover")
        takeover = self.run_cli(
            "takeover", "--change", "portable", "--run-id", "run-remote-takeover",
            "--generation", "2", "--coordinator-id", "coordinator-takeover",
        )
        self.assertNotEqual(takeover.returncode, 0)
        self.assertEqual(
            json.loads(takeover.stderr)["error"]["code"], "execution_scope_unsupported"
        )
        self.assertEqual(
            self.run_directory_snapshot("run-remote-takeover"), before_takeover
        )

        init_receipt = self.explicit_workspace_receipt("run-remote-init")
        init_path = self.repository / "receipt-remote-init.json"
        init_path.write_text(json.dumps(init_receipt), encoding="utf-8")
        initialized = self.run_cli(
            "init", "--change", "portable", "--run-id", "run-remote-init",
            "--coordinator-id", "coordinator-init", "--driver", "host",
            "--workspace-receipt", init_path.name,
        )
        self.assertNotEqual(initialized.returncode, 0)
        self.assertEqual(
            json.loads(initialized.stderr)["error"]["code"], "execution_scope_unsupported"
        )
        self.assertFalse((
            self.repository / "openspec/runs/portable/run-remote-init"
        ).exists())

        different = self.explicit_workspace_receipt("run-local-different")
        different["execution_host"] = {"id": "runtime:different-local", "boundary": "local"}
        different["execution_workspace"] = {
            "execution_host_id": "runtime:different-local",
            "workspace_key": "folder:different-local",
            "kind": "folder",
            "path": "/tmp/different-local",
        }
        different_path = self.repository / "receipt-local-different.json"
        different_path.write_text(json.dumps(different), encoding="utf-8")
        different_bootstrap = self.result(self.run_cli(
            "bootstrap", "--change", "portable", "--run-id", "run-local-different",
            "--bootstrap-id", "bootstrap-local-different", "--driver", "orca",
            "--workspace-receipt", different_path.name,
        ))
        different_claim = self.run_cli(
            "claim-coordinator", "--capsule", different_bootstrap["capsule_path"],
            "--coordinator-id", "coordinator-local-different",
        )
        self.assertNotEqual(different_claim.returncode, 0)
        self.assertEqual(
            json.loads(different_claim.stderr)["error"]["code"],
            "execution_scope_unsupported",
        )

    def test_rejects_missing_execution_snapshot_fields_before_journaling(self) -> None:
        for field, run_id in (("base_revision", "run-missing-base"), ("dirty_paths", "run-missing-dirty")):
            with self.subTest(field=field):
                receipt = self.explicit_workspace_receipt(run_id)
                receipt.pop(field)
                path = self.repository / f"receipt-{field}.json"
                path.write_text(json.dumps(receipt), encoding="utf-8")
                rejected = self.run_cli(
                    "bootstrap", "--change", "portable", "--run-id", run_id,
                    "--bootstrap-id", f"bootstrap-{field}", "--driver", "orca",
                    "--workspace-receipt", path.name,
                )
                self.assertNotEqual(rejected.returncode, 0)
                self.assertFalse((
                    self.repository / f"openspec/runs/portable/{run_id}/events.jsonl"
                ).exists())

    def test_rejects_a_workspace_receipt_with_an_aliased_repository_path(self) -> None:
        receipt = self.explicit_workspace_receipt("run-aliased")
        aliased = receipt["canonical_root"] + "/."
        receipt["canonical_root"] = aliased
        receipt["orchestration_home"]["path"] = aliased
        path = self.repository / "receipt-aliased.json"
        path.write_text(json.dumps(receipt), encoding="utf-8")

        rejected = self.run_cli(
            "bootstrap", "--change", "portable", "--run-id", "run-aliased",
            "--bootstrap-id", "bootstrap-aliased", "--driver", "orca",
            "--workspace-receipt", path.name,
        )

        self.assertNotEqual(rejected.returncode, 0)
        self.assertEqual(
            json.loads(rejected.stderr)["error"]["code"], "workspace_receipt_mismatch"
        )
        self.assertFalse((
            self.repository / "openspec/runs/portable/run-aliased/events.jsonl"
        ).exists())

    def test_rejects_every_host_run_semantic_divergence_before_journaling(self) -> None:
        def makes_worktree(receipt: dict) -> None:
            for field in ("orchestration_home", "execution_workspace"):
                receipt[field]["kind"] = "git-worktree"
                receipt[field]["worktree_path"] = receipt["canonical_root"]

        cases = {
            "repository-id": lambda value: value.update(repository_id="host-run-invalid"),
            "remote-host": lambda value: value["execution_host"].update(boundary="remote"),
            "different-identities": lambda value: value["execution_workspace"].update(
                workspace_key="folder:host-run-22222222-2222-4222-8222-222222222222"
            ),
            "worktree": makes_worktree,
            "wrong-path": lambda value: (
                value["orchestration_home"].update(path="/tmp/other-workspace"),
                value["execution_workspace"].update(path="/tmp/other-workspace"),
            ),
            "workspace-key": lambda value: (
                value["orchestration_home"].update(workspace_key="folder:wrong"),
                value["execution_workspace"].update(workspace_key="folder:wrong"),
            ),
            "authority-scope": lambda value: value["authority"].update(scope="workspace"),
            "aliased-root": lambda value: (
                value.update(canonical_root=value["canonical_root"] + "/."),
                value["orchestration_home"].update(path=value["orchestration_home"]["path"] + "/."),
                value["execution_workspace"].update(path=value["execution_workspace"]["path"] + "/."),
            ),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name):
                run_id = f"run-{name}"
                receipt = self.explicit_host_workspace_receipt(run_id)
                mutate(receipt)
                path = self.repository / f"receipt-{name}.json"
                path.write_text(json.dumps(receipt), encoding="utf-8")
                rejected = self.run_cli(
                    "bootstrap", "--change", "portable", "--run-id", run_id,
                    "--bootstrap-id", f"bootstrap-{name}", "--driver", "host",
                    "--workspace-receipt", path.name,
                )
                self.assertNotEqual(rejected.returncode, 0)
                self.assertFalse((
                    self.repository / f"openspec/runs/portable/{run_id}"
                ).exists())

        wrong_run = self.explicit_host_workspace_receipt("another-run")
        wrong_run_path = self.repository / "receipt-wrong-run.json"
        wrong_run_path.write_text(json.dumps(wrong_run), encoding="utf-8")
        rejected = self.run_cli(
            "bootstrap", "--change", "portable", "--run-id", "run-wrong-run",
            "--bootstrap-id", "bootstrap-wrong-run", "--driver", "host",
            "--workspace-receipt", wrong_run_path.name,
        )
        self.assertNotEqual(rejected.returncode, 0)
        self.assertFalse((
            self.repository / "openspec/runs/portable/run-wrong-run"
        ).exists())

    def test_fails_closed_for_receipt_tampering_deletion_and_scope_divergence(self) -> None:
        bootstrap, _ = self.bootstrap_and_claim()
        directory = self.repository / "openspec/runs/portable/run-1"
        receipt_path = directory / runtime.WORKSPACE_BOOTSTRAP_RECEIPT_FILE
        original_receipt = receipt_path.read_text(encoding="utf-8")

        receipt = json.loads(original_receipt)
        receipt["base_revision"] = "tampered-revision"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        tampered = self.run_cli(
            "resume", "--change", "portable", "--run-id", "run-1", "--generation", "2"
        )
        self.assertNotEqual(tampered.returncode, 0)
        self.assertEqual(json.loads(tampered.stderr)["error"]["code"], "workspace_binding_invalid")

        receipt_path.write_text(original_receipt, encoding="utf-8")
        projection = runtime._projection(directory)
        other_repository = self.repository / "other-repository"
        other_repository.mkdir()
        with self.assertRaisesRegex(
            runtime.AgentGraphCliError, "does not match --repo"
        ):
            runtime._verify_workspace_binding(other_repository, directory, projection)
        for field, value in (
            ("base_revision", "divergent-revision"),
            ("dirty_paths", ["divergent/path.py"]),
        ):
            with self.subTest(divergent=field):
                divergent = json.loads(json.dumps(projection))
                divergent["workspace_scope"][field] = value
                with self.assertRaisesRegex(
                    runtime.AgentGraphCliError, f"{field} does not match"
                ):
                    runtime._verify_workspace_binding(self.repository, directory, divergent)

        receipt_path.unlink()
        missing = self.run_cli(
            "resume", "--change", "portable", "--run-id", "run-1", "--generation", "2"
        )
        self.assertNotEqual(missing.returncode, 0)
        self.assertEqual(json.loads(missing.stderr)["error"]["code"], "workspace_binding_invalid")

    def test_binding_preflight_protects_every_public_mutator_without_side_effects(self) -> None:
        mutators = [
            ("takeover", "--coordinator-id", "coordinator-stale"),
            ("recover-driver-selection",),
            ("resume",),
            ("dispatch", "--task", "ROOT-01", "--local"),
            ("sync",),
            ("record-result", "--attempt", "attempt-missing", "--result-json", "{}"),
            ("reply", "--question", "question-missing", "--body", "answer"),
            ("abandon-attempt", "--attempt", "attempt-missing", "--reason", "lost"),
            ("recover-attempt", "--attempt", "attempt-missing"),
            ("recover-cleanup", "--attempt", "attempt-missing"),
            ("run-check", "--task", "ROOT-01"),
            (
                "import-checked-task", "--task", "ROOT-01", "--import-id", "import-binding",
                "--note", "Binding must win.",
            ),
            ("grade", "--task", "ROOT-01", "--grade", "pass", "--note", "stale"),
            ("record-repair", "--task", "ROOT-01", "--hypothesis", "stale"),
            (
                "audit-reject-attempt", "--attempt", "attempt-missing",
                "--rejection-id", "rejection-binding", "--finding-ref", "file:missing.json",
                "--hypothesis", "stale",
            ),
            (
                "cleanup-register", "--cleanup-id", "cleanup-binding", "--kind", "other",
                "--target", "missing", "--owner", "coordinator-stale",
            ),
            (
                "add-cleanup", "--cleanup-id", "cleanup-binding", "--kind", "other",
                "--target", "missing", "--owner", "coordinator-stale",
            ),
            ("cleanup-finish", "--cleanup-id", "cleanup-missing"),
            ("finish-cleanup", "--cleanup-id", "cleanup-missing"),
            ("cleanup-retain", "--cleanup-id", "cleanup-missing", "--receipt", "{}"),
            ("complete", "--outcome", "pass"),
        ]

        for tamper_mode in ("deleted", "hash", "content"):
            run_id = f"run-binding-{tamper_mode}"
            bootstrap = self.result(self.run_cli(
                "bootstrap", "--change", "portable", "--run-id", run_id,
                "--bootstrap-id", f"bootstrap-binding-{tamper_mode}", "--driver", "host",
            ))
            self.result(self.run_cli(
                "claim-coordinator", "--capsule", bootstrap["capsule_path"],
                "--coordinator-id", f"coordinator-binding-{tamper_mode}",
            ))
            directory = self.repository / f"openspec/runs/portable/{run_id}"
            receipt_path = directory / runtime.WORKSPACE_BOOTSTRAP_RECEIPT_FILE
            if tamper_mode == "deleted":
                receipt_path.unlink()
            elif tamper_mode == "hash":
                lines = (directory / "events.jsonl").read_text(encoding="utf-8").splitlines()
                first = json.loads(lines[0])
                first["data"]["workspace_scope"]["binding_receipt_hash"] = "sha256:" + "0" * 64
                lines[0] = json.dumps(first, separators=(",", ":"), sort_keys=True)
                (directory / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
            else:
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                receipt["base_revision"] = "tampered-content-revision"
                receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
                lines = (directory / "events.jsonl").read_text(encoding="utf-8").splitlines()
                first = json.loads(lines[0])
                first["data"]["workspace_scope"]["binding_receipt_hash"] = runtime._workspace_receipt_hash(receipt)
                lines[0] = json.dumps(first, separators=(",", ":"), sort_keys=True)
                (directory / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
                (directory / "state.json").write_text("{}\n", encoding="utf-8")
                with (directory / "events.jsonl").open("ab") as handle:
                    handle.write(b'{"partial":')

            snapshot = self.run_directory_snapshot(run_id)
            for command, *extra in mutators:
                with self.subTest(tamper=tamper_mode, command=command):
                    rejected = self.run_cli(
                        command, "--change", "portable", "--run-id", run_id,
                        "--generation", "1", *extra,
                    )
                    self.assertNotEqual(rejected.returncode, 0)
                    self.assertEqual(
                        json.loads(rejected.stderr)["error"]["code"],
                        "workspace_binding_invalid",
                    )
                    self.assertEqual(self.run_directory_snapshot(run_id), snapshot)

    def test_takeover_fences_the_prior_generation(self) -> None:
        bootstrap, _ = self.bootstrap_and_claim()
        takeover = self.result(
            self.run_cli(
                "takeover", "--change", "portable", "--run-id", "run-1",
                "--generation", "2", "--coordinator-id", "coordinator-2",
            )
        )
        self.assertEqual(takeover["coordinator_generation"], 3)
        before_scope = bootstrap["state"]["workspace_scope"]
        after_scope = takeover["state"]["workspace_scope"]
        self.assertEqual(
            {key: value for key, value in before_scope.items() if key != "coordinator_generation"},
            {key: value for key, value in after_scope.items() if key != "coordinator_generation"},
        )

        stale = self.run_cli(
            "dispatch", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--task", "ROOT-01", "--local",
        )
        self.assertNotEqual(stale.returncode, 0)
        error = json.loads(stale.stderr)["error"]
        self.assertEqual(error["code"], "stale_coordinator")

    def test_pins_policy_before_reserving_a_host_attempt(self) -> None:
        self.bootstrap_and_claim()

        dispatched = self.result(
            self.run_cli(
                "dispatch", "--change", "portable", "--run-id", "run-1",
                "--generation", "2", "--task", "ROOT-01", "--local", "--defer-launch",
            )
        )

        snapshot = self.repository / "openspec/runs/portable/run-1/artifacts/routing-policy-v1.json"
        policy = json.loads(snapshot.read_text(encoding="utf-8"))
        expected_digest = "sha256:" + hashlib.sha256(
            json.dumps(policy, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ).hexdigest()
        attempt = dispatched["state"]["attempts"][dispatched["attempt_id"]]

        self.assertEqual(attempt["routing_summary"]["policy_digest"], expected_digest)
        self.assertEqual(
            attempt["routing_summary"]["policy_source"],
            "skills/impl/references/routing-policy.seed.json",
        )
        self.assertEqual(attempt["routing_summary"]["policy_id"], policy["policy_id"])

        source = self.repository / "skills/impl/references/routing-policy.seed.json"
        edited = {**policy, "policy_id": "edited-source-policy"}
        source.write_text(json.dumps(edited), encoding="utf-8")
        resumed = self.result(
            self.run_cli(
                "resume", "--change", "portable", "--run-id", "run-1", "--generation", "2",
            )
        )
        resumed_attempt = resumed["state"]["attempts"][dispatched["attempt_id"]]

        self.assertEqual(resumed_attempt["routing_summary"]["policy_digest"], expected_digest)
        self.assertEqual(json.loads(snapshot.read_text(encoding="utf-8"))["policy_id"], policy["policy_id"])

    def test_executes_a_complete_dependency_chain_without_provider_grading(self) -> None:
        self.bootstrap_and_claim()
        ready = self.result(self.run_cli("ready", "--change", "portable", "--run-id", "run-1"))
        self.assertEqual([task["id"] for task in ready["ready"]], ["ROOT-01"])

        for task_id, changed_file in (("ROOT-01", "src/root.py"), ("NEXT-02", "src/next.py")):
            dispatched = self.result(
                self.run_cli(
                    "dispatch", "--change", "portable", "--run-id", "run-1",
                    "--generation", "2", "--task", task_id, "--local",
                )
            )
            attempt_id = dispatched["attempt_id"]
            report = {
                "task_id": task_id,
                "attempt_id": attempt_id,
                "outcome": "reported",
                "summary": f"Reported {task_id}.",
                "files_changed": [changed_file],
                "checks_run": ["python3 -m unittest tests.test_root"],
                "evidence_refs": [],
                "questions": [],
                "external_refs": {},
            }
            reported = self.result(
                self.run_cli(
                    "record-result", "--change", "portable", "--run-id", "run-1",
                    "--generation", "2", "--attempt", attempt_id,
                    "--result-json", json.dumps(report),
                )
            )
            self.assertIsNone(reported["state"]["tasks"][task_id]["grade"])
            checked = self.result(
                self.run_cli(
                    "run-check", "--change", "portable", "--run-id", "run-1",
                    "--generation", "2", "--task", task_id,
                )
            )
            self.assertEqual(checked["check"]["status"], "passed")
            self.result(
                self.run_cli(
                    "grade", "--change", "portable", "--run-id", "run-1",
                    "--generation", "2", "--task", task_id, "--grade", "pass",
                    "--note", "The report and focused check passed.",
                )
            )

        completed = self.result(
            self.run_cli(
                "complete", "--change", "portable", "--run-id", "run-1",
                "--generation", "2", "--outcome", "pass",
            )
        )
        self.assertEqual(completed["state"]["outcome"], "pass")

        events = (self.repository / "openspec/runs/portable/run-1/events.jsonl").read_text().splitlines()
        projection = json.loads((self.repository / "openspec/runs/portable/run-1/state.json").read_text())
        self.assertEqual(projection["last_sequence"], len(events))
        event_types = [json.loads(line)["type"] for line in events]
        self.assertLess(event_types.index("driver_selection_reserved"), event_types.index("driver_selected"))
        self.assertLess(event_types.index("attempt_reserved"), event_types.index("attempt_started"))
        attempt_events = [
            event for line in events
            if (event := json.loads(line))["type"] in {"attempt_reserved", "attempt_started"}
        ]
        for reserved, started in zip(attempt_events[::2], attempt_events[1::2], strict=True):
            self.assertEqual(started["data"]["workspace_scope"], reserved["data"]["workspace_scope"])
            self.assertEqual(started["data"]["execution_profile"], reserved["data"]["execution_profile"])
            self.assertEqual(
                reserved["data"]["resolved_placement"],
                reserved["data"]["execution_profile"]["resolved_placement"],
            )
            self.assertEqual(reserved["data"]["external_refs"], {})
            self.assertIsInstance(started["data"]["external_refs"], dict)

    def test_audit_rejects_a_reported_attempt_and_retries_with_distinct_evidence(self) -> None:
        self.bootstrap_and_claim()
        dispatched = self.result(self.run_cli(
            "dispatch", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--task", "ROOT-01", "--local",
        ))
        attempt_id = dispatched["attempt_id"]
        report = {
            "task_id": "ROOT-01",
            "attempt_id": attempt_id,
            "outcome": "reported",
            "summary": "Reported the first implementation.",
            "files_changed": ["src/root.py"],
            "checks_run": ["python3 -m unittest tests.test_root"],
            "evidence_refs": [],
            "questions": [],
            "external_refs": {},
        }
        reported = self.result(self.run_cli(
            "record-result", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--attempt", attempt_id,
            "--result-json", json.dumps(report),
        ))
        checked = self.result(self.run_cli(
            "run-check", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--task", "ROOT-01",
        ))
        self.assertEqual(checked["check"]["attempt_id"], attempt_id)
        artifact = self.repository / checked["check"]["artifact"]
        self.assertTrue(artifact.is_file())
        artifact_payload = json.loads(artifact.read_text(encoding="utf-8"))
        self.assertEqual(artifact_payload["command_digest"], checked["check"]["command_digest"])
        self.assertEqual(
            artifact_payload["source_snapshot_digest"],
            checked["check"]["source_snapshot_digest"],
        )
        self.result(self.run_cli(
            "cleanup-register", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--cleanup-id", "cleanup-audit-01", "--kind", "other",
            "--target", "retained-resource", "--owner", attempt_id,
        ))
        finding_path = self.repository / "audit/findings.json"
        finding_path.parent.mkdir()
        finding_path.write_text(json.dumps({
            "schema_version": 1,
            "finding_id": "audit-retry",
            "classification": "acceptance_violation",
            "task_id": "ROOT-01",
            "attempt_id": attempt_id,
            "acceptance_reference": "ROOT-01 acceptance",
            "evidence_ref": "file:audit/findings.json",
            "affected": [{"file": "src/root.py", "identity": "root implementation"}],
            "reproduction": {
                "steps": ["Inspect the reported implementation."],
                "observed": "The acceptance is violated.",
                "expected": "The acceptance is satisfied.",
            },
            "smallest_repair_hypothesis": "Repair the acceptance violation.",
            "why_current_check_does_not_detect": "The focused Check does not inspect this invariant.",
        }) + "\n", encoding="utf-8")
        self.result(self.run_cli(
            "record-finding", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--finding", "audit/findings.json",
        ))
        rejection_arguments = (
            "--change", "portable", "--run-id", "run-1", "--generation", "2",
            "--attempt", attempt_id, "--rejection-id", "rejection-01",
            "--finding-ref", " file:audit/findings.json ",
            "--finding-ref", "file:audit/findings.json",
            "--hypothesis", "  Bind   each retry to its own check.  ",
        )
        events_path = self.repository / "openspec/runs/portable/run-1/events.jsonl"
        before_invalid = events_path.read_bytes()
        stale = self.run_cli(
            "audit-reject-attempt",
            *rejection_arguments[:5], "1", *rejection_arguments[6:],
        )
        self.assertNotEqual(stale.returncode, 0)
        self.assertEqual(json.loads(stale.stderr)["error"]["code"], "stale_coordinator")
        self.assertEqual(events_path.read_bytes(), before_invalid)
        for invalid_ref in (
            "file:../outside.json",
            "file:audit/missing.json",
            "commit:abc123",
        ):
            with self.subTest(invalid_ref=invalid_ref):
                invalid = self.run_cli(
                    "audit-reject-attempt", "--change", "portable", "--run-id", "run-1",
                    "--generation", "2", "--attempt", attempt_id,
                    "--rejection-id", "rejection-invalid", "--finding-ref", invalid_ref,
                    "--hypothesis", "Reject invalid evidence.",
                )
                self.assertNotEqual(invalid.returncode, 0)
                self.assertEqual(
                    json.loads(invalid.stderr)["error"]["code"], "audit_rejection_invalid"
                )
                self.assertEqual(events_path.read_bytes(), before_invalid)

        original_attempt = copy.deepcopy(reported["state"]["attempts"][attempt_id])
        first_result_path = self.repository / f"openspec/runs/portable/run-1/results/{attempt_id}.json"
        first_result_bytes = first_result_path.read_bytes()
        report_receipt = self.repository / original_attempt["report"]["receipt_path"]
        report_receipt_bytes = report_receipt.read_bytes()
        cleanup_pending = self.run_cli("audit-reject-attempt", *rejection_arguments)
        self.assertNotEqual(cleanup_pending.returncode, 0)
        self.assertEqual(
            json.loads(cleanup_pending.stderr)["error"]["code"], "cleanup_pending"
        )
        self.assertEqual(events_path.read_bytes(), before_invalid)
        self.result(self.run_cli(
            "cleanup-retain", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--cleanup-id", "cleanup-audit-01",
            "--receipt", '{"reason":"accepted for external ownership"}',
        ))
        rejected = self.result(self.run_cli("audit-reject-attempt", *rejection_arguments))
        attempt = rejected["state"]["attempts"][attempt_id]
        self.assertEqual(attempt["status"], "audit-rejected")
        self.assertEqual(
            attempt["audit_rejection"],
            {
                "rejection_id": "rejection-01",
                "finding_refs": ["file:audit/findings.json"],
                "hypothesis": "Bind each retry to its own check.",
            },
        )
        self.assertNotIn("task_id", attempt["audit_rejection"])
        self.assertNotIn("attempt_id", attempt["audit_rejection"])
        self.assertEqual(attempt["report"], original_attempt["report"])
        self.assertEqual(report_receipt.read_bytes(), report_receipt_bytes)
        self.assertIsNone(rejected["state"]["tasks"]["ROOT-01"]["check"])
        rejection_event = json.loads(events_path.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(rejection_event["type"], "attempt_audit_rejected")
        self.assertEqual(
            set(rejection_event["data"]),
            {"rejection_id", "task_id", "attempt_id", "finding_refs", "hypothesis"},
        )

        repeated = self.result(self.run_cli("audit-reject-attempt", *rejection_arguments))
        self.assertTrue(repeated["idempotent"])
        changed = self.run_cli(
            "audit-reject-attempt", *rejection_arguments[:-1],
            "A changed hypothesis conflicts.",
        )
        self.assertNotEqual(changed.returncode, 0)
        self.assertEqual(
            json.loads(changed.stderr)["error"]["code"], "audit_rejection_conflict"
        )
        different_id = self.run_cli(
            "audit-reject-attempt", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--attempt", attempt_id,
            "--rejection-id", "rejection-02", "--finding-ref", "file:audit/findings.json",
            "--hypothesis", "Another rejection conflicts.",
        )
        self.assertNotEqual(different_id.returncode, 0)
        self.assertEqual(
            json.loads(different_id.stderr)["error"]["code"], "audit_rejection_conflict"
        )

        retried = self.result(self.run_cli(
            "dispatch", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--task", "ROOT-01", "--attempt-id", "attempt-root-retry",
            "--local",
        ))
        second_report = {**report, "attempt_id": retried["attempt_id"], "summary": "Reported the repaired implementation."}
        self.result(self.run_cli(
            "record-result", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--attempt", retried["attempt_id"],
            "--result-json", json.dumps(second_report),
        ))
        retry_projection = json.loads(
            (self.repository / "openspec/runs/portable/run-1/state.json").read_text(encoding="utf-8")
        )
        self.assertEqual(first_result_path.read_bytes(), first_result_bytes)
        self.assertEqual(
            retry_projection["attempts"][attempt_id]["report"],
            original_attempt["report"],
        )
        premature_grade = self.run_cli(
            "grade", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--task", "ROOT-01", "--grade", "pass",
            "--note", "The old check cannot grade the retry.",
        )
        self.assertNotEqual(premature_grade.returncode, 0)
        self.assertEqual(
            json.loads(premature_grade.stderr)["error"]["code"], "evidence_required"
        )
        second_check = self.result(self.run_cli(
            "run-check", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--task", "ROOT-01",
        ))
        self.assertEqual(second_check["check"]["attempt_id"], "attempt-root-retry")
        second_artifact = self.repository / second_check["check"]["artifact"]
        self.assertTrue(second_artifact.is_file())
        self.assertNotEqual(second_artifact, artifact)
        self.assertNotEqual(
            second_check["check"]["source_snapshot_digest"],
            checked["check"]["source_snapshot_digest"],
        )
        graded = self.result(self.run_cli(
            "grade", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--task", "ROOT-01", "--grade", "pass",
            "--note", "The repaired attempt and its own check passed.",
        ))
        self.assertEqual(graded["state"]["tasks"]["ROOT-01"]["grade"], "pass")
        self.assertEqual(
            graded["state"]["attempts"][attempt_id]["check"]["artifact"],
            checked["check"]["artifact"],
        )

    def test_recovers_a_failed_check_before_grading_with_a_fresh_attempt(self) -> None:
        tasks = self.repository / "openspec/changes/portable/tasks.md"
        tasks.write_text(
            TASKS.replace("raise SystemExit(0)", "raise SystemExit(1)", 1),
            encoding="utf-8",
        )
        self.write_process_decision()
        self.bootstrap_and_claim()
        dispatched = self.result(self.run_cli(
            "dispatch", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--task", "ROOT-01", "--local",
        ))
        attempt_id = dispatched["attempt_id"]
        self.result(self.run_cli(
            "record-result", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--attempt", attempt_id,
            "--result-json", json.dumps({
                "task_id": "ROOT-01", "attempt_id": attempt_id, "outcome": "reported",
                "summary": "Reported the failed-check implementation.",
                "files_changed": ["src/root.py"], "checks_run": ["focused check"],
                "evidence_refs": [], "questions": [], "external_refs": {},
            }),
        ))
        failed_check = self.run_cli(
            "run-check", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--task", "ROOT-01",
        )
        self.assertNotEqual(failed_check.returncode, 0)
        self.assertEqual(json.loads(failed_check.stderr)["error"]["code"], "check_failed")

        self.result(self.run_cli(
            "cleanup-register", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--cleanup-id", "cleanup-failed-check", "--kind", "other",
            "--target", "retained-resource", "--owner", attempt_id,
        ))
        unsettled = self.run_cli(
            "record-repair", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--task", "ROOT-01",
            "--hypothesis", "Correct the focused failure before retrying.",
        )
        self.assertNotEqual(unsettled.returncode, 0)
        self.assertEqual(json.loads(unsettled.stderr)["error"]["code"], "cleanup_pending")
        self.result(self.run_cli(
            "cleanup-retain", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--cleanup-id", "cleanup-failed-check",
            "--receipt", '{"reason":"external owner accepted the resource"}',
        ))

        repaired = self.result(self.run_cli(
            "record-repair", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--task", "ROOT-01",
            "--hypothesis", "Correct the focused failure before retrying.",
        ))
        state = repaired["state"]
        self.assertEqual(state["attempts"][attempt_id]["status"], "check-rejected")
        self.assertEqual(state["attempts"][attempt_id]["check"]["status"], "failed")
        self.assertIsNone(state["tasks"]["ROOT-01"]["grade"])
        self.assertEqual(state["tasks"]["ROOT-01"]["status"], "pending")
        self.assertTrue(self.result(self.run_cli(
            "record-repair", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--task", "ROOT-01",
            "--hypothesis", "Correct the focused failure before retrying.",
        ))["idempotent"])
        retry = self.result(self.run_cli(
            "dispatch", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--task", "ROOT-01", "--local",
        ))
        self.assertNotEqual(retry["attempt_id"], attempt_id)
        events = (self.repository / "openspec/runs/portable/run-1/events.jsonl").read_text(encoding="utf-8")
        self.assertEqual(events.count('"type":"attempt_check_rejected"'), 1)

    def test_exhausts_repeated_or_third_audit_hypothesis_truthfully(self) -> None:
        self.bootstrap_and_claim()
        # Two technical reports may not open a third writer implicitly.  Only
        # one explicit, idempotent coordinator amendment authorizes it.
        finding_one = self.repository / "audit/finding-one.json"
        finding_two = self.repository / "audit/finding-two.json"
        finding_one.parent.mkdir()

        def report_and_check(attempt_id: str) -> None:
            self.result(self.run_cli(
                "record-result", "--change", "portable", "--run-id", "run-1",
                "--generation", "2", "--attempt", attempt_id,
                "--result-json", json.dumps({
                    "task_id": "ROOT-01", "attempt_id": attempt_id, "outcome": "reported",
                    "summary": "Reported an audited implementation.",
                    "files_changed": ["src/root.py"], "checks_run": ["focused check"],
                    "evidence_refs": [], "questions": [], "external_refs": {},
                }),
            ))
            self.result(self.run_cli(
                "run-check", "--change", "portable", "--run-id", "run-1",
                "--generation", "2", "--task", "ROOT-01",
            ))

        first = self.result(self.run_cli(
            "dispatch", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--task", "ROOT-01", "--local",
        ))["attempt_id"]
        report_and_check(first)
        finding_one.write_text(json.dumps({
            "schema_version": 1, "finding_id": "finding-one", "classification": "acceptance_violation",
            "task_id": "ROOT-01", "attempt_id": first, "acceptance_reference": "task#/acceptance",
            "affected": [{"file": "src/root.py", "identity": "root"}],
            "reproduction": {"steps": ["run check"], "observed": "bad", "expected": "good"},
            "smallest_repair_hypothesis": "repair one", "why_current_check_does_not_detect": "scope",
        }), encoding="utf-8")
        self.result(self.run_cli("record-finding", "--change", "portable", "--run-id", "run-1", "--generation", "2", "--finding", str(finding_one.relative_to(self.repository))))
        self.result(self.run_cli(
            "audit-reject-attempt", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--attempt", first, "--rejection-id", "audit-one",
            "--finding-ref", "file:audit/finding-one.json", "--hypothesis", "Inspect the first audit finding.",
        ))
        second = self.result(self.run_cli(
            "dispatch", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--task", "ROOT-01", "--local",
        ))["attempt_id"]
        report_and_check(second)
        fenced = self.run_cli(
            "dispatch", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--task", "ROOT-01", "--local",
        )
        self.assertNotEqual(fenced.returncode, 0)
        self.result(self.run_cli("record-decision", "--change", "portable", "--run-id", "run-1", "--generation", "2", "--task", "ROOT-01", "--decision-id", "amend-one", "--action", "amend_acceptance", "--note", "Authorize one bounded repair."))
        third = self.result(self.run_cli(
            "dispatch", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--task", "ROOT-01", "--local",
        ))["attempt_id"]
        self.assertNotEqual(self.run_cli(
            "dispatch", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--task", "ROOT-01", "--local",
        ).returncode, 0)

    def test_replays_an_identical_result_idempotently(self) -> None:
        self.bootstrap_and_claim()
        dispatched = self.result(
            self.run_cli(
                "dispatch", "--change", "portable", "--run-id", "run-1",
                "--generation", "2", "--task", "ROOT-01", "--local",
            )
        )
        report = {
            "task_id": "ROOT-01",
            "attempt_id": dispatched["attempt_id"],
            "outcome": "reported",
            "summary": "Reported root.",
            "files_changed": ["src/root.py"],
            "checks_run": ["python3 -m unittest tests.test_root"],
            "evidence_refs": [],
            "questions": [],
            "external_refs": {},
        }
        arguments = (
            "--change", "portable", "--run-id", "run-1", "--generation", "2",
            "--attempt", dispatched["attempt_id"], "--result-json", json.dumps(report),
        )
        self.result(self.run_cli("record-result", *arguments))
        repeated = self.result(self.run_cli("record-result", *arguments))
        self.assertTrue(repeated["idempotent"])

    def test_preserves_the_accepted_result_when_a_later_report_differs(self) -> None:
        self.bootstrap_and_claim()
        dispatched = self.result(
            self.run_cli(
                "dispatch", "--change", "portable", "--run-id", "run-1",
                "--generation", "2", "--task", "ROOT-01", "--local",
            )
        )
        attempt_id = dispatched["attempt_id"]
        accepted = {
            "task_id": "ROOT-01",
            "attempt_id": attempt_id,
            "outcome": "reported",
            "summary": "Accepted root result.",
            "files_changed": ["src/root.py"],
            "checks_run": ["python3 -m unittest tests.test_root"],
            "evidence_refs": [],
            "questions": [],
            "external_refs": {},
        }
        self.result(self.run_cli(
            "record-result", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--attempt", attempt_id,
            "--result-json", json.dumps(accepted),
        ))
        result_path = self.repository / f"openspec/runs/portable/run-1/results/{attempt_id}.json"
        accepted_bytes = result_path.read_bytes()
        state_path = self.repository / "openspec/runs/portable/run-1/state.json"
        accepted_report = copy.deepcopy(
            json.loads(state_path.read_text(encoding="utf-8"))["attempts"][attempt_id]["report"]
        )

        conflicting = {**accepted, "summary": "Later conflicting result."}
        rejected = self.run_cli(
            "record-result", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--attempt", attempt_id,
            "--result-json", json.dumps(conflicting),
        )

        self.assertNotEqual(rejected.returncode, 0)
        self.assertEqual(result_path.read_bytes(), accepted_bytes)
        projection = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(projection["attempts"][attempt_id]["report"], accepted_report)

    def test_freezes_an_amended_scope_only_when_the_reserved_attempt_launches(self) -> None:
        self.bootstrap_and_claim()
        reserved = self.result(self.run_cli(
            "dispatch", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--task", "ROOT-01", "--local", "--defer-launch",
        ))
        attempt_id = reserved["attempt_id"]
        amended = self.result(self.run_cli(
            "amend-graph", "--change", "portable", "--run-id", "run-1", "--generation", "2",
            "--amendment-id", "amend-root-extra", "--parent-task", "ROOT-01",
            "--parent-attempt", attempt_id, "--path", "src/extra.py",
            "--reason", "The implementation requires its adjacent generated file.",
        ))
        scope = amended["state"]["attempts"][attempt_id]["effective_scope"]
        self.assertEqual(scope["paths"], ["src/root.py", "src/extra.py"])
        self.assertEqual(scope["amendment_ids"], ["amend-root-extra"])

        launched = self.result(self.run_cli(
            "recover-attempt", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--attempt", attempt_id,
        ))
        capsule_path = self.repository / launched["receipt"]["external_refs"]["capsule_path"]
        capsule = json.loads(capsule_path.read_text(encoding="utf-8"))
        self.assertEqual(capsule["effective_scope"], scope)
        before = self.run_directory_snapshot("run-1")
        late = self.run_cli(
            "amend-graph", "--change", "portable", "--run-id", "run-1", "--generation", "2",
            "--amendment-id", "amend-root-late", "--parent-task", "ROOT-01",
            "--parent-attempt", attempt_id, "--path", "src/late.py",
            "--reason", "This amendment is too late.",
        )
        self.assertNotEqual(late.returncode, 0)
        self.assertEqual(json.loads(late.stderr)["error"]["code"], "invalid_graph")
        self.assertEqual(self.run_directory_snapshot("run-1"), before)

    def test_rejects_shell_operators_before_execution(self) -> None:
        tasks = self.repository / "openspec/changes/portable/tasks.md"
        tasks.write_text(TASKS.replace(
            f'"{sys.executable}" -c "raise SystemExit(0)"',
            f'"{sys.executable}" -c "raise SystemExit(0)" && "{sys.executable}" -V',
            1,
        ), encoding="utf-8")
        self.write_process_decision(allow_unsafe_checks=True)
        rejected = self.run_cli(
            "bootstrap", "--change", "portable", "--run-id", "shell-boundary",
            "--bootstrap-id", "bootstrap-shell-boundary", "--driver", "host",
        )

        self.assertNotEqual(rejected.returncode, 0)
        error = json.loads(rejected.stderr)["error"]
        self.assertEqual(error["code"], "process_decision_invalid")
        self.assertEqual(error["field_path"], "decision.selected_check.command")
        self.assertIn("shell operator", error["message"])
        self.assertFalse(
            (self.repository / "openspec/runs/portable/shell-boundary").exists()
        )

    def test_imports_checked_tasks_atomically_with_safe_source_checks(self) -> None:
        tasks_path = self.repository / "openspec/changes/portable/tasks.md"
        checked_tasks = TASKS.replace("- [ ]", "- [x]")
        tasks_path.write_text(checked_tasks, encoding="utf-8")
        self.write_process_decision()
        bootstrap = self.result(self.run_cli(
            "bootstrap", "--change", "portable", "--run-id", "run-checked",
            "--bootstrap-id", "bootstrap-checked", "--driver", "host",
        ))
        self.result(self.run_cli(
            "claim-coordinator", "--capsule", bootstrap["capsule_path"],
            "--coordinator-id", "coordinator-checked",
        ))
        run_directory = self.repository / "openspec/runs/portable/run-checked"
        graph = runtime.parse_task_graph(tasks_path)

        stale = self.run_cli(
            "import-checked-task", "--change", "portable", "--run-id", "run-checked",
            "--generation", "1", "--task", "ROOT-01", "--import-id", "import-root-01",
            "--note", "Import the verified source task.",
        )
        self.assertNotEqual(stale.returncode, 0)
        self.assertEqual(json.loads(stale.stderr)["error"]["code"], "stale_coordinator")

        imported = self.result(self.run_cli(
            "import-checked-task", "--change", "portable", "--run-id", "run-checked",
            "--generation", "2", "--task", "ROOT-01", "--import-id", "import-root-01",
            "--note", "Import the verified source task.",
        ))
        self.assertEqual(imported["grade"], "pass")
        self.assertEqual(imported["check"]["command"], graph.by_id()["ROOT-01"].check)
        self.assertEqual(imported["check"]["status"], "passed")
        graded = self.result(self.run_cli(
            "grade", "--change", "portable", "--run-id", "run-checked",
            "--generation", "2", "--task", "ROOT-01", "--grade", "pass",
            "--note", "The checked import remains independently gradable.",
        ))
        self.assertTrue(graded["idempotent"])

        self.assertTrue((run_directory / "state.json").is_file())

    def test_blocks_pass_with_ungraded_tasks_and_pending_cleanup(self) -> None:
        bootstrap, _ = self.bootstrap_and_claim()
        workspace = bootstrap["state"]["workspace_scope"]["execution_workspace"]
        self.result(
            self.run_cli(
                "cleanup-register", "--change", "portable", "--run-id", "run-1",
                "--generation", "2", "--kind", "process",
                "--target", json.dumps({"kind": "process", "root_pid": 99999999}),
                "--owner", json.dumps({
                    "execution_host_id": workspace["execution_host_id"],
                    "workspace_key": workspace["workspace_key"],
                    "coordinator_generation": 2,
                    "terminal_id": None,
                    "incarnation_id": None,
                    "process_root": 99999999,
                    "provenance": "test cleanup registration",
                }),
            )
        )
        blocked = self.run_cli(
            "complete", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--outcome", "pass",
        )
        self.assertNotEqual(blocked.returncode, 0)
        self.assertEqual(json.loads(blocked.stderr)["error"]["code"], "cleanup_pending")

    def test_blocks_completion_when_attempt_cleanup_registration_was_interrupted(self) -> None:
        self.bootstrap_and_claim()
        directory = self.repository / "openspec/runs/portable/run-1"
        journal = runtime._journal(directory)
        projection = journal.verify_projection()
        scope = projection["workspace_scope"]
        profile = runtime._execution_profile_for_task(
            runtime._task_from_state(projection, "ROOT-01"), scope
        )
        owner = {
            "execution_host_id": scope["execution_workspace"]["execution_host_id"],
            "workspace_key": scope["execution_workspace"]["workspace_key"],
            "attempt_id": "attempt-1",
            "terminal_id": "terminal-1",
            "incarnation_id": "incarnation-1",
            "process_root": None,
            "provenance": "test receipt",
        }
        before = ((directory / "events.jsonl").read_bytes(), (directory / "state.json").read_bytes())
        with self.assertRaises(runtime.JournalError):
            journal.append(
                "attempt_started",
                {
                    "task_id": "ROOT-01",
                    "attempt_id": "attempt-1",
                    "driver": "orca",
                    "cleanup_id": "cleanup-attempt-1",
                    "execution_profile": profile,
                    "resource_owner": owner,
                },
                coordinator_generation=2,
            )
        self.assertEqual(before, ((directory / "events.jsonl").read_bytes(), (directory / "state.json").read_bytes()))
        self.assertNotIn("attempt-1", journal.verify_projection()["attempts"])

    def test_status_watch_reads_saved_projection(self) -> None:
        self.bootstrap_and_claim()
        completed = self.run_cli(
            "status", "--change", "portable", "--run-id", "run-1",
            "--watch", "--iterations", "1", "--interval", "0",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        status = json.loads(completed.stdout)
        self.assertEqual(status["kind"], "snapshot")
        status = status["state"]
        self.assertIn("ROOT-01", {task["task_id"] for task in status["tasks"]})
        self.assertNotIn("transcript", json.dumps(status).casefold())

    def test_resume_rebuilds_a_stale_saved_projection_from_the_journal(self) -> None:
        self.bootstrap_and_claim()
        state_path = self.repository / "openspec/runs/portable/run-1/state.json"
        state_path.write_text("{}\n", encoding="utf-8")

        resumed = self.result(
            self.run_cli(
                "resume", "--change", "portable", "--run-id", "run-1", "--generation", "2"
            )
        )

        rebuilt = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(resumed["coordinator"]["generation"], 2)
        self.assertEqual(rebuilt["last_sequence"], 5)

    def test_abandons_a_lost_attempt_before_retrying_it(self) -> None:
        self.bootstrap_and_claim()
        dispatched = self.result(
            self.run_cli(
                "dispatch", "--change", "portable", "--run-id", "run-1",
                "--generation", "2", "--task", "ROOT-01", "--local",
            )
        )
        blocked = self.result(self.run_cli("ready", "--change", "portable", "--run-id", "run-1"))
        self.assertNotIn("ROOT-01", {task["id"] for task in blocked["ready"]})

        abandoned = self.result(
            self.run_cli(
                "abandon-attempt", "--change", "portable", "--run-id", "run-1",
                "--generation", "2", "--attempt", dispatched["attempt_id"],
                "--reason", "The local worker disappeared before reporting.",
            )
        )

        self.assertEqual(abandoned["state"]["attempts"][dispatched["attempt_id"]]["status"], "abandoned")
        ready = self.result(self.run_cli("ready", "--change", "portable", "--run-id", "run-1"))
        self.assertIn("ROOT-01", {task["id"] for task in ready["ready"]})

    def test_reduction_releases_two_surplus_owners_and_retains_one_writer(self) -> None:
        tasks_path = self.repository / "openspec/changes/portable/tasks.md"
        tasks_path.write_text(
            TASKS
            + f'''\n- [ ] THIRD-03 Build the independent task
  Depends: []
  Paths: [src/third.py]
  Mode: write
  Isolation: auto
  Acceptance: The third task is reported and verified.
  Check: "{sys.executable}" -c "raise SystemExit(0)"
''',
            encoding="utf-8",
        )
        self.write_process_decision()
        graph = runtime.parse_task_graph(tasks_path)
        directory = runtime._new_run_directory(self.repository, "portable", "reduction-1")
        journal = runtime._journal(directory)
        scope = runtime._persist_workspace_scope(
            self.repository,
            directory,
            runtime._automatic_host_workspace_receipt(self.repository, "reduction-1"),
            run_id="reduction-1",
            coordinator_generation=1,
        )
        decision = json.loads(
            (self.repository / "openspec/changes/portable/process-decision.json").read_text(encoding="utf-8")
        )
        journal.append(
            "run_started",
            {
                "change": "portable",
                "run_id": "reduction-1",
                "coordinator_id": "coordinator-1",
                "coordinator_generation": 1,
                "base_commit": runtime._current_commit(self.repository),
                "dirty_paths": [],
                "workspace_scope": scope,
                "process_decision": decision["decision"],
                "graph_contract": decision["graph_contract"],
                "tasks": [task.to_dict() for task in graph.tasks],
            },
            coordinator_generation=1,
        )
        journal.append("driver_selected", {"driver": "orca"}, coordinator_generation=1)
        profiles = {task.id: runtime._execution_profile_for_task(task, scope) for task in graph.tasks}
        workspace = scope["execution_workspace"]
        active = (("ROOT-01", "attempt-root"), ("NEXT-02", "attempt-next"), ("THIRD-03", "attempt-third"))
        refs = {
            attempt_id: {
                "tier": "supervised",
                "runtime_id": "runtime-reduction",
                "worktree_id": "worktree-reduction",
                "run_id": "run-reduction",
                "task_id": f"external-{task_id}",
                "dispatch_id": f"dispatch-{task_id}",
            }
            for task_id, attempt_id in active
        }
        for task_id, attempt_id in active:
            journal.append("task_ready", {"task_id": task_id}, coordinator_generation=1)
            projection = journal.append(
                "attempt_reserved",
                {
                    "task_id": task_id,
                    "attempt_id": attempt_id,
                    "driver": "orca",
                    "workspace_scope": scope,
                    "execution_profile": profiles[task_id],
                    "resolved_placement": profiles[task_id]["resolved_placement"],
                    "external_refs": {},
                },
                coordinator_generation=1,
            )
            effective_scope = projection["attempts"][attempt_id]["effective_scope"]
            journal.append(
                "attempt_scope_frozen",
                {"attempt_id": attempt_id, "effective_scope": effective_scope},
                coordinator_generation=1,
            )
            owner = {
                "execution_host_id": workspace["execution_host_id"],
                "workspace_key": workspace["workspace_key"],
                "attempt_id": attempt_id,
                "terminal_id": None,
                "incarnation_id": None,
                "process_root": None,
                "provenance": (
                    "orca-supervised:runtime-reduction:worktree-reduction:run-reduction:"
                    + refs[attempt_id]["dispatch_id"]
                ),
            }
            journal.append(
                "attempt_started",
                {
                    "task_id": task_id,
                    "attempt_id": attempt_id,
                    "driver": "orca",
                    "tier": "supervised",
                    "external_refs": refs[attempt_id],
                    "cleanup_id": f"cleanup-{attempt_id}",
                    "workspace_scope": scope,
                    "execution_profile": profiles[task_id],
                    "effective_scope": effective_scope,
                    "resource_owner": owner,
                    "cleanup_registration": {
                        "cleanup_id": f"cleanup-{attempt_id}",
                        "kind": "other",
                        "target": refs[attempt_id]["dispatch_id"],
                        "owner": owner,
                        "external_refs": refs[attempt_id],
                    },
                },
                coordinator_generation=1,
            )

        class FakeReductionOrca(runtime.OrcaDriver):
            def __init__(self) -> None:
                self.runtime_id = "runtime-reduction"
                self.run_id = "run-reduction"
                self.released: list[str] = []

            def release(self, attempt):
                self.released.append(attempt["attempt_id"])
                return runtime.DriverReceipt(
                    "release",
                    "released",
                    external_refs=refs[attempt["attempt_id"]],
                    raw={"state": "released"},
                )

        amended = amend_process_decision(
            decision["decision"],
            amendment_id="reduce-active-workers",
            changed_evidence=["Two owners are now surplus to the retained writer."],
            reason="Reduce the active session to one retained writer.",
            mode="verified_single",
            replacement_check=decision["decision"]["selected_check"],
        )
        amended_path = self.repository / "amended-decision.json"
        amended_path.write_text(json.dumps({"decision": amended}), encoding="utf-8")
        fake = FakeReductionOrca()
        original = runtime._driver_for_state
        runtime._driver_for_state = lambda *args: fake
        try:
            result = runtime.command_amend_decision(
                argparse.Namespace(
                    repo=self.repository,
                    change="portable",
                    run_id="reduction-1",
                    generation=1,
                    decision=amended_path.name,
                    reduction_json=json.dumps(
                        {
                            "integrator": "coordinator-1",
                            "reason": "Only ROOT-01 remains active.",
                            "cleanup_plan": "Release surplus provider owners through their receipts.",
                            "retained_task_ids": ["ROOT-01"],
                        }
                    ),
                )
            )
        finally:
            runtime._driver_for_state = original

        self.assertEqual(fake.released, ["attempt-next", "attempt-third"])
        self.assertEqual(
            [item["attempt_id"] for item in result["cleanup"]["released"]],
            ["attempt-next", "attempt-third"],
        )
        state = result["state"]
        self.assertEqual(state["attempts"]["attempt-root"]["status"], "running")
        for attempt_id in ("attempt-next", "attempt-third"):
            self.assertEqual(state["attempts"][attempt_id]["status"], "abandoned")
            self.assertEqual(state["cleanup"][f"cleanup-{attempt_id}"]["status"], "verified")
        self.assertTrue(all(task["grade"] is None for task in state["tasks"].values()))

    def test_blocks_frontend_completion_when_the_graph_omits_visuals(self) -> None:
        tasks = self.repository / "openspec/changes/portable/tasks.md"
        tasks.write_text(TASKS.replace("src/root.py", "src/App.tsx"), encoding="utf-8")
        self.write_process_decision()
        self.bootstrap_and_claim()
        dispatched = self.result(
            self.run_cli(
                "dispatch", "--change", "portable", "--run-id", "run-1",
                "--generation", "2", "--task", "ROOT-01", "--local",
            )
        )
        report = {
            "task_id": "ROOT-01",
            "attempt_id": dispatched["attempt_id"],
            "outcome": "reported",
            "summary": "Reported the frontend change.",
            "files_changed": ["src/App.tsx"],
            "checks_run": ["python3 -m unittest tests.test_root"],
            "evidence_refs": [],
            "questions": [],
            "external_refs": {},
        }
        self.result(
            self.run_cli(
                "record-result", "--change", "portable", "--run-id", "run-1",
                "--generation", "2", "--attempt", dispatched["attempt_id"],
                "--result-json", json.dumps(report),
            )
        )
        self.result(
            self.run_cli(
                "run-check", "--change", "portable", "--run-id", "run-1",
                "--generation", "2", "--task", "ROOT-01",
            )
        )
        self.result(
            self.run_cli(
                "grade", "--change", "portable", "--run-id", "run-1",
                "--generation", "2", "--task", "ROOT-01", "--grade", "pass",
                "--note", "The nonvisual check passed.",
            )
        )
        next_attempt = self.result(
            self.run_cli(
                "dispatch", "--change", "portable", "--run-id", "run-1",
                "--generation", "2", "--task", "NEXT-02", "--local",
            )
        )
        self.result(
            self.run_cli(
                "record-result", "--change", "portable", "--run-id", "run-1",
                "--generation", "2", "--attempt", next_attempt["attempt_id"],
                "--result-json", json.dumps(
                    {
                        "task_id": "NEXT-02",
                        "attempt_id": next_attempt["attempt_id"],
                        "outcome": "reported",
                        "summary": "Verified the non-frontend dependency.",
                        "files_changed": [],
                        "checks_run": [f'"{sys.executable}" -c "raise SystemExit(0)"'],
                        "evidence_refs": [],
                        "questions": [],
                        "external_refs": {},
                    }
                ),
            )
        )
        self.result(
            self.run_cli(
                "run-check", "--change", "portable", "--run-id", "run-1",
                "--generation", "2", "--task", "NEXT-02",
            )
        )
        self.result(
            self.run_cli(
                "grade", "--change", "portable", "--run-id", "run-1",
                "--generation", "2", "--task", "NEXT-02", "--grade", "pass",
                "--note", "The non-frontend dependency check passed.",
            )
        )
        source = self.repository / "src/App.tsx"
        source.parent.mkdir(exist_ok=True)
        source.write_text("export const App = () => <main>Changed</main>;\n", encoding="utf-8")

        pass_result = self.run_cli(
            "complete", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--outcome", "pass",
        )
        self.assertNotEqual(pass_result.returncode, 0)
        self.assertIn("frontend changes require Visual entries", pass_result.stderr)

    def test_sync_passes_persisted_context_to_orca_probe_and_cleanup(self) -> None:
        graph = runtime.parse_task_graph(self.repository / "openspec/changes/portable/tasks.md")
        directory = runtime._new_run_directory(self.repository, "portable", "live-1")
        journal = runtime._journal(directory)
        scope = runtime._persist_workspace_scope(
            self.repository, directory, runtime._automatic_host_workspace_receipt(self.repository, "live-1"),
            run_id="live-1", coordinator_generation=1,
        )
        profiles = {task.id: runtime._execution_profile_for_task(task, scope) for task in graph.tasks}
        workspace = scope["execution_workspace"]
        refs = {
            attempt_id: {
                "tier": "supervised", "runtime_id": "runtime-live", "worktree_id": "worktree-live",
                "run_id": "run-live", "task_id": "task-live" if attempt_id == "attempt-1" else "task-next",
                "dispatch_id": "ctx-live" if attempt_id == "attempt-1" else "ctx-next",
            }
            for attempt_id in ("attempt-1", "attempt-2")
        }
        owners = {
            attempt_id: {
                "execution_host_id": workspace["execution_host_id"], "workspace_key": workspace["workspace_key"],
                "attempt_id": attempt_id, "terminal_id": None, "incarnation_id": None, "process_root": None,
                "provenance": f"orca-supervised:runtime-live:worktree-live:run-live:{refs[attempt_id]['dispatch_id']}",
            }
            for attempt_id in ("attempt-1", "attempt-2")
        }
        projection = journal.append(
            "run_started",
            {
                "change": "portable",
                "run_id": "live-1",
                "coordinator_id": "coordinator-1",
                "coordinator_generation": 1,
                "base_commit": runtime._current_commit(self.repository),
                "dirty_paths": [],
                "workspace_scope": scope,
                "tasks": [task.to_dict() for task in graph.tasks],
            },
            coordinator_generation=1,
        )
        projection = journal.append(
            "driver_selected",
            {"driver": "orca"},
            coordinator_generation=1,
        )
        projection = journal.append("task_ready", {"task_id": "ROOT-01"}, coordinator_generation=1)
        projection = journal.append(
            "attempt_reserved",
            {"task_id": "ROOT-01", "attempt_id": "attempt-1", "driver": "orca", "workspace_scope": scope, "execution_profile": profiles["ROOT-01"], "resolved_placement": profiles["ROOT-01"]["resolved_placement"], "external_refs": {}},
            coordinator_generation=1,
        )
        effective_scope = projection["attempts"]["attempt-1"]["effective_scope"]
        projection = journal.append(
            "attempt_scope_frozen",
            {"attempt_id": "attempt-1", "effective_scope": effective_scope},
            coordinator_generation=1,
        )
        projection = journal.append(
            "attempt_started",
            {
                "task_id": "ROOT-01",
                "attempt_id": "attempt-1",
                "driver": "orca",
                "tier": "supervised",
                "external_refs": refs["attempt-1"],
                "cleanup_id": "cleanup-attempt-1",
                "workspace_scope": scope,
                "execution_profile": profiles["ROOT-01"],
                "effective_scope": effective_scope,
                "resource_owner": owners["attempt-1"],
                "cleanup_registration": {
                    "cleanup_id": "cleanup-attempt-1", "kind": "other", "target": "ctx-live",
                    "owner": owners["attempt-1"], "external_refs": refs["attempt-1"],
                },
            },
            coordinator_generation=1,
        )
        journal.append("task_ready", {"task_id": "NEXT-02"}, coordinator_generation=1)
        projection = journal.append(
            "attempt_reserved",
            {"task_id": "NEXT-02", "attempt_id": "attempt-2", "driver": "orca", "workspace_scope": scope, "execution_profile": profiles["NEXT-02"], "resolved_placement": profiles["NEXT-02"]["resolved_placement"], "external_refs": {}},
            coordinator_generation=1,
        )
        effective_scope = projection["attempts"]["attempt-2"]["effective_scope"]
        journal.append(
            "attempt_scope_frozen",
            {"attempt_id": "attempt-2", "effective_scope": effective_scope},
            coordinator_generation=1,
        )
        journal.append(
            "attempt_started",
            {
                "task_id": "NEXT-02",
                "attempt_id": "attempt-2",
                "driver": "orca",
                "tier": "supervised",
                "external_refs": refs["attempt-2"],
                "cleanup_id": "cleanup-attempt-2",
                "workspace_scope": scope,
                "execution_profile": profiles["NEXT-02"],
                "effective_scope": effective_scope,
                "resource_owner": owners["attempt-2"],
                "cleanup_registration": {
                    "cleanup_id": "cleanup-attempt-2", "kind": "other", "target": "ctx-next",
                    "owner": owners["attempt-2"], "external_refs": refs["attempt-2"],
                },
            },
            coordinator_generation=1,
        )

        class FakeLiveOrca(runtime.OrcaDriver):
            def __init__(self):
                self.actions = []
                self.context_calls = []
                self.run_id = "run-live"
                self.runtime_id = "runtime-live"
                self.worktree_id = "worktree-live"
                self.release_fails = True

            def poll(self, attempt, *, cursor=None, include_delivery=True):
                self.context_calls.append(("poll", copy.deepcopy(attempt)))
                return runtime.DriverReceipt(
                    "poll",
                    "observed",
                    external_refs={"cursor": "cursor-2"},
                    raw={"show": {}, "read": {}, "delivery": None},
                )

            def check_delivery(self, run_id):
                return {
                    "ok": True,
                    "result": {
                        "deliveryId": "delivery-1",
                        "messages": [
                            {
                                "id": "message-1",
                                "type": "worker_done",
                                "subject": "Dependent complete",
                                "body": "The dependent read completed.",
                                "payload": json.dumps(
                                    {
                                        "taskId": "task-next",
                                        "dispatchId": "ctx-next",
                                        "outcome": "succeeded",
                                        "checksRun": ["python3 -m unittest tests.test_next"],
                                    }
                                ),
                            }
                        ],
                    },
                }

            def release(self, attempt):
                self.actions.append("release")
                self.context_calls.append(("release", copy.deepcopy(attempt)))
                if self.release_fails:
                    self.release_fails = False
                    raise runtime.DriverError(
                        "release interrupted", code="connection_lost"
                    )
                attempt_id = attempt["attempt_id"]
                dispatch_id = "ctx-live" if attempt_id == "attempt-1" else "ctx-next"
                return runtime.DriverReceipt(
                    "release", "released",
                    external_refs={
                        "tier": "supervised", "dispatch_id": dispatch_id,
                    },
                    raw={"state": "released"},
                )

            def ack_delivery(self, run_id, delivery_id):
                self.actions.append("ack")
                return {"ok": True, "result": {"deliveryId": delivery_id}}

        fake = FakeLiveOrca()
        original = runtime._driver_for_state
        runtime._driver_for_state = lambda *args: fake
        try:
            arguments = argparse.Namespace(
                repo=self.repository,
                change="portable",
                run_id="live-1",
                generation=1,
            )
            runtime.command_sync(arguments)
            after_failure = runtime._projection(directory)
            self.assertEqual(
                after_failure["attempts"]["attempt-2"]["status"], "reported"
            )
            self.assertEqual(
                after_failure["cleanup"]["cleanup-attempt-2"]["status"], "unverifiable"
            )
            task = runtime._task_from_state(after_failure, "NEXT-02")
            journal.verify_projection()
            with self.assertRaisesRegex(
                runtime.AgentGraphCliError, "driver-owned"
            ) as bypass:
                runtime.command_cleanup_finish(
                    argparse.Namespace(
                        **vars(arguments),
                        cleanup_id="cleanup-attempt-2",
                        target=None,
                        receipt='{"claimed": "released"}',
                    )
                )
            self.assertEqual(
                bypass.exception.code, "driver_cleanup_requires_recovery"
            )
            recovered = runtime.command_recover_cleanup(
                argparse.Namespace(**vars(arguments), attempt="attempt-2")
            )
            journal.verify_projection()
            journal.append(
                "check_recorded",
                {
                    "task_id": "NEXT-02",
                    "attempt_id": "attempt-2",
                    "command": task.check,
                    "status": "passed",
                    "exit_code": 0,
                    "duration_ms": 1,
                    "attempts": 1,
                    "total_duration_ms": 1,
                    "artifact": "artifacts/checks/NEXT-02-001.json",
                },
                coordinator_generation=1,
            )
            journal.append(
                "finding_recorded",
                {
                    "schema_version": 1,
                    "finding_id": "finding-next-02",
                    "classification": "acceptance_violation",
                    "task_id": "NEXT-02",
                    "attempt_id": "attempt-2",
                    "acceptance_reference": "NEXT-02 acceptance",
                    "evidence_ref": "file:artifacts/audit/NEXT-02.json",
                    "affected": [{"file": "src/next.py", "identity": "next implementation"}],
                    "reproduction": {
                        "steps": ["Inspect the reported implementation."],
                        "observed": "The acceptance is violated.",
                        "expected": "The acceptance is satisfied.",
                    },
                    "smallest_repair_hypothesis": "Recover cleanup after audit rejection.",
                    "why_current_check_does_not_detect": "The focused Check does not inspect cleanup recovery.",
                },
                coordinator_generation=1,
            )
            journal.append(
                "attempt_audit_rejected",
                {
                    "rejection_id": "rejection-next-02",
                    "task_id": "NEXT-02",
                    "attempt_id": "attempt-2",
                    "finding_refs": ["file:artifacts/audit/NEXT-02.json"],
                    "hypothesis": "Recover cleanup after audit rejection.",
                },
                coordinator_generation=1,
            )
            result = runtime.command_sync(arguments)
        finally:
            runtime._driver_for_state = original

        self.assertEqual(result["state"]["tasks"]["ROOT-01"]["status"], "running")
        self.assertEqual(result["state"]["tasks"]["NEXT-02"]["status"], "pending")
        self.assertEqual(
            result["state"]["attempts"]["attempt-2"]["status"], "audit-rejected"
        )
        self.assertEqual(result["state"]["attempts"]["attempt-1"]["cursor"], "cursor-2")
        self.assertEqual(result["state"]["attempts"]["attempt-2"]["cursor"], "cursor-2")
        self.assertEqual(result["state"]["cleanup"]["cleanup-attempt-1"]["status"], "pending")
        self.assertEqual(result["state"]["cleanup"]["cleanup-attempt-2"]["status"], "verified")
        self.assertTrue(recovered["finished"])
        self.assertFalse(recovered["idempotent"])
        self.assertEqual(fake.actions, ["release", "ack", "release", "ack"])
        for operation, attempt in fake.context_calls:
            with self.subTest(operation=operation, attempt_id=attempt["attempt_id"]):
                profile = profiles[attempt["task_id"]]
                self.assertEqual(attempt["workspace_scope"], scope)
                self.assertEqual(attempt["execution_profile"], profile)
                self.assertEqual(attempt["resolved_placement"], profile["resolved_placement"])
                self.assertEqual(attempt["external_refs"], refs[attempt["attempt_id"]])

    def test_dispatch_recovery_and_resume_pass_exact_persisted_context(self) -> None:
        self.bootstrap_and_claim()

        class FakeDriver:
            def __init__(self) -> None:
                self.calls: list[tuple[str, object]] = []

            def start_attempt(self, attempt):
                self.calls.append(("start_attempt", copy.deepcopy(attempt)))
                return runtime.DriverReceipt(
                    "start_attempt",
                    "started",
                    external_refs={"worker_handle": f"worker-{attempt['attempt_id']}"},
                )

            def reconcile(self, attempts):
                self.calls.append(("reconcile", copy.deepcopy(list(attempts))))
                return runtime.DriverReceipt("reconcile", "observed", raw=[])

        fake = FakeDriver()
        original = runtime._driver_for_state
        runtime._driver_for_state = lambda *args: fake
        dispatch_arguments = argparse.Namespace(
            repo=self.repository,
            change="portable",
            run_id="run-1",
            generation=2,
            task="ROOT-01",
            attempt_id=None,
            worker=None,
            local=True,
            route_input=None,
            defer_launch=False,
        )
        try:
            dispatched = runtime.command_dispatch(dispatch_arguments)
        finally:
            runtime._driver_for_state = original

        dispatched_attempt = dispatched["state"]["attempts"][dispatched["attempt_id"]]
        start_calls = [call for call in fake.calls if call[0] == "start_attempt"]
        self.assertEqual(len(start_calls), 1)
        start_attempt = start_calls[0][1]
        self.assertEqual(start_attempt["workspace_scope"], dispatched_attempt["workspace_scope"])
        self.assertEqual(start_attempt["execution_profile"], dispatched_attempt["execution_profile"])
        self.assertEqual(start_attempt["resolved_placement"], dispatched_attempt["resolved_placement"])
        self.assertEqual(start_attempt["external_refs"], {})

        second_bootstrap = self.result(self.run_cli(
            "bootstrap", "--change", "portable", "--run-id", "run-2",
            "--bootstrap-id", "bootstrap-2", "--driver", "host",
        ))
        self.result(self.run_cli(
            "claim-coordinator", "--capsule", second_bootstrap["capsule_path"],
            "--coordinator-id", "coordinator-2",
        ))
        deferred_arguments = argparse.Namespace(
            **{**vars(dispatch_arguments), "run_id": "run-2", "defer_launch": True}
        )
        original = runtime._driver_for_state
        runtime._driver_for_state = lambda *args: fake
        try:
            reserved = runtime.command_dispatch(deferred_arguments)
            reserved_attempt = reserved["state"]["attempts"][reserved["attempt_id"]]
            with self.assertRaises(runtime.StaleCoordinatorError):
                runtime.command_resume(
                    argparse.Namespace(
                        repo=self.repository,
                        change="portable",
                        run_id="run-2",
                        generation=1,
                    )
                )
            self.assertEqual(len(fake.calls), 1)
            runtime.command_resume(
                argparse.Namespace(
                    repo=self.repository,
                    change="portable",
                    run_id="run-2",
                    generation=2,
                )
            )
            recovered = runtime.command_recover_attempt(
                argparse.Namespace(
                    repo=self.repository,
                    change="portable",
                    run_id="run-2",
                    generation=2,
                    attempt=reserved["attempt_id"],
                )
            )
        finally:
            runtime._driver_for_state = original

        reconcile_attempts = [call[1] for call in fake.calls if call[0] == "reconcile"]
        recovery_calls = [call[1] for call in fake.calls if call[0] == "start_attempt"]
        self.assertEqual(len(reconcile_attempts), 1)
        self.assertEqual(len(recovery_calls), 2)
        for operation, attempt in [
            *(("resume", attempt) for attempt in reconcile_attempts[0]),
            ("recovery", recovery_calls[-1]),
        ]:
            with self.subTest(operation=operation):
                self.assertEqual(attempt["workspace_scope"], reserved_attempt["workspace_scope"])
                self.assertEqual(attempt["execution_profile"], reserved_attempt["execution_profile"])
                self.assertEqual(attempt["resolved_placement"], reserved_attempt["resolved_placement"])
                self.assertEqual(attempt["external_refs"], reserved_attempt["external_refs"])

    def test_rejects_missing_or_mismatched_persisted_driver_context(self) -> None:
        self.bootstrap_and_claim()
        dispatched = self.result(self.run_cli(
            "dispatch", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--task", "ROOT-01", "--local", "--defer-launch",
        ))
        attempt = dispatched["state"]["attempts"][dispatched["attempt_id"]]
        invalid_attempts = {
            "missing_scope": {key: value for key, value in attempt.items() if key != "workspace_scope"},
            "missing_profile": {key: value for key, value in attempt.items() if key != "execution_profile"},
            "missing_placement": {key: value for key, value in attempt.items() if key != "resolved_placement"},
            "missing_refs": {key: value for key, value in attempt.items() if key != "external_refs"},
            "mismatched_placement": {
                **attempt,
                "resolved_placement": {**attempt["resolved_placement"], "workspace_key": "folder:other"},
            },
        }
        for failure, candidate in invalid_attempts.items():
            with self.subTest(failure=failure):
                with self.assertRaises(runtime.DriverError):
                    runtime.persisted_driver_context(candidate)

    def test_sync_keeps_host_result_events_on_the_shared_ingestion_path(self) -> None:
        self.bootstrap_and_claim()
        dispatched = self.result(
            self.run_cli(
                "dispatch", "--change", "portable", "--run-id", "run-1",
                "--generation", "2", "--task", "ROOT-01", "--local",
            )
        )
        capsule = json.loads((self.repository / dispatched["capsule"]).read_text(encoding="utf-8"))
        result_path = self.repository / capsule["result_path"]
        result_path.write_text(
            json.dumps(
                {
                    "task_id": "ROOT-01",
                    "attempt_id": dispatched["attempt_id"],
                    "outcome": "reported",
                    "summary": "The host worker completed.",
                    "files_changed": ["src/root.py"],
                    "checks_run": ["python3 -m unittest tests.test_root"],
                    "evidence_refs": [],
                    "questions": [],
                    "external_refs": {"host": "native"},
                }
            ),
            encoding="utf-8",
        )

        synced = self.result(
            self.run_cli(
                "sync", "--change", "portable", "--run-id", "run-1", "--generation", "2"
            )
        )

        self.assertEqual(synced["state"]["tasks"]["ROOT-01"]["status"], "reported")

    def test_sync_replays_a_quarantined_malformed_candidate_after_a_crash(self) -> None:
        self.bootstrap_and_claim()
        dispatched = self.result(
            self.run_cli(
                "dispatch", "--change", "portable", "--run-id", "run-1",
                "--generation", "2", "--task", "ROOT-01", "--local",
            )
        )
        directory = self.repository / "openspec/runs/portable/run-1"
        raw = b'{"task_id":"ROOT-01"'
        evidence = directory / "artifacts/malformed-provider-results" / f"{dispatched['attempt_id']}.json"
        evidence.parent.mkdir(parents=True)
        evidence.write_bytes(raw)

        synced = runtime.command_sync(
            argparse.Namespace(
                repo=self.repository,
                change="portable",
                run_id="run-1",
                generation=2,
            )
        )

        attempt = synced["state"]["attempts"][dispatched["attempt_id"]]
        self.assertEqual(attempt["status"], "abandoned")
        self.assertEqual(evidence.read_bytes(), raw)
        self.assertEqual(
            attempt["provider_result_rejection"]["sha256"],
            "sha256:" + runtime.hashlib.sha256(raw).hexdigest(),
        )

    def test_rejects_unowned_terminals_as_cleanup_authority(self) -> None:
        self.bootstrap_and_claim()
        directory = self.repository / "openspec/runs/portable/run-1"
        dispatched = self.result(self.run_cli(
            "dispatch", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--task", "ROOT-01", "--local",
        ))
        attempt_id = dispatched["attempt_id"]
        before = self.run_directory_snapshot("run-1")
        unowned = self.run_cli(
            "cleanup-register", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--cleanup-id", "cleanup-external-terminal",
            "--kind", "terminal", "--target", "external-terminal-01", "--owner", json.dumps({
                "execution_host_id": dispatched["state"]["workspace_scope"]["execution_workspace"]["execution_host_id"],
                "workspace_key": dispatched["state"]["workspace_scope"]["execution_workspace"]["workspace_key"],
                "attempt_id": attempt_id,
                "terminal_id": "external-terminal-01",
                "incarnation_id": "external-incarnation-01",
                "process_root": None,
                "provenance": "test unowned terminal",
            }),
        )
        self.assertNotEqual(unowned.returncode, 0)
        self.assertEqual(
            json.loads(unowned.stderr)["error"]["code"], "cleanup_authority_unproven"
        )
        self.assertEqual(self.run_directory_snapshot("run-1"), before)
        for command in (
            ("cleanup-finish", "--cleanup-id", "cleanup-external-terminal"),
            ("cleanup-retain", "--cleanup-id", "cleanup-external-terminal", "--receipt", "{}"),
        ):
            with self.subTest(command=command[0]):
                rejected = self.run_cli(
                    command[0], "--change", "portable", "--run-id", "run-1",
                    "--generation", "2", *command[1:],
                )
                self.assertNotEqual(rejected.returncode, 0)
                self.assertEqual(
                    json.loads(rejected.stderr)["error"]["code"], "unknown_cleanup"
                )
        (directory / "results" / f"{attempt_id}.json").write_bytes(b"not-json")

        synced = runtime.command_sync(
            argparse.Namespace(
                repo=self.repository,
                change="portable",
                run_id="run-1",
                generation=2,
            )
        )

        self.assertEqual(synced["state"]["attempts"][attempt_id]["status"], "abandoned")
        self.assertNotIn("cleanup-external-terminal", synced["state"]["cleanup"])
        events = [json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()]
        self.assertNotIn("cleanup_finished", [event["type"] for event in events])

    def test_rejects_a_malformed_candidate_evidence_collision(self) -> None:
        self.bootstrap_and_claim()
        dispatched = self.result(
            self.run_cli(
                "dispatch", "--change", "portable", "--run-id", "run-1",
                "--generation", "2", "--task", "ROOT-01", "--local",
            )
        )
        directory = self.repository / "openspec/runs/portable/run-1"
        (directory / "results" / f"{dispatched['attempt_id']}.json").write_bytes(b"not-json")
        evidence = directory / "artifacts/malformed-provider-results" / f"{dispatched['attempt_id']}.json"
        evidence.parent.mkdir(parents=True)
        evidence.write_bytes(b"different-malformed-bytes")

        with self.assertRaisesRegex(runtime.AgentGraphCliError, "already differs") as raised:
            runtime.command_sync(
                argparse.Namespace(
                    repo=self.repository,
                    change="portable",
                    run_id="run-1",
                    generation=2,
                )
            )
        self.assertEqual(raised.exception.code, "malformed_candidate_collision")

    def test_fails_closed_when_rejected_candidate_evidence_disappears(self) -> None:
        self.bootstrap_and_claim()
        dispatched = self.result(
            self.run_cli(
                "dispatch", "--change", "portable", "--run-id", "run-1",
                "--generation", "2", "--task", "ROOT-01", "--local",
            )
        )
        directory = self.repository / "openspec/runs/portable/run-1"
        attempt_id = dispatched["attempt_id"]
        (directory / "results" / f"{attempt_id}.json").write_bytes(b"not-json")
        journal = runtime._journal(directory)
        projection = journal.verify_projection()
        projection, candidate = runtime._preserve_malformed_host_result(
            self.repository, directory, journal, projection, 2, attempt_id
        )
        self.assertIsNotNone(candidate)
        (directory / "artifacts/malformed-provider-results" / f"{attempt_id}.json").unlink()

        with self.assertRaisesRegex(runtime.AgentGraphCliError, "evidence is missing") as raised:
            runtime.command_sync(
                argparse.Namespace(
                    repo=self.repository,
                    change="portable",
                    run_id="run-1",
                    generation=2,
                )
            )
        self.assertEqual(raised.exception.code, "malformed_candidate_evidence_missing")

    def test_recovers_driver_and_attempt_reservations_idempotently(self) -> None:
        bootstrap = self.result(
            self.run_cli(
                "bootstrap", "--change", "portable", "--run-id", "run-1",
                "--bootstrap-id", "bootstrap-1", "--driver", "host",
            )
        )
        directory = self.repository / "openspec/runs/portable/run-1"
        journal = runtime._journal(directory)
        projection = journal.append(
            "coordinator_claimed",
            {"coordinator_id": "coordinator-1", "capsule_path": bootstrap["capsule_path"]},
            coordinator_generation=2,
        )
        projection = journal.append(
            "driver_selection_reserved",
            {"reservation_id": "driver-selection-generation-2", "requested": "host"},
            coordinator_generation=2,
        )
        recovered_driver = self.result(
            self.run_cli(
                "recover-driver-selection", "--change", "portable", "--run-id", "run-1",
                "--generation", "2",
            )
        )
        self.assertEqual(recovered_driver["state"]["driver"], "host")

        task = runtime._task_from_state(recovered_driver["state"], "ROOT-01")
        profile = runtime._execution_profile_for_task(task, recovered_driver["state"]["workspace_scope"])
        journal.verify_projection()
        projection = journal.append("task_ready", {"task_id": task.id}, coordinator_generation=2)
        projection = journal.append(
            "attempt_reserved",
            {
                "task_id": task.id,
                "attempt_id": "attempt-crash",
                "driver": "host",
                "worker": "local",
                "task": task.to_dict(),
                "dependency_digest": [],
                "workspace_scope": recovered_driver["state"]["workspace_scope"],
                "execution_profile": profile,
                "resolved_placement": profile["resolved_placement"],
                "external_refs": {},
            },
            coordinator_generation=2,
        )
        host = runtime.HostDriver(self.repository, directory)
        host.start_attempt(
            {
                "task_id": task.id,
                "attempt_id": "attempt-crash",
                "task": task.to_dict(),
                "dependency_digest": [],
                "workspace_scope": recovered_driver["state"]["workspace_scope"],
                "execution_profile": profile,
                "resolved_placement": profile["resolved_placement"],
                "external_refs": {},
                "local": True,
            }
        )

        recovered_attempt = self.result(
            self.run_cli(
                "recover-attempt", "--change", "portable", "--run-id", "run-1",
                "--generation", "2", "--attempt", "attempt-crash",
            )
        )

        self.assertEqual(recovered_attempt["state"]["attempts"]["attempt-crash"]["status"], "running")
        self.assertEqual(recovered_attempt["receipt"]["operation"], "start_attempt")


if __name__ == "__main__":
    unittest.main()
