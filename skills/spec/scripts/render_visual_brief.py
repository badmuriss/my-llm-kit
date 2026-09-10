#!/usr/bin/env python3
"""Render one canonical Markdown spec as an offline visual HTML/PDF brief."""
from __future__ import annotations

import argparse
import base64
import html
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

from visual_diagrams import cached_diagrams, digest, export_pdf, parse_diagrams, render_diagrams, validate_svg

MARKER = 'name="visual-brief-generator" content="my-llm-kit-v1"'
FENCE = re.compile(r"^```visual-brief[ \t]*\n(.*?)^```[ \t]*$", re.M | re.S)
MAX_SOURCE_BYTES = 262_144
MAX_HTML_BYTES = 20_000_000
CSS = (Path(__file__).parents[1] / "assets" / "visual-brief.css").read_text(encoding="utf-8")


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


def _gallery(diagrams: list[dict[str, str]], svgs: list[str], pt: bool) -> str:
    if len(diagrams) != len(svgs):
        raise ValueError("every Mermaid diagram must be rendered; no text-only fallback")
    if not diagrams:
        return ""
    rows = []
    for diagram, svg in zip(diagrams, svgs):
        encoded = base64.b64encode(validate_svg(svg).encode()).decode()
        rows.append(f'''<figure class="diagram"><h3>{html.escape(diagram['title'])}</h3>
<div class="diagram-frame"><img data-mermaid-sha256="{diagram['sha256']}" alt="{html.escape(diagram['description'])}" src="data:image/svg+xml;base64,{encoded}"></div>
<figcaption>{html.escape(diagram['description'])}</figcaption>
<details class="diagram-source"><summary>{'Ver código Mermaid' if pt else 'View Mermaid source'}</summary><pre>{html.escape(diagram['code'])}</pre></details></figure>''')
    return f'<section class="diagrams" id="diagrams"><h2>{"Fluxos e relações" if pt else "Flows and relationships"}</h2>{"".join(rows)}</section>'


def render(source: str, source_name: str, svgs: list[str] | None = None) -> str:
    data = parse_brief(source)
    diagrams = parse_diagrams(source)
    images = svgs or []
    gallery = _gallery(diagrams, images, data.get("language") == "pt-BR")
    e = html.escape
    pt = data.get("language") == "pt-BR"
    def label(en: str, br: str) -> str:
        return br if pt else en
    flow = "".join(f'<li><h3>{e(row["title"])}</h3><p>{e(row["detail"])}</p></li>' for row in data["flow"])
    checks = "".join(f'<tr><td>{e(row["criterion"])}</td><td>{e(row["evidence"])}</td></tr>' for row in data["checks"])
    risks = "".join(f'<article class="risk"><h3>{e(row["symptom"])}</h3><p><strong>{label("Inspect", "Onde olhar")}:</strong> {e(row["inspect"])}</p><p><strong>{label("Recovery", "Recuperação")}:</strong> {e(row["recovery"])}</p></article>' for row in data["risks"])
    def items(key: str) -> str:
        return "<ul>" + "".join(f"<li>{e(item)}</li>" for item in data[key]) + "</ul>" if data[key] else f'<p>{label("None recorded.", "Nenhum item registrado.")}</p>'
    diagram_link = f'<a href="#diagrams">{label("Diagrams", "Diagramas")}</a>' if diagrams else ""
    return f'''<!doctype html>
<html lang="{data.get('language', 'en')}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta {MARKER}><meta name="spec-sha256" content="{digest(source)}"><meta name="diagrams-sha256" content="{digest(json.dumps(images))}">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'">
<title>{e(data['title'])}</title><style>{CSS}</style></head><body><main>
<header><div class="eyebrow">{label('Visual specification / planning snapshot', 'Especificação visual / retrato do planejamento')}</div><h1>{e(data['title'])}</h1><p class="summary">{e(data['summary'])}</p></header>
<div class="notice"><strong>{label('Proposed, not execution evidence.', 'Proposta, não evidência de execução.')}</strong> {label('No approval, passing check or live status is implied by this page.', 'Esta página não significa aprovação, teste aprovado ou acompanhamento ao vivo.')}</div>
<nav aria-label="{label('Sections', 'Seções')}"><a href="#change">{label('Change', 'Mudança')}</a><a href="#flow">{label('Flow', 'Fluxo')}</a>{diagram_link}<a href="#checks">{label('Acceptance', 'Aceite')}</a><a href="#risks">{label('Failures', 'Falhas')}</a></nav>
<h2 id="change">{label('What changes', 'O que muda')}</h2><div class="pair"><section><h3>{label('Before', 'Antes')}</h3><p>{e(data['before'])}</p></section><section><h3>{label('After', 'Depois')}</h3><p>{e(data['after'])}</p></section></div>
<h2 id="flow">{label('Decision flow', 'Fluxo de decisão')}</h2><ol class="flow">{flow}</ol>
<h2 id="checks">{label('How we will verify it', 'Como vamos verificar')}</h2><table><thead><tr><th>{label('Criterion', 'Critério')}</th><th>{label('Required evidence', 'Evidência necessária')}</th></tr></thead><tbody>{checks}</tbody></table>
{gallery}
<section class="secondary"><h2 id="risks">{label('When something goes wrong', 'Quando algo der errado')}</h2>{risks}<h2>{label('Decisions and tradeoffs', 'Decisões e escolhas')}</h2>{items('decisions')}<h2>{label('Outside this scope', 'Fora deste escopo')}</h2>{items('excluded')}</section>
<details open><summary>{label('Source and traceability', 'Fonte e rastreabilidade')}</summary><p>{e(source_name)}</p><code>SHA-256: {digest(source)}</code><p>{label('Regenerate after changing the spec. This is a static derived view, not another source of truth.', 'Gere novamente após mudar a spec. Esta é uma visão estática derivada, não outra fonte da verdade.')}</p></details>
<p class="footer">{label('Open locally. Print to PDF through the browser. No scripts, remote fonts or network requests.', 'Abra localmente. Imprima em PDF pelo navegador. Sem scripts, fontes remotas ou requisições de rede.')}</p>
</main></body></html>\n'''


def check_fresh(source: str, output: str) -> bool:
    return MARKER in output and f'name="spec-sha256" content="{digest(source)}"' in output


def _existing(path: Path) -> str:
    if path.stat().st_size > MAX_HTML_BYTES:
        raise ValueError("existing visual brief exceeds the size limit")
    return path.read_text(encoding="utf-8")


def _destination(source: Path, output: Path, pdf: Path | None) -> None:
    if output.resolve() == source.resolve() or output.suffix.lower() != ".html" or output.is_symlink():
        raise ValueError("output must be a separate, non-symlink HTML file")
    if output.exists() and MARKER not in _existing(output):
        raise ValueError("refusing to overwrite an unrelated HTML file")
    if pdf is not None and (pdf.suffix.lower() != ".pdf" or pdf.exists() or pdf.is_symlink() or pdf.resolve() in {source.resolve(), output.resolve()}):
        raise ValueError("PDF output must be a new, separate .pdf file; choose a new name or remove your old export")


def _publish(output: Path, content: str) -> None:
    descriptor, temporary = tempfile.mkstemp(dir=output.parent, suffix=".html")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(temporary, output)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true", help="verify source, images and HTML without a browser or writes")
    parser.add_argument("--pdf", type=Path, help="export the same HTML to a new PDF using local Chromium")
    parser.add_argument("--mmdc", help="installed Mermaid CLI executable; no automatic installation")
    parser.add_argument("--browser", help="local Chromium/Chrome executable for Mermaid and PDF")
    args = parser.parse_args(argv)
    try:
        if args.check and args.pdf:
            raise ValueError("--check is read-only and cannot be combined with --pdf")
        if args.source.stat().st_size > MAX_SOURCE_BYTES:
            raise ValueError("spec exceeds the bounded source size")
        source = args.source.read_text(encoding="utf-8")
        parse_brief(source)
        diagrams = parse_diagrams(source)
        _destination(args.source, args.output, args.pdf)
        if args.check:
            existing = _existing(args.output)
            if not check_fresh(source, existing) or existing != render(source, args.source.name, cached_diagrams(existing, diagrams)):
                raise ValueError("visual brief is stale, modified, or generated by a different renderer")
            print("Visual brief source, diagrams and content match.")
            return 0
        images = render_diagrams(diagrams, mmdc=args.mmdc, browser=args.browser)
        rendered = render(source, args.source.name, images)
        # Complete all fallible rendering before replacing any existing document.
        with tempfile.TemporaryDirectory(prefix="visual-brief-") as directory:
            temporary_html = Path(directory) / "brief.html"
            temporary_html.write_text(rendered, encoding="utf-8")
            temporary_pdf = Path(directory) / "brief.pdf"
            if args.pdf:
                export_pdf(temporary_html, temporary_pdf, browser=args.browser)
                args.pdf.parent.mkdir(parents=True, exist_ok=True)
                with args.pdf.open("xb") as target:
                    target.write(temporary_pdf.read_bytes())
            args.output.parent.mkdir(parents=True, exist_ok=True)
            _publish(args.output, rendered)
        print(f"Visual brief written: {args.output} ({len(diagrams)} Mermaid diagrams)")
        if args.pdf:
            print(f"PDF written: {args.pdf}")
        return 0
    except (OSError, UnicodeError, ValueError) as error:
        print(f"Cannot render visual brief: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
