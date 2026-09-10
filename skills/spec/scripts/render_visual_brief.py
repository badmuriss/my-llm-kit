#!/usr/bin/env python3
"""Render a human-readable planning view from one canonical Markdown spec."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

MARKER = 'name="visual-brief-generator" content="my-llm-kit-v1"'
FENCE = re.compile(r"^```visual-brief[ \t]*\n(.*?)^```[ \t]*$", re.M | re.S)
MAX_SOURCE_BYTES = 262_144
CSS = """
:root{color-scheme:light;font-family:system-ui,-apple-system,Segoe UI,sans-serif;color:#17243b;background:#edf1f5}
*{box-sizing:border-box}body{margin:0}main{max-width:1100px;margin:32px auto;padding:40px;background:white;border-radius:14px}
header{border-top:7px solid #166b70;padding-top:20px}h1{font-size:34px;line-height:1.14;margin:14px 0}h2{font-size:20px;margin:28px 0 12px}h3{font-size:16px;margin:0 0 7px}p,li,td{font-size:15px;line-height:1.5;overflow-wrap:anywhere}p{margin:6px 0 12px}.eyebrow{font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:#516176}.summary{font-size:18px;max-width:900px}.notice{border-left:4px solid #b57312;background:#fff5df;padding:12px 16px;margin:20px 0;font-size:14px}.pair{display:flex;gap:18px}.pair>section{flex:1;border:1px solid #d4dde6;border-radius:10px;padding:18px}.pair>section:last-child{background:#edf8f6;border-color:#9bc8c2}.flow{list-style:none;padding:0;counter-reset:step}.flow li{counter-increment:step;position:relative;border-left:2px solid #b8d3d0;padding:0 0 18px 26px;margin-left:15px}.flow li:before{content:counter(step);position:absolute;left:-15px;top:0;background:#166b70;color:white;width:28px;height:28px;border-radius:50%;text-align:center;line-height:28px;font-size:13px}.flow li:last-child{border-color:transparent;padding-bottom:0}.flow p{margin:0;color:#516176}.flow h3{padding-top:3px}table{border-collapse:collapse;width:100%;table-layout:fixed}th,td{text-align:left;padding:12px;border-bottom:1px solid #d4dde6;vertical-align:top}th{background:#eef3f6;font-size:13px}td:first-child{font-weight:600}details{border-top:1px solid #d4dde6;margin-top:24px;padding-top:12px}summary{cursor:pointer;font-weight:600}code{font:12px ui-monospace,monospace;overflow-wrap:anywhere}.footer{font-size:12px;color:#516176;margin-top:24px}.risk{border:1px solid #e6d1af;border-left:4px solid #b57312;padding:14px 18px;margin:12px 0;border-radius:8px}.risk p{font-size:14px}.risk strong{color:#17243b}nav{display:flex;gap:16px;flex-wrap:wrap;margin:24px 0}a{color:#166b70}.secondary{margin-top:26px}
@media(max-width:680px){main{margin:0;padding:22px;border-radius:0}.pair{display:block}.pair>section{margin-bottom:12px}h1{font-size:28px}th,td{padding:8px}}
@media print{:root{background:white}@page{size:A4;margin:15mm}html,body{background:white}main{margin:0;padding:0;max-width:none;border-radius:0}h1{font-size:26px}h2{font-size:17px;margin-top:18px}p,li,td{font-size:11px}h3{font-size:12px}.summary{font-size:13px}.notice{font-size:10px}nav{display:none}.pair>section{padding:12px}.flow li{padding-bottom:12px}.flow p{font-size:11px}.flow li:before{width:23px;height:23px;line-height:23px;left:-12px}.risk p{font-size:11px}.secondary{break-before:page}h2,h3{break-after:avoid}tr,.risk,.flow li{break-inside:avoid}thead{display:table-header-group}details{display:block}details>*{display:block}.footer{font-size:9px}}
"""


def _text(value: Any, field: str, maximum: int = 800) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{field} must be nonempty text of at most {maximum} characters")
    return value


def parse_brief(source: str) -> dict[str, Any]:
    if len(source.encode()) > MAX_SOURCE_BYTES:
        raise ValueError("spec exceeds the bounded source size")
    matches = FENCE.findall(source)
    if len(matches) != 1:
        raise ValueError("the canonical spec must contain exactly one visual-brief JSON fence")
    try:
        data = json.loads(matches[0])
    except json.JSONDecodeError as error:
        raise ValueError("visual-brief contains invalid JSON") from error
    required = {"schema_version", "title", "summary", "before", "after", "flow", "checks", "risks", "decisions", "excluded"}
    if not isinstance(data, dict) or set(data) - {"language"} != required:
        raise ValueError("visual-brief has missing or unknown fields")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("unsupported visual-brief schema")
    if data.get("language", "en") not in {"en", "pt-BR"}:
        raise ValueError("supported languages are en and pt-BR")
    for key in ("title", "summary", "before", "after"):
        _text(data[key], key, 160 if key == "title" else 800)
    for key, fields, limit in (
        ("flow", {"title", "detail"}, 6),
        ("checks", {"criterion", "evidence"}, 12),
        ("risks", {"symptom", "inspect", "recovery"}, 8),
    ):
        rows = data[key]
        if not isinstance(rows, list) or not 1 <= len(rows) <= limit:
            raise ValueError(f"{key} must contain 1 to {limit} entries; split larger views")
        for row in rows:
            if not isinstance(row, dict) or set(row) != fields:
                raise ValueError(f"invalid {key} entry")
            for field in fields:
                _text(row[field], f"{key}.{field}", 400)
    for key in ("decisions", "excluded"):
        if not isinstance(data[key], list) or len(data[key]) > 12:
            raise ValueError(f"{key} must contain at most 12 entries")
        for item in data[key]:
            _text(item, key, 400)
    return data


def render(source: str, source_name: str) -> str:
    data = parse_brief(source)
    e = html.escape
    pt = data.get("language") == "pt-BR"
    def label(en: str, br: str) -> str:
        return br if pt else en
    digest = hashlib.sha256(source.encode()).hexdigest()
    flow = "".join(f'<li><h3>{e(row["title"])}</h3><p>{e(row["detail"])}</p></li>' for row in data["flow"])
    checks = "".join(f'<tr><td>{e(row["criterion"])}</td><td>{e(row["evidence"])}</td></tr>' for row in data["checks"])
    risks = "".join(f'<article class="risk"><h3>{e(row["symptom"])}</h3><p><strong>{label("Inspect", "Onde olhar")}:</strong> {e(row["inspect"])}</p><p><strong>{label("Recovery", "Recuperação")}:</strong> {e(row["recovery"])}</p></article>' for row in data["risks"])
    def items(key: str) -> str:
        return "<ul>" + "".join(f"<li>{e(item)}</li>" for item in data[key]) + "</ul>" if data[key] else f'<p>{label("None recorded.", "Nenhum item registrado.")}</p>'
    return f'''<!doctype html>
<html lang="{data.get('language', 'en')}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta {MARKER}><meta name="spec-sha256" content="{digest}">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>{e(data['title'])}</title><style>{CSS}</style></head><body><main>
<header><div class="eyebrow">{label('Visual specification / planning snapshot', 'Especificação visual / retrato do planejamento')}</div><h1>{e(data['title'])}</h1><p class="summary">{e(data['summary'])}</p></header>
<div class="notice"><strong>{label('Proposed, not execution evidence.', 'Proposta, não evidência de execução.')}</strong> {label('No approval, passing check or live status is implied by this page.', 'Esta página não significa aprovação, teste aprovado ou acompanhamento ao vivo.')}</div>
<nav aria-label="{label('Sections', 'Seções')}"><a href="#change">{label('Change', 'Mudança')}</a><a href="#flow">{label('Flow', 'Fluxo')}</a><a href="#checks">{label('Acceptance', 'Aceite')}</a><a href="#risks">{label('Failures', 'Falhas')}</a></nav>
<h2 id="change">{label('What changes', 'O que muda')}</h2><div class="pair"><section><h3>{label('Before', 'Antes')}</h3><p>{e(data['before'])}</p></section><section><h3>{label('After', 'Depois')}</h3><p>{e(data['after'])}</p></section></div>
<h2 id="flow">{label('Decision flow', 'Fluxo de decisão')}</h2><ol class="flow">{flow}</ol>
<h2 id="checks">{label('How we will verify it', 'Como vamos verificar')}</h2><table><thead><tr><th>{label('Criterion', 'Critério')}</th><th>{label('Required evidence', 'Evidência necessária')}</th></tr></thead><tbody>{checks}</tbody></table>
<section class="secondary"><h2 id="risks">{label('When something goes wrong', 'Quando algo der errado')}</h2>{risks}<h2>{label('Decisions and tradeoffs', 'Decisões e escolhas')}</h2>{items('decisions')}<h2>{label('Outside this scope', 'Fora deste escopo')}</h2>{items('excluded')}</section>
<details open><summary>{label('Source and traceability', 'Fonte e rastreabilidade')}</summary><p>{e(source_name)}</p><code>SHA-256: {digest}</code><p>{label('Regenerate after changing the spec. This is a static derived view, not another source of truth.', 'Gere novamente após mudar a spec. Esta é uma visão estática derivada, não outra fonte da verdade.')}</p></details>
<p class="footer">{label('Open locally. Print to PDF through the browser. No scripts, remote fonts or network requests.', 'Abra localmente. Imprima em PDF pelo navegador. Sem scripts, fontes remotas ou requisições de rede.')}</p>
</main></body></html>\n'''


def check_fresh(source: str, output: str) -> bool:
    digest = hashlib.sha256(source.encode()).hexdigest()
    return MARKER in output and f'name="spec-sha256" content="{digest}"' in output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true", help="check source fingerprint without writing")
    args = parser.parse_args(argv)
    try:
        if args.source.stat().st_size > MAX_SOURCE_BYTES:
            raise ValueError("spec exceeds the bounded source size")
        source = args.source.read_text(encoding="utf-8")
        rendered = render(source, args.source.name)
        if args.output.resolve() == args.source.resolve() or args.output.suffix.lower() != ".html" or args.output.is_symlink():
            raise ValueError("output must be a separate, non-symlink HTML file")
        if args.check:
            existing = args.output.read_text(encoding="utf-8")
            if not check_fresh(source, existing) or existing != rendered:
                raise ValueError("visual brief is stale, modified, or generated by a different renderer")
            print("Visual brief source fingerprint matches.")
            return 0
        if args.output.exists() and MARKER not in args.output.read_text(encoding="utf-8"):
            raise ValueError("refusing to overwrite an unrelated HTML file")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(dir=args.output.parent, suffix=".html")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(rendered)
            os.replace(temporary, args.output)
        finally:
            Path(temporary).unlink(missing_ok=True)
        print(f"Visual brief written: {args.output}")
        return 0
    except (OSError, UnicodeError, ValueError) as error:
        print(f"Cannot render visual brief: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
