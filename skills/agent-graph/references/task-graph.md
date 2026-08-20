# Task graph contract

Agent Graph turns an OpenSpec task list into a validated directed acyclic graph. The repository journal owns task truth. Drivers only transport task capsules and results.

## Task fields

Each Markdown task has a stable ID and exactly one of every required field:

```md
- [ ] API-01 Implement the endpoint
  Depends: [DOMAIN-01]
  Paths: [src/api/, tests/test_api.py]
  Mode: write
  Isolation: auto
  Acceptance: The endpoint returns a validated domain result.
  Check: python3 -m unittest tests.test_api
```

`Depends` lists task IDs. `[]` marks a root task. Every referenced task must exist, and the graph must not contain self-dependencies or cycles.

`Paths` lists normalized repository-relative files or directory prefixes. A directory ends in `/`. Absolute paths, backslashes, `.` or `..` segments, and globs are invalid.

`Mode` is `read` or `write`. Read tasks cannot report changed files. `Isolation` is `auto` or `worktree`; isolation never overrides dependency or conflict rules.

## Scheduling

A dependency unblocks its consumers only after a coordinator records grade `pass`. A worker report, provider completion, or successful process exit does not unblock a dependency.

The scheduler scans tasks in document order and returns a deterministic maximal ready wave. Concurrent write tasks cannot have overlapping path prefixes. Read tasks do not claim write ownership.

## Durable state

One run stores:

```text
openspec/runs/<change>/<run-id>/
  events.jsonl
  state.json
  artifacts/
  capsules/
  results/
```

Each append flushes and syncs the journal before atomically replacing `state.json`. The journal is canonical; resume rebuilds a missing or stale projection after a valid replay.

The journal accepts recovery only when its last line lacks a newline. Recovery archives those exact bytes, truncates the incomplete tail, and appends `journal_repaired`. Invalid JSON or invalid events on complete lines block the run.

Every mutation presents the active coordinator generation. Transfer or takeover increments that generation and fences the previous coordinator.

Driver selection and task attempts are journaled as reservations before provider mutation. A crash can therefore leave an explicit incomplete reservation instead of an invisible orphan. `recover-driver-selection` and `recover-attempt` replay the same provider retry identity. A lost attempt becomes retryable only after driver reconciliation, proven release, and an `attempt_abandoned` transition.

Driver cleanup is independently recoverable after a report is durable. `sync` retries pending driver-owned cleanup, and `recover-cleanup` retries one reported attempt explicitly. A tracked terminal listing that proves the recorded handle is already absent is a successful idempotent release; cleanup never relies on an unverified caller receipt.

## Structured results

Workers write one object that conforms to `worker-result.schema.json`. The coordinator rejects unknown fields, mismatched task or attempt IDs, duplicate terminal reports, unsafe evidence references, and files outside the task's declared paths.

The coordinator capsule conforms to `coordinator-capsule.schema.json`. It contains repository and run identity, a dirty-path snapshot, the generation, and the exact resume command. It contains no conversation or worker transcript.
