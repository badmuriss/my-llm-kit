import json
import os
import shutil
import site
import subprocess
import sys
import tempfile
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

    def test_emits_core_install_skills_as_shell_rows(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

        result = read_section("core_install_skills")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), manifest["core_install_skills"])

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


@unittest.skipUnless(shutil.which("bash"), "requires bash")
class CoreInstallBehavior(unittest.TestCase):
    def test_runs_the_installed_runtime_in_an_unrelated_project_after_repeat_install(self) -> None:
        for installer in ("setup.sh", "install.sh"):
            with self.subTest(installer=installer), tempfile.TemporaryDirectory() as temporary:
                user_directory = Path(temporary) / "user directory"
                project = Path(temporary) / "consumer project"
                project.mkdir()
                for host in (".claude", ".codex"):
                    (user_directory / host).mkdir(parents=True)
                unrelated = user_directory / ".agents" / "skills" / "unrelated"
                unrelated.mkdir(parents=True)
                (unrelated / "SKILL.md").write_text("User-owned skill.\n", encoding="utf-8")
                owned_core = unrelated.parent / "writing"
                owned_core.mkdir()
                (owned_core / "SKILL.md").write_text("Customized writing policy.\n", encoding="utf-8")
                environment = {
                    **os.environ, "HOME": str(user_directory),
                    "PYTHONPATH": os.pathsep.join([*site.getsitepackages(), site.getusersitepackages()]),
                }
                for _ in range(2):
                    result = subprocess.run(
                        ["bash", str(ROOT / installer)], cwd=project, env=environment,
                        capture_output=True, text=True, timeout=60,
                    )
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                installed = user_directory / ".agents" / "skills" / "agent-graph"
                result = subprocess.run(
                    [sys.executable, str(installed / "scripts" / "agent_graph.py"),
                     "intake", "--repo", str(project), "--request", "Fix the local typo.",
                     "--check", "git diff --check", "--signals-json",
                     json.dumps({"small_change": True, "known_scope": True}), "--json"],
                    cwd=project, env=environment, capture_output=True, text=True, timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                payload = json.loads(result.stdout)["result"]
                self.assertEqual(payload["decision"]["mode"], "direct")
                self.assertEqual(payload["repository_facts"]["canonical_root"], str(project))
                self.assertFalse((project / "skills").exists())
                self.assertFalse((project / "openspec").exists())
                self.assertEqual((unrelated / "SKILL.md").read_text(), "User-owned skill.\n")
                self.assertFalse((user_directory / ".claude" / "skills" / "unrelated").exists())
                self.assertFalse(owned_core.is_symlink())
                self.assertEqual((owned_core / "SKILL.md").read_text(), "Customized writing policy.\n")
                if installer == "setup.sh":
                    self.assertEqual(
                        (user_directory / ".agents" / "AGENTS.md").read_text(),
                        (ROOT / "instructions" / "AGENTS.md").read_text(),
                    )


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
