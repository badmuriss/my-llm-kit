#!/usr/bin/env python3
"""Create and verify the immutable control runtime owned by an Agent Graph run."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping


CONTROL_RUNTIME_PROTOCOL_VERSION = 1
CONTROL_RUNTIME_DIRECTORY = "control-runtime"
CONTROL_RUNTIME_REF_FILE = "control-runtime-ref.json"
SNAPSHOT_METADATA_FILE = "control-runtime-metadata.json"
ENTRYPOINT_RELATIVE_PATH = Path("scripts") / "agent_graph.py"
ROUTING_POLICY_SEED_SOURCE_PATH = Path("impl") / "references" / "routing-policy.seed.json"
ROUTING_POLICY_SEED_SNAPSHOT_PATH = Path("references") / "routing-policy.seed.json"


class ControlRuntimeError(RuntimeError):
    """Reports a missing, divergent, or unsafe pinned control runtime."""

    code = "control_runtime_invalid"


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        if hasattr(os, "O_DIRECTORY"):
            directory = os.open(path.parent, os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _snapshot_files(source_root: Path) -> list[tuple[Path, Path]]:
    files: list[tuple[Path, Path]] = []
    scripts = source_root / "scripts"
    references = source_root / "references"
    if not (scripts / "agent_graph.py").is_file():
        raise ControlRuntimeError(f"control runtime entrypoint is missing: {scripts / 'agent_graph.py'}")
    for source in sorted(scripts.glob("*.py")):
        files.append((source, source.relative_to(source_root)))
    drivers = scripts / "drivers"
    for source in sorted(drivers.glob("*.py")):
        files.append((source, source.relative_to(source_root)))
    for source in sorted(references.glob("*.json")):
        files.append((source, source.relative_to(source_root)))
    policy_source = source_root.parent / ROUTING_POLICY_SEED_SOURCE_PATH
    if not policy_source.is_file():
        raise ControlRuntimeError(
            f"control runtime routing policy is missing: {policy_source}"
        )
    files.append((policy_source, ROUTING_POLICY_SEED_SNAPSHOT_PATH))
    return files


def _directory_digest(directory: Path) -> tuple[str, int, int]:
    digest = hashlib.sha256()
    file_count = 0
    byte_count = 0
    try:
        paths = sorted(directory.rglob("*"))
    except OSError as error:
        raise ControlRuntimeError(f"cannot enumerate control runtime {directory}: {error}") from error
    for path in paths:
        if path.is_symlink():
            raise ControlRuntimeError(f"control runtime contains a symbolic link: {path}")
        relative = path.relative_to(directory).as_posix().encode("utf-8")
        if path.is_dir():
            digest.update(b"D")
            digest.update(len(relative).to_bytes(8, "big"))
            digest.update(relative)
            continue
        if not path.is_file():
            raise ControlRuntimeError(f"control runtime contains an unsupported entry: {path}")
        try:
            content = path.read_bytes()
        except OSError as error:
            raise ControlRuntimeError(f"cannot read control runtime file {path}: {error}") from error
        digest.update(b"F")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
        file_count += 1
        byte_count += len(content)
    return f"sha256:{digest.hexdigest()}", file_count, byte_count


def _make_read_only(directory: Path) -> None:
    for path in sorted(directory.rglob("*"), reverse=True):
        mode = stat.S_IMODE(path.stat().st_mode)
        if path.is_dir():
            path.chmod(mode & ~0o222)
        else:
            path.chmod(mode & ~0o222)
    directory.chmod(stat.S_IMODE(directory.stat().st_mode) & ~0o222)


def create_control_runtime(
    *,
    source_root: Path,
    run_directory: Path,
    source_revision: str,
) -> dict[str, Any]:
    """Atomically materialize a minimal runtime before the run journal exists."""

    source_root = source_root.resolve()
    run_directory = run_directory.resolve()
    destination = run_directory / CONTROL_RUNTIME_DIRECTORY
    reference_path = run_directory / CONTROL_RUNTIME_REF_FILE
    if destination.exists() or reference_path.exists():
        raise ControlRuntimeError(f"control runtime already exists for run: {run_directory}")
    if (run_directory / "events.jsonl").exists():
        raise ControlRuntimeError("control runtime must be pinned before the journal is created")
    staging_root = Path(tempfile.mkdtemp(prefix=".control-runtime-", dir=run_directory))
    staging = staging_root / CONTROL_RUNTIME_DIRECTORY
    staging.mkdir()
    try:
        files = _snapshot_files(source_root)
        for source, relative in files:
            destination_file = staging / relative
            destination_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination_file)
        metadata = {
            "protocol_version": CONTROL_RUNTIME_PROTOCOL_VERSION,
            "source_revision": source_revision,
        }
        _atomic_write_json(staging / SNAPSHOT_METADATA_FILE, metadata)
        directory_digest, file_count, byte_count = _directory_digest(staging)
        os.replace(staging, destination)
        if hasattr(os, "O_DIRECTORY"):
            directory_descriptor = os.open(run_directory, os.O_DIRECTORY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
        staging_root.rmdir()
        _make_read_only(destination)
        entrypoint = (destination / ENTRYPOINT_RELATIVE_PATH).resolve()
        reference = {
            "schema_version": 1,
            "entrypoint": str(entrypoint),
            "directory": str(destination.resolve()),
            "directory_digest": directory_digest,
            "protocol_version": CONTROL_RUNTIME_PROTOCOL_VERSION,
            "source_revision": source_revision,
            "creation_receipt": {
                "method": "atomic-directory-rename",
                "created_at": _now(),
                "file_count": file_count,
                "byte_count": byte_count,
            },
        }
        _atomic_write_json(reference_path, reference)
        return reference
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        if staging_root.exists():
            shutil.rmtree(staging_root, ignore_errors=True)
        if destination.exists() and not reference_path.exists():
            _remove_tree(destination)
        raise


def _required_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ControlRuntimeError(f"control runtime {field} must be a non-empty string")
    return value


def validate_control_runtime_ref(value: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version",
        "entrypoint",
        "directory",
        "directory_digest",
        "protocol_version",
        "source_revision",
        "creation_receipt",
    }
    if not isinstance(value, Mapping):
        raise ControlRuntimeError("control runtime reference must be an object")
    unknown = sorted(set(value) - required)
    missing = sorted(required - set(value))
    if unknown or missing:
        details = []
        if missing:
            details.append(f"missing {', '.join(missing)}")
        if unknown:
            details.append(f"unknown {', '.join(unknown)}")
        raise ControlRuntimeError(f"invalid control runtime reference: {'; '.join(details)}")
    if value["schema_version"] != 1:
        raise ControlRuntimeError("control runtime schema version is unsupported")
    entrypoint = Path(_required_string(value["entrypoint"], "entrypoint"))
    directory = Path(_required_string(value["directory"], "directory"))
    if not entrypoint.is_absolute() or not directory.is_absolute():
        raise ControlRuntimeError("control runtime paths must be absolute")
    digest = _required_string(value["directory_digest"], "directory_digest")
    if not digest.startswith("sha256:") or len(digest) != 71:
        raise ControlRuntimeError("control runtime directory_digest must be sha256")
    if value["protocol_version"] != CONTROL_RUNTIME_PROTOCOL_VERSION:
        raise ControlRuntimeError("control runtime protocol version is unsupported")
    _required_string(value["source_revision"], "source_revision")
    receipt = value["creation_receipt"]
    if not isinstance(receipt, Mapping) or receipt.get("method") != "atomic-directory-rename":
        raise ControlRuntimeError("control runtime creation receipt is invalid")
    return json.loads(json.dumps(dict(value), sort_keys=True))


def verify_control_runtime(value: Mapping[str, Any]) -> dict[str, Any]:
    """Fail closed unless every durable runtime identity still matches its snapshot."""

    reference = validate_control_runtime_ref(value)
    directory = Path(reference["directory"])
    entrypoint = Path(reference["entrypoint"])
    if not directory.is_dir():
        raise ControlRuntimeError(f"control runtime directory is missing: {directory}")
    expected_entrypoint = directory / ENTRYPOINT_RELATIVE_PATH
    if entrypoint != expected_entrypoint or not entrypoint.is_file():
        raise ControlRuntimeError("control runtime entrypoint diverged from its pinned location")
    metadata_path = directory / SNAPSHOT_METADATA_FILE
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ControlRuntimeError(f"control runtime metadata is unreadable: {error}") from error
    if not isinstance(metadata, Mapping):
        raise ControlRuntimeError("control runtime metadata must be an object")
    if metadata.get("protocol_version") != reference["protocol_version"]:
        raise ControlRuntimeError("control runtime protocol version diverged")
    if metadata.get("source_revision") != reference["source_revision"]:
        raise ControlRuntimeError("control runtime source revision diverged")
    actual_digest, file_count, byte_count = _directory_digest(directory)
    if actual_digest != reference["directory_digest"]:
        raise ControlRuntimeError("control runtime directory digest diverged")
    receipt = reference["creation_receipt"]
    if receipt.get("file_count") != file_count or receipt.get("byte_count") != byte_count:
        raise ControlRuntimeError("control runtime creation receipt diverged")
    return reference


def load_control_runtime_ref(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ControlRuntimeError(f"cannot read control runtime reference {path}: {error}") from error
    if not isinstance(value, Mapping):
        raise ControlRuntimeError("control runtime reference must be an object")
    return validate_control_runtime_ref(value)


def load_run_control_runtime(run_directory: Path) -> dict[str, Any]:
    run_directory = run_directory.resolve()
    reference = load_control_runtime_ref(run_directory / CONTROL_RUNTIME_REF_FILE)
    expected_directory = (run_directory / CONTROL_RUNTIME_DIRECTORY).resolve()
    if Path(reference["directory"]) != expected_directory:
        raise ControlRuntimeError("control runtime directory does not belong to its run")
    return reference


def _remove_tree(directory: Path) -> None:
    if not directory.exists():
        return
    for path in sorted(directory.rglob("*"), reverse=True):
        try:
            path.chmod(stat.S_IMODE(path.stat().st_mode) | stat.S_IWUSR)
        except OSError:
            pass
    try:
        directory.chmod(stat.S_IMODE(directory.stat().st_mode) | stat.S_IWUSR)
    except OSError:
        pass
    shutil.rmtree(directory)


def release_control_runtime(value: Mapping[str, Any], *, run_terminal: bool) -> None:
    if not run_terminal:
        raise ControlRuntimeError("an active run cannot release its control runtime")
    reference = verify_control_runtime(value)
    _remove_tree(Path(reference["directory"]))
