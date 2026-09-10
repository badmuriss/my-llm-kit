import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("visual_brief", ROOT / "scripts/render_visual_brief.py")
assert SPEC and SPEC.loader
brief = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(brief)
EXAMPLE = (ROOT / "assets/visual-brief-example.md").read_text(encoding="utf-8")


def source(data):
    return "# Spec\n\n```visual-brief\n" + json.dumps(data) + "\n```\n"


class VisualBriefTests(unittest.TestCase):
    def test_renders_the_example_deterministically_without_network_or_script(self):
        rendered = brief.render(EXAMPLE, "spec.md")
        self.assertEqual(rendered, brief.render(EXAMPLE, "spec.md"))
        self.assertIn("Proposta, não evidência de execução.", rendered)
        self.assertIn("Quando algo der errado", rendered)
        self.assertNotIn("<script", rendered)
        self.assertNotIn('src="http', rendered)
        self.assertIn("Content-Security-Policy", rendered)
        self.assertTrue(brief.check_fresh(EXAMPLE, rendered))
        self.assertFalse(brief.check_fresh(EXAMPLE + "changed", rendered))

    def test_escapes_all_authored_fields_instead_of_executing_markup(self):
        data = brief.parse_brief(EXAMPLE)
        data["summary"] = '<script>alert("test")</script>'
        rendered = brief.render(source(data), '<img src="remote">')
        self.assertNotIn('<script>', rendered)
        self.assertNotIn('<img', rendered)
        self.assertIn('&lt;script&gt;', rendered)

    def test_rejects_ambiguous_or_unsupported_shapes(self):
        for invalid in ("# No brief", EXAMPLE + EXAMPLE, '```visual-brief\n{bad}\n```'):
            with self.subTest(source=invalid[:30]), self.assertRaises(ValueError):
                brief.parse_brief(invalid)
        for key, value in (("schema_version", True), ("language", "xx"), ("flow", []), ("checks", []), ("decisions", "text")):
            data = brief.parse_brief(EXAMPLE)
            data[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                brief.parse_brief(source(data))
        data = brief.parse_brief(EXAMPLE)
        data["execution_status"] = "passed"
        with self.assertRaises(ValueError):
            brief.parse_brief(source(data))

    def test_rejects_a_flow_that_would_be_truncated_or_unreadable(self):
        data = brief.parse_brief(EXAMPLE)
        data["flow"] = data["flow"] * 2
        with self.assertRaisesRegex(ValueError, "split larger views"):
            brief.parse_brief(source(data))

    def test_cli_checks_freshness_and_refuses_unrelated_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "spec.md"
            out = Path(directory) / "spec.html"
            src.write_text(EXAMPLE, encoding="utf-8")
            args = [str(src), "--output", str(out)]
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(brief.main(args), 0)
                self.assertEqual(brief.main(args + ["--check"]), 0)
                out.write_text(out.read_text().replace("Antes", "Modified"))
                self.assertEqual(brief.main(args + ["--check"]), 1)
                out.write_text("unrelated content")
                self.assertEqual(brief.main(args), 1)
                self.assertEqual(out.read_text(), "unrelated content")
                self.assertEqual(brief.main([str(src), "--output", str(src)]), 1)
            self.assertEqual(src.read_text(encoding="utf-8"), EXAMPLE)


if __name__ == "__main__":
    unittest.main()
