# Portable agent graph orchestration

## Why

Large `impl` and research runs currently depend on one coordinator session. The session decides task order, carries worker output, integrates changes, and grades evidence. Its context grows with every dispatch and becomes the only place that knows what happened.

The existing implementation state solves atomic writes and basic resume, but models tasks as a flat list. It does not encode dependencies, write conflicts, attempts, provider references, or a reconstructable event history.

Orca already offers useful coordination primitives. A live probe confirmed Run, Task, dependency gating, Dispatch, ask/reply, and `worker_done`. The same probe also found a degraded path where `worker-start` could not resolve a valid worktree and low-level Dispatches did not gain supervised worker ownership. The harness must use Orca without depending on one happy path.

Native Codex subagents solve context isolation, but the probe did not expose durable Task, Dependency, or Dispatch IDs. The kit must provide those identities itself.

## Change

Create a portable agent graph runtime owned by `my-llm-kit`.

The runtime will:

- treat the user-facing `$impl <slug>` call as a bootstrap and transfer execution to a fresh coordinator session;
- parse explicit dependencies, repository path scopes, access mode, and isolation from `tasks.md`;
- keep a single-writer, append-only journal and a reconstructable state projection in the repository;
- schedule only evidence-approved dependencies and non-conflicting write scopes;
- expose Orca and host-native drivers behind one small contract;
- distinguish a worker report from a passing task grade;
- store terminal output and provider receipts as artifacts instead of copying them into the coordinator context;
- resume attempts and cleanup from repository state;
- provide the same graph semantics to `impl` and research;
- reserve a driver boundary for Maestri without implementing or guessing its API.

This is a clean replacement of the flat impl state. The repository shows no active external contract that requires a compatibility layer.

## Outcomes

- Orca users can inspect real Run, Task, Dispatch, question, and terminal activity.
- Non-Orca users retain durable graph state and can use host-native subagents or local execution.
- Implementation starts in a clean coordinator context instead of inheriting the planning or research conversation.
- A coordinator can recover after context loss without reconstructing history from chat.
- Parallel writes require explicit, non-overlapping path scopes.
- Provider completion cannot bypass task checks or integration review.

## Non-goals

- Build a general workflow engine.
- Add LangGraph, Temporal, or another orchestration dependency.
- Implement the future Maestri driver.
- Infer arbitrary glob intersections.
- Preserve the current flat state schema or CLI.
- Automatically merge conflicting worktrees.

## Evidence

The baseline runtime probe is recorded in [evidence/baseline-orchestration-probe.md](evidence/baseline-orchestration-probe.md). The research and source adjudication live in [the research finding](../../../research/2026-08-20-agent-orchestration-harness.md).
