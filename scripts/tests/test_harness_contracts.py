import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[2]
GRAPH = ROOT / "skills" / "agent-graph" / "scripts" / "agent_graph.py"


class PortableGraphDocumentationBehavior(unittest.TestCase):
    def read(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_spec_requires_and_validates_every_graph_field(self) -> None:
        sources = self.read("skills/spec/SKILL.md") + self.read("commands/spec.md")

        for field in ("Depends:", "Paths:", "Mode:", "Isolation:", "Acceptance:", "Check:"):
            self.assertIn(field, sources)
        self.assertIn("agent_graph.py validate", sources)
        self.assertIn("never starts workers", sources)

    def test_impl_owns_the_fresh_coordinator_and_graph_commands(self) -> None:
        sources = self.read("skills/impl/SKILL.md") + self.read("commands/impl.md")

        for command in (
            "bootstrap", "claim-coordinator", "resume", "ready", "dispatch", "sync",
            "record-result", "reply", "run-check", "grade", "record-repair",
            "cleanup-register", "cleanup-finish", "status --watch", "takeover", "digest", "complete",
        ):
            self.assertIn(command, sources)
        self.assertIn("fresh top-level session", sources)
        self.assertIn("Never create an Orca Task or Dispatch for the coordinator", sources)
        self.assertIn("generated capsule", sources)
        self.assertIn("tracked-terminal", sources)
        self.assertIn("Maestri", sources)

    def test_research_keeps_collectors_read_only_and_adjudication_local(self) -> None:
        source = self.read("skills/research/SKILL.md")

        self.assertIn("Mode: read", source)
        self.assertIn("agent_graph.py validate", source)
        self.assertIn("dispatch", source)
        self.assertIn("record-result", source)
        self.assertIn("main researcher", source)

    def test_active_harness_docs_do_not_reference_the_flat_runtime(self) -> None:
        paths = [ROOT / "README.md", *sorted((ROOT / "commands").glob("*.md"))]
        paths.extend(
            ROOT / relative
            for relative in (
                "skills/spec/SKILL.md",
                "skills/impl/SKILL.md",
                "skills/research/SKILL.md",
                "skills/frontend-visual-validation/SKILL.md",
            )
        )
        forbidden = "impl" + "_state.py"
        legacy_directory = "openspec/" + "impl-state"

        for path in paths:
            with self.subTest(path=path.relative_to(ROOT)):
                content = path.read_text(encoding="utf-8")
                self.assertNotIn(forbidden, content)
                self.assertNotIn(legacy_directory, content)

    def test_the_shipped_change_validates_without_starting_workers(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(GRAPH),
                "validate",
                "--repo",
                str(ROOT),
                "--change",
                "portable-agent-graph-orchestration",
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"task_count": 8', result.stdout)


if __name__ == "__main__":
    unittest.main()
