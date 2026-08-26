import json
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from drivers.base import DriverError  # noqa: E402
from drivers.orca import OrcaDriver, resolve_orca_command  # noqa: E402
from context_capsules import build_reused_session_handoff  # noqa: E402


def session_handoff(task_id: str) -> dict:
    return build_reused_session_handoff(
        task_id=task_id,
        acceptance="The current task is accepted.",
        dependency_summaries=[{"task_id": "ROOT-01", "summary": "The prior task passed."}],
        diff_since_previous_check=["src/first.py"],
        unresolved_material_finding_refs=[],
        allowed_paths=["src/next.py"],
        check="python3 -m unittest tests.test_next",
        session_memory={
            "decisions": ["Keep the task boundary narrow."],
            "invariants": ["The terminal remains owned by the same session."],
            "central_files": ["src/first.py"],
            "traps": [],
            "green_checks": ["python3 -m unittest tests.test_first"],
            "carry_forward_findings": [],
        },
    )


def active_session_terminal(refs: dict, cleanup_tier: str) -> dict:
    terminal = refs["reusable_session_terminal"] if cleanup_tier == "supervised" else refs["terminal"]
    return {
        "terminal": terminal,
        "execution_profile": refs["execution_profile"],
        "workspace_scope": refs["workspace_scope"],
        "lease_status": "active",
        "cleanup_tier": cleanup_tier,
    }


class FakeOrca:
    def __init__(
        self,
        repository: Path,
        *,
        supervised_error: str | None = None,
        minimal_create_receipt: bool = False,
        app_version: str | None = "1.4.186",
    ) -> None:
        self.repository = repository
        self.supervised_error = supervised_error
        self.minimal_create_receipt = minimal_create_receipt
        self.dispatch_exists = True
        self.dispatch_is_null = False
        self.dispatch_error: str | None = None
        self.omit_runtime_id = False
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
            "processRootId": "pty-1",
            "retentionPolicy": "auto_release",
        }
        self.worktree = {
            "id": f"repo-1::{repository}",
            "path": str(repository),
            "hostId": "host-local",
            "git": {"path": str(repository), "isMainWorktree": True},
            "isMainWorktree": True,
        }
        self.worker_profile: dict | None = None
        self.worker_launch_override: dict | None = None
        self.worker_start_error: str | None = None
        self.worker_dispatch_id: object = "dispatch-1"
        self.worker_effects: list[dict] | None = None
        self.dispatch_receipt_id: object = "dispatch-low"
        self.dynamic_dispatch = False
        self.terminal_send_error: str | None = None
        self.terminal_lease_capable = True
        self.app_version = app_version
        self.lease_delivery_state: str | None = "acknowledged"
        self.wait_result: dict = {
            "satisfied": True,
            "condition": "tui-idle",
            "status": "running",
        }
        self.session_predecessor = {"taskId": "task-1", "attemptId": "attempt-1", "dispatchId": "dispatch-1"}
        self.current_successor_lease_id: str | None = None

    def _attempt_id(self, arguments: list[str], suffix: str) -> str:
        retry_request = arguments[arguments.index("--retry-request") + 1]
        return retry_request.removeprefix("run-1-").removesuffix(suffix)

    def _participant(
        self, task_id: str, attempt_id: str, dispatch_id: str, lease_id: str
    ) -> dict:
        profile = self.worker_profile
        return {
            "runId": "run-1",
            "taskId": task_id,
            "attemptId": attempt_id,
            "dispatchId": dispatch_id,
            "terminalHandle": "term-new",
            "ptyIncarnation": "pty-1:inc-1",
            "paneKey": "tab-1:leaf-1",
            "executionHostId": "host-local",
            "workspaceKey": f"worktree:repo-1::{self.repository}",
            "coordinatorGeneration": 1,
            "processRootId": "pty-1",
            "retentionPolicy": "auto_release",
            "ownerPrincipal": f"dispatch:{dispatch_id}",
            "leaseId": lease_id,
            "hostScope": None,
            "launchProfile": {
                "agent": profile["resolved"]["agent"],
                "model": profile["resolved"]["model"],
                "effort": profile["resolved"]["effort"],
                "permissionMode": "yolo",
                "routeRef": None,
            },
        }

    def __call__(self, argv):
        arguments = list(argv)[1:]
        self.calls.append(arguments)
        command = arguments[:2]
        if arguments[0] == "status":
            meta = {} if self.omit_runtime_id else {"runtimeId": "runtime-1"}
            capabilities = ["orchestration.contract.v1", "orchestration.worker-launch-preferences.v1"]
            if self.terminal_lease_capable:
                capabilities.append("maestro.terminal-lease.v1")
            runtime = {
                "reachable": True,
                "state": "ready",
                "capabilities": capabilities,
                **({"appVersion": self.app_version} if self.app_version is not None else {}),
            }
            return {"ok": True, "result": {"runtime": runtime, "graph": {"state": "ready"}}, "_meta": meta}
        if command == ["worktree", "current"]:
            return {"ok": True, "result": {"worktree": self.worktree}}
        if command == ["worktree", "show"]:
            return {"ok": True, "result": {"worktree": self.worktree}}
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
        if command == ["orchestration", "task-update"]:
            task_id = arguments[arguments.index("--id") + 1]
            status = arguments[arguments.index("--status") + 1]
            return {"ok": True, "result": {"task": {"id": task_id, "status": status}}}
        if command == ["orchestration", "worker-start"]:
            if "--terminal" in arguments:
                terminal = arguments[arguments.index("--terminal") + 1]
                task_id = arguments[arguments.index("--task") + 1]
                if terminal != "term-new":
                    return {"ok": False, "error": {"code": "terminal_not_owned", "message": "wrong terminal"}}
                dispatch_id = f"dispatch-{task_id}" if self.dynamic_dispatch else self.worker_dispatch_id
                attempt_id = self._attempt_id(arguments, "-dispatch")
                predecessor_lease_id = self.current_successor_lease_id or "lease-predecessor"
                successor_lease_id = f"lease-{task_id}"
                predecessor = self._participant(
                    self.session_predecessor["taskId"],
                    self.session_predecessor["attemptId"],
                    self.session_predecessor["dispatchId"],
                    predecessor_lease_id,
                )
                successor = self._participant(task_id, attempt_id, dispatch_id, successor_lease_id)
                self.current_successor_lease_id = successor_lease_id
                self.session_predecessor = {"taskId": task_id, "attemptId": attempt_id, "dispatchId": dispatch_id}
                return {
                    "ok": True,
                    "result": {
                        "dispatchId": dispatch_id,
                        "leaseTransfer": {
                            "version": 1,
                            "kind": "settled_resource_reuse",
                            "runId": "run-1",
                            "taskId": task_id,
                            "attemptId": attempt_id,
                            "terminalHandle": terminal,
                            "ptyIncarnation": "pty-1:inc-1",
                            "executionHostId": "host-local",
                            "workspaceKey": f"worktree:repo-1::{self.repository}",
                            "coordinatorGeneration": 1,
                            "processRootId": "pty-1",
                            "retentionPolicy": "auto_release",
                            "hostScope": None,
                            "predecessorOwnerPrincipal": f"dispatch:{predecessor['dispatchId']}",
                            "successorOwnerPrincipal": f"dispatch:{dispatch_id}",
                            "launchProfile": successor["launchProfile"],
                            "fromDispatchId": predecessor["dispatchId"],
                            "toDispatchId": dispatch_id,
                            "predecessorLeaseId": predecessor_lease_id,
                            "successorLeaseId": successor_lease_id,
                            "predecessor": predecessor,
                            "successor": successor,
                        },
                    },
                }
            if self.supervised_error:
                return {"ok": False, "error": {"code": self.supervised_error, "message": "composition failed"}, "result": {"stage": "select", "effects": [], "residualResources": []}}
            if self.worker_start_error:
                return {"ok": False, "error": {"code": self.worker_start_error, "message": "profile unsupported"}, "result": {"stage": "launch", "effects": [], "residualResources": []}}
            profile = self.worker_profile
            legacy_launch = {"requested": profile["resolved"], "effective": profile["resolved"]}
            lease_launch = {
                "requested": {**profile["resolved"], "permissionMode": "yolo", "executable": None},
                "effective": {**profile["resolved"], "permissionMode": "yolo", "executable": "codex"},
            }
            launch = self.worker_launch_override or (lease_launch if self.terminal_lease_capable else legacy_launch)
            worktree_id = arguments[arguments.index("--worktree") + 1].removeprefix("id:")
            effects = self.worker_effects if self.worker_effects is not None else [
                {"kind": "worktree", "action": "reused", "id": worktree_id}
            ]
            self.live.add("term-new")
            self.session_predecessor = {
                "taskId": arguments[arguments.index("--task") + 1],
                "attemptId": self._attempt_id(arguments, "-start"),
                "dispatchId": str(self.worker_dispatch_id),
            }
            return {"ok": True, "result": {"dispatchId": self.worker_dispatch_id, "worker": {"terminal": "worker-1"}, "launch": launch, "effects": effects}}
        if command == ["terminal", "create"]:
            self.live.add("term-new")
            if self.minimal_create_receipt:
                return {"ok": True, "result": {"agentTerminalHandle": "term-new"}}
            return {"ok": True, "result": self.incarnation}
        if command == ["terminal", "wait"]:
            return {"ok": True, "result": {"wait": dict(self.wait_result)}}
        if command == ["terminal", "send"]:
            if self.terminal_send_error:
                return {"ok": False, "error": {"code": self.terminal_send_error, "message": "delivery failed"}}
            text = arguments[arguments.index("--text") + 1]
            if "--lease-input" not in arguments:
                return {"ok": True, "result": {"send": {"handle": "term-new"}}}
            lease_input = json.loads(arguments[arguments.index("--lease-input") + 1])
            expected_keys = {"commandId", "idempotencyKey", "contentDigest", "enqueueSequence", "leaseId", "authority", "runId", "coordinatorGeneration", "expectedLifecycleState", "observedInputSurface", "expiresAt", "expectedGraphRevision"}
            if (
                set(lease_input) != expected_keys
                or lease_input["leaseId"] != self.current_successor_lease_id
                or lease_input["contentDigest"] != f"sha256:{hashlib.sha256(text.encode()).hexdigest()}"
                or lease_input["enqueueSequence"] != 2
                or lease_input["authority"] != "coordinator"
                or lease_input["runId"] != "run-1"
                or lease_input["coordinatorGeneration"] != 1
                or lease_input["expectedLifecycleState"] != "active"
                or lease_input["observedInputSurface"] != "working"
                or lease_input["expectedGraphRevision"] is not None
                or not all(isinstance(lease_input[field], str) and lease_input[field] for field in ("commandId", "idempotencyKey", "expiresAt"))
            ):
                return {"ok": False, "error": {"code": "lease_input_invalid", "message": "lease envelope diverged"}}
            delivery_receipt = (
                {"id": "delivery-1", "state": self.lease_delivery_state}
                if self.lease_delivery_state is not None
                else None
            )
            return {"ok": True, "result": {"send": {
                "handle": "term-new",
                **({"deliveryReceipt": delivery_receipt} if delivery_receipt is not None else {}),
            }}}
        if command == ["orchestration", "dispatch"]:
            if self.dispatch_error:
                return {
                    "ok": False,
                    "error": {"code": self.dispatch_error, "message": "dispatch failed"},
                }
            task_id = arguments[arguments.index("--task") + 1]
            dispatch_id = f"dispatch-{task_id}" if self.dynamic_dispatch else self.dispatch_receipt_id
            self.session_predecessor = {"taskId": task_id, "attemptId": self._attempt_id(arguments, "-dispatch"), "dispatchId": dispatch_id}
            return {"ok": True, "result": {"id": dispatch_id, "mutation": {"requestId": "run-1-attempt-1"}}}
        if command in (["orchestration", "worker-show"], ["orchestration", "dispatch-show"]):
            if command == ["orchestration", "dispatch-show"]:
                requested_task = arguments[arguments.index("--task") + 1]
                if not self.dispatch_exists:
                    return {
                        "ok": False,
                        "error": {"code": "dispatch_not_found", "message": "not found"},
                    }
                if self.dispatch_is_null:
                    return {"ok": True, "result": {"dispatch": None}}
                return {
                    "ok": True,
                    "result": {
                        "dispatch": {
                            "id": f"dispatch-{requested_task}" if self.dynamic_dispatch else "dispatch-low",
                            "task_id": requested_task if self.dynamic_dispatch else "task-1",
                            "assignee_handle": "term-new",
                            "assignee_pane_key": "tab-1:leaf-1",
                            "process_incarnation": f"repo-1::{self.repository}@@pty-1:inc-1",
                        "status": "completed",
                        **self.dispatch_identity_override,
                        }
                    },
                }
            dispatch_id = arguments[arguments.index("--dispatch") + 1]
            return {
                "ok": True,
                "result": {
                    "worker": {"dispatchId": dispatch_id, "terminal": self.incarnation, "launchProfile": self._participant("task-1", "attempt-1", dispatch_id, "lease-worker-show")["launchProfile"]},
                    "status": "completed",
                },
            }
        if command in (["orchestration", "worker-read"], ["terminal", "read"]):
            return {"ok": True, "result": {"cursor": "cursor-2", "text": "bounded"}}
        if command == ["orchestration", "check"]:
            return {"ok": True, "result": {"count": 0, "messages": []}}
        if command == ["orchestration", "reply"]:
            return {"ok": True, "result": {"messageId": "question-1", "status": "answered"}}
        if command == ["orchestration", "worker-release"]:
            return {"ok": True, "result": {"state": "released"}}
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

    def test_confirms_a_long_turn_from_the_versioned_send_acknowledgement(self) -> None:
        fake = FakeOrca(self.repository)
        driver = self.driver(fake)
        driver.detect()
        call_count = len(fake.calls)

        receipt = driver._send_terminal_handoff("term-new", "work for a long time")

        self.assertEqual(receipt["delivery_confirmation"]["kind"], "turn_started")
        commands = [call[:2] for call in fake.calls[call_count:]]
        self.assertEqual(commands, [["terminal", "send"]])

    def test_rejects_unversioned_and_older_send_acknowledgements(self) -> None:
        for version in (None, "1.4.185", "invalid"):
            with self.subTest(version=version):
                fake = FakeOrca(self.repository, app_version=version)
                driver = self.driver(fake)
                driver.detect()

                with self.assertRaises(DriverError) as error:
                    driver._send_terminal_handoff("term-new", "unit work")

                self.assertEqual(error.exception.code, "session_delivery_unproven")

    def test_requires_a_terminal_delivery_state_for_a_managed_lease(self) -> None:
        text = "continue the managed lease"
        lease_input = {
            "commandId": "command-1",
            "idempotencyKey": "key-1",
            "contentDigest": f"sha256:{hashlib.sha256(text.encode()).hexdigest()}",
            "enqueueSequence": 2,
            "leaseId": "lease-next",
            "authority": "coordinator",
            "runId": "run-1",
            "coordinatorGeneration": 1,
            "expectedLifecycleState": "active",
            "observedInputSurface": "working",
            "expiresAt": "2026-08-26T00:00:00Z",
            "expectedGraphRevision": None,
        }
        for state, proven in ((None, False), ("queued", False), ("acknowledged", True)):
            with self.subTest(state=state):
                fake = FakeOrca(self.repository)
                fake.current_successor_lease_id = "lease-next"
                fake.lease_delivery_state = state
                driver = self.driver(fake)
                driver.detect()
                arguments = (
                    "--lease-input",
                    json.dumps(lease_input, separators=(",", ":"), sort_keys=True),
                )

                if proven:
                    receipt = driver._send_terminal_handoff("term-new", text, *arguments)
                    self.assertEqual(
                        receipt["delivery_confirmation"]["receipt_state"],
                        "acknowledged",
                    )
                else:
                    with self.assertRaises(DriverError) as error:
                        driver._send_terminal_handoff("term-new", text, *arguments)
                    self.assertEqual(error.exception.code, "session_delivery_unproven")

    def test_rejects_wait_receipts_without_reachable_terminal_state(self) -> None:
        invalid_receipts = (
            {},
            {"satisfied": False, "condition": "tui-idle", "status": "running"},
            {"satisfied": True, "condition": "exit", "status": "running"},
            {"satisfied": True, "condition": "tui-idle", "status": "unknown"},
        )
        for wait_result in invalid_receipts:
            with self.subTest(wait_result=wait_result):
                fake = FakeOrca(self.repository)
                fake.wait_result = wait_result
                with self.assertRaises(DriverError) as error:
                    self.driver(fake)._wait_for_terminal("term-new", "tui-idle")
                self.assertEqual(error.exception.code, "terminal_wait_unconfirmed")

    def release_attempt(self, refs: dict, **overrides: object) -> dict[str, object]:
        return {
            "attempt_id": "attempt-1",
            "tier": "tracked-terminal",
            "dispatch_id": refs["dispatch_id"],
            "task_id": "ROOT-01",
            "external_task_id": refs["task_id"],
            "run_id": refs["run_id"],
            "execution_profile": refs["execution_profile"],
            "workspace_scope": refs["workspace_scope"],
            "external_refs": refs,
            **overrides,
        }

    def test_returns_old_peer_browser_surface_receipt_without_tab_commands(self) -> None:
        fake = FakeOrca(self.repository)
        driver = self.driver(fake)
        driver.detect()
        request = {
            "schema_version": 1, "request_id": "surface-request-1", "task_id": "ROOT-01", "attempt_id": "attempt-1",
            "idempotency_key": "surface-key-1", "mode": "visible", "retention": "release",
            "execution_host_id": "host-local", "workspace_key": "folder:workspace-1", "page_binding": None,
            "binding": {"kind": "initial_url", "value": "https://example.test/preview"},
            "viewport": {"width": 1280, "height": 720}, "source_revision": "commit-123",
        }
        receipt = driver.reserve_browser_surface(request)
        self.assertEqual(receipt.status, "unsupported")
        self.assertEqual(receipt.external_refs["browser_surface"]["unavailability"]["code"], "old-peer")
        self.assertFalse(any(call[:2] in (["terminal", "create"], ["terminal", "show"]) for call in fake.calls))

    def attempt(
        self,
        fake: FakeOrca,
        *,
        recover: bool = False,
        external_refs: dict | None = None,
    ) -> dict:
        profile = {
            "role": "implementation",
            "requested": {"lane": "fast", "agent": "codex", "model": "gpt-5.6", "effort": "medium"},
            "resolved": {"agent": "codex", "model": "gpt-5.6", "effort": "medium"},
            "fallback_reason": None,
            "placement_request": {"kind": "current-workspace"},
            "resolved_placement": {
                "execution_host_id": "host-local",
                "workspace_key": f"worktree:repo-1::{self.repository}",
                "kind": "git-worktree",
                "path": str(self.repository),
                "receipt_ref": "artifact:openspec/runs/change/run/artifacts/current-placement.json",
            },
        }
        fake.worker_profile = profile
        scope = {
            "schema_version": 1,
            "repository_id": "repo-1",
            "canonical_root": str(self.repository),
            "execution_host": {"id": "host-local", "boundary": "local"},
            "orchestration_home": {"execution_host_id": "host-local", "workspace_key": f"worktree:repo-1::{self.repository}", "kind": "git-worktree", "path": str(self.repository), "worktree_path": str(self.repository)},
            "execution_workspace": {"execution_host_id": "host-local", "workspace_key": f"worktree:repo-1::{self.repository}", "kind": "git-worktree", "path": str(self.repository), "worktree_path": str(self.repository)},
            "base_revision": "0123456789abcdef0123456789abcdef01234567",
            "dirty_paths": [],
            "run_id": "run-1",
            "coordinator_generation": 1,
            "binding_receipt_ref": "artifact:openspec/runs/change/run/artifacts/workspace.json",
            "binding_receipt_hash": "sha256:" + "a" * 64,
        }
        return {
            "task_id": "ROOT-01",
            "attempt_id": "attempt-1",
            "recover": recover,
            "execution_profile": profile,
            "workspace_scope": scope,
            **({"external_refs": external_refs} if external_refs else {}),
        }

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
        attempt = driver.start_attempt(self.attempt(fake))

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
        task_ready = next(call for call in fake.calls if call[:2] == ["orchestration", "task-update"])
        worker_start = next(call for call in fake.calls if call[:2] == ["orchestration", "worker-start"])
        self.assertEqual(task_ready[task_ready.index("--status") + 1], "ready")
        self.assertLess(fake.calls.index(task_ready), fake.calls.index(worker_start))
        ready_retry_request = task_ready[task_ready.index("--retry-request") + 1]
        worker_start_retry_request = worker_start[worker_start.index("--retry-request") + 1]
        self.assertEqual(ready_retry_request, "run-1-attempt-1-ready")
        self.assertEqual(worker_start_retry_request, "run-1-attempt-1-start")
        self.assertNotEqual(ready_retry_request, worker_start_retry_request)
        released = driver.release({"tier": "supervised", "dispatch_id": "dispatch-1"})
        self.assertEqual(released.status, "released")

    def test_relaunches_a_pre_resource_recovery_after_public_absence_proof(self) -> None:
        fake = FakeOrca(self.repository)
        fake.dispatch_is_null = True
        driver = self.driver(fake)
        driver.detect()
        driver.start_run("Probe", [{"id": "ROOT-01", "depends": [], "capsule": "bounded"}])

        recovered = driver.start_attempt(self.attempt(fake, recover=True))

        self.assertEqual(recovered.external_refs["tier"], "supervised")
        self.assertIn("pre_resource_recovery", recovered.raw)
        self.assertTrue(any(call[:2] == ["orchestration", "task-update"] for call in fake.calls))
        self.assertTrue(any(call[:2] == ["orchestration", "worker-start"] for call in fake.calls))

    def test_blocks_pre_resource_recovery_when_a_dispatch_is_ambiguous(self) -> None:
        fake = FakeOrca(self.repository)
        driver = self.driver(fake)
        driver.detect()
        driver.start_run("Probe", [{"id": "ROOT-01", "depends": [], "capsule": "bounded"}])

        with self.assertRaisesRegex(DriverError, "cannot prove") as raised:
            driver.start_attempt(self.attempt(fake, recover=True))

        self.assertEqual(raised.exception.code, "cleanup_unproven")
        self.assertFalse(any(call[:2] == ["orchestration", "worker-start"] for call in fake.calls))

    def test_reengages_one_exact_terminal_for_the_next_serial_task(self) -> None:
        fake = FakeOrca(self.repository, supervised_error="selector_not_found")
        fake.terminal_lease_capable = False
        driver = self.driver(fake)
        driver.detect()
        driver.start_run(
            "Probe",
            [
                {"id": "ROOT-01", "depends": [], "capsule": "first"},
                {"id": "NEXT-02", "depends": ["ROOT-01"], "capsule": "second"},
            ],
        )
        first = driver.start_attempt(self.attempt(fake))
        fake.dynamic_dispatch = True
        next_attempt = self.attempt(fake)
        next_attempt.update(
            {
                "task_id": "NEXT-02",
                "attempt_id": "attempt-2",
                "session_terminal": active_session_terminal(first.external_refs, "tracked-terminal"),
                "session_handoff": session_handoff("NEXT-02"),
            }
        )

        second = driver.start_attempt(next_attempt)

        self.assertTrue(second.external_refs["session_reused"])
        self.assertEqual(second.external_refs["session_parent_attempt_id"], "attempt-1")
        self.assertEqual(second.external_refs["terminal"]["handle"], first.external_refs["terminal"]["handle"])
        self.assertEqual(
            len([call for call in fake.calls if call[:2] == ["terminal", "create"]]), 1
        )
        self.assertEqual(
            len([call for call in fake.calls if call[:2] == ["orchestration", "worker-start"]]), 1
        )
        dispatches = [call for call in fake.calls if call[:2] == ["orchestration", "dispatch"]]
        self.assertEqual(len(dispatches), 2)
        self.assertEqual([call[call.index("--task") + 1] for call in dispatches], ["task-1", "task-2"])
        sends = [call for call in fake.calls if call[:2] == ["terminal", "send"]]
        self.assertEqual(len(sends), 1)
        self.assertNotIn("--lease-input", sends[0])
        second_ready = [call for call in fake.calls if call[:2] == ["orchestration", "task-update"]][-1]
        self.assertEqual(second_ready[second_ready.index("--id") + 1], "task-2")
        self.assertEqual(second_ready[second_ready.index("--status") + 1], "ready")

    def test_rejects_session_reuse_after_profile_drift(self) -> None:
        fake = FakeOrca(self.repository, supervised_error="selector_not_found")
        driver = self.driver(fake)
        driver.detect()
        driver.start_run("Probe", [{"id": "ROOT-01", "depends": [], "capsule": "first"}])
        first = driver.start_attempt(self.attempt(fake))
        next_attempt = self.attempt(fake)
        drifted_profile = json.loads(json.dumps(first.external_refs["execution_profile"]))
        drifted_profile["resolved"]["model"] = "other-model"
        next_attempt.update(
            {
                "attempt_id": "attempt-2",
                "execution_profile": drifted_profile,
                "session_terminal": active_session_terminal(first.external_refs, "tracked-terminal"),
                "session_handoff": session_handoff("ROOT-01"),
            }
        )

        with self.assertRaises(DriverError):
            driver.start_attempt(next_attempt)

    def test_rejects_managed_session_reuse_before_worker_start_on_an_old_peer(self) -> None:
        fake = FakeOrca(self.repository)
        fake.terminal_lease_capable = False
        driver = self.driver(fake)
        driver.detect()
        driver.start_run("Probe", [{"id": "ROOT-01", "depends": [], "capsule": "first"}, {"id": "NEXT-02", "depends": ["ROOT-01"], "capsule": "second"}])
        first = driver.start_attempt(self.attempt(fake))
        next_attempt = self.attempt(fake)
        next_attempt.update(
            {
                "task_id": "NEXT-02",
                "attempt_id": "attempt-2",
                "session_terminal": active_session_terminal(first.external_refs, "supervised"),
                "session_handoff": session_handoff("NEXT-02"),
            }
        )

        with self.assertRaises(DriverError) as raised:
            driver.start_attempt(next_attempt)

        self.assertEqual(raised.exception.code, "session_reuse_unavailable")
        self.assertEqual(len([call for call in fake.calls if call[:2] == ["orchestration", "worker-start"]]), 1)
        self.assertFalse(any(call[:2] == ["terminal", "send"] for call in fake.calls))

    def test_rejects_settled_or_remote_session_leases_before_dispatch(self) -> None:
        for lease_status, remote in (("settled", False), ("active", True)):
            with self.subTest(lease_status=lease_status, remote=remote):
                fake = FakeOrca(self.repository, supervised_error="selector_not_found")
                driver = self.driver(fake)
                driver.detect()
                driver.start_run("Probe", [{"id": "ROOT-01", "depends": [], "capsule": "first"}])
                first = driver.start_attempt(self.attempt(fake))
                next_attempt = self.attempt(fake)
                scope = json.loads(json.dumps(first.external_refs["workspace_scope"]))
                if remote:
                    scope["execution_host"]["boundary"] = "remote"
                next_attempt.update(
                    {
                        "attempt_id": "attempt-2",
                        "workspace_scope": scope,
                        "session_terminal": {
                            **active_session_terminal(first.external_refs, "tracked-terminal"),
                            "workspace_scope": scope,
                            "lease_status": lease_status,
                        },
                        "session_handoff": session_handoff("ROOT-01"),
                    }
                )

                with self.assertRaises(DriverError):
                    driver.start_attempt(next_attempt)
                self.assertFalse(any(call[:2] == ["terminal", "send"] for call in fake.calls))

    def test_rolls_back_the_exact_terminal_when_incremental_delivery_fails(self) -> None:
        fake = FakeOrca(self.repository, supervised_error="selector_not_found")
        driver = self.driver(fake)
        driver.detect()
        driver.start_run("Probe", [{"id": "ROOT-01", "depends": [], "capsule": "first"}, {"id": "NEXT-02", "depends": ["ROOT-01"], "capsule": "second"}])
        first = driver.start_attempt(self.attempt(fake))
        fake.dynamic_dispatch = True
        fake.terminal_send_error = "delivery_rejected"
        next_attempt = self.attempt(fake)
        next_attempt.update(
            {
                "task_id": "NEXT-02", "attempt_id": "attempt-2",
                "session_terminal": active_session_terminal(first.external_refs, "tracked-terminal"),
                "session_handoff": session_handoff("NEXT-02"),
            }
        )

        with self.assertRaises(DriverError) as raised:
            driver.start_attempt(next_attempt)

        self.assertEqual(raised.exception.code, "session_delivery_rolled_back")
        self.assertEqual(raised.exception.receipt["residual_resources"], "zero")
        self.assertEqual(len([call for call in fake.calls if call[:2] == ["terminal", "close"]]), 1)
        self.assertNotIn("term-new", fake.live)

    def test_falls_back_only_after_a_recognized_selector_failure(self) -> None:
        fake = FakeOrca(self.repository, supervised_error="selector_not_found")
        driver = self.driver(fake)
        driver.detect()
        driver.start_run("Probe", [{"id": "ROOT-01", "depends": [], "capsule": "bounded"}])

        attempt = driver.start_attempt(self.attempt(fake))

        self.assertEqual(attempt.external_refs["tier"], "tracked-terminal")
        self.assertEqual(attempt.degradation["code"], "selector_not_found")
        self.assertIn("term-new", driver.created_terminals["attempt-1"]["handle"])
        self.assertEqual(
            driver.created_terminals["attempt-1"]["ownership"],
            attempt.external_refs["terminal"]["ownership"],
        )
        terminal_create = next(
            call for call in fake.calls if call[:2] == ["terminal", "create"]
        )
        command = terminal_create[terminal_create.index("--command") + 1]
        self.assertIn("--model gpt-5.6", command)
        self.assertIn("model_reasoning_effort=medium", command)
        self.assertIn("--yolo", command)
        self.assertEqual(attempt.external_refs["terminal_command"], command)
        self.assertEqual(
            attempt.raw["dispatch_show"]["result"]["dispatch"]["id"],
            attempt.external_refs["dispatch_id"],
        )

    def test_resolves_full_identity_after_a_handle_only_create_receipt(self) -> None:
        fake = FakeOrca(
            self.repository,
            supervised_error="selector_not_found",
            minimal_create_receipt=True,
        )
        driver = self.driver(fake)
        driver.detect()
        driver.start_run("Probe", [{"id": "ROOT-01", "depends": [], "capsule": "bounded"}])

        attempt = driver.start_attempt(self.attempt(fake))

        self.assertEqual(attempt.external_refs["terminal"]["incarnation_id"], "inc-1")
        self.assertIn(["terminal", "show", "--terminal", "term-new", "--json"], fake.calls)

    def test_recovers_a_tracked_terminal_already_present_in_a_fresh_snapshot(self) -> None:
        fake = FakeOrca(self.repository, supervised_error="selector_not_found")
        first = self.driver(fake)
        first.detect()
        first.start_run("Probe", [{"id": "ROOT-01", "depends": [], "capsule": "bounded"}])
        first_started = first.start_attempt(self.attempt(fake))

        resumed = self.driver(fake)
        resumed.detect()
        resumed.run_id = "run-1"
        resumed.task_ids = {"ROOT-01": "task-1"}
        fake.calls.clear()
        recovered = resumed.start_attempt(
            self.attempt(fake, recover=True, external_refs=first_started.external_refs)
        )

        self.assertEqual(recovered.external_refs["terminal"]["handle"], "term-new")
        self.assertFalse(recovered.external_refs["terminal"]["created_by_harness"])
        self.assertTrue(recovered.external_refs["terminal"]["recovered"])
        self.assertTrue(recovered.external_refs["terminal"]["pinned_creation_owned"])
        self.assertTrue(recovered.raw["recovered_terminal"])
        self.assertIn("term-new", resumed._terminal_snapshot)
        self.assertIsNotNone(recovered.raw["dispatch_show"])
        self.assertFalse(any(call[:2] == ["worktree", "current"] for call in fake.calls))
        self.assertFalse(any(call[:2] == ["orchestration", "worker-start"] for call in fake.calls))
        self.assertFalse(any(call[:2] == ["terminal", "create"] for call in fake.calls))
        self.assertEqual(recovered.external_refs["tier"], "tracked-terminal")
        self.assertEqual(recovered.external_refs["dispatch_id"], first_started.external_refs["dispatch_id"])
        replay = next(call for call in fake.calls if call[:2] == ["orchestration", "dispatch"])
        self.assertEqual(replay[replay.index("--run") + 1], "run-1")
        self.assertEqual(replay[replay.index("--task") + 1], "task-1")
        self.assertEqual(
            replay[replay.index("--retry-request") + 1],
            "run-1-attempt-1-dispatch",
        )
        self.assertIn(
            ["worktree", "show", "--worktree", f"id:repo-1::{self.repository}", "--json"],
            fake.calls,
        )
        released = resumed.release(self.release_attempt(recovered.external_refs))
        self.assertEqual(released.status, "released")
        self.assertNotIn("term-new", fake.live)

    def test_recovery_rejects_a_replayed_dispatch_for_another_terminal(self) -> None:
        fake = FakeOrca(self.repository, supervised_error="selector_not_found")
        driver = self.driver(fake)
        driver.detect()
        driver.start_run("Probe", [{"id": "ROOT-01", "depends": [], "capsule": "bounded"}])
        started = driver.start_attempt(self.attempt(fake))
        fake.dispatch_identity_override = {
            "assignee_handle": "term-lost",
            "assignee_pane_key": "tab-lost:leaf-lost",
            "process_incarnation": f"repo-1::{self.repository}@@pty-lost:inc-lost",
        }

        with self.assertRaisesRegex(DriverError, "tracked terminal binding"):
            driver.start_attempt(
                self.attempt(fake, recover=True, external_refs=started.external_refs)
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
            driver.start_attempt(self.attempt(fake))

        self.assertNotIn("term-new", fake.live)
        self.assertIn(
            ["terminal", "close", "--terminal", "term-new", "--tab", "--json"],
            fake.calls,
        )

    def test_closes_an_acquired_terminal_when_dispatch_omits_its_id(self) -> None:
        fake = FakeOrca(self.repository, supervised_error="selector_not_found")
        fake.dispatch_receipt_id = ""
        driver = self.driver(fake)
        driver.detect()
        driver.start_run("Probe", [{"id": "ROOT-01", "depends": [], "capsule": "bounded"}])

        with self.assertRaisesRegex(DriverError, "omitted its dispatch ID") as raised:
            driver.start_attempt(self.attempt(fake))

        self.assertEqual(raised.exception.code, "invalid_receipt")
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
            driver.start_attempt(self.attempt(fake))
        self.assertFalse(any(call[:2] == ["terminal", "create"] for call in fake.calls))

    def test_rejects_an_unproven_supervised_profile_before_recording_receipts(self) -> None:
        fake = FakeOrca(self.repository)
        driver = self.driver(fake)
        driver.detect()
        driver.start_run("Probe", [{"id": "ROOT-01", "depends": [], "capsule": "bounded"}])
        attempt = self.attempt(fake)
        fake.worker_launch_override = {
            "requested": {"agent": "codex", "model": "gpt-5.6", "effort": "medium"},
            "effective": {"agent": "codex", "model": "gpt-5.6", "effort": "high"},
        }

        with self.assertRaisesRegex(DriverError, "did not prove|yolo launch profile") as raised:
            driver.start_attempt(attempt)

        self.assertEqual(raised.exception.code, "worker_profile_unproven")
        self.assertIn("worker_start", raised.exception.receipt["cause"])
        self.assertEqual(raised.exception.receipt["rollback"]["residual_resources"], "zero")

    def test_rejects_a_supervised_success_without_a_dispatch_id(self) -> None:
        fake = FakeOrca(self.repository)
        fake.worker_dispatch_id = ""
        driver = self.driver(fake)
        driver.detect()
        driver.start_run("Probe", [{"id": "ROOT-01", "depends": [], "capsule": "bounded"}])

        with self.assertRaisesRegex(DriverError, "dispatch ID") as raised:
            driver.start_attempt(self.attempt(fake))

        self.assertEqual(raised.exception.code, "invalid_receipt")

    def test_rejects_an_unrelated_effect_that_reuses_the_selected_worktree_id(self) -> None:
        fake = FakeOrca(self.repository)
        fake.worker_effects = [
            {"kind": "terminal", "action": "created", "id": f"repo-1::{self.repository}"}
        ]
        driver = self.driver(fake)
        driver.detect()
        driver.start_run("Probe", [{"id": "ROOT-01", "depends": [], "capsule": "bounded"}])

        with self.assertRaisesRegex(DriverError, "effects did not prove") as raised:
            driver.start_attempt(self.attempt(fake))

        self.assertEqual(raised.exception.code, "placement_not_resolved")

    def test_fails_closed_when_tracked_terminal_cannot_apply_a_non_codex_profile(self) -> None:
        fake = FakeOrca(self.repository, supervised_error="selector_not_found")
        driver = self.driver(fake)
        driver.detect()
        driver.start_run("Probe", [{"id": "ROOT-01", "depends": [], "capsule": "bounded"}])
        attempt = self.attempt(fake)
        profile = attempt["execution_profile"]
        profile["requested"].update(agent="agent-alpha", model="model-alpha")
        profile["resolved"].update(agent="agent-alpha", model="model-alpha")
        with self.assertRaisesRegex(DriverError, "cannot prove") as raised:
            driver.start_attempt(attempt)

        self.assertEqual(raised.exception.code, "fallback_profile_unproven")
        self.assertEqual(raised.exception.receipt["resolved"]["agent"], "agent-alpha")
        self.assertFalse(any(call[:2] == ["terminal", "create"] for call in fake.calls))

    def test_rejects_a_missing_runtime_identity_before_any_terminal_can_be_owned(self) -> None:
        fake = FakeOrca(self.repository)
        fake.omit_runtime_id = True

        with self.assertRaisesRegex(DriverError, "runtime identity") as raised:
            self.driver(fake).detect()

        self.assertEqual(raised.exception.code, "preflight_failed")
        self.assertFalse(any(call[:2] == ["terminal", "create"] for call in fake.calls))

    def test_bounds_transcript_reads_and_replies_to_questions(self) -> None:
        fake = FakeOrca(self.repository, supervised_error="selector_not_found")
        driver = self.driver(fake)
        driver.detect()
        driver.start_run("Probe", [{"id": "ROOT-01", "depends": [], "capsule": "bounded"}])
        started = driver.start_attempt(self.attempt(fake))
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
        started = driver.start_attempt(self.attempt(fake))

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

    def test_reconciliation_accepts_an_explicit_empty_dispatch_as_absent(self) -> None:
        fake = FakeOrca(self.repository)
        fake.dispatch_is_null = True
        driver = self.driver(fake)
        driver.detect()
        driver.start_run("Probe", [{"id": "ROOT-01", "depends": [], "capsule": "bounded"}])

        reconciliation = driver.reconcile(
            [{"attempt_id": "attempt-1", "task_id": "ROOT-01", "status": "reserved"}]
        )

        self.assertEqual(reconciliation.raw[0]["resource_state"], "absent")

    def test_closes_only_the_same_created_terminal_incarnation(self) -> None:
        fake = FakeOrca(self.repository, supervised_error="selector_not_found")
        driver = self.driver(fake)
        driver.detect()
        driver.start_run("Probe", [{"id": "ROOT-01", "depends": [], "capsule": "bounded"}])
        started = driver.start_attempt(self.attempt(fake))
        refs = started.external_refs

        released = driver.release(self.release_attempt(refs))

        self.assertEqual(released.status, "released")
        self.assertNotIn("term-new", fake.live)
        self.assertIn(["terminal", "close", "--terminal", "term-new", "--tab", "--json"], fake.calls)

        fake2 = FakeOrca(self.repository, supervised_error="selector_not_found")
        driver2 = self.driver(fake2)
        driver2.detect()
        driver2.start_run("Probe", [{"id": "ROOT-01", "depends": [], "capsule": "bounded"}])
        refs2 = driver2.start_attempt(self.attempt(fake2)).external_refs
        fake2.incarnation["incarnationId"] = "replaced"
        with self.assertRaisesRegex(DriverError, "incarnation changed"):
            driver2.release(self.release_attempt(refs2))
        self.assertIn("term-new", fake2.live)

    def test_rejects_release_for_a_different_dispatch_or_task_without_terminal_effects(self) -> None:
        fake = FakeOrca(self.repository, supervised_error="selector_not_found")
        driver = self.driver(fake)
        driver.detect()
        driver.start_run("Probe", [{"id": "ROOT-01", "depends": [], "capsule": "bounded"}])
        refs = driver.start_attempt(self.attempt(fake)).external_refs

        for field, value in (("dispatch_id", "dispatch-other"), ("external_task_id", "task-other")):
            with self.subTest(field=field):
                fake.calls.clear()
                with self.assertRaisesRegex(DriverError, "does not match") as raised:
                    driver.release(self.release_attempt(refs, **{field: value}))

                self.assertEqual(raised.exception.code, "cleanup_unproven")
                self.assertFalse(any(call[:2] == ["terminal", "list"] for call in fake.calls))
                self.assertFalse(any(call[:2] == ["terminal", "show"] for call in fake.calls))
                self.assertFalse(any(call[:2] == ["terminal", "close"] for call in fake.calls))
                self.assertIn("term-new", fake.live)

    def test_releases_a_durably_rehydrated_owned_terminal(self) -> None:
        fake = FakeOrca(self.repository, supervised_error="selector_not_found")
        first = self.driver(fake)
        first.detect()
        first.start_run("Probe", [{"id": "ROOT-01", "depends": [], "capsule": "bounded"}])
        refs = first.start_attempt(self.attempt(fake)).external_refs

        resumed = self.driver(fake)
        resumed.detect()
        resumed.created_terminals["attempt-1"] = dict(refs["terminal"])
        fake.calls.clear()

        released = resumed.release(self.release_attempt(refs))

        self.assertEqual(released.status, "released")
        self.assertFalse(any(call[:2] == ["worktree", "current"] for call in fake.calls))
        self.assertIn(
            ["worktree", "show", "--worktree", f"id:repo-1::{self.repository}", "--json"],
            fake.calls,
        )
        self.assertIn(["terminal", "close", "--terminal", "term-new", "--tab", "--json"], fake.calls)
        self.assertNotIn("term-new", fake.live)

    def test_rejects_changed_saved_placement_before_terminal_cleanup_effects(self) -> None:
        fake = FakeOrca(self.repository, supervised_error="selector_not_found")
        driver = self.driver(fake)
        driver.detect()
        driver.start_run("Probe", [{"id": "ROOT-01", "depends": [], "capsule": "bounded"}])
        refs = driver.start_attempt(self.attempt(fake)).external_refs
        fake.worktree["hostId"] = "host-other"
        fake.calls.clear()

        with self.assertRaisesRegex(DriverError, "workspace placement exactly") as raised:
            driver.release(self.release_attempt(refs))

        self.assertEqual(raised.exception.code, "placement_not_resolved")
        self.assertFalse(any(call[:2] == ["worktree", "current"] for call in fake.calls))
        self.assertFalse(any(call[:2] == ["terminal", "list"] for call in fake.calls))
        self.assertFalse(any(call[:2] == ["terminal", "show"] for call in fake.calls))
        self.assertFalse(any(call[:2] == ["terminal", "close"] for call in fake.calls))
        self.assertIn("term-new", fake.live)

    def test_treats_an_absent_recorded_terminal_as_prior_cleanup(self) -> None:
        fake = FakeOrca(self.repository, supervised_error="selector_not_found")
        driver = self.driver(fake)
        driver.detect()
        driver.start_run("Probe", [{"id": "ROOT-01", "depends": [], "capsule": "bounded"}])
        refs = driver.start_attempt(self.attempt(fake)).external_refs
        fake.live.discard("term-new")

        released = driver.release(self.release_attempt(refs))

        self.assertTrue(released.external_refs["prior_cleanup"])
        self.assertEqual(released.raw["state"], "already_absent")


class CommandSelectionBehavior(unittest.TestCase):
    def test_pins_the_configured_command(self) -> None:
        self.assertEqual(resolve_orca_command({"ORCA_CLI_COMMAND": "wrapper --profile dev"}), ("wrapper", "--profile", "dev"))


if __name__ == "__main__":
    unittest.main()
