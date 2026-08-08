#!/usr/bin/env python3
"""Build a self-contained Rule Curator HTML file from a rules JSON document.

Reads curator-template.html (which contains the placeholder token
__RULE_CURATOR_DATA__) and a rules JSON file, injects the data inline, and writes
one self-contained HTML file the user can open offline.

Standard library only; no third-party packages, so it runs in any environment.

    python build_curator.py rules.json -o rule-curator.html
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PLACEHOLDER = "__RULE_CURATOR_DATA__"
REQUIRED_KEYS = ("meta", "categories", "rules")

# Rule ids end up in HTML attributes and localStorage keys; category colors end
# up in style attributes. The template escapes both, but reject anything odd
# here too so a malformed rules.json fails loudly at build time.
ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
COLOR_RE = re.compile(r"^(#[0-9a-fA-F]{3,8}|[A-Za-z]+)$")


def fail(message):
    """Report a problem clearly and exit non-zero instead of punting."""
    print(f"build_curator: error: {message}", file=sys.stderr)
    sys.exit(1)


def load_rules(path):
    if not path.is_file():
        fail(f"rules file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"rules file is not valid JSON ({path}): {exc}")
    if not isinstance(data, dict):
        fail("rules JSON must be an object with meta / categories / rules")
    missing = [k for k in REQUIRED_KEYS if k not in data]
    if missing:
        fail(f"rules JSON missing required key(s): {', '.join(missing)}")
    if not isinstance(data["rules"], list):
        fail("rules JSON 'rules' must be a list")
    if not isinstance(data["categories"], list):
        fail("rules JSON 'categories' must be a list")
    seen_ids = set()
    for rule in data["rules"]:
        rule_id = rule.get("id") if isinstance(rule, dict) else None
        if not isinstance(rule_id, str) or not ID_RE.fullmatch(rule_id):
            fail(f"rule id must match [A-Za-z0-9_-]+, got: {rule_id!r}")
        if rule_id in seen_ids:
            fail(f"duplicate rule id: {rule_id!r}")
        seen_ids.add(rule_id)
    for cat in data["categories"]:
        color = cat.get("color") if isinstance(cat, dict) else None
        if color is not None and (not isinstance(color, str) or not COLOR_RE.fullmatch(color)):
            fail(f"category color must be a hex literal or CSS color name, got: {color!r}")
    return data


def load_template(path):
    if not path.is_file():
        fail(
            f"template not found: {path}\n"
            "Pass --template or run from the skill directory next to "
            "curator-template.html."
        )
    text = path.read_text(encoding="utf-8")
    if PLACEHOLDER not in text:
        fail(f"template is missing the {PLACEHOLDER} placeholder: {path}")
    return text


def embed(data):
    """Serialize for safe inline embedding inside a <script> element.

    Escaping <, >, & to their JSON unicode forms keeps the payload valid JSON
    while making it impossible for rule text containing '</script>' to break out
    of the script element.
    """
    # A build id namespaces the UI's localStorage so separate audits opened in
    # the same browser do not overwrite each other's keep/drop/modify decisions.
    data["meta"]["buildId"] = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw = json.dumps(data, ensure_ascii=False, indent=2)
    return raw.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build a self-contained Rule Curator HTML file.")
    parser.add_argument("rules", type=Path, help="path to the rules JSON file")
    parser.add_argument(
        "-o", "--output", type=Path, default=Path("rule-curator.html"),
        help="output HTML path (default: rule-curator.html)",
    )
    parser.add_argument(
        "-t", "--template", type=Path,
        default=Path(__file__).resolve().parent / "curator-template.html",
        help="template path (default: curator-template.html next to this script)",
    )
    args = parser.parse_args(argv)

    data = load_rules(args.rules)
    template = load_template(args.template)
    html = template.replace(PLACEHOLDER, embed(data))
    args.output.write_text(html, encoding="utf-8")

    print(f"Wrote {args.output} ({len(data['rules'])} rules). Open it in a browser.")


if __name__ == "__main__":
    main()
