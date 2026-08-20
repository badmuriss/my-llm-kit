import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from drivers.base import DriverError  # noqa: E402
from drivers.orca import OrcaDriver, resolve_orca_command  # noqa: E402


class FakeOrca:
    def __init__(
        self,
        repository: Path,
        *,
        supervised_error: str | None = None,
        minimal_create_receipt: bool = False,
    ) -> None:
        self.repository = repository
        self.supervised_error = supervised_error
        self.minimal_create_receipt = minimal_create_receipt
        self.dispatch_exists = True
        self.dispatch_error: str | None = None
        self.dispatch_identity_override: dict[str, str] = {}
        self.calls: list[list[str]] = []
        self.live = {"term-old"}
        self.incarnation = {
            "handle": "term-new",
            "ptyId": "pty-1",
            "incarnationId": "inc-1",
            "worktreeId": f"repo-1::{repository}",
            "worktreePath": str(repository),
            "tabId": "tab-1",
            "leafId": "leaf-1",
        }

    def __call__(self, argv):
        arguments = list(argv)[1:]
        self.calls.append(arguments)
        command = arguments[:2]
        if arguments[0] == "status":
            return {"ok": True, "result": {"runtime": {"reachable": True, "state": "ready", "capabilities": ["orchestration.contract.v1"]}, "graph": {"state": "ready"}}, "_meta": {"runtimeId": "runtime-1"}}
        if command == ["worktree", "current"]:
            return {"ok": True, "result": {"worktree": {"id": f"repo-1::{self.repository}", "path": str(self.repository)}}}
        if command == ["worktree", "show"]:
            return {"ok": True, "result": {"worktree": {"id": f"repo-1::{self.repository}", "path": str(self.repository)}}}
        if command == ["terminal", "list"]:
            items = []
            if "term-old" in self.live:
                items.append({"handle": "term-old"})
            if "term-new" in self.live:
                items.append({**self.incarnation, "title": "agent-graph-run-1-attempt-1"})
            return {"ok": True, "result": {"terminals": items}}
        if command == ["orchestration", "run-create"]:
            return {"ok": True, "result": {"id": "run-1"}}
        if command == ["orchestration", "task-create"]:
            count = sum(call[:2] == ["orchestration", "task-create"] for call in self.calls)
            return {"ok": True, "result": {"id": f"task-{count}"}}
        if command == ["orchestration", "worker-start"]:
            if self.supervised_error:
                return {"ok": False, "error": {"code": self.supervised_error, "message": "composition failed"}, "result": {"stage": "select", "effects": [], "residualResources": []}}
            return {"ok": True, "result": {"dispatchId": "dispatch-1", "worker": {"terminal": "worker-1"}}}
        if command == ["terminal", "create"]:
            self.live.add("term-new")
            if self.minimal_create_receipt:
                return {"ok": True, "result": {"agentTerminalHandle": "term-new"}}
            return {"ok": True, "result": self.incarnation}
        if command == ["terminal", "wait"]:
            return {"ok": True, "result": {"state": "tui-idle"}}
        if command == ["orchestration", "dispatch"]:
            if self.dispatch_error:
                return {
                    "ok": False,
                    "error": {"code": self.dispatch_error, "message": "dispatch failed"},
                }
            return {"ok": True, "result": {"id": "dispatch-low", "mutation": {"requestId": "run-1-attempt-1"}}}
        if command in (["orchestration", "worker-show"], ["orchestration", "dispatch-show"]):
            if command == ["orchestration", "dispatch-show"]:
                if not self.dispatch_exists:
                    return {
                        "ok": False,
                        "error": {"code": "dispatch_not_found", "message": "not found"},
                    }
                return {
                    "ok": True,
                    "result": {
                        "dispatch": {
                            "id": "dispatch-low",
                            "task_id": "task-1",
                            "assignee_handle": "term-new",
                            "assignee_pane_key": "tab-1:leaf-1",
                            "process_incarnation": f"repo-1::{self.repository}@@pty-1:inc-1",
                            "status": "completed",
                            **self.dispatch_identity_override,
                        }
                    },
                }
            return {"ok": True, "result": {"status": "completed"}}
        if command in (["orchestration", "worker-read"], ["terminal", "read"]):
            return {"ok": True, "result": {"cursor": "cursor-2", "text": "bounded"}}
        if command == ["orchestration", "check"]:
            return {"ok": True, "result": {"count": 0, "messages": []}}
        if command == ["orchestration", "reply"]:
            return {"ok": True, "result": {"messageId": "question-1", "status": "answered"}}
        if command == ["orchestration", "worker-release"]:
            return {"ok": True, "result": {"status": "released"}}
        if command == ["terminal", "show"]:
            return {"ok": True, "result": self.incarnation}
        if command == ["terminal", "close"]:
            self.live.discard("term-new")
            return {"ok": True, "result": {"closed": True, **self.incarnation}}
        raise AssertionError(f"unexpected fake Orca command: {arguments}")


class OrcaDriverBehavior(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repository = Path(self.temporary_directory.name).resolve()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def driver(self, fake: FakeOrca) -> OrcaDriver:
        return OrcaDriver(self.repository, runner=fake, environment={"ORCA_CLI_COMMAND": "fake-orca"})

    def test_starts_a_full_supervised_attempt(self) -> None:
        fake = FakeOrca(self.repository)
        driver = self.driver(fake)
        detected = driver.detect()
        started = driver.start_run(
            "Probe",
            [
                {"id": "ROOT-01", "depends": [], "capsule": "bounded"},
                {"id": "NEXT-02", "depends": ["ROOT-01"], "capsule": "dependent"},
            ],
        )
        attempt = driver.start_attempt({"task_id": "ROOT-01", "attempt_id": "attempt-1"})

        self.assertEqual(detected.status, "available")
        self.assertEqual(
            started.external_refs["task_ids"],
            {"ROOT-01": "task-1", "NEXT-02": "task-2"},
        )
        second_task_call = [
            call for call in fake.calls if call[:2] == ["orchestration", "task-create"]
        ][1]
        self.assertIn('["task-1"]', second_task_call)
        self.assertEqual(attempt.external_refs["tier"], "supervised")
        released = driver.release({"tier": "supervised", "dispatch_id": "dispatch-1"})
        self.assertEqual(released.status, "released")

    def test_falls_back_only_after_a_recognized_selector_failure(self) -> None:
        fake = FakeOrca(self.repository, supervised_error="selector_not_found")
        driver = self.driver(fake)
        driver.detect()
        driver.start_run("Probe", [{"id": "ROOT-01", "depends": [], "capsule": "bounded"}])

        attempt = driver.start_attempt({"task_id": "ROOT-01", "attempt_id": "attempt-1"})

        self.assertEqual(attempt.external_refs["tier"], "tracked-terminal")
        self.assertEqual(attempt.degradation["code"], "selector_not_found")
        self.assertIn("term-new", driver.created_terminals["attempt-1"]["handle"])

    def test_resolves_full_identity_after_a_handle_only_create_receipt(self) -> None:
        fake = FakeOrca(
            self.repository,
            supervised_error="selector_not_found",
            minimal_create_receipt=True,
        )
        driver = self.driver(fake)
        driver.detect()
        driver.start_run("Probe", [{"id": "ROOT-01", "depends": [], "capsule": "bounded"}])

        attempt = driver.start_attempt({"task_id": "ROOT-01", "attempt_id": "attempt-1"})

        self.assertEqual(attempt.external_refs["terminal"]["incarnation_id"], "inc-1")
        self.assertIn(["terminal", "show", "--terminal", "term-new", "--json"], fake.calls)

    def test_recovers_a_tracked_terminal_already_present_in_a_fresh_snapshot(self) -> None:
        fake = FakeOrca(self.repository, supervised_error="selector_not_found")
        first = self.driver(fake)
        first.detect()
        first.start_run("Probe", [{"id": "ROOT-01", "depends": [], "capsule": "bounded"}])
        first.start_attempt({"task_id": "ROOT-01", "attempt_id": "attempt-1"})

        resumed = self.driver(fake)
        resumed.detect()
        resumed.run_id = "run-1"
        resumed.task_ids = {"ROOT-01": "task-1"}
        recovered = resumed.start_attempt(
            {"task_id": "ROOT-01", "attempt_id": "attempt-1", "recover": True}
        )

        self.assertEqual(recovered.external_refs["terminal"]["handle"], "term-new")
        self.assertTrue(recovered.raw["recovered_terminal"])
        self.assertIn("term-new", resumed._terminal_snapshot)
        self.assertIsNotNone(recovered.raw["dispatch_show"])

    def test_recovery_rejects_a_replayed_dispatch_for_another_terminal(self) -> None:
        fake = FakeOrca(self.repository, supervised_error="selector_not_found")
        driver = self.driver(fake)
        driver.detect()
        driver.start_run("Probe", [{"id": "ROOT-01", "depends": [], "capsule": "bounded"}])
        fake.dispatch_identity_override = {
            "assignee_handle": "term-lost",
            "assignee_pane_key": "tab-lost:leaf-lost",
            "process_incarnation": f"repo-1::{self.repository}@@pty-lost:inc-lost",
        }

        with self.assertRaisesRegex(DriverError, "reserved Dispatch"):
            driver.start_attempt(
                {"task_id": "ROOT-01", "attempt_id": "attempt-1", "recover": True}
            )

        self.assertNotIn("term-new", fake.live)
        self.assertIn(
            ["terminal", "close", "--terminal", "term-new", "--tab", "--json"],
            fake.calls,
        )

    def test_closes_an_acquired_terminal_when_dispatch_fails(self) -> None:
        fake = FakeOrca(self.repository, supervised_error="selector_not_found")
        fake.dispatch_error = "delivery_failed"
        driver = self.driver(fake)
        driver.detect()
        driver.start_run("Probe", [{"id": "ROOT-01", "depends": [], "capsule": "bounded"}])

        with self.assertRaisesRegex(DriverError, "dispatch failed"):
            driver.start_attempt({"task_id": "ROOT-01", "attempt_id": "attempt-1"})

        self.assertNotIn("term-new", fake.live)
        self.assertIn(
            ["terminal", "close", "--terminal", "term-new", "--tab", "--json"],
            fake.calls,
        )

    def test_explicit_orca_fails_instead_of_switching_to_host(self) -> None:
        fake = FakeOrca(self.repository, supervised_error="authority_denied")
        driver = self.driver(fake)
        driver.detect()
        driver.start_run("Probe", [{"id": "ROOT-01", "depends": [], "capsule": "bounded"}])

        with self.assertRaisesRegex(DriverError, "composition failed"):
            driver.start_attempt({"task_id": "ROOT-01", "attempt_id": "attempt-1"})
        self.assertFalse(any(call[:2] == ["terminal", "create"] for call in fake.calls))

    def test_bounds_transcript_reads_and_replies_to_questions(self) -> None:
        fake = FakeOrca(self.repository, supervised_error="selector_not_found")
        driver = self.driver(fake)
        driver.detect()
        driver.start_run("Probe", [{"id": "ROOT-01", "depends": [], "capsule": "bounded"}])
        started = driver.start_attempt({"task_id": "ROOT-01", "attempt_id": "attempt-1"})
        refs = started.external_refs

        observed = driver.poll({"tier": refs["tier"], "dispatch_id": refs["dispatch_id"], "external_task_id": refs["task_id"], "terminal_handle": refs["terminal"]["handle"]}, cursor="cursor-1")
        replied = driver.send(
            {"external_refs": {"dispatch_id": refs["dispatch_id"], "run_id": refs["run_id"]}},
            {
                "kind": "reply",
                "message_id": "question-1",
                "body": "yes",
                "delivery_id": "delivery-1",
            },
        )
        acknowledged = driver.ack_delivery(refs["run_id"], "delivery-1")

        read_call = next(call for call in fake.calls if call[:2] == ["terminal", "read"])
        self.assertIn("50", read_call)
        self.assertIn("cursor-1", read_call)
        self.assertEqual(observed.external_refs["cursor"], "cursor-2")
        self.assertEqual(replied.status, "sent")
        self.assertTrue(acknowledged["ok"])
        self.assertIn("--ack", fake.calls[-1])

    def test_reconciles_attempts_without_treating_completion_as_a_grade(self) -> None:
        fake = FakeOrca(self.repository)
        driver = self.driver(fake)
        driver.detect()
        driver.start_run("Probe", [{"id": "ROOT-01", "depends": [], "capsule": "bounded"}])
        started = driver.start_attempt({"task_id": "ROOT-01", "attempt_id": "attempt-1"})

        reconciliation = driver.reconcile([{"attempt_id": "attempt-1", "tier": "supervised", "dispatch_id": started.external_refs["dispatch_id"]}])

        self.assertEqual(reconciliation.status, "observed")
        self.assertNotIn("grade", str(reconciliation.raw))

    def test_reconciliation_retains_a_reserved_terminal_created_before_dispatch(self) -> None:
        fake = FakeOrca(self.repository, supervised_error="selector_not_found")
        driver = self.driver(fake)
        driver.detect()
        driver.start_run("Probe", [{"id": "ROOT-01", "depends": [], "capsule": "bounded"}])
        fake.live.add("term-new")
        fake.dispatch_exists = False

        reconciliation = driver.reconcile(
            [{"attempt_id": "attempt-1", "task_id": "ROOT-01", "status": "reserved"}]
        )

        self.assertEqual(reconciliation.raw[0]["resource_state"], "present")

    def test_closes_only_the_same_created_terminal_incarnation(self) -> None:
        fake = FakeOrca(self.repository, supervised_error="selector_not_found")
        driver = self.driver(fake)
        driver.detect()
        driver.start_run("Probe", [{"id": "ROOT-01", "depends": [], "capsule": "bounded"}])
        started = driver.start_attempt({"task_id": "ROOT-01", "attempt_id": "attempt-1"})
        refs = started.external_refs

        released = driver.release({"attempt_id": "attempt-1", "tier": "tracked-terminal", "dispatch_id": refs["dispatch_id"]})

        self.assertEqual(released.status, "released")
        self.assertNotIn("term-new", fake.live)
        self.assertIn(["terminal", "close", "--terminal", "term-new", "--tab", "--json"], fake.calls)

        fake2 = FakeOrca(self.repository, supervised_error="selector_not_found")
        driver2 = self.driver(fake2)
        driver2.detect()
        driver2.start_run("Probe", [{"id": "ROOT-01", "depends": [], "capsule": "bounded"}])
        refs2 = driver2.start_attempt({"task_id": "ROOT-01", "attempt_id": "attempt-1"}).external_refs
        fake2.incarnation["incarnationId"] = "replaced"
        with self.assertRaisesRegex(DriverError, "incarnation changed"):
            driver2.release({"attempt_id": "attempt-1", "tier": "tracked-terminal", "dispatch_id": refs2["dispatch_id"]})
        self.assertIn("term-new", fake2.live)

    def test_treats_an_absent_recorded_terminal_as_prior_cleanup(self) -> None:
        fake = FakeOrca(self.repository, supervised_error="selector_not_found")
        driver = self.driver(fake)
        driver.detect()
        driver.start_run("Probe", [{"id": "ROOT-01", "depends": [], "capsule": "bounded"}])
        refs = driver.start_attempt(
            {"task_id": "ROOT-01", "attempt_id": "attempt-1"}
        ).external_refs
        fake.live.discard("term-new")

        released = driver.release(
            {
                "attempt_id": "attempt-1",
                "tier": "tracked-terminal",
                "dispatch_id": refs["dispatch_id"],
            }
        )

        self.assertTrue(released.external_refs["prior_cleanup"])
        self.assertEqual(released.raw["state"], "already_absent")


class CommandSelectionBehavior(unittest.TestCase):
    def test_pins_the_configured_command(self) -> None:
        self.assertEqual(resolve_orca_command({"ORCA_CLI_COMMAND": "wrapper --profile dev"}), ("wrapper", "--profile", "dev"))


if __name__ == "__main__":
    unittest.main()
