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
            [
                "spec",
                "impl",
                "grill-me",
                "trim-code-comments",
                "thermo-nuclear-code-quality-review",
            ],
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
        self.assertEqual(
            result.stdout.splitlines(),
            [
                "spec",
                "impl",
                "grill-me",
                "trim-code-comments",
                "thermo-nuclear-code-quality-review",
            ],
        )


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


class ScrapingDogMcpBehavior(unittest.TestCase):
    package_spec = "https://codeload.github.com/badmuriss/Scrapingdog-mcp/tar.gz/8084d8a77b5836f7c0ef7cfbaec5ab12f1fcb741"

    def test_registers_and_preflights_the_server_on_unix(self) -> None:
        setup = (ROOT / "setup.sh").read_text(encoding="utf-8")

        self.assertIn(f'SCRAPINGDOG_MCP_PACKAGE="{self.package_spec}"', setup)
        self.assertIn('npm install --global "$SCRAPINGDOG_MCP_PACKAGE"', setup)
        self.assertIn('npm ci --include=dev --prefix "$(npm root --global)/scrapingdog-mcp"', setup)
        self.assertIn("claude mcp add --scope user scrapingdog -- node", setup)
        self.assertIn("codex mcp add scrapingdog -- node", setup)
        self.assertIn("claude mcp get scrapingdog", setup)
        self.assertIn("codex mcp get scrapingdog", setup)
        self.assertIn('node "$REPO_DIR/scripts/preflight_scrapingdog_mcp.mjs" "$entrypoint"', setup)

    def test_registers_and_preflights_the_server_on_windows(self) -> None:
        setup = (ROOT / "setup.ps1").read_text(encoding="utf-8")

        self.assertIn(f'$ScrapingDogMcpPackage = "{self.package_spec}"', setup)
        self.assertIn('"install", "--global", $ScrapingDogMcpPackage', setup)
        self.assertIn('"ci", "--include=dev", "--prefix", $packageDirectory', setup)
        self.assertIn('"scrapingdog", "--", "node", $entrypoint', setup)
        self.assertIn("mcp get scrapingdog", setup)
        self.assertIn('"scripts\\preflight_scrapingdog_mcp.mjs"', setup)

    def test_installs_the_pull_request_commit(self) -> None:
        unix_setup = (ROOT / "setup.sh").read_text(encoding="utf-8")
        windows_setup = (ROOT / "setup.ps1").read_text(encoding="utf-8")

        self.assertIn(self.package_spec, unix_setup)
        self.assertIn(self.package_spec, windows_setup)

    def test_keeps_the_api_key_out_of_host_configuration(self) -> None:
        unix_setup = (ROOT / "setup.sh").read_text(encoding="utf-8")
        windows_setup = (ROOT / "setup.ps1").read_text(encoding="utf-8")

        self.assertNotIn("--env SCRAPINGDOG_API_KEY=", unix_setup)
        self.assertNotIn("-e SCRAPINGDOG_API_KEY=", unix_setup)
        self.assertNotIn('"--env", "SCRAPINGDOG_API_KEY=', windows_setup)


class DcgConfigurationBehavior(unittest.TestCase):
    def test_keeps_checkout_from_ref_protected(self) -> None:
        allowlist = (ROOT / "dcg" / "allowlist.toml").read_text(encoding="utf-8")

        self.assertNotIn("core.git:checkout-ref-discard", allowlist)


class PipelockIntegrationBehavior(unittest.TestCase):
    def test_installs_and_configures_supported_hosts_on_unix(self) -> None:
        setup = (ROOT / "setup.sh").read_text(encoding="utf-8")

        self.assertIn('scripts/install_pipelock.py" --target "$pipelock_bin"', setup)
        self.assertIn('"$pipelock_bin" codex install', setup)
        self.assertIn('"$pipelock_bin" claude setup', setup)

    def test_installs_and_configures_supported_hosts_on_windows(self) -> None:
        setup = (ROOT / "setup.ps1").read_text(encoding="utf-8")

        self.assertIn('"scripts\\install_pipelock.py"', setup)
        self.assertIn('Invoke-Native $PipelockPath @("codex", "install")', setup)
        self.assertIn('Invoke-Native $PipelockPath @("claude", "setup")', setup)


if __name__ == "__main__":
    unittest.main()
