import contextlib
import io
import json
import tempfile
import unittest
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import render_visual_brief as brief
import visual_diagrams as diagrams

EXAMPLE = (ROOT / "assets/visual-brief-example.md").read_text(encoding="utf-8")
TEXT_ONLY = EXAMPLE.split("## Da especificação")[0]
SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 100"><text x="10" y="20">A to B</text></svg>'


def source(data):
    return "# Spec\n\n```visual-brief\n" + json.dumps(data) + "\n```\n"


class VisualBriefTests(unittest.TestCase):
    def test_renders_plain_brief_without_network_or_script(self):
        rendered = brief.render(TEXT_ONLY, "spec.md")
        self.assertEqual(rendered, brief.render(TEXT_ONLY, "spec.md"))
        self.assertIn("Proposta, não evidência de execução.", rendered)
        self.assertIn("Quando algo der errado", rendered)
        self.assertNotIn("<script", rendered)
        self.assertNotIn('src="http', rendered)
        self.assertIn("Content-Security-Policy", rendered)
        self.assertTrue(brief.check_fresh(TEXT_ONLY, rendered))
        self.assertFalse(brief.check_fresh(TEXT_ONLY + "changed", rendered))

    def test_escapes_authored_fields(self):
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
        data["execution_status"] = "passed"
        with self.assertRaises(ValueError):
            brief.parse_brief(source(data))

    def test_rejects_unreadable_flow_instead_of_truncating(self):
        data = brief.parse_brief(EXAMPLE)
        data["flow"] *= 2
        with self.assertRaisesRegex(ValueError, "split larger views"):
            brief.parse_brief(source(data))

    def test_cli_checks_freshness_and_preserves_unrelated_files(self):
        with tempfile.TemporaryDirectory() as directory:
            src, out = Path(directory) / "spec.md", Path(directory) / "spec.html"
            src.write_text(TEXT_ONLY, encoding="utf-8")
            args = [str(src), "--output", str(out), "--html-only"]
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(brief.main(args), 0)
                self.assertEqual(brief.main(args + ["--check"]), 0)
                out.write_text(out.read_text().replace("Antes", "Modified"))
                self.assertEqual(brief.main(args + ["--check"]), 1)
                out.write_text("unrelated content")
                self.assertEqual(brief.main(args), 1)
                self.assertEqual(out.read_text(), "unrelated content")
                self.assertEqual(brief.main([str(src), "--output", str(src)]), 1)
            self.assertEqual(src.read_text(encoding="utf-8"), TEXT_ONLY)

    def test_exports_pdf_by_default_and_checks_without_exporting_again(self):
        with tempfile.TemporaryDirectory() as directory:
            src, out = Path(directory) / "spec.md", Path(directory) / "spec.html"
            src.write_text(TEXT_ONLY, encoding="utf-8")
            def export(html_path, pdf_path, **kwargs):
                content = html_path.read_text(encoding="utf-8")
                self.assertIn("data:font/woff2;base64,", content)
                self.assertIn("SIL OPEN FONT LICENSE", content)
                pdf_path.write_bytes(b"%PDF-test")
            args = [str(src), "--output", str(out)]
            with patch.object(brief, "export_pdf", side_effect=export) as exporter, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(brief.main(args), 0)
                self.assertEqual(out.with_suffix(".pdf").read_bytes(), b"%PDF-test")
                self.assertEqual(brief.main(args + ["--check"]), 0)
                self.assertEqual(exporter.call_count, 1)

    def test_html_only_skips_browser_and_default_export_failure_preserves_html(self):
        with tempfile.TemporaryDirectory() as directory:
            src, out = Path(directory) / "spec.md", Path(directory) / "spec.html"
            src.write_text(TEXT_ONLY, encoding="utf-8")
            args = [str(src), "--output", str(out)]
            with patch.object(brief, "export_pdf", side_effect=ValueError("browser absent")) as exporter, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(brief.main(args + ["--html-only"]), 0)
                exporter.assert_not_called()
                previous = out.read_bytes()
                src.write_text(TEXT_ONLY.replace("Antes", "Before"), encoding="utf-8")
                self.assertEqual(brief.main(args), 1)
                self.assertEqual(out.read_bytes(), previous)
                self.assertFalse(out.with_suffix(".pdf").exists())

    def test_embeds_rendered_images_and_keeps_editable_source(self):
        rendered = brief.render(EXAMPLE, "spec.md", [SVG, SVG])
        self.assertEqual(rendered.count('<img data-mermaid-sha256='), 2)
        self.assertIn('data:image/svg+xml;base64,', rendered)
        self.assertIn('sequenceDiagram', rendered)
        self.assertIn('img-src data:', rendered)
        self.assertNotIn('<script', rendered)
        self.assertEqual(diagrams.cached_diagrams(rendered, diagrams.parse_diagrams(EXAMPLE)), [SVG, SVG])
        with self.assertRaisesRegex(ValueError, "every Mermaid"):
            brief.render(EXAMPLE, "spec.md")

    def test_checks_diagrams_without_browser_and_detects_image_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            src, out = Path(directory) / "spec.md", Path(directory) / "spec.html"
            src.write_text(EXAMPLE, encoding="utf-8")
            rendered = brief.render(EXAMPLE, src.name, [SVG, SVG])
            out.write_text(rendered, encoding="utf-8")
            args = [str(src), "--output", str(out), "--check"]
            with patch.object(brief, "render_diagrams", side_effect=AssertionError("unexpected browser")), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(brief.main(args), 0)
                import base64
                out.write_text(rendered.replace(base64.b64encode(SVG.encode()).decode(), base64.b64encode(SVG.replace("A to B", "A to C").encode()).decode()), encoding="utf-8")
                self.assertEqual(brief.main(args), 1)

    def test_preserves_documents_when_mermaid_or_pdf_rendering_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            src, out, pdf = [Path(directory) / name for name in ("spec.md", "spec.html", "spec.pdf")]
            src.write_text(EXAMPLE, encoding="utf-8")
            previous = brief.render(TEXT_ONLY, src.name)
            out.write_text(previous, encoding="utf-8")
            args = [str(src), "--output", str(out), "--pdf", str(pdf)]
            with contextlib.redirect_stderr(io.StringIO()):
                with patch.object(brief, "render_diagrams", side_effect=ValueError("invalid syntax")):
                    self.assertEqual(brief.main(args), 1)
                with patch.object(brief, "render_diagrams", return_value=[SVG, SVG]), patch.object(brief, "export_pdf", side_effect=ValueError("browser absent")):
                    self.assertEqual(brief.main(args), 1)
            self.assertEqual(out.read_text(), previous)
            self.assertFalse(pdf.exists())

    def test_refuses_pdf_overwrites_symlinks_and_pdf_in_check_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            src, out, pdf = [Path(directory) / name for name in ("spec.md", "spec.html", "spec.pdf")]
            src.write_text(TEXT_ONLY, encoding="utf-8")
            pdf.write_bytes(b"owned PDF")
            with contextlib.redirect_stderr(io.StringIO()):
                args = [str(src), "--output", str(out), "--pdf", str(pdf)]
                self.assertEqual(brief.main(args), 1)
                self.assertEqual(brief.main(args + ["--check"]), 1)
                out.symlink_to(src)
                self.assertEqual(brief.main([str(src), "--output", str(out)]), 1)
            self.assertEqual(pdf.read_bytes(), b"owned PDF")
            self.assertEqual(src.read_text(), TEXT_ONLY)


class MermaidTests(unittest.TestCase):
    def test_parses_real_fences_and_ignores_quoted_examples(self):
        parsed = diagrams.parse_diagrams(EXAMPLE)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["title"], "Uma fonte, duas formas de leitura")
        self.assertEqual(diagrams.parse_diagrams('````markdown\n```mermaid\ngraph TD\nA-->B\n```\n````'), [])
        self.assertEqual(len(diagrams.parse_diagrams('# State\n~~~mermaid\nstateDiagram-v2\n[*] --> Ready\n~~~')), 1)

    def test_rejects_unsafe_empty_unclosed_or_overlarge_diagrams(self):
        for code in ('', '---\nconfig: {}\n---\ngraph TD', 'graph TD\n%%{init: {}}%%', 'graph TD\nA[https://example.com]', 'graph TD\nA@{ img: "secret" }', 'graph TD\n' + 'x' * 12000):
            with self.subTest(code=code[:30]), self.assertRaises(ValueError):
                diagrams.parse_diagrams('# Diagram\n```mermaid\n' + code + '\n```')
        with self.assertRaisesRegex(ValueError, "unclosed"):
            diagrams.parse_diagrams('# Diagram\n```mermaid\ngraph TD')
        with self.assertRaisesRegex(ValueError, "six"):
            diagrams.parse_diagrams(('# D\n```mermaid\ngraph TD\nA-->B\n```\n') * 7)

    def test_rejects_active_or_external_svg_and_invalid_geometry(self):
        for svg in (
            SVG.replace('<text ', '<text onclick="bad" '),
            SVG.replace('</svg>', '<script>alert(1)</script></svg>'),
            SVG.replace('</svg>', '<image href="file:///secret"/></svg>'),
            SVG.replace('</svg>', '<style>@import "https://example.com";</style></svg>'),
            SVG.replace('<text ', '<text style="fill:url(https://example.com)" '),
            SVG.replace('300 100', 'nan 0'), '<!DOCTYPE svg>' + SVG, 'not an SVG',
        ):
            with self.subTest(svg=svg[:60]), self.assertRaises(ValueError):
                diagrams.validate_svg(svg)
        self.assertEqual(diagrams.validate_svg(SVG), SVG)

    def test_uses_fixed_local_configuration_and_no_shell(self):
        request = diagrams.parse_diagrams('# Diagram\n```mermaid\ngraph TD\nA-->B\n```')
        def run(command, **kwargs):
            self.assertEqual(command[0], '/bin/mmdc')
            settings = json.loads(Path(command[command.index('-c') + 1]).read_text())
            self.assertEqual(settings['securityLevel'], 'strict')
            self.assertFalse(settings['htmlLabels'])
            launch = json.loads(Path(command[command.index('-p') + 1]).read_text())
            self.assertNotIn('--no-sandbox', launch['args'])
            Path(command[command.index('-o') + 1]).write_text(SVG)
        with patch.object(diagrams, '_executable', return_value='/bin/mmdc'), patch.object(diagrams, 'run_tool', side_effect=run):
            self.assertEqual(diagrams.render_diagrams(request), [SVG])

    def test_missing_mermaid_is_not_silently_omitted(self):
        with patch.object(diagrams.shutil, 'which', return_value=None):
            self.assertEqual(diagrams.render_diagrams([]), [])
            with self.assertRaisesRegex(ValueError, 'unavailable'):
                diagrams.render_diagrams(diagrams.parse_diagrams(EXAMPLE))


if __name__ == "__main__":
    unittest.main()
