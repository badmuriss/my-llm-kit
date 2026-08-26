"""Orca transport with supervised and incarnation-safe tracked-terminal tiers."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from drivers.base import (
    DriverError,
    DriverReceipt,
    build_capability_receipt,
    capability,
    execution_profile_from_attempt,
)
from context_capsules import build_reused_session_handoff
from browser_surfaces import (  # noqa: E402
    BrowserSurfaceError,
    public_receipt,
    unavailable_receipt,
    validate_browser_surface_request,
    validate_receipt_for_request,
)


Runner = Callable[[Sequence[str]], Mapping[str, Any]]
FALLBACK_CODES = frozenset({"selector_not_found"})
VERIFIED_AGENT_PROMPT_MINIMUM_VERSION = (1, 4, 186)


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


def _runtime_version_at_least(value: Any, minimum: tuple[int, int, int]) -> bool:
    if not isinstance(value, str):
        return False
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", value)
    if match is None:
        return False
    return tuple(int(part) for part in match.groups()) >= minimum


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


def _public_git_worktree(receipt: Mapping[str, Any]) -> dict[str, str]:
    """Normalize only the authoritative fields exposed by public worktree show."""

    worktree = _entity(receipt, "worktree")
    worktree_id = worktree.get("id")
    host_id = worktree.get("hostId")
    path = worktree.get("path")
    git = worktree.get("git")
    is_main_worktree = worktree.get("isMainWorktree")
    git_path = git.get("path") if isinstance(git, Mapping) else None
    git_is_main_worktree = git.get("isMainWorktree") if isinstance(git, Mapping) else None
    if (
        not isinstance(worktree_id, str)
        or "::" not in worktree_id
        or not isinstance(host_id, str)
        or not host_id
        or not isinstance(path, str)
        or not path
        or not isinstance(git, Mapping)
        or not isinstance(is_main_worktree, bool)
        or git_path != path
        or not isinstance(git_is_main_worktree, bool)
        or git_is_main_worktree != is_main_worktree
    ):
        raise DriverError(
            "Orca worktree receipt omitted authoritative Git worktree identity",
            code="placement_not_resolved",
            receipt=receipt,
        )
    return {
        "id": worktree_id,
        "execution_host_id": host_id,
        "workspace_key": f"worktree:{worktree_id}",
        "kind": "git-worktree",
        "path": path,
    }


class OrcaDriver:
    """Translate Agent Graph actions to one pinned Orca runtime."""

    def __init__(
        self,
        repository: Path,
        *,
        runner: Runner | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self.repository = Path(repository).resolve()
        self.command = resolve_orca_command(environment)
        self.runner = runner or _default_runner
        self.runtime_id: str | None = None
        self.runtime_version: str | None = None
        self.worktree_id: str | None = None
        self.runtime_capabilities: frozenset[str] = frozenset()
        self.run_id: str | None = None
        self.task_ids: dict[str, str] = {}
        self.created_terminals: dict[str, dict[str, Any]] = {}
        self._terminal_snapshot: set[str] = set()
        self._managed_reuse_inflight: dict[str, Any] | None = None

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

    def _wait_for_terminal(
        self, handle: str, condition: str, *, timeout_ms: int = 60_000
    ) -> Mapping[str, Any]:
        receipt = self._call(
            "terminal", "wait", "--terminal", handle, "--for", condition,
            "--timeout-ms", str(timeout_ms), "--json",
        )
        wait = _entity(receipt, "wait")
        expected_status = {"tui-idle": "running", "exit": "exited"}.get(condition)
        if (
            expected_status is None
            or wait.get("satisfied") is not True
            or wait.get("condition") != condition
            or wait.get("status") != expected_status
        ):
            raise DriverError(
                f"terminal wait did not confirm {condition}",
                code="terminal_wait_unconfirmed",
                receipt=receipt,
            )
        return receipt

    def _send_terminal_handoff(
        self, handle: str, text: str, *extra_arguments: str
    ) -> Mapping[str, Any]:
        sent = self._call(
            "terminal", "send", "--terminal", handle, "--text", text,
            *extra_arguments, "--enter", "--json",
        )
        delivery = _entity(sent, "send")
        delivery_receipt = delivery.get("deliveryReceipt")
        managed_lease = "--lease-input" in extra_arguments
        receipt_state = (
            delivery_receipt.get("state")
            if isinstance(delivery_receipt, Mapping)
            else None
        )
        verified_runtime = (
            _runtime_version_at_least(
                self.runtime_version, VERIFIED_AGENT_PROMPT_MINIMUM_VERSION
            )
            and delivery.get("handle") == handle
        )
        managed_delivery_proven = (
            not managed_lease
            or receipt_state in {"written_to_pty", "acknowledged"}
        )
        if not verified_runtime or not managed_delivery_proven:
            raise DriverError(
                "terminal send lacks a versioned turn-start acknowledgement",
                code="session_delivery_unproven",
                receipt=sent,
            )
        return {
            **dict(sent),
            "delivery_confirmation": {
                "kind": "turn_started",
                "runtime_version": self.runtime_version,
                **({"receipt_state": receipt_state} if managed_lease else {}),
            },
        }

    def detect(self) -> DriverReceipt:
        status = self._call("status", "--json")
        status_result = _result(status)
        runtime = status_result.get("runtime")
        graph = status_result.get("graph")
        if not isinstance(runtime, Mapping) or not isinstance(graph, Mapping):
            raise DriverError("Orca status omitted runtime or graph state", code="preflight_failed", receipt=status)
        capabilities = runtime.get("capabilities")
        runtime_version = runtime.get("appVersion")
        if (
            runtime.get("reachable") is not True
            or runtime.get("state") != "ready"
            or graph.get("state") != "ready"
            or not isinstance(capabilities, list)
            or "orchestration.contract.v1" not in capabilities
        ):
            raise DriverError("Orca runtime lacks the required orchestration contract", code="preflight_failed", receipt=status)
        worktree = self._call("worktree", "current", "--json")
        current_worktree = _public_git_worktree(worktree)
        worktree_path = Path(current_worktree["path"]).resolve()
        worktree_id = current_worktree["id"]
        shown = self._call("worktree", "show", "--worktree", f"id:{worktree_id}", "--json")
        shown_worktree = _public_git_worktree(shown)
        shown_path = Path(shown_worktree["path"]).resolve()
        if shown_worktree["id"] != worktree_id or shown_path != worktree_path:
            raise DriverError("Orca current worktree changed during detection", code="selector_not_found", receipt=shown)
        if shown_path != self.repository:
            raise DriverError(
                "Orca worktree selector resolved another checkout",
                code="selector_not_found",
                receipt=shown,
            )
        terminals = self._call("terminal", "list", "--worktree", f"id:{worktree_id}", "--json")
        self._terminal_snapshot = {
            str(_first(item, "handle", "terminalHandle"))
            for item in _list(_result(terminals))
            if isinstance(item, Mapping) and _first(item, "handle", "terminalHandle")
        }
        meta = status.get("_meta")
        self.runtime_id = str(meta.get("runtimeId")) if isinstance(meta, Mapping) and meta.get("runtimeId") else None
        if self.runtime_id is None:
            raise DriverError(
                "Orca status omitted the runtime identity required for terminal ownership",
                code="preflight_failed",
                receipt=status,
            )
        self.worktree_id = worktree_id
        self.runtime_capabilities = frozenset(
            capability for capability in capabilities if isinstance(capability, str)
        )
        self.runtime_version = runtime_version if isinstance(runtime_version, str) else None
        portable_capabilities = {
            "local_checks": capability(
                "supported",
                method="configuration",
                evidence="orca:coordinator-local-check-boundary",
            ),
            "user_questions": capability(
                "supported",
                method="provider_reported",
                evidence="orca:orchestration.contract.v1",
            ),
            "process_tree_cleanup": capability(
                "supported",
                method="observed",
                evidence="orca:terminal-list-lifecycle-snapshot",
            ),
            "isolated_workspace": capability(
                "supported",
                method="provider_reported",
                evidence="orca:orchestration.contract.v1-worktree-boundary",
            ),
            "visible_worker_dispatch": capability(
                "supported",
                method="provider_reported",
                evidence="orca:orchestration.contract.v1-visible-worker",
            ),
            "durable_worker_handle": capability(
                "supported",
                method="observed",
                evidence="orca:runtime-and-terminal-identity",
            ),
            "browser_surface": (
                capability(
                    "supported",
                    method="provider_reported",
                    evidence="orca:browser.surface.v1",
                )
                if "browser.surface.v1" in self.runtime_capabilities
                else capability(
                    "unsupported",
                    reason="Orca runtime did not advertise browser.surface.v1.",
                )
            ),
            "usage_metrics": (
                capability(
                    "supported",
                    method="provider_reported",
                    evidence="orca:usage.metrics.v1",
                )
                if "usage.metrics.v1" in self.runtime_capabilities
                else capability(
                    "unavailable",
                    reason="Orca runtime did not expose usage.metrics.v1.",
                )
            ),
            "cache_metrics": (
                capability(
                    "supported",
                    method="provider_reported",
                    evidence="orca:cache.metrics.v1",
                )
                if "cache.metrics.v1" in self.runtime_capabilities
                else capability(
                    "unavailable",
                    reason="Orca runtime did not expose cache.metrics.v1.",
                )
            ),
        }
        capability_receipt = build_capability_receipt(
            "orca",
            portable_capabilities,
            version="1",
            extensions={
                "orca": {
                    "runtime_id": self.runtime_id,
                    "worktree_id": worktree_id,
                    "runtime_capabilities": sorted(self.runtime_capabilities),
                    "terminal_snapshot": sorted(self._terminal_snapshot),
                }
            },
        )
        return DriverReceipt(
            "detect",
            "available",
            external_refs={
                "runtime_id": self.runtime_id,
                "worktree_id": worktree_id,
                "capabilities": capability_receipt["capabilities"],
                "capability_receipt": capability_receipt,
            },
            raw={"status": status, "worktree": worktree, "worktree_show": shown, "terminal_list": terminals},
        )

    def _worktree_selector(self, resolved: Mapping[str, Any]) -> str:
        workspace_key = resolved["workspace_key"]
        if isinstance(workspace_key, str) and workspace_key.startswith("worktree:"):
            worktree_id = workspace_key.removeprefix("worktree:")
            if "::" in worktree_id:
                return f"id:{worktree_id}"
        path = resolved["path"]
        if isinstance(path, str) and path:
            return f"path:{path}"
        raise DriverError(
            "Orca cannot select the resolved workspace with a public exact selector",
            code="placement_not_supported",
            receipt={"resolved_placement": dict(resolved)},
        )

    def _pinned_terminal(self, attempt: Mapping[str, Any]) -> Mapping[str, Any] | None:
        terminal = attempt.get("terminal")
        if isinstance(terminal, Mapping):
            return terminal
        refs = attempt.get("external_refs")
        if isinstance(refs, Mapping) and isinstance(refs.get("terminal"), Mapping):
            return refs["terminal"]
        return None

    def _resolve_worktree(
        self,
        profile: Mapping[str, Any],
        attempt: Mapping[str, Any],
        *,
        recovering: bool,
        restoring: bool = False,
    ) -> Mapping[str, Any]:
        request = profile["placement_request"]
        resolved = profile["resolved_placement"]
        kind = request["kind"]
        host_id = resolved["execution_host_id"]
        workspace_key = resolved["workspace_key"]
        workspace_scope = attempt["workspace_scope"]
        remote_execution = workspace_scope["execution_host"]["boundary"] == "remote"
        if remote_execution and kind != "existing-workspace":
            raise DriverError(
                "remote placement supports only an exact existing workspace",
                code="placement_not_supported",
                receipt={"placement_request": request, "resolved_placement": resolved},
            )

        def show_worktree(selector: str) -> Mapping[str, Any]:
            environment = ["--environment", host_id] if remote_execution else []
            return self._call(
                "worktree",
                "show",
                *environment,
                "--worktree",
                selector,
                "--json",
            )

        pinned_terminal = self._pinned_terminal(attempt)
        if recovering:
            if pinned_terminal and (
                pinned_terminal.get("created_by_harness") is not True
                and pinned_terminal.get("pinned_creation_owned") is not True
            ):
                raise DriverError(
                    "recovery requires the original owned terminal identity",
                    code="cleanup_unproven",
                    receipt={"terminal": pinned_terminal},
                )
            if pinned_terminal:
                pinned_worktree_id = pinned_terminal.get("worktree_id")
                if not isinstance(pinned_worktree_id, str) or not pinned_worktree_id:
                    raise DriverError(
                        "recovery terminal identity lacks its pinned worktree ID",
                        code="cleanup_unproven",
                        receipt={"terminal": pinned_terminal},
                    )
            receipt = show_worktree(self._worktree_selector(resolved))
        elif restoring:
            receipt = show_worktree(self._worktree_selector(resolved))
        elif kind == "current-workspace":
            if resolved["path"] is None:
                raise DriverError(
                    "current-workspace placement requires its exact pinned path",
                    code="placement_not_resolved",
                    receipt={"resolved_placement": resolved},
                )
            if Path(resolved["path"]).resolve() != self.repository:
                raise DriverError(
                    "current-workspace placement does not match this repository checkout",
                    code="placement_not_resolved",
                    receipt={"resolved_placement": resolved, "repository": str(self.repository)},
                )
            receipt = show_worktree(self._worktree_selector(resolved))
        elif kind == "existing-workspace":
            receipt = show_worktree(self._worktree_selector(resolved))
        else:
            created = self._call(
                "worktree", "create", "--name", request["name_hint"], "--parent-worktree", request["parent_workspace_key"], "--json"
            )
            created_id = _entity(created, "worktree").get("id")
            if not isinstance(created_id, str) or "::" not in created_id:
                raise DriverError(
                    "Orca did not identify the created child worktree",
                    code="placement_not_resolved",
                    receipt=created,
                )
            receipt = show_worktree(f"id:{created_id}")
        worktree = _public_git_worktree(receipt)
        actual_host = worktree["execution_host_id"]
        actual_key = worktree["workspace_key"]
        actual_kind = worktree["kind"]
        actual_path = worktree["path"]
        worktree_id = worktree["id"]
        if (
            not isinstance(worktree_id, str)
            or actual_host != host_id
            or actual_key != workspace_key
            or actual_kind != resolved["kind"]
            or (resolved["path"] is not None and actual_path != resolved["path"])
            or (recovering and pinned_terminal is not None and worktree_id != pinned_terminal["worktree_id"])
        ):
            raise DriverError(
                "Orca did not resolve the requested workspace placement exactly",
                code="placement_not_resolved",
                receipt=receipt,
            )
        return {
            "worktree_id": worktree_id,
            "resolved_placement": resolved,
            "receipt": receipt,
        }

    def _prove_pre_resource_recovery_absent(
        self,
        *,
        attempt_id: str,
        external_task: str,
    ) -> Mapping[str, Any]:
        """Require public proof that a failed pre-resource start owns nothing."""

        dispatch = self._call(
            "orchestration", "dispatch-show", "--task", external_task, "--json", allow_error=True
        )
        dispatch_result = _result(dispatch)
        dispatch_value = dispatch_result.get("dispatch") if isinstance(dispatch_result, Mapping) else None
        terminals = self._call(
            "terminal", "list", "--worktree", f"id:{self.worktree_id}",
            "--include-visual-layouts", "--json",
        )
        expected_title = _attempt_terminal_title(self.run_id, attempt_id) if self.run_id else None
        title_present = bool(
            expected_title and _terminal_handles_for_title(terminals, expected_title)
        )
        if dispatch.get("ok") is False or dispatch_value is not None or title_present:
            raise DriverError(
                "pre-resource recovery cannot prove the original attempt has no dispatch or terminal",
                code="cleanup_unproven",
                receipt={"dispatch": dispatch, "terminal_list": terminals},
            )
        return {"dispatch": dispatch, "terminal_list": terminals}

    def _mark_task_ready(self, external_task: str, retry_request: str) -> Mapping[str, Any]:
        """Advance only the transport task that Harness has already authorized."""

        receipt = self._call(
            "orchestration", "task-update", "--id", external_task, "--status", "ready",
            "--run", str(self.run_id), "--retry-request", retry_request, "--json",
        )
        task = _entity(receipt, "task")
        if task.get("id") != external_task or task.get("status") != "ready":
            raise DriverError(
                "Orca task readiness update did not prove the authorized task state",
                code="invalid_receipt",
                receipt=receipt,
            )
        return receipt

    def _restore_saved_placement(self, attempt: Mapping[str, Any]) -> Mapping[str, Any]:
        refs = attempt.get("external_refs")
        workspace_scope = attempt.get("workspace_scope")
        if not isinstance(refs, Mapping) or not isinstance(workspace_scope, Mapping):
            raise DriverError(
                "tracked terminal release requires saved placement references and workspace scope",
                code="cleanup_unproven",
            )
        saved_profile = refs.get("execution_profile")
        saved_placement = refs.get("resolved_placement")
        saved_worktree_id = refs.get("worktree_id")
        if (
            not isinstance(saved_profile, Mapping)
            or not isinstance(saved_placement, Mapping)
            or not isinstance(saved_worktree_id, str)
            or not saved_worktree_id
        ):
            raise DriverError(
                "tracked terminal release requires a complete saved execution placement",
                code="cleanup_unproven",
            )
        supplied_profile = attempt.get("execution_profile")
        if supplied_profile is not None and supplied_profile != saved_profile:
            raise DriverError(
                "tracked terminal release execution profile differs from its saved profile",
                code="cleanup_unproven",
                receipt={"saved": saved_profile, "supplied": supplied_profile},
            )
        profile = execution_profile_from_attempt(
            {
                "execution_profile": saved_profile,
                "workspace_scope": workspace_scope,
            }
        )
        resolved = profile["resolved_placement"]
        if resolved != saved_placement:
            raise DriverError(
                "tracked terminal release placement differs from its saved placement",
                code="cleanup_unproven",
                receipt={"saved": saved_placement, "resolved": resolved},
            )
        execution_host = workspace_scope.get("execution_host")
        if (
            not isinstance(execution_host, Mapping)
            or execution_host.get("id") != resolved.get("execution_host_id")
        ):
            raise DriverError(
                "tracked terminal release workspace scope differs from its saved host",
                code="cleanup_unproven",
                receipt={"workspace_scope": workspace_scope, "resolved_placement": resolved},
            )
        placement = self._resolve_worktree(
            profile,
            {"workspace_scope": workspace_scope},
            recovering=False,
            restoring=True,
        )
        if placement["worktree_id"] != saved_worktree_id:
            raise DriverError(
                "tracked terminal release resolved a different pinned worktree",
                code="cleanup_unproven",
                receipt={"saved_worktree_id": saved_worktree_id, "placement": placement},
            )
        return placement

    def _terminal_command(self, profile: Mapping[str, Any]) -> str:
        resolved = profile["resolved"]
        if resolved["agent"] != "codex":
            raise DriverError(
                "tracked-terminal fallback cannot prove this agent's model and effort flags",
                code="fallback_profile_unproven",
                receipt={"resolved": resolved},
            )
        return shlex.join(
            (
                "codex",
                "--model",
                resolved["model"],
                "-c",
                f"model_reasoning_effort={resolved['effort']}",
                "--yolo",
            )
        )

    def _worker_start_evidence(
        self,
        worker_start: Mapping[str, Any],
        profile: Mapping[str, Any],
        placement: Mapping[str, Any],
    ) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
        result = _result(worker_start)
        launch = result.get("launch")
        effects = result.get("effects")
        if not isinstance(launch, Mapping) or not isinstance(effects, list):
            raise DriverError(
                "Orca worker-start omitted public launch or worktree effects evidence",
                code="worker_profile_unproven",
                receipt={
                    "worker_start": worker_start,
                },
            )
        requested = launch.get("requested")
        effective = launch.get("effective")
        resolved = profile["resolved"]
        lease_capable = "maestro.terminal-lease.v1" in self.runtime_capabilities
        if not lease_capable and (requested != resolved or effective != resolved):
            raise DriverError(
                "Orca worker-start launch did not prove the resolved agent, model, and effort",
                code="worker_profile_unproven",
                receipt={
                    "worker_start": worker_start,
                    "expected_resolved": resolved,
                },
            )
        if lease_capable:
            expected_fields = {"agent", "model", "effort", "permissionMode", "executable"}
            if (
                not isinstance(requested, Mapping)
                or not isinstance(effective, Mapping)
                or set(requested) != expected_fields
                or set(effective) != expected_fields
                or any(requested.get(field) != resolved[field] for field in ("agent", "model", "effort"))
                or any(effective.get(field) != resolved[field] for field in ("agent", "model", "effort"))
                or requested.get("permissionMode") != "yolo"
                or effective.get("permissionMode") != "yolo"
                or requested.get("executable") not in {None, effective.get("executable")}
                or not isinstance(effective.get("executable"), str)
                or not effective["executable"]
            ):
                raise DriverError(
                    "lease-capable Orca worker-start did not prove the yolo launch profile",
                    code="worker_profile_unproven",
                    receipt={"worker_start": worker_start, "expected_resolved": resolved},
                )
        worktree_effect = next(
            (
                effect
                for effect in effects
                if isinstance(effect, Mapping)
                and effect.get("kind") == "worktree"
                and effect.get("action") in {"created", "reused"}
                and _first(effect, "worktreeId", "worktree_id", "id")
                == placement["worktree_id"]
            ),
            None,
        )
        if not isinstance(worktree_effect, Mapping):
            raise DriverError(
                "Orca worker-start effects did not prove the selected worktree",
                code="placement_not_resolved",
                receipt={
                    "worker_start": worker_start,
                    "expected_worktree_id": placement["worktree_id"],
                },
            )
        return launch, worktree_effect

    def _supervised_session_terminal(
        self,
        worker_show: Mapping[str, Any],
        *,
        dispatch_id: str,
    ) -> dict[str, Any]:
        """Return the exact provider-owned terminal identity usable by a serial session."""

        worker = _entity(worker_show, "worker")
        observed_dispatch_id = _first(worker, "dispatchId", "dispatch_id", "id")
        terminal = worker.get("terminal")
        if not isinstance(terminal, Mapping):
            terminal = _entity(worker_show, "terminal", "terminalResource", "resource")
        if observed_dispatch_id != dispatch_id or not isinstance(terminal, Mapping):
            raise DriverError(
                "Orca worker-show did not prove the supervised terminal identity",
                code="worker_terminal_unproven",
                receipt=worker_show,
            )
        identity = self._terminal_identity(
            {"result": {"terminal": terminal}},
            created_by_harness=False,
        )
        return identity

    def _validated_session_launch_profile(
        self,
        candidate: Any,
        profile: Mapping[str, Any],
        receipt: Mapping[str, Any],
    ) -> dict[str, Any]:
        resolved = profile["resolved"]
        if (
            not isinstance(candidate, Mapping)
            or set(candidate) != {"agent", "model", "effort", "permissionMode", "routeRef"}
            or any(not isinstance(candidate.get(field), str) or not candidate[field] for field in ("agent", "model", "effort", "permissionMode"))
            or any(candidate.get(field) != resolved[field] for field in ("agent", "model", "effort"))
            or candidate.get("permissionMode") != "yolo"
            or candidate.get("routeRef") is not None and not isinstance(candidate.get("routeRef"), str)
        ):
            raise DriverError(
                "Orca did not prove the serial terminal launch profile",
                code="worker_terminal_unproven",
                receipt=receipt,
            )
        return dict(candidate)

    def _validate_lease_participant(
        self,
        participant: Any,
        *,
        attempt_id: str,
        task_id: str,
        terminal: Mapping[str, Any],
        placement: Mapping[str, Any],
        dispatch_id: str,
        expected_lease_id: str,
    ) -> bool:
        if not isinstance(participant, Mapping):
            return False
        expected = {
            "runId": self.run_id,
            "taskId": task_id,
            "attemptId": attempt_id,
            "dispatchId": dispatch_id,
            "terminalHandle": terminal["handle"],
            "ptyIncarnation": terminal["process_incarnation"],
            "paneKey": terminal["pane_key"],
            "executionHostId": placement["resolved_placement"]["execution_host_id"],
            "workspaceKey": placement["resolved_placement"]["workspace_key"],
            "coordinatorGeneration": terminal["coordinator_generation"],
            "processRootId": terminal["pty_id"],
            "retentionPolicy": "auto_release",
            "ownerPrincipal": f"dispatch:{dispatch_id}",
            "leaseId": expected_lease_id,
        }
        return all(participant.get(key) == value for key, value in expected.items())

    def _lease_input_envelope(
        self,
        *,
        handoff: Mapping[str, Any],
        attempt: Mapping[str, Any],
        task_id: str,
        attempt_id: str,
        successor_lease_id: str,
    ) -> dict[str, Any]:
        handoff_id = handoff.get("handoff_id")
        generation = attempt["workspace_scope"].get("coordinator_generation")
        if (
            not successor_lease_id
            or not isinstance(handoff_id, str)
            or not handoff_id
            or not isinstance(generation, int)
            or isinstance(generation, bool)
            or generation < 0
        ):
            raise DriverError(
                "Orca lease transfer omitted the authenticated successor input envelope",
                code="session_reuse_unavailable",
                receipt={"handoff": dict(handoff)},
            )
        canonical_handoff = json.dumps(handoff, separators=(",", ":"), sort_keys=True)
        seed = f"{handoff_id}:{task_id}:{attempt_id}".encode()
        digest = hashlib.sha256(seed).hexdigest()
        return {
            "commandId": f"handoff-{digest[:24]}",
            "idempotencyKey": f"handoff-{digest}",
            "leaseId": successor_lease_id,
            "contentDigest": f"sha256:{hashlib.sha256(canonical_handoff.encode()).hexdigest()}",
            "enqueueSequence": 2,
            "authority": "coordinator",
            "runId": self.run_id,
            "coordinatorGeneration": generation,
            "expectedLifecycleState": "active",
            "observedInputSurface": "working",
            "expiresAt": (datetime.now(UTC) + timedelta(seconds=60)).isoformat().replace("+00:00", "Z"),
            "expectedGraphRevision": None,
        }

    def _assert_dispatch_binding(
        self,
        dispatch: Mapping[str, Any],
        *,
        dispatch_id: Any,
        task_id: str,
        terminal: Mapping[str, Any],
    ) -> None:
        provider_dispatch = _entity(dispatch, "dispatch")
        expected_incarnation = (
            f"{terminal['worktree_id']}@@{terminal['process_incarnation']}"
        )
        if (
            _first(provider_dispatch, "id", "dispatchId", "dispatch_id") != dispatch_id
            or _first(provider_dispatch, "task_id", "taskId") != task_id
            or _first(
                provider_dispatch,
                "assignee_handle",
                "assigneeHandle",
                "terminalHandle",
            )
            != terminal["handle"]
            or _first(
                provider_dispatch,
                "assignee_pane_key",
                "assigneePaneKey",
                "paneKey",
            )
            != terminal["pane_key"]
            or _first(
                provider_dispatch,
                "process_incarnation",
                "processIncarnation",
            )
            != expected_incarnation
        ):
            raise DriverError(
                "Orca dispatch did not prove the tracked terminal binding",
                code="fallback_binding_unproven",
                receipt={
                    "dispatch": dispatch,
                    "dispatch_id": dispatch_id,
                    "task_id": task_id,
                    "terminal": dict(terminal),
                },
            )

    def _recover_tracked_attempt(
        self,
        *,
        attempt: Mapping[str, Any],
        attempt_id: str,
        local_task: str,
        external_task: str,
        retry_request: str,
        placement: Mapping[str, Any],
        profile: Mapping[str, Any],
        pinned_terminal: Mapping[str, Any],
    ) -> DriverReceipt:
        ownership = pinned_terminal.get("ownership")
        expected_ownership = {
            "attempt_id": attempt_id,
            "local_task_id": local_task,
            "external_task_id": external_task,
            "dispatch_id": pinned_terminal.get("ownership", {}).get("dispatch_id")
            if isinstance(ownership, Mapping)
            else None,
            "run_id": self.run_id,
        }
        if (
            not isinstance(ownership, Mapping)
            or any(
                not isinstance(expected_ownership[key], str)
                or not expected_ownership[key]
                or ownership.get(key) != expected_ownership[key]
                for key in expected_ownership
            )
        ):
            raise DriverError(
                "tracked-terminal recovery requires its exact durable ownership binding",
                code="cleanup_unproven",
                receipt={"terminal": dict(pinned_terminal), "expected": expected_ownership},
            )
        shown = self._call(
            "terminal", "show", "--terminal", str(pinned_terminal.get("handle") or ""), "--json"
        )
        identity = self._terminal_identity(
            shown,
            created_by_harness=False,
            recovered=True,
            pinned_creation_owned=True,
        )
        identity_keys = (
            "runtime_id",
            "handle",
            "pty_id",
            "incarnation_id",
            "worktree_id",
            "tab_id",
            "leaf_id",
        )
        if any(identity[key] != pinned_terminal.get(key) for key in identity_keys):
            raise DriverError(
                "recovered terminal does not match the owned terminal identity",
                code="cleanup_unproven",
                receipt={"actual": identity, "expected": dict(pinned_terminal)},
            )
        waited: Mapping[str, Any] | None = None
        dispatched: Mapping[str, Any] | None = None
        dispatch_show: Mapping[str, Any] | None = None
        try:
            waited = self._wait_for_terminal(str(identity["handle"]), "tui-idle")
            dispatched = self._call(
                "orchestration", "dispatch", "--task", external_task, "--to", str(identity["handle"]),
                "--run", str(self.run_id), "--inject", "--retry-request", retry_request, "--json",
            )
            dispatch_result = _result(dispatched)
            dispatch_id = _first(dispatch_result, "id", "dispatchId", "dispatch_id")
            if (
                not isinstance(dispatch_id, str)
                or not dispatch_id
                or dispatch_id != ownership["dispatch_id"]
            ):
                raise DriverError(
                    "tracked-terminal recovery dispatch did not prove its pinned dispatch binding",
                    code="invalid_receipt",
                    receipt={"dispatch": dispatched, "ownership": dict(ownership)},
                )
            dispatch_show = self._call("orchestration", "dispatch-show", "--task", external_task, "--json")
            self._assert_dispatch_binding(
                dispatch_show,
                dispatch_id=dispatch_id,
                task_id=external_task,
                terminal=identity,
            )
        except DriverError as error:
            try:
                rollback = self._close_created_terminal({**identity, "ownership": ownership})
            except DriverError as cleanup_error:
                raise DriverError(
                    "Orca tracked-terminal recovery failed and could not clean safely",
                    code="cleanup_failed",
                    receipt={"cause": error.receipt, "rollback": cleanup_error.receipt},
                ) from error
            raise DriverError(
                str(error), code=error.code, receipt={"cause": error.receipt, "rollback": rollback}
            ) from error
        owned_terminal = {**identity, "ownership": dict(ownership)}
        self.created_terminals[attempt_id] = owned_terminal
        refs = attempt.get("external_refs")
        terminal_command = refs.get("terminal_command") if isinstance(refs, Mapping) else None
        return DriverReceipt(
            "start_attempt",
            "started",
            local_ids={"task_id": local_task, "attempt_id": attempt_id},
            external_refs={
                "tier": "tracked-terminal",
                "run_id": self.run_id,
                "task_id": external_task,
                "dispatch_id": ownership["dispatch_id"],
                "worktree_id": placement["worktree_id"],
                "terminal": owned_terminal,
                "terminal_command": terminal_command,
                "execution_profile": profile,
                "resolved_placement": placement["resolved_placement"],
                "workspace_scope": attempt["workspace_scope"],
                "placement_environment": profile["resolved_placement"]["execution_host_id"]
                if attempt["workspace_scope"]["execution_host"]["boundary"] == "remote"
                else None,
                "placement_receipt": placement["receipt"],
            },
            raw={
                "placement": placement["receipt"],
                "recovered_terminal": True,
                "recovery_terminal": shown,
                "terminal_wait": waited,
                "dispatch": dispatched,
                "dispatch_show": dispatch_show,
            },
        )

    def _reengage_unleased_tracked_terminal(
        self,
        *,
        attempt: Mapping[str, Any],
        attempt_id: str,
        local_task: str,
        external_task: str,
        retry_request: str,
        placement: Mapping[str, Any],
        profile: Mapping[str, Any],
        task_ready: Mapping[str, Any],
        identity: Mapping[str, Any],
        prior_binding: Mapping[str, Any],
        handoff: Mapping[str, Any],
    ) -> DriverReceipt:
        """Reuse only an explicitly unleased fallback terminal through Dispatch."""

        waited: Mapping[str, Any] | None = None
        dispatched: Mapping[str, Any] | None = None
        dispatch_show: Mapping[str, Any] | None = None
        owned_terminal = {
            **identity,
            "managed_lease": False,
            "ownership": {
                "attempt_id": attempt_id,
                "local_task_id": local_task,
                "external_task_id": external_task,
                "dispatch_id": "",
                "run_id": self.run_id,
            },
        }
        try:
            waited = self._wait_for_terminal(str(identity["handle"]), "tui-idle")
            dispatched = self._call(
                "orchestration", "dispatch", "--task", external_task, "--to", str(identity["handle"]),
                "--run", str(self.run_id), "--inject", "--retry-request", retry_request, "--json",
            )
            dispatch_id = _first(_result(dispatched), "id", "dispatchId", "dispatch_id")
            if not isinstance(dispatch_id, str) or not dispatch_id:
                raise DriverError("unleased terminal dispatch omitted its ID", code="invalid_receipt", receipt=dispatched)
            owned_terminal["ownership"] = {**owned_terminal["ownership"], "dispatch_id": dispatch_id}
            dispatch_show = self._call("orchestration", "dispatch-show", "--task", external_task, "--json")
            self._assert_dispatch_binding(
                dispatch_show, dispatch_id=dispatch_id, task_id=external_task, terminal=identity
            )
            delivered = self._send_terminal_handoff(
                str(identity["handle"]),
                json.dumps(handoff, separators=(",", ":"), sort_keys=True),
            )
        except DriverError as error:
            try:
                rollback = self._close_created_terminal(owned_terminal)
            except DriverError as cleanup_error:
                raise DriverError(
                    "unleased terminal reuse failed with unresolved cleanup",
                    code="cleanup_failed",
                    receipt={
                        "cause": error.receipt,
                        "dispatch": dispatched,
                        "dispatch_show": dispatch_show,
                        "rollback": cleanup_error.receipt,
                    },
                ) from error
            outcome_code = (
                "session_delivery_rolled_back"
                if error.code in {"delivery_rejected", "session_delivery_unproven"}
                else error.code
            )
            raise DriverError(
                "unleased terminal reuse failed after verified rollback",
                code=outcome_code,
                receipt={
                    "cause": error.receipt,
                    "rollback": rollback,
                    "residual_resources": "zero",
                },
            ) from error
        self.created_terminals[attempt_id] = owned_terminal
        return DriverReceipt(
            "start_attempt",
            "started",
            local_ids={"task_id": local_task, "attempt_id": attempt_id},
            external_refs={
                "tier": "tracked-terminal",
                "run_id": self.run_id,
                "task_id": external_task,
                "dispatch_id": owned_terminal["ownership"]["dispatch_id"],
                "worktree_id": placement["worktree_id"],
                "terminal": owned_terminal,
                "execution_profile": profile,
                "resolved_placement": placement["resolved_placement"],
                "workspace_scope": attempt["workspace_scope"],
                "session_reused": True,
                "session_parent_attempt_id": prior_binding["attempt_id"],
            },
            raw={
                "task_ready": task_ready,
                "terminal_wait": waited,
                "dispatch": dispatched,
                "dispatch_show": dispatch_show,
                "session_handoff_delivery": delivered,
            },
        )

    def _reengage_session_terminal(
        self,
        *,
        attempt: Mapping[str, Any],
        attempt_id: str,
        local_task: str,
        external_task: str,
        retry_request: str,
        placement: Mapping[str, Any],
        profile: Mapping[str, Any],
        session_terminal: Mapping[str, Any],
        task_ready: Mapping[str, Any],
    ) -> DriverReceipt:
        """Dispatch a later serial task to one still-owned, exact terminal.

        The prior task's terminal is reusable only when the coordinator passes
        its persisted identity, profile and workspace scope.  The provider is
        never asked to locate a vaguely similar terminal.
        """

        if attempt["workspace_scope"]["execution_host"]["boundary"] != "local":
            raise DriverError("remote session reuse is not independently verifiable", code="session_reuse_unavailable")
        required = {
            "terminal", "execution_profile", "workspace_scope", "lease_status", "cleanup_tier",
        }
        cleanup_tier = session_terminal.get("cleanup_tier")
        if (
            set(session_terminal) != required
            or session_terminal.get("lease_status") != "active"
            or cleanup_tier not in {"supervised", "tracked-terminal"}
        ):
            raise DriverError("session reuse requires one active exact terminal lease", code="session_reuse_unavailable")
        if (
            session_terminal.get("execution_profile") != profile
            or session_terminal.get("workspace_scope") != attempt["workspace_scope"]
        ):
            raise DriverError("session terminal profile or workspace drifted", code="session_reuse_unavailable")
        session_handoff = attempt.get("session_handoff")
        if not isinstance(session_handoff, Mapping):
            raise DriverError("session reuse requires an immutable incremental capsule", code="session_reuse_unavailable")
        try:
            validated_handoff = build_reused_session_handoff(
                task_id=str(session_handoff.get("task_id", "")),
                acceptance=str(session_handoff.get("acceptance", "")),
                dependency_summaries=session_handoff.get("dependency_summaries", []),
                diff_since_previous_check=session_handoff.get("diff_since_previous_check", []),
                unresolved_material_finding_refs=session_handoff.get("unresolved_material_finding_refs", []),
                allowed_paths=session_handoff.get("allowed_paths", []),
                check=str(session_handoff.get("check", "")),
                session_memory=session_handoff.get("session_memory", {}),
            )
        except ValueError as error:
            raise DriverError("session reuse capsule is invalid", code="session_reuse_unavailable") from error
        if validated_handoff != session_handoff or validated_handoff["task_id"] != local_task:
            raise DriverError("session reuse capsule drifted", code="session_reuse_unavailable")
        prior_terminal = session_terminal.get("terminal")
        if not isinstance(prior_terminal, Mapping):
            raise DriverError("session reuse terminal identity is missing", code="session_reuse_unavailable")
        prior_binding_key = "ownership" if cleanup_tier == "tracked-terminal" else "session_binding"
        prior_binding = prior_terminal.get(prior_binding_key)
        if not isinstance(prior_binding, Mapping) or not all(
            isinstance(prior_binding.get(field), str) and prior_binding[field]
            for field in ("attempt_id", "local_task_id", "external_task_id", "dispatch_id", "run_id")
        ):
            raise DriverError("session reuse terminal ownership is incomplete", code="session_reuse_unavailable")
        shown = self._call("terminal", "show", "--terminal", str(prior_terminal.get("handle") or ""), "--json")
        identity = self._terminal_identity(
            shown, created_by_harness=False, recovered=True, pinned_creation_owned=True
        )
        identity_keys = (
            "runtime_id", "handle", "pty_id", "incarnation_id", "worktree_id", "tab_id", "leaf_id",
        )
        if (
            any(identity.get(key) != prior_terminal.get(key) for key in identity_keys)
            or identity["worktree_id"] != placement["worktree_id"]
        ):
            raise DriverError(
                "session terminal identity or workspace drifted", code="session_reuse_unavailable",
                receipt={"actual": identity, "expected": dict(prior_terminal)},
            )
        if cleanup_tier == "tracked-terminal":
            if prior_terminal.get("managed_lease") is not False:
                raise DriverError(
                    "tracked terminal reuse requires an explicit unleased terminal receipt",
                    code="session_reuse_unavailable",
                    receipt={"terminal": dict(prior_terminal)},
                )
            return self._reengage_unleased_tracked_terminal(
                attempt=attempt,
                attempt_id=attempt_id,
                local_task=local_task,
                external_task=external_task,
                retry_request=retry_request,
                placement=placement,
                profile=profile,
                task_ready=task_ready,
                identity=identity,
                prior_binding=prior_binding,
                handoff=validated_handoff,
            )
        if "maestro.terminal-lease.v1" not in self.runtime_capabilities:
            raise DriverError(
                "Orca does not advertise the managed terminal lease protocol",
                code="session_reuse_unavailable",
                receipt={"capabilities": sorted(self.runtime_capabilities)},
            )
        identity = {
            **identity,
            "coordinator_generation": attempt["workspace_scope"]["coordinator_generation"],
        }
        launched = self._call(
            "orchestration", "worker-start", "--task", external_task,
            "--terminal", str(identity["handle"]), "--worktree", f"id:{placement['worktree_id']}",
            "--run", str(self.run_id), "--retry-request", retry_request, "--json",
        )
        self._managed_reuse_inflight = {
            "task_id": external_task,
            "attempt_id": attempt_id,
            "worker_start": launched,
            "dispatch_id": None,
        }
        launch_result = _result(launched)
        dispatch_id = _first(launch_result, "id", "dispatchId", "dispatch_id")
        if not isinstance(dispatch_id, str) or not dispatch_id:
            raise DriverError("session worker-start omitted its authoritative dispatch ID", code="invalid_receipt", receipt=launched)
        self._managed_reuse_inflight["dispatch_id"] = dispatch_id
        lease_transfer = _first(launch_result, "leaseTransfer", "lease_transfer")
        if not isinstance(lease_transfer, Mapping):
            raise DriverError("session worker-start omitted its lease-transfer receipt", code="invalid_receipt", receipt=launched)
        if (
            lease_transfer.get("version") != 1
            or lease_transfer.get("kind") != "settled_resource_reuse"
            or lease_transfer.get("runId") != self.run_id
            or lease_transfer.get("taskId") != external_task
            or lease_transfer.get("attemptId") != attempt_id
            or lease_transfer.get("terminalHandle") != identity["handle"]
            or lease_transfer.get("ptyIncarnation") != identity["process_incarnation"]
            or lease_transfer.get("executionHostId") != placement["resolved_placement"]["execution_host_id"]
            or lease_transfer.get("workspaceKey") != placement["resolved_placement"]["workspace_key"]
            or lease_transfer.get("coordinatorGeneration") != identity["coordinator_generation"]
            or lease_transfer.get("processRootId") != identity["pty_id"]
            or lease_transfer.get("retentionPolicy") != "auto_release"
            or not (lease_transfer.get("hostScope") is None or isinstance(lease_transfer.get("hostScope"), str))
            or lease_transfer.get("predecessorOwnerPrincipal") != f"dispatch:{prior_binding['dispatch_id']}"
            or lease_transfer.get("successorOwnerPrincipal") != f"dispatch:{dispatch_id}"
            or lease_transfer.get("fromDispatchId") != prior_binding["dispatch_id"]
            or lease_transfer.get("toDispatchId") != dispatch_id
            or not isinstance(lease_transfer.get("predecessorLeaseId"), str)
            or not lease_transfer["predecessorLeaseId"]
            or not isinstance(lease_transfer.get("successorLeaseId"), str)
            or not lease_transfer["successorLeaseId"]
            or not self._validate_lease_participant(
                lease_transfer.get("predecessor"),
                attempt_id=str(prior_binding["attempt_id"]),
                task_id=str(prior_binding["external_task_id"]),
                terminal=identity,
                placement=placement,
                dispatch_id=str(prior_binding["dispatch_id"]),
                expected_lease_id=lease_transfer["predecessorLeaseId"],
            )
            or not self._validate_lease_participant(
                lease_transfer.get("successor"),
                attempt_id=attempt_id,
                task_id=external_task,
                terminal=identity,
                placement=placement,
                dispatch_id=dispatch_id,
                expected_lease_id=lease_transfer["successorLeaseId"],
            )
        ):
            raise DriverError("session worker-start did not accept the terminal lease transfer", code="session_reuse_unavailable", receipt=launched)
        host_scope = lease_transfer["hostScope"]
        if (
            "hostScope" not in lease_transfer["predecessor"]
            or "hostScope" not in lease_transfer["successor"]
            or lease_transfer["predecessor"]["hostScope"] != host_scope
            or lease_transfer["successor"]["hostScope"] != host_scope
        ):
            raise DriverError(
                "Orca lease transfer host scope diverged between participants",
                code="session_reuse_unavailable",
                receipt=launched,
            )
        predecessor_launch_profile = self._validated_session_launch_profile(
            lease_transfer["predecessor"].get("launchProfile"), profile, lease_transfer
        )
        top_level_launch_profile = self._validated_session_launch_profile(
            lease_transfer.get("launchProfile"), profile, lease_transfer
        )
        successor_launch_profile = self._validated_session_launch_profile(
            lease_transfer["successor"].get("launchProfile"), profile, lease_transfer
        )
        if successor_launch_profile != predecessor_launch_profile or top_level_launch_profile != successor_launch_profile:
            raise DriverError(
                "Orca successor launch profile diverged from its settled predecessor",
                code="session_reuse_unavailable",
                receipt=launched,
            )
        lease_input = self._lease_input_envelope(
            handoff=validated_handoff,
            attempt=attempt,
            task_id=local_task,
            attempt_id=attempt_id,
            successor_lease_id=lease_transfer["successorLeaseId"],
        )
        dispatch_show = self._call("orchestration", "dispatch-show", "--task", external_task, "--json")
        self._assert_dispatch_binding(
            dispatch_show, dispatch_id=dispatch_id, task_id=external_task, terminal=identity
        )
        terminal_binding = {
            "attempt_id": attempt_id,
            "local_task_id": local_task,
            "external_task_id": external_task,
            "dispatch_id": dispatch_id,
            "run_id": self.run_id,
        }
        owned_terminal = {
            **identity,
            **({"ownership": terminal_binding} if cleanup_tier == "tracked-terminal" else {"session_binding": terminal_binding}),
        }
        delivered = self._send_terminal_handoff(
            str(identity["handle"]),
            json.dumps(validated_handoff, separators=(",", ":"), sort_keys=True),
            "--lease-input",
            json.dumps(lease_input, separators=(",", ":"), sort_keys=True),
        )
        self._managed_reuse_inflight = None
        if cleanup_tier == "tracked-terminal":
            self.created_terminals[attempt_id] = owned_terminal
        session_refs = {
            "tier": cleanup_tier,
            "run_id": self.run_id,
            "task_id": external_task,
            "dispatch_id": dispatch_id,
            "worktree_id": placement["worktree_id"],
            "execution_profile": profile,
            "resolved_placement": placement["resolved_placement"],
            "workspace_scope": attempt["workspace_scope"],
            "session_reused": True,
            "session_parent_attempt_id": prior_binding["attempt_id"],
        }
        if cleanup_tier == "supervised":
            session_refs.update(
                runtime_id=self.runtime_id,
                reusable_session_terminal=owned_terminal,
            )
        else:
            session_refs["terminal"] = owned_terminal
        return DriverReceipt(
            "start_attempt",
            "started",
            local_ids={"task_id": local_task, "attempt_id": attempt_id},
            external_refs=session_refs,
            raw={
                "task_ready": task_ready,
                "session_terminal": shown,
                "worker_start": launched,
                "lease_transfer": lease_transfer,
                "lease_input": lease_input,
                "dispatch_show": dispatch_show,
                "session_handoff_delivery": delivered,
            },
        )

    def _require_launch_preferences(self) -> None:
        if "orchestration.worker-launch-preferences.v1" not in self.runtime_capabilities:
            raise DriverError(
                "Orca does not support worker launch preferences",
                code="profile_not_supported",
                receipt={"capabilities": sorted(self.runtime_capabilities)},
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

    def _terminal_identity(
        self,
        terminal: Mapping[str, Any],
        *,
        created_by_harness: bool,
        recovered: bool = False,
        pinned_creation_owned: bool = False,
    ) -> dict[str, Any]:
        result = _entity(terminal, "terminal", "createdTerminal", "agentTerminal")
        identity = {
            "runtime_id": self.runtime_id,
            "handle": _first(result, "handle", "terminalHandle"),
            "pty_id": _first(result, "ptyId", "pty_id"),
            "incarnation_id": _first(result, "incarnationId", "incarnation_id"),
            "worktree_id": _first(result, "worktreeId", "worktree_id") or self.worktree_id,
            "tab_id": _first(result, "tabId", "tab_id"),
            "leaf_id": _first(result, "leafId", "leaf_id"),
            "created_by_harness": created_by_harness,
            "recovered": recovered,
            "pinned_creation_owned": pinned_creation_owned,
        }
        if not all(
            identity[key]
            for key in (
                "runtime_id",
                "handle",
                "pty_id",
                "incarnation_id",
                "worktree_id",
                "tab_id",
                "leaf_id",
            )
        ):
            raise DriverError("created terminal lacks incarnation identity", code="invalid_receipt", receipt=terminal)
        identity["pane_key"] = f"{identity['tab_id']}:{identity['leaf_id']}"
        identity["process_incarnation"] = f"{identity['pty_id']}:{identity['incarnation_id']}"
        return identity

    def _close_created_terminal(self, expected: Mapping[str, Any]) -> dict[str, Any]:
        if (
            expected.get("created_by_harness") is not True
            and expected.get("pinned_creation_owned") is not True
        ):
            raise DriverError(
                "terminal cleanup requires a driver-owned creation identity",
                code="cleanup_unproven",
                receipt={"terminal": dict(expected)},
            )
        shown = self._call("terminal", "show", "--terminal", str(expected["handle"]), "--json")
        actual = self._terminal_identity(shown, created_by_harness=False)
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

    def _rollback_managed_reuse(self, state: Mapping[str, Any]) -> Mapping[str, Any]:
        """Release a successful managed worker-start after any later validation error."""

        task_id = state.get("task_id")
        dispatch_id = state.get("dispatch_id")
        attempt_id = state.get("attempt_id")
        reconciliation: Mapping[str, Any] | None = None
        if not isinstance(dispatch_id, str) or not dispatch_id:
            if not isinstance(task_id, str) or not task_id:
                raise DriverError("managed reuse rollback lacks task identity", code="cleanup_failed", receipt=dict(state))
            reconciliation = self._call(
                "orchestration", "dispatch-show", "--task", task_id, "--json", allow_error=True
            )
            if reconciliation.get("ok") is not False:
                dispatch_id = _first(_entity(reconciliation, "dispatch"), "id", "dispatchId", "dispatch_id")
        if not isinstance(dispatch_id, str) or not dispatch_id:
            raise DriverError(
                "managed reuse rollback cannot identify the created dispatch",
                code="cleanup_failed",
                receipt={"worker_start": state.get("worker_start"), "reconciliation": reconciliation},
            )
        if not isinstance(attempt_id, str) or not attempt_id:
            raise DriverError(
                "managed reuse rollback lacks attempt identity",
                code="cleanup_failed",
                receipt={"worker_start": state.get("worker_start"), "reconciliation": reconciliation},
            )
        retry_request = f"{self.run_id}-{attempt_id}-managed-rollback"
        released = self._call(
            "orchestration", "worker-release", "--dispatch", dispatch_id,
            "--retry-request", retry_request, "--json", allow_error=True,
        )
        release_state = _result(released).get("state")
        if released.get("ok") is not False and release_state in {
            "released",
            "already_absent",
            "already_released",
        }:
            return {
                "reconciliation": reconciliation,
                "worker_release": released,
                "residual_resources": "zero",
            }
        diagnostic = self._call(
            "orchestration", "worker-show", "--dispatch", dispatch_id, "--json", allow_error=True
        )
        raise DriverError(
            "managed reuse rollback did not prove terminal cleanup",
            code="cleanup_failed",
            receipt={
                "worker_start": state.get("worker_start"),
                "reconciliation": reconciliation,
                "worker_release": released,
                "worker_show": diagnostic,
                "residual_resources": "unknown",
            },
        )

    def start_attempt(self, attempt: Mapping[str, Any]) -> DriverReceipt:
        local_task = str(attempt["task_id"])
        attempt_id = str(attempt["attempt_id"])
        recovering = attempt.get("recover") is True
        profile = execution_profile_from_attempt(attempt)
        pinned_terminal = self._pinned_terminal(attempt)
        if not (recovering and pinned_terminal):
            self._require_launch_preferences()
        pre_resource_recovery = (
            self._prove_pre_resource_recovery_absent(
                attempt_id=attempt_id,
                external_task=self.task_ids.get(local_task, str(attempt.get("external_task_id", ""))),
            )
            if recovering and not pinned_terminal
            else None
        )
        placement = self._resolve_worktree(profile, attempt, recovering=recovering)
        self.worktree_id = str(placement["worktree_id"])
        external_task = self.task_ids.get(local_task, str(attempt.get("external_task_id", "")))
        if not external_task or not self.run_id or not self.worktree_id:
            raise DriverError("Orca run and task identities are required", code="not_started")
        retry_request_base = f"{self.run_id}-{attempt_id}"
        ready_retry_request = f"{retry_request_base}-ready"
        worker_start_retry_request = f"{retry_request_base}-start"
        terminal_dispatch_retry_request = f"{retry_request_base}-dispatch"
        if recovering and pinned_terminal:
            return self._recover_tracked_attempt(
                attempt=attempt,
                attempt_id=attempt_id,
                local_task=local_task,
                external_task=external_task,
                retry_request=terminal_dispatch_retry_request,
                placement=placement,
                profile=profile,
                pinned_terminal=pinned_terminal,
            )
        task_ready = self._mark_task_ready(external_task, ready_retry_request)
        session_terminal = attempt.get("session_terminal")
        if isinstance(session_terminal, Mapping):
            try:
                receipt = self._reengage_session_terminal(
                    attempt=attempt,
                    attempt_id=attempt_id,
                    local_task=local_task,
                    external_task=external_task,
                    retry_request=terminal_dispatch_retry_request,
                    placement=placement,
                    profile=profile,
                    session_terminal=session_terminal,
                    task_ready=task_ready,
                )
            except DriverError as error:
                state = self._managed_reuse_inflight
                self._managed_reuse_inflight = None
                if state is None:
                    raise
                try:
                    rollback = self._rollback_managed_reuse(state)
                except DriverError as cleanup_error:
                    raise DriverError(
                        "managed session reuse failed with unresolved cleanup",
                        code="cleanup_failed",
                        receipt={"cause": error.receipt, "rollback": cleanup_error.receipt},
                    ) from error
                outcome_code = (
                    "session_delivery_rolled_back"
                    if error.code in {"delivery_rejected", "session_delivery_unproven"}
                    else error.code
                )
                raise DriverError(
                    str(error), code=outcome_code, receipt={"cause": error.receipt, "rollback": rollback}
                ) from error
            self._managed_reuse_inflight = None
            return receipt
        resolved = profile["resolved"]
        workspace_scope = attempt["workspace_scope"]
        remote_execution = workspace_scope["execution_host"]["boundary"] == "remote"
        worker_location = (
            ["--on", profile["resolved_placement"]["execution_host_id"]]
            if remote_execution
            else []
        )
        supervised = self._call(
            "orchestration", "worker-start", "--task", external_task, *worker_location, "--worktree", f"id:{self.worktree_id}", "--agent", resolved["agent"], "--model", resolved["model"], "--effort", resolved["effort"], "--run", self.run_id, "--retry-request", worker_start_retry_request, "--json", allow_error=True
        )
        if supervised.get("ok") is not False:
            result = _result(supervised)
            dispatch_id = _first(result, "dispatchId", "dispatch_id", "id")
            self._managed_reuse_inflight = {
                "task_id": external_task,
                "attempt_id": attempt_id,
                "worker_start": supervised,
                "dispatch_id": dispatch_id,
            }
            if not isinstance(dispatch_id, str) or not dispatch_id:
                try:
                    rollback = self._rollback_managed_reuse(self._managed_reuse_inflight)
                except DriverError as cleanup_error:
                    raise DriverError(
                        "Orca worker-start omitted its dispatch ID with unresolved cleanup",
                        code="cleanup_failed",
                        receipt={"worker_start": supervised, "rollback": cleanup_error.receipt},
                    ) from cleanup_error
                finally:
                    self._managed_reuse_inflight = None
                raise DriverError(
                    "Orca worker-start success omitted its dispatch ID",
                    code="invalid_receipt",
                    receipt={"worker_start": supervised, "rollback": rollback},
                )
            try:
                launch, worktree_effect = self._worker_start_evidence(
                    supervised, profile, placement
                )
            except DriverError as error:
                try:
                    rollback = self._rollback_managed_reuse(self._managed_reuse_inflight)
                except DriverError as cleanup_error:
                    raise DriverError(
                        "Orca worker-start validation failed with unresolved cleanup",
                        code="cleanup_failed",
                        receipt={"cause": error.receipt, "rollback": cleanup_error.receipt},
                    ) from error
                finally:
                    self._managed_reuse_inflight = None
                raise DriverError(
                    str(error), code=error.code, receipt={"cause": error.receipt, "rollback": rollback}
                ) from error
            worker_show = self._call(
                "orchestration", "worker-show", "--dispatch", dispatch_id, "--json", allow_error=True
            )
            reusable_session: dict[str, Any] = {}
            if worker_show.get("ok") is not False:
                try:
                    reusable_session_terminal = self._supervised_session_terminal(
                        worker_show, dispatch_id=dispatch_id
                    )
                    reusable_session = {
                        "reusable_session_terminal": {
                            **reusable_session_terminal,
                            "session_binding": {
                                "attempt_id": attempt_id,
                                "local_task_id": local_task,
                                "external_task_id": external_task,
                                "dispatch_id": dispatch_id,
                                "run_id": self.run_id,
                            },
                        },
                    }
                except DriverError:
                    # Missing reuse proof is not a reason to reject a healthy new worker.
                    reusable_session = {}
            self._managed_reuse_inflight = None
            return DriverReceipt(
                "start_attempt", "started", local_ids={"task_id": local_task, "attempt_id": attempt_id}, external_refs={"tier": "supervised", "runtime_id": self.runtime_id, "run_id": self.run_id, "task_id": external_task, "dispatch_id": dispatch_id, "worktree_id": placement["worktree_id"], "execution_profile": profile, "resolved_placement": placement["resolved_placement"], "workspace_scope": attempt["workspace_scope"], "placement_environment": profile["resolved_placement"]["execution_host_id"] if remote_execution else None, "placement_receipt": placement["receipt"], "launch": launch, "placement_effect": worktree_effect, **reusable_session}, raw={"placement": placement["receipt"], "task_ready": task_ready, "worker_start": supervised, "worker_show": worker_show, **({"pre_resource_recovery": pre_resource_recovery} if pre_resource_recovery is not None else {})}
            )
        code, message = _error(supervised)
        if code not in FALLBACK_CODES:
            raise DriverError(message, code=code, receipt=supervised)
        if remote_execution:
            raise DriverError(
                "remote worker-start cannot fall back to a local tracked terminal",
                code="remote_fallback_unproven",
                receipt={"worker_start": supervised, "placement": placement["receipt"]},
            )
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
        terminal_command = self._terminal_command(profile)
        expected_terminal = self._pinned_terminal(attempt) if recovering else None
        pinned_creation_owned = bool(
            expected_terminal
            and (
                expected_terminal.get("created_by_harness") is True
                or expected_terminal.get("pinned_creation_owned") is True
            )
        )
        terminal = (
            self._call("terminal", "show", "--terminal", recovered_handle, "--json")
            if recovered_handle
            else self._call(
                "terminal", "create", "--worktree", f"id:{self.worktree_id}", "--title", terminal_title, "--command", terminal_command, "--json"
            )
        )
        terminal_show: Mapping[str, Any] | None = None
        try:
            identity = self._terminal_identity(
                terminal,
                created_by_harness=not bool(recovered_handle),
                recovered=bool(recovered_handle),
                pinned_creation_owned=pinned_creation_owned,
            )
        except DriverError:
            handle = _terminal_handle(terminal)
            if not handle:
                raise
            terminal_show = self._call("terminal", "show", "--terminal", handle, "--json")
            identity = self._terminal_identity(
                terminal_show,
                created_by_harness=not bool(recovered_handle),
                recovered=bool(recovered_handle),
                pinned_creation_owned=pinned_creation_owned,
            )
        if recovering:
            if not expected_terminal or any(
                identity.get(key) != expected_terminal.get(key)
                for key in ("runtime_id", "handle", "pty_id", "incarnation_id", "worktree_id", "tab_id", "leaf_id")
            ):
                raise DriverError(
                    "recovered terminal does not match the owned terminal identity",
                    code="cleanup_unproven",
                    receipt={"actual": identity, "expected": expected_terminal},
                )
        if identity["handle"] in self._terminal_snapshot and not (recovering and recovered_handle):
            raise DriverError("Orca reused a pre-existing terminal for fallback", code="unsafe_fallback", receipt=terminal)
        waited: Mapping[str, Any] | None = None
        dispatched: Mapping[str, Any] | None = None
        dispatch_show: Mapping[str, Any] | None = None
        try:
            waited = self._wait_for_terminal(str(identity["handle"]), "tui-idle")
            dispatched = self._call("orchestration", "dispatch", "--task", external_task, "--to", str(identity["handle"]), "--run", self.run_id, "--inject", "--retry-request", terminal_dispatch_retry_request, "--json")
            dispatch_id = _first(_result(dispatched), "id", "dispatchId", "dispatch_id")
            if not isinstance(dispatch_id, str) or not dispatch_id:
                raise DriverError(
                    "Orca tracked-terminal dispatch omitted its dispatch ID",
                    code="invalid_receipt",
                    receipt=dispatched,
                )
            dispatch_show = self._call("orchestration", "dispatch-show", "--task", external_task, "--json")
            self._assert_dispatch_binding(
                dispatch_show,
                dispatch_id=dispatch_id,
                task_id=external_task,
                terminal=identity,
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
        terminal_ownership = {
            "attempt_id": attempt_id,
            "local_task_id": local_task,
            "external_task_id": external_task,
            "dispatch_id": dispatch_id,
            "run_id": self.run_id,
        }
        if not all(isinstance(value, str) and value for value in terminal_ownership.values()):
            raise DriverError(
                "Orca tracked-terminal dispatch omitted its ownership binding",
                code="invalid_receipt",
                receipt={"dispatch": dispatched, "ownership": terminal_ownership},
            )
        owned_terminal = {**identity, "ownership": terminal_ownership}
        self.created_terminals[attempt_id] = owned_terminal
        return DriverReceipt(
            "start_attempt",
            "started",
            local_ids={"task_id": local_task, "attempt_id": attempt_id},
            external_refs={"tier": "tracked-terminal", "run_id": self.run_id, "task_id": external_task, "dispatch_id": dispatch_id, "worktree_id": placement["worktree_id"], "terminal": {**owned_terminal, "managed_lease": False}, "terminal_command": terminal_command, "execution_profile": profile, "resolved_placement": placement["resolved_placement"], "workspace_scope": attempt["workspace_scope"], "placement_environment": profile["resolved_placement"]["execution_host_id"] if remote_execution else None, "placement_receipt": placement["receipt"]},
            raw={"placement": placement["receipt"], "task_ready": task_ready, "worker_start": supervised, "terminal_snapshot": existing_terminals, "recovered_terminal": bool(recovered_handle), "terminal_command": terminal_command, "terminal_create": terminal, "terminal_show": terminal_show, "terminal_wait": waited, "dispatch": dispatched, "dispatch_show": dispatch_show, **({"pre_resource_recovery": pre_resource_recovery} if pre_resource_recovery is not None else {})},
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
        if tier == "supervised":
            dispatch_id = str(attempt["dispatch_id"])
            receipt = self._call("orchestration", "worker-release", "--dispatch", dispatch_id, "--json", allow_error=True)
            if receipt.get("ok") is False:
                code, message = _error(receipt)
                if code != "already_released":
                    raise DriverError(message, code=code, receipt=receipt)
            return DriverReceipt("release", "released", external_refs={"tier": tier, "dispatch_id": dispatch_id}, raw=receipt)
        if tier != "tracked-terminal":
            raise DriverError(f"unknown Orca lifecycle tier: {tier}", code="invalid_tier")
        attempt_id = attempt.get("attempt_id")
        record = self.created_terminals.get(str(attempt_id)) if isinstance(attempt_id, str) else None
        if not isinstance(record, Mapping):
            raise DriverError("tracked terminal has no creation receipt", code="cleanup_unproven")
        expected = record
        ownership = expected.get("ownership")
        if not isinstance(ownership, Mapping):
            raise DriverError("tracked terminal ownership receipt is malformed", code="cleanup_unproven")
        supplied = {
            "attempt_id": attempt.get("attempt_id"),
            "local_task_id": attempt.get("task_id"),
            "external_task_id": attempt.get("external_task_id"),
            "dispatch_id": attempt.get("dispatch_id"),
            "run_id": attempt.get("run_id"),
        }
        if any(
            not isinstance(supplied[key], str) or supplied[key] != ownership.get(key)
            for key in supplied
        ):
            raise DriverError(
                "tracked terminal release does not match its owned attempt binding",
                code="cleanup_unproven",
                receipt={"expected": dict(ownership), "supplied": supplied},
            )
        placement = self._restore_saved_placement(attempt)
        if expected.get("worktree_id") != placement["worktree_id"]:
            raise DriverError(
                "tracked terminal release terminal differs from its saved worktree",
                code="cleanup_unproven",
                receipt={"terminal": dict(expected), "placement": placement},
            )
        dispatch_id = ownership["dispatch_id"]
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

    def _browser_surface(self, operation: str, request: Mapping[str, Any]) -> DriverReceipt:
        try:
            requested = validate_browser_surface_request(request)
        except BrowserSurfaceError as error:
            raise DriverError(str(error), code="browser_surface_invalid") from error
        if "browser.surface.v1" not in self.runtime_capabilities:
            compact = unavailable_receipt(
                requested, operation=operation, code="old-peer", detail="Orca did not advertise browser.surface.v1."
            )
        else:
            provider = self._call(
                "browser-surface",
                "--operation",
                operation,
                "--request",
                json.dumps(requested, separators=(",", ":"), sort_keys=True),
                "--json",
                allow_error=True,
            )
            if provider.get("ok") is False:
                provider_code, _provider_message = _error(provider)
                code = {
                    "remote_unreachable": "remote-unreachable",
                    "outcome_unknown": "outcome-unknown",
                    "unverifiable": "unverifiable",
                    "unsupported": "unsupported",
                }.get(provider_code, "unverifiable")
                compact = unavailable_receipt(
                    requested,
                    operation=operation,
                    code=code,
                    detail="Browser-surface provider outcome was not independently verifiable.",
                )
            else:
                candidate = _entity(provider, "receipt", "browserSurfaceReceipt")
                try:
                    compact = validate_receipt_for_request(candidate, requested)
                except BrowserSurfaceError as error:
                    raise DriverError(str(error), code="invalid_receipt") from error
        compact = public_receipt(compact)
        return DriverReceipt(
            f"browser_surface_{operation}",
            compact["status"],
            external_refs={"browser_surface": compact},
            raw={"receipt_id": compact["receipt_id"], "operation": operation},
        )

    def reserve_browser_surface(self, request: Mapping[str, Any]) -> DriverReceipt:
        return self._browser_surface("reserve", request)

    def bind_browser_surface(self, request: Mapping[str, Any]) -> DriverReceipt:
        return self._browser_surface("bind", request)

    def capture_browser_surface(self, request: Mapping[str, Any]) -> DriverReceipt:
        return self._browser_surface("capture", request)

    def release_browser_surface(self, request: Mapping[str, Any]) -> DriverReceipt:
        return self._browser_surface("release", request)

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
                dispatch_result = _result(dispatch)
                dispatch_value = (
                    dispatch_result.get("dispatch")
                    if isinstance(dispatch_result, Mapping)
                    else object()
                )
                resource_state = (
                    "present"
                    if dispatch_value is not None or title_present
                    else "absent"
                    if dispatch.get("ok") is True and isinstance(dispatch_result, Mapping) and "dispatch" in dispatch_result
                    else "unknown"
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
