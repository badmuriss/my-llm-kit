#!/usr/bin/env python3
"""Install a pinned Pipelock release after verifying its published checksum."""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import platform
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


VERSION = "3.3.0"
REPOSITORY = "luckyPipewrench/pipelock"


@dataclass(frozen=True)
class ReleaseAsset:
    filename: str
    sha256: str

    @property
    def url(self) -> str:
        return f"https://github.com/{REPOSITORY}/releases/download/v{VERSION}/{self.filename}"


ASSETS = {
    ("linux", "amd64"): ReleaseAsset(
        "pipelock_3.3.0_linux_amd64.tar.gz",
        "cbc03ba3a5cc1400e288f4a2782ffd59ca162f5f0120d972ab82717ad5519dfc",
    ),
    ("linux", "arm64"): ReleaseAsset(
        "pipelock_3.3.0_linux_arm64.tar.gz",
        "d682ffb0f81138099a14f8c991880688ea692f80cd114d75010eb9a622e1fbf6",
    ),
    ("darwin", "amd64"): ReleaseAsset(
        "pipelock_3.3.0_darwin_amd64.tar.gz",
        "63483c0ada75d83f0efecd858f3b237e6d9586d021f169d3b203708a9c59c844",
    ),
    ("darwin", "arm64"): ReleaseAsset(
        "pipelock_3.3.0_darwin_arm64.tar.gz",
        "f0148f89a0a6a626a5d6cbbf3f546a124b4c71a1d7e00cf987ffb016f43c5139",
    ),
    ("windows", "amd64"): ReleaseAsset(
        "pipelock_3.3.0_windows_amd64.zip",
        "e9f690b88065c8d71cde2c05bce1719aedd6125acce581f6b686bc39204a060e",
    ),
    ("windows", "arm64"): ReleaseAsset(
        "pipelock_3.3.0_windows_arm64.zip",
        "c65cd37f8e4d30afbdb4d3828d7c9ea3444ac7f49040e5a01d3928bb4db86d35",
    ),
}


def normalized_platform(system: str, machine: str) -> tuple[str, str]:
    operating_system = system.lower()
    if operating_system.startswith("msys") or operating_system.startswith("cygwin"):
        operating_system = "windows"
    architecture = machine.lower()
    architecture = {
        "x86_64": "amd64",
        "amd64": "amd64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }.get(architecture, architecture)
    return operating_system, architecture


def select_asset(system: str, machine: str) -> ReleaseAsset:
    target = normalized_platform(system, machine)
    try:
        return ASSETS[target]
    except KeyError as error:
        raise ValueError(f"unsupported Pipelock target: {target[0]}/{target[1]}") from error


def verify_checksum(payload: bytes, expected: str) -> None:
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        raise ValueError(f"Pipelock checksum mismatch: got {actual}, expected {expected}")


def extract_binary(payload: bytes, filename: str, executable_name: str) -> bytes:
    candidates: list[bytes] = []
    if filename.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            for item in archive.infolist():
                path = PurePosixPath(item.filename)
                unix_mode = item.external_attr >> 16
                if item.is_dir() or stat.S_ISLNK(unix_mode) or path.name != executable_name:
                    continue
                candidates.append(archive.read(item))
    else:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
            for item in archive.getmembers():
                path = PurePosixPath(item.name)
                if not item.isfile() or path.name != executable_name:
                    continue
                stream = archive.extractfile(item)
                if stream is None:
                    raise ValueError("Pipelock archive contains an unreadable binary")
                candidates.append(stream.read())
    if len(candidates) != 1 or not candidates[0]:
        raise ValueError(f"Pipelock archive must contain exactly one {executable_name} binary")
    return candidates[0]


def installed_version_matches(target: Path) -> bool:
    if not target.is_file():
        return False
    try:
        result = subprocess.run(
            [str(target), "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    output = f"{result.stdout}\n{result.stderr}"
    return result.returncode == 0 and VERSION in output


def download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "my-llm-kit-installer"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def install(target: Path, system: str, machine: str, dry_run: bool) -> None:
    asset = select_asset(system, machine)
    if installed_version_matches(target):
        print(f"Pipelock v{VERSION} already installed at {target}")
        return
    if dry_run:
        print(f"[dry-run] verify {asset.url} and install Pipelock v{VERSION} at {target}")
        return

    payload = download(asset.url)
    verify_checksum(payload, asset.sha256)
    executable_name = "pipelock.exe" if normalized_platform(system, machine)[0] == "windows" else "pipelock"
    binary = extract_binary(payload, asset.filename, executable_name)

    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".pipelock-", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(binary)
            stream.flush()
            os.fsync(stream.fileno())
        executable_mode = (
            stat.S_IRUSR
            | stat.S_IWUSR
            | stat.S_IXUSR
            | stat.S_IRGRP
            | stat.S_IXGRP
            | stat.S_IROTH
            | stat.S_IXOTH
        )
        temporary.chmod(executable_mode)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Installed Pipelock v{VERSION} at {target}")


def default_target(system: str) -> Path:
    suffix = ".exe" if system.lower() == "windows" else ""
    return Path.home() / ".local" / "bin" / f"pipelock{suffix}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--target", type=Path)
    args = parser.parse_args()
    system = platform.system()
    target = args.target or default_target(system)
    try:
        install(target, system, platform.machine(), args.dry_run)
    except (OSError, ValueError, tarfile.TarError, zipfile.BadZipFile) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
