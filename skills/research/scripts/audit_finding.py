#!/usr/bin/env python3
"""Validate the required provenance structure of a research finding."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REQUIRED_SECTIONS = (
    "Protocol",
    "Provider trail",
    "Claim ledger",
    "Findings",
    "Disagreements",
    "Open questions",
    "Council review",
    "Sources consulted",
    "Trial by fire",
)
PROTOCOL_FIELDS = ("Question", "Decision criterion", "Falsifier", "Risk", "Credits used")
PROVIDER_HEADERS = ("Intent", "Provider", "Tool or endpoint", "Outcome", "Credits", "Fallback reason")
CLAIM_HEADERS = (
    "Claim",
    "Source",
    "Accessed",
    "Snapshot",
    "Primary",
    "Direct",
    "Current",
    "Independent",
    "Verdict",
)
ALLOWED_RISKS = {"routine", "material", "high"}
ALLOWED_BINARY_VALUES = {"yes", "no", "partial", "unknown"}
ALLOWED_VERDICTS = {"accepted", "limited", "volatile", "rejected"}
ACCESS_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
URL = re.compile(r"https?://\S+")
FILENAME = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9][a-z0-9-]*\.md$")
ACCESSED_INLINE = re.compile(r"(accessed|acessado) \d{4}-\d{2}-\d{2}")
MONEY_OR_PERCENT = re.compile(r"\d[\d.,]*\s*(%|R\$|USD|US\$|BRL)|(R\$|USD|US\$|BRL)\s*\d[\d.,]*")
UNIT_WORDS = (
    "ms", "s", "sec", "seconds", "min", "minutes", "hours", "days", "weeks", "months", "years",
    "kb", "mb", "gb", "tb", "users", "requests", "credits", "tokens", "people", "companies",
    "stars", "downloads", "installs", "views", "votes", "cases", "respondents", "employees",
    "reais", "dollars", "million", "billion", "thousand", "milhões", "bilhões", "mil", "x",
)
NUMBER_WITH_UNIT = re.compile(
    r"\b\d{2,}[\d.,]*\s*(" + "|".join(re.escape(word) for word in UNIT_WORDS) + r")\b",
    re.IGNORECASE,
)
NUMERIC_FIELD = re.compile(r"^\d+(\s*credits)?$")


def section_body(text: str, heading: str) -> str | None:
    pattern = re.compile(
        rf"^## {re.escape(heading)}\s*$\n(.*?)(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    return match.group(1).strip() if match else None


def field_value(body: str, name: str) -> str | None:
    match = re.search(rf"^- {re.escape(name)}:\s*(.+?)\s*$", body, re.MULTILINE)
    return match.group(1).strip() if match else None


def table_rows(body: str, expected_headers: tuple[str, ...]) -> list[list[str]]:
    rows = []
    for line in body.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if tuple(cells) == expected_headers:
            continue
        if cells and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        rows.append(cells)
    return rows


def strip_urls(line: str) -> str:
    return URL.sub(" ", line)


def audit(text: str, filename: str | None = None) -> tuple[list[str], list[str]]:
    """Return (errors, warnings). Errors fail the audit; warnings do not."""
    errors: list[str] = []
    warnings: list[str] = []
    bodies: dict[str, str] = {}

    if filename is not None and not FILENAME.match(filename):
        warnings.append(f"filename {filename} does not match YYYY-MM-DD-slug.md")
    if "example.com" in text:
        errors.append("finding still contains example.com placeholder")

    for heading in REQUIRED_SECTIONS:
        body = section_body(text, heading)
        if body is None:
            errors.append(f"missing section: {heading}")
            continue
        bodies[heading] = body

    protocol = bodies.get("Protocol")
    if protocol is not None:
        for name in PROTOCOL_FIELDS:
            value = field_value(protocol, name)
            if not value:
                errors.append(f"missing protocol field: {name}")
        risk = field_value(protocol, "Risk")
        if risk and risk not in ALLOWED_RISKS:
            errors.append(f"invalid risk: {risk}")
        credits_used = field_value(protocol, "Credits used")
        if credits_used and not NUMERIC_FIELD.match(credits_used):
            errors.append(f"protocol field Credits used must be numeric: {credits_used}")

    provider_trail = bodies.get("Provider trail")
    if provider_trail is not None:
        provider_rows = table_rows(provider_trail, PROVIDER_HEADERS)
        if not provider_rows or all(not any(row) for row in provider_rows):
            errors.append("provider trail has no attempts")
        for index, row in enumerate(provider_rows, start=1):
            if len(row) != len(PROVIDER_HEADERS):
                errors.append(
                    f"provider trail row {index} has {len(row)} columns; expected {len(PROVIDER_HEADERS)}"
                )
                continue
            if not all(row[:4]):
                errors.append(f"provider trail row {index} is missing required values")
            if not re.fullmatch(r"\d+", row[4]):
                errors.append(f"provider trail row {index} has non-numeric credits: {row[4]}")

    sources = bodies.get("Sources consulted")
    source_urls = set(URL.findall(sources)) if sources else set()

    claim_ledger = bodies.get("Claim ledger")
    if claim_ledger is not None:
        claim_rows = table_rows(claim_ledger, CLAIM_HEADERS)
        if not claim_rows:
            errors.append("claim ledger has no claims")
        unknown_independent = 0
        for index, row in enumerate(claim_rows, start=1):
            if len(row) != len(CLAIM_HEADERS):
                errors.append(
                    f"claim ledger row {index} has {len(row)} columns; expected {len(CLAIM_HEADERS)}"
                )
                continue
            claim, source, accessed, _snapshot, primary, direct, current, independent, verdict = row
            if not claim:
                errors.append(f"claim ledger row {index} has no claim")
            ledger_url = URL.search(source)
            if not ledger_url:
                errors.append(f"claim ledger row {index} has no source URL")
            elif sources is not None and ledger_url.group(0).rstrip(".,)") not in {
                url.rstrip(".,)") for url in source_urls
            }:
                errors.append(f"claim ledger row {index} URL is missing from Sources consulted")
            if independent == "unknown":
                unknown_independent += 1
            if not ACCESS_DATE.fullmatch(accessed):
                errors.append(f"claim ledger row {index} has invalid access date")
            for label, value in (
                ("Primary", primary),
                ("Direct", direct),
                ("Current", current),
                ("Independent", independent),
            ):
                if value not in ALLOWED_BINARY_VALUES:
                    errors.append(f"claim ledger row {index} has invalid {label}: {value}")
            if verdict not in ALLOWED_VERDICTS:
                errors.append(f"claim ledger row {index} has invalid verdict: {verdict}")
        if claim_rows and unknown_independent * 2 > len(claim_rows):
            warnings.append(
                f"{unknown_independent} of {len(claim_rows)} claims have Independent: unknown"
            )

    findings = bodies.get("Findings")
    if findings is not None:
        for line in findings.splitlines():
            bare = strip_urls(line)
            if not (MONEY_OR_PERCENT.search(bare) or NUMBER_WITH_UNIT.search(bare)):
                continue
            if not (URL.search(line) and ACCESSED_INLINE.search(line)):
                errors.append(f"number without URL and access date in Findings: {line.strip()[:80]}")

    council = bodies.get("Council review")
    if council is not None:
        status = field_value(council, "Status")
        if status not in {"not run", "passed", "findings", "unverified"}:
            errors.append(f"invalid council status: {status or 'missing'}")
        if not field_value(council, "Reason"):
            errors.append("missing council reason")
        risk = field_value(bodies.get("Protocol", ""), "Risk")
        if risk == "high" and status == "not run":
            errors.append("Risk: high requires a council run; Status: not run")

    if sources is not None:
        source_lines = [line for line in sources.splitlines() if line.lstrip().startswith("-")]
        if not source_lines:
            errors.append("sources consulted has no entries")
        for index, line in enumerate(source_lines, start=1):
            if not URL.search(line) or not re.search(r"accessed \d{4}-\d{2}-\d{2}", line):
                errors.append(f"source entry {index} needs a URL and access date")

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("finding", type=Path)
    args = parser.parse_args()

    if not args.finding.is_file():
        print(f"Research finding not found: {args.finding}", file=sys.stderr)
        return 2

    errors, warnings = audit(args.finding.read_text(encoding="utf-8"), args.finding.name)
    for warning in warnings:
        print(f"WARN: {warning}", file=sys.stderr)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(f"Research finding audit passed: {args.finding}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
