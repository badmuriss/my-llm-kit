import json
import io
import os
import argparse
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from collections.abc import Mapping
from unittest.mock import patch
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "agent_graph.py"
sys.path.insert(0, str(SCRIPT.parent))

import graph_core  # noqa: E402
import validation  # noqa: E402
from graph_core import EventJournal, GraphValidationError, JournalError, apply_event, empty_projection  # noqa: E402
import agent_graph as runtime  # noqa: E402
import adaptive_intake  # noqa: E402
from drivers.base import DriverReceipt  # noqa: E402
from validation import (  # noqa: E402
    CheckExecutionError,
    _WindowsJob,
    _terminate_process_tree,
    finalize_shared_check_recovery,
    recover_shared_check,
    run_bounded_command,
    run_shared_check,
)


TASKS = f'''# Tasks

- [ ] ROOT-01 Exercise lifecycle behavior
  Depends: []
  Paths: [src/root.py]
  Mode: write
  Isolation: auto
  Acceptance: The worker lifecycle remains bounded.
  Check: "{sys.executable}" -c "import subprocess, sys, time; child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); print(child.pid, flush=True); time.sleep(30)"

- [ ] AUX-02 Preserve an independent lifecycle packet
  Depends: []
  Paths: [src/aux.py]
  Mode: read
  Isolation: auto
  Acceptance: The second packet remains independent.
  Check: "{sys.executable}" -c "raise SystemExit(0)"
'''


class ResourceLifecycleBehavior(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repository = Path(self.temporary_directory.name)
        change = self.repository / "openspec/changes/portable"
        change.mkdir(parents=True)
        for name, body in {
            "proposal.md": "# Proposal\n",
            "design.md": "# Design\n",
            "tasks.md": TASKS,
        }.items():
            (change / name).write_text(body, encoding="utf-8")
        graph = runtime.parse_task_graph(change / "tasks.md")
        transition = adaptive_intake.decide_process(
            self.repository,
            request="Exercise lifecycle behavior with independent packets.",
            check_command=graph.tasks[0].check,
            signals={
                "known_scope": True,
                "graph_requested": True,
                "cohesion": "independent",
                "independent_packets": [
                    {"packet_id": task.id, "paths": list(task.paths), "check": {"command": task.check, "oracle": f"{task.id} passes."}}
                    for task in graph.tasks
                ],
                "integrator": "coordinator-1",
                "permission_observed": True,
                "budget_limits": [{"resource": "workers", "value": 2, "unit": "workers", "rationale": "Two independent fixture packets."}],
                "cleanup_plan": "Verify every owned process and provider receipt.",
            },
        )
        (change / "process-decision.json").write_text(json.dumps(transition), encoding="utf-8")
        for command in (
            ["git", "init", "-q", str(self.repository)],
            ["git", "-C", str(self.repository), "config", "user.email", "test@example.com"],
            ["git", "-C", str(self.repository), "config", "user.name", "Test"],
            ["git", "-C", str(self.repository), "add", "."],
            ["git", "-C", str(self.repository), "commit", "-qm", "fixture"],
        ):
            subprocess.run(command, check=True)
        bootstrap = self.run_cli(
            "bootstrap", "--change", "portable", "--run-id", "run-1",
            "--bootstrap-id", "bootstrap-1", "--driver", "host",
        )
        capsule = json.loads(bootstrap.stdout)["result"]["capsule_path"]
        self.run_cli(
            "claim-coordinator", "--capsule", capsule, "--coordinator-id", "coordinator-1",
        )
        self.run_directory = self.repository / "openspec/runs/portable/run-1"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def run_cli(self, command: str, *arguments: str) -> subprocess.CompletedProcess[str]:
        completed = self.raw_cli(command, *arguments)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return completed

    def raw_cli(self, command: str, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), command, "--repo", str(self.repository), "--json", *arguments],
            check=False,
            capture_output=True,
            text=True,
        )

    def append_repairs(self, count: int) -> int:
        journal = EventJournal(self.run_directory / "events.jsonl", self.run_directory / "state.json")
        journal.verify_projection()
        for index in range(count):
            journal.append(
                "journal_repaired",
                {"artifact": f"artifact-{index}", "discarded_bytes": index},
                coordinator_generation=2,
            )
        return journal.verify_projection()["last_sequence"]

    def orca_route_input(self) -> str:
        path = self.repository / "openspec/changes/portable/orca-route.json"
        path.write_text(json.dumps({
            "authority": {"coordinator_id": "coordinator-1", "coordinator_generation": 1, "source": "test coordinator policy"},
            "capability_catalog": {"profiles": [
                {"agent": "codex", "model": "catalog-luna", "lane": "fast", "efforts": ["low", "medium"], "cost_rank": 0},
                {"agent": "codex", "model": "catalog-terra", "lane": "balanced", "efforts": ["medium", "high"], "cost_rank": 1},
            ]},
            "routing_request": {"role": "implementation", "risk": "material", "check_strength": "decisive", "overrides": {"lane": "balanced", "effort": "medium"}},
        }), encoding="utf-8")
        return path.relative_to(self.repository).as_posix()

    def test_streams_ndjson_and_resets_an_expired_cursor(self) -> None:
        current = self.append_repairs(70)
        expired = self.run_cli(
            "status", "--change", "portable", "--run-id", "run-1", "--watch",
            "--cursor", "0", "--iterations", "1",
        )
        lines = expired.stdout.splitlines()
        self.assertEqual(len(lines), 1)
        reset = json.loads(lines[0])
        self.assertEqual(reset["kind"], "reset")
        self.assertEqual(reset["reason"], "cursor_expired")
        self.assertEqual(reset["cursor"], current)

        mid_window = self.run_cli(
            "status", "--change", "portable", "--run-id", "run-1", "--watch",
            "--cursor", str(current - 2), "--iterations", "1",
        )
        deltas = [json.loads(line) for line in mid_window.stdout.splitlines()]
        self.assertEqual([delta["kind"] for delta in deltas], ["delta"])
        self.assertEqual(deltas[-1]["cursor"], current)

        continuous = subprocess.Popen(
            [
                sys.executable, str(SCRIPT), "status", "--repo", str(self.repository), "--json",
                "--change", "portable", "--run-id", "run-1", "--watch", "--interval", "0.05",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            first_line = continuous.stdout.readline()
            self.assertEqual(json.loads(first_line)["kind"], "snapshot")
            time.sleep(0.1)
            self.assertIsNone(continuous.poll())
        finally:
            continuous.terminate()
            continuous.communicate(timeout=5)

    def test_discards_partial_and_oversized_tail_boundaries(self) -> None:
        journal = EventJournal(self.run_directory / "events.jsonl", self.run_directory / "state.json")
        journal.verify_projection()
        journal.append(
            "journal_repaired",
            {"artifact": "x" * (4 * 1024 * 1024 + 512), "discarded_bytes": 1},
            coordinator_generation=2,
        )
        expected = self.append_repairs(2)
        tail = journal.recent_events(64)
        self.assertTrue(tail)
        self.assertEqual(tail[-1]["sequence"], expected)

        with (self.run_directory / "events.jsonl").open("ab") as handle:
            handle.write(b'{"partial":')
        observed = self.run_cli(
            "status", "--change", "portable", "--run-id", "run-1", "--watch",
            "--cursor", str(expected), "--iterations", "1",
        )
        self.assertEqual(observed.stdout, "")

    def test_derives_completion_provenance_after_excluding_bootstrap_dirty_paths(self) -> None:
        projection = {
            "dirty_paths": ["src/preexisting.tsx", "assets/"],
            "tasks": {
                "ROOT-01": {
                    "contract": {"paths": ["src/"]},
                },
            },
            "attempts": {
                "attempt-root-01-001": {
                    "task_id": "ROOT-01",
                    "status": "reported",
                    "report": {"files_changed": ["src/owned.tsx"]},
                },
            },
        }
        owned, unowned = runtime._completion_provenance(
            self.repository,
            self.run_directory,
            projection,
            [
                "src/preexisting.tsx",
                "assets/logo.svg",
                "src/owned.tsx",
                "src/unowned.tsx",
                "openspec/runs/portable/run-1/results/attempt-root-01-001.json",
            ],
        )
        self.assertEqual(owned, ["src/owned.tsx"])
        self.assertEqual(unowned, ["src/unowned.tsx"])

    def test_exempts_bootstrap_dirty_descendants_only_for_explicit_directories(self) -> None:
        projection = {"dirty_paths": ["assets"]}
        self.assertFalse(runtime._is_bootstrap_dirty_path("assets/later.tsx", projection["dirty_paths"]))
        self.assertTrue(runtime._is_bootstrap_dirty_path("assets/later.tsx", ["assets/"]))
        _, unowned = runtime._completion_provenance(
            self.repository,
            self.run_directory,
            {**projection, "tasks": {}, "attempts": {}},
            ["assets/later.tsx"],
        )
        self.assertEqual(unowned, ["assets/later.tsx"])

    def test_preserves_git_untracked_directory_markers_in_bootstrap_snapshots(self) -> None:
        completed = subprocess.CompletedProcess(
            ["git", "status"],
            0,
            stdout="?? assets/\0?? src/preexisting.tsx\0",
            stderr="",
        )
        with patch.object(runtime, "_git", return_value=completed):
            self.assertEqual(runtime._dirty_paths(self.repository), ["assets/", "src/preexisting.tsx"])

    def test_rejects_post_bootstrap_frontend_changes_without_attempt_provenance(self) -> None:
        projection = {
            "status": "active",
            "coordinator": {"generation": 2},
            "base_commit": "base",
            "dirty_paths": ["src/preexisting.tsx"],
            "tasks": {
                "ROOT-01": {
                    "grade": "pass",
                    "contract": {"paths": ["src/"], "visual": []},
                },
            },
            "attempts": {
                "attempt-root-01-001": {
                    "task_id": "ROOT-01",
                    "status": "reported",
                    "report": {"files_changed": ["src/owned.tsx"]},
                },
            },
            "cleanup": {},
        }

        class Journal:
            def verify_projection(self):
                return projection

        arguments = runtime.argparse.Namespace(
            repo=self.repository,
            change="portable",
            run_id="run-1",
            generation=2,
            outcome="pass",
        )
        with patch.object(runtime, "load_run_control_runtime", return_value={}), \
             patch.object(runtime, "verify_control_runtime", return_value={}), \
             patch.object(runtime, "_journal", return_value=Journal()), \
             patch.object(runtime, "_changed_paths_since", return_value=["src/unowned.tsx"]):
            with self.assertRaises(runtime.AgentGraphCliError) as rejected:
                runtime.command_complete(arguments)
        self.assertEqual(rejected.exception.code, "changed_path_unproven")

    def test_allows_preexisting_frontend_changes_without_a_visual_contract(self) -> None:
        projection = {
            "status": "active",
            "coordinator": {"generation": 2},
            "base_commit": "base",
            "dirty_paths": ["src/preexisting.tsx"],
            "tasks": {
                "ROOT-01": {
                    "grade": "pass",
                    "contract": {"paths": ["src/"], "visual": []},
                },
            },
            "attempts": {},
            "cleanup": {},
        }

        class Journal:
            def verify_projection(self):
                return projection

            def append(self, event_type, data, *, coordinator_generation):
                self.event = (event_type, data, coordinator_generation)
                return {**projection, "status": "complete", "outcome": data["outcome"]}

        journal = Journal()
        arguments = runtime.argparse.Namespace(
            repo=self.repository,
            change="portable",
            run_id="run-1",
            generation=2,
            outcome="pass",
        )
        with patch.object(runtime, "load_run_control_runtime", return_value={}), \
             patch.object(runtime, "verify_control_runtime", return_value={}), \
             patch.object(runtime, "_journal", return_value=journal), \
             patch.object(runtime, "_changed_paths_since", return_value=["src/preexisting.tsx"]), \
             patch.object(runtime, "release_control_runtime"):
            result = runtime.command_complete(arguments)
        self.assertTrue(result["completed"])
        self.assertEqual(journal.event[0], "run_completed")

    def test_fences_concurrent_cli_dispatch_and_keeps_a_valid_projection(self) -> None:
        commands = [
            [
                sys.executable, str(SCRIPT), "dispatch", "--repo", str(self.repository), "--json",
                "--change", "portable", "--run-id", "run-1", "--generation", "2",
                "--task", "ROOT-01", "--local",
            ]
            for _ in range(2)
        ]
        processes = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for command in commands]
        completed = [process.communicate(timeout=10) for process in processes]
        return_codes = [process.returncode for process in processes]
        self.assertEqual(return_codes.count(0), 1, completed)
        self.assertEqual(return_codes.count(1), 1, completed)
        failure = next(stderr for process, (_, stderr) in zip(processes, completed) if process.returncode)
        self.assertIn(json.loads(failure)["error"]["code"], {"invalid_graph", "task_not_ready", "stale_revision"})
        projection = EventJournal(self.run_directory / "events.jsonl", self.run_directory / "state.json").verify_projection()
        sequences = [json.loads(line)["sequence"] for line in (self.run_directory / "events.jsonl").read_text().splitlines()]
        self.assertEqual(sequences, list(range(1, projection["last_sequence"] + 1)))
        self.assertEqual(len(projection["attempts"]), 1)

    def test_keeps_mutation_output_compact_and_terminates_check_descendants(self) -> None:
        dispatched = self.run_cli(
            "dispatch", "--change", "portable", "--run-id", "run-1", "--generation", "2",
            "--task", "ROOT-01", "--local",
        )
        dispatch_payload = json.loads(dispatched.stdout)["result"]
        self.assertNotIn("state", dispatch_payload)
        capsule_path = self.repository / dispatch_payload["capsule"]
        capsule = json.loads(capsule_path.read_text(encoding="utf-8"))
        result_path = self.repository / capsule["result_path"]
        result_path.write_text(json.dumps({
            "task_id": "ROOT-01", "attempt_id": "attempt-root-01-001", "outcome": "reported",
            "summary": "report body context must remain in the artifact", "files_changed": [], "checks_run": ["local"],
            "evidence_refs": [], "questions": [], "external_refs": {},
        }), encoding="utf-8")
        recorded = self.run_cli(
            "record-result", "--change", "portable", "--run-id", "run-1", "--generation", "2",
            "--attempt", "attempt-root-01-001", "--result", capsule["result_path"],
        )
        self.assertNotIn("report body context", recorded.stdout)
        self.assertNotIn("state", json.loads(recorded.stdout)["result"])
        checked = self.raw_cli(
            "run-check", "--change", "portable", "--run-id", "run-1", "--generation", "2",
            "--task", "ROOT-01", "--timeout", "0.2", "--output-cap", "64",
        )
        self.assertEqual(checked.returncode, 1, checked.stderr)
        state = EventJournal(self.run_directory / "events.jsonl", self.run_directory / "state.json").verify_projection()
        artifact = self.repository / state["tasks"]["ROOT-01"]["check"]["artifact"]
        evidence = json.loads(artifact.read_text(encoding="utf-8"))
        self.assertTrue(evidence["timed_out"])
        self.assertLessEqual(len(evidence["stdout"].encode()), 64)
        self.assertLessEqual(len(evidence["stderr"].encode()), 64)
        child_id = int(evidence["stdout"].strip())
        time.sleep(0.2)
        with self.assertRaises(ProcessLookupError):
            os.kill(child_id, 0)

    def test_projects_typed_cleanup_as_verified_and_unverifiable_evidence_as_pending(self) -> None:
        owner = {
            "execution_host_id": "local", "workspace_key": "folder:test", "attempt_id": "child-1",
            "terminal_id": "terminal-1", "incarnation_id": "incarnation-1", "process_root": None,
            "provenance": "authoritative receipt",
        }
        state = empty_projection()
        state["last_sequence"] = 1
        state["status"] = "active"
        state["cleanup"] = {"cleanup-1": {"cleanup_id": "cleanup-1", "kind": "terminal", "owner": owner, "delegation_id": "child", "status": "pending"}}
        verified = apply_event(state, {
            "type": "cleanup_finished",
            "data": {"cleanup_id": "cleanup-1", "receipt": {"kind": "terminal", "owner": owner, "terminal_id": "terminal-1", "incarnation_id": "incarnation-1", "status": "verified"}},
            "sequence": 1,
        })
        self.assertEqual(verified["cleanup"]["cleanup-1"]["status"], "verified")
        unverifiable = apply_event(state, {
            "type": "cleanup_unverifiable",
            "data": {"cleanup_id": "cleanup-1", "receipt": {"reason": "provider receipt is not authoritative"}},
            "sequence": 1,
        })
        self.assertEqual(unverifiable["cleanup"]["cleanup-1"]["status"], "unverifiable")
        with self.assertRaises((GraphValidationError, JournalError)):
            apply_event(state, {
                "type": "cleanup_finished",
                "data": {"cleanup_id": "cleanup-1", "receipt": "arbitrary"}, "sequence": 1,
            })

    def test_rejects_verified_process_cleanup_linked_to_another_delegation(self) -> None:
        owner = {
            "execution_host_id": "local", "workspace_key": "folder:test", "attempt_id": "child-1",
            "terminal_id": None, "incarnation_id": None, "process_root": 42,
            "provenance": "authoritative process receipt",
        }
        lifecycle = {
            "started": {"receipt_id": "started-a", "receipt_path": "openspec/runs/portable/run-1/artifacts/started-a.json", "sha256": "sha256:" + "a" * 64, "byte_length": 1},
            "reported": {"receipt_id": "reported-a", "receipt_path": "openspec/runs/portable/run-1/artifacts/reported-a.json", "sha256": "sha256:" + "b" * 64, "byte_length": 1},
        }
        state = empty_projection()
        state.update({"change": "portable", "run_id": "run-1", "status": "active"})
        state["delegations"] = {
            "delegation-a": {"status": "reported", "resource_owner": owner, "cleanup_id": "cleanup-process-a", "lifecycle_receipts": lifecycle},
            "delegation-b": {"status": "reported", "resource_owner": owner, "cleanup_id": "cleanup-terminal-b", "lifecycle_receipts": lifecycle},
        }
        state["cleanup"] = {
            "cleanup-process-a": {"cleanup_id": "cleanup-process-a", "kind": "process", "owner": owner, "delegation_id": "delegation-a", "status": "verified", "receipt": {"kind": "process", "status": "verified"}},
            "cleanup-terminal-b": {"cleanup_id": "cleanup-terminal-b", "kind": "terminal", "owner": owner, "delegation_id": "delegation-b", "status": "retained", "receipt": {"observation": "unobserved"}},
        }
        with self.assertRaisesRegex(JournalError, "different delegation"):
            apply_event(state, {
                "type": "delegation_released",
                "data": {
                    "delegation_id": "delegation-b", "cleanup_id": "cleanup-process-a",
                    "receipt": {"receipt_id": "released-b", "receipt_path": "openspec/runs/portable/run-1/artifacts/released-b.json", "sha256": "sha256:" + "c" * 64, "byte_length": 1},
                },
                "sequence": 1,
            })

    def test_rejects_retained_terminal_cleanup_even_with_matching_owner(self) -> None:
        owner = {
            "execution_host_id": "local", "workspace_key": "folder:test", "attempt_id": "child-1",
            "terminal_id": "terminal-1", "incarnation_id": "incarnation-1", "process_root": None,
            "provenance": "authoritative receipt",
        }
        lifecycle = {
            "started": {"receipt_id": "started-a", "receipt_path": "openspec/runs/portable/run-1/artifacts/started-a.json", "sha256": "sha256:" + "a" * 64, "byte_length": 1},
            "reported": {"receipt_id": "reported-a", "receipt_path": "openspec/runs/portable/run-1/artifacts/reported-a.json", "sha256": "sha256:" + "b" * 64, "byte_length": 1},
        }
        state = empty_projection()
        state.update({"change": "portable", "run_id": "run-1", "status": "active"})
        state["delegations"] = {
            "delegation-a": {"status": "reported", "resource_owner": owner, "cleanup_id": "cleanup-terminal-a", "lifecycle_receipts": lifecycle},
        }
        state["cleanup"] = {
            "cleanup-terminal-a": {"cleanup_id": "cleanup-terminal-a", "kind": "terminal", "owner": owner, "delegation_id": "delegation-a", "status": "retained", "receipt": {"observation": "unobserved"}},
        }
        with self.assertRaisesRegex(JournalError, "verified terminal cleanup"):
            apply_event(state, {
                "type": "delegation_released",
                "data": {
                    "delegation_id": "delegation-a", "cleanup_id": "cleanup-terminal-a",
                    "receipt": {"receipt_id": "released-a", "receipt_path": "openspec/runs/portable/run-1/artifacts/released-a.json", "sha256": "sha256:" + "c" * 64, "byte_length": 1},
                },
                "sequence": 1,
            })

    def test_pins_host_recovery_identity_and_derives_only_matching_orca_owner(self) -> None:
        dispatched = self.run_cli(
            "dispatch", "--change", "portable", "--run-id", "run-1", "--generation", "2",
            "--task", "ROOT-01", "--local",
        )
        capsule_path = self.repository / json.loads(dispatched.stdout)["result"]["capsule"]
        capsule = json.loads(capsule_path.read_text(encoding="utf-8"))
        self.assertIn("workspace_scope", capsule)
        self.assertIn("execution_profile", capsule)
        journal = EventJournal(self.run_directory / "events.jsonl", self.run_directory / "state.json")
        projection = journal.verify_projection()
        attempt = projection["attempts"]["attempt-root-01-001"]
        journal.append(
            "attempt_start_failed",
            {"task_id": "ROOT-01", "attempt_id": "attempt-root-01-001", "code": "interrupted", "message": "test"},
            coordinator_generation=2,
        )
        class RecordingHost:
            def __init__(self, delegate) -> None:
                self.delegate = delegate
                self.requests: list[dict] = []

            def start_attempt(self, request):
                self.requests.append(dict(request))
                return self.delegate.start_attempt(request)

        driver = RecordingHost(runtime.HostDriver(self.repository, self.run_directory))
        recovery = runtime.argparse.Namespace(
            repo=self.repository, change="portable", run_id="run-1", generation=2,
            attempt="attempt-root-01-001",
        )
        with patch.object(runtime, "_driver_for_state", return_value=driver):
            runtime.command_recover_attempt(recovery)
        recovered = EventJournal(self.run_directory / "events.jsonl", self.run_directory / "state.json").verify_projection()["attempts"]["attempt-root-01-001"]
        self.assertEqual(recovered["workspace_scope"], attempt["workspace_scope"])
        self.assertEqual(recovered["execution_profile"], attempt["execution_profile"])
        self.assertEqual(recovered["external_refs"], attempt["external_refs"])
        self.assertEqual(driver.requests[-1]["workspace_scope"], attempt["workspace_scope"])
        self.assertEqual(driver.requests[-1]["execution_profile"], attempt["execution_profile"])
        self.assertEqual(driver.requests[-1]["external_refs"], attempt["external_refs"])

    def test_public_orca_dispatch_and_recovery_pin_authoritative_identity(self) -> None:
        source = EventJournal(self.run_directory / "events.jsonl", self.run_directory / "state.json").verify_projection()
        directory = runtime._new_run_directory(self.repository, "portable", "run-orca")
        scope = runtime._persist_workspace_scope(
            self.repository, directory, runtime._automatic_host_workspace_receipt(self.repository, "run-orca"),
            run_id="run-orca", coordinator_generation=1,
        )
        journal = EventJournal(directory / "events.jsonl", directory / "state.json")
        journal.append("run_started", {
            "change": "portable", "run_id": "run-orca", "coordinator_id": "coordinator-1",
            "coordinator_generation": 1, "base_commit": source["base_commit"], "dirty_paths": [],
            "workspace_scope": scope,
            "tasks": [task["contract"] for task in source["tasks"].values()],
        }, coordinator_generation=1)
        journal.append("driver_selected", {
            "requested": "orca", "driver": "orca", "reason": "test", "external_refs": {}, "receipts": [], "receipt_ids": [],
        }, coordinator_generation=1)

        class RecordingDriver:
            def __init__(self) -> None:
                self.requests: list[dict] = []
                self.variant: tuple[str, str, int] = ("terminal-1", "incarnation-1", 42)
                self.runtime_id = "runtime-1"
                self.release_proven = False

            def start_attempt(self, request):
                self.requests.append(dict(request))
                handle, incarnation, process_root = self.variant
                refs = {
                    "tier": "tracked-terminal", "run_id": "run-1", "task_id": "task-1", "dispatch_id": "dispatch-1",
                    "terminal": {"handle": handle, "incarnation_id": incarnation, "process_root": process_root,
                        "ownership": {"attempt_id": request["attempt_id"], "run_id": "run-1", "dispatch_id": "dispatch-1"}},
                }
                return DriverReceipt("start_attempt", "started", external_refs=refs)

            def reconcile(self, requests):
                return DriverReceipt("reconcile", "observed", raw=[{"resource_state": "absent"}])

            def release(self, request):
                if not self.release_proven:
                    raise runtime.DriverError("release proof unavailable", code="release_unknown")
                return DriverReceipt("release", "released", external_refs=dict(request["external_refs"]))

        driver = RecordingDriver()
        dispatch = runtime.argparse.Namespace(repo=self.repository, change="portable", run_id="run-orca", generation=1, task="ROOT-01", attempt_id="attempt-orca-1", worker=None, local=False, route_input=self.orca_route_input())
        with patch.object(runtime, "_driver_for_state", return_value=driver):
            runtime.command_dispatch(dispatch)
        projection = journal.verify_projection()
        attempt = projection["attempts"]["attempt-orca-1"]
        cleanup = projection["cleanup"]["cleanup-attempt-orca-1"]
        self.assertEqual(driver.requests[0]["workspace_scope"], scope)
        self.assertEqual(driver.requests[0]["execution_profile"], attempt["execution_profile"])
        self.assertEqual(driver.requests[0]["external_refs"], {})
        self.assertEqual(cleanup["target"], "terminal-1")
        self.assertEqual(cleanup["owner"]["incarnation_id"], "incarnation-1")
        self.assertEqual(attempt["execution_profile"]["resolved"], {
            "agent": "codex", "model": "catalog-terra", "effort": "medium",
        })
        self.assertNotIn("high", json.dumps(attempt["execution_profile"]))

        journal.append("attempt_start_failed", {"task_id": "ROOT-01", "attempt_id": "attempt-orca-1", "code": "interrupted", "message": "test"}, coordinator_generation=1)
        recovery = runtime.argparse.Namespace(repo=self.repository, change="portable", run_id="run-orca", generation=1, attempt="attempt-orca-1")
        with patch.object(runtime, "_driver_for_state", return_value=driver):
            runtime.command_recover_attempt(recovery)
        self.assertEqual(driver.requests[-1]["workspace_scope"], scope)
        self.assertEqual(driver.requests[-1]["execution_profile"], attempt["execution_profile"])
        self.assertEqual(driver.requests[-1]["external_refs"], attempt["external_refs"])
        self.assertEqual(driver.requests[-1]["resource_owner"], cleanup["owner"])

        for index, (handle, incarnation, process_root) in enumerate((("terminal-2", "incarnation-1", 42), ("terminal-1", "incarnation-2", 42), ("terminal-1", "incarnation-1", 43))):
            journal.verify_projection()
            journal.append("attempt_start_failed", {"task_id": "ROOT-01", "attempt_id": "attempt-orca-1", "code": "interrupted", "message": "test"}, coordinator_generation=1)
            before = ((directory / "events.jsonl").read_bytes(), (directory / "state.json").read_bytes())
            driver.variant = (handle, incarnation, process_root)
            with patch.object(runtime, "_driver_for_state", return_value=driver):
                with self.assertRaises(runtime.AgentGraphCliError):
                    runtime.command_recover_attempt(recovery)
            after = ((directory / "events.jsonl").read_bytes(), (directory / "state.json").read_bytes())
            if index == 0:
                self.assertNotEqual(before, after)
                failed = journal.verify_projection()["attempts"]["attempt-orca-1"]
                self.assertTrue(failed["post_start_unresolved"])
                self.assertEqual(journal.verify_projection()["cleanup"]["cleanup-attempt-orca-1"]["status"], "pending")
            else:
                self.assertEqual(before, after)

        driver.release_proven = True
        cleanup_recovery = runtime.argparse.Namespace(
            repo=self.repository, change="portable", run_id="run-orca", generation=1,
            attempt="attempt-orca-1",
        )
        pending_cleanup_ids = [
            cleanup_id for cleanup_id, cleanup in journal.verify_projection()["cleanup"].items()
            if isinstance(cleanup.get("owner"), Mapping) and cleanup["owner"].get("attempt_id") == "attempt-orca-1"
            and cleanup.get("status") == "pending"
        ]
        self.assertEqual(len(pending_cleanup_ids), 2)
        with patch.object(runtime, "_driver_for_state", return_value=driver):
            for cleanup_id in pending_cleanup_ids:
                cleanup_recovery.cleanup_id = cleanup_id
                runtime.command_recover_cleanup(cleanup_recovery)
        self.assertTrue(all(
            cleanup["status"] == "verified"
            for cleanup in journal.verify_projection()["cleanup"].values()
            if isinstance(cleanup.get("owner"), Mapping) and cleanup["owner"].get("attempt_id") == "attempt-orca-1"
        ))
        before = ((directory / "events.jsonl").read_bytes(), (directory / "state.json").read_bytes())
        starts_before = len(driver.requests)
        with patch.object(runtime, "_driver_for_state", side_effect=AssertionError("burned recovery must not construct a provider")):
            with self.assertRaisesRegex(runtime.AgentGraphCliError, "attempt ID is burned") as rejected:
                runtime.command_recover_attempt(recovery)
        self.assertEqual(rejected.exception.code, "post_start_attempt_burned")
        self.assertEqual(len(driver.requests), starts_before)
        self.assertEqual(before, ((directory / "events.jsonl").read_bytes(), (directory / "state.json").read_bytes()))

        abandon = runtime.argparse.Namespace(
            repo=self.repository, change="portable", run_id="run-orca", generation=1,
            attempt="attempt-orca-1", reason="exact cleanup settled",
        )
        with patch.object(runtime, "_driver_for_state", return_value=driver):
            runtime.command_abandon_attempt(abandon)
        self.assertEqual(journal.verify_projection()["attempts"]["attempt-orca-1"]["status"], "abandoned")

        driver.variant = ("terminal-1", "incarnation-1", 42)
        fresh = runtime.argparse.Namespace(
            repo=self.repository, change="portable", run_id="run-orca", generation=1,
            task="ROOT-01", attempt_id="attempt-orca-2", worker=None, local=False,
            route_input=self.orca_route_input(),
        )
        with patch.object(runtime, "_driver_for_state", return_value=driver):
            runtime.command_dispatch(fresh)
        self.assertEqual(journal.verify_projection()["attempts"]["attempt-orca-2"]["status"], "running")

    def test_records_distinct_cleanup_refs_for_each_recovery_mismatch(self) -> None:
        source = EventJournal(self.run_directory / "events.jsonl", self.run_directory / "state.json").verify_projection()

        class RecordingDriver:
            def __init__(self, run_id: str) -> None:
                self.run_id = run_id
                self.variant = ("terminal-a", "incarnation-a", 41)
                self.start_requests: list[dict] = []
                self.release_requests: list[dict] = []
                self.release_proven = False
                self.runtime_id = "runtime-1"

            def start_attempt(self, request):
                self.start_requests.append(dict(request))
                handle, incarnation, process_root = self.variant
                return DriverReceipt("start_attempt", "started", external_refs={
                    "tier": "tracked-terminal", "run_id": self.run_id, "task_id": "task-1", "dispatch_id": "dispatch-1",
                    "terminal": {"handle": handle, "incarnation_id": incarnation, "process_root": process_root,
                        "ownership": {"attempt_id": request["attempt_id"], "run_id": self.run_id, "dispatch_id": "dispatch-1"}},
                })

            def release(self, request):
                self.release_requests.append(dict(request))
                if not self.release_proven:
                    raise runtime.DriverError("temporary release disconnect", code="release_unknown")
                return DriverReceipt("release", "released", external_refs=dict(request["external_refs"]))

            def reconcile(self, requests):
                return DriverReceipt("reconcile", "observed", raw=[{"resource_state": "absent"}])

        for index, mismatch in enumerate((("terminal-b", "incarnation-a", 41), ("terminal-a", "incarnation-b", 41), ("terminal-a", "incarnation-a", 42)), start=1):
            run_id = f"run-mismatch-{index}"
            directory = runtime._new_run_directory(self.repository, "portable", run_id)
            scope = runtime._persist_workspace_scope(
                self.repository, directory, runtime._automatic_host_workspace_receipt(self.repository, run_id),
                run_id=run_id, coordinator_generation=1,
            )
            journal = EventJournal(directory / "events.jsonl", directory / "state.json")
            journal.append("run_started", {
                "change": "portable", "run_id": run_id, "coordinator_id": "coordinator-1", "coordinator_generation": 1,
                "base_commit": source["base_commit"], "dirty_paths": [], "workspace_scope": scope,
                "tasks": [task["contract"] for task in source["tasks"].values()],
            }, coordinator_generation=1)
            journal.append("driver_selected", {
                "requested": "orca", "driver": "orca", "reason": "test", "external_refs": {}, "receipts": [], "receipt_ids": [],
            }, coordinator_generation=1)
            driver = RecordingDriver(run_id)
            dispatch = runtime.argparse.Namespace(
                repo=self.repository, change="portable", run_id=run_id, generation=1, task="ROOT-01",
                attempt_id="attempt-mismatch", worker=None, local=False, route_input=self.orca_route_input(),
            )
            with patch.object(runtime, "_driver_for_state", return_value=driver):
                runtime.command_dispatch(dispatch)
            journal.verify_projection()
            journal.append("attempt_start_failed", {
                "task_id": "ROOT-01", "attempt_id": "attempt-mismatch", "code": "interrupted", "message": "test",
            }, coordinator_generation=1)
            driver.variant = mismatch
            recovery = runtime.argparse.Namespace(
                repo=self.repository, change="portable", run_id=run_id, generation=1, attempt="attempt-mismatch",
            )
            with patch.object(runtime, "_driver_for_state", return_value=driver):
                with self.assertRaises(runtime.AgentGraphCliError):
                    runtime.command_recover_attempt(recovery)
            self.assertEqual(len(driver.start_requests), 2)
            self.assertEqual(len(driver.release_requests), 1)
            state = journal.verify_projection()
            obligations = {
                cleanup_id: cleanup for cleanup_id, cleanup in state["cleanup"].items()
                if isinstance(cleanup.get("owner"), Mapping) and cleanup["owner"].get("attempt_id") == "attempt-mismatch"
            }
            self.assertEqual(len(obligations), 2)
            self.assertTrue(all(cleanup["status"] == "pending" for cleanup in obligations.values()))
            refs_a, refs_b = [cleanup["external_refs"] for cleanup in obligations.values()]
            self.assertNotEqual(refs_a["terminal"], refs_b["terminal"])
            with patch.object(runtime, "_driver_for_state", side_effect=AssertionError("pending obligations must block abandonment before a driver is constructed")):
                with self.assertRaisesRegex(runtime.AgentGraphCliError, "cleanup must be verified"):
                    runtime.command_abandon_attempt(runtime.argparse.Namespace(
                        repo=self.repository, change="portable", run_id=run_id, generation=1,
                        attempt="attempt-mismatch", reason="pending cleanup",
                    ))

            retry_cleanup_id = next(iter(obligations))
            with patch.object(runtime, "_driver_for_state", return_value=driver):
                for _ in range(2):
                    runtime.command_recover_cleanup(runtime.argparse.Namespace(
                        repo=self.repository, change="portable", run_id=run_id, generation=1,
                        attempt="attempt-mismatch", cleanup_id=retry_cleanup_id,
                    ))
            self.assertEqual(
                journal.verify_projection()["cleanup"][retry_cleanup_id]["status"], "unverifiable"
            )

            driver.release_proven = True
            with patch.object(runtime, "_driver_for_state", return_value=driver):
                for cleanup_id in obligations:
                    runtime.command_recover_cleanup(runtime.argparse.Namespace(
                        repo=self.repository, change="portable", run_id=run_id, generation=1,
                        attempt="attempt-mismatch", cleanup_id=cleanup_id,
                    ))
            self.assertEqual(len(driver.release_requests), 5)
            for release_request in driver.release_requests[1:]:
                refs = release_request["external_refs"]
                self.assertEqual(release_request["dispatch_id"], refs["dispatch_id"])
                self.assertEqual(release_request["external_task_id"], refs["task_id"])
                self.assertEqual(release_request["run_id"], refs["run_id"])
                self.assertEqual(release_request["terminal_handle"], refs["terminal"]["handle"])
            before_replay = len(driver.release_requests)
            with patch.object(runtime, "_driver_for_state", side_effect=AssertionError("terminal replay must not construct a driver")):
                runtime.command_recover_cleanup(runtime.argparse.Namespace(
                    repo=self.repository, change="portable", run_id=run_id, generation=1,
                    attempt="attempt-mismatch", cleanup_id=next(iter(obligations)),
                ))
            self.assertEqual(len(driver.release_requests), before_replay)
            with patch.object(runtime, "_driver_for_state", return_value=driver):
                runtime.command_abandon_attempt(runtime.argparse.Namespace(
                    repo=self.repository, change="portable", run_id=run_id, generation=1,
                    attempt="attempt-mismatch", reason="all exact cleanup verified",
                ))
            self.assertEqual(journal.verify_projection()["attempts"]["attempt-mismatch"]["status"], "abandoned")

    def test_verifies_provider_cleanup_against_its_selected_immutable_refs(self) -> None:
        journal = EventJournal(self.run_directory / "events.jsonl", self.run_directory / "state.json")
        projection = journal.verify_projection()
        scope = projection["workspace_scope"]
        task = runtime._task_from_state(projection, "ROOT-01")
        profile = runtime._execution_profile_for_task(task, scope)
        refs_a = {
            "tier": "supervised", "runtime_id": "runtime-a", "worktree_id": "worktree-a",
            "run_id": "run-a", "task_id": "task-1", "dispatch_id": "dispatch-a",
        }
        refs_b = {
            "tier": "supervised", "runtime_id": "runtime-b", "worktree_id": "worktree-b",
            "run_id": "run-b", "task_id": "task-1", "dispatch_id": "dispatch-b",
        }
        owner_a, _ = runtime._orca_lifecycle_from_receipt(refs_a, "attempt-provider-ab", scope)
        owner_b, _ = runtime._orca_lifecycle_from_receipt(refs_b, "attempt-provider-ab", scope)
        journal.append("attempt_reserved", {
            "task_id": "ROOT-01", "attempt_id": "attempt-provider-ab", "driver": "orca",
            "workspace_scope": scope, "execution_profile": profile,
        }, coordinator_generation=2)
        effective_scope = journal.verify_projection()["attempts"]["attempt-provider-ab"]["effective_scope"]
        journal.append("attempt_scope_frozen", {
            "attempt_id": "attempt-provider-ab", "effective_scope": effective_scope,
        }, coordinator_generation=2)
        journal.append("attempt_started", {
            "task_id": "ROOT-01", "attempt_id": "attempt-provider-ab", "driver": "orca",
            "external_refs": refs_a, "workspace_scope": scope, "execution_profile": profile,
            "effective_scope": effective_scope,
            "resource_owner": owner_a,
            "cleanup_id": "cleanup-provider-a",
            "cleanup_registration": {
                "cleanup_id": "cleanup-provider-a", "kind": "other", "target": "dispatch-a",
                "owner": owner_a, "external_refs": refs_a,
            },
        }, coordinator_generation=2)
        journal.append("attempt_start_failed", {
            "task_id": "ROOT-01", "attempt_id": "attempt-provider-ab", "code": "returned-effect",
            "message": "second provider effect", "post_start_unresolved": True,
            "receipt": {"returned_refs": refs_b}, "resource_owner": owner_b,
            "cleanup_id": "cleanup-provider-b",
            "cleanup_registration": {
                "cleanup_id": "cleanup-provider-b", "kind": "other", "target": "dispatch-b",
                "owner": owner_b, "external_refs": refs_b,
            },
        }, coordinator_generation=2)
        receipt_b = {
            "kind": "provider-dispatch", "owner": owner_b, "dispatch_id": "dispatch-b",
            "runtime_id": "runtime-b", "worktree_id": "worktree-b", "run_id": "run-b", "status": "released",
        }
        journal.append("cleanup_finished", {"cleanup_id": "cleanup-provider-b", "receipt": receipt_b}, coordinator_generation=2)
        state = journal.verify_projection()
        self.assertEqual(state["cleanup"]["cleanup-provider-a"]["owner"], owner_a)
        self.assertEqual(state["cleanup"]["cleanup-provider-a"]["external_refs"], refs_a)
        self.assertEqual(state["cleanup"]["cleanup-provider-b"]["owner"], owner_b)
        self.assertEqual(state["cleanup"]["cleanup-provider-b"]["external_refs"], refs_b)
        self.assertEqual(state["cleanup"]["cleanup-provider-a"]["status"], "pending")
        self.assertEqual(state["cleanup"]["cleanup-provider-b"]["status"], "verified")
        before = ((self.run_directory / "events.jsonl").read_bytes(), (self.run_directory / "state.json").read_bytes())
        with self.assertRaises(JournalError):
            journal.append("cleanup_finished", {"cleanup_id": "cleanup-provider-a", "receipt": receipt_b}, coordinator_generation=2)
        self.assertEqual(before, ((self.run_directory / "events.jsonl").read_bytes(), (self.run_directory / "state.json").read_bytes()))

    def test_registers_supervised_orca_cleanup_and_blocks_unowned_malformed_recovery(self) -> None:
        source = EventJournal(self.run_directory / "events.jsonl", self.run_directory / "state.json").verify_projection()

        def prepare(run_id: str) -> tuple[Path, EventJournal, dict]:
            directory = runtime._new_run_directory(self.repository, "portable", run_id)
            scope = runtime._persist_workspace_scope(
                self.repository, directory, runtime._automatic_host_workspace_receipt(self.repository, run_id),
                run_id=run_id, coordinator_generation=1,
            )
            journal = EventJournal(directory / "events.jsonl", directory / "state.json")
            journal.append("run_started", {
                "change": "portable", "run_id": run_id, "coordinator_id": "coordinator-1",
                "coordinator_generation": 1, "base_commit": source["base_commit"], "dirty_paths": [],
                "workspace_scope": scope, "tasks": [task["contract"] for task in source["tasks"].values()],
            }, coordinator_generation=1)
            journal.append("driver_selected", {
                "requested": "orca", "driver": "orca", "reason": "test", "external_refs": {}, "receipts": [], "receipt_ids": [],
            }, coordinator_generation=1)
            return directory, journal, scope

        class TierDriver:
            def __init__(self, refs: dict) -> None:
                self.refs = refs
                self.requests: list[dict] = []
                self.release_requests: list[dict] = []
                self.runtime_id = "runtime-1"

            def start_attempt(self, request):
                self.requests.append(dict(request))
                return DriverReceipt("start_attempt", "started", external_refs=self.refs)

            def release(self, request):
                self.release_requests.append(dict(request))
                return DriverReceipt("release", "unverifiable", external_refs={})

        supervised_directory, supervised_journal, scope = prepare("run-supervised")
        supervised = TierDriver({
            "tier": "supervised", "run_id": "run-supervised", "task_id": "task-1", "dispatch_id": "dispatch-1", "worktree_id": "worktree-1",
        })
        dispatch = runtime.argparse.Namespace(
            repo=self.repository, change="portable", run_id="run-supervised", generation=1,
            task="ROOT-01", attempt_id="attempt-supervised-1", worker=None, local=False, route_input=self.orca_route_input(),
        )
        with patch.object(runtime, "_driver_for_state", return_value=supervised):
            runtime.command_dispatch(dispatch)
        supervised_attempt = supervised_journal.verify_projection()["attempts"]["attempt-supervised-1"]
        self.assertIsNotNone(supervised_attempt.get("resource_owner"))
        self.assertEqual(supervised_attempt.get("cleanup_id"), "cleanup-attempt-supervised-1")
        self.assertEqual(supervised_journal.verify_projection()["cleanup"]["cleanup-attempt-supervised-1"]["target"], "dispatch-1")
        self.assertEqual(supervised.requests[0]["execution_profile"]["resolved"]["model"], "catalog-terra")

        malformed_directory, malformed_journal, _ = prepare("run-malformed")
        malformed = TierDriver({
            "tier": "tracked-terminal", "run_id": "run-malformed", "task_id": "task-1", "dispatch_id": "dispatch-1",
            "terminal": {"handle": "terminal-1", "ownership": {"attempt_id": "attempt-malformed-1", "run_id": "run-malformed", "dispatch_id": "dispatch-1"}},
        })
        bad_dispatch = runtime.argparse.Namespace(
            repo=self.repository, change="portable", run_id="run-malformed", generation=1,
            task="ROOT-01", attempt_id="attempt-malformed-1", worker=None, local=False, route_input=self.orca_route_input(),
        )
        with patch.object(runtime, "_driver_for_state", return_value=malformed):
            with self.assertRaises(runtime.AgentGraphCliError):
                runtime.command_dispatch(bad_dispatch)
        malformed_state = malformed_journal.verify_projection()
        self.assertEqual(malformed_state["attempts"]["attempt-malformed-1"]["status"], "interrupted")
        self.assertTrue(malformed_state["attempts"]["attempt-malformed-1"]["post_start_unresolved"])
        self.assertEqual(malformed_state["cleanup"], {})
        before = ((malformed_directory / "events.jsonl").read_bytes(), (malformed_directory / "state.json").read_bytes())
        starts_before = len(malformed.requests)
        releases_before = len(malformed.release_requests)
        recovery = runtime.argparse.Namespace(
            repo=self.repository, change="portable", run_id="run-malformed", generation=1,
            attempt="attempt-malformed-1",
        )
        with patch.object(runtime, "_driver_for_state", side_effect=AssertionError("blocked recovery must not construct a provider")):
            with self.assertRaisesRegex(runtime.AgentGraphCliError, "post-start identity is unresolved") as rejected:
                runtime.command_recover_attempt(recovery)
        self.assertEqual(rejected.exception.code, "post_start_identity_unresolved")
        self.assertEqual(len(malformed.requests), starts_before)
        self.assertEqual(len(malformed.release_requests), releases_before)
        self.assertEqual(before, ((malformed_directory / "events.jsonl").read_bytes(), (malformed_directory / "state.json").read_bytes()))
        abandon = runtime.argparse.Namespace(
            repo=self.repository, change="portable", run_id="run-malformed", generation=1,
            attempt="attempt-malformed-1", reason="cannot prove ownership",
        )
        with patch.object(runtime, "_driver_for_state", side_effect=AssertionError("unowned failure must not reconcile a provider")):
            with self.assertRaisesRegex(runtime.AgentGraphCliError, "cannot be abandoned") as rejected:
                runtime.command_abandon_attempt(abandon)
        self.assertEqual(rejected.exception.code, "post_start_identity_unresolved")
        self.assertEqual(len(malformed.requests), starts_before)
        self.assertEqual(len(malformed.release_requests), releases_before)
        self.assertEqual(before, ((malformed_directory / "events.jsonl").read_bytes(), (malformed_directory / "state.json").read_bytes()))

    def cleanup_snapshot(self) -> tuple[bytes, bytes]:
        return (
            (self.run_directory / "events.jsonl").read_bytes(),
            (self.run_directory / "state.json").read_bytes(),
        )

    def coordinator_cleanup_owner(self, **identity: object) -> dict[str, object]:
        scope = EventJournal(
            self.run_directory / "events.jsonl", self.run_directory / "state.json"
        ).verify_projection()["workspace_scope"]["execution_workspace"]
        return {
            "execution_host_id": scope["execution_host_id"],
            "workspace_key": scope["workspace_key"],
            "coordinator_generation": 2,
            "terminal_id": None,
            "incarnation_id": None,
            "process_root": None,
            "provenance": "orchestrator receipt",
            **identity,
        }

    def test_rejects_descriptive_process_target_and_finishes_typed_process_cleanup(self) -> None:
        process_target = {"kind": "process", "root_pid": 99999999}
        process_owner = self.coordinator_cleanup_owner(process_root=99999999)
        before = self.cleanup_snapshot()
        malformed_process = self.raw_cli(
            "cleanup-register", "--change", "portable", "--run-id", "run-1", "--generation", "2",
            "--cleanup-id", "cleanup-malformed-process", "--kind", "process",
            "--target", "pid=99999999 children=100,101", "--owner", json.dumps(process_owner),
        )
        self.assertNotEqual(malformed_process.returncode, 0)
        self.assertEqual(self.cleanup_snapshot(), before)
        self.run_cli(
            "cleanup-register", "--change", "portable", "--run-id", "run-1", "--generation", "2",
            "--cleanup-id", "cleanup-process", "--kind", "process",
            "--target", json.dumps(process_target), "--owner", json.dumps(process_owner),
        )
        self.assertEqual(
            EventJournal(self.run_directory / "events.jsonl", self.run_directory / "state.json")
            .verify_projection()["cleanup"]["cleanup-process"]["target"],
            process_target,
        )
        self.run_cli(
            "cleanup-finish", "--change", "portable", "--run-id", "run-1", "--generation", "2",
            "--cleanup-id", "cleanup-process", "--receipt", json.dumps({
                "kind": "process", "owner": process_owner, "target": process_target,
                "descendant_pids": [100, 101], "status": "verified",
            }),
        )
        self.assertEqual(
            EventJournal(self.run_directory / "events.jsonl", self.run_directory / "state.json")
            .verify_projection()["cleanup"]["cleanup-process"]["status"],
            "verified",
        )

    def test_rejects_untyped_terminal_owner_and_finishes_typed_terminal_cleanup(self) -> None:
        terminal_owner = self.coordinator_cleanup_owner(
            terminal_id="terminal-orca-1", incarnation_id="incarnation-orca-1",
        )
        before = self.cleanup_snapshot()
        untyped_terminal = self.raw_cli(
            "cleanup-register", "--change", "portable", "--run-id", "run-1", "--generation", "2",
            "--cleanup-id", "cleanup-untyped-terminal", "--kind", "terminal",
            "--target", "terminal-orca-1", "--owner", "orca-terminal:terminal-orca-1",
        )
        self.assertNotEqual(untyped_terminal.returncode, 0)
        self.assertEqual(self.cleanup_snapshot(), before)
        self.run_cli(
            "cleanup-register", "--change", "portable", "--run-id", "run-1", "--generation", "2",
            "--cleanup-id", "cleanup-terminal", "--kind", "terminal",
            "--target", "terminal-orca-1", "--owner", json.dumps(terminal_owner),
        )
        self.run_cli(
            "cleanup-finish", "--change", "portable", "--run-id", "run-1", "--generation", "2",
            "--cleanup-id", "cleanup-terminal", "--receipt", json.dumps({
                "kind": "terminal", "owner": terminal_owner, "terminal_id": "terminal-orca-1",
                "incarnation_id": "incarnation-orca-1", "status": "verified",
            }),
        )
        self.assertEqual(
            EventJournal(self.run_directory / "events.jsonl", self.run_directory / "state.json")
            .verify_projection()["cleanup"]["cleanup-terminal"]["status"],
            "verified",
        )

    def test_rejects_cleanup_target_owner_mismatch_and_identity_reuse(self) -> None:
        target = {"kind": "process", "root_pid": 99999999}
        owner = self.coordinator_cleanup_owner(process_root=99999999)
        before = self.cleanup_snapshot()
        mismatch = self.raw_cli(
            "cleanup-register", "--change", "portable", "--run-id", "run-1", "--generation", "2",
            "--cleanup-id", "cleanup-mismatch", "--kind", "process", "--target", json.dumps(target),
            "--owner", json.dumps(self.coordinator_cleanup_owner(process_root=99999998)),
        )
        self.assertNotEqual(mismatch.returncode, 0)
        self.assertEqual(self.cleanup_snapshot(), before)
        self.run_cli(
            "cleanup-register", "--change", "portable", "--run-id", "run-1", "--generation", "2",
            "--cleanup-id", "cleanup-identity", "--kind", "process", "--target", json.dumps(target),
            "--owner", json.dumps(owner),
        )
        before_reuse = self.cleanup_snapshot()
        reused = self.raw_cli(
            "cleanup-register", "--change", "portable", "--run-id", "run-1", "--generation", "2",
            "--cleanup-id", "cleanup-reused", "--kind", "process", "--target", json.dumps(target),
            "--owner", json.dumps({
                **owner,
                "terminal_id": "different-terminal",
                "incarnation_id": "different-incarnation",
            }),
        )
        self.assertNotEqual(reused.returncode, 0)
        self.assertEqual(self.cleanup_snapshot(), before_reuse)
        self.assertTrue(graph_core._cleanup_identity_reused(
            {
                "kind": "terminal",
                "target": "terminal-orca-1",
                "owner": {
                    **owner,
                    "terminal_id": "terminal-orca-1",
                    "incarnation_id": "incarnation-orca-1",
                    "process_root": 111,
                },
            },
            "terminal",
            "terminal-orca-1",
            {
                **owner,
                "terminal_id": "terminal-orca-1",
                "incarnation_id": "incarnation-orca-1",
                "process_root": 222,
            },
        ))

    def test_retains_legacy_cleanup_with_bounded_replacement_reference(self) -> None:
        process_target = {"kind": "process", "root_pid": 99999999}
        process_owner = self.coordinator_cleanup_owner(process_root=99999999)
        self.run_cli(
            "cleanup-register", "--change", "portable", "--run-id", "run-1", "--generation", "2",
            "--cleanup-id", "cleanup-replacement", "--kind", "process",
            "--target", json.dumps(process_target), "--owner", json.dumps(process_owner),
        )
        journal = EventJournal(self.run_directory / "events.jsonl", self.run_directory / "state.json")
        journal.append(
            "cleanup_registered",
            {
                "cleanup_id": "cleanup-legacy", "kind": "process",
                "target": "pid=99999999 children=100,101", "owner": "old-orca-owner",
            },
            coordinator_generation=2,
        )
        self.run_cli(
            "cleanup-retain", "--change", "portable", "--run-id", "run-1", "--generation", "2",
            "--cleanup-id", "cleanup-legacy", "--receipt", "{}", "--reason", "Legacy target was not a root PID.",
            "--replacement-cleanup-id", "cleanup-replacement",
        )
        replayed = journal.verify_projection()["cleanup"]
        self.assertEqual(replayed["cleanup-legacy"]["target"], "pid=99999999 children=100,101")
        self.assertEqual(replayed["cleanup-legacy"]["status"], "retained")
        self.assertEqual(replayed["cleanup-legacy"]["receipt"]["replacement_cleanup_id"], "cleanup-replacement")

    def test_cleans_lingering_owned_tree_on_root_exit_and_interrupt(self) -> None:
        marker = self.repository / "lingering-child.pid"
        root_exits = (
            "import pathlib, subprocess, sys; "
            "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); "
            "pathlib.Path(sys.argv[1]).write_text(str(child.pid)); print(child.pid, flush=True)"
        )
        result = run_bounded_command(
            [sys.executable, "-c", root_exits, str(marker)], cwd=self.repository, timeout_seconds=3,
        )
        child_id = int(marker.read_text(encoding="utf-8"))
        self.assertEqual(result.exit_code, 0)
        self.assertFalse(result.residue_unverifiable)
        with self.assertRaises(ProcessLookupError):
            os.kill(child_id, 0)

        interrupted_marker = self.repository / "interrupted-child.pid"
        original_wait = subprocess.Popen.wait
        raised = False

        def interrupt_once(process, *arguments, **keywords):
            nonlocal raised
            if not raised:
                raised = True
                time.sleep(0.15)
                raise KeyboardInterrupt
            return original_wait(process, *arguments, **keywords)

        with patch.object(subprocess.Popen, "wait", new=interrupt_once):
            with self.assertRaises(KeyboardInterrupt):
                run_bounded_command(
                    [sys.executable, "-c", root_exits, str(interrupted_marker)],
                    cwd=self.repository, timeout_seconds=3,
                )
        interrupted_child = int(interrupted_marker.read_text(encoding="utf-8"))
        with self.assertRaises(ProcessLookupError):
            os.kill(interrupted_child, 0)

    @unittest.skipUnless(os.name == "posix", "POSIX gate handoff is required")
    def test_publishes_process_authority_before_releasing_the_target_gate(self) -> None:
        marker = self.repository / "target-ran"
        observed: list[Mapping[str, object]] = []

        def published(identity: Mapping[str, object]) -> None:
            observed.append(identity)
            self.assertFalse(marker.exists(), "target executed before durable ownership publication")

        result = run_bounded_command(
            [
                sys.executable,
                "-c",
                "from pathlib import Path; import sys; Path(sys.argv[1]).write_text('ran')",
                str(marker),
            ],
            cwd=self.repository,
            timeout_seconds=2,
            on_started=published,
        )
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(len(observed), 1)
        self.assertIsInstance(observed[0]["process_root"], int)
        self.assertEqual(observed[0]["process_group"], observed[0]["process_root"])
        self.assertTrue(marker.is_file())

    @unittest.skipUnless(os.name == "posix", "POSIX process groups are required")
    def test_recovers_publicly_after_owner_crashes_on_both_sides_of_the_gate(self) -> None:
        projection = EventJournal(
            self.run_directory / "events.jsonl", self.run_directory / "state.json"
        ).verify_projection()
        owner_script = self.repository / "gate-owner.py"
        owner_script.write_text(
            "import json, sys, time\n"
            "from pathlib import Path\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "from validation import run_shared_check\n"
            "config = json.loads(Path(sys.argv[2]).read_text())\n"
            "def published(record):\n"
            "    Path(config['published']).write_text(json.dumps(dict(record)))\n"
            "    while config['phase'] == 'before' and not Path(config['release']).exists():\n"
            "        time.sleep(0.01)\n"
            "run_shared_check(\n"
            "    config['target'], repository=Path(config['repository']),\n"
            "    workspace=Path(config['workspace']), run_directory=Path(config['run_directory']),\n"
            "    workspace_scope=config['workspace_scope'], base_revision=config['base_revision'],\n"
            "    owner_generation=2, timeout_seconds=30,\n"
            "    consumer_ref='attempt:ROOT-01:attempt-root-01-001', on_running=published,\n"
            ")\n",
            encoding="utf-8",
        )

        def wait_for(path: Path) -> None:
            deadline = time.monotonic() + 5
            while not path.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(path.exists(), f"timed out waiting for {path.name}")

        def wait_for_group_exit(process_group: int) -> None:
            deadline = time.monotonic() + 5
            while validation._process_group_is_live(process_group) and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertFalse(validation._process_group_is_live(process_group))

        for phase in ("before", "after"):
            published = self.repository / f"gate-{phase}-published.json"
            release = self.repository / f"gate-{phase}-release"
            target_marker = self.repository / f"gate-{phase}-target"
            child_marker = self.repository / f"gate-{phase}-child"
            config_path = self.repository / f"gate-{phase}.json"
            target = [
                sys.executable,
                "-c",
                "from pathlib import Path; import subprocess, sys, time; "
                "Path(sys.argv[1]).write_text('started'); "
                "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); "
                "Path(sys.argv[2]).write_text(str(child.pid)); time.sleep(30)",
                str(target_marker),
                str(child_marker),
            ]
            config_path.write_text(
                json.dumps(
                    {
                        "phase": phase,
                        "published": str(published),
                        "release": str(release),
                        "target": target,
                        "repository": str(self.repository),
                        "workspace": str(self.repository),
                        "run_directory": str(self.run_directory),
                        "workspace_scope": projection["workspace_scope"],
                        "base_revision": projection["base_commit"],
                    }
                ),
                encoding="utf-8",
            )
            owner = subprocess.Popen(
                [sys.executable, str(owner_script), str(SCRIPT.parent), str(config_path)],
                cwd=self.repository,
            )
            wait_for(published)
            record = json.loads(published.read_text(encoding="utf-8"))
            self.assertEqual(record["cleanup_authority"], "process_group")
            self.assertEqual(record["process_group"], record["process_root"])
            if phase == "before":
                owner.kill()
                owner.wait(timeout=5)
                self.assertFalse(target_marker.exists(), "target escaped before gate release")
                wait_for_group_exit(record["process_group"])
            else:
                wait_for(target_marker)
                wait_for(child_marker)
                owner.kill()
                owner.wait(timeout=5)
                os.killpg(record["process_group"], signal.SIGKILL)
                wait_for_group_exit(record["process_group"])
                with self.assertRaises(ProcessLookupError):
                    os.kill(int(child_marker.read_text(encoding="utf-8")), 0)

            recovered = self.run_cli(
                "recover-check-execution", "--change", "portable", "--run-id", "run-1",
                "--generation", "2", "--execution-id", record["execution_id"],
            )
            self.assertEqual(json.loads(recovered.stdout)["result"]["lifecycle"], "failed_verified")
            cleanup = json.loads((self.repository / record["cleanup_ref"]).read_text(encoding="utf-8"))
            self.assertEqual(cleanup["status"], "verified_absent")

    @unittest.skipUnless(os.name == "posix", "POSIX process groups are required")
    def test_recovery_refuses_an_orphan_that_still_owns_the_persisted_group(self) -> None:
        marker = self.repository / "orphan-child.pid"
        root = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import pathlib, subprocess, sys; "
                "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); "
                "pathlib.Path(sys.argv[1]).write_text(str(child.pid)); import time; time.sleep(0.2)",
                str(marker),
            ],
            start_new_session=True,
        )
        deadline = time.monotonic() + 5
        start_identity = None
        while time.monotonic() < deadline:
            start_identity = validation._process_start_identity(root.pid)
            if start_identity is not None:
                break
            time.sleep(0.01)
        root.wait(timeout=5)
        child_id = int(marker.read_text(encoding="utf-8"))
        self.assertTrue(validation._process_group_is_live(root.pid))
        execution_id = "check-0123456789abcdef01234567"
        executions = self.run_directory / "artifacts/check-executions"
        artifact_ref = f"openspec/runs/portable/run-1/artifacts/check-executions/results/{execution_id}.json"
        cleanup_ref = f"openspec/runs/portable/run-1/artifacts/check-executions/cleanup/{execution_id}.json"
        artifact = self.repository / artifact_ref
        artifact.parent.mkdir(parents=True)
        artifact.write_text(json.dumps({
            "exit_code": 124, "duration_ms": 1, "timed_out": True,
            "residue_unverifiable": True, "start_error": None,
        }), encoding="utf-8")
        cleanup = self.repository / cleanup_ref
        cleanup.parent.mkdir(parents=True)
        cleanup.write_text(json.dumps({"status": "unverifiable"}), encoding="utf-8")
        self.assertIsNotNone(start_identity)
        record = {
            "execution_id": execution_id,
            "command_digest": "sha256:" + "0" * 64,
            "source_snapshot_digest": "sha256:" + "1" * 64,
            "execution_policy_digest": "sha256:" + "2" * 64,
            "timeout_seconds": 1.0,
            "output_cap_bytes": 1,
            "owner_generation": 2,
            "lifecycle": "blocked",
            "artifact_ref": artifact_ref,
            "cleanup_ref": cleanup_ref,
            "cleanup_id": f"check-cleanup-{execution_id}",
            "consumer_refs": ["attempt:ROOT-01:attempt-root-01-001"],
            "process_root": root.pid,
            "process_group": root.pid,
            "process_start_identity": start_identity,
            "cleanup_authority": "process_group",
            "cleanup_authority_id": None,
        }
        record_path = executions / f"{execution_id}.json"
        record_path.parent.mkdir(parents=True, exist_ok=True)
        record_path.write_text(json.dumps(record), encoding="utf-8")
        try:
            with self.assertRaisesRegex(CheckExecutionError, "process group"):
                recover_shared_check(
                    repository=self.repository,
                    run_directory=self.run_directory,
                    execution_id=execution_id,
                )
            self.assertEqual(json.loads(record_path.read_text(encoding="utf-8"))["lifecycle"], "blocked")
            self.assertEqual(json.loads(cleanup.read_text(encoding="utf-8"))["status"], "unverifiable")
        finally:
            os.killpg(root.pid, signal.SIGKILL)
            deadline = time.monotonic() + 5
            while validation._process_group_is_live(root.pid) and time.monotonic() < deadline:
                time.sleep(0.05)
        with self.assertRaises(ProcessLookupError):
            os.kill(child_id, 0)

    def test_recovery_keeps_the_journal_and_side_record_retryable_across_append_failures(self) -> None:
        execution_id = "check-abcdef0123456789abcdef01"
        artifacts = self.run_directory / "artifacts/check-executions"
        artifact_ref = f"openspec/runs/portable/run-1/artifacts/check-executions/results/{execution_id}.json"
        cleanup_ref = f"openspec/runs/portable/run-1/artifacts/check-executions/cleanup/{execution_id}.json"
        artifact = self.repository / artifact_ref
        artifact.parent.mkdir(parents=True)
        artifact.write_text(json.dumps({
            "exit_code": 124, "duration_ms": 1, "timed_out": True,
            "residue_unverifiable": True, "start_error": None,
        }), encoding="utf-8")
        cleanup = self.repository / cleanup_ref
        cleanup.parent.mkdir(parents=True)
        cleanup.write_text(json.dumps({"status": "unverifiable"}), encoding="utf-8")
        record = {
            "execution_id": execution_id,
            "command_digest": "sha256:" + "0" * 64,
            "source_snapshot_digest": "sha256:" + "1" * 64,
            "execution_policy_digest": "sha256:" + "2" * 64,
            "timeout_seconds": 1.0,
            "output_cap_bytes": 1,
            "owner_generation": 2,
            "lifecycle": "blocked",
            "artifact_ref": artifact_ref,
            "cleanup_ref": cleanup_ref,
            "cleanup_id": f"check-cleanup-{execution_id}",
            "consumer_refs": ["attempt:ROOT-01:attempt-root-01-001"],
            "process_root": 99999999,
            "process_group": 99999999,
            "process_start_identity": "gone",
            "cleanup_authority": "process_group",
            "cleanup_authority_id": None,
        }
        record_path = artifacts / f"{execution_id}.json"
        record_path.parent.mkdir(parents=True, exist_ok=True)
        record_path.write_text(json.dumps(record), encoding="utf-8")
        journal = EventJournal(self.run_directory / "events.jsonl", self.run_directory / "state.json")
        binding = {
            **record,
            "lifecycle": "running",
            "consumer_ref": record["consumer_refs"][0],
        }
        del binding["consumer_refs"]
        journal.append("check_execution_recorded", binding, coordinator_generation=2)
        journal.append("check_execution_recorded", {**binding, "lifecycle": "blocked"}, coordinator_generation=2)
        arguments = argparse.Namespace(
            repo=self.repository, change="portable", run_id="run-1", generation=2,
            execution_id=execution_id,
        )
        # Patch the class owned by the CLI module.  Other test modules load a
        # fresh graph_core module while discovery is importing tests, so the
        # locally imported EventJournal may not be the class command_recover_check
        # actually constructs.
        original_append = runtime.EventJournal.append

        def reject_recovery_append(self, event_type, data, *, coordinator_generation, timestamp=None):
            if event_type == "check_execution_recovered":
                raise JournalError("simulated append rejection")
            return original_append(self, event_type, data, coordinator_generation=coordinator_generation, timestamp=timestamp)

        with patch.object(runtime.EventJournal, "append", new=reject_recovery_append):
            with self.assertRaises(JournalError):
                runtime.command_recover_check(arguments)
        self.assertEqual(json.loads(record_path.read_text(encoding="utf-8"))["lifecycle"], "blocked")
        self.assertEqual(json.loads(cleanup.read_text(encoding="utf-8"))["status"], "verified_absent")

        prepared = recover_shared_check(
            repository=self.repository, run_directory=self.run_directory, execution_id=execution_id,
        )
        swapped = json.loads(record_path.read_text(encoding="utf-8"))
        swapped["command_digest"] = "sha256:" + "3" * 64
        record_path.write_text(json.dumps(swapped), encoding="utf-8")
        with self.assertRaisesRegex(CheckExecutionError, "identity changed"):
            finalize_shared_check_recovery(
                repository=self.repository, run_directory=self.run_directory, prepared=prepared,
            )
        self.assertEqual(json.loads(record_path.read_text(encoding="utf-8"))["lifecycle"], "blocked")
        self.assertEqual(json.loads(cleanup.read_text(encoding="utf-8"))["status"], "verified_absent")
        record_path.write_text(json.dumps(record), encoding="utf-8")

        with patch.object(runtime, "finalize_shared_check_recovery", side_effect=CheckExecutionError("simulated crash")):
            with self.assertRaises(runtime.AgentGraphCliError):
                runtime.command_recover_check(arguments)
        self.assertEqual(json.loads(record_path.read_text(encoding="utf-8"))["lifecycle"], "blocked")
        self.assertEqual(journal.verify_projection()["check_executions"][execution_id]["lifecycle"], "failed_verified")
        self.assertEqual(json.loads(record_path.read_text(encoding="utf-8"))["lifecycle"], "failed_verified")

        recovered = self.run_cli(
            "recover-check-execution", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--execution-id", execution_id,
        )
        self.assertEqual(json.loads(recovered.stdout)["result"]["lifecycle"], "failed_verified")
        self.assertEqual(json.loads(record_path.read_text(encoding="utf-8"))["lifecycle"], "failed_verified")
        self.assertEqual(json.loads(cleanup.read_text(encoding="utf-8"))["status"], "verified_absent")
        replayed = self.run_cli(
            "recover-check-execution", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--execution-id", execution_id,
        )
        self.assertEqual(json.loads(replayed.stdout)["result"]["lifecycle"], "failed_verified")
        events = [json.loads(line) for line in (self.run_directory / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(sum(event["type"] == "check_execution_recovered" for event in events), 1)

    def test_recovers_publicly_after_running_publication_failure(self) -> None:
        journal = EventJournal(self.run_directory / "events.jsonl", self.run_directory / "state.json")
        projection = journal.verify_projection()

        def reject_running_publication(_record: Mapping[str, object]) -> None:
            raise JournalError("simulated running publication failure")

        with self.assertRaisesRegex(CheckExecutionError, "public recovery"):
            run_shared_check(
                [sys.executable, "-c", "import time; time.sleep(1)"],
                repository=self.repository,
                workspace=self.repository,
                run_directory=self.run_directory,
                workspace_scope=projection["workspace_scope"],
                base_revision=projection["base_commit"],
                owner_generation=2,
                timeout_seconds=2,
                consumer_ref="attempt:ROOT-01:attempt-root-01-001",
                on_running=reject_running_publication,
            )
        record_path = next((self.run_directory / "artifacts/check-executions").glob("check-*.json"))
        record = json.loads(record_path.read_text(encoding="utf-8"))
        self.assertEqual(record["lifecycle"], "blocked")
        recovered = self.run_cli(
            "recover-check-execution", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--execution-id", record["execution_id"],
        )
        self.assertEqual(json.loads(recovered.stdout)["result"]["lifecycle"], "failed_verified")
        self.assertEqual(
            journal.verify_projection()["check_executions"][record["execution_id"]]["lifecycle"],
            "failed_verified",
        )
        self.assertEqual(json.loads(record_path.read_text(encoding="utf-8"))["lifecycle"], "failed_verified")

    def test_rejects_a_stale_owner_before_it_rewrites_completion_artifacts(self) -> None:
        journal = EventJournal(self.run_directory / "events.jsonl", self.run_directory / "state.json")
        projection = journal.verify_projection()
        published = threading.Event()
        release_owner = threading.Event()
        failures: list[BaseException] = []

        def pause_after_running(_record: Mapping[str, object]) -> None:
            published.set()
            self.assertTrue(release_owner.wait(timeout=5))

        def run_owner() -> None:
            try:
                run_shared_check(
                    [sys.executable, "-c", "import time; time.sleep(0.1)"],
                    repository=self.repository,
                    workspace=self.repository,
                    run_directory=self.run_directory,
                    workspace_scope=projection["workspace_scope"],
                    base_revision=projection["base_commit"],
                    owner_generation=2,
                    timeout_seconds=2,
                    consumer_ref="attempt:ROOT-01:attempt-root-01-001",
                    on_running=pause_after_running,
                )
            except BaseException as error:
                failures.append(error)

        owner = threading.Thread(target=run_owner)
        owner.start()
        self.assertTrue(published.wait(timeout=5))
        record_path = next((self.run_directory / "artifacts/check-executions").glob("check-*.json"))
        record = json.loads(record_path.read_text(encoding="utf-8"))
        original_identity = {
            field: record[field]
            for field in (
                "execution_id", "command_digest", "source_snapshot_digest",
                "execution_policy_digest", "timeout_seconds", "output_cap_bytes",
                "artifact_ref", "cleanup_ref", "cleanup_id", "process_root",
                "process_group", "process_start_identity", "cleanup_authority",
                "cleanup_authority_id", "lifecycle",
            )
        }
        record["owner_generation"] += 1
        record_path.write_text(json.dumps(record), encoding="utf-8")
        release_owner.set()
        owner.join(timeout=5)
        self.assertFalse(owner.is_alive())
        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], CheckExecutionError)
        self.assertEqual(
            json.loads(record_path.read_text(encoding="utf-8"))["owner_generation"], 3
        )
        self.assertEqual(
            {
                field: json.loads(record_path.read_text(encoding="utf-8"))[field]
                for field in original_identity
            },
            original_identity,
        )
        self.assertFalse((self.repository / record["artifact_ref"]).exists())
        cleanup = json.loads((self.repository / record["cleanup_ref"]).read_text(encoding="utf-8"))
        self.assertEqual(cleanup["status"], "registered")

    def test_reports_windows_cleanup_proof_failures(self) -> None:
        class Process:
            pid = 11

            @staticmethod
            def poll():
                return None

        with patch.object(runtime.os, "name", "nt"), patch("validation.os.name", "nt"):
            verified = _WindowsJob(1, lambda handle: True)
            self.assertFalse(_terminate_process_tree(Process(), verified))
            unverifiable = _WindowsJob(1, lambda handle: False)
            self.assertTrue(_terminate_process_tree(Process(), unverifiable))

    def test_persists_windows_authority_before_resuming_or_fails_closed(self) -> None:
        class Process:
            def __init__(self) -> None:
                self.pid = 91
                self._handle = 92
                self.stdout = io.BytesIO()
                self.stderr = io.BytesIO()
                self.returncode = None

            def wait(self, timeout=None):
                self.returncode = 0
                return 0

            def poll(self):
                return self.returncode

        ordering: list[str] = []
        creation_flags: list[int] = []
        published: list[Mapping[str, object]] = []
        job = _WindowsJob(1, lambda handle: True, authority_id="job-91")
        def created(*args, **keywords):
            ordering.append("popen")
            creation_flags.append(keywords["creationflags"])
            return Process()
        with patch("validation.os.name", "nt"), \
             patch("validation.subprocess.Popen", side_effect=created), \
             patch("validation._create_windows_job", side_effect=lambda process, authority_id: (ordering.append("assign"), job)[1]), \
             patch("validation._resume_windows_process", side_effect=lambda process: (ordering.append("resume"), True)[1]):
            result = run_bounded_command(
                ["ignored"],
                cwd=self.repository,
                timeout_seconds=1,
                on_started=lambda identity: (ordering.append("persist"), published.append(identity)),
            )
        self.assertEqual(ordering[:4], ["popen", "assign", "persist", "resume"])
        self.assertNotEqual(creation_flags[0] & 0x00000004, 0)
        self.assertEqual(published[0]["process_root"], 91)
        self.assertEqual(published[0]["cleanup_authority"], "job_object")
        self.assertEqual(published[0]["cleanup_authority_id"], "job-91")
        self.assertIsNone(result.start_error)

        ordering = []
        with patch("validation.os.name", "nt"), \
             patch("validation.subprocess.Popen", side_effect=lambda *args, **kwargs: (ordering.append("popen"), Process())[1]), \
             patch("validation._create_windows_job", side_effect=lambda process, authority_id: (ordering.append("assign"), None)[1]), \
             patch("validation._resume_windows_process", side_effect=lambda process: (ordering.append("resume"), True)[1]), \
             patch("validation.subprocess.run", return_value=type("Done", (), {"returncode": 0})()):
            failed = run_bounded_command(["ignored"], cwd=self.repository, timeout_seconds=1)
        self.assertEqual(ordering, ["popen", "assign"])
        self.assertEqual(failed.start_error, "windows_job_setup_failed")
        self.assertTrue(failed.residue_unverifiable)

    def test_blocks_consistency_sensitive_readers_during_the_append_projection_window(self) -> None:
        journal = EventJournal(self.run_directory / "events.jsonl", self.run_directory / "state.json")
        baseline = journal.verify_projection()["last_sequence"]
        entered = threading.Event()
        release = threading.Event()
        failures: list[BaseException] = []
        original_write = graph_core.atomic_write_json

        def paused_write(path, value):
            if Path(path) == journal.projection_path and value.get("last_sequence") == baseline + 1:
                entered.set()
                if not release.wait(5):
                    raise RuntimeError("append pause was not released")
            return original_write(path, value)

        def append() -> None:
            try:
                journal.append("journal_repaired", {"artifact": "paused", "discarded_bytes": 1}, coordinator_generation=2)
            except BaseException as error:
                failures.append(error)

        with patch.object(graph_core, "atomic_write_json", side_effect=paused_write):
            writer = threading.Thread(target=append)
            writer.start()
            self.assertTrue(entered.wait(2))
            verified = subprocess.Popen(
                [sys.executable, str(SCRIPT), "status", "--repo", str(self.repository), "--json", "--change", "portable", "--run-id", "run-1"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            watched = subprocess.Popen(
                [sys.executable, str(SCRIPT), "status", "--repo", str(self.repository), "--json", "--change", "portable", "--run-id", "run-1", "--watch", "--iterations", "1"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            time.sleep(0.15)
            self.assertIsNone(verified.poll())
            self.assertIsNone(watched.poll())
            release.set()
            writer.join(timeout=5)
        self.assertFalse(failures)
        verified_stdout, verified_stderr = verified.communicate(timeout=5)
        watched_stdout, watched_stderr = watched.communicate(timeout=5)
        self.assertEqual(verified.returncode, 0, verified_stderr)
        self.assertEqual(watched.returncode, 0, watched_stderr)
        self.assertEqual(json.loads(verified_stdout)["result"]["last_sequence"], baseline + 1)
        self.assertEqual(json.loads(watched_stdout)["cursor"], baseline + 1)
