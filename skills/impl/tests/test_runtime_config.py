import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "runtime_config.py"
CURRENT_OS = "windows" if os.name == "nt" else "macos" if sys.platform == "darwin" else "linux"


class RuntimeConfigurationBehavior(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary_directory.name)
        self.project = self.directory / "project with spaces"
        self.project.mkdir()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def run_runtime(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment.pop("IMPL_PROJECT_DIR", None)
        environment.pop("IMPL_OS", None)
        return subprocess.run(
            [sys.executable, str(SCRIPT), *arguments],
            cwd=self.directory,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_resolves_project_and_os_from_dotenv(self) -> None:
        (self.directory / ".env").write_text(
            f'IMPL_OS={CURRENT_OS}\nIMPL_PROJECT_DIR="{self.project}"\n',
            encoding="utf-8",
        )

        result = self.run_runtime()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(self.project), result.stdout)
        self.assertIn(f'"operating_system": "{CURRENT_OS}"', result.stdout)

    def test_resolves_relative_project_from_env_file_directory(self) -> None:
        (self.directory / ".env").write_text(
            f"IMPL_OS={CURRENT_OS}\nIMPL_PROJECT_DIR=project with spaces\n",
            encoding="utf-8",
        )

        result = self.run_runtime()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(self.project), result.stdout)

    def test_rejects_an_os_that_disagrees_with_the_machine(self) -> None:
        different_os = "windows" if CURRENT_OS != "windows" else "linux"
        (self.directory / ".env").write_text(
            f"IMPL_OS={different_os}\nIMPL_PROJECT_DIR={self.project}\n",
            encoding="utf-8",
        )

        result = self.run_runtime()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match detected OS", result.stderr)

    def test_cli_project_overrides_dotenv(self) -> None:
        other_project = self.directory / "other"
        other_project.mkdir()
        (self.directory / ".env").write_text(
            f"IMPL_OS={CURRENT_OS}\nIMPL_PROJECT_DIR={self.project}\n",
            encoding="utf-8",
        )

        result = self.run_runtime("--repo", str(other_project))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(other_project), result.stdout)


if __name__ == "__main__":
    unittest.main()
