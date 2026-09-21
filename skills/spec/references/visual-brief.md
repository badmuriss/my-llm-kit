# Human-readable visual specification

Help the owner understand and challenge a proposed change before implementation,
and locate evidence after failure. A diagram is not acceptance evidence. Keep the
canonical decision/spec; derive the HTML and PDF from it, not another plan.

## Choose the view by the question

| Question | Useful view |
|---|---|
| What changes and why? | Before/after comparison and decision alternatives |
| Which systems depend on each other? | Small architecture or data-flow diagram |
| What happens over time, including retries? | Sequence or state diagram with failure paths |
| What does the user interact with? | Wireframe or screen flow, including empty/error states |
| How will we know it works? | Criterion-to-check/evidence table |
| Where should I look after a failure? | Symptom, evidence locator, owner and recovery table |

A worker dependency graph is not the software architecture. Label boundaries,
arrows and their meanings. Expose detail progressively; use color plus text, not
color alone. Substantial plans should explain objective, changes, choices,
exclusions, acceptance and failure/recovery. Trivial edits need no report pack.

## One source, including Mermaid

Put exactly one `visual-brief` JSON fence and the relevant standard `mermaid`
fences in the existing Markdown spec. Follow
[`visual-brief-example.md`](../assets/visual-brief-example.md). Write each diagram
under a short heading, preferably with `accTitle` and a one-line `accDescr`.
Use a flowchart, sequence, state, class or ER diagram. Keep at most six diagrams,
12,000 characters each. Split complex views instead of shrinking unreadable text.
Do not force a diagram when a comparison or short explanation is clearer.

The renderer embeds locally produced SVGs as isolated data images. HTML needs no
JavaScript, CDN, network requests or adjacent asset files. Mermaid source remains
available in collapsible details for editing; print hides those code blocks and
keeps the diagrams and captions. Missing tools or invalid diagrams fail the build,
not silently fall back to raw Mermaid in a supposedly complete PDF.

PDF is the default deliverable, with offline HTML as a companion. Even without
Mermaid, PDF export needs Python and local Chromium/Chrome. Install optional
Mermaid tooling explicitly when needed, not on every core install:

```sh
npm install --prefix "<installed-spec>/tools"
python3 "<installed-spec>/scripts/render_visual_brief.py" "<project>/decisions/<slug>.md" \
  --output "<project>/decisions/<slug>.html" \
  --mmdc "<installed-spec>/tools/node_modules/.bin/mmdc" \
  --browser /path/to/chrome
```

An existing `mmdc` on PATH works without `--mmdc`. The npm dependency installs a
local Mermaid CLI and Puppeteer browser; nothing is added globally. With an
existing Chromium/Chrome, use `PUPPETEER_SKIP_DOWNLOAD=1` during installation and
pass `--browser /path/to/chrome`. No package installation happens in the renderer.
On Windows use `py -3` and the installed `mmdc.cmd`; native Windows is unverified.
Resolve all skill scripts from their installed directory, not the consumer repo.

## PDF from the same rendered HTML

```sh
python3 "<installed-spec>/scripts/render_visual_brief.py" "<project>/decisions/<slug>.md" \
  --output "<project>/decisions/<slug>.html" \
  --mmdc "<installed-spec>/tools/node_modules/.bin/mmdc" \
  --browser /path/to/chrome --pdf "<project>/decisions/<slug>.pdf"
```

Omit `--pdf` to write beside the HTML with the same stem and `.pdf` extension.
Omit `--mmdc` for specs without Mermaid. Export requires local Chromium or Chrome
(defaults to `chromium` on PATH); it refuses to overwrite an existing PDF.
Choose a new export name or explicitly remove your previous export. The browser sandbox remains enabled; configure a supported local browser rather
than disabling its protections. Renderer subprocesses have finite timeouts and
fixed Mermaid security configuration. No private diagram is sent to a public
rendering service.

`--html-only` is an explicit exception for a user-requested HTML deliverable or
local template development; a plain brief then needs Python only. It must not
silently replace a required PDF. Missing browser or failed export returns an
error without replacing the existing HTML. `--pdf` and `--html-only` are mutually
exclusive. Existing scripts that intentionally need HTML alone must add
`--html-only`; `--check` remains read-only and needs no browser.

## Template and typography

Reuse `assets/visual-brief.css`: white paper, graphite text, Inter variable,
numbered sections, ruled comparisons and tables, restrained spacing. Avoid
decorative dashboard cards, oversized cover-only pages and tiny print text.
The A4 stylesheet uses 10.5pt body text, repeating table headings, kept-together
rows and page numbers. Long content flows across pages; never clamp or truncate
the summary to fit a page. Keep diagrams readable and split an overfull diagram
at the source instead of reducing its text indefinitely.

The renderer embeds `assets/fonts/InterVariable.woff2` and its OFL license in the
offline HTML. Do not replace it with a CDN dependency. Font source:
https://github.com/rsms/inter/tree/master/docs/font-files, license in
`assets/fonts/OFL.txt`, retrieved 2026-09-20. Design direction, researched with
Refero on that date: Vectary's white technical-document structure and Inter
hierarchy; Expo's restrained technical typography. The
incredibly-pretty-websites skill informed spacing, responsive type and print
polish, not a new runtime dependency.

Check freshness without rerendering Mermaid, starting a browser or writing:

```sh
python3 "<installed-spec>/scripts/render_visual_brief.py" "<project>/decisions/<slug>.md" \
  --output "<project>/decisions/<slug>.html" --check
```

This verifies source identity, the embedded-image digest and exact HTML content.
It does not approve the spec, validate diagram semantics or certify a separately
edited PDF. Source changes require regeneration, including the PDF export.
Unrelated HTML and symlink outputs are not overwritten. Inputs are escaped;
Mermaid config directives, remote resources and active SVG/HTML are rejected.

## Handoff and execution evidence

Link the PDF first in the handoff, optionally followed by HTML and canonical
Markdown. Do not make the user export it themselves. Present the visual brief
before substantial code changes. Existing authorization
still applies: do not manufacture another approval round. Stop for a genuine
scope/risk decision or an existing approval requirement. Check diagram semantics
against the spec and inspect desktop, tablet/mobile and printed views for clipped
labels, overlap, unreadable scaling and missing arrows. Rasterize and inspect
every page of the actual PDF, not just the browser's print-media preview. Check
that embedded fonts loaded and no content disappeared at page boundaries.
A render/build alone is
not visual acceptance. Reuse the template and fix concrete defects, not endless
cosmetic passes.

The page is a static planning snapshot, not a live dashboard. Actual execution
views must derive from the existing verified journal and check receipts,
preserving generation and source identity. Never invent another status ledger.
Keep rendered HTML/PDF/SVG out of recurrent model context. Return paths, source
fingerprint and the relevant change summary; regenerate after source changes,
not after every worker poll.

Mermaid is the default relational view here; draw.io remains an optional editor,
not an installed MCP dependency. C4 levels are selected for useful questions,
not as a mandatory four-level documentation exercise.

Primary references accessed 2026-09-10:
https://github.com/mermaid-js/mermaid-cli
https://mermaid.js.org/config/usage.html
https://mermaid.js.org/config/schema-docs/config.html
https://www.drawio.com/docs/manual/mermaid/
https://www.drawio.com/docs/manual/generate/drawio-mcp-server/
https://c4model.com/diagrams
https://c4model.com/tooling
