import argparse
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "agent_graph.py"
sys.path.insert(0, str(SCRIPT.parent))
import agent_graph as runtime  # noqa: E402


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
        subprocess.run(["git", "init", "-q", str(self.repository)], check=True)
        subprocess.run(["git", "-C", str(self.repository), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(self.repository), "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "-C", str(self.repository), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.repository), "commit", "-qm", "test fixture"], check=True)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def run_cli(self, command: str, *arguments: str):
        return subprocess.run(
            [sys.executable, str(SCRIPT), command, "--repo", str(self.repository), "--json", *arguments],
            check=False,
            capture_output=True,
            text=True,
        )

    def result(self, completed):
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)["result"]

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

    def test_takeover_fences_the_prior_generation(self) -> None:
        self.bootstrap_and_claim()
        takeover = self.result(
            self.run_cli(
                "takeover", "--change", "portable", "--run-id", "run-1",
                "--generation", "2", "--coordinator-id", "coordinator-2",
            )
        )
        self.assertEqual(takeover["coordinator_generation"], 3)

        stale = self.run_cli(
            "dispatch", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--task", "ROOT-01", "--local",
        )
        self.assertNotEqual(stale.returncode, 0)
        error = json.loads(stale.stderr)["error"]
        self.assertEqual(error["code"], "stale_coordinator")

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
                "checks_run": [],
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
            "checks_run": [],
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

    def test_rejects_shell_operators_before_execution(self) -> None:
        tasks = self.repository / "openspec/changes/portable/tasks.md"
        tasks.write_text(TASKS.replace(
            f'"{sys.executable}" -c "raise SystemExit(0)"',
            f'"{sys.executable}" -c "raise SystemExit(0)" && "{sys.executable}" -V',
            1,
        ), encoding="utf-8")
        self.bootstrap_and_claim()

        rejected = self.run_cli(
            "run-check", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--task", "ROOT-01",
        )

        self.assertNotEqual(rejected.returncode, 0)
        error = json.loads(rejected.stderr)["error"]
        self.assertIn("shell operator", error["message"])

    def test_blocks_pass_with_ungraded_tasks_and_pending_cleanup(self) -> None:
        self.bootstrap_and_claim()
        self.result(
            self.run_cli(
                "cleanup-register", "--change", "portable", "--run-id", "run-1",
                "--generation", "2", "--kind", "process", "--target", "99999999",
                "--owner", "coordinator-1",
            )
        )
        blocked = self.run_cli(
            "complete", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--outcome", "pass",
        )
        self.assertNotEqual(blocked.returncode, 0)
        self.assertEqual(json.loads(blocked.stderr)["error"]["code"], "cleanup_pending")

    def test_status_watch_reads_saved_projection(self) -> None:
        self.bootstrap_and_claim()
        status = self.result(
            self.run_cli(
                "status", "--change", "portable", "--run-id", "run-1",
                "--watch", "--iterations", "1", "--interval", "0",
            )
        )
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

    def test_blocks_frontend_completion_when_the_graph_omits_visuals(self) -> None:
        tasks = self.repository / "openspec/changes/portable/tasks.md"
        root_only = TASKS.split("\n- [ ] NEXT-02", 1)[0].replace("src/root.py", "src/App.tsx")
        tasks.write_text(root_only + "\n", encoding="utf-8")
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
            "checks_run": [],
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
        source = self.repository / "src/App.tsx"
        source.parent.mkdir(exist_ok=True)
        source.write_text("export const App = () => <main>Changed</main>;\n", encoding="utf-8")

        pass_result = self.run_cli(
            "complete", "--change", "portable", "--run-id", "run-1",
            "--generation", "2", "--outcome", "pass",
        )
        self.assertNotEqual(pass_result.returncode, 0)
        self.assertIn("frontend changes require Visual entries", pass_result.stderr)

    def test_sync_maps_real_orca_worker_done_and_releases_before_ack(self) -> None:
        graph = runtime.parse_task_graph(self.repository / "openspec/changes/portable/tasks.md")
        directory = runtime._new_run_directory(self.repository, "portable", "live-1")
        journal = runtime._journal(directory)
        projection = journal.append(
            "run_started",
            {
                "change": "portable",
                "run_id": "live-1",
                "coordinator_id": "coordinator-1",
                "coordinator_generation": 1,
                "base_commit": runtime._current_commit(self.repository),
                "dirty_paths": [],
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
            {"task_id": "ROOT-01", "attempt_id": "attempt-1", "driver": "orca"},
            coordinator_generation=1,
        )
        projection = journal.append(
            "attempt_started",
            {
                "task_id": "ROOT-01",
                "attempt_id": "attempt-1",
                "driver": "orca",
                "tier": "supervised",
                "external_refs": {
                    "tier": "supervised",
                    "run_id": "run-live",
                    "task_id": "task-live",
                    "dispatch_id": "ctx-live",
                },
                "cleanup_id": "cleanup-attempt-1",
            },
            coordinator_generation=1,
        )
        journal.append(
            "cleanup_registered",
            {"cleanup_id": "cleanup-attempt-1", "kind": "terminal", "target": "ctx-live", "owner": "attempt-1"},
            coordinator_generation=1,
        )
        journal.append("task_ready", {"task_id": "NEXT-02"}, coordinator_generation=1)
        journal.append(
            "attempt_reserved",
            {"task_id": "NEXT-02", "attempt_id": "attempt-2", "driver": "orca"},
            coordinator_generation=1,
        )
        journal.append(
            "attempt_started",
            {
                "task_id": "NEXT-02",
                "attempt_id": "attempt-2",
                "driver": "orca",
                "tier": "supervised",
                "external_refs": {
                    "tier": "supervised",
                    "run_id": "run-live",
                    "task_id": "task-next",
                    "dispatch_id": "ctx-next",
                },
                "cleanup_id": "cleanup-attempt-2",
            },
            coordinator_generation=1,
        )
        journal.append(
            "cleanup_registered",
            {"cleanup_id": "cleanup-attempt-2", "kind": "terminal", "target": "ctx-next", "owner": "attempt-2"},
            coordinator_generation=1,
        )

        class FakeLiveOrca(runtime.OrcaDriver):
            def __init__(self):
                self.actions = []
                self.run_id = "run-live"
                self.release_fails = True

            def poll(self, attempt, *, cursor=None, include_delivery=True):
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
                                    }
                                ),
                            }
                        ],
                    },
                }

            def release(self, attempt):
                self.actions.append("release")
                if self.release_fails:
                    self.release_fails = False
                    raise runtime.DriverError(
                        "release interrupted", code="connection_lost"
                    )
                return runtime.DriverReceipt("release", "released", raw={"state": "released"})

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
            with self.assertRaisesRegex(runtime.DriverError, "release interrupted"):
                runtime.command_sync(arguments)
            after_failure = runtime._projection(directory)
            self.assertEqual(
                after_failure["attempts"]["attempt-2"]["status"], "reported"
            )
            self.assertEqual(
                after_failure["cleanup"]["cleanup-attempt-2"]["status"], "pending"
            )
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
            result = runtime.command_sync(arguments)
        finally:
            runtime._driver_for_state = original

        self.assertEqual(result["state"]["tasks"]["ROOT-01"]["status"], "running")
        self.assertEqual(result["state"]["tasks"]["NEXT-02"]["status"], "reported")
        self.assertEqual(result["state"]["attempts"]["attempt-1"]["cursor"], "cursor-2")
        self.assertEqual(result["state"]["attempts"]["attempt-2"]["cursor"], "cursor-2")
        self.assertEqual(result["state"]["cleanup"]["cleanup-attempt-1"]["status"], "pending")
        self.assertEqual(result["state"]["cleanup"]["cleanup-attempt-2"]["status"], "done")
        self.assertTrue(recovered["finished"])
        self.assertFalse(recovered["idempotent"])
        self.assertEqual(fake.actions, ["release", "release", "ack"])

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
                    "checks_run": [],
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
        self.assertTrue(recovered_attempt["receipt"]["raw"]["replayed"])


if __name__ == "__main__":
    unittest.main()
