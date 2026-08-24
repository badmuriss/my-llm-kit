import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[2]
AUDITOR = ROOT / "skills" / "research" / "scripts" / "audit_finding.py"


VALID_FINDING = """# Research finding

## Protocol

- Question: Does unittest discovery require an importable start directory?
- Decision criterion: The official documentation states it directly.
- Falsifier: The official documentation contradicts it.
- Risk: material
- Budget: 75 credits
- Credits used: 0

## Provider trail

| Intent | Provider | Tool or endpoint | Outcome | Credits | Fallback reason |
|---|---|---|---|---|---|
| Product fact | official docs | https://docs.python.org/3/library/unittest.html | answered | 0 | None |

## Claim ledger

| Claim | Source | Accessed | Snapshot | Primary | Direct | Current | Independent | Verdict |
|---|---|---|---|---|---|---|---|---|
| Discovery requires an importable start directory. | https://docs.python.org/3/library/unittest.html | 2026-08-12 | research/sources/unittest/discovery.md | yes | yes | yes | yes | accepted |

## Findings

Discovery requires an importable start directory.

## Disagreements

None.

## Open questions

None.

## Council review

- Status: not run
- Reason: no council trigger
- Accepted findings: None.
- Rejected findings: None.

## Sources consulted

- https://docs.python.org/3/library/unittest.html, accessed 2026-08-12.

## Trial by fire

- Primary-source claims: Discovery requires an importable start directory.
- Secondary-only claims: None.
- Volatile claims: None.
"""


class ResearchAuditBehavior(unittest.TestCase):
    def run_audit(self, content: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            finding = Path(directory) / "2026-08-12-unittest-discovery.md"
            finding.write_text(content, encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(AUDITOR), str(finding)],
                check=False,
                capture_output=True,
                text=True,
            )

    def test_accepts_a_complete_finding(self) -> None:
        result = self.run_audit(VALID_FINDING)

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_a_claim_without_provenance(self) -> None:
        invalid = VALID_FINDING.replace(
            "| https://docs.python.org/3/library/unittest.html | 2026-08-12 |",
            "| no-source | yesterday |",
            1,
        )

        result = self.run_audit(invalid)

        self.assertEqual(result.returncode, 1)
        self.assertIn("has no source URL", result.stderr)
        self.assertIn("has invalid access date", result.stderr)

    def test_rejects_a_missing_provider_trail(self) -> None:
        invalid = VALID_FINDING.replace(
            "| Product fact | official docs |"
            " https://docs.python.org/3/library/unittest.html | answered | 0 | None |",
            "| | | | | | |",
        )

        result = self.run_audit(invalid)

        self.assertEqual(result.returncode, 1)
        self.assertIn("provider trail row 1 is missing required values", result.stderr)


if __name__ == "__main__":
    unittest.main()
