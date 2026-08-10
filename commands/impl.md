---
description: Implement an openspec change with bounded delegation, verified evidence, resumable state, and project-local learning
---

You are the orchestrator. Dispatch and synthesize; do not write the bulk of the code yourself. Keep your context lean.

**Change to implement:** $ARGUMENTS

Steps:
1. Read `openspec/changes/$ARGUMENTS/tasks.md`, plus `proposal.md` and `design.md` when present. If the slug is missing or ambiguous, list `openspec/changes/` and ask which change to use.
2. Read repository instructions. Obtain the real build, test, lint, and typecheck commands plus one or two exemplar files.
3. Create one stable run ID. The scripts run on Windows, macOS, and Linux and load `IMPL_OS` plus `IMPL_PROJECT_DIR` from a local `.env`; `--repo` overrides it. Use `py -3` on Windows when `python3` is unavailable. If no active state exists, run `python3 ~/.agents/skills/impl/scripts/impl_state.py init --change $ARGUMENTS --run-id <run-id>`. It may replace a completed state from an older run. If active state exists, run `resume --change $ARGUMENTS`. Inspect reported diffs, interrupted tasks, processes, and cleanup obligations before restarting anything. If no unchecked task remains, stop.
4. Run `agent-resource-guard check --intent agent --demand 2 --prune` when available. Keep at most two workers from this run active. Retry with one when two are denied. Work locally when one is denied. Run `agent-resource-guard check --intent heavy --prune` before builds, typechecks, test suites, browser runs, or development servers.
5. If `openspec/impl-learning/runs/` exists, run `python3 ~/.agents/skills/impl/scripts/learning.py refresh`, then read `ACTIVE_RULES.md`. Apply only matching project-local rules. Repository instructions and the approved change win on conflict.
6. Classify each unchecked task. Send mechanical work to `fast-worker` and reasoning-heavy work to `deep-reasoner`. For high-stakes uncertainty, use two independent deep reasoners and reconcile. Preserve ordering only for real dependencies.
7. Before dispatch, mark the task `running` with `impl_state.py update-task --worker ...`. Register every process, worktree, branch, and temporary path with `add-cleanup`.
8. Every dispatch carries the exact task, file scope, acceptance criteria, exemplar paths, real check command, and persisted digest. Include this clause: "Leave one runnable check per non-trivial logic, and prove that check can fail with an isolated fixture, fake, or transient mutation. Restore it, confirm the diff is clean, and rerun green. Missing evidence is `unobserved`, never `pass`. Stop if files outside scope are required." Codex dispatches also reuse existing code before standard library, installed dependencies, or new code; fix root causes; mark deliberate shortcuts with `ponytail:`.
9. Review every returned diff. Never trust a worker summary. Run the check before checking `tasks.md`.
10. Grade each task `pass`, `fail`, `unobserved`, or `blocked`. Only `pass` checks the box. Persist the grade, concise note, and existing `file:` or `commit:` evidence references with `update-task`.
11. Before each repair, persist a distinct one-line hypothesis. The state script caps repair at two hypotheses. At the cap, grade the task `blocked`.
12. Append one concise persisted digest entry after each completed task. Include it in subsequent dispatches.
13. Run full validation and the repository's OpenSpec archive step when one exists.
14. Stop background commands and finish every registered cleanup obligation. Do not complete state with running or interrupted work.
15. Run `python3 ~/.agents/skills/impl/scripts/impl_state.py export-run --change $ARGUMENTS --outcome <pass|partial|blocked>`. It creates the schema-version 3 run record with task grades and evidence. Add only structured incidents and learnings. A verified incident includes symptom, hypothesis, proposed fix, verification plan, and evidence refs.
16. Add learning only from integrator-observed evidence. Use `kind: rule` for loadable guidance, `kind: gate_candidate` for a potential mechanical gate, and `kind: skill` for a reusable workflow need. Skill learnings require `skill_name` and `skill_description`. Matching lessons promote only across distinct changes. Generated skills stay project-local until reviewed; never install or publish them automatically.
17. Run `learning.py refresh`, then `learning.py check`. Review `ACTIVE_RULES.md`, `GATE_CANDIDATES.md`, `QUALITY_SIGNALS.md`, `SKILLS.md`, and generated skill folders. Never hand-edit generated artifacts.
18. Run `python3 ~/.agents/skills/impl/scripts/impl_state.py complete --change $ARGUMENTS --outcome <pass|partial|blocked>`. Report files, checks, grades, incidents, learning candidates, gate candidates, generated skills, active rules, and unproven work.

Anti-patterns:
- `repair until green`: relaxing an assertion or replacing a hard case.
- `green by omission`: reporting success without required evidence.
- `threshold creep`: widening tolerance instead of pinning nondeterminism.
- `auto-approved baselines`: regenerating expected output after failure.
- `forced learning`: inventing a lesson or change so every run produces something.
- `unsafe resume`: restarting a command before reconciling real processes, diffs, and state.
