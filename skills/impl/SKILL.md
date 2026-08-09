---
name: impl
description: Implement an existing OpenSpec change by dispatching its tasks to clean-context subagents, reviewing diffs, and grading evidence. Use when the user invokes "$impl" or "/impl", asks to implement a slug under openspec/changes, or wants an approved spec executed. Do not use to invent a missing spec.
---

# Impl

Act as the tech-lead orchestrator. Dispatch and synthesize; do not write the bulk of the code yourself. Use subagents because tasks benefit from parallel, isolated contexts.

Treat text following `$impl` or `/impl` as the change slug. Otherwise use the slug named by the user.

## Workflow

1. Read `openspec/changes/<slug>/tasks.md`, plus `proposal.md` and `design.md` when present. Do not read the whole codebase into the orchestrator context.
   - If the slug is missing or ambiguous, list `openspec/changes/` and ask which change to use.

2. Read the repository instructions first. Obtain the real build, test, lint, and typecheck commands plus one or two exemplar files. Discover commands only when project instructions do not provide them.

3. Classify every unchecked task.
   - Mechanical work: dispatch a fast worker using [fast-worker.md](references/fast-worker.md).
   - Reasoning-heavy work: dispatch a deep reasoner using [deep-reasoner.md](references/deep-reasoner.md).
   - High-stakes or uncertain work: dispatch two independent deep reasoners without showing either the other's answer, then reconcile.
   - Run independent tasks in parallel. Preserve ordering only for real dependencies.

4. Include in every dispatch:
   - exact task text and file scope;
   - acceptance criteria and exemplar paths;
   - the real check command;
   - the running digest from completed tasks;
   - this clause:

     > Leave one runnable check per non-trivial logic, and prove that check can fail: break the target with an isolated fixture, fake, or transient mutation, never production or an external system. Confirm the check fails on the known-bad case, restore the mutation, confirm the diff is clean, and rerun the check green. If the check still passes with the logic broken, or the restore leaves the target dirty, grade it `unobserved`, not `pass`. If the task requires touching files outside its scope, stop and report instead of improvising.

   - Add for Codex dispatches: reuse existing code before the standard library, installed dependencies, or new code. Fix root causes. Mark deliberate shortcuts with `ponytail:` comments.

5. Review every returned diff. Never trust the subagent summary alone. Run the check before updating `tasks.md`.

6. Grade each task:
   - `pass`: required evidence was collected and the assertion held. Check the task box.
   - `fail`: the check ran and failed. Leave the box open.
   - `unobserved`: required evidence could not be collected. Leave the box open.
   - `blocked`: environment, authority, or dependency prevents execution. Leave the box open.
   - Never turn missing evidence into `pass`.

7. Cap repair at two rounds per task. Before each round, record a distinct one-line root-cause hypothesis. At the cap, grade the task `blocked` and report both hypotheses.

8. Append one concise line to a running digest after each completed task. Include the digest in subsequent dispatches so workers reuse completed helpers.

9. Run the repository's full validation commands after all task-level work. Report changed files, checks, grades, and everything that remains unproven. Follow the repository's OpenSpec archive step when one exists.

## Guardrails

- Do not relax assertions, replace hard cases with easy ones, or widen tolerances to make a check green.
- Do not regenerate baselines or snapshots automatically after a failure.
- Do not mark skipped or missing evidence as success.
- Stop a worker that expands beyond its assigned files.
