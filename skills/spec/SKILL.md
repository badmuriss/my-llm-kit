---
name: spec
description: Select the minimum planning mode for a codebase change. Emit OpenSpec only for graph mode. Use for $spec, /spec, architecture requests, or proposal.md/design.md/tasks.md. Never implement code.
---

# Spec

Act as the architect. Select the minimum process and produce only its required artifact. Never implement code.

## Workflow

1. Read repository instructions, relevant history, touched code, ADRs, and prior decisions.
2. Run adaptive intake with the request, one direct acceptance check, and only observed task signals. Intake inspects the repository before returning questions.
3. Ask only returned material questions. Never invoke `$grill-me` unless the user explicitly asks for that stress test.
4. Follow the returned `ProcessDecision v1` mode:

   - `direct`: return the objective, scope, check, and stop condition. Write no durable planning file.
   - `verified_single`: return the decision capsule and one-writer hypothesis/check loop. Write no OpenSpec graph.
   - `light_spec`: write `decisions/<slug>.md`. Include revision, invariants, decisions, check, and escalation or reduction triggers. OpenSpec is optional.
   - `graph`: write `openspec/changes/<slug>/proposal.md`, `design.md`, `tasks.md`, and persist the returned transition as `process-decision.json`.

5. Give every graph task these fields:

   ```md
   - [ ] API-01 Implement the endpoint
     Depends: [DOMAIN-01]
     Paths: [src/api/, tests/test_api.py]
     Mode: write
     Isolation: auto
     Context: Keep the endpoint within the validated domain boundary.
     Acceptance: The endpoint returns the validated result.
     Check: python3 -m unittest tests.test_api
   ```

   `Depends` may be empty. `Paths` uses normalized repository-relative files or directory prefixes, never globs. `Mode` is `read` or `write`. `Isolation` is `auto` or `worktree`. Use one direct executable for `Check:` and move shell composition into a reviewed script.
6. Load `frontend-visual-validation` for rendered graph work. Add one reasoned `Visual-Scope:` and one `Visual:` entry per supported platform and state.
7. In graph mode, run `python3 skills/agent-graph/scripts/agent_graph.py validate --change <slug> --json`. Use `py` on Windows. Validation must pass before handoff and never starts workers. Bootstrap separately verifies that the saved decision revision, packets, checks, permission, budget, integration owner, and cleanup plan still match the graph.
8. Run `$spec-council --phase verdict <slug>` only when `--council` is present. Record accepted and rejected findings.
9. Tell the user to run `$impl` or `/impl` with the decision or approved graph slug.

Checks and external evidence decide acceptance. Council advice does not.

Mode selection uses repository facts and task signals. It never depends on a
provider, model, Canvas, or available worker count. Graph execution hints may
describe role, risk, tools, context budgets, and a bounded `ContextRef`. Spec
validates them without dispatching workers. Research collection uses `Mode:
read`; the main researcher owns source adjudication. A checkbox or process exit
is never an evidence grade.
