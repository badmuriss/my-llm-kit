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

3. Initialize or reconcile crash-safe run state before dispatching.
   - Use one stable run ID for the whole execution.
   - If no active state exists, run `python3 ~/.agents/skills/impl/scripts/impl_state.py --repo . init --change <slug> --run-id <run-id>`. It replaces only a completed state from an older run. The generated file conforms to [impl-state.schema.json](references/impl-state.schema.json).
   - If an active state exists, run the same script with `resume --change <slug>`. Inspect every reported diff, interrupted task, process, and cleanup obligation before restarting or dispatching anything.
   - The state tracks only unchecked OpenSpec tasks. If none remain, stop instead of inventing work.

4. Check machine-wide capacity before dispatching.
   - Run `agent-resource-guard check --intent agent --demand 2 --prune` when the command exists.
   - Never keep more than two workers from this run active at once.
   - If a batch of two is denied, retry with `--demand 1`. If one is denied, do integration or review work locally and retry after an existing worker exits. Do not open another terminal.
   - Run `agent-resource-guard check --intent heavy --prune` before each build, typecheck, test suite, browser run, or development server. A denial is not test evidence; wait for capacity.

5. Load project-local impl rules before dispatching.
   - If `openspec/impl-learning/runs/` exists, run `python3 ~/.agents/skills/impl/scripts/learning.py refresh --repo .`.
   - Read `openspec/impl-learning/ACTIVE_RULES.md` after regeneration.
   - Apply only rules whose scopes match the current change. Repository instructions and the approved OpenSpec change take precedence.
   - Never copy these rules into Codex memory, `AGENTS.md`, or another project automatically.

6. Classify every unchecked task.
   - Mechanical work: dispatch a fast worker using [fast-worker.md](references/fast-worker.md).
   - Reasoning-heavy work: dispatch a deep reasoner using [deep-reasoner.md](references/deep-reasoner.md).
   - High-stakes or uncertain work: dispatch two independent deep reasoners without showing either the other's answer, then reconcile.
   - Run independent tasks in parallel within the two-worker limit. Preserve ordering only for real dependencies.

7. Include in every dispatch:
   - exact task text and file scope;
   - acceptance criteria and exemplar paths;
   - the real check command;
   - the running digest from completed tasks;
   - this clause:

     > Leave one runnable check per non-trivial logic, and prove that check can fail: break the target with an isolated fixture, fake, or transient mutation, never production or an external system. Confirm the check fails on the known-bad case, restore the mutation, confirm the diff is clean, and rerun the check green. If the check still passes with the logic broken, or the restore leaves the target dirty, grade it `unobserved`, not `pass`. If the task requires touching files outside its scope, stop and report instead of improvising.

   - Add for Codex dispatches: reuse existing code before the standard library, installed dependencies, or new code. Fix root causes. Mark deliberate shortcuts with `ponytail:` comments.

8. Checkpoint every state transition.
   - Mark a task `running` with its worker before dispatch.
   - Register each process PID, worktree, branch, or temporary path that this run must clean with `add-cleanup`.
   - After review, call `update-task` with the evidence grade, concise note, and `file:` or `commit:` evidence references. Commit references use the full immutable SHA. A `pass` or `fail` without an existing reference is rejected.
   - Record each repair hypothesis before the attempt. The state script rejects repeated hypotheses and a third repair attempt.
   - Append the running digest with the `digest` command. State writes are atomic.

9. Review every returned diff. Never trust the subagent summary alone. Run the check before updating `tasks.md`.

10. Grade each task:
   - `pass`: required evidence was collected and the assertion held. Check the task box.
   - `fail`: the check ran and failed. Leave the box open.
   - `unobserved`: required evidence could not be collected. Leave the box open.
   - `blocked`: environment, authority, or dependency prevents execution. Leave the box open.
   - Never turn missing evidence into `pass`.

11. Cap repair at two rounds per task. Before each round, record a distinct one-line root-cause hypothesis in the state file. At the cap, grade the task `blocked` and report both hypotheses.

12. Append one concise line to the persisted digest after each completed task. Include the digest in subsequent dispatches so workers reuse completed helpers.

13. Run the repository's full validation commands after all task-level work. Follow the repository's OpenSpec archive step when one exists.

14. Stop every background command and finish every registered cleanup obligation. A completed state cannot contain running or interrupted tasks or pending cleanup.

15. Export the run and refresh project-local artifacts.
   - Run `python3 ~/.agents/skills/impl/scripts/impl_state.py --repo . export-run --change <slug> --outcome <pass|partial|blocked>`. It copies final task grades and evidence into a new record under `openspec/impl-learning/runs/` that conforms to [learning-run.schema.json](references/learning-run.schema.json).
   - Record every task grade, observed evidence, and existing `file:` or `commit:` evidence references. Set the run outcome to `pass`, `partial`, or `blocked`.
   - Add incidents and learnings to the exported record. Record incidents separately from learnings. Each incident names its kind, symptom, hypothesis, proposed fix, verification plan, status, and evidence references. A hypothesis is not a learned rule.
   - Derive learnings only from events the orchestrator observed in diffs, checks, repairs, conflicts, or integration. Link each learning to a passing task, verified incident, existing file, or existing commit. An uneventful run uses empty `incidents` and `learnings` arrays.
   - Before adding a learning, search prior run records. Reuse the same key, scopes, and rule text when the same lesson recurs. Use a new key with `supersedes` when the new rule replaces an older one.
   - Use `kind: rule` for guidance the harness may load. Use `kind: gate_candidate` when recurrence could become a test, guard, linter, or script. Gate candidates require a normal reviewed OpenSpec change and never modify code automatically.
   - Keep evidence concrete and local to this run. Never promote a subagent claim that the orchestrator did not verify.
   - Run `python3 ~/.agents/skills/impl/scripts/learning.py refresh --repo .`, then run the same command with `check` instead of `refresh`.
   - The compiler promotes matching observations only across distinct OpenSpec changes. It generates `ACTIVE_RULES.md`, `GATE_CANDIDATES.md`, and `QUALITY_SIGNALS.md`. Quality signals include task grades and incident categories, not PR throughput.

16. Complete the persisted state with `python3 ~/.agents/skills/impl/scripts/impl_state.py --repo . complete --change <slug> --outcome <pass|partial|blocked>`. Report changed files, checks, grades, incidents, learning candidates, gate candidates, newly active rules, and everything that remains unproven.

## Guardrails

- Do not relax assertions, replace hard cases with easy ones, or widen tolerances to make a check green.
- Do not regenerate baselines or snapshots automatically after a failure.
- Do not mark skipped or missing evidence as success.
- Stop a worker that expands beyond its assigned files.
- Do not invent a lesson to make every run look useful.
- Do not hand-edit `openspec/impl-learning/ACTIVE_RULES.md`; it is generated state.
- Do not hand-edit `GATE_CANDIDATES.md` or `QUALITY_SIGNALS.md`; they are generated state.
- Do not activate a learning from repeated run IDs that belong to the same OpenSpec change.
- Do not turn a gate candidate into code without a reviewed change and a failing behavioral test.
- Stop when no unchecked, verified, in-scope task remains. A non-empty run is not a success condition.
- Do not restart commands restored from a crashed or resumed session without inspecting whether an equivalent process already exists.
