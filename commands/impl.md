---
description: Implement an OpenSpec change with executable checks, resumable state, and bounded delegation
---

Implement the approved change. Inspect every diff and grade only observed evidence.

**Change to implement:** $ARGUMENTS

1. Read the change's tasks, proposal, design, repository instructions, touched code, the smallest relevant validation command, and exemplar files.
2. Initialize `impl_state.py`, or resume active state and inspect diffs, processes, and cleanup before restarting work.
3. Use the current context for one localized task. Delegate only for useful parallelism, isolation, ambiguity, or high consequence. Run the resource guard before workers and heavy commands.
4. Mark each task `running`; use worker `local` for current-context work. Register cleanup obligations.
5. Stay inside task scope. Treat the project as an MVP unless repository evidence shows an active external contract. Prefer deleting or rewriting the affected path over migrations, adapters, aliases, dual paths and compatibility fallbacks. Reuse existing code, fix root causes, finish full requested sweeps, and leave no placeholders or stubs.
6. Run `impl_state.py run-check --change $ARGUMENTS --task <id>`. Do not add tests by default or merely to pin constants, defaults, toggles, deletions, trivial passthroughs or type-system guarantees. Add one only for requested coverage, a likely regression, non-trivial behavior, security, data integrity or a public contract. When warranted, a regression test must fail on the known-bad behavior. Use a negative fixture only when a new check may be vacuous.
7. Load `frontend-visual-validation`. Confirm each `Visual-Scope:` against product context. For every platform declared by that surface and state, run the UI at the canonical viewport, capture a PNG under `.visual-evidence/<change>/`, inspect it with `view_image` or `computer-use`, and record a manifest with concrete observations. DOM snapshots and builds are not visual evidence.
8. Review the diff. Grade `pass` only when the recorded check passed, acceptance criteria hold, and every visual expectation has a valid manifest passed through `--evidence-ref`. Otherwise grade `fail`, `unobserved`, or `blocked`. File existence alone is not proof.
9. Record a distinct hypothesis before each repair. Escalate model or effort after observed failure, ambiguity, or risk. Stop after the bounded repair cap.
10. Run the smallest relevant validation. Run the full suite only for broad or risky changes, releases, or when repository instructions require it. Finish cleanup and complete state before any learning work. A completed run may optionally be snapshotted into shadow-mode observations; failure there never changes completion.
11. Keep every extracted rule, gate, or skill in `DRAFT_CANDIDATES.md`. Recurrence is not activation. Activate only through a reviewed change or a separately validated executable gate.

Do not load draft candidates into the implementation prompt or generate active project rules or skills automatically.
