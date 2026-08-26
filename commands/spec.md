---
description: Select the minimum planning mode; use OpenSpec only for graph work
---

You are the architect. Select the minimum process before writing planning artifacts. Never implement code.

**Change to plan:** $ARGUMENTS

1. Read repository instructions, relevant history, touched code, ADRs, and existing decisions.
2. Run `python3 skills/agent-graph/scripts/agent_graph.py intake --request "<bounded request>" --check "<direct check>" --signals-json '<observed signals>' --json`. Use `py` on Windows. Ask only questions returned by intake. Never invoke `/grill-me` unless the user explicitly requests it.
3. Follow the selected mode:
   - `direct`: return the objective, scope, check, and stop condition. Create no durable spec.
   - `verified_single`: return one decision capsule and a hypothesis/check loop for one writer. Create no OpenSpec graph.
   - `light_spec`: write `decisions/<slug>.md` with revision, invariants, decisions, check, and transition triggers. OpenSpec remains optional.
   - `graph`: write `openspec/changes/<slug>/proposal.md`, `design.md`, `tasks.md`, and the returned transition as `process-decision.json`.
4. For `graph`, give every task a stable ID plus one `Depends:`, `Paths:`, `Mode:`, `Isolation:`, `Acceptance:`, and `Check:` field. Use repository-relative paths, never globs.
5. For rendered graph work, add `Visual-Scope:` and `Visual:` contracts for every supported state. Use `frontend-visual-validation`.
6. For `graph`, run `python3 skills/agent-graph/scripts/agent_graph.py validate --change <slug> --json`. Fix every error without starting a worker. Bootstrap will also require the saved decision revision and packet contract to match the tasks.
7. Run `$spec-council --phase verdict <slug>` once only when `--council` is present. Record accepted and rejected findings.
8. Tell the user to run `/impl` with the decision or approved graph slug.

Intake chooses a mode from repository facts and task signals. It never consults
a provider, model, Canvas, or available worker count. `spec` never dispatches or
materializes a worker. A checked box or process exit is not acceptance evidence.
