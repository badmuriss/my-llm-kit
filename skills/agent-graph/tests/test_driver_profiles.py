import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import agent_graph as runtime
from drivers.base import DriverError, persisted_driver_context, resolve_capability_request
from drivers.host import HostDriver
from drivers.orca import OrcaDriver
from graph_core import TaskContract, TaskGraph
from validation import CAPABILITY_NAMES, validate_capability_receipt


FIXTURES = Path(__file__).parents[1] / "fixtures" / "maestro-protocol-v1"
WORKSPACE_SCOPES = json.loads((FIXTURES / "workspace-scopes.json").read_text())


class FakeOrca:
    def __init__(self, repository: Path) -> None:
        self.repository = repository
        self.calls: list[list[str]] = []
        self.runtime_capabilities = [
            "orchestration.contract.v1",
            "orchestration.worker-launch-preferences.v1",
        ]
        self.worktrees = {
            f"repo-1::{repository}": self._worktree(
                f"repo-1::{repository}", "host-local", str(repository), True
            ),
            "repo-1::/srv/worktrees/remote-01": self._worktree(
                "repo-1::/srv/worktrees/remote-01", "host-remote", "/srv/worktrees/remote-01", False
            ),
            "repo-1::/tmp/child-01": self._worktree(
                "repo-1::/tmp/child-01", "host-local", "/tmp/child-01", False
            ),
        }
        self.current = self.worktrees[f"repo-1::{repository}"]
        self.wrong_placement = False
        self.worker_profile: dict | None = None
        self.worker_start_error: str | None = None
        self.resolution_host_override: str | None = None
        self.pinned_terminal = {
            "handle": "term-pinned",
            "ptyId": "pty-1",
            "incarnationId": "inc-1",
            "worktreeId": f"repo-1::{repository}",
            "tabId": "tab-1",
            "leafId": "leaf-1",
        }

    @staticmethod
    def _worktree(worktree_id, host, path, is_main_worktree):
        return {
            "id": worktree_id,
            "hostId": host,
            "path": path,
            "git": {"path": path, "isMainWorktree": is_main_worktree},
            "isMainWorktree": is_main_worktree,
        }

    def __call__(self, argv):
        arguments = list(argv)[1:]
        self.calls.append(arguments)
        command = arguments[:2]
        if arguments[0] == "status":
            return {
                "ok": True,
                "result": {
                    "runtime": {
                        "reachable": True,
                        "state": "ready",
                        "capabilities": self.runtime_capabilities,
                    },
                    "graph": {"state": "ready"},
                },
                "_meta": {"runtimeId": "runtime-1"},
            }
        if command == ["worktree", "current"]:
            return {"ok": True, "result": {"worktree": self.current}}
        if command == ["worktree", "show"]:
            environment = (
                arguments[arguments.index("--environment") + 1]
                if "--environment" in arguments
                else None
            )
            selector = arguments[arguments.index("--worktree") + 1]
            if selector.startswith("id:"):
                worktree = next(
                    value for value in self.worktrees.values() if value["id"] == selector.removeprefix("id:")
                )
            elif selector.startswith("path:"):
                worktree = next(
                    value for value in self.worktrees.values() if value["path"] == selector.removeprefix("path:")
                )
            else:
                raise AssertionError(f"unsupported selector: {selector}")
            if environment is not None and environment != worktree["hostId"]:
                raise AssertionError(f"wrong environment for worktree: {environment}")
            if self.resolution_host_override:
                worktree = copy.deepcopy(worktree)
                worktree["hostId"] = self.resolution_host_override
            if self.wrong_placement and selector == "id:repo-1::/tmp/child-01":
                worktree = copy.deepcopy(worktree)
                worktree["path"] = "/tmp/wrong-child"
                worktree["git"]["path"] = "/tmp/wrong-child"
            return {"ok": True, "result": {"worktree": worktree}}
        if command == ["worktree", "create"]:
            return {"ok": True, "result": {"worktree": {"id": "repo-1::/tmp/child-01"}}}
        if command == ["terminal", "list"]:
            return {"ok": True, "result": {"terminals": []}}
        if command == ["terminal", "show"]:
            return {"ok": True, "result": self.pinned_terminal}
        if command == ["terminal", "wait"]:
            return {
                "ok": True,
                "result": {
                    "satisfied": True,
                    "condition": "tui-idle",
                    "status": "running",
                },
            }
        if command == ["orchestration", "run-create"]:
            return {"ok": True, "result": {"id": "run-1"}}
        if command == ["orchestration", "task-create"]:
            return {"ok": True, "result": {"id": "task-1"}}
        if command == ["orchestration", "task-update"]:
            return {
                "ok": True,
                "result": {
                    "task": {
                        "id": arguments[arguments.index("--id") + 1],
                        "status": arguments[arguments.index("--status") + 1],
                    }
                },
            }
        if command == ["orchestration", "worker-start"]:
            if self.worker_start_error:
                return {"ok": False, "error": {"code": self.worker_start_error, "message": "profile unsupported"}, "result": {"effects": [], "residualResources": []}}
            profile = self.worker_profile
            worktree_id = arguments[arguments.index("--worktree") + 1].removeprefix("id:")
            return {"ok": True, "result": {"dispatchId": "dispatch-1", "launch": {"requested": profile["resolved"], "effective": profile["resolved"]}, "effects": [{"kind": "worktree", "action": "reused", "id": worktree_id}]}}
        if command == ["orchestration", "worker-show"]:
            profile = self.worker_profile["resolved"]
            return {
                "ok": True,
                "result": {
                    "worker": {
                        "dispatchId": arguments[arguments.index("--dispatch") + 1],
                        "terminal": self.pinned_terminal,
                        "launchProfile": {
                            "agent": profile["agent"],
                            "model": profile["model"],
                            "effort": profile["effort"],
                            "permissionMode": "yolo",
                        },
                    }
                },
            }
        if command == ["orchestration", "dispatch"]:
            return {"ok": True, "result": {"id": "dispatch-low"}}
        if command == ["orchestration", "dispatch-show"]:
            return {
                "ok": True,
                "result": {
                    "dispatch": {
                        "id": "dispatch-low",
                        "task_id": "task-1",
                        "assignee_handle": "term-pinned",
                        "assignee_pane_key": "tab-1:leaf-1",
                        "process_incarnation": (
                            f"{self.pinned_terminal['worktreeId']}@@"
                            f"{self.pinned_terminal['ptyId']}:"
                            f"{self.pinned_terminal['incarnationId']}"
                        ),
                    }
                },
            }
        raise AssertionError(f"unexpected command: {arguments}")


class DriverProfileBehavior(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repository = Path(self.temporary_directory.name).resolve()
        self.fake = FakeOrca(self.repository)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_reports_the_same_portable_capability_names_with_truthful_adapter_values(self) -> None:
        host = HostDriver(
            self.repository, self.repository / "openspec/runs/change/run"
        ).detect().external_refs["capability_receipt"]
        orca = OrcaDriver(
            self.repository,
            runner=self.fake,
            environment={"ORCA_CLI_COMMAND": "fake-orca"},
        ).detect().external_refs["capability_receipt"]

        validate_capability_receipt(host)
        validate_capability_receipt(orca)
        self.assertEqual(set(host["capabilities"]), CAPABILITY_NAMES)
        self.assertEqual(set(orca["capabilities"]), CAPABILITY_NAMES)
        self.assertEqual(host["capabilities"]["visible_worker_dispatch"]["status"], "unsupported")
        self.assertEqual(orca["capabilities"]["visible_worker_dispatch"]["status"], "supported")
        self.assertEqual(host["capabilities"]["usage_metrics"]["status"], "unavailable")
        self.assertEqual(orca["capabilities"]["cache_metrics"]["status"], "unavailable")
        self.assertNotIn("orca", host["extensions"])
        self.assertIn("orca", orca["extensions"])

    def test_resolves_missing_optional_capabilities_for_only_the_requested_operation(self) -> None:
        host = HostDriver(
            self.repository, self.repository / "openspec/runs/change/run"
        ).detect().external_refs["capability_receipt"]
        downgraded = resolve_capability_request(
            host["capabilities"],
            ["visible_worker_dispatch"],
            operation="worker_dispatch",
            compatible_alternative="local_execution",
        )
        blocked = resolve_capability_request(
            host["capabilities"],
            ["browser_surface"],
            operation="visual_inspection",
        )
        telemetry = resolve_capability_request(
            host["capabilities"],
            ["usage_metrics", "cache_metrics"],
            operation="telemetry_capture",
            compatible_alternative="serialize_unavailable",
        )

        self.assertEqual(downgraded["outcome"], "downgraded")
        self.assertEqual(blocked["outcome"], "blocked")
        self.assertEqual(telemetry["missing_capabilities"], ["usage_metrics", "cache_metrics"])
        core = json.dumps([downgraded, blocked, telemetry]).casefold()
        for private_name in ("orca", "terminal", "canvas", "model-"):
            self.assertNotIn(private_name, core)

    def test_accepts_new_orca_optional_capabilities_only_when_the_runtime_advertises_them(self) -> None:
        self.fake.runtime_capabilities.extend(
            ["browser.surface.v1", "usage.metrics.v1", "cache.metrics.v1"]
        )
        receipt = OrcaDriver(
            self.repository,
            runner=self.fake,
            environment={"ORCA_CLI_COMMAND": "fake-orca"},
        ).detect().external_refs["capability_receipt"]

        for name in ("browser_surface", "usage_metrics", "cache_metrics"):
            self.assertEqual(receipt["capabilities"][name]["status"], "supported")

    def test_never_falls_back_to_host_for_an_explicit_orca_selection(self) -> None:
        graph = TaskGraph(
            (
                TaskContract(
                    id="ROOT-01",
                    title="Bounded",
                    depends=(),
                    paths=("src/root.py",),
                    mode="write",
                    isolation="auto",
                    acceptance="The task is verified.",
                    check="python3 -m unittest",
                ),
            )
        )

        class UnavailableOrca:
            def __init__(self, repository):
                self.repository = repository

            def detect(self):
                raise DriverError("Orca is unavailable", code="cli_unavailable")

        with patch.object(runtime, "OrcaDriver", UnavailableOrca), patch.object(
            runtime, "HostDriver"
        ) as host:
            with self.assertRaisesRegex(DriverError, "Orca is unavailable"):
                runtime._select_driver(
                    self.repository,
                    self.repository / "openspec/runs/change/run",
                    "orca",
                    graph,
                )
            host.assert_not_called()

    def test_negotiates_each_advertised_agent_model_and_effort_without_a_codex_default(self) -> None:
        for agent, model, effort in (
            ("agent-alpha", "model-fast", "medium"),
            ("agent-beta", "model-strong", "high"),
        ):
            with self.subTest(agent=agent, model=model, effort=effort):
                driver = self._started_orca()
                receipt = driver.start_attempt(
                    self._attempt(
                        requested_agent=agent,
                        requested_model=model,
                        requested_effort=effort,
                    )
                )

                start = [call for call in self.fake.calls if call[:2] == ["orchestration", "worker-start"]][-1]
                ready_index = next(
                    index
                    for index, call in enumerate(self.fake.calls)
                    if call[:2] == ["orchestration", "task-update"]
                )
                worker_start_index = self.fake.calls.index(start)
                self.assertLess(ready_index, worker_start_index)
                self.assertEqual(start[start.index("--agent") + 1], agent)
                self.assertEqual(start[start.index("--model") + 1], model)
                self.assertEqual(start[start.index("--effort") + 1], effort)
                self.assertNotIn("codex", start)
                self.assertEqual(receipt.external_refs["execution_profile"]["resolved"]["agent"], agent)
                self.assertEqual(receipt.external_refs["execution_profile"], self.fake.worker_profile)
                self.assertEqual(receipt.external_refs["launch"], receipt.raw["worker_start"]["result"]["launch"])

    def test_preserves_an_explicit_fallback_and_rejects_an_unadvertised_profile(self) -> None:
        driver = self._started_orca()
        fallback = self._attempt(
            requested_agent="agent-beta",
            requested_model="model-strong",
            requested_effort="xhigh",
            resolved_agent="agent-beta",
            resolved_model="model-strong",
            resolved_effort="high",
            fallback_reason="The selected runtime only permits high effort for this task.",
        )

        receipt = driver.start_attempt(fallback)

        self.assertEqual(receipt.external_refs["execution_profile"]["fallback_reason"], fallback["execution_profile"]["fallback_reason"])
        unsupported = self._attempt(
            requested_agent="unknown-agent",
            requested_model="unknown-model",
            requested_effort="medium",
        )
        self.fake.worker_start_error = "profile_not_supported"
        with self.assertRaisesRegex(DriverError, "profile unsupported") as raised:
            driver.start_attempt(unsupported)
        self.assertEqual(raised.exception.code, "profile_not_supported")

    def test_resolves_current_existing_remote_and_child_worktree_placements_exactly(self) -> None:
        current = self._started_orca().start_attempt(self._attempt())
        self.assertEqual(current.external_refs["resolved_placement"]["workspace_key"], self._local_worktree_key())
        self.assertEqual(current.external_refs["resolved_placement"]["kind"], "git-worktree")
        current_show = [
            call for call in self.fake.calls if call[:2] == ["worktree", "show"]
        ][-1]
        self.assertEqual(
            current_show[current_show.index("--worktree") + 1],
            f"id:{self._local_worktree_key().removeprefix('worktree:')}",
        )

        remote_driver = self._started_orca()
        remote = remote_driver.start_attempt(
            self._attempt(
                placement_request={
                    "kind": "existing-workspace",
                    "execution_host_id": "host-remote",
                    "workspace_key": "worktree:repo-1::/srv/worktrees/remote-01",
                },
                resolved_placement={
                    "execution_host_id": "host-remote",
                    "workspace_key": "worktree:repo-1::/srv/worktrees/remote-01",
                    "kind": "git-worktree",
                    "path": None,
                    "receipt_ref": "artifact:openspec/runs/change/run/artifacts/remote-placement.json",
                },
                workspace_scope=self._remote_scope(),
            )
        )
        self.assertEqual(remote.external_refs["resolved_placement"]["execution_host_id"], "host-remote")
        self.assertEqual(
            remote.raw["placement"]["result"]["worktree"]["id"],
            remote.external_refs["worktree_id"],
        )
        remote_show = [
            call for call in self.fake.calls if call[:2] == ["worktree", "show"]
        ][-1]
        self.assertEqual(remote_show[remote_show.index("--environment") + 1], "host-remote")
        self.assertIn("id:repo-1::/srv/worktrees/remote-01", remote_show)
        remote_start = [
            call for call in self.fake.calls if call[:2] == ["orchestration", "worker-start"]
        ][-1]
        self.assertEqual(remote_start[remote_start.index("--on") + 1], "host-remote")
        self.assertEqual(
            remote_start[remote_start.index("--worktree") + 1],
            "id:repo-1::/srv/worktrees/remote-01",
        )
        self.assertEqual(remote.external_refs["placement_environment"], "host-remote")
        self.assertEqual(remote.external_refs["placement_receipt"], remote.raw["placement"])

        child_driver = self._started_orca()
        child = child_driver.start_attempt(
            self._attempt(
                placement_request={
                    "kind": "create-child-worktree",
                    "execution_host_id": "host-local",
                    "parent_workspace_key": self._local_worktree_key(),
                    "name_hint": "worker-01",
                },
                resolved_placement={
                    "execution_host_id": "host-local",
                    "workspace_key": "worktree:repo-1::/tmp/child-01",
                    "kind": "git-worktree",
                    "path": "/tmp/child-01",
                    "receipt_ref": "artifact:openspec/runs/change/run/artifacts/child-placement.json",
                },
            )
        )
        self.assertEqual(child.external_refs["resolved_placement"]["workspace_key"], "worktree:repo-1::/tmp/child-01")
        self.assertTrue(any(call[:2] == ["worktree", "create"] for call in self.fake.calls))

    def test_rejects_mismatched_child_placement_before_dispatch(self) -> None:
        self.fake.wrong_placement = True
        driver = self._started_orca()
        attempt = self._attempt(
            placement_request={
                "kind": "create-child-worktree",
                "execution_host_id": "host-local",
                "parent_workspace_key": self._local_worktree_key(),
                "name_hint": "worker-01",
            },
            resolved_placement={
                "execution_host_id": "host-local",
                "workspace_key": "worktree:repo-1::/tmp/child-01",
                "kind": "git-worktree",
                "path": "/tmp/child-01",
                "receipt_ref": "artifact:openspec/runs/change/run/artifacts/child-placement.json",
            },
        )

        with self.assertRaisesRegex(DriverError, "placement exactly"):
            driver.start_attempt(attempt)
        self.assertFalse(any(call[:2] == ["orchestration", "worker-start"] for call in self.fake.calls))

    def test_rejects_current_workspace_without_a_pinned_path_before_dispatch(self) -> None:
        driver = self._started_orca()
        attempt = self._attempt(
            resolved_placement={
                "execution_host_id": "host-local",
                "workspace_key": self._local_worktree_key(),
                "kind": "git-worktree",
                "path": None,
                "receipt_ref": "artifact:openspec/runs/change/run/artifacts/current-placement.json",
            }
        )

        with self.assertRaisesRegex(DriverError, "exact pinned path"):
            driver.start_attempt(attempt)
        self.assertFalse(any(call[:2] == ["orchestration", "worker-start"] for call in self.fake.calls))

    def test_rejects_current_workspace_from_another_checkout_before_dispatch(self) -> None:
        another_checkout = self.repository / "another-checkout"
        another_checkout.mkdir()
        driver = OrcaDriver(
            another_checkout,
            runner=self.fake,
            environment={"ORCA_CLI_COMMAND": "fake-orca"},
        )
        self.fake.calls.clear()

        with self.assertRaisesRegex(DriverError, "another checkout") as raised:
            driver.detect()

        self.assertEqual(raised.exception.code, "selector_not_found")
        self.assertFalse(any(call[:2] == ["terminal", "list"] for call in self.fake.calls))
        self.assertFalse(any(call[:2] == ["orchestration", "run-create"] for call in self.fake.calls))
        self.assertFalse(any(call[:2] == ["orchestration", "task-create"] for call in self.fake.calls))
        self.assertFalse(any(call[:2] == ["orchestration", "worker-start"] for call in self.fake.calls))

    def test_rejects_remote_tracked_terminal_fallback_without_local_terminal_side_effects(self) -> None:
        driver = self._started_orca()
        attempt = self._attempt(
            placement_request={
                "kind": "existing-workspace",
                "execution_host_id": "host-remote",
                "workspace_key": "worktree:repo-1::/srv/worktrees/remote-01",
            },
            resolved_placement={
                "execution_host_id": "host-remote",
                "workspace_key": "worktree:repo-1::/srv/worktrees/remote-01",
                "kind": "git-worktree",
                "path": None,
                "receipt_ref": "artifact:openspec/runs/change/run/artifacts/remote-placement.json",
            },
            workspace_scope=self._remote_scope(),
        )
        self.fake.worker_start_error = "selector_not_found"
        self.fake.calls.clear()

        with self.assertRaisesRegex(DriverError, "cannot fall back") as raised:
            driver.start_attempt(attempt)

        self.assertEqual(raised.exception.code, "remote_fallback_unproven")
        worker_start = next(
            call for call in self.fake.calls if call[:2] == ["orchestration", "worker-start"]
        )
        self.assertEqual(worker_start[worker_start.index("--on") + 1], "host-remote")
        self.assertFalse(any(call[:2] == ["terminal", "list"] for call in self.fake.calls))
        self.assertFalse(any(call[:2] == ["terminal", "create"] for call in self.fake.calls))

    def test_rejects_a_remote_receipt_from_another_host_before_worker_start(self) -> None:
        driver = self._started_orca()
        attempt = self._attempt(
            placement_request={
                "kind": "existing-workspace",
                "execution_host_id": "host-remote",
                "workspace_key": "worktree:repo-1::/srv/worktrees/remote-01",
            },
            resolved_placement={
                "execution_host_id": "host-remote",
                "workspace_key": "worktree:repo-1::/srv/worktrees/remote-01",
                "kind": "git-worktree",
                "path": None,
                "receipt_ref": "artifact:openspec/runs/change/run/artifacts/remote-placement.json",
            },
            workspace_scope=self._remote_scope(),
        )
        self.fake.resolution_host_override = "host-local"
        self.fake.calls.clear()

        with self.assertRaisesRegex(DriverError, "placement exactly"):
            driver.start_attempt(attempt)

        resolution = next(
            call for call in self.fake.calls if call[:2] == ["worktree", "show"]
        )
        self.assertEqual(resolution[resolution.index("--environment") + 1], "host-remote")
        self.assertFalse(any(call[:2] == ["orchestration", "worker-start"] for call in self.fake.calls))

    def test_rejects_remote_current_or_child_placement_before_any_orca_effect(self) -> None:
        driver = self._started_orca()
        remote_scope = self._remote_scope()
        rejected = (
            self._attempt(
                placement_request={"kind": "current-workspace"},
                resolved_placement={
                    "execution_host_id": "host-remote",
                    "workspace_key": "worktree:repo-1::/srv/worktrees/remote-01",
                    "kind": "git-worktree",
                    "path": "/srv/worktrees/remote-01",
                    "receipt_ref": "artifact:openspec/runs/change/run/artifacts/remote-placement.json",
                },
                workspace_scope=remote_scope,
            ),
            self._attempt(
                placement_request={
                    "kind": "create-child-worktree",
                    "execution_host_id": "host-remote",
                    "parent_workspace_key": "worktree:repo-1::/srv/worktrees/remote-01",
                    "name_hint": "remote-child",
                },
                resolved_placement={
                    "execution_host_id": "host-remote",
                    "workspace_key": "worktree:repo-1::/srv/worktrees/remote-child",
                    "kind": "git-worktree",
                    "path": "/srv/worktrees/remote-child",
                    "receipt_ref": "artifact:openspec/runs/change/run/artifacts/remote-child-placement.json",
                },
                workspace_scope=remote_scope,
            ),
        )

        for attempt in rejected:
            with self.subTest(kind=attempt["execution_profile"]["placement_request"]["kind"]):
                self.fake.calls.clear()
                with self.assertRaisesRegex(DriverError, "only an exact existing"):
                    driver.start_attempt(attempt)
                self.assertEqual(self.fake.calls, [])

    def test_host_capsule_delivers_the_same_profile_and_remote_placement_without_an_agent_cli(self) -> None:
        directory = self.repository / "openspec" / "runs" / "change" / "run-1"
        driver = HostDriver(self.repository, directory)
        attempt = self._attempt(workspace_scope=self._remote_scope(), placement_request={
            "kind": "existing-workspace", "execution_host_id": "host-remote", "workspace_key": "worktree:repo-1::/srv/worktrees/remote-01"
        }, resolved_placement={
            "execution_host_id": "host-remote", "workspace_key": "worktree:repo-1::/srv/worktrees/remote-01", "kind": "git-worktree", "path": None,
            "receipt_ref": "artifact:openspec/runs/change/run/artifacts/remote-placement.json"
        })
        attempt["task"] = self._task()
        attempt["dependency_digest"] = []

        receipt = driver.start_attempt(attempt)
        capsule = json.loads((self.repository / receipt.raw["capsule_path"]).read_text())

        self.assertEqual(capsule["execution_profile"], attempt["execution_profile"])
        self.assertEqual(capsule["workspace_scope"], attempt["workspace_scope"])
        self.assertEqual(receipt.external_refs["resolved_placement"]["execution_host_id"], "host-remote")

    def test_resumes_an_existing_worktree_from_another_checkout(self) -> None:
        another_checkout = self.repository / "another-checkout"
        another_checkout.mkdir()
        self.fake.worktrees[f"repo-1::{another_checkout}"] = self.fake._worktree(
            f"repo-1::{another_checkout}", "host-local", str(another_checkout), False
        )
        self.fake.current = self.fake.worktrees[f"repo-1::{another_checkout}"]
        driver = OrcaDriver(another_checkout, runner=self.fake, environment={"ORCA_CLI_COMMAND": "fake-orca"})
        driver.detect()
        driver.start_run("Profiled", [{"id": "MLK-05", "depends": [], "capsule": "bounded"}])
        attempt = self._attempt(
            placement_request={
                "kind": "existing-workspace",
                "execution_host_id": "host-local",
                "workspace_key": self._local_worktree_key(),
            }
        )
        attempt["recover"] = True
        attempt["external_refs"] = {
            "terminal": {
                "runtime_id": "runtime-1",
                "handle": "term-pinned",
                "pty_id": "pty-1",
                "incarnation_id": "inc-1",
                "worktree_id": f"repo-1::{self.repository}",
                "tab_id": "tab-1",
                "leaf_id": "leaf-1",
                "created_by_harness": True,
                "recovered": False,
                "pinned_creation_owned": False,
                "pane_key": "tab-1:leaf-1",
                "process_incarnation": "pty-1:inc-1",
                "ownership": {
                    "attempt_id": "attempt-mlk-05",
                    "local_task_id": "MLK-05",
                    "external_task_id": "task-1",
                    "dispatch_id": "dispatch-low",
                    "run_id": "run-1",
                },
            }
        }
        self.fake.calls.clear()

        receipt = driver.start_attempt(attempt)

        self.assertTrue(attempt["recover"])
        self.assertEqual(receipt.external_refs["worktree_id"], f"repo-1::{self.repository}")
        self.assertEqual(receipt.external_refs["tier"], "tracked-terminal")
        self.assertEqual(receipt.external_refs["terminal"]["handle"], "term-pinned")
        self.assertEqual(receipt.external_refs["dispatch_id"], "dispatch-low")
        self.assertFalse(any(call[:2] == ["worktree", "current"] for call in self.fake.calls))
        self.assertFalse(any(call[:2] == ["orchestration", "worker-start"] for call in self.fake.calls))
        self.assertFalse(any(call[:2] == ["terminal", "create"] for call in self.fake.calls))
        self.assertIn(["worktree", "show", "--worktree", f"id:repo-1::{self.repository}", "--json"], self.fake.calls)

    def test_resumes_a_child_worktree_from_its_saved_placement(self) -> None:
        another_checkout = self.repository / "another-checkout"
        another_checkout.mkdir()
        self.fake.worktrees[f"repo-1::{another_checkout}"] = self.fake._worktree(
            f"repo-1::{another_checkout}", "host-local", str(another_checkout), False
        )
        self.fake.current = self.fake.worktrees[f"repo-1::{another_checkout}"]
        self.fake.pinned_terminal = {
            "handle": "term-pinned",
            "ptyId": "pty-1",
            "incarnationId": "inc-1",
            "worktreeId": "repo-1::/tmp/child-01",
            "tabId": "tab-1",
            "leafId": "leaf-1",
        }
        driver = OrcaDriver(
            another_checkout,
            runner=self.fake,
            environment={"ORCA_CLI_COMMAND": "fake-orca"},
        )
        driver.detect()
        driver.start_run("Profiled", [{"id": "MLK-05", "depends": [], "capsule": "bounded"}])
        attempt = self._attempt(
            placement_request={
                "kind": "create-child-worktree",
                "execution_host_id": "host-local",
                "name_hint": "child-01",
                "parent_workspace_key": self._local_worktree_key(),
            },
            resolved_placement={
                "execution_host_id": "host-local",
                "workspace_key": "worktree:repo-1::/tmp/child-01",
                "kind": "git-worktree",
                "path": "/tmp/child-01",
                "receipt_ref": "artifact:openspec/runs/change/run/artifacts/child-placement.json",
            },
        )
        attempt["recover"] = True
        attempt["external_refs"] = {
            "terminal": {
                "runtime_id": "runtime-1",
                "handle": "term-pinned",
                "pty_id": "pty-1",
                "incarnation_id": "inc-1",
                "worktree_id": "repo-1::/tmp/child-01",
                "tab_id": "tab-1",
                "leaf_id": "leaf-1",
                "created_by_harness": True,
                "recovered": False,
                "pinned_creation_owned": False,
                "pane_key": "tab-1:leaf-1",
                "process_incarnation": "pty-1:inc-1",
                "ownership": {
                    "attempt_id": "attempt-mlk-05",
                    "local_task_id": "MLK-05",
                    "external_task_id": "task-1",
                    "dispatch_id": "dispatch-low",
                    "run_id": "run-1",
                },
            }
        }
        self.fake.calls.clear()

        receipt = driver.start_attempt(attempt)

        self.assertEqual(receipt.external_refs["worktree_id"], "repo-1::/tmp/child-01")
        self.assertFalse(any(call[:2] == ["worktree", "current"] for call in self.fake.calls))
        self.assertFalse(any(call[:2] == ["worktree", "create"] for call in self.fake.calls))
        self.assertIn(
            ["worktree", "show", "--worktree", "id:repo-1::/tmp/child-01", "--json"],
            self.fake.calls,
        )

    def test_persisted_context_reaches_folder_selected_child_and_ssh_fakes(self) -> None:
        selected = self._attempt(
            placement_request={
                "kind": "existing-workspace",
                "execution_host_id": "host-local",
                "workspace_key": self._local_worktree_key(),
            }
        )
        child = self._attempt(
            placement_request={
                "kind": "create-child-worktree",
                "execution_host_id": "host-local",
                "parent_workspace_key": self._local_worktree_key(),
                "name_hint": "worker-01",
            },
            resolved_placement={
                "execution_host_id": "host-local",
                "workspace_key": "worktree:repo-1::/tmp/child-01",
                "kind": "git-worktree",
                "path": "/tmp/child-01",
                "receipt_ref": "artifact:openspec/runs/change/run/artifacts/child-placement.json",
            },
        )
        ssh = self._attempt(
            workspace_scope=self._remote_scope(),
            placement_request={
                "kind": "existing-workspace",
                "execution_host_id": "host-remote",
                "workspace_key": "worktree:repo-1::/srv/worktrees/remote-01",
            },
            resolved_placement={
                "execution_host_id": "host-remote",
                "workspace_key": "worktree:repo-1::/srv/worktrees/remote-01",
                "kind": "git-worktree",
                "path": "/srv/worktrees/remote-01",
                "receipt_ref": "artifact:openspec/runs/change/run/artifacts/remote-placement.json",
            },
        )

        class RecordingDriver:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def start_attempt(self, attempt: dict[str, object]) -> None:
                self.calls.append(copy.deepcopy(attempt))

        driver = RecordingDriver()
        for name, attempt in {
            "folder": self._attempt(),
            "selected": selected,
            "child": child,
            "ssh": ssh,
        }.items():
            with self.subTest(placement=name):
                driver.start_attempt({**attempt, **persisted_driver_context(attempt)})

        self.assertEqual(len(driver.calls), 4)
        for attempt in driver.calls:
            self.assertEqual(
                attempt["resolved_placement"],
                attempt["execution_profile"]["resolved_placement"],
            )
            self.assertIsInstance(attempt["workspace_scope"], dict)
            self.assertIsInstance(attempt["external_refs"], dict)

    def _started_orca(self) -> OrcaDriver:
        driver = OrcaDriver(self.repository, runner=self.fake, environment={"ORCA_CLI_COMMAND": "fake-orca"})
        driver.detect()
        driver.start_run("Profiled", [{"id": "MLK-05", "depends": [], "capsule": "bounded"}])
        return driver

    def _task(self) -> dict[str, object]:
        return {
            "id": "MLK-05", "title": "Profiles", "depends": [], "paths": ["skills/agent-graph/"], "mode": "write",
            "isolation": "auto", "context": "", "acceptance": "Profiles are explicit.", "check": "python3 -m unittest", "visual": [], "visual_scope": []
        }

    def _attempt(
        self,
        *,
        requested_agent="agent-alpha",
        requested_model="model-fast",
        requested_effort="medium",
        resolved_agent=None,
        resolved_model=None,
        resolved_effort=None,
        fallback_reason=None,
        placement_request=None,
        resolved_placement=None,
        workspace_scope=None,
    ) -> dict[str, object]:
        resolved_agent = resolved_agent or requested_agent
        resolved_model = resolved_model or requested_model
        resolved_effort = resolved_effort or requested_effort
        placement_request = placement_request or {"kind": "current-workspace"}
        resolved_placement = resolved_placement or {
            "execution_host_id": "host-local", "workspace_key": self._local_worktree_key(), "kind": "git-worktree", "path": str(self.repository),
            "receipt_ref": "artifact:openspec/runs/change/run/artifacts/current-placement.json",
        }
        profile = {
            "role": "implementation",
            "requested": {"lane": "fast", "agent": requested_agent, "model": requested_model, "effort": requested_effort},
            "resolved": {"agent": resolved_agent, "model": resolved_model, "effort": resolved_effort},
            "fallback_reason": fallback_reason,
            "placement_request": placement_request,
            "resolved_placement": resolved_placement,
        }
        self.fake.worker_profile = profile
        return {
            "task_id": "MLK-05", "attempt_id": "attempt-mlk-05", "workspace_scope": workspace_scope or self._local_scope(),
            "execution_profile": profile, "resolved_placement": copy.deepcopy(resolved_placement), "external_refs": {},
        }

    def _local_scope(self) -> dict[str, object]:
        scope = copy.deepcopy(WORKSPACE_SCOPES["folder_local"])
        scope["canonical_root"] = str(self.repository)
        worktree = {
            "execution_host_id": "host-local",
            "workspace_key": self._local_worktree_key(),
            "kind": "git-worktree",
            "path": str(self.repository),
            "worktree_path": str(self.repository),
        }
        scope["orchestration_home"] = dict(worktree)
        scope["execution_workspace"] = dict(worktree)
        return scope

    def _local_worktree_key(self) -> str:
        return f"worktree:repo-1::{self.repository}"

    def _remote_scope(self) -> dict[str, object]:
        scope = copy.deepcopy(WORKSPACE_SCOPES["worktree_remote"])
        scope["execution_workspace"].update({"workspace_key": "worktree:repo-1::/srv/worktrees/remote-01", "path": "/srv/worktrees/remote-01", "worktree_path": "/srv/worktrees/remote-01"})
        return scope


if __name__ == "__main__":
    unittest.main()
