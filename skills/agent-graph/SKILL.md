---
name: agent-graph
description: Run dependency-aware agent task graphs with durable repository state, evidence grading, portable drivers, and fresh coordinator handoff.
---

# Agent Graph

Use this skill when a workflow needs durable task identities, explicit dependencies, bounded path ownership, or crash-safe coordination across agents.

## Core contract

Treat `events.jsonl` as canonical. Rebuild `state.json` from its events. Only the current coordinator generation may append an event.

Parse each task's `Depends`, `Paths`, `Mode`, `Isolation`, `Acceptance`, and single `Check` field. Reject unsafe paths and invalid dependency graphs before dispatch.

Schedule a task only when every dependency has grade `pass`. Serialize write tasks whose file or directory prefixes overlap. A worker report changes an attempt to `reported`; it never grades the task.

## Safety rules

- Give workers one task capsule, not the full planning transcript.
- Keep workers from writing the journal.
- Validate every worker result against its task and attempt.
- Run checks and assign grades in the coordinator.
- Archive and remove only a partial final journal line. Treat all earlier corruption as fatal.
- Register resources that need cleanup and retain their receipts.
- Reserve driver selection and attempts before provider mutation. On resume, use `recover-driver-selection` or `recover-attempt` with the same provider retry identity. Use `abandon-attempt` only when driver reconciliation and release prove cleanup.
- Retry pending driver-owned release with `sync` or `recover-cleanup`; never mark terminal cleanup done from an unverified caller claim.
- Never treat provider completion as evidence of `pass`.

See [the task graph reference](references/task-graph.md) for the data model and scheduler rules.
