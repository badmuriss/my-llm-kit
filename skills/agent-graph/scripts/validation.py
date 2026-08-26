#!/usr/bin/env python3
"""Validation helpers shared by the Agent Graph CLI."""

from __future__ import annotations

import hashlib
import json
import math
import os
import shlex
import subprocess
import signal
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from graph_core import GraphValidationError, TASK_ID_PATTERN, normalize_repo_path


SHELL_OPERATOR_CHARACTERS = frozenset("|&;<>")
CLEANUP_KINDS = frozenset({"process", "worktree", "branch", "temp_path", "terminal", "other"})
CHECK_OUTPUT_CAP_BYTES = 65_536
MAX_CHECK_OUTPUT_CAP_BYTES = 1_048_576
MAX_CHECK_TIMEOUT_SECONDS = 3_600.0
REFERENCES_DIRECTORY = Path(__file__).resolve().parents[1] / "references"
_POSIX_GATE_LAUNCHER = (
    "import os, sys; "
    "gate = int(sys.argv[1]); "
    "released = os.read(gate, 1); "
    "os.close(gate); "
    "os.execvp(sys.argv[2], sys.argv[2:]) if released else sys.exit(126)"
)
CAPABILITY_NAMES = frozenset(
    {
        "local_checks",
        "user_questions",
        "process_tree_cleanup",
        "isolated_workspace",
        "visible_worker_dispatch",
        "durable_worker_handle",
        "browser_surface",
        "usage_metrics",
        "cache_metrics",
    }
)


@dataclass(frozen=True, slots=True)
class BoundedCommandResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    residue_unverifiable: bool
    start_error: str | None


@dataclass(frozen=True, slots=True)
class SharedCheckResult:
    execution_id: str
    command_digest: str
    source_snapshot_digest: str
    execution_policy_digest: str
    timeout_seconds: float
    output_cap_bytes: int
    owner_generation: int
    lifecycle: str
    artifact_ref: str
    cleanup_ref: str
    cleanup_id: str
    process_root: int | None
    process_group: int | None
    process_start_identity: str | None
    cleanup_authority: str
    cleanup_authority_id: str
    completed: BoundedCommandResult
    duration_ms: int


class CheckExecutionError(RuntimeError):
    """A durable Check execution cannot safely be joined or retried."""


def atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Persist one Check artifact without exposing a partial record to joiners."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _git_bytes(workspace: Path, *arguments: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(workspace), *arguments],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        message = completed.stderr.decode("utf-8", errors="replace").strip()
        raise CheckExecutionError(f"source snapshot git command failed: {message or arguments[0]}")
    return completed.stdout


def source_snapshot_digest(
    workspace: Path,
    *,
    workspace_scope: Mapping[str, Any],
    base_revision: str | None,
    run_directory: Path,
) -> str:
    """Hash the exact source surface while excluding only this run's artifacts."""

    if not isinstance(base_revision, str) or not base_revision:
        raise CheckExecutionError("source snapshot requires a persisted base revision")
    root = workspace.resolve()
    try:
        excluded = run_directory.resolve().relative_to(root).as_posix()
    except ValueError as error:
        raise CheckExecutionError("current run is outside the execution workspace") from error
    tracked_diff = _git_bytes(
        root,
        "diff",
        "--binary",
        base_revision,
        "--",
        ".",
        f":(exclude){excluded}/**",
    )
    untracked_names = _git_bytes(root, "ls-files", "--others", "--exclude-standard", "-z")
    untracked: list[dict[str, str]] = []
    for raw_name in untracked_names.split(b"\0"):
        if not raw_name:
            continue
        name = raw_name.decode("utf-8", errors="surrogateescape")
        if name == excluded or name.startswith(f"{excluded}/"):
            continue
        try:
            content = (root / name).read_bytes()
        except OSError as error:
            raise CheckExecutionError(f"cannot read untracked source file {name}: {error}") from error
        untracked.append({"path": name, "sha256": hashlib.sha256(content).hexdigest()})
    return _canonical_digest(
        {
            "workspace_scope": workspace_scope,
            "base_revision": base_revision,
            "tracked_diff_sha256": hashlib.sha256(tracked_diff).hexdigest(),
            "untracked": sorted(untracked, key=lambda entry: entry["path"]),
        }
    )


@contextmanager
def _execution_lock(path: Path) -> Any:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt

            if path.stat().st_size == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            return
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _pid_is_live(pid: object) -> bool:
    if not isinstance(pid, int) or isinstance(pid, bool) or pid < 1:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _process_start_identity(process_id: int) -> str | None:
    """Return a PID-reuse-safe local start identity when the host exposes one."""

    if os.name != "posix":
        return None
    try:
        fields = Path(f"/proc/{process_id}/stat").read_text(encoding="utf-8").split()
    except OSError:
        return None
    return fields[21] if len(fields) > 21 else None


def _execution_policy(timeout_seconds: float, output_cap_bytes: int) -> tuple[dict[str, int | float], str]:
    if (
        not isinstance(timeout_seconds, (int, float))
        or isinstance(timeout_seconds, bool)
        or not math.isfinite(timeout_seconds)
        or timeout_seconds <= 0
        or timeout_seconds > MAX_CHECK_TIMEOUT_SECONDS
    ):
        raise CliValidationError("check timeout must be finite and within the supported bound")
    if (
        not isinstance(output_cap_bytes, int)
        or isinstance(output_cap_bytes, bool)
        or not 1 <= output_cap_bytes <= MAX_CHECK_OUTPUT_CAP_BYTES
    ):
        raise CliValidationError("check output cap must be within the supported bound")
    policy = {"output_cap_bytes": output_cap_bytes, "timeout_seconds": float(timeout_seconds)}
    return policy, _canonical_digest(policy)


def _read_execution(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CheckExecutionError(f"check execution record is unreadable: {path}") from error
    if not isinstance(value, dict):
        raise CheckExecutionError("check execution record must be an object")
    return value


_OWNER_CAS_FIELDS = (
    "execution_id",
    "command_digest",
    "source_snapshot_digest",
    "execution_policy_digest",
    "timeout_seconds",
    "output_cap_bytes",
    "owner_generation",
    "artifact_ref",
    "cleanup_ref",
    "cleanup_id",
    "owner_pid",
    "process_root",
    "process_group",
    "process_start_identity",
    "cleanup_authority",
    "cleanup_authority_id",
    "lifecycle",
)


def _require_owner_cas(
    current: Mapping[str, Any], expected: Mapping[str, Any], context: str
) -> None:
    """Reject a stale owner before it can write an execution artifact or lifecycle."""

    if any(current.get(field) != expected.get(field) for field in _OWNER_CAS_FIELDS):
        raise CheckExecutionError(f"check execution ownership was lost before {context}")


def load_shared_check_record(*, run_directory: Path, execution_id: str) -> dict[str, Any]:
    """Load the immutable side record for the public recovery reconciler."""

    if not TASK_ID_PATTERN.fullmatch(execution_id) or not execution_id.startswith("check-"):
        raise CheckExecutionError("check execution ID is invalid")
    return _read_execution(
        run_directory / "artifacts" / "check-executions" / f"{execution_id}.json"
    )


def _write_execution_artifact_once(path: Path, artifact: Mapping[str, Any]) -> None:
    if not path.exists():
        atomic_write_json(path, artifact)
        return
    saved = _read_execution(path)
    if saved != artifact:
        raise CheckExecutionError("check execution artifact already belongs to another owner")


def run_shared_check(
    arguments: list[str],
    *,
    repository: Path,
    workspace: Path,
    run_directory: Path,
    workspace_scope: Mapping[str, Any],
    base_revision: str | None,
    owner_generation: int,
    timeout_seconds: float,
    output_cap_bytes: int = CHECK_OUTPUT_CAP_BYTES,
    consumer_ref: str,
    on_running: Callable[[Mapping[str, Any]], None] | None = None,
) -> SharedCheckResult:
    """Join or own one durable Check keyed by argv and exact source bytes."""

    policy, policy_digest = _execution_policy(timeout_seconds, output_cap_bytes)
    command_digest = _canonical_digest(arguments)
    snapshot_digest = source_snapshot_digest(
        workspace,
        workspace_scope=workspace_scope,
        base_revision=base_revision,
        run_directory=run_directory,
    )
    execution_id = f"check-{hashlib.sha256(f'{command_digest}:{snapshot_digest}:{policy_digest}'.encode()).hexdigest()[:24]}"
    executions_directory = run_directory / "artifacts" / "check-executions"
    record_path = executions_directory / f"{execution_id}.json"
    lock_path = executions_directory / ".lock"
    owner = False
    while True:
        with _execution_lock(lock_path):
            if not record_path.exists():
                active_match: tuple[Path, dict[str, Any]] | None = None
                for prior_path in executions_directory.glob("check-*.json"):
                    prior = _read_execution(prior_path)
                    if (
                        prior.get("command_digest") == command_digest
                        and prior.get("source_snapshot_digest") == snapshot_digest
                        and prior.get("execution_policy_digest") == policy_digest
                        and prior.get("lifecycle") == "running"
                    ):
                        active_match = (prior_path, prior)
                        break
                    if (
                        prior.get("command_digest") == command_digest
                        and prior.get("source_snapshot_digest") == snapshot_digest
                        and prior.get("lifecycle") == "blocked"
                    ):
                        raise CheckExecutionError(
                            "an earlier blocked check execution requires verified recovery: "
                            f"recover-check-execution --execution-id {prior.get('execution_id')}"
                        )
                if active_match is not None:
                    record_path, record = active_match
                    execution_id = str(record["execution_id"])
            if record_path.exists():
                record = _read_execution(record_path)
                if (
                    record.get("command_digest") != command_digest
                    or record.get("source_snapshot_digest") != snapshot_digest
                    or record.get("execution_policy_digest") != policy_digest
                ):
                    raise CheckExecutionError("check execution key collision")
                consumers = record.setdefault("consumer_refs", [])
                if consumer_ref not in consumers:
                    consumers.append(consumer_ref)
                    atomic_write_json(record_path, record)
                lifecycle = record.get("lifecycle")
                if lifecycle in {"passed", "failed", "failed_verified"}:
                    artifact_ref = record.get("artifact_ref")
                    if not isinstance(artifact_ref, str):
                        raise CheckExecutionError("completed check execution lacks an artifact")
                    artifact_path = repository / artifact_ref
                    evidence = _read_execution(artifact_path)
                    completed = BoundedCommandResult(
                        int(evidence["exit_code"]), "", "", bool(evidence.get("timed_out")),
                        bool(evidence.get("residue_unverifiable")), evidence.get("start_error"),
                    )
                    return _shared_result(record, completed, int(evidence["duration_ms"]))
                if lifecycle == "blocked":
                    raise CheckExecutionError(
                        "check execution has unverifiable owner residue: "
                        f"recover-check-execution --execution-id {record.get('execution_id')}"
                    )
                if lifecycle != "running":
                    raise CheckExecutionError("check execution has an invalid lifecycle")
                if not _pid_is_live(record.get("owner_pid")):
                    record["lifecycle"] = "blocked"
                    atomic_write_json(record_path, record)
                    raise CheckExecutionError("check owner exited before verified cleanup")
            else:
                artifact_ref = (run_directory / "artifacts" / "check-executions" / "results" / f"{execution_id}.json").relative_to(repository).as_posix()
                cleanup_ref = (run_directory / "artifacts" / "check-executions" / "cleanup" / f"{execution_id}.json").relative_to(repository).as_posix()
                record = {
                    "schema_version": 1,
                    "execution_id": execution_id,
                    "command_digest": command_digest,
                    "source_snapshot_digest": snapshot_digest,
                    "execution_policy_digest": policy_digest,
                    "timeout_seconds": policy["timeout_seconds"],
                    "output_cap_bytes": policy["output_cap_bytes"],
                    "owner_generation": owner_generation,
                    "lifecycle": "running",
                    "artifact_ref": artifact_ref,
                    "consumer_refs": [consumer_ref],
                    "cleanup_ref": cleanup_ref,
                    "cleanup_id": f"check-cleanup-{execution_id}",
                    "owner_pid": os.getpid(),
                    "process_root": None,
                    "process_group": None,
                    "process_start_identity": None,
                    "cleanup_authority": "process_group" if os.name != "nt" else "job_object",
                    "cleanup_authority_id": execution_id if os.name == "nt" else None,
                }
                atomic_write_json(record_path, record)
                owner = True
        if owner:
            break
        time.sleep(0.02)

    started = time.monotonic()
    owner_expected = dict(record)
    running_owner_record: dict[str, Any] | None = None

    def persist_process_identity(process_identity: Mapping[str, Any]) -> None:
        nonlocal running_owner_record
        with _execution_lock(lock_path):
            current = _read_execution(record_path)
            _require_owner_cas(current, owner_expected, "publishing process ownership")
            current.update(process_identity)
            atomic_write_json(record_path, current)
            running_owner_record = dict(current)
            atomic_write_json(
                repository / str(current["cleanup_ref"]),
                {
                    "execution_id": execution_id,
                    "cleanup_id": current["cleanup_id"],
                    "process_root": current["process_root"],
                    "process_group": current["process_group"],
                    "process_start_identity": current["process_start_identity"],
                    "cleanup_authority": current["cleanup_authority"],
                    "cleanup_authority_id": current["cleanup_authority_id"],
                    "status": "registered",
                },
            )
        if on_running is not None:
            on_running(dict(current))

    try:
        completed = run_bounded_command(
            arguments,
            cwd=workspace,
            timeout_seconds=timeout_seconds,
            output_cap_bytes=output_cap_bytes,
            on_started=persist_process_identity,
            windows_job_name=execution_id,
        )
    except BaseException as error:
        completed = BoundedCommandResult(
            125, "", "", False, True, f"running_publication_failed:{type(error).__name__}"
        )
    duration_ms = round((time.monotonic() - started) * 1000)
    artifact = {
        "schema_version": 1,
        "execution_id": execution_id,
        "command_digest": command_digest,
        "source_snapshot_digest": snapshot_digest,
        "execution_policy_digest": policy_digest,
        "timeout_seconds": policy["timeout_seconds"],
        "output_cap_bytes": policy["output_cap_bytes"],
        "exit_code": completed.exit_code,
        "duration_ms": duration_ms,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "start_error": completed.start_error,
        "timed_out": completed.timed_out,
        "residue_unverifiable": completed.residue_unverifiable,
    }
    with _execution_lock(lock_path):
        record = _read_execution(record_path)
        if running_owner_record is None:
            _require_owner_cas(record, owner_expected, "recording a start failure")
        else:
            _require_owner_cas(record, running_owner_record, "recording completion")
        _write_execution_artifact_once(repository / str(record["artifact_ref"]), artifact)
        record["lifecycle"] = (
            "passed" if completed.exit_code == 0 else "blocked"
            if completed.timed_out or completed.residue_unverifiable else "failed"
        )
        cleanup_path = repository / str(record["cleanup_ref"])
        if cleanup_path.exists():
            cleanup = _read_execution(cleanup_path)
            cleanup["status"] = (
                "unverifiable" if completed.timed_out or completed.residue_unverifiable else "verified"
            )
            atomic_write_json(cleanup_path, cleanup)
        atomic_write_json(record_path, record)
    if completed.start_error and completed.start_error.startswith("running_publication_failed:"):
        raise CheckExecutionError("check running publication failed; public recovery is required")
    return _shared_result(record, completed, duration_ms)


def _verify_recovery_authority(record: Mapping[str, Any]) -> None:
    """Fail closed unless the persisted process authority is conclusively absent."""

    process_root = record.get("process_root")
    start_identity = record.get("process_start_identity")
    if not isinstance(process_root, int) or isinstance(process_root, bool) or process_root < 1:
        raise CheckExecutionError("check execution has no recoverable process identity")
    if os.name == "posix" and not isinstance(start_identity, str):
        raise CheckExecutionError("check execution has no recoverable process start identity")
    live = _pid_is_live(process_root)
    if live and start_identity is not None and _process_start_identity(process_root) != start_identity:
        raise CheckExecutionError("check execution process identity is stale or unverifiable")
    if live:
        raise CheckExecutionError("check execution process identity is still live or unverifiable")
    if record.get("cleanup_authority") == "process_group":
        process_group = record.get("process_group")
        if not isinstance(process_group, int) or isinstance(process_group, bool) or process_group < 1:
            raise CheckExecutionError("check execution has no recoverable process group")
        if _process_group_is_live(process_group):
            raise CheckExecutionError("check execution process group is still live or unverifiable")
        return
    if record.get("cleanup_authority") == "job_object":
        authority_id = record.get("cleanup_authority_id")
        if not isinstance(authority_id, str) or not _windows_job_is_settled(authority_id):
            raise CheckExecutionError("check execution Job authority is still live or unverifiable")
        return
    raise CheckExecutionError("check execution cleanup authority is unknown")


def recover_shared_check(*, repository: Path, run_directory: Path, execution_id: str) -> SharedCheckResult:
    """Persist non-terminal recovery evidence before public terminal publication."""

    executions_directory = run_directory / "artifacts" / "check-executions"
    record_path = executions_directory / f"{execution_id}.json"
    lock_path = executions_directory / ".lock"
    with _execution_lock(lock_path):
        record = _read_execution(record_path)
        if record.get("lifecycle") == "running":
            if _pid_is_live(record.get("owner_pid")):
                raise CheckExecutionError("check execution owner is still live")
            _verify_recovery_authority(record)
            record["lifecycle"] = "blocked"
            cleanup_path = repository / str(record["cleanup_ref"])
            cleanup = _read_execution(cleanup_path)
            cleanup["status"] = "unverifiable"
            atomic_write_json(cleanup_path, cleanup)
            atomic_write_json(record_path, record)
        if record.get("lifecycle") not in {"blocked", "failed_verified"}:
            raise CheckExecutionError("only a blocked check execution can be recovered")
        _verify_recovery_authority(record)
        artifact_path = repository / str(record["artifact_ref"])
        if not artifact_path.exists():
            _write_execution_artifact_once(
                artifact_path,
                {
                    "schema_version": 1,
                    "execution_id": record["execution_id"],
                    "command_digest": record["command_digest"],
                    "source_snapshot_digest": record["source_snapshot_digest"],
                    "execution_policy_digest": record["execution_policy_digest"],
                    "timeout_seconds": record["timeout_seconds"],
                    "output_cap_bytes": record["output_cap_bytes"],
                    "exit_code": 125,
                    "duration_ms": 0,
                    "stdout": "",
                    "stderr": "",
                    "start_error": "owner_crashed_before_artifact",
                    "timed_out": False,
                    "residue_unverifiable": True,
                },
            )
        if record.get("lifecycle") == "blocked":
            recovery_stage = {
                "status": "prepared",
                "identity_digest": _canonical_digest(
                    {field: record.get(field) for field in _OWNER_CAS_FIELDS}
                ),
            }
            existing_stage = record.get("recovery_stage")
            if existing_stage is not None and existing_stage != recovery_stage:
                raise CheckExecutionError("check execution recovery fence changed")
            cleanup = _read_execution(repository / str(record["cleanup_ref"]))
            cleanup["status"] = "verified_absent"
            cleanup["verified_absent"] = True
            atomic_write_json(repository / str(record["cleanup_ref"]), cleanup)
            record["recovery_stage"] = recovery_stage
            atomic_write_json(record_path, record)
        artifact = _read_execution(repository / str(record["artifact_ref"]))
        recovered = {**record, "lifecycle": "failed_verified"}
    completed = BoundedCommandResult(int(artifact["exit_code"]), "", "", bool(artifact.get("timed_out")), bool(artifact.get("residue_unverifiable")), artifact.get("start_error"))
    return _shared_result(recovered, completed, int(artifact["duration_ms"]))


def finalize_shared_check_recovery(
    *, repository: Path, run_directory: Path, prepared: SharedCheckResult
) -> SharedCheckResult:
    """Converge a staged recovery after its public terminal event is durable."""

    executions_directory = run_directory / "artifacts" / "check-executions"
    record_path = executions_directory / f"{prepared.execution_id}.json"
    lock_path = executions_directory / ".lock"
    with _execution_lock(lock_path):
        record = _read_execution(record_path)
        immutable_identity = {
            "execution_id": prepared.execution_id,
            "command_digest": prepared.command_digest,
            "source_snapshot_digest": prepared.source_snapshot_digest,
            "execution_policy_digest": prepared.execution_policy_digest,
            "timeout_seconds": prepared.timeout_seconds,
            "output_cap_bytes": prepared.output_cap_bytes,
            "owner_generation": prepared.owner_generation,
            "artifact_ref": prepared.artifact_ref,
            "cleanup_ref": prepared.cleanup_ref,
            "cleanup_id": prepared.cleanup_id,
            "process_root": prepared.process_root,
            "process_group": prepared.process_group,
            "process_start_identity": prepared.process_start_identity,
            "cleanup_authority": prepared.cleanup_authority,
            "cleanup_authority_id": prepared.cleanup_authority_id or None,
        }
        if any(record.get(field) != value for field, value in immutable_identity.items()):
            raise CheckExecutionError("check execution identity changed before recovery finalization")
        if record.get("lifecycle") not in {"blocked", "failed_verified"}:
            raise CheckExecutionError("check execution recovery state is invalid")
        _verify_recovery_authority(record)
        if record.get("lifecycle") == "blocked":
            expected_stage = {
                "status": "prepared",
                "identity_digest": _canonical_digest(
                    {field: record.get(field) for field in _OWNER_CAS_FIELDS}
                ),
            }
            if record.get("recovery_stage") != expected_stage:
                raise CheckExecutionError("check execution recovery was not prepared")
            cleanup = _read_execution(repository / str(record["cleanup_ref"]))
            if cleanup.get("status") != "verified_absent" or cleanup.get("verified_absent") is not True:
                raise CheckExecutionError("check execution recovery cleanup proof is missing")
            record["lifecycle"] = "failed_verified"
            record["recovery_stage"] = {**expected_stage, "status": "committed"}
            atomic_write_json(record_path, record)
        artifact = _read_execution(repository / str(record["artifact_ref"]))
    completed = BoundedCommandResult(int(artifact["exit_code"]), "", "", bool(artifact.get("timed_out")), bool(artifact.get("residue_unverifiable")), artifact.get("start_error"))
    return _shared_result(record, completed, int(artifact["duration_ms"]))


def _shared_result(
    record: Mapping[str, Any], completed: BoundedCommandResult, duration_ms: int
) -> SharedCheckResult:
    return SharedCheckResult(
        str(record["execution_id"]), str(record["command_digest"]),
        str(record["source_snapshot_digest"]), str(record["execution_policy_digest"]),
        float(record["timeout_seconds"]), int(record["output_cap_bytes"]),
        int(record["owner_generation"]), str(record["lifecycle"]),
        str(record["artifact_ref"]), str(record["cleanup_ref"]), str(record["cleanup_id"]),
        record.get("process_root"), record.get("process_group"),
        record.get("process_start_identity"), str(record["cleanup_authority"]),
        str(record["cleanup_authority_id"] or ""), completed, duration_ms,
    )


def _bounded_pipe_reader(
    stream: Any,
    output: bytearray,
    limit: int,
    capture_open: threading.Event,
) -> None:
    """Drain one inherited pipe without allowing post-return buffer mutation."""

    try:
        while chunk := stream.read(8192):
            if not capture_open.is_set():
                return
            if len(output) < limit:
                output.extend(chunk[: limit - len(output)])
    except (OSError, ValueError):
        # The owner closes the pipe during forced tree cleanup.
        return


class _WindowsJob:
    """One kill-on-close Windows Job Object, when the platform can create it."""

    def __init__(self, handle: Any, close_handle: Any, authority_id: str = "") -> None:
        self.handle = handle
        self._close_handle = close_handle
        self.authority_id = authority_id
        self.closed = False

    def close(self) -> bool:
        if self.closed:
            return True
        self.closed = True
        return bool(self._close_handle(self.handle))


def _create_windows_job(process: subprocess.Popen[bytes], authority_id: str) -> _WindowsJob | None:
    """Attach the process to an exact kill-on-close owned tree on Windows."""

    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        class IoCounters(ctypes.Structure):
            _fields_ = [("read_operation_count", ctypes.c_ulonglong), ("write_operation_count", ctypes.c_ulonglong), ("other_operation_count", ctypes.c_ulonglong), ("read_transfer_count", ctypes.c_ulonglong), ("write_transfer_count", ctypes.c_ulonglong), ("other_transfer_count", ctypes.c_ulonglong)]

        class BasicLimitInformation(ctypes.Structure):
            _fields_ = [("per_process_user_time_limit", ctypes.c_longlong), ("per_job_user_time_limit", ctypes.c_longlong), ("limit_flags", wintypes.DWORD), ("minimum_working_set_size", ctypes.c_size_t), ("maximum_working_set_size", ctypes.c_size_t), ("active_process_limit", wintypes.DWORD), ("affinity", ctypes.c_size_t), ("priority_class", wintypes.DWORD), ("scheduling_class", wintypes.DWORD)]

        class ExtendedLimitInformation(ctypes.Structure):
            _fields_ = [("basic_limit_information", BasicLimitInformation), ("io_info", IoCounters), ("process_memory_limit", ctypes.c_size_t), ("job_memory_limit", ctypes.c_size_t), ("peak_process_memory_used", ctypes.c_size_t), ("peak_job_memory_used", ctypes.c_size_t)]

        create = kernel32.CreateJobObjectW
        create.argtypes = (wintypes.LPVOID, wintypes.LPCWSTR)
        create.restype = wintypes.HANDLE
        close = kernel32.CloseHandle
        close.argtypes = (wintypes.HANDLE,)
        close.restype = wintypes.BOOL
        assign = kernel32.AssignProcessToJobObject
        assign.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
        assign.restype = wintypes.BOOL
        set_information = kernel32.SetInformationJobObject
        set_information.argtypes = (wintypes.HANDLE, wintypes.INT, wintypes.LPVOID, wintypes.DWORD)
        set_information.restype = wintypes.BOOL

        handle = create(None, authority_id)
        if not handle:
            return None
        information = ExtendedLimitInformation()
        information.basic_limit_information.limit_flags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not set_information(handle, 9, ctypes.byref(information), ctypes.sizeof(information)):
            close(handle)
            return None
        process_handle = wintypes.HANDLE(process._handle)  # type: ignore[attr-defined]
        if not assign(handle, process_handle):
            close(handle)
            return None
        return _WindowsJob(handle, close, authority_id)
    except (AttributeError, OSError):
        return None


def _resume_windows_process(process: subprocess.Popen[bytes]) -> bool:
    """Resume only a child already assigned to this runner's Job Object."""

    if os.name != "nt":
        return True
    try:
        import ctypes
        from ctypes import wintypes

        resume = ctypes.WinDLL("ntdll", use_last_error=True).NtResumeProcess
        resume.argtypes = (wintypes.HANDLE,)
        resume.restype = ctypes.c_long
        return resume(wintypes.HANDLE(process._handle)) == 0  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        return False


def _process_group_is_live(process_id: int) -> bool:
    try:
        os.killpg(process_id, 0)
    except ProcessLookupError:
        return False
    return True


def _windows_job_is_settled(authority_id: str) -> bool:
    """Prove a persisted named Job has no remaining owned process on Windows."""

    if os.name != "nt":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        open_job = kernel32.OpenJobObjectW
        open_job.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR)
        open_job.restype = wintypes.HANDLE
        close = kernel32.CloseHandle
        close.argtypes = (wintypes.HANDLE,)
        close.restype = wintypes.BOOL
        query = kernel32.QueryInformationJobObject
        query.argtypes = (wintypes.HANDLE, wintypes.INT, wintypes.LPVOID, wintypes.DWORD, wintypes.LPVOID)
        query.restype = wintypes.BOOL

        handle = open_job(0x0004, False, authority_id)
        if not handle:
            return ctypes.get_last_error() == 2

        class Accounting(ctypes.Structure):
            _fields_ = [
                ("total_user_time", ctypes.c_longlong), ("total_kernel_time", ctypes.c_longlong),
                ("this_period_total_user_time", ctypes.c_longlong), ("this_period_total_kernel_time", ctypes.c_longlong),
                ("total_page_fault_count", wintypes.DWORD), ("total_processes", wintypes.DWORD),
                ("active_processes", wintypes.DWORD), ("total_terminated_processes", wintypes.DWORD),
            ]

        accounting = Accounting()
        try:
            return bool(query(handle, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None)) and accounting.active_processes == 0
        finally:
            close(handle)
    except (AttributeError, OSError):
        return False


def _terminate_process_tree(
    process: subprocess.Popen[bytes], windows_job: _WindowsJob | None = None
) -> bool:
    """Terminate the owned tree and report whether complete cleanup is unproven."""

    try:
        if os.name == "nt":
            if windows_job is not None:
                return not windows_job.close()
            completed = subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=False,
                capture_output=True,
                timeout=10,
            )
            if completed.returncode != 0:
                return True
        else:
            if not _process_group_is_live(process.pid):
                return False
            os.killpg(process.pid, signal.SIGTERM)
            deadline = time.monotonic() + 2
            while _process_group_is_live(process.pid) and time.monotonic() < deadline:
                time.sleep(0.05)
            if _process_group_is_live(process.pid):
                os.killpg(process.pid, signal.SIGKILL)
                deadline = time.monotonic() + 2
                while _process_group_is_live(process.pid) and time.monotonic() < deadline:
                    time.sleep(0.05)
            return _process_group_is_live(process.pid)
    except (OSError, subprocess.SubprocessError):
        return True
    return process.poll() is None


def run_bounded_command(
    arguments: list[str],
    *,
    cwd: Path,
    timeout_seconds: float,
    output_cap_bytes: int = CHECK_OUTPUT_CAP_BYTES,
    on_started: Callable[[Mapping[str, Any]], None] | None = None,
    windows_job_name: str | None = None,
) -> BoundedCommandResult:
    """Run a direct command with bounded capture and an owned process tree."""

    _execution_policy(timeout_seconds, output_cap_bytes)
    creationflags = 0
    gate_read: int | None = None
    gate_write: int | None = None
    launched_arguments = arguments
    pass_fds: tuple[int, ...] = ()
    if os.name == "nt":
        creationflags = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | 0x00000004  # CREATE_SUSPENDED is part of the Win32 process contract.
        )
    else:
        gate_read, gate_write = os.pipe()
        os.set_inheritable(gate_read, True)
        launched_arguments = [
            sys.executable,
            "-c",
            _POSIX_GATE_LAUNCHER,
            str(gate_read),
            *arguments,
        ]
        pass_fds = (gate_read,)
    try:
        process_options: dict[str, Any] = {
            "cwd": cwd,
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "creationflags": creationflags,
            "start_new_session": os.name != "nt",
        }
        if pass_fds:
            process_options["pass_fds"] = pass_fds
        process = subprocess.Popen(
            launched_arguments,
            **process_options,
        )
    except OSError as error:
        if gate_read is not None:
            os.close(gate_read)
        if gate_write is not None:
            os.close(gate_write)
        return BoundedCommandResult(127, "", str(error), False, False, str(error))
    if gate_read is not None:
        os.close(gate_read)
        gate_read = None

    windows_job = _create_windows_job(process, windows_job_name or f"agent-graph-{process.pid}")
    if os.name == "nt" and windows_job is None:
        cleanup_unverifiable = _terminate_process_tree(process, windows_job)
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                stream.close()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            cleanup_unverifiable = _terminate_process_tree(process, windows_job) or cleanup_unverifiable
        return BoundedCommandResult(
            127,
            "",
            "Windows owned Job Object setup failed before command execution",
            False,
            True,
            "windows_job_setup_failed",
        )
    if on_started is not None:
        try:
            on_started(
                {
                    "process_root": process.pid,
                    "process_group": process.pid if os.name == "posix" else None,
                    "process_start_identity": _process_start_identity(process.pid),
                    "cleanup_authority": "process_group" if os.name == "posix" else "job_object",
                    "cleanup_authority_id": None if os.name == "posix" else windows_job.authority_id,
                }
            )
        except BaseException:
            _terminate_process_tree(process, windows_job)
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                _terminate_process_tree(process, windows_job)
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
            if gate_write is not None:
                os.close(gate_write)
            raise
    if os.name == "nt" and not _resume_windows_process(process):
        cleanup_unverifiable = _terminate_process_tree(process, windows_job)
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                stream.close()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            cleanup_unverifiable = _terminate_process_tree(process, windows_job) or cleanup_unverifiable
        return BoundedCommandResult(
            127,
            "",
            "Windows suspended process could not be resumed after authority publication",
            False,
            True,
            "windows_process_resume_failed",
        )
    if gate_write is not None:
        try:
            os.write(gate_write, b"1")
        except OSError as error:
            cleanup_unverifiable = _terminate_process_tree(process, windows_job)
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                cleanup_unverifiable = _terminate_process_tree(process, windows_job) or cleanup_unverifiable
            return BoundedCommandResult(
                127,
                "",
                "durable process gate could not be released",
                False,
                cleanup_unverifiable,
                f"gate_release_failed:{error.__class__.__name__}",
            )
        finally:
            os.close(gate_write)
            gate_write = None
    stdout = bytearray()
    stderr = bytearray()
    capture_open = threading.Event()
    capture_open.set()
    readers = [
        threading.Thread(target=_bounded_pipe_reader, args=(process.stdout, stdout, output_cap_bytes, capture_open), daemon=True),
        threading.Thread(target=_bounded_pipe_reader, args=(process.stderr, stderr, output_cap_bytes, capture_open), daemon=True),
    ]
    for reader in readers:
        reader.start()
    timed_out = False
    residue_unverifiable = os.name == "nt" and windows_job is None
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        residue_unverifiable = _terminate_process_tree(process, windows_job)
    except BaseException:
        _terminate_process_tree(process, windows_job)
        raise
    finally:
        if not timed_out:
            if os.name == "nt":
                # Closing the owned Job Object kills every remaining descendant even
                # after its root has already exited.  Without that binding, taskkill
                # cannot prove a vanished root had no surviving children.
                residue_unverifiable = _terminate_process_tree(process, windows_job) or residue_unverifiable
            elif _process_group_is_live(process.pid):
                residue_unverifiable = _terminate_process_tree(process) or residue_unverifiable
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            residue_unverifiable = _terminate_process_tree(process, windows_job) or residue_unverifiable
        capture_open.clear()
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    residue_unverifiable = True
        for reader in readers:
            reader.join(timeout=0.5)
            if reader.is_alive():
                residue_unverifiable = True
    if process.poll() is None:
        residue_unverifiable = True
    exit_code = 124 if timed_out else int(process.returncode or 0)
    if residue_unverifiable and exit_code == 0:
        exit_code = 125
    return BoundedCommandResult(
        exit_code,
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
        timed_out,
        residue_unverifiable,
        None,
    )


class CliValidationError(ValueError):
    """Reports unsafe CLI input or an invalid repository artifact."""


def _validate_schema(value: Any, schema_name: str, context: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise CliValidationError(f"{context} must be one JSON object")
    schema = load_json_object(REFERENCES_DIRECTORY / schema_name, f"{context} schema")
    try:
        Draft202012Validator(schema).validate(value)
    except ValidationError as error:
        location = ".".join(str(item) for item in error.absolute_path)
        suffix = f" at {location}" if location else ""
        raise CliValidationError(f"invalid {context}{suffix}: {error.message}") from error
    return json.loads(json.dumps(value))


def validate_process_decision(value: Any) -> dict[str, Any]:
    """Validate one bounded decision and its complete mode revision chain."""

    decision = _validate_schema(value, "process-decision.schema.json", "process decision")
    amendments = decision["amendments"]
    if decision["revision"] != len(amendments) + 1:
        raise CliValidationError(
            "process decision revision must equal its initial revision plus amendments"
        )

    expected_mode = decision["initial_mode"]
    for index, amendment in enumerate(amendments, start=1):
        if amendment["from_revision"] != index or amendment["to_revision"] != index + 1:
            raise CliValidationError("process decision amendments must form a contiguous revision chain")
        if amendment["from_mode"] != expected_mode:
            raise CliValidationError("process decision amendment from_mode does not match prior evidence")
        expected_mode = amendment["to_mode"]
    if decision["mode"] != expected_mode:
        raise CliValidationError("process decision mode changed without a matching amendment")
    if amendments and decision["selected_check"] != amendments[-1]["replacement_check"]:
        raise CliValidationError("process decision selected check does not match its latest amendment")

    for question in decision["material_questions"]:
        safe_default = question["safe_default_selected"]
        if safe_default != (question["provenance"] == "safe_default"):
            raise CliValidationError(
                "material question safe-default selection does not match its provenance"
            )
    return decision


def validate_capability_receipt(value: Any) -> dict[str, Any]:
    """Validate complete canonical capability truth and explicit degradation."""

    receipt = _validate_schema(
        value, "capability-receipt.schema.json", "capability receipt"
    )
    missing = {
        name
        for name, capability in receipt["capabilities"].items()
        if capability["status"] != "supported"
    }
    declared_missing = set(receipt["missing_capabilities"])
    if missing != declared_missing:
        raise CliValidationError(
            "capability receipt missing_capabilities must exactly match non-supported declarations"
        )

    requested_missing = set(receipt["requested_capabilities"]) & missing
    degradation = receipt["degradation"]
    degraded_missing = set(degradation["missing_capabilities"])
    if requested_missing != degraded_missing:
        raise CliValidationError(
            "capability receipt degradation must name every requested missing capability"
        )
    if requested_missing and degradation["outcome"] == "none":
        raise CliValidationError(
            "capability receipt must downgrade or block an operation with missing requirements"
        )
    if not requested_missing and degradation["outcome"] != "none":
        raise CliValidationError(
            "capability receipt cannot degrade an operation whose requested capabilities are supported"
        )
    if set(receipt["capabilities"]) != CAPABILITY_NAMES:
        raise CliValidationError("capability receipt must declare the complete canonical capability set")
    return receipt


def require_identifier(value: str, context: str) -> str:
    if not isinstance(value, str) or not TASK_ID_PATTERN.fullmatch(value):
        raise CliValidationError(f"{context} must be a safe identifier without path separators")
    return value


def repository_relative_path(repository: Path, value: str | Path, context: str) -> tuple[Path, str]:
    text = value.as_posix() if isinstance(value, Path) else value
    try:
        normalized = normalize_repo_path(text, context)
    except GraphValidationError as error:
        raise CliValidationError(str(error)) from error
    if normalized.endswith("/"):
        raise CliValidationError(f"{context} must name a file")
    resolved = (repository / normalized).resolve()
    try:
        resolved.relative_to(repository.resolve())
    except ValueError as error:
        raise CliValidationError(f"{context} must stay inside the repository") from error
    return resolved, normalized


def load_json_object(path: Path, context: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise CliValidationError(f"{context} does not exist: {path}") from error
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CliValidationError(f"cannot read {context} {path}: {error}") from error
    if not isinstance(value, dict):
        raise CliValidationError(f"{context} must contain one JSON object")
    return value


def direct_command_arguments(command: str) -> list[str]:
    """Parse one direct executable and reject shell composition on every OS."""

    if not isinstance(command, str) or not command.strip():
        raise CliValidationError("check command must be a non-empty string")
    try:
        lexer = shlex.shlex(
            command,
            posix=os.name != "nt",
            punctuation_chars="|&;<>",
        )
        lexer.whitespace_split = True
        arguments = list(lexer)
    except ValueError as error:
        raise CliValidationError(f"check command has invalid quoting: {error}") from error
    if not arguments:
        raise CliValidationError("check command is empty")
    operator = next(
        (
            token
            for token in arguments
            if token and all(character in SHELL_OPERATOR_CHARACTERS for character in token)
        ),
        None,
    )
    if operator is not None:
        raise CliValidationError(
            f"check uses shell operator {operator!r}; move composition into a reviewed script"
        )
    return arguments


def canonical_receipt_id(receipt: Mapping[str, Any]) -> str:
    serialized = json.dumps(receipt, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return "receipt-" + hashlib.sha256(serialized).hexdigest()


def process_exists(process_id: str) -> bool:
    if not process_id.isdigit():
        return False
    if os.name == "nt":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {process_id}", "/FO", "CSV", "/NH"],
            check=False,
            capture_output=True,
            text=True,
        )
        return result.returncode == 0 and f'"{process_id}"' in result.stdout
    try:
        os.kill(int(process_id), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def cleanup_target_exists(repository: Path, kind: str, target: str | Mapping[str, Any]) -> bool:
    if kind not in CLEANUP_KINDS:
        raise CliValidationError(f"cleanup kind must be one of: {', '.join(sorted(CLEANUP_KINDS))}")
    if kind == "process":
        if isinstance(target, Mapping):
            if set(target) != {"kind", "root_pid"} or target.get("kind") != "process":
                raise CliValidationError("process cleanup target must contain only kind and root_pid")
            process_id = target.get("root_pid")
            if not isinstance(process_id, int) or isinstance(process_id, bool) or process_id < 1:
                raise CliValidationError("process cleanup target root_pid must be a positive integer")
            return process_exists(str(process_id))
        if not target.isdigit():
            raise CliValidationError("legacy process cleanup target must be a PID")
        return process_exists(target)
    if not isinstance(target, str):
        raise CliValidationError("cleanup target must be a string outside process cleanup")
    if kind == "branch":
        result = subprocess.run(
            ["git", "-C", str(repository), "show-ref", "--verify", "--quiet", f"refs/heads/{target}"],
            check=False,
        )
        return result.returncode == 0
    if kind in {"worktree", "temp_path"}:
        target_path = Path(target)
        if not target_path.is_absolute():
            target_path = repository / target_path
        if target_path.exists():
            return True
        if kind == "temp_path":
            return False
        result = subprocess.run(
            ["git", "-C", str(repository), "worktree", "list", "--porcelain"],
            check=False,
            capture_output=True,
            text=True,
        )
        registered = {
            Path(line.removeprefix("worktree ")).resolve()
            for line in result.stdout.splitlines()
            if line.startswith("worktree ")
        }
        return target_path.resolve() in registered
    return False
