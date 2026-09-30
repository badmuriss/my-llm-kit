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
    def test_runs_the_installed_collector_in_an_unrelated_project_after_repeat_install(self) -> None:
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
                owned_core = unrelated.parent / "frontend-visual-validation"
                owned_core.mkdir()
                (owned_core / "SKILL.md").write_text("Customized visual policy.\n", encoding="utf-8")
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
                installed = user_directory / ".agents" / "skills" / "research"
                sources = project / "sources.json"
                sources.write_text(json.dumps([{"slug": "fixture", "url": "https://example.com/"}]))
                result = subprocess.run(
                    [sys.executable, str(installed / "scripts" / "collect_sources.py"),
                     "--input", str(sources), "--out", str(project / "evidence"),
                     "--project-scope", "installer-test", "--dry-run"],
                    cwd=project, env=environment, capture_output=True, text=True, timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                payload = json.loads(result.stdout.splitlines()[0])
                self.assertEqual(payload["input"]["url"], "https://example.com/")
                self.assertEqual(payload["project_scope"], "installer-test")
                self.assertFalse((project / "evidence").exists())
                self.assertFalse((project / "skills").exists())
                self.assertEqual((unrelated / "SKILL.md").read_text(), "User-owned skill.\n")
                self.assertFalse((user_directory / ".claude" / "skills" / "unrelated").exists())
                self.assertFalse(owned_core.is_symlink())
                self.assertEqual((owned_core / "SKILL.md").read_text(), "Customized visual policy.\n")
                if installer == "setup.sh":
                    self.assertEqual(
                        (user_directory / ".agents" / "AGENTS.md").read_text(),
                        (ROOT / "instructions" / "AGENTS.md").read_text(),
                    )


@unittest.skipUnless(shutil.which("bash"), "requires bash")
class InstructionInstallBehavior(unittest.TestCase):
    def run_setup(self, user_directory: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        environment = {
            **os.environ,
            "HOME": str(user_directory),
            "PYTHONPATH": os.pathsep.join([*site.getsitepackages(), site.getusersitepackages()]),
        }
        result = subprocess.run(
            ["bash", str(ROOT / "setup.sh"), *arguments],
            cwd=user_directory, env=environment,
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_migrates_duplicate_instructions_to_agents_after_a_read_only_preview(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            user_directory = Path(temporary)
            for host in (".agents", ".claude", ".codex", ".omp/agent"):
                (user_directory / host).mkdir(parents=True)
            legacy = user_directory / ".claude" / "CLAUDE.md"
            shared = user_directory / ".agents" / "AGENTS.md"
            previous = "Previously managed shared instructions.\n"
            shared.write_text(previous, encoding="utf-8")
            legacy.write_text(previous, encoding="utf-8")

            self.run_setup(user_directory, "--dry-run")
            self.assertEqual(legacy.read_text(), previous)
            self.assertEqual(shared.read_text(), previous)
            self.assertFalse((legacy.parent / "AGENTS.md").exists())
            for _ in range(2):
                self.run_setup(user_directory)
            self.assertFalse(legacy.exists())
            expected = (ROOT / "instructions" / "AGENTS.md").read_text()
            for host in (".agents", ".claude", ".codex", ".omp/agent"):
                self.assertEqual((user_directory / host / "AGENTS.md").read_text(), expected)

    def test_preserves_custom_claude_instructions_during_repeat_setup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            user_directory = Path(temporary)
            (user_directory / ".claude").mkdir()
            legacy = user_directory / ".claude" / "CLAUDE.md"
            content = "Private project and account instructions.\n"
            legacy.write_text(content, encoding="utf-8")
            for _ in range(2):
                self.run_setup(user_directory)
            self.assertEqual(legacy.read_text(), content)
            self.assertEqual(
                (legacy.parent / "AGENTS.md").read_text(),
                (ROOT / "instructions" / "AGENTS.md").read_text(),
            )


@unittest.skipUnless(os.name == "posix" and shutil.which("bash"), "requires POSIX command stubs")
class FullPreviewBehavior(unittest.TestCase):
    def test_previews_integrations_without_running_tools_that_write_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            user_directory = Path(temporary) / "user directory"
            user_directory.mkdir()
            binaries = Path(temporary) / "bin"
            binaries.mkdir()
            for name in ("claude", "codex", "opencode", "npm", "firecrawl"):
                command = binaries / name
                command.write_text('#!/bin/sh\nprintf called > "$HOME/external-command-ran"\nexit 73\n')
                command.chmod(0o755)
            environment = {
                "HOME": str(user_directory),
                "PATH": str(binaries) + os.pathsep + os.environ["PATH"],
                "PYTHONPATH": os.pathsep.join([*site.getsitepackages(), site.getusersitepackages()]),
            }
            result = subprocess.run(
                ["bash", str(ROOT / "setup.sh"), "--full", "--dry-run"],
                cwd=user_directory, env=environment,
                capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(list(user_directory.iterdir()), [])
            self.assertIn("[dry-run] claude mcp add", result.stdout)
            self.assertIn("[dry-run] codex mcp add", result.stdout)


@unittest.skipUnless(os.name == "posix" and shutil.which("node"), "requires node and a POSIX npm stub")
class StagehandInstallBehavior(unittest.TestCase):
    def test_installs_scripts_without_creating_an_omp_host_and_reuses_an_existing_host(self) -> None:
        for with_omp in (False, True):
            with self.subTest(with_omp=with_omp), tempfile.TemporaryDirectory() as temporary:
                user_directory = Path(temporary) / "user directory"
                user_directory.mkdir()
                binaries = Path(temporary) / "bin"
                binaries.mkdir()
                npm = binaries / "npm"
                npm.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                npm.chmod(0o755)
                omp = user_directory / ".omp" / "agent"
                if with_omp:
                    omp.mkdir(parents=True)
                    (omp / "config.yml").write_text("User-owned native configuration.\n", encoding="utf-8")
                environment = {**os.environ, "PATH": str(binaries) + os.pathsep + os.environ["PATH"]}
                installer = ROOT / "skills" / "stagehand-browser" / "tools" / "install.mjs"
                for _ in range(2):
                    result = subprocess.run(
                        ["node", str(installer), "--home", str(user_directory)],
                        env=environment, capture_output=True, text=True, timeout=30,
                    )
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                canonical = user_directory / ".agents" / "skills" / "stagehand-browser"
                self.assertEqual(canonical.resolve(), installer.parent.parent)
                if with_omp:
                    self.assertTrue((omp / "extensions" / "stagehand-browser.mjs").is_file())
                    self.assertEqual((omp / "config.yml").read_text(), "User-owned native configuration.\n")
                else:
                    self.assertFalse((user_directory / ".omp").exists())


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
