# Human-readable visual specification

The owner must be able to understand the proposed change, challenge a decision
before implementation, and find the right evidence when something fails. A
pretty diagram is not acceptance evidence. Keep the canonical decision/spec;
render a view of it rather than maintaining a second independent plan.

## What to present

For substantial planning, show a compact overview containing the objective,
before/after behavior, important decisions and exclusions, verification criteria,
and failure/recovery paths. Make unverified assumptions visible. Expose technical
detail progressively instead of putting every file and agent in one diagram.

Choose visuals by the question, not by the available tool:

| Question | Useful view |
|---|---|
| What changes and why? | Before/after cards and decision alternatives |
| Which systems depend on each other? | A small architecture/data-flow diagram |
| What happens over time, including retries? | Sequence or state diagram with failure paths |
| What does the user interact with? | Wireframe or screen flow, including empty/error states |
| How will we know it works? | Criterion-to-check/evidence table |
| Where should I look after a failure? | Symptom, evidence locator, owner and recovery table |

The worker dependency graph is not the software architecture. Label the system
boundary, arrows and their meanings. Use color plus text, not color alone. A
simple task should receive a short explanation, not a compulsory report pack.

## Included renderer

The dependency-free script reads exactly one `visual-brief` JSON fence in the
existing Markdown spec. Use the field shape in
[`visual-brief-example.md`](../assets/visual-brief-example.md). This is bounded
presentation metadata inside the canonical spec, not another scheduler, task
ledger or separately maintained JSON file. Detailed reasoning stays in that same
spec; the visual overview need not reproduce it verbatim.

```text
python3 "<installed-spec>/scripts/render_visual_brief.py" "<project>/decisions/<slug>.md" --output "<project>/decisions/<slug>.html"
python3 "<installed-spec>/scripts/render_visual_brief.py" "<project>/decisions/<slug>.md" --output "<project>/decisions/<slug>.html" --check
```

On Windows use `py -3`. Resolve the script from the installed skill, not the
consumer project's checkout. Open the HTML locally; it contains no JavaScript,
CDN dependency, remote fonts or network calls. It supports section navigation,
progressive source details, a before/after comparison, an ordered decision flow,
acceptance evidence and troubleshooting cards. Print the same page to PDF when
requested or useful for sharing; do not author another independent PDF document.

The source hash and proposed/not-executed notice remain visible. `--check`
compares both the source fingerprint and the generated content. It never approves
the spec or the code. The renderer refuses to overwrite an unrelated HTML file.
The input limits keep the overview legible; split a larger view rather than
shrinking text or silently dropping content.

## Rich diagrams and portability

The included ordered flow is an overview, not a general graph renderer. Use an
existing Mermaid renderer for relational/sequence diagrams, or draw.io when
editable canvas layout adds value. No MCP or renderer installation is required
for the included overview, and none is automatically added to the global stack.
Keep diagram source near the canonical spec and embed a locally rendered SVG
when composing a richer view. Never pass private architecture or secrets to a
public diagram URL or remote renderer without appropriate authorization.

draw.io's official tooling supports Mermaid imports and editable diagrams;
Mermaid CLI supports SVG, PNG and PDF export. Automatic rendering does not prove
that dependencies, labels, retry behavior or evidence claims are correct. Check
those against the source, then inspect the rendered view for clipping and overlap.
Avoid repeated cosmetic-agent passes: reuse the template, render once, repair a
concrete defect, and stop. Sources accessed 2026-09-10:
https://www.drawio.com/docs/manual/generate/drawio-mcp-server/
https://www.drawio.com/docs/manual/mermaid/
https://github.com/mermaid-js/mermaid-cli

## Handoff and execution evidence

Present the visual brief before code changes for substantial work. When the owner
already authorized implementation and no material uncertainty remains, presenting
the brief does not manufacture another approval round. Stop for a genuinely
unresolved scope/risk decision or an existing approval requirement.

This renderer is a static planning view, not a live dashboard. A later execution
view must derive actual state from the existing verified journal and check
receipts, preserve generation/source identity, and distinguish proposed, running,
passed, failed and unavailable. Never infer a successful check from a diagram or
checked Markdown box. Do not add a second status ledger for visualization.

Keep HTML/PDF and large rendered assets outside recurrent model context. Return
their path, source fingerprint and relevant change summary; reread source only
when a decision needs it. Re-render after a material spec change, not every poll.

C4's creator recommends only the diagram levels that add value and separates a
model from its views; use that principle, not a mandatory four-level ceremony:
https://c4model.com/diagrams and https://c4model.com/tooling, accessed 2026-09-10.
