import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[2]
MANIFEST = ROOT / "install-manifest.json"
MANIFEST_READER = ROOT / "scripts" / "read_install_manifest.py"


class SharedManifestBehavior(unittest.TestCase):
    def test_includes_the_reduced_harness_dependencies(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

        self.assertEqual(
            manifest["reduced_install_skills"],
            ["spec", "impl", "grill-me"],
        )

    def test_emits_manifest_rows_for_shell(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(MANIFEST_READER),
                "reduced_install_skills",
                "--manifest",
                str(MANIFEST),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["spec", "impl", "grill-me"])


class PaperSearchPreflightBehavior(unittest.TestCase):
    def test_runs_a_real_query_on_unix(self) -> None:
        setup = (ROOT / "setup.sh").read_text(encoding="utf-8")

        self.assertIn("paper-search-mcp --version", setup)
        self.assertIn("paper-search search 'CodePlan repository-level coding'", setup)
        self.assertIn("web fallback active: ScrapingDog when keyed, then Firecrawl", setup)

    def test_runs_a_real_query_on_windows(self) -> None:
        setup = (ROOT / "setup.ps1").read_text(encoding="utf-8")

        self.assertIn('Invoke-Native "paper-search-mcp" @("--version")', setup)
        self.assertIn('paper-search search "CodePlan repository-level coding"', setup)
        self.assertIn("web fallback active: ScrapingDog when keyed, then Firecrawl", setup)


if __name__ == "__main__":
    unittest.main()
