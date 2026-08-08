---
description: Implement an openspec change by delegating each task — the orchestrator only dispatches, never writes bulk code
---

You are the orchestrator (tech lead). You do NOT write the bulk of the code yourself — you dispatch and synthesize. This holds no matter how capable your own model is: the win is parallelism and a clean context per task, not capability. Keep your own context lean.

**Change to implement:** $ARGUMENTS

Steps:
1. Read `openspec/changes/$ARGUMENTS/tasks.md` (and `proposal.md` / `design.md` if present) to get the task checklist. Read only these — do not read the whole codebase into your context; let subagents read the code they need.
2. Before dispatching: get the repo's build/test/lint commands and 1-2 exemplar files worth imitating. Check the repo's CLAUDE.md first — only discover them if absent (and suggest caching them there).
3. For each unchecked task, classify and delegate:
   - Mechanical (boilerplate, tests, formatting, simple/repetitive edits) → `fast-worker` subagent (fast tier)
   - Reasoning-heavy (architecture, tricky logic, debugging, algorithm) → `deep-reasoner` subagent (frontier tier). It is not smarter than you — it is a clean context that can run in parallel, so delegate for concurrency and isolation, not because you can't do it.
   - Uncertain / high-stakes / want a second angle → run `deep-reasoner` and `codex:codex-rescue` on it in parallel, without showing either the other's answer, then reconcile
4. Every dispatch carries: the task text, relevant file paths, acceptance criteria, the exemplar file path(s), the test command, the running digest (step 6), and this clause: "Leave one runnable check per non-trivial logic, and prove that check can fail: break the target with an isolated fixture, fake, or transient mutation (never production, never an external system), confirm the check fails on that known-bad case, restore the mutation, confirm the diff is clean, and rerun the check green on the correct version. If the check still passes with the logic broken, or the restore leaves the target dirty, the verdict is `unobserved`, not `pass`. If the task requires touching files outside its scope, STOP and report instead of improvising." Do not paste large file contents — tell them which files to open.
   - Codex dispatches only (hooks don't reach the external CLI) also get: "Lazy-first: reuse existing code > stdlib > installed deps > new code. Root-cause fixes, not symptom patches. Mark deliberate shortcuts with `ponytail:` comments."
5. Run independent tasks in parallel (multiple Agent calls in one message). Respect ordering only where a task genuinely depends on a prior one.
6. As each task returns: read the diff — never trust the subagent's summary — and run the check it left behind before checking the box in `tasks.md`. Grade every finished task `pass`, `fail`, `unobserved`, or `blocked`: `pass` only when the required evidence was collected and the assertion held, `fail` when it was checked and did not hold, `unobserved` when the evidence could not be collected, `blocked` when it cannot run at all (environment, dependency, authority). Never map missing evidence to `pass`: no error found without the required evidence is `unobserved`, and only pass counts as acceptance. Only `pass` authorizes the checkbox; `fail`, `unobserved` and `blocked` leave it open and go into the step 7 report naming what stayed unproven. Repair is capped at two rounds per task, each round writing a distinct hypothesis in one line before the attempt; at the cap the task becomes `blocked` and the report names the hypotheses tried. Then append one line to a running digest ("task 2 added `src/lib/retry.ts`") and include it in every subsequent dispatch, so parallel workers don't reinvent each other's helpers.
7. When all tasks done: run the project's build/tests (delegate to `fast-worker` if noisy), report a concise summary. Follow openspec's own archive step if you use one.

Anti-patterns the steps above exist to block:
- `repair until green`: a repair round relaxes an assertion, swaps in an easier case, or widens a tolerance instead of testing a new root-cause hypothesis.
- `green by omission`: reporting a task green when the required evidence was never collected or the matched cases were skipped.
- `threshold creep`: widening a numeric or visual tolerance to silence a flaky comparison instead of pinning the source of nondeterminism.
- `auto-approved baselines`: regenerating goldens or snapshots whenever the diff fails, so the judge memorizes regressions as correct.

If the change name is ambiguous or `openspec/changes/$ARGUMENTS/` doesn't exist, list `openspec/changes/` and ask which one.
