import os
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "key-env-check.sh"


class KeyEnvironmentDetectionBehavior(unittest.TestCase):
    def run_check(
        self,
        home: Path,
        *,
        api_key: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["HOME"] = str(home)
        if api_key is None:
            environment.pop("SCRAPINGDOG_API_KEY", None)
        else:
            environment["SCRAPINGDOG_API_KEY"] = api_key
        return subprocess.run(
            ["bash", str(SCRIPT)],
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_detects_the_current_environment_without_printing_the_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            secret = "current-secret-value"

            result = self.run_check(Path(temporary_directory), api_key=secret)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "current")
        self.assertNotIn(secret, result.stdout + result.stderr)

    def test_detects_an_interactive_shell_environment_without_printing_the_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            home = Path(temporary_directory)
            secret = "interactive-secret-value"
            (home / ".bashrc").write_text(
                f"export SCRAPINGDOG_API_KEY={secret}\n",
                encoding="utf-8",
            )

            result = self.run_check(home)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "interactive")
        self.assertNotIn(secret, result.stdout + result.stderr)

    def test_reports_missing_only_after_both_environments_are_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = self.run_check(Path(temporary_directory))

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.strip(), "missing")


if __name__ == "__main__":
    unittest.main()
