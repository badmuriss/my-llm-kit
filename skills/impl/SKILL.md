---
name: impl
description: Implement an existing OpenSpec change with executable checks, resumable state, and bounded delegation. Use when the user invokes "$impl" or "/impl", asks to implement a slug under openspec/changes, or wants an approved spec executed. Do not invent a missing spec.
---

# Impl

Act as the integrator. Implement the approved tasks, inspect every diff, and grade only observed evidence.

Treat text following `$impl` or `/impl` as the change slug. Otherwise use the slug named by the user.

## Workflow

1. Read `tasks.md`, then the relevant parts of `proposal.md` and `design.md`.
   - If the slug is missing or ambiguous, list `openspec/changes/` and ask for the slug.
   - Stop when no unchecked task remains.

2. Read repository instructions and the touched code.
   - Obtain the real focused and full validation commands.
   - Read one or two exemplar files. Do not load the whole repository without a reason.

3. Initialize or resume state.
   - Run `python3 ~/.agents/skills/impl/scripts/impl_state.py init --change <slug> --run-id <run-id>` for a new run.
   - Run `resume --change <slug>` when active state exists.
   - Inspect reported diffs, interrupted tasks, processes, and cleanup before restarting anything.

4. Choose the smallest execution path that fits the task.
   - Execute one localized task in the current context.
   - Dispatch independent or repetitive tasks when parallelism pays for coordination.
   - Use an independent reasoner for ambiguous, cross-cutting, security-sensitive, or high-consequence work.
   - Use two independent reasoners only for high-stakes uncertainty that lacks a decisive external check.
   - Read [model-routing.md](references/model-routing.md) when the host supports model overrides.
   - Before dispatching, run `agent-resource-guard check --intent agent --demand <count> --prune`. Keep at most two workers active.

5. Execute one task at a time per worker.
   - Mark it `running`; use worker `local` for current-context work.
   - Keep the task's exact paths and acceptance criteria in scope.
   - Register processes, worktrees, branches, and temporary paths that require cleanup.
   - Reuse existing code and dependencies. Fix root causes. Do not leave placeholders, stubs, elided lists, or invented completion claims.
   - If the request says every file or item, count the full requested scope. Sampling must be declared.
   - Finish the current line of attack before switching unless observed evidence makes the switch better.

6. Run the task contract through state:

   ```text
   python3 ~/.agents/skills/impl/scripts/impl_state.py run-check --change <slug> --task <id>
   ```

   - The command comes from the task's `Check:` line.
   - Review that line before execution. `run-check` launches the executable directly and rejects shell operators; complex checks belong in a repository script.
   - A bug fix needs a regression test that fails on the known-bad behavior and passes after the fix.
   - Use a negative fixture or mutation when a newly written check may be vacuous. Do not mutate every task by ritual.
   - `Check: missing validation evidence` remains `unobserved` and cannot pass.
   - Run `agent-resource-guard check --intent heavy --prune` before a test suite, build, typecheck, browser run, or development server.
   - For a task with `Visual:` entries, load `$frontend-visual-validation`, confirm each contextual `Visual-Scope:`, run or reuse the application, capture every declared platform under `.visual-evidence/<change>/`, and inspect every PNG with `view_image` or `computer-use`.
   - Write one manifest per task with the exact expectations, browser engines, screenshot paths, SHA-256 digests, vision tool, timestamp, pass status and concrete observations. Follow [visual-evidence.example.json](references/visual-evidence.example.json). Code review, tests, DOM snapshots and accessibility trees cannot satisfy a `Visual:` entry.

7. Review the diff and grade the task.
   - `pass`: the recorded check passed and the reviewed diff meets the acceptance criteria.
   - `fail`: the recorded check ran and failed.
   - `unobserved`: the required evidence could not be collected.
   - `blocked`: environment, authority, dependency, or scope prevents execution.
   - Add `file:` or immutable `commit:` references when an artifact matters, but never use file existence as a substitute for a passing check.
   - Pass the visual manifest as `--evidence-ref file:.visual-evidence/<change>/<manifest>.json`. `impl_state.py` rejects missing expectations, invalid PNGs, wrong viewport widths, failed surfaces and manifests not reviewed with a vision tool.
   - Only `pass` checks the task box.

8. Repair from evidence.
   - Record one distinct root-cause hypothesis before each repair.
   - The state caps repairs after two failed hypotheses. At the cap, report both and grade `blocked`.
   - Escalate model or effort after an observed failure, unresolved ambiguity, or increased consequence, not because a static table says every hard task needs maximum compute.

9. Integrate and finish.
   - Append one concise digest entry after each completed task.
   - Run the repository's full validation and OpenSpec archive step when present.
   - Stop background commands and finish every cleanup obligation.
   - Run `complete --change <slug> --outcome <pass|partial|blocked>`.
   - Report changed files, check commands and results, task grades, repair hypotheses, cleanup, and anything unproven.

10. Optionally record learning after normal completion.
   - Learning is shadow-mode telemetry, never a completion gate. Do not delay or change the completed outcome when snapshotting, candidate extraction, or compilation fails.
   - Run `python3 ~/.agents/skills/impl/scripts/learning.py snapshot --change <slug>` only after `complete`. It copies observed task checks into a provenance-linked run record conforming to [learning-run.schema.json](references/learning-run.schema.json).
   - Add a candidate only for a pattern observed in a check, diff, repair, or review. Cite one or more task IDs with `add-candidate`; use `stance: oppose` when later evidence contradicts the same scoped statement.
   - Run `learning.py compile` to refresh `openspec/impl-learning/DRAFT_CANDIDATES.md`. The compiler never creates active rules or skills, and `impl` never loads this file.
   - Five supporting OpenSpec changes mark only a recurring draft. Activation requires a separate reviewed change or an executable gate that fails on the negative case, passes on the positive case, and survives full validation.
   - For a candidate trial, compare completed states with identical task checks using `learning.py compare --candidate <key> --off-state <path> --on-state <path>`. Treat no gain, regression, or extra cost without benefit as rejection evidence. The command reports deltas and never declares a winner.

## Stop condition

Stop when every requested, in-scope task is passed or explicitly reported as fail, unobserved, or blocked. More thinking is not evidence. Never load `DRAFT_CANDIDATES.md` into an implementation prompt, convert recurrence counts into active rules or generated skills, or overwrite an observation record. See [the paper audit](../../research/2026-08-10-agent-trajectory-learning-audit.md).

If frontend file changes are present, a `pass` outcome also requires at least one task with explicit `Visual:` expectations. This catches plans that omitted visual validation entirely.
