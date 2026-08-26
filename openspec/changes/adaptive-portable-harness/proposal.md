# Adaptive portable harness

## Why

`maestro-harness-orchestration` completed the portable graph control plane and
the Orca/Maestro integration boundary. It deliberately proved that a run can
work through the Host driver without Orca. Its default entry path nevertheless
still assumes a durable graph, a fresh coordinator, and a high-capability
execution profile for every implementation.

That makes a small, known, reversible change pay for machinery that does not
improve its acceptance evidence. It also makes a host capability and a work
decision too easy to conflate: Orca Canvas is a valuable client, but it must
not determine whether a task needs a graph.

The audited findings in `research/2026-08-21-adaptive-harness-evidence.md` and
`research/2026-08-21-adaptive-harness-interview-routing.md` support a
capability-first, process-adaptive policy. This change turns that policy into a
portable product contract while retaining Orca as the first rich adapter.

## Change

Create one adaptive intake before planning or implementation. It will:

- inspect the local request and repository before asking questions;
- ask only when an answer can change behavior, scope, risk, acceptance, or
  process mode;
- choose `direct`, `verified_single`, `light_spec`, or `graph` from observable
  task signals, rather than from the available host;
- record a compact, versioned decision capsule and a separately observed
  capability receipt;
- allow escalation and de-escalation when evidence changes the task shape;
- require real independent work packets, isolated ownership, checks,
  integration, budgets, and cleanup before creating a graph;
- keep OpenSpec and Orca optional upgrades: a lightweight Markdown decision
  record and the Host driver remain functional without either;
- make adapters declare verified capabilities and explicit degradations;
- preserve `AgentGraphView` and generic delegation intent as core contracts,
  while treating Maestro mutations, terminal identities, and Canvas layout as
  Orca-adapter concerns; and
- collect shadow-only process telemetry when a provider exposes it, without
  inventing prices, cache data, or quality evidence.

## Outcomes

- A user with only a supported local host can complete a direct or verified
  single-agent task with an honest check result.
- A user with OpenSpec gains durable planning only when its risk or uncertainty
  warrants it.
- A user with Orca gains supervised workers and the Canvas for graph-mode work,
  without changing task truth, evidence grades, or acceptance semantics.
- A future host or Canvas implements a small capability/conformance boundary
  instead of forcing a rewrite of skills, policies, or project knowledge.
- A graph is evidence of parallel work, not a visual default or a template of
  ornamental roles.

## Non-goals

- Modify a completed Maestro run or reopen its evidence grades.
- Replace, delay, or make a competing Canvas for Orca.
- Guarantee equal features across hosts or providers.
- Add a generic workflow engine, remote control plane, or model-specific
  scheduler constants.
- Set global numeric defaults for workers, tokens, context, retries, or wall
  time without a task-local policy and observable provider data.
- Automatically invoke `grill-me`; it remains an explicit stress-test tool.

## Evidence

- `research/2026-08-21-adaptive-harness-evidence.md`
- `research/2026-08-21-adaptive-harness-interview-routing.md`
- `openspec/changes/maestro-harness-orchestration/design.md`
