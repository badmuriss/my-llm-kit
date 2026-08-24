import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[2]
MANIFEST = ROOT / "install-manifest.json"
MANIFEST_READER = ROOT / "scripts" / "read_install_manifest.py"


def read_section(section: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(MANIFEST_READER), section, "--manifest", str(MANIFEST)],
        check=False,
        capture_output=True,
        text=True,
    )


class SharedManifestBehavior(unittest.TestCase):
    def test_emits_every_community_skill_as_a_shell_row(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

        result = read_section("community_skills")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines(),
            [
                f"{entry['name']}|{entry['url']}|{entry['path']}"
                for entry in manifest["community_skills"]
            ],
        )

    def test_emits_reduced_install_skills_as_shell_rows(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

        result = read_section("reduced_install_skills")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), manifest["reduced_install_skills"])

    def test_documents_every_shipped_and_community_skill(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        shipped = sorted(
            path.parent.name for path in (ROOT / "skills").glob("*/SKILL.md")
        )
        community = [entry["name"] for entry in manifest["community_skills"]]

        for name in (*shipped, *community):
            with self.subTest(skill=name):
                self.assertIn(f"`{name}`", readme)


class ScrapingDogMcpBehavior(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
