#!/usr/bin/env python3
"""Repository-backed transport for host-native and local workers.

The host driver deliberately does not start agents.  The active host owns its
native worker API, while this module supplies the bounded capsule and durable
result boundary shared by native and local execution.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


SCRIPTS_DIRECTORY = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIRECTORY))

from graph_core import (  # noqa: E402
    TASK_ID_PATTERN,
    GraphValidationError,
    TaskContract,
    normalize_repo_path,
    validate_worker_result,
)
from artifact_policy import artifact_policy  # noqa: E402
from drivers.base import (  # noqa: E402
    DriverError,
    DriverReceipt,
    build_capability_receipt,
    capability,
    execution_profile_from_attempt,
)
from browser_surfaces import (  # noqa: E402
    BrowserSurfaceError,
    public_receipt,
    unavailable_receipt,
    validate_browser_surface_request,
    validate_receipt_for_request,
)


CAPSULE_FIELDS = frozenset(
    {"task", "effective_scope", "dependency_digest", "driver_instructions", "execution_profile", "workspace_scope", "result_path"}
)
OPTIONAL_CAPSULE_FIELDS = frozenset({"session_handoff"})
RESULT_FIELDS = (
    "task_id",
    "attempt_id",
    "outcome",
    "summary",
    "files_changed",
    "checks_run",
    "evidence_refs",
    "questions",
    "external_refs",
)


class HostDriverError(DriverError):
    """Reports an invalid host-driver request or repository artifact."""


class DuplicateResultError(HostDriverError):
    """Reports a second terminal result for one attempt."""


class CanonicalResultConflictError(HostDriverError):
    """Reports distinct candidate and canonical result bodies without mutation."""


def _json_digest(value: Mapping[str, Any]) -> str:
    payload = json.dumps(dict(value), separators=(",", ":"), sort_keys=True).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _file_digest(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def coordinator_capsule_invocation(capsule_path: str | Path) -> str:
    """Return the exact manual fresh-session invocation for a capsule."""

    path = _repository_path_text(capsule_path, "coordinator capsule path")
    return f"$impl --coordinator-capsule {path}"


def _repository_path_text(value: str | Path, context: str) -> str:
    text = value.as_posix() if isinstance(value, Path) else value
    try:
        return normalize_repo_path(text, context)
    except GraphValidationError as error:
        raise HostDriverError(str(error)) from error


def _artifact_name(attempt_id: str) -> str:
    if not isinstance(attempt_id, str) or not TASK_ID_PATTERN.fullmatch(attempt_id):
        raise HostDriverError("attempt_id must be safe for a repository artifact name")
    return f"{attempt_id}.json"


def _read_json_object(path: Path, context: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise HostDriverError(f"{context} does not exist: {path}") from error
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise HostDriverError(f"cannot read {context} {path}: {error}") from error
    if not isinstance(value, dict):
        raise HostDriverError(f"{context} must contain one JSON object")
    return value


def _write_new_json(path: Path, value: Mapping[str, Any], context: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as error:
        raise HostDriverError(f"{context} already exists: {path}") from error
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _task_payload(task: TaskContract) -> dict[str, Any]:
    return {
        "id": task.id,
        "title": task.title,
        "depends": list(task.depends),
        "paths": list(task.paths),
        "mode": task.mode,
        "isolation": task.isolation,
        "context": task.context,
        "acceptance": task.acceptance,
        "check": task.check,
        "visual": list(task.visual),
        "visual_scope": list(task.visual_scope),
    }


def _effective_scope(task: TaskContract, attempt_id: str, value: Any) -> dict[str, Any]:
    scope = value if isinstance(value, Mapping) else {
        "attempt_id": attempt_id,
        "parent_task_id": task.id,
        "paths": list(task.paths),
        "amendment_ids": [],
    }
    required = {"attempt_id", "parent_task_id", "paths", "amendment_ids"}
    if not isinstance(scope, Mapping) or set(scope) - (required | {"digest"}) or not required <= set(scope):
        raise HostDriverError("effective_scope is invalid")
    canonical = {key: scope[key] for key in ("attempt_id", "parent_task_id", "paths", "amendment_ids")}
    if canonical["attempt_id"] != attempt_id or canonical["parent_task_id"] != task.id:
        raise HostDriverError("effective_scope does not match its attempt")
    if not isinstance(canonical["paths"], list) or not isinstance(canonical["amendment_ids"], list):
        raise HostDriverError("effective_scope paths and amendment_ids must be arrays")
    for path in canonical["paths"]:
        try:
            normalize_repo_path(path, "effective_scope path")
        except GraphValidationError as error:
            raise HostDriverError(str(error)) from error
    digest = f"sha256:{hashlib.sha256(json.dumps(canonical, separators=(',', ':'), sort_keys=True).encode('utf-8')).hexdigest()}"
    if "digest" in scope and scope["digest"] != digest:
        raise HostDriverError("effective_scope digest is invalid")
    return {**canonical, "digest": digest}


def _task_from_payload(value: Mapping[str, Any]) -> TaskContract:
    try:
        return TaskContract(
            id=value["id"],
            title=value["title"],
            depends=tuple(value["depends"]),
            paths=tuple(value["paths"]),
            mode=value["mode"],
            isolation=value["isolation"],
            context=value.get("context", ""),
            acceptance=value["acceptance"],
            check=value["check"],
            visual=tuple(value.get("visual", ())),
            visual_scope=tuple(value.get("visual_scope", ())),
        )
    except (KeyError, TypeError) as error:
        raise HostDriverError("saved task contract is malformed") from error


def _latest_report(
    projection: Mapping[str, Any], task_state: Mapping[str, Any]
) -> Mapping[str, Any]:
    attempts = projection.get("attempts", {})
    if not isinstance(attempts, Mapping):
        return {}
    attempt_ids = task_state.get("attempt_ids", [])
    if not isinstance(attempt_ids, list):
        return {}
    for attempt_id in reversed(attempt_ids):
        attempt = attempts.get(attempt_id, {})
        if isinstance(attempt, Mapping) and isinstance(attempt.get("report"), Mapping):
            return attempt["report"]
    return {}


def dependency_digest_from_projection(
    task: TaskContract, projection: Mapping[str, Any]
) -> list[dict[str, Any]]:
    tasks = projection.get("tasks", {})
    if not isinstance(tasks, Mapping):
        raise HostDriverError("projection tasks must be an object")
    digest: list[dict[str, Any]] = []
    for dependency_id in task.depends:
        dependency = tasks.get(dependency_id)
        if not isinstance(dependency, Mapping):
            raise HostDriverError(f"projection is missing dependency {dependency_id}")
        if dependency.get("grade") != "pass":
            raise HostDriverError(
                f"task {task.id} is not ready; dependency {dependency_id} is not pass"
            )
        report = _latest_report(projection, dependency)
        digest.append(
            {
                "task_id": dependency_id,
                "grade": "pass",
                "summary": report.get("summary", ""),
                "files_changed": list(report.get("files_changed", [])),
                "evidence_refs": list(report.get("evidence_refs", [])),
            }
        )
    return digest


def _validate_dependency_digest(
    task: TaskContract, value: Any
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise HostDriverError("dependency_digest must be an array")
    expected_ids = list(task.depends)
    actual_ids: list[str] = []
    normalized: list[dict[str, Any]] = []
    for entry in value:
        if not isinstance(entry, Mapping):
            raise HostDriverError("dependency_digest entries must be objects")
        task_id = entry.get("task_id")
        grade = entry.get("grade")
        if not isinstance(task_id, str) or not task_id:
            raise HostDriverError("dependency_digest task_id must be a non-empty string")
        if grade != "pass":
            raise HostDriverError(
                f"task {task.id} is not ready; dependency {task_id} is not pass"
            )
        actual_ids.append(task_id)
        normalized.append(json.loads(json.dumps(dict(entry), sort_keys=True)))
    if actual_ids != expected_ids:
        raise HostDriverError("dependency_digest does not match the task dependencies")
    return normalized


def _attempt_task(attempt: Mapping[str, Any]) -> TaskContract:
    value = attempt.get("task", attempt.get("contract"))
    if isinstance(value, TaskContract):
        task = value
    elif isinstance(value, Mapping):
        task = _task_from_payload(value)
    else:
        raise HostDriverError("attempt must include its task contract")
    if attempt.get("task_id") != task.id:
        raise HostDriverError("attempt task_id does not match its task contract")
    return task


def _driver_instructions(attempt_id: str) -> dict[str, Any]:
    return {
        "role": "bounded_worker",
        "attempt_id": attempt_id,
        "coordinator": False,
        "execution": "Use the active host's native worker API or execute locally.",
        "scope": "Work only on the task contract and declared repository paths.",
        "result": {
            "format": "agent-graph worker-result JSON",
            "required_fields": list(RESULT_FIELDS),
            "outcome": "reported",
            "write_once": True,
        },
        "artifact_policy": artifact_policy(),
        "prohibitions": [
            "Do not act as the implementation coordinator.",
            "Do not mutate the graph journal or projection.",
            "Do not shell out to an agent CLI.",
        ],
    }


class HostDriver:
    """Create bounded host capsules and accept schema-validated results."""

    name = "host"

    def __init__(
        self,
        repository: Path,
        run_directory: Path,
        *,
        native_browser_surface: Callable[[str, Mapping[str, Any]], Mapping[str, Any]] | None = None,
    ) -> None:
        self.repository = Path(repository).resolve()
        self.run_directory = Path(run_directory).resolve()
        try:
            self.run_directory.relative_to(self.repository)
        except ValueError as error:
            raise HostDriverError("run directory must be inside the repository") from error
        self.capsules_directory = self.run_directory / "capsules"
        self.results_directory = self.run_directory / "results"
        self.native_browser_surface = native_browser_surface

    def _relative(self, path: Path) -> str:
        return path.relative_to(self.repository).as_posix()

    def _capsule_path(self, attempt_id: str) -> Path:
        return self.capsules_directory / _artifact_name(attempt_id)

    def _result_path(self, attempt_id: str) -> Path:
        return self.results_directory / _artifact_name(attempt_id)

    def detect(self) -> DriverReceipt:
        """Report capabilities without probing or mutating an external host."""

        capabilities = {
            "local_checks": capability(
                "supported", method="configuration", evidence="host:bounded-command-runner"
            ),
            "user_questions": capability(
                "supported", method="configuration", evidence="host:manual-question-boundary"
            ),
            "process_tree_cleanup": capability(
                "supported", method="configuration", evidence="host:owned-process-tree-runner"
            ),
            "isolated_workspace": capability(
                "unsupported", reason="Host does not create an isolated workspace."
            ),
            "visible_worker_dispatch": capability(
                "unsupported", reason="Visible worker dispatch is owned by the active host."
            ),
            "durable_worker_handle": capability(
                "unavailable", reason="A native worker handle is optional and was not observed."
            ),
            "browser_surface": (
                capability("supported", method="configuration", evidence="host:explicit-native-browser-surface")
                if self.native_browser_surface is not None
                else capability("unsupported", reason="Host has no explicit native browser-surface capability.")
            ),
            "usage_metrics": capability(
                "unavailable", reason="Host did not expose provider usage metrics."
            ),
            "cache_metrics": capability(
                "unavailable", reason="Host did not expose provider cache metrics."
            ),
        }
        capability_receipt = build_capability_receipt(
            self.name,
            capabilities,
            version="1",
            extensions={
                "host": {
                    "execution_tiers": ["local", "host-native", "manual"],
                    "agent_cli_subprocess": False,
                }
            },
        )

        return DriverReceipt(
            "detect",
            "available",
            external_refs={
                "driver": self.name,
                "capabilities": capability_receipt["capabilities"],
                "capability_receipt": capability_receipt,
            },
        )

    def start_run(
        self, objective: str, tasks: Sequence[Mapping[str, Any]]
    ) -> DriverReceipt:
        """Bind the driver to the already-created repository run."""

        if not isinstance(objective, str) or not objective.strip():
            raise HostDriverError("objective must be a non-empty string")
        if not isinstance(tasks, Sequence) or isinstance(tasks, (str, bytes)):
            raise HostDriverError("tasks must be a sequence")
        return DriverReceipt(
            "start_run",
            "started",
            external_refs={"driver": self.name},
            raw={
                "objective": objective,
                "task_count": len(tasks),
                "run_directory": self._relative(self.run_directory),
            },
        )

    def start_attempt(
        self,
        attempt: Mapping[str, Any],
    ) -> DriverReceipt:
        """Write one task capsule after confirming its dependencies passed."""

        task = _attempt_task(attempt)
        execution_profile = execution_profile_from_attempt(attempt)
        attempt_id = attempt.get("attempt_id")
        _artifact_name(attempt_id)
        worker_handle = attempt.get("worker_handle")
        local = attempt.get("local", False)
        if worker_handle is not None and (
            not isinstance(worker_handle, str) or not worker_handle.strip()
        ):
            raise HostDriverError("worker_handle must be a non-empty string when provided")

        result_path = self._result_path(attempt_id)
        effective_scope = _effective_scope(task, attempt_id, attempt.get("effective_scope"))
        session_handoff = attempt.get("session_handoff")
        if session_handoff is not None and not isinstance(session_handoff, Mapping):
            raise HostDriverError("session_handoff must be a bounded object when supplied")
        capsule = {
            "task": _task_payload(task),
            "effective_scope": effective_scope,
            "dependency_digest": _validate_dependency_digest(
                task, attempt.get("dependency_digest")
            ),
            "driver_instructions": _driver_instructions(attempt_id),
            "execution_profile": execution_profile,
            "workspace_scope": attempt["workspace_scope"],
            "result_path": self._relative(result_path),
            **({"session_handoff": dict(session_handoff)} if session_handoff is not None else {}),
        }
        capsule_path = self._capsule_path(attempt_id)
        replayed = False
        if capsule_path.exists():
            if self.load_capsule(attempt_id) != capsule:
                raise HostDriverError(
                    f"task capsule already exists with different content: {capsule_path}"
                )
            replayed = True
        else:
            _write_new_json(capsule_path, capsule, "task capsule")
        tier = "local" if local else "host-native"
        return DriverReceipt(
            "start_attempt",
            "started",
            local_ids={"task_id": task.id, "attempt_id": attempt_id},
            external_refs={
                "tier": tier,
                "capsule_path": self._relative(capsule_path),
                "result_path": capsule["result_path"],
                "execution_profile": execution_profile,
                "resolved_placement": execution_profile["resolved_placement"],
                **({"worker_handle": worker_handle} if worker_handle else {}),
            },
            raw={
                "capsule_path": self._relative(capsule_path),
                "result_path": capsule["result_path"],
                "replayed": replayed,
            },
        )

    def load_capsule(self, attempt_id: str) -> dict[str, Any]:
        """Load and structurally verify one repository capsule."""

        capsule = _read_json_object(self._capsule_path(attempt_id), "task capsule")
        if set(capsule) not in {CAPSULE_FIELDS, CAPSULE_FIELDS | OPTIONAL_CAPSULE_FIELDS}:
            raise HostDriverError("task capsule has fields outside the bounded contract")
        if not isinstance(capsule.get("task"), Mapping):
            raise HostDriverError("task capsule task must be an object")
        _task_from_payload(capsule["task"])
        scope = _effective_scope(_task_from_payload(capsule["task"]), attempt_id, capsule.get("effective_scope"))
        if scope != capsule["effective_scope"]:
            raise HostDriverError("task capsule effective_scope is invalid")
        if not isinstance(capsule.get("dependency_digest"), list):
            raise HostDriverError("task capsule dependency_digest must be an array")
        if not isinstance(capsule.get("driver_instructions"), Mapping):
            raise HostDriverError("task capsule driver_instructions must be an object")
        execution_profile_from_attempt(capsule)
        expected_result = self._relative(self._result_path(attempt_id))
        if capsule.get("result_path") != expected_result:
            raise HostDriverError("task capsule result_path does not match its attempt")
        if "session_handoff" in capsule and not isinstance(capsule["session_handoff"], Mapping):
            raise HostDriverError("task capsule session_handoff must be an object")
        return capsule

    def record_result(
        self,
        task: TaskContract,
        attempt_id: str,
        result: Mapping[str, Any],
        *,
        projection: Mapping[str, Any] | None = None,
    ) -> DriverReceipt:
        """Validate and durably record one terminal report exactly once."""

        self.load_capsule(attempt_id)
        if projection is not None:
            attempt = projection.get("attempts", {}).get(attempt_id, {})
            if isinstance(attempt, Mapping) and attempt and attempt.get("task_id") != task.id:
                raise HostDriverError("projection attempt does not belong to the task")
        capsule = self.load_capsule(attempt_id)
        scope = capsule["effective_scope"]
        if projection is not None:
            attempt = projection.get("attempts", {}).get(attempt_id, {})
            if isinstance(attempt, Mapping):
                try:
                    persisted_scope = _effective_scope(task, attempt_id, attempt.get("effective_scope"))
                except HostDriverError as error:
                    raise HostDriverError("effective_scope drift in immutable attempt", code="scope_drift") from error
                if persisted_scope != scope:
                    raise HostDriverError(
                        "effective_scope drift between immutable capsule and attempt",
                        code="scope_drift",
                    )
        effective_task = TaskContract(**{**task.to_dict(), "paths": tuple(scope["paths"])})
        try:
            validated = validate_worker_result(result, effective_task, attempt_id)
        except GraphValidationError as error:
            raise HostDriverError(str(error)) from error
        result_path = self._result_path(attempt_id)
        if result_path.exists():
            candidate_digest = _json_digest(validated)
            canonical_digest = _file_digest(result_path)
            try:
                saved = self.read_result(task, attempt_id)
            except HostDriverError as error:
                raise CanonicalResultConflictError(
                    f"canonical_result_conflict attempt={attempt_id} candidate_digest={candidate_digest} canonical_digest={canonical_digest}",
                    code="canonical_result_conflict",
                ) from error
            if saved == validated:
                return DriverReceipt(
                    "record_result",
                    "reported",
                    local_ids={"task_id": task.id, "attempt_id": attempt_id},
                    raw={"result": saved, "recovered_existing_file": True},
                )
            raise CanonicalResultConflictError(
                f"canonical_result_conflict attempt={attempt_id} candidate_digest={candidate_digest} canonical_digest={canonical_digest}",
                code="canonical_result_conflict",
            )
        _write_new_json(result_path, validated, "worker result")
        return DriverReceipt(
            "record_result",
            "reported",
            local_ids={"task_id": task.id, "attempt_id": attempt_id},
            raw={
                "event": "worker_reported",
                "result_path": self._relative(result_path),
                "result": validated,
            },
        )

    def record_local_result(
        self,
        task: TaskContract,
        attempt_id: str,
        result: Mapping[str, Any],
        *,
        projection: Mapping[str, Any] | None = None,
    ) -> DriverReceipt:
        """Submit local execution through the identical result boundary."""

        return self.record_result(
            task,
            attempt_id,
            result,
            projection=projection,
        )

    def read_result(self, task: TaskContract, attempt_id: str) -> dict[str, Any]:
        """Read and validate a result written directly to its capsule path."""

        result = _read_json_object(self._result_path(attempt_id), "worker result")
        try:
            capsule = self.load_capsule(attempt_id)
            effective_task = TaskContract(**{**task.to_dict(), "paths": tuple(capsule["effective_scope"]["paths"])})
            return validate_worker_result(result, effective_task, attempt_id)
        except GraphValidationError as error:
            raise HostDriverError(str(error)) from error

    def poll(
        self,
        attempt: Mapping[str, Any],
        *,
        cursor: str | None = None,
    ) -> DriverReceipt:
        """Return a bounded lifecycle event when a valid result is present."""

        task = _attempt_task(attempt)
        attempt_id = attempt.get("attempt_id")
        _artifact_name(attempt_id)
        if attempt.get("status") == "reported":
            return DriverReceipt(
                "poll",
                "observed",
                local_ids={"task_id": task.id, "attempt_id": attempt_id},
                external_refs={"cursor": cursor},
                raw={"events": []},
            )
        path = self._result_path(attempt_id)
        if not path.exists():
            return DriverReceipt(
                "poll",
                "observed",
                local_ids={"task_id": task.id, "attempt_id": attempt_id},
                external_refs={"cursor": cursor},
                raw={"events": []},
            )
        result = self.read_result(task, attempt_id)
        event = {
            "type": "worker_reported",
            "task_id": task.id,
            "attempt_id": attempt_id,
            "result_path": self._relative(path),
            "result": result,
        }
        return DriverReceipt(
            "poll",
            "observed",
            local_ids={"task_id": task.id, "attempt_id": attempt_id},
            external_refs={"cursor": str(path.stat().st_mtime_ns)},
            raw={"events": [event]},
        )

    def send(
        self, attempt: Mapping[str, Any], message: Mapping[str, Any]
    ) -> DriverReceipt:
        """Return scoped guidance for delivery by the active host."""

        attempt_id = attempt.get("attempt_id")
        _artifact_name(attempt_id)
        if not isinstance(message, Mapping) or not message:
            raise HostDriverError("message must be a non-empty object")
        worker_handle = _worker_handle(attempt)
        return DriverReceipt(
            "send",
            "host-delivery-required",
            local_ids={"attempt_id": attempt_id},
            external_refs=({"worker_handle": worker_handle} if worker_handle else {}),
            raw={"message": json.loads(json.dumps(dict(message), sort_keys=True))},
        )

    def release(
        self, attempt: Mapping[str, Any]
    ) -> DriverReceipt:
        """Confirm that the host driver itself owns no process to terminate."""

        attempt_id = attempt.get("attempt_id")
        _artifact_name(attempt_id)
        worker_handle = _worker_handle(attempt)
        return DriverReceipt(
            "release",
            "released",
            local_ids={"attempt_id": attempt_id},
            external_refs=({"worker_handle": worker_handle} if worker_handle else {}),
            raw={"cleanup": "none-owned-by-driver"},
        )

    def _browser_surface(self, operation: str, request: Mapping[str, Any]) -> DriverReceipt:
        try:
            requested = validate_browser_surface_request(request)
        except BrowserSurfaceError as error:
            raise HostDriverError(str(error), code="browser_surface_invalid") from error
        if self.native_browser_surface is None:
            receipt = unavailable_receipt(
                requested,
                operation=operation,
                code="native-capability-unavailable",
                detail="Host has no explicit native browser-surface capability.",
            )
        else:
            try:
                receipt = validate_receipt_for_request(
                    self.native_browser_surface(operation, requested), requested
                )
            except BrowserSurfaceError as error:
                raise HostDriverError(str(error), code="browser_surface_invalid") from error
        compact = public_receipt(receipt)
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

    def reconcile(
        self, attempts: Sequence[Mapping[str, Any]]
    ) -> DriverReceipt:
        """Rebuild host-attempt observations without requiring live handles."""

        observations: list[dict[str, Any]] = []
        for attempt in attempts:
            if not isinstance(attempt, Mapping):
                raise HostDriverError("projection contains a malformed attempt")
            if attempt.get("driver") != self.name:
                continue
            task = _attempt_task(attempt)
            attempt_id = attempt.get("attempt_id")
            _artifact_name(attempt_id)
            capsule_exists = self._capsule_path(attempt_id).is_file()
            result_exists = self._result_path(attempt_id).is_file()
            observation: dict[str, Any] = {
                "task_id": task.id,
                "attempt_id": attempt_id,
                "status": attempt.get("status"),
                "capsule_path": (
                    self._relative(self._capsule_path(attempt_id)) if capsule_exists else None
                ),
                "result_path": (
                    self._relative(self._result_path(attempt_id)) if result_exists else None
                ),
                "worker_handle": _worker_handle(attempt),
            }
            if result_exists and attempt.get("status") == "running":
                observation["event"] = {
                    "type": "worker_reported",
                    "result": self.read_result(task, attempt_id),
                }
            observations.append(observation)
        return DriverReceipt("reconcile", "observed", raw=observations)

    def coordinator_handoff(
        self,
        capsule_path: str | Path,
        *,
        visible_fresh_session_handoff: bool,
    ) -> DriverReceipt:
        """Describe the host-owned top-level coordinator transfer boundary."""

        invocation = coordinator_capsule_invocation(capsule_path)
        return DriverReceipt(
            "coordinator_handoff",
            (
                "host-handoff-required"
                if visible_fresh_session_handoff
                else "manual-handoff-required"
            ),
            external_refs={"driver": self.name},
            raw={"invocation": invocation, "continue_in_bootstrap": False},
        )


def _worker_handle(attempt: Mapping[str, Any]) -> Any:
    direct = attempt.get("worker_handle")
    if direct is not None:
        return direct
    external_refs = attempt.get("external_refs", {})
    if isinstance(external_refs, Mapping):
        return external_refs.get("worker_handle")
    return None


__all__ = [
    "CAPSULE_FIELDS",
    "DuplicateResultError",
    "HostDriver",
    "HostDriverError",
    "coordinator_capsule_invocation",
    "dependency_digest_from_projection",
]
