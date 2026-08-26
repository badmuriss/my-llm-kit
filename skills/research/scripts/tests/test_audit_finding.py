"""Behavioral tests for audit_finding semantic checks."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(SCRIPTS))

from audit_finding import audit  # noqa: E402


def audit_fixture(name: str) -> tuple[list[str], list[str]]:
    return audit((FIXTURES / name).read_text(encoding="utf-8"), name)


class TestPassingFinding:
    def test_accepts_complete_finding_without_budget(self):
        errors, warnings = audit_fixture("2026-08-21-good.md")
        assert errors == []
        assert warnings == []


class TestSemanticErrors:
    @pytest.mark.parametrize(
        ("fixture", "fragment"),
        [
            ("bad-bare-number.md", "number without URL and access date"),
            ("bad-example-com.md", "example.com"),
            ("bad-high-risk-no-council.md", "Risk: high requires a council run"),
            ("bad-ledger-url-missing.md", "missing from Sources consulted"),
        ],
    )
    def test_rejects_known_bad_finding(self, fixture: str, fragment: str):
        errors, _ = audit_fixture(fixture)
        assert any(fragment in error for error in errors), errors


class TestWarnings:
    def test_warns_on_filename_without_date_prefix(self):
        errors, warnings = audit_fixture("bad-bare-number.md")
        assert any("YYYY-MM-DD-slug.md" in warning for warning in warnings)

    def test_warns_when_most_claims_have_unknown_independence(self):
        text = (FIXTURES / "2026-08-21-good.md").read_text(encoding="utf-8")
        text = text.replace("| yes | yes | yes | yes | accepted |", "| yes | yes | yes | unknown | accepted |")
        errors, warnings = audit(text, "2026-08-21-good.md")
        assert errors == []
        assert any("Independent: unknown" in warning for warning in warnings)
