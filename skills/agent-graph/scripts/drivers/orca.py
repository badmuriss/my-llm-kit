"""Orca transport with supervised and incarnation-safe tracked-terminal tiers."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from drivers.base import DriverError, DriverReceipt


Runner = Callable[[Sequence[str]], Mapping[str, Any]]
FALLBACK_CODES = frozenset({"selector_not_found"})


def _attempt_terminal_title(run_id: str, attempt_id: str) -> str:
    return f"agent-graph-{run_id}-{attempt_id}"


def resolve_orca_command(environment: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """Select one Orca CLI without probing alternative executables."""

    values = dict(environment or os.environ)
    configured = values.get("ORCA_CLI_COMMAND", "").strip()
    if configured:
        command = tuple(shlex.split(configured, posix=os.name != "nt"))
        if not command:
            raise DriverError("ORCA_CLI_COMMAND is empty", code="invalid_cli")
        return command
    if values.get("ORCA_DEV_REPO_ROOT"):
        return ("orca-dev",)
    inside_orca = bool(values.get("ORCA_TERMINAL_HANDLE") or values.get("ORCA_WORKTREE_ID"))
    if sys.platform.startswith("linux") and not inside_orca:
        return ("orca-ide",)
    return ("orca",)


def _default_runner(argv: Sequence[str]) -> Mapping[str, Any]:
    completed = subprocess.run(
        list(argv), check=False, capture_output=True, text=True, encoding="utf-8"
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no output"
        raise DriverError(
            f"Orca returned non-JSON output: {detail}",
            code="invalid_receipt",
            receipt={"argv": list(argv), "exit_code": completed.returncode},
        ) from error
    if not isinstance(payload, Mapping):
        raise DriverError("Orca receipt must be an object", code="invalid_receipt", receipt=payload)
    return dict(payload)


def _result(receipt: Mapping[str, Any]) -> Mapping[str, Any]:
    value = receipt.get("result", receipt)
    return value if isinstance(value, Mapping) else {}


def _entity(receipt: Mapping[str, Any], *names: str) -> Mapping[str, Any]:
    value = _result(receipt)
    for name in names:
        nested = value.get(name)
        if isinstance(nested, Mapping):
            return nested
    return value


def _error(receipt: Mapping[str, Any]) -> tuple[str, str]:
    value = receipt.get("error")
    if not isinstance(value, Mapping):
        return "orca_error", "Orca command failed"
    return str(value.get("code") or "orca_error"), str(value.get("message") or "Orca command failed")


def _first(value: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in value and value[name] is not None:
            return value[name]
    return None


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, Mapping):
        for key in ("items", "terminals", "tasks", "messages"):
            if isinstance(value.get(key), list):
                return list(value[key])
    return []


def _terminal_handle(value: Any) -> str | None:
    if isinstance(value, Mapping):
        for key in ("handle", "terminalHandle", "agentTerminalHandle"):
            handle = value.get(key)
            if isinstance(handle, str) and handle:
                return handle
        for nested in value.values():
            handle = _terminal_handle(nested)
            if handle:
                return handle
    elif isinstance(value, list):
        for nested in value:
            handle = _terminal_handle(nested)
            if handle:
                return handle
    return None


def _terminal_handles_for_title(value: Any, title: str) -> list[str]:
    handles: list[str] = []
    if isinstance(value, Mapping):
        if value.get("title") == title:
            handle = _terminal_handle(value)
            if handle:
                handles.append(handle)
        for nested in value.values():
            handles.extend(_terminal_handles_for_title(nested, title))
    elif isinstance(value, list):
        for nested in value:
            handles.extend(_terminal_handles_for_title(nested, title))
    return list(dict.fromkeys(handles))


class OrcaDriver:
    """Translate Agent Graph actions to one pinned Orca runtime."""

    def __init__(
        self,
        repository: Path,
        *,
        runner: Runner | None = None,
        environment: Mapping[str, str] | None = None,
        agent: str = "codex",
    ) -> None:
        self.repository = Path(repository).resolve()
        self.command = resolve_orca_command(environment)
        self.runner = runner or _default_runner
        self.agent = agent
        self.runtime_id: str | None = None
        self.worktree_id: str | None = None
        self.run_id: str | None = None
        self.task_ids: dict[str, str] = {}
        self.created_terminals: dict[str, dict[str, Any]] = {}
        self._terminal_snapshot: set[str] = set()

    def _call(self, *arguments: str, allow_error: bool = False) -> Mapping[str, Any]:
        argv = [*self.command, *arguments]
        try:
            receipt = self.runner(argv)
        except DriverError:
            raise
        except (OSError, subprocess.SubprocessError) as error:
            raise DriverError(
                f"selected Orca CLI failed: {error}",
                code="cli_unavailable",
                receipt={"argv": argv},
            ) from error
        if not isinstance(receipt, Mapping):
            raise DriverError("Orca runner returned a non-object", code="invalid_receipt")
        normalized = dict(receipt)
        if normalized.get("ok") is False and not allow_error:
            code, message = _error(normalized)
            raise DriverError(message, code=code, receipt=normalized)
        return normalized

    def detect(self) -> DriverReceipt:
        status = self._call("status", "--json")
        status_result = _result(status)
        runtime = status_result.get("runtime")
        graph = status_result.get("graph")
        if not isinstance(runtime, Mapping) or not isinstance(graph, Mapping):
            raise DriverError("Orca status omitted runtime or graph state", code="preflight_failed", receipt=status)
        capabilities = runtime.get("capabilities")
        if (
            runtime.get("reachable") is not True
            or runtime.get("state") != "ready"
            or graph.get("state") != "ready"
            or not isinstance(capabilities, list)
            or "orchestration.contract.v1" not in capabilities
        ):
            raise DriverError("Orca runtime lacks the required orchestration contract", code="preflight_failed", receipt=status)
        worktree = self._call("worktree", "current", "--json")
        worktree_result = _entity(worktree, "worktree")
        worktree_path = Path(str(_first(worktree_result, "path", "worktreePath") or "")).resolve()
        worktree_id = _first(worktree_result, "id", "worktreeId")
        if worktree_path != self.repository or not isinstance(worktree_id, str) or "::" not in worktree_id:
            raise DriverError("Orca did not resolve the exact repository worktree", code="selector_not_found", receipt=worktree)
        shown = self._call("worktree", "show", "--worktree", f"id:{worktree_id}", "--json")
        shown_result = _entity(shown, "worktree")
        shown_path = Path(str(_first(shown_result, "path", "worktreePath") or "")).resolve()
        if shown_path != self.repository:
            raise DriverError("Orca worktree selector resolved another checkout", code="selector_not_found", receipt=shown)
        terminals = self._call("terminal", "list", "--worktree", f"id:{worktree_id}", "--json")
        self._terminal_snapshot = {
            str(_first(item, "handle", "terminalHandle"))
            for item in _list(_result(terminals))
            if isinstance(item, Mapping) and _first(item, "handle", "terminalHandle")
        }
        meta = status.get("_meta")
        self.runtime_id = str(meta.get("runtimeId")) if isinstance(meta, Mapping) and meta.get("runtimeId") else None
        self.worktree_id = worktree_id
        return DriverReceipt(
            "detect",
            "available",
            external_refs={"runtime_id": self.runtime_id, "worktree_id": worktree_id, "capabilities": capabilities},
            raw={"status": status, "worktree": worktree, "worktree_show": shown, "terminal_list": terminals},
        )

    def start_run(
        self,
        objective: str,
        tasks: Sequence[Mapping[str, Any]],
        *,
        retry_request: str | None = None,
    ) -> DriverReceipt:
        if not self.worktree_id:
            self.detect()
        run_arguments = ["orchestration", "run-create", "--objective", objective]
        if retry_request:
            run_arguments.extend(["--retry-request", retry_request])
        run_arguments.append("--json")
        run = self._call(*run_arguments)
        run_result = _entity(run, "run")
        run_id = _first(run_result, "id", "runId")
        if not isinstance(run_id, str) or not run_id:
            raise DriverError("Orca run receipt omitted its ID", code="invalid_receipt", receipt=run)
        self.run_id = run_id
        task_receipts: list[Mapping[str, Any]] = []
        pending = {str(task["id"]): task for task in tasks}
        known_local_ids = set(pending)
        ordered: list[Mapping[str, Any]] = []
        while pending:
            progressed = False
            for local_id, task in list(pending.items()):
                dependencies = [str(item) for item in task.get("depends", [])]
                if all(dependency not in pending for dependency in dependencies):
                    unknown = [dependency for dependency in dependencies if dependency not in known_local_ids]
                    if unknown:
                        raise DriverError(
                            f"Orca task {local_id} references unknown dependencies: {', '.join(unknown)}",
                            code="invalid_task_graph",
                        )
                    ordered.append(task)
                    del pending[local_id]
                    progressed = True
            if not progressed:
                raise DriverError("Orca task dependencies contain a cycle", code="invalid_task_graph")
        for task in ordered:
            local_id = str(task["id"])
            dependencies = [self.task_ids[str(item)] for item in task.get("depends", [])]
            capsule = str(task.get("capsule", task.get("title", local_id)))
            argv = ["orchestration", "task-create", "--spec", capsule, "--deps", json.dumps(dependencies), "--run", run_id]
            if retry_request:
                argv.extend(["--retry-request", f"{retry_request}-{local_id}"])
            argv.append("--json")
            receipt = self._call(*argv)
            external_id = _first(_entity(receipt, "task"), "id", "taskId")
            if not isinstance(external_id, str) or not external_id:
                raise DriverError("Orca task receipt omitted its ID", code="invalid_receipt", receipt=receipt)
            self.task_ids[local_id] = external_id
            task_receipts.append(receipt)
        return DriverReceipt(
            "start_run", "started", external_refs={"run_id": run_id, "task_ids": dict(self.task_ids)}, raw={"run": run, "tasks": task_receipts}
        )

    def _terminal_identity(self, terminal: Mapping[str, Any]) -> dict[str, Any]:
        result = _entity(terminal, "terminal", "createdTerminal", "agentTerminal")
        identity = {
            "runtime_id": self.runtime_id,
            "handle": _first(result, "handle", "terminalHandle"),
            "pty_id": _first(result, "ptyId", "pty_id"),
            "incarnation_id": _first(result, "incarnationId", "incarnation_id"),
            "worktree_id": _first(result, "worktreeId", "worktree_id") or self.worktree_id,
            "tab_id": _first(result, "tabId", "tab_id"),
            "leaf_id": _first(result, "leafId", "leaf_id"),
            "created_by_harness": True,
        }
        if not all(identity[key] for key in ("handle", "pty_id", "incarnation_id", "worktree_id", "tab_id", "leaf_id")):
            raise DriverError("created terminal lacks incarnation identity", code="invalid_receipt", receipt=terminal)
        identity["pane_key"] = f"{identity['tab_id']}:{identity['leaf_id']}"
        identity["process_incarnation"] = f"{identity['pty_id']}:{identity['incarnation_id']}"
        return identity

    def _close_created_terminal(self, expected: Mapping[str, Any]) -> dict[str, Any]:
        shown = self._call("terminal", "show", "--terminal", str(expected["handle"]), "--json")
        actual = self._terminal_identity(shown)
        keys = (
            "runtime_id",
            "handle",
            "pty_id",
            "incarnation_id",
            "worktree_id",
            "tab_id",
            "leaf_id",
        )
        if any(actual[key] != expected[key] for key in keys):
            raise DriverError(
                "terminal incarnation changed before cleanup",
                code="cleanup_unproven",
                receipt=shown,
            )
        closed = self._call(
            "terminal", "close", "--terminal", str(expected["handle"]), "--tab", "--json"
        )
        listed = self._call(
            "terminal", "list", "--worktree", f"id:{expected['worktree_id']}", "--json"
        )
        live_handles = {
            str(_first(item, "handle", "terminalHandle"))
            for item in _list(_result(listed))
            if isinstance(item, Mapping)
        }
        if expected["handle"] in live_handles:
            raise DriverError(
                "created terminal remains live after close",
                code="cleanup_failed",
                receipt=listed,
            )
        return {"show": shown, "close": closed, "list": listed}

    def start_attempt(self, attempt: Mapping[str, Any]) -> DriverReceipt:
        local_task = str(attempt["task_id"])
        attempt_id = str(attempt["attempt_id"])
        recovering = attempt.get("recover") is True
        external_task = self.task_ids.get(local_task, str(attempt.get("external_task_id", "")))
        if not external_task or not self.run_id or not self.worktree_id:
            raise DriverError("Orca run and task identities are required", code="not_started")
        retry_request = f"{self.run_id}-{attempt_id}"
        supervised = self._call(
            "orchestration", "worker-start", "--task", external_task, "--worktree", f"id:{self.worktree_id}", "--agent", self.agent, "--run", self.run_id, "--retry-request", retry_request, "--json", allow_error=True
        )
        if supervised.get("ok") is not False:
            result = _result(supervised)
            dispatch_id = _first(result, "dispatchId", "dispatch_id", "id")
            return DriverReceipt(
                "start_attempt", "started", local_ids={"task_id": local_task, "attempt_id": attempt_id}, external_refs={"tier": "supervised", "run_id": self.run_id, "task_id": external_task, "dispatch_id": dispatch_id}, raw=supervised
            )
        code, message = _error(supervised)
        if code not in FALLBACK_CODES:
            raise DriverError(message, code=code, receipt=supervised)
        failure = _result(supervised)
        if failure.get("outcome") == "outcome_unknown" or failure.get("residualResources"):
            raise DriverError("supervised failure left ambiguous resources", code="unsafe_fallback", receipt=supervised)
        terminal_title = _attempt_terminal_title(self.run_id, attempt_id)
        existing_terminals = self._call(
            "terminal",
            "list",
            "--worktree",
            f"id:{self.worktree_id}",
            "--include-visual-layouts",
            "--json",
        )
        recovered_handles = _terminal_handles_for_title(existing_terminals, terminal_title)
        if len(recovered_handles) > 1:
            raise DriverError(
                "Orca found multiple terminals for the reserved attempt identity",
                code="unsafe_fallback",
                receipt=existing_terminals,
            )
        recovered_handle = recovered_handles[0] if recovered_handles else None
        if recovered_handle and not recovering:
            raise DriverError(
                "Orca found a pre-existing terminal outside explicit attempt recovery",
                code="unsafe_fallback",
                receipt=existing_terminals,
            )
        terminal = (
            self._call("terminal", "show", "--terminal", recovered_handle, "--json")
            if recovered_handle
            else self._call(
                "terminal", "create", "--worktree", f"id:{self.worktree_id}", "--title", terminal_title, "--command", self.agent, "--json"
            )
        )
        terminal_show: Mapping[str, Any] | None = None
        try:
            identity = self._terminal_identity(terminal)
        except DriverError:
            handle = _terminal_handle(terminal)
            if not handle:
                raise
            terminal_show = self._call("terminal", "show", "--terminal", handle, "--json")
            identity = self._terminal_identity(terminal_show)
        if identity["handle"] in self._terminal_snapshot and not (recovering and recovered_handle):
            raise DriverError("Orca reused a pre-existing terminal for fallback", code="unsafe_fallback", receipt=terminal)
        waited: Mapping[str, Any] | None = None
        dispatched: Mapping[str, Any] | None = None
        dispatch_show: Mapping[str, Any] | None = None
        try:
            waited = self._call("terminal", "wait", "--terminal", str(identity["handle"]), "--for", "tui-idle", "--timeout-ms", "60000", "--json")
            dispatched = self._call("orchestration", "dispatch", "--task", external_task, "--to", str(identity["handle"]), "--run", self.run_id, "--inject", "--retry-request", retry_request, "--json")
            dispatch_id = _first(_result(dispatched), "id", "dispatchId", "dispatch_id")
            if recovering:
                dispatch_show = self._call("orchestration", "dispatch-show", "--task", external_task, "--json")
                provider_dispatch = _entity(dispatch_show, "dispatch")
                expected_incarnation = f"{identity['worktree_id']}@@{identity['process_incarnation']}"
                if (
                    _first(provider_dispatch, "id", "dispatchId", "dispatch_id") != dispatch_id
                    or _first(provider_dispatch, "task_id", "taskId") != external_task
                    or _first(provider_dispatch, "assignee_handle", "assigneeHandle", "terminalHandle") != identity["handle"]
                    or _first(provider_dispatch, "assignee_pane_key", "assigneePaneKey", "paneKey") != identity["pane_key"]
                    or _first(provider_dispatch, "process_incarnation", "processIncarnation") != expected_incarnation
                ):
                    raise DriverError(
                        "Orca could not prove the recovered terminal belongs to the reserved Dispatch",
                        code="unsafe_fallback",
                        receipt={"dispatch": dispatched, "dispatch_show": dispatch_show, "terminal": terminal_show or terminal},
                    )
        except DriverError as error:
            try:
                rollback = self._close_created_terminal(identity)
            except DriverError as cleanup_error:
                raise DriverError(
                    "Orca fallback failed and its terminal could not be cleaned safely",
                    code="cleanup_failed",
                    receipt={
                        "cause": {"code": error.code, "message": str(error), "receipt": error.receipt},
                        "rollback": {"code": cleanup_error.code, "message": str(cleanup_error), "receipt": cleanup_error.receipt},
                    },
                ) from error
            raise DriverError(
                str(error),
                code=error.code,
                receipt={"cause": error.receipt, "rollback": rollback},
            ) from error
        self.created_terminals[attempt_id] = identity
        return DriverReceipt(
            "start_attempt",
            "started",
            local_ids={"task_id": local_task, "attempt_id": attempt_id},
            external_refs={"tier": "tracked-terminal", "run_id": self.run_id, "task_id": external_task, "dispatch_id": dispatch_id, "terminal": identity},
            raw={"worker_start": supervised, "terminal_snapshot": existing_terminals, "recovered_terminal": bool(recovered_handle), "terminal_create": terminal, "terminal_show": terminal_show, "terminal_wait": waited, "dispatch": dispatched, "dispatch_show": dispatch_show},
            degradation={"code": code, "message": message, "from": "supervised", "to": "tracked-terminal"},
        )

    def poll(
        self,
        attempt: Mapping[str, Any],
        *,
        cursor: str | None = None,
        include_delivery: bool = True,
    ) -> DriverReceipt:
        tier = str(attempt["tier"])
        dispatch_id = str(attempt["dispatch_id"])
        if tier == "supervised":
            shown = self._call("orchestration", "worker-show", "--dispatch", dispatch_id, "--json")
            argv = ["orchestration", "worker-read", "--dispatch", dispatch_id, "--limit", "50"]
        elif tier == "tracked-terminal":
            shown = self._call("orchestration", "dispatch-show", "--task", str(attempt["external_task_id"]), "--json")
            argv = ["terminal", "read", "--terminal", str(attempt["terminal_handle"]), "--limit", "50"]
        else:
            raise DriverError(f"unknown Orca lifecycle tier: {tier}", code="invalid_tier")
        if cursor:
            argv.extend(["--cursor", cursor])
        argv.append("--json")
        read = self._call(*argv)
        delivery = self.check_delivery(str(attempt.get("run_id", self.run_id))) if include_delivery else None
        result = _result(read)
        next_cursor = _first(result, "nextCursor", "cursor", "latestCursor")
        return DriverReceipt("poll", "observed", external_refs={"tier": tier, "dispatch_id": dispatch_id, "cursor": next_cursor}, raw={"show": shown, "read": read, "delivery": delivery})

    def check_delivery(self, run_id: str) -> Mapping[str, Any]:
        return self._call(
            "orchestration",
            "check",
            "--run",
            run_id,
            "--wait",
            "--types",
            "question,worker_done,escalation",
            "--timeout-ms",
            "1000",
            "--json",
        )

    def send(self, attempt: Mapping[str, Any], message: Mapping[str, Any]) -> DriverReceipt:
        attempt_refs = attempt.get("external_refs")
        refs = attempt_refs if isinstance(attempt_refs, Mapping) else {}
        dispatch_id = attempt.get("dispatch_id") or refs.get("dispatch_id")
        run_id = attempt.get("run_id") or refs.get("run_id") or self.run_id
        if message.get("kind") == "reply":
            receipt = self._call("orchestration", "reply", "--id", str(message["message_id"]), "--body", str(message["body"]), "--run", str(run_id), "--json")
        else:
            if not dispatch_id:
                raise DriverError("attempt has no Orca Dispatch ID", code="invalid_attempt")
            receipt = self._call("orchestration", "send", "--to", f"dispatch:{dispatch_id}", "--subject", str(message.get("subject", "Coordinator guidance")), "--body", str(message["body"]), "--json")
        return DriverReceipt(
            "send",
            "sent",
            external_refs={"dispatch_id": str(dispatch_id) if dispatch_id else "", "run_id": str(run_id)},
            raw=receipt,
        )

    def ack_delivery(self, run_id: str, delivery_id: str) -> Mapping[str, Any]:
        return self._call(
            "orchestration", "check", "--run", run_id, "--ack", delivery_id, "--json"
        )

    def release(self, attempt: Mapping[str, Any]) -> DriverReceipt:
        tier = str(attempt["tier"])
        dispatch_id = str(attempt["dispatch_id"])
        if tier == "supervised":
            receipt = self._call("orchestration", "worker-release", "--dispatch", dispatch_id, "--json", allow_error=True)
            if receipt.get("ok") is False:
                code, message = _error(receipt)
                if code != "already_released":
                    raise DriverError(message, code=code, receipt=receipt)
            return DriverReceipt("release", "released", external_refs={"tier": tier, "dispatch_id": dispatch_id}, raw=receipt)
        if tier != "tracked-terminal":
            raise DriverError(f"unknown Orca lifecycle tier: {tier}", code="invalid_tier")
        attempt_id = str(attempt["attempt_id"])
        expected = self.created_terminals.get(attempt_id)
        if not expected:
            raise DriverError("tracked terminal has no creation receipt", code="cleanup_unproven")
        listed = self._call(
            "terminal", "list", "--worktree", f"id:{expected['worktree_id']}", "--json"
        )
        live_handles = {
            str(_first(item, "handle", "terminalHandle"))
            for item in _list(_result(listed))
            if isinstance(item, Mapping)
        }
        if expected["handle"] not in live_handles:
            return DriverReceipt(
                "release",
                "released",
                external_refs={
                    "tier": tier,
                    "dispatch_id": dispatch_id,
                    "terminal": expected,
                    "prior_cleanup": True,
                },
                raw={"list": listed, "state": "already_absent"},
            )
        cleanup = self._close_created_terminal(expected)
        return DriverReceipt("release", "released", external_refs={"tier": tier, "dispatch_id": dispatch_id, "terminal": expected}, raw=cleanup)

    def reconcile(self, attempts: Sequence[Mapping[str, Any]]) -> DriverReceipt:
        observations: list[dict[str, Any]] = []
        for attempt in attempts:
            if attempt.get("status") in {"reserved", "interrupted"} or not attempt.get("dispatch_id"):
                attempt_id = str(attempt.get("attempt_id") or "")
                local_task = str(attempt.get("task_id") or "")
                external_task = self.task_ids.get(local_task)
                dispatch = (
                    self._call(
                        "orchestration",
                        "dispatch-show",
                        "--task",
                        external_task,
                        "--json",
                        allow_error=True,
                    )
                    if external_task
                    else {"ok": False, "error": {"code": "task_not_bound"}}
                )
                terminals = self._call(
                    "terminal",
                    "list",
                    "--worktree",
                    f"id:{self.worktree_id}",
                    "--include-visual-layouts",
                    "--json",
                )
                expected_title = (
                    _attempt_terminal_title(self.run_id, attempt_id)
                    if self.run_id
                    else None
                )
                title_present = bool(
                    expected_title
                    and _terminal_handles_for_title(terminals, expected_title)
                )
                resource_state = (
                    "present"
                    if dispatch.get("ok") is not False or title_present
                    else "absent" if expected_title else "unknown"
                )
                observations.append(
                    {
                        "attempt_id": attempt_id,
                        "status": attempt.get("status"),
                        "resource_state": resource_state,
                        "dispatch": dispatch,
                        "terminal_list": terminals,
                    }
                )
                continue
            try:
                observed = self.poll(attempt)
                observations.append(observed.to_dict())
            except DriverError as error:
                observations.append({"attempt_id": attempt.get("attempt_id"), "status": "error", "code": error.code, "receipt": error.receipt})
        return DriverReceipt("reconcile", "observed", raw=observations)
