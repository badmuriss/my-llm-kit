---
name: impl
description: Implement through the minimum justified process. Use a fresh coordinator and durable graph only for an approved graph-mode OpenSpec change. Use for $impl, a process decision, or an approved slug.
---

# Impl

Act as the integrator. Start from a valid `ProcessDecision v1` or run adaptive intake. A worker report never proves a task passed.

## Mode entry

Read repository instructions and the supplied decision. If no decision exists,
run `agent_graph.py intake` with one direct check and observed signals. Do not
invoke `grill-me` implicitly.

- `direct`: use one local writer. Make the bounded change, run the selected check, and report the result. Do not create OpenSpec, a journal, or a graph.
- `verified_single`: use one writer and a bounded hypothesis/check loop. Record each distinct hypothesis and stop on acceptance or the decision's budget. Do not create OpenSpec or a graph.
- `light_spec`: use one writer and the amendable `decisions/<slug>.md` record. OpenSpec is optional. Promote only after a material amendment selects `graph` and proves complete packet contracts.
- `graph`: require an approved OpenSpec graph, then use the durable workflow below.

## Bootstrap

A graph-mode `$impl <slug>` is a bounded bootstrap:

```text
python3 skills/agent-graph/scripts/agent_graph.py validate --change <slug> --json
python3 skills/agent-graph/scripts/agent_graph.py bootstrap --change <slug> --run-id <run-id> --driver auto --json
```

The approved change must include
`openspec/changes/<slug>/process-decision.json`. Bootstrap fails closed unless
its current graph contract matches the task packets, checks, permission, budget,
integration owner, and cleanup plan.

Do not load the full package first. Transfer the returned `$impl --coordinator-capsule <path>` invocation to one fresh top-level session in the current checkout.

- Before delivery, register the owned terminal, Codex process tree, and PTY root.
  Orca creates a fresh agent terminal in the current worktree, waits for TUI
  readiness, sends the capsule invocation as a full handoff, verifies delivery,
  then stops. Never create an Orca Task or Dispatch for the coordinator.
- A host with visible fresh-session handoff uses that surface.
- A host without it prints the exact invocation and stops. A nested subagent is not a coordinator.

The owner may explicitly declare the current session to be the fresh coordinator. It claims the supplied capsule or existing run and must not bootstrap another coordinator.

The bootstrap freezes and hashes the minimal control runtime before the first
dispatch. The task-local decision and verified capability receipt select the
coordinator's model, effort, and placement. Record requested and resolved values
plus any fallback. Use the pinned entrypoint for all later commands. Stop the
bootstrap session after the handoff receipt.

## Coordinator loop

Run `claim-coordinator`, then `resume`. Never bootstrap from a claimed coordinator. Every mutating command presents the current generation.

1. Query `ready`. Choose the smallest useful non-conflicting wave.
2. Classify ready work into only the roles it needs: research, documentation, implementation, review, verification, or integration. The coordinator filters review by cohesive package and material risk, rather than auditing every microtask. Before routing Codex workers, read [the model-routing policy](references/model-routing.md); use [fast-worker](references/fast-worker.md) for bounded mechanical work and [deep-reasoner](references/deep-reasoner.md) for hard judgment. Resolve each attempt through the runtime catalog with the cheapest sufficient model and effort. Persist requested/resolved values independently with fallback, rationale, role, risk, and cost rank. Do not escalate model or effort automatically. Apply the `minimal-by-default-v1` artifact budget from `agent-graph`: no speculative tests or Markdown.
3. Run `dispatch --task <id> --generation <n>`. Give a worker only the generated capsule, which is bounded and transcript-free. Use host-native workers when available or `--local` for one localized task.
4. Use `sync` for provider lifecycle, `reply` for questions, and `record-result` for a structured result. Driver degradation and auto-selection stay visible in receipts. Dynamic children inherit or narrow paths and context; they cannot grade parents, recursively delegate, or mutate the journal.
5. Run `run-check --task <id> --generation <n>`. It executes directly and rejects shell operators. A process exit or provider completion is never a grade.
6. Inspect the whole task diff. A failed check is not a fail grade: after its attempt-owned cleanup is settled or retained, run `record-repair --task <id> --hypothesis <text>` before any terminal grade. It records `attempt_check_rejected`, preserves the failed evidence on that attempt, and returns the task to pending for a fresh attempt ID.
7. For a passing check, record any public finding first. Only a complete blocking finding can use `audit-reject-attempt`; a failed check always uses `record-repair`. The default is one implementation plus one repair. Before a third attempt, the coordinator must record one explicit decision to amend acceptance or Paths, or regroup the package. No stronger model, new hypothesis, or third attempt starts automatically. Hardening becomes durable carry-forward; advisory findings do not block a valid grade. Run `grade --grade pass|fail|unobserved|blocked --note <text>` only for an ordinary terminal decision. Pass requires a reported attempt and its own passing check. Frontend pass also requires one `file:` visual manifest reviewed through `frontend-visual-validation`.
8. Register the terminal, Codex process tree, PTY root, and other resources with
   `cleanup-register` before capsule delivery or other side effects. Finish them
   with `cleanup-finish` only after the target or receipt proves cleanup.

Use `status --watch` for projection-only monitoring. Use `takeover` after coordinator loss. Takeover reconciles attempts, increments the generation, and fences the prior coordinator.
Resume reports incomplete reservations. Recover them with `recover-driver-selection` or `recover-attempt`, which reuse the provider retry identity. If reconciliation proves an attempt cannot return, run `abandon-attempt --attempt <id> --reason <text>`; that command must prove driver-owned release before making the task retryable. Never retry a reserved, running, or interrupted attempt in place.

## Drivers

- `--driver orca` requires Orca. Prefer supervised workers. A recognized composition failure may record `driver_degraded` and use tracked-terminal lifecycle. Never switch to host silently.
- `--driver host` writes bounded capsules and accepts host-native or local results. It never guesses private APIs or shells out to an agent CLI.
- Host and Orca implement the same portable task, profile, capsule, evidence, and cleanup semantics. Host is the baseline path and needs no Orca process. Orca is the current rich adapter for supervised workers, terminal receipts, browser surfaces, worktree UI, and Maestro Canvas state. It is not a prerequisite.
- `--driver auto` records one selection and reason. The selection cannot change during a run.
- Maestri is reserved for a future driver conformance implementation. No adapter exists here.

Drivers apply only after `graph` mode is selected. Adapter capabilities may
downgrade one operation or block it. They never choose the process mode.

## Finish

Review source changes by cohesive package and material risk. The reviewer is read-only. Verify material findings and rerun affected checks.

When the repository configures a cyclomatic-complexity rule, run that project-native
gate after the task check and before the final review. A configured gate must pass
before completion. Do not raise its ceiling, disable the rule, or add an inline
suppression to pass an ordinary implementation. A policy change requires explicit
task scope.

Treat complexity as a repair trigger, not proof of poor design. Inspect each new or
worsened violation and ask whether the change deleted decisions, converted them to
data, or moved them behind a cohesive private boundary. Preserve a small public
interface when splitting a deep module. For behavior-preserving refactors, record
the maximum-function score, module decision total when the tool exposes it,
production line delta, helper or public-symbol delta, and branches deleted versus
moved. The behavior check remains authoritative.

In graph mode, record a complete blocking finding and use `audit-reject-attempt`
when changed code introduces or worsens a configured violation. Other modes repair
the same diff before reporting completion. Generated evidence and frozen runtime
snapshots stay outside source audits when the repository marks them as generated.

Then run the read-only `thermo-nuclear-code-quality-review` skill. Run `rule-curator` only when the approved scope is a whole-corpus rule audit; review individual rule edits directly. Verify findings, rerun affected checks, then run `digest`, finish all cleanup, and run `complete --outcome <pass|partial|blocked>`. Report files, checks, grades, repair hypotheses, driver degradation, cleanup receipts, review findings, and unproven behavior.

After normal completion, `python3 skills/impl/scripts/learning.py snapshot --change <slug> --run-id <run-id>` may record shadow learning. It records mode, result, retries, observed time, rework, coordination overhead, resolved profiles, and provider usage or cache fields only when exposed. Missing telemetry is `unavailable`, never zero or estimated. The snapshot never changes the run, routing, capability receipt, evidence grade, rule, or skill.
