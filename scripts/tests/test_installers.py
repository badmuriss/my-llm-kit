import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[2]
MANIFEST = ROOT / "install-manifest.json"
MANIFEST_READER = ROOT / "scripts" / "read_install_manifest.py"


class SharedManifestBehavior(unittest.TestCase):
    def test_includes_every_vendored_dependency_of_spec(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

        self.assertIn("spec", manifest["reduced_install_skills"])
        self.assertIn("impl", manifest["reduced_install_skills"])
        self.assertIn("grill-me", manifest["reduced_install_skills"])

    def test_emits_rows_for_shell_without_reimplementing_json_parsing(self) -> None:
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


class InstallerContractBehavior(unittest.TestCase):
    def test_setup_scripts_share_the_same_manifest(self) -> None:
        shell_setup = (ROOT / "setup.sh").read_text(encoding="utf-8")
        windows_setup = (ROOT / "setup.ps1").read_text(encoding="utf-8")

        self.assertIn("install-manifest.json", shell_setup)
        self.assertIn("install-manifest.json", windows_setup)
        self.assertNotIn("OWN_REPOS=(", shell_setup)
        self.assertNotIn("COMMUNITY_SKILLS=(", shell_setup)
        self.assertNotIn("PLUGINS=(", shell_setup)

    def test_reduced_installer_reads_grill_me_from_the_manifest(self) -> None:
        installer = (ROOT / "install.sh").read_text(encoding="utf-8")

        self.assertIn("reduced_install_skills", installer)
        self.assertNotIn("install_vendored_skill spec", installer)
        self.assertNotIn("install_vendored_skill impl", installer)

    def test_windows_setup_uses_native_filesystem_and_dcg_operations(self) -> None:
        windows_setup = (ROOT / "setup.ps1").read_text(encoding="utf-8")

        self.assertIn('ItemType Junction', windows_setup)
        self.assertIn('destructive_command_guard/main/install.ps1', windows_setup)
        self.assertIn('agent resource guard is Linux-only', windows_setup)
        self.assertNotIn('C:\\Users\\', windows_setup)

    def test_readme_leads_with_an_agent_install_prompt(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        prompt_position = readme.index("Install my-llm-kit from")
        manual_position = readme.index("Manual fallback for Linux and macOS")
        self.assertLess(prompt_position, manual_position)
        self.assertIn(".\\setup.ps1 -DryRun", readme)
        self.assertIn("grill-me", readme[prompt_position:manual_position])

    def test_readme_skill_requires_agent_first_installation(self) -> None:
        skill = (ROOT / "skills" / "readme-pass" / "SKILL.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("agent-install prompt", skill)
        self.assertIn("dry-run or preview first", skill)
        self.assertIn("manual commands", skill)


if __name__ == "__main__":
    unittest.main()
