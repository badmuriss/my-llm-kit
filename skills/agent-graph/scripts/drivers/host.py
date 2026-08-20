#!/usr/bin/env python3
"""Repository-backed transport for host-native and local workers.

The host driver deliberately does not start agents.  The active host owns its
native worker API, while this module supplies the bounded capsule and durable
result boundary shared by native and local execution.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


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
from drivers.base import DriverError, DriverReceipt  # noqa: E402


CAPSULE_FIELDS = frozenset(
    {"task", "dependency_digest", "driver_instructions", "result_path"}
)
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
        "prohibitions": [
            "Do not act as the implementation coordinator.",
            "Do not mutate the graph journal or projection.",
            "Do not shell out to an agent CLI.",
        ],
    }


class HostDriver:
    """Create bounded host capsules and accept schema-validated results."""

    name = "host"

    def __init__(self, repository: Path, run_directory: Path) -> None:
        self.repository = Path(repository).resolve()
        self.run_directory = Path(run_directory).resolve()
        try:
            self.run_directory.relative_to(self.repository)
        except ValueError as error:
            raise HostDriverError("run directory must be inside the repository") from error
        self.capsules_directory = self.run_directory / "capsules"
        self.results_directory = self.run_directory / "results"

    def _relative(self, path: Path) -> str:
        return path.relative_to(self.repository).as_posix()

    def _capsule_path(self, attempt_id: str) -> Path:
        return self.capsules_directory / _artifact_name(attempt_id)

    def _result_path(self, attempt_id: str) -> Path:
        return self.results_directory / _artifact_name(attempt_id)

    def detect(self) -> DriverReceipt:
        """Report capabilities without probing or mutating an external host."""

        capabilities = {
            "repository_state": True,
            "native_worker_handle": "optional",
            "visible_fresh_session_handoff": "host_owned",
            "agent_cli_subprocess": False,
        }

        return DriverReceipt(
            "detect",
            "available",
            external_refs={"driver": self.name, "capabilities": capabilities},
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
        attempt_id = attempt.get("attempt_id")
        _artifact_name(attempt_id)
        worker_handle = attempt.get("worker_handle")
        local = attempt.get("local", False)
        if worker_handle is not None and (
            not isinstance(worker_handle, str) or not worker_handle.strip()
        ):
            raise HostDriverError("worker_handle must be a non-empty string when provided")

        result_path = self._result_path(attempt_id)
        capsule = {
            "task": _task_payload(task),
            "dependency_digest": _validate_dependency_digest(
                task, attempt.get("dependency_digest")
            ),
            "driver_instructions": _driver_instructions(attempt_id),
            "result_path": self._relative(result_path),
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
        if set(capsule) != CAPSULE_FIELDS:
            raise HostDriverError("task capsule has fields outside the bounded contract")
        if not isinstance(capsule.get("task"), Mapping):
            raise HostDriverError("task capsule task must be an object")
        _task_from_payload(capsule["task"])
        if not isinstance(capsule.get("dependency_digest"), list):
            raise HostDriverError("task capsule dependency_digest must be an array")
        if not isinstance(capsule.get("driver_instructions"), Mapping):
            raise HostDriverError("task capsule driver_instructions must be an object")
        expected_result = self._relative(self._result_path(attempt_id))
        if capsule.get("result_path") != expected_result:
            raise HostDriverError("task capsule result_path does not match its attempt")
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
            if isinstance(attempt, Mapping) and attempt.get("status") == "reported":
                raise DuplicateResultError(
                    f"attempt already has a terminal report: {attempt_id}"
                )
            if isinstance(attempt, Mapping) and attempt and attempt.get("task_id") != task.id:
                raise HostDriverError("projection attempt does not belong to the task")
        try:
            validated = validate_worker_result(result, task, attempt_id)
        except GraphValidationError as error:
            raise HostDriverError(str(error)) from error
        result_path = self._result_path(attempt_id)
        if result_path.exists():
            raise DuplicateResultError(f"attempt already has a terminal report: {attempt_id}")
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
            return validate_worker_result(result, task, attempt_id)
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
