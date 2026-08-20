---
name: impl
description: Implement an existing OpenSpec graph through a fresh coordinator, durable journal, executable checks, evidence grades, and bounded workers. Use for $impl, /impl, or an approved slug. Do not invent a missing spec.
---

# Impl

Act as the integrator. The repository journal is canonical. A worker report never proves a task passed.

## Bootstrap

A normal `$impl <slug>` is a bounded bootstrap:

```text
python3 skills/agent-graph/scripts/agent_graph.py validate --change <slug> --json
python3 skills/agent-graph/scripts/agent_graph.py bootstrap --change <slug> --run-id <run-id> --driver auto --json
```

Do not load the full package first. Transfer the returned `$impl --coordinator-capsule <path>` invocation to one fresh top-level session in the current checkout.

- Orca creates a fresh agent terminal in the current worktree, waits for TUI readiness, sends the capsule invocation as a full handoff, verifies delivery, then stops. Never create an Orca Task or Dispatch for the coordinator.
- A host with visible fresh-session handoff uses that surface.
- A host without it prints the exact invocation and stops. A nested subagent is not a coordinator.

The owner may explicitly declare the current session to be the fresh coordinator. It claims the supplied capsule or existing run and must not bootstrap another coordinator.

## Coordinator loop

Run `claim-coordinator`, then `resume`. Never bootstrap from a claimed coordinator. Every mutating command presents the current generation.

1. Query `ready`. Choose the smallest useful non-conflicting wave.
2. Run `dispatch --task <id> --generation <n>`. Give a worker only the generated capsule. Use host-native workers when available or `--local` for one localized task.
3. Use `sync` for provider lifecycle, `reply` for questions, and `record-result` for a structured result. Driver degradation and auto-selection stay visible in receipts.
4. Run `run-check --task <id> --generation <n>`. It executes directly and rejects shell operators.
5. Inspect the whole task diff. Run `grade --grade pass|fail|unobserved|blocked --note <text>`. Pass requires a reported attempt and passing check. Frontend pass also requires one `file:` visual manifest reviewed through `frontend-visual-validation`.
6. Before each repair, run `record-repair --task <id> --hypothesis <text>`. After two distinct failed hypotheses, grade the task blocked.
7. Register resources with `cleanup-register`. Finish them with `cleanup-finish` only after the target or receipt proves cleanup.

Use `status --watch` for projection-only monitoring. Use `takeover` after coordinator loss. Takeover reconciles attempts, increments the generation, and fences the prior coordinator.
Resume reports incomplete reservations. Recover them with `recover-driver-selection` or `recover-attempt`, which reuse the provider retry identity. If reconciliation proves an attempt cannot return, run `abandon-attempt --attempt <id> --reason <text>`; that command must prove driver-owned release before making the task retryable. Never retry a reserved, running, or interrupted attempt in place.

## Drivers

- `--driver orca` requires Orca. Prefer supervised workers. A recognized composition failure may record `driver_degraded` and use tracked-terminal lifecycle. Never switch to host silently.
- `--driver host` writes bounded capsules and accepts host-native or local results. It never guesses private APIs or shells out to an agent CLI.
- `--driver auto` records one selection and reason. The selection cannot change during a run.
- Maestri is reserved for a future driver conformance implementation. No adapter exists here.

## Finish

Run `thermo-nuclear-code-quality-review` for source changes. Give it the merge-base diff and every untracked, non-ignored source file. The reviewer is read-only. Verify each finding and rerun affected checks.

Then run `digest`, finish all cleanup, and run `complete --outcome <pass|partial|blocked>`. Report files, checks, grades, repair hypotheses, driver degradation, cleanup receipts, review findings, and unproven behavior.

After normal completion, `python3 skills/impl/scripts/learning.py snapshot --change <slug> --run-id <run-id>` may record shadow learning. It never changes the outcome and never activates a rule or skill.
