import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[2]
CONFIGURER = ROOT / "scripts" / "configure_opencode_mcp.py"


class OpenCodeMcpConfigurationBehavior(unittest.TestCase):
    def run_configurer(self, config: Path, name: str, *command: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(CONFIGURER),
                "--config",
                str(config),
                "--name",
                name,
                "--command",
                *command,
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_configures_servers_idempotently_and_preserves_unrelated_settings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "opencode.json"
            config.write_text(
                json.dumps(
                    {
                        "$schema": "https://opencode.ai/config.json",
                        "theme": "quiet",
                        "mcp": {"existing": {"type": "remote", "url": "https://mcp.test"}},
                    }
                ),
                encoding="utf-8",
            )

            first = self.run_configurer(config, "paper-search", "paper-search-mcp")
            second = self.run_configurer(config, "paper-search", "paper-search-mcp")

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            saved = json.loads(config.read_text(encoding="utf-8"))
            self.assertEqual(saved["theme"], "quiet")
            self.assertEqual(saved["mcp"]["existing"]["url"], "https://mcp.test")
            self.assertEqual(saved["mcp"]["paper-search"]["command"], ["paper-search-mcp"])
            self.assertEqual(len(list(config.parent.glob("opencode.json.bak-*"))), 1)

    def test_accepts_jsonc_and_refuses_a_conflicting_entry_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "opencode.json"
            original = '''{
  // Keep this user setting intact.
  "theme": "quiet",
  "mcp": {
    "scrapingdog": {"type": "local", "command": ["custom-server"]},
  },
}'''
            config.write_text(original, encoding="utf-8")

            result = self.run_configurer(config, "scrapingdog", "node", "/tmp/server.js")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("refusing to replace", result.stderr)
            self.assertEqual(config.read_text(encoding="utf-8"), original)
            self.assertEqual(list(config.parent.glob("opencode.json.bak-*")), [])


if __name__ == "__main__":
    unittest.main()
