import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[2]
GRAPH = ROOT / "skills" / "agent-graph" / "scripts" / "agent_graph.py"


class PortableGraphDocumentationBehavior(unittest.TestCase):
    def read(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8")

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
