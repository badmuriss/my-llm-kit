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

For substantial plans or an explicit visual request, present a rendered
[visual brief](references/visual-brief.md) before implementation handoff. Keep it
derived from the existing spec, distinguish proposals from execution evidence,
and use only visuals that clarify the change. Trivial edits need no new artifact.

Do not invoke `grill-me`, a council or a whole-corpus audit unless requested.
When the plan is ready, provide the appropriate `$impl` invocation. Do not demand
another approval when the user already authorized implementation of this scope.
