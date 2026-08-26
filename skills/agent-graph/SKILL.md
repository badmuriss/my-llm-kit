---
name: agent-graph
description: Select a portable process from repository facts, then run durable dependency-aware graphs only when graph mode is justified.
---

# Agent Graph

Run adaptive intake before planning or implementation. Use the durable graph
only when the decision proves independent packets, bounded ownership, checks,
integration, budget, and cleanup.

## Adaptive entry

`agent_graph.py intake` returns `direct`, `verified_single`, `light_spec`, or
`graph`. It reads bounded repository facts before asking a question. It creates
no run or worker.

- Direct and verified-single work need no OpenSpec, graph, Canvas, or Orca process.
- Light spec uses one amendable Markdown decision record. OpenSpec remains optional.
- Graph mode alone creates the durable journal and fresh coordinator handoff.

Persist a graph selection as
`openspec/changes/<slug>/process-decision.json`. Bootstrap validates that its
current decision revision, packet paths, checks, permission, budget, integrator,
and cleanup plan match the OpenSpec task graph before creating run artifacts.

Choose the mode from task evidence. Resolve Host, Orca, or future adapter
capabilities only after selection. Never use a provider, model, Canvas, or
worker count as a mode signal. `grill-me` remains explicit and opt-in.

## Core contract

Treat `events.jsonl` as canonical. Rebuild `state.json` from its events. Only the current coordinator generation may append an event.

Parse each task's `Depends`, `Paths`, `Mode`, `Isolation`, `Acceptance`, and single `Check` field. Reject unsafe paths and invalid dependency graphs before dispatch.

Schedule a task only when every dependency has grade `pass`. Serialize write tasks whose file or directory prefixes overlap. A worker report changes an attempt to `reported`; it never grades the task.

## Artifact budget

Workers default to `minimal-by-default-v1`: create no new test suite or supplemental Markdown. Reuse or extend an existing artifact first. Add at most one focused regression test per reproducible defect, and only when the acceptance, a security or data-integrity invariant, or a public contract requires it. Do not add tests for constants, trivial passthroughs, type guarantees, implementation details, or behavior explicitly removed from scope. Do not create status logs, duplicate plans, or narrative check reports; receipts and `WorkerResult` are the evidence trail. Run the task's declared `Check` first and widen validation only for broad or high-risk changes. Host capsules and Orca task specs carry this policy to the worker.

Use `rule-curator` as an occasional maintenance pass over the standing rule
corpus, not as a worker role or a per-task artifact. Run it after a material
rule-set change, consolidate only evidence-backed duplicates, and leave
project-specific rules in their canonical skill or `AGENTS.md` source.

## Safety rules

- Give workers one task capsule, not the full planning transcript.
- Keep workers from writing the journal.
- Validate every worker result against its task and attempt.
- Run checks and assign grades in the coordinator.
- Archive and remove only a partial final journal line. Treat all earlier corruption as fatal.
- Register every owned terminal, Codex process tree, PTY root, browser surface,
  and temporary artifact before side effects. Terminal, Codex-tree, and PTY-root
  registrations must exist before delivering the capsule; retain their receipts.
- Reserve driver selection and attempts before provider mutation. On resume, use `recover-driver-selection` or `recover-attempt` with the same provider retry identity. Use `abandon-attempt` only when driver reconciliation and release prove cleanup.
- Retry pending driver-owned release with `sync` or `recover-cleanup`; never mark terminal cleanup done from an unverified caller claim.
- Never treat provider completion as evidence of `pass`.

See [the task graph reference](references/task-graph.md) for the data model and scheduler rules.

## Portable boundary

The core owns `ProcessDecision`, `CapabilityReceipt`, `AgentGraphView`, generic
delegation, checks, evidence grades, and cleanup semantics. It never requires a
Maestro mutation, Canvas layout, provider terminal handle, or Orca identity.

Host is the baseline adapter and works without an Orca process. Orca is the
current rich adapter. Its bridge owns Maestro mutations, document layout,
supervised worker and terminal receipts, browser surfaces, and worktree UI.
Future adapters declare the same portable capabilities and explicit
degradations. An unavailable rich feature blocks or downgrades only the
operation that requested it.

## Harness boundary

`impl` bootstraps one immutable control-runtime reference, then hands the exact
capsule invocation to one fresh visible top-level coordinator. The bootstrap
session stops after the handoff receipt; all later commands use the pinned
absolute entrypoint. The task-local decision and verified capability receipt
select the coordinator profile. Workers use the cheapest compatible catalog
profile for their role, risk, tools, context, and check. A resolved profile
keeps requested and resolved values, fallback reason, rationale, role, risk,
and cost rank independent of provider model names.

The coordinator derives only the smallest useful non-conflicting wave. It may
delegate dynamically, but children inherit or narrow paths, context, and
capabilities, cannot grade parents, recursively launch workers, or append the
journal. Keep at most one heavy worker active. Orca and the native Host path
share these semantics; Orca-specific APIs and the optional Linux resource guard
are never required for normal operation.

Canvas changes, checkboxes, provider completion, and process exit are receipts or
inputs, not evidence grades. Only the active coordinator grades after an exact
attempt-bound check and independently verified or explicitly retained cleanup.

Shadow learning runs only after completion through
`skills/impl/scripts/learning.py`. It preserves provider usage, cache, and
resolved profile fields only when receipts expose them. Missing telemetry is
`unavailable`, never zero or estimated, and no learning artifact changes the
current run or promotes policy automatically.
