import hashlib
import importlib.util
import io
import stat
import sys
import tarfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).parents[2]
MODULE_PATH = ROOT / "scripts" / "install_pipelock.py"
SPEC = importlib.util.spec_from_file_location("install_pipelock", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
install_pipelock = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = install_pipelock
SPEC.loader.exec_module(install_pipelock)


class ReleaseSelectionBehavior(unittest.TestCase):
    def test_normalizes_supported_architectures(self) -> None:
        self.assertEqual(install_pipelock.normalized_platform("Linux", "x86_64"), ("linux", "amd64"))
        self.assertEqual(install_pipelock.normalized_platform("Darwin", "arm64"), ("darwin", "arm64"))
        self.assertEqual(install_pipelock.normalized_platform("Windows", "AMD64"), ("windows", "amd64"))

    def test_rejects_an_unsupported_target(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported Pipelock target"):
            install_pipelock.select_asset("plan9", "mips")


class ChecksumVerificationBehavior(unittest.TestCase):
    def test_accepts_the_expected_digest(self) -> None:
        payload = b"verified release"
        install_pipelock.verify_checksum(payload, hashlib.sha256(payload).hexdigest())

    def test_rejects_a_mismatched_digest(self) -> None:
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            install_pipelock.verify_checksum(b"tampered", "0" * 64)


class ArchiveExtractionBehavior(unittest.TestCase):
    def test_reads_only_the_named_regular_file_from_tar(self) -> None:
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w:gz") as archive:
            binary = b"pipelock binary"
            item = tarfile.TarInfo("release/pipelock")
            item.size = len(binary)
            archive.addfile(item, io.BytesIO(binary))
            link = tarfile.TarInfo("pipelock-link")
            link.type = tarfile.SYMTYPE
            link.linkname = "/etc/passwd"
            archive.addfile(link)

        extracted = install_pipelock.extract_binary(stream.getvalue(), "release.tar.gz", "pipelock")

        self.assertEqual(extracted, b"pipelock binary")

    def test_reads_the_named_file_from_zip(self) -> None:
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, mode="w") as archive:
            archive.writestr("release/pipelock.exe", b"windows binary")

        extracted = install_pipelock.extract_binary(stream.getvalue(), "release.zip", "pipelock.exe")

        self.assertEqual(extracted, b"windows binary")

    def test_rejects_duplicate_binaries(self) -> None:
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, mode="w") as archive:
            archive.writestr("one/pipelock.exe", b"one")
            archive.writestr("two/pipelock.exe", b"two")

        with self.assertRaisesRegex(ValueError, "exactly one"):
            install_pipelock.extract_binary(stream.getvalue(), "release.zip", "pipelock.exe")

    def test_rejects_a_zip_symlink_disguised_as_the_binary(self) -> None:
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, mode="w") as archive:
            item = zipfile.ZipInfo("pipelock.exe")
            item.create_system = 3
            item.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(item, "/outside/pipelock.exe")

        with self.assertRaisesRegex(ValueError, "exactly one"):
            install_pipelock.extract_binary(stream.getvalue(), "release.zip", "pipelock.exe")


if __name__ == "__main__":
    unittest.main()
