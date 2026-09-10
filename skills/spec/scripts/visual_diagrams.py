"""Local Mermaid rendering and safe, self-contained SVG images for visual briefs."""
from __future__ import annotations

import base64
import hashlib
import json
import math
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

MAX_DIAGRAMS = 6
MAX_CODE_CHARS = 12_000
MAX_SVG_BYTES = 2_000_000
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})([^\r\n]*)$")
TYPES = frozenset({"flowchart", "graph", "sequenceDiagram", "stateDiagram", "stateDiagram-v2", "classDiagram", "erDiagram"})
TAGS = frozenset({"svg", "g", "defs", "path", "rect", "polygon", "polyline", "circle", "ellipse", "line", "text", "tspan", "title", "desc", "style", "marker", "clipPath", "linearGradient", "radialGradient", "stop", "symbol", "use", "filter", "feDropShadow"})
IMAGE = re.compile(r'<img data-mermaid-sha256="([a-f0-9]{64})" alt="[^"]*" src="data:image/svg\+xml;base64,([A-Za-z0-9+/=]+)">')
NETWORK_ARGS = ["--disable-background-networking"]


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _diagram(code: str, heading: str) -> dict[str, str]:
    if not code.strip() or len(code) > MAX_CODE_CHARS:
        raise ValueError("Mermaid diagram is empty or too large; split the view")
    meaningful = [line.strip() for line in code.splitlines() if line.strip() and not line.strip().startswith("%%")]
    if not meaningful or meaningful[0].split()[0].rstrip(";") not in TYPES:
        raise ValueError("use a Mermaid flowchart, sequence, state, class or ER diagram without frontmatter")
    # Per-diagram configuration must not override the renderer's security policy.
    if "%%{" in code or re.search(r"https?:|file:|data:|javascript:|ftp:|//|@import|<\s*(?:script|img|iframe|a)\b|\b(?:img|icon)\s*:", code, re.I):
        raise ValueError("Mermaid directives, external resources and active links are not allowed")
    title = re.search(r"^\s*accTitle\s*:\s*(.+)$", code, re.M)
    description = re.search(r"^\s*accDescr\s*:\s*(.+)$", code, re.M)
    name = title.group(1).strip() if title else heading
    if not name or len(name) > 160:
        raise ValueError("each Mermaid diagram needs a short heading or accTitle")
    return {"code": code, "title": name, "description": description.group(1).strip() if description else name, "sha256": digest(code)}


def parse_diagrams(source: str) -> list[dict[str, str]]:
    """Recognize real Markdown fences, not examples nested in a longer fence."""
    result: list[dict[str, str]] = []
    opened: str | None = None
    language = heading = ""
    lines: list[str] = []
    for line in source.splitlines():
        fence = FENCE.match(line)
        if opened is not None:
            if fence and not fence[2].strip() and fence[1][0] == opened[0] and len(fence[1]) >= len(opened):
                if language == "mermaid":
                    result.append(_diagram("\n".join(lines) + "\n", heading))
                opened = None
            else:
                lines.append(line)
        elif fence:
            opened, language, lines = fence[1], fence[2].strip().lower(), []
        elif re.match(r"^#{1,6}\s+", line):
            heading = re.sub(r"^#{1,6}\s+", "", line).strip().rstrip("#").strip()
    if opened is not None and language == "mermaid":
        raise ValueError("unclosed Mermaid fence")
    if len(result) > MAX_DIAGRAMS:
        raise ValueError("at most six diagrams per brief; split larger views")
    return result


def validate_svg(svg: str) -> str:
    """Fail closed on active content; images are additionally isolated by <img>."""
    if len(svg.encode()) > MAX_SVG_BYTES or re.search(r"<!DOCTYPE|<!ENTITY", svg, re.I):
        raise ValueError("unsafe or oversized Mermaid SVG")
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as error:
        raise ValueError("Mermaid did not produce valid SVG") from error
    if root.tag != "{http://www.w3.org/2000/svg}svg":
        raise ValueError("Mermaid output must be an SVG document")
    try:
        view = [float(value) for value in root.attrib["viewBox"].replace(",", " ").split()]
        if len(view) != 4 or not all(math.isfinite(value) for value in view) or min(view[2:]) <= 0:
            raise ValueError
    except (KeyError, ValueError) as error:
        raise ValueError("Mermaid SVG needs a finite, positive viewBox") from error
    for element in root.iter():
        tag = element.tag.removeprefix("{http://www.w3.org/2000/svg}")
        if tag not in TAGS:
            safe_tag = re.sub(r"[^a-zA-Z0-9_-]", "?", tag.rsplit("}", 1)[-1])[:80]
            raise ValueError(f"Mermaid SVG contains unsupported element {safe_tag} with {len(element)} children")
        for attribute, value in element.attrib.items():
            local = attribute.rsplit("}", 1)[-1].lower()
            if local.startswith("on") or (local in {"href", "src"} and not value.startswith("#")):
                raise ValueError("Mermaid SVG contains an event or external reference")
        styling = (element.text or "") if tag == "style" else element.get("style", "")
        attributes = " ".join(element.attrib.values())
        if re.search(r"@import|https?:|file:|data:|javascript:|//|\\", styling, re.I):
            raise ValueError("Mermaid SVG contains unsafe styles")
        if any(not target.strip(" \"'").startswith("#") for target in re.findall(r"url\(([^)]*)\)", styling + attributes, re.I)):
            raise ValueError("Mermaid SVG contains an external resource")
    return svg


def _executable(name: str | None, default: str) -> str:
    resolved = shutil.which(name or default)
    if not resolved:
        raise ValueError(f"{default} is unavailable; install the optional local visual tools or pass its executable path")
    return resolved


def run_tool(command: list[str], *, timeout: int = 90) -> None:
    # Never include tool stderr (which may contain authored source) in errors.
    with tempfile.TemporaryFile() as log:
        try:
            process = subprocess.run(command, stdout=log, stderr=log, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ValueError("local visual renderer could not finish; check installation and diagram syntax") from error
        if process.returncode:
            raise ValueError("local visual renderer failed; check installation and diagram syntax")


def render_diagrams(diagrams: list[dict[str, str]], *, mmdc: str | None = None, browser: str | None = None) -> list[str]:
    if not diagrams:
        return []
    executable = _executable(mmdc, "mmdc")
    with tempfile.TemporaryDirectory(prefix="visual-mermaid-") as directory:
        work = Path(directory)
        config = work / "mermaid.json"
        launch: dict[str, Any] = {"args": NETWORK_ARGS.copy()}
        if browser:
            launch["executablePath"] = _executable(browser, "chromium")
        puppeteer = work / "puppeteer.json"
        puppeteer.write_text(json.dumps(launch), encoding="utf-8")
        rendered = []
        for diagram in diagrams:
            config.write_text(json.dumps({"securityLevel": "strict", "htmlLabels": False, "flowchart": {"htmlLabels": False}, "theme": "neutral", "deterministicIds": True, "deterministicIDSeed": diagram["sha256"]}), encoding="utf-8")
            src, out = work / "diagram.mmd", work / "diagram.svg"
            src.write_text(diagram["code"], encoding="utf-8")
            out.unlink(missing_ok=True)
            run_tool([executable, "-i", str(src), "-o", str(out), "-c", str(config), "-p", str(puppeteer), "-b", "transparent"])
            if not out.exists() or out.stat().st_size > MAX_SVG_BYTES:
                raise ValueError("Mermaid output is absent or exceeds the size limit")
            rendered.append(validate_svg(out.read_text(encoding="utf-8")))
        return rendered


def cached_diagrams(output: str, diagrams: list[dict[str, str]]) -> list[str]:
    matches = IMAGE.findall(output)
    if len(matches) != len(diagrams):
        raise ValueError("rendered Mermaid diagrams are missing or modified")
    svgs = []
    for (sha, encoded), diagram in zip(matches, diagrams):
        if sha != diagram["sha256"] or len(encoded) > MAX_SVG_BYTES * 2:
            raise ValueError("rendered Mermaid source is stale")
        try:
            svgs.append(validate_svg(base64.b64decode(encoded, validate=True).decode("utf-8")))
        except (ValueError, UnicodeError) as error:
            raise ValueError("invalid embedded Mermaid SVG") from error
    return svgs


def export_pdf(html_path: Path, pdf_path: Path, *, browser: str | None = None) -> None:
    executable = _executable(browser, "chromium")
    with tempfile.TemporaryDirectory(prefix="visual-pdf-") as directory:
        run_tool([executable, "--headless", "--disable-gpu", "--no-first-run", "--no-default-browser-check", *NETWORK_ARGS,
                  f"--user-data-dir={directory}", "--no-pdf-header-footer",
                  f"--print-to-pdf={pdf_path.resolve()}", html_path.resolve().as_uri()])
    if not pdf_path.is_file() or pdf_path.read_bytes()[:5] != b"%PDF-":
        raise ValueError("browser did not produce a PDF")
