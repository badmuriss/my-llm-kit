---
name: spec
description: Plan a requested codebase change or architecture decision. Use when planning is requested; do not implement code.
---

# Spec

Define the outcome, scope, constraints and sufficient acceptance evidence. Read
only instructions, code and prior decisions that can change this plan. Resolve
questions from available evidence before asking the user.

Choose the least durable artifact that the task needs:

- `direct`: objective, scope and check in the response; no file.
- `verified_single`: a bounded hypothesis/check loop for one writer.
- `light_spec`: an amendable `decisions/<slug>.md` for a material architectural
  decision. Reuse an existing decision record when it fits.
- `graph`: independent deliverables requiring durable coordination. Read
  [graph-planning.md](references/graph-planning.md) only for this mode.

Planning does not require running the intake CLI for a bounded edit. Do not
select graph because more models or workers happen to be available.

For substantial work, map each required outcome to observable evidence. Separate
optional ideas and exclusions. Define completion as meeting the current request,
not merely finishing implementation or obtaining a successful process exit.
Name any acceptance that cannot currently be observed.

For substantial plans or an explicit visual request, deliver a **PDF visual
summary** before implementation handoff, with a direct link to the actual PDF.
Use the bundled [visual brief](references/visual-brief.md) renderer and template;
it produces PDF plus self-contained HTML by default. HTML alone, screenshots or
instructions to print are not a completed PDF delivery. If export is blocked,
report that explicitly; use HTML-only only when the user requests that exception.
Inspect the rendered PDF for pagination, legibility and missing content. Keep
Mermaid flow/sequence diagrams in the canonical spec when they explain the
change; render them into the same offline PDF as the decisions and checks.
Distinguish proposals from execution evidence. Trivial edits need no artifact.

## Validate the plan before handoff

For a requested adversarial review, or a substantial plan involving migration,
retirement, changed contracts or independent integration risks, use the bounded
[plan validation](references/plan-validation.md) workflow before declaring the
plan ready. Use read-only subagents when delegation is allowed and independent
review can add evidence; skip delegation for trivial, single-path edits. This is
plan validation, not permission to implement, run live experiments or create a
new orchestration graph. Respect explicit model, budget and placement choices.

Keep requirements, findings, decisions and remaining proof obligations in the
existing spec. Reviewer agreement does not prove completeness; an unresolved
required capability must remain visible in the handoff.

Do not invoke `grill-me`, a separate council or a whole-corpus audit merely
because it is installed. Reuse a requested council that already covers these
risks instead of spawning another review.
When an implementation plan is ready, provide the appropriate `$impl` invocation
as a handoff, not as execution authority. For research-only requests, report the
design and remaining proof obligations without implying implementation starts.
Do not demand another approval when the user already authorized implementation
of this scope.
