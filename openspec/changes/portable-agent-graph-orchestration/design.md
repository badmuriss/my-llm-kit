# Design

## Architecture

`my-llm-kit` owns the canonical graph. Drivers translate graph actions into an execution environment. A driver never owns task truth or evidence grades.

```text
tasks.md
   |
   v
graph parser and validator
   |
   v
events.jsonl  ->  state.json  ->  ready task query
   ^                               |
   |                               v
verifier and integrator      Orca or host driver
   ^                               |
   |                               v
structured worker result  <-  task capsule
```

The runtime lives in a new `agent-graph` skill. This avoids naming collisions with Orca's own `orchestration` skill and gives `impl` and research one shared contract.

## Task contract

Every task keeps the existing checkbox, stable ID, acceptance criterion, and one `Check:` line. It adds these required fields:

```md
- [ ] API-01 Implement the endpoint
  Depends: [DOMAIN-01]
  Paths: [src/api/, src/api.test.ts]
  Mode: write
  Isolation: auto
  Acceptance: The endpoint returns the validated domain result.
  Check: python3 -m unittest tests.test_api
```

`Depends` contains task IDs. An empty list declares a root task.

`Paths` contains normalized repository-relative files or directory prefixes. A directory ends with `/`. Globs, absolute paths, `..`, and empty values are invalid. Prefixes make conflict detection deterministic across platforms.

`Mode` is `read` or `write`. A read task may inspect its declared context without claiming write ownership. A write task may change only its declared paths.

`Isolation` is `auto` or `worktree`. `auto` uses the current checkout unless the driver has a concrete placement constraint. `worktree` requests a separate checkout. Worktree isolation does not waive dependency or path-conflict rules.

The parser rejects duplicate IDs, unknown dependencies, self-dependencies, cycles, missing fields, duplicate fields, unsafe paths, and any task without exactly one `Check:` line.

## Scheduler invariants

- A task becomes ready only when every dependency has grade `pass`.
- `worker_done`, process exit, or a result file moves an attempt to `reported`. It never moves the task to `pass`.
- Each worker has at most one active attempt.
- Read tasks may share a checkout.
- Write tasks may run together only when their normalized path prefixes do not overlap.
- Overlapping write tasks are serialized even when separate worktrees could hide the filesystem conflict.
- A failed or blocked dependency keeps downstream tasks blocked with a recorded reason.
- The scheduler chooses no fixed fan-out. Host limits and the repository resource policy remain authoritative.

The integrator remains the only actor that applies task grades. It reviews the diff, runs the recorded check, validates visual evidence when present, and then appends `task_graded`.

## Fresh coordinator bootstrap

The user-facing `$impl <slug>` invocation is a bootstrap, not the implementation coordinator. This rule applies even when the invoking conversation appears short. A deterministic handoff is safer than estimating context fullness from token counts or model behavior.

The bootstrap performs only bounded work:

1. Resolve the repository and slug.
2. Validate `proposal.md`, `design.md`, and `tasks.md` without loading their full content into the conversation.
3. Inspect active run state, dirty paths, and live coordinator ownership.
4. Write a coordinator capsule under the run directory.
5. Start or instruct one fresh top-level coordinator session in the same checkout.
6. Stop the invoking session after the handoff receipt is verified.

The capsule contains the repository path, slug, run ID, driver selection, base commit, dirty-path snapshot, coordinator generation, and exact resume command. It contains no conversation transcript, research transcript, or worker output.

The fresh session receives only the capsule path and this instruction:

```text
$impl --coordinator-capsule <repository-relative-path>
```

That internal invocation claims coordinator ownership and skips another bootstrap. A normal `$impl <slug>` never runs implementation work in place.

State records one `coordinator_id` and a monotonically increasing `coordinator_generation`. Every mutation presents the current capsule generation. A stale coordinator receives an error and cannot append events. Explicit takeover reconciles workers and cleanup, increments the generation, records `coordinator_taken_over`, and invalidates the prior capsule.

### Orca bootstrap

Orca creates a fresh Codex or Claude terminal in the current worktree and sends the capsule invocation as a full handoff. It does not create a worker Task or Dispatch for the coordinator. The new terminal creates or binds the Orca Run after claiming the local coordinator generation.

The bootstrap uses the current worktree because the spec or prior implementation state may be uncommitted. It creates a separate worktree only when the user or task contract requires one. After prompt delivery is confirmed, the old session stops monitoring and does not read the new terminal.

### Bootstrap without Orca

If the host exposes a visible top-level fresh-session handoff, use it with the same capsule. A nested or hidden subagent is not a coordinator substitute.

When the host cannot open a visible fresh session, the bootstrap prints the exact capsule invocation and stops before implementation. The user opens one new top-level session and submits that invocation. This manual boundary preserves portability and prevents the full session from silently becoming coordinator.

## Durable state

Each run uses:

```text
openspec/runs/<change>/<run-id>/
  events.jsonl
  state.json
  artifacts/
  capsules/
  results/
```

`events.jsonl` is canonical. `state.json` is a projection rebuilt from the journal. One coordinator process is the journal writer. Workers report through the driver and never append directly.

The writer appends one JSON object, flushes it, and calls `fsync`. Resume accepts a final partial line only as a crash artifact: it archives the bytes, truncates that line, appends `journal_repaired`, and rebuilds the projection. Invalid data anywhere else blocks the run.

Core event types are:

- `run_started`, `coordinator_claimed`, `coordinator_transferred`, `coordinator_taken_over`, and `driver_selected`;
- `task_ready`, `attempt_started`, and `driver_degraded`;
- `question_opened` and `question_answered`;
- `worker_reported`, `check_recorded`, and `task_graded`;
- `cleanup_registered` and `cleanup_finished`;
- `run_completed`.

Each attempt stores its local ID, task ID, driver, worker identity, lifecycle tier, external references, artifact paths, timestamps, outcome, and cleanup ownership. Exact provider receipts go to artifacts and are referenced by path.

## Worker result

A worker returns a schema-validated JSON object:

```json
{
  "task_id": "API-01",
  "attempt_id": "attempt-01",
  "outcome": "reported",
  "summary": "Implemented the endpoint and ran its focused check.",
  "files_changed": ["src/api/handler.py"],
  "checks_run": ["python3 -m unittest tests.test_api"],
  "evidence_refs": ["file:openspec/runs/change/run/artifacts/check.txt"],
  "questions": [],
  "external_refs": {}
}
```

The runtime rejects unknown fields, mismatched task or attempt IDs, changed files outside `Paths`, unsafe evidence paths, and a second terminal report for the same attempt.

## Driver contract

Drivers implement seven operations:

- `detect`: report availability and capabilities without mutation;
- `start_run`: bind external run state;
- `start_attempt`: deliver one task capsule;
- `poll`: return bounded lifecycle events and a cursor;
- `send`: answer a question or send scoped guidance;
- `release`: clean resources owned by the attempt;
- `reconcile`: inspect external state after resume or connection loss.

Every operation returns a typed receipt. Driver errors enter the journal. `--driver orca` fails when Orca cannot satisfy the minimum tracked tier. `--driver host` never invokes Orca. `--driver auto` records its selection and reason; it does not silently change drivers after the run starts.

## Orca driver

The driver resolves the exact CLI once. It honors `ORCA_CLI_COMMAND`, uses `orca-ide` on Linux outside an Orca terminal, and uses `orca` on other supported hosts. It does not try another executable after a selected CLI fails.

Preflight verifies runtime reachability, the orchestration contract capability, repository registration, and an exact worktree selector.

The driver exposes two lifecycle tiers:

### Supervised tier

Use `worker-start`, `worker-show`, `worker-read`, and `worker-release`. Store Run, Task, Dispatch, terminal, worktree, pane, and process-incarnation references.

### Tracked-terminal tier

If `worker-start` returns a recognized selector or composition failure, create one agent terminal, wait for TUI readiness, and use `dispatch --inject`. Append `driver_degraded` with the exact error and created resources.

This tier uses `dispatch-show`, `check`, and bounded `terminal read`. It does not call worker APIs after the runtime says the Dispatch has no supervised agent terminal. The harness closes only a terminal it created, after terminal completion and identity reconciliation. It never closes a reused or unproven terminal.

The driver maps an Orca `worker_done` to `worker_reported`. The local verifier still decides the task grade. Questions use Orca ask/reply and remain linked to the local attempt.

## Host driver

The host driver keeps all orchestration state in the repository. `start_attempt` writes a compact task capsule and returns it to the coordinator.

When the host exposes a native subagent API, the `impl` or research skill sends that capsule through the host. When no subagent API exists, the coordinator executes one ready task locally. Both paths submit the same worker-result schema.

The host driver does not shell out to a guessed agent CLI. Authentication, sandbox, model routing, and session control remain owned by the active host. Native worker handles are metadata, not durable task identity.

## CLI surface

`agent_graph.py` provides:

- `bootstrap`, `claim-coordinator`, `takeover`, `validate`, `init`, `resume`, `ready`, and `status`;
- `dispatch`, `sync`, `record-result`, `reply`, and `recover-cleanup`;
- `run-check`, `grade`, cleanup commands, `digest`, and `complete`;
- `probe-orca` for a bounded, read-only integration probe with explicit cleanup.

Agent-facing calls support JSON output. Human status shows task, dependencies, attempt, driver tier, worker, evidence grade, blockers, and cleanup. `status --watch` reads the projection and does not copy terminal transcripts.

## Integration with existing harnesses

`spec` emits and validates the expanded task contract. It never starts workers.

`impl` first transfers to a fresh coordinator through the bootstrap contract. The claimed coordinator initializes or resumes the graph, queries ready tasks, chooses the smallest useful wave, and uses the selected driver. It preserves current evidence grades, repair caps, visual validation, cleanup, and shadow learning.

Research uses the same runtime for collector tasks. Research tasks default to `Mode: read`. Collector results are artifacts; the main researcher still adjudicates claims and owns the final finding.

The current `impl_state.py` state and CLI are removed. `learning.py` reads completed agent-graph projections. No migration or dual write is added because the repository has no active external state contract.

## Maestri boundary

This change does not create a Maestri adapter. A future adapter must implement the driver contract and pass the shared driver conformance suite. It cannot change task readiness, evidence grading, journal semantics, or worker-result validation.

## Real-environment validation

The baseline probe used the installed Orca runtime and one read-only Codex terminal. It confirmed task dependency gating, ask/reply, completion messages, and terminal reuse through low-level Dispatch. It also reproduced selector and ownership failures in the supervised APIs. The native Codex probe returned a useful result but no durable graph IDs.

This is a weak sample from one Orca installation and one native subagent. It decides required recovery behavior, not general product reliability. Exact commands and identifiers are recorded in [evidence/baseline-orchestration-probe.md](evidence/baseline-orchestration-probe.md).

The baseline did not test fresh coordinator transfer. The final live probe must open a separate coordinator terminal, prove that it claims the local generation, and prove that the bootstrap session cannot mutate the run afterward.

## Decisions

- The repository journal is canonical. Orca is not required for correctness.
- A normal `$impl <slug>` always hands off to a fresh top-level coordinator.
- The invoking session stops after the handoff and never supervises the coordinator as a worker.
- Only the coordinator writes the journal.
- Path scopes use prefixes, not globs.
- Orca degradation stays inside the Orca driver and is always visible.
- A worker report and an evidence grade are separate states.
- The flat impl state is replaced without compatibility code.

## Rejected alternatives

- Orca as canonical state: prevents non-Orca execution and couples resume to one runtime.
- Native subagent state as canonical: does not provide a portable durable graph contract.
- Continue implementation in the invoking session when it seems fresh: freshness cannot be verified and the behavior would vary by host.
- Use a nested native subagent as coordinator: recreates the hidden-session problem and returns orchestration output to the old context.
- LangGraph or Temporal: adds a dependency before the kit needs a general workflow engine.
- One new worktree per task: increases setup and integration cost without modeling semantic conflicts.
- Arbitrary glob scopes: deterministic overlap analysis is complex and unnecessary for the MVP.
- Automatic Maestri stub: invents an unverified API and creates code that cannot be validated.

## Assumptions

- The kit remains an MVP without active external state consumers.
- Python standard library remains sufficient for the runtime.
- The Orca CLI continues to provide JSON receipts for the documented commands, while exact capabilities are checked at runtime.
