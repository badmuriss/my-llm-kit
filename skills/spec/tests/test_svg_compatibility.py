"""Regression coverage for Mermaid's inert SVG shadow definitions."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from visual_diagrams import validate_svg


class SvgCompatibilityTests(unittest.TestCase):
    def test_allows_the_static_drop_shadow_used_by_mermaid(self):
        svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><filter id="shadow"><feDropShadow dx="4" dy="4" stdDeviation="0"/></filter></defs><rect width="10" height="10" filter="url(#shadow)"/></svg>'
        self.assertEqual(validate_svg(svg), svg)

    def test_filters_do_not_permit_images_or_event_handlers(self):
        for child in ('<feImage href="https://example.com/image"/>', '<feDropShadow onload="bad"/>'):
            svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><filter>' + child + '</filter></defs></svg>'
            with self.subTest(child=child), self.assertRaises(ValueError):
                validate_svg(svg)
