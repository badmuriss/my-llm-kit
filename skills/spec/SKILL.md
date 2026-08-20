---
name: spec
description: Plan a codebase change and emit a validated OpenSpec task graph. Use for $spec, /spec, architecture requests, or proposal.md/design.md/tasks.md. The optional --council flag adds one bounded review. Never implement code.
---

# Spec

Act as the architect. Produce an executable OpenSpec graph, never implementation code.

## Workflow

1. Read repository instructions, relevant history, touched code, ADRs, and related OpenSpec files.
2. Design the smallest complete change. Treat the project as an MVP unless the repository proves an active external contract. Prefer a clean rewrite over compatibility layers for an MVP.
3. Use `$grill-me` only when an unresolved owner decision changes behavior, architecture, or scope.
4. Write `openspec/changes/<slug>/proposal.md`, `design.md`, and `tasks.md`.
5. Give every task these fields:

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
6. Load `frontend-visual-validation` for rendered UI. Add one reasoned `Visual-Scope:` and one `Visual:` entry per supported platform and state.
7. Run `python3 skills/agent-graph/scripts/agent_graph.py validate --change <slug> --json`. Use `py` on Windows. Validation must pass before handoff and never starts workers.
8. Run `$spec-council --phase verdict <slug>` only when `--council` is present. Record accepted and rejected findings.
9. Tell the user to run `$impl <slug>` or `/impl <slug>`.

Checks and external evidence decide acceptance. Council advice does not.
