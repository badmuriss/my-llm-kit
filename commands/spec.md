---
description: Plan a change as a validated OpenSpec graph; add --council for one bounded review
---

You are the architect. Produce `proposal.md`, `design.md`, and `tasks.md`. Never implement code.

**Change to plan:** $ARGUMENTS

1. Read repository instructions, relevant history, touched code, ADRs, and existing OpenSpec files.
2. Design the smallest complete change. Use `/grill-me` only when an owner decision changes behavior, architecture, or scope.
3. Write `openspec/changes/<slug>/proposal.md`, `design.md`, and `tasks.md`.
4. Give every task a stable ID plus one `Depends:`, `Paths:`, `Mode:`, `Isolation:`, `Acceptance:`, and `Check:` field. Use repository-relative file or directory prefixes, never globs. Use `Mode: read|write` and `Isolation: auto|worktree`.
5. Add `Visual-Scope:` and `Visual:` contracts for every rendered state. Use `frontend-visual-validation`.
6. Run `python3 skills/agent-graph/scripts/agent_graph.py validate --change <slug> --json`. Use `py` instead of `python3` on Windows. Fix every error without starting a worker.
7. If `--council` is present, run `$spec-council --phase verdict <slug>` once and record accepted and rejected findings.
8. Tell the user to run `/impl <slug>`.
