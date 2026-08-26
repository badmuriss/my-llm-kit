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

A checked source box is structural source metadata, not evidence. Validation and run initialization preserve `[x]` tasks as pending and ungraded. The current coordinator explicitly invokes `import-checked-task --generation <generation> --task <task-id> --import-id <stable-id> --note <note>` through the pinned control runtime. Import runs the task's exact `Check` command in the pinned workspace. One stable import ID atomically records the verified artifact, check, and grade. A retry verifies the same evidence and cannot duplicate or partially grade the task. No checkbox can set a grade directly.

## Workspace and attempt identity

Each run starts from one `WorkspaceBootstrapReceipt v1` issued for that run. The receipt names the repository, orchestration home, execution workspace, execution host, base revision, dirty paths, and issuing authority. An automatic Host receipt is available only with explicit `--driver host`. Auto and Orca runs require `--workspace-receipt`. A relative receipt path stays inside the repository. An absolute path may name a host-local external input. The run persists only the validated receipt object, never its source path.

The runtime saves the receipt before `run_started`. It then derives one `WorkspaceScope` from the receipt and adds the run ID, coordinator generation, receipt reference, and receipt hash. Claim verifies the saved receipt separately. Every public mutator replays the complete journal prefix and verifies the binding before generation checks or side effects. Resume can repair a partial tail or stale projection only after this preflight succeeds. A generation change updates only `coordinator_generation`.

A `host-run` receipt is local and run-scoped. It uses a `host-run-<UUIDv4>` repository ID, one identical folder identity for orchestration and execution, the exact canonical repository root, and `folder:<repository_id>` as its workspace key. The local execution-host ID remains opaque.

Folder workspaces and Git worktrees use distinct `kind` values. Workspace and host IDs are opaque receipt values, not task IDs or reconstructed paths. Orca receipts may use keys such as `folder:<folderWorkspaceId>` and `worktree:<repositoryId>::<worktreePath>`, plus host IDs such as `ssh:<id>` or `runtime:<uuid>`. Remote paths may use absolute POSIX or Windows drive syntax.

The orchestration home owns the journal and evidence artifacts. Until remote execution identity is implemented, bootstrap may record another execution scope, but init and claim reject it with `execution_scope_unsupported`. Driver construction, takeover, dispatch, checks, and checked import enforce the same boundary before side effects. The executable scope must be local and exactly equal to the canonical orchestration home.

Each attempt stores an `ExecutionProfile` from `execution-profile.schema.json`. It keeps the requested and resolved agent, model, effort, and placement together. Any supported-value fallback needs a concrete reason.

`PlacementRequest` has three forms:

- `current-workspace` uses the exact pinned execution workspace.
- `existing-workspace` names the execution host and opaque workspace key.
- `create-child-worktree` names the execution host and exact parent workspace key.

`ResolvedPlacement` records the selected host, workspace key, folder or worktree kind, optional disclosed path, and placement receipt. A child must resolve to a new Git worktree on the requested parent host.

## Scheduling

A dependency unblocks its consumers only after a coordinator records grade `pass`. A worker report, provider completion, or successful process exit does not unblock a dependency.

The scheduler scans tasks in document order and returns a deterministic maximal ready wave. Concurrent write tasks cannot have overlapping path prefixes. Read tasks do not claim write ownership.

Each normal `check_recorded` event names the latest reported attempt. The attempt keeps its own report and check. The task check is only the latest alias. Historical numbering comes from prior `attempt.check` records, so a retry creates `TASK-002` and cannot reuse `TASK-001` evidence. Checked-task import remains a separate check-backed contract without a worker attempt.

For a latest reported, ungraded attempt with its own failed check, `record-repair` appends `attempt_check_rejected` only after cleanup owned by that attempt is settled or explicitly retained. The event stores one normalized, distinct hypothesis on the attempt, preserves its immutable report and failed check, clears only the task's latest-check alias, and returns the task to pending for a fresh attempt ID without grading it. Replaying the same attempt and byte-equivalent hypothesis is idempotent; a changed hypothesis conflicts.

`record-finding` accepts exactly one fenced public record, either `--finding` or `--finding-json`, before it mutates the journal. A record names one of `acceptance_violation`, `reproducible_regression`, `security_or_integrity`, `hardening`, or `advisory`. A blocking record names the violated acceptance reference, affected file and identity, reproduction or verifiable reasoning, the smallest repair hypothesis, and why the selected Check misses it.

The coordinator may run `audit-reject-attempt` only for a latest reported, ungraded attempt with its own passing Check and registered blocking finding. A failed Check always follows `record-repair`. `attempt_audit_rejected` preserves the report, receipt, and Check, records one normalized hypothesis, and returns the task to pending. Exact replay is idempotent.

The default budget is one implementation plus one repair. After that repair, dispatch remains fenced until one explicit coordinator decision amends acceptance or Paths, regroups the package, accepts the Check, requests input, or blocks the task. An amendment or regroup can authorize exactly one third attempt. A fourth attempt, stronger model, or new hypothesis never starts automatically. `hardening` becomes a durable `carry_forward` record and does not prevent an otherwise valid pass. `advisory` neither blocks nor consumes repair budget.

Finding references use an existing confined `file:<repository-relative-path>` or an existing `commit:<full-sha>`. The retry remains blocked while any cleanup linked through `attempt.cleanup_id`, `cleanup.owner`, `cleanup.owner.attempt_id`, or `cleanup.attempt_id` is missing or nonterminal.

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

Attempts, questions, cursors, and cleanup records have explicit schemas. New process cleanup records use `{kind: "process", root_pid: <integer>}` rather than a descriptive PID string. Their owner names exactly one attempt or coordinator generation, the execution host and workspace, terminal and incarnation when present, and the optional process root. Finish evidence repeats that identity and lists descendants separately. A terminal ID alone cannot authorize release. Historical malformed cleanup records remain readable as recorded; they can be retained with a bounded reason and a distinct replacement cleanup reference, never rewritten into the typed form.

Driver selection and task attempts are journaled as reservations before provider mutation. A crash can therefore leave an explicit incomplete reservation instead of an invisible orphan. `recover-driver-selection` and `recover-attempt` replay the same provider retry identity. A lost attempt becomes retryable only after driver reconciliation, proven release, and an `attempt_abandoned` transition.

Driver cleanup is independently recoverable after a report is durable. `sync` retries pending driver-owned cleanup, and `recover-cleanup` accepts reported or audit-rejected attempts. A tracked terminal listing that proves the recorded handle is already absent is a successful idempotent release. `cleanup-retain` records a separate `cleanup_retained` transition with an explicit receipt. Done, verified, or retained cleanup unblocks retry; cleanup never relies on an unverified caller receipt.

## Structured results

Workers write one closed object that conforms to `worker-result.schema.json`: `outcome` is always `reported`, `external_refs` is an object, and evidence uses only `file:` or full-SHA `commit:` references. A no-change report may use empty `files_changed` and `checks_run` to record a blocker, question, or audit finding without inventing a check. A report with changed files must name at least one check. A WorkerResult only reports work: it cannot grade a task or author a task status. The coordinator's attempt-bound Check/import and public `grade` command own those transitions. A graph amendment names its active parent task and attempt, coordinator generation, normalized paths, and reason. The reducer derives an immutable effective path union, ordered amendment IDs, and digest for that attempt. Dispatch stores that exact scope in the worker capsule, and result validation uses it without changing the frozen task contract. The coordinator rejects unknown fields, mismatched task or attempt IDs, duplicate terminal reports, unsafe evidence references, and files outside that effective path union.

## Malformed result quarantine

`quarantine-result` is the public path for a malformed canonical result candidate. `record-result` detects malformed bytes at that same canonical path and performs the identical fenced, content-addressed quarantine before returning its receipt. Both paths require the current coordinator generation, exact task and running attempt, and validate the run binding before any mutation. They read raw bytes without normalization and atomically relocate them to `artifacts/result-quarantine/sha256/<digest>.json`. Orca derives the key from the exact attempt, message, and delivery identities; a caller-supplied mismatch fails closed. The bounded receipt and `attempt_result_quarantined` event contain only paths, digest, byte length, validation error code, task, attempt, generation, revision, and key, never the invalid body.

The same key and digest replay idempotently. Changed bytes, a reused key, stale authority, a missing candidate, symlink, path escape, noncanonical path, or an existing conflicting receipt fail closed. Receipt generation and revision are immutable issuance metadata. A current fenced caller may recover a receipt issued by an earlier coordinator generation or projection revision for the same bound running attempt, but never rewrites it. A durable quarantine terminates that attempt's result slot. It neither records a worker report nor changes audit hypotheses, implementation-failure counters, or grades. Reconciliation and recovery return the saved receipt without rereading, replacing, or recreating its canonical path; after cleanup is settled, public abandonment closes that attempt and a fresh attempt ID is required.

Once a host result is reported, its canonical bytes and report receipt are also immutable. `record-result`, `sync`, recovery, and resume verify the stored digest before lifecycle mutation. Divergent bytes are preserved as content-addressed quarantine evidence and return one bounded integrity error naming the accepted receipt and observed digest. Restoring the exact accepted bytes makes the original report replay idempotently without a second event.

The coordinator capsule conforms to `coordinator-capsule.schema.json`. It contains repository and run identity, a dirty-path snapshot, the generation, and the exact resume command. It contains no conversation or worker transcript.

## Context capsules

`context_capsules.py` builds one immutable capsule for each attempt. A capsule contains repository-relative artifact references and bounded excerpts, not full artifacts. Each reference records its origin, snapshot path, SHA-256 hash, revision, media type, title, and priority.

Composition seeds material depth only at the task reference, which is the first material item, while also traversing from `attempt_id` as a non-material graph anchor. It follows `depends_on` from a task to its dependency, `context_for` from a target to its selected context, and `produces` from a producer to evidence. Only the attempt anchor is traversal-only and never snapshotted as a capsule item, even when an input reference ID collides with the attempt ID. A visited set stops cycles. Stable edge and reference ordering makes the same inputs produce the same capsule ID. Lifecycle edges such as `executes`, `reports_to`, and `spawned_by` never import terminal output, worker reports, prompts, or conversations.

Selection always keeps the task contract first. User notes follow, then dependency digests and decisions, then source and evidence references. The item budget limits references. Byte and token budgets limit excerpt material. The portable token estimate counts UTF-8 bytes, which is deliberately conservative. Oversized content stays available through its pinned artifact path and receives only a bounded digest. Composition confines every reachable snapshot to the repository and verifies its hash before applying the selection budget.

The coordinator fetches a Maestro note with an authenticated `fetch_and_pin_revision` transaction. It requests the exact revision and expected hash. Unauthorized, missing, expired, changed, or non-Markdown responses fail before composition. A valid response becomes `openspec/runs/<change>/<run-id>/artifacts/maestro-notes/<note-id>/<revision>.md`. The writer never replaces an existing revision file. A later note edit creates another revision path and cannot change a dispatched capsule. Maestro retains every fetched revision until the coordinator calls `release_run_revisions` for the terminal run.

### Reused writer handoffs

Graph mode starts as `single_writer`. It may reuse an explicit Host-native worker handle only after the prior dependent task has passed and the handle, workspace scope, and complete execution profile are byte-equivalent. Host never guesses an agent command or turns a missing handle into a worker. The follow-up handoff carries only the current task acceptance, approved dependency summaries, changed paths since the prior Check, unresolved finding references, allowed paths, selected Check, and bounded session memory. It excludes the projection, task graph, terminal transcript, prior report body, and complete specification. Any profile, ownership, workspace, lease, remote-boundary, or context-budget uncertainty requires a fresh session instead.

## Maestro protocol v1

`agent-graph-view.schema.json`, `maestro-mutation.schema.json`, and `delegation-intent.schema.json` define the Canvas boundary. Conformance fixtures live under `fixtures/maestro-protocol-v1/`.

`AgentGraphView v1` contains bounded task, attempt, note-reference, terminal-receipt, evidence, cleanup, and portal nodes, plus a required `RunProgressSummary v1`. Typed edges connect those nodes. Snapshots and deltas carry a revision and resumable cursor. A non-null progress activity sequence must equal that view revision. The view excludes prompts, conversations, terminal output, transcripts, full file bodies, and unbounded reports.

`RunProgressSummary v1` is derived only from the journal reducer and its observed final envelope. It reports exclusive task counts, bounded current and next tasks, cleanup groups, blocker and material-finding identities, and one deterministic state. Terminal presentation, idle indicators, provider completion, silence, and apparent stalls do not affect it. A complete state and 100 percent require no carry-forward finding, unresolved material finding or owned cleanup, blocked or failed task, unresolved input, or partial outcome. Retryable findings remain material without blocking runnable work. Unobserved task outcomes and unverifiable cleanup remain `outcome_unknown`.

The journal and reducer are canonical for progress. Frames emitted by
`status --watch` are projections, not canonical events. The watch emits
resumable NDJSON projections from the reducer, and consumers resume with its
bounded cursor. Consumers must not infer progress from a checkbox, terminal
decoration, provider completion, apparent idleness, or process exit.

Frontend tasks request either a `visible` native browser surface or an explicit
`offscreen` surface. A visible capture requires an observed native pane, focus,
paint, exact page binding, and a linked vision review. An offscreen capture is
valid only when the request explicitly selected offscreen and the receipt keeps
that observation. Unsupported or unobservable required surfaces become
`unobserved` or `blocked`; they never silently downgrade to headless evidence.
Page cleanup uses the exact surface and page binding from the receipt. The
Harness releases a page only after durable evidence exists, the attempt is
settled, `retention=false`, ownership is Harness, and the exact binding is
verified. Other cases retain the page or remain `unverifiable`, and the
release or retention receipt is recorded before grading.

Maestro mutations and delegation intents carry an authenticated actor envelope, exact workspace anchor, expected revision, and coordinator generation. Note content travels only as an immutable hash-identified snapshot path. Cross-workspace or stale-generation input fails closed.

## Adaptive intake contracts

`process-decision.schema.json` defines `ProcessDecision v1`. It records only the
request digest, repository scope, observable task signals, explicit assumptions,
material questions and their decision effects, the selected process mode and
check, task-local limits, transition triggers, and a contiguous amendment
history. `initial_mode`, `mode`, and `revision` make every later mode change
auditable. An amendment carries the changed evidence and replacement check.
Conversation transcripts, terminal output, provider or model choices, global
scores, and universal thresholds are not decision fields.

`capability-receipt.schema.json` defines `CapabilityReceipt v1`. Every adapter
declares the same complete set of portable capability names with a supported,
unsupported, or unavailable status. A supported claim includes verification;
missing requested capabilities select an explicit compatible downgrade or block
only that operation. Adapter identity is core data, while provider commands,
model identifiers, terminal handles, Canvas state, and future adapter data live
only in the receipt's bounded `extensions` namespaces. Unknown extension values
remain forward-compatible without becoming portable capability claims.

The process decision is made before capability resolution. A capable adapter
cannot promote a cohesive task into graph mode, and a missing optional adapter
feature cannot invalidate work that a smaller selected mode can execute.

## Harness integration contract

The coordinator consumes task execution hints, role and risk metadata, bounded
context references, and the runtime capability catalog. Spec validation checks
these fields and the exact `Check` command, but never dispatches or materializes
a worker. A normal impl handoff freezes the control runtime, requests
`strong` plus supported `xhigh` for the fresh coordinator, and records any
fallback before worker planning.

Automatic decomposition is role-based, not a fixed team: coordinator,
research, documentation, implementation, review, verification, and integration
roles are created only for ready work. Workers resolve the cheapest sufficient
profile and persist requested/resolved model and effort independently, with
fallback, rationale, role, risk, and cost rank. Dynamic delegation can narrow
the parent's paths and capsule only; a child cannot widen its allowance, grade
its parent, become a recursive delegation parent, or mutate the journal. The
coordinator keeps one heavy worker at a time and chooses the smallest useful
path-safe wave.

Research collectors are `Mode: read` tasks that return source URLs, access
dates, local artifacts, provider trail rows, and verification status. The main
researcher opens and adjudicates sources and owns conclusions. Host and Orca
drivers receive the same capsule, profile, evidence, and cleanup contract; no
Orca API or optional Linux resource guard is required for the Host path.

Learning reads only completed canonical graph state and writes a deterministic,
bounded projection of task checks, evidence references, visual expectations,
and lifecycle facts. Prompts, report bodies, terminal output, note bodies, and
conversation transcripts are excluded even when present in the source state.

## Maestro compatibility export

`export_maestro_compatibility.py --repo <repo> --change <change> --run-id <run>
--output <directory>` is the portable producer boundary for Maestro. It accepts
only a completed passing Harness run whose required capability tasks have
passing immutable checks plus either checked-import or ordinary grade/check
evidence, and whose owned cleanup is verified. For ordinary grades, the exact
`check_recorded` event and byte-identical state projection establish
`status: passed`; the public check artifact must match its command, task,
attempt, zero exit, and non-timeout result, but need not repeat a status field.
Checked-import artifacts retain their published `status: passed` requirement. It
reads the exact `events.jsonl`, `state.json`, and `control-runtime-ref.json`
bytes and records their SHA-256 digests. A released control-runtime directory
is not required: the persisted reference and its recorded directory digest are
the immutable runtime identity.

The exporter writes canonical JSON under
`<output>/sha256/<manifest-byte-digest>/`: one manifest and exactly eight
receipts. The existing seven capability receipts remain stable and the eighth
binds the pinned routing policy. The run-progress receipt jointly binds the
passing MLK-07, MLK-07P, and MLK-19 producers. The routing-policy receipt binds
the MLK-20 producer to the real `artifacts/routing-policy-v1.json` bytes and to
the approved attempt's canonical policy digest. Each receipt binds the producer
run, task grade, check/import evidence bytes, opaque workspace scope, and
control-runtime identity. The manifest lists the exact receipt byte digests and
required capability set. The CLI reports the exact canonical
`<output>/sha256/<manifest-byte-digest>/manifest.json` path. The exporter
never starts work or mutates the source run.

A checked import backed by `CheckExecution v1` resolves exactly one projected
execution by its artifact and exact `import:<task>:<import-id>` consumer. The
canonical journal replay must reproduce the same task and execution. Execution
ID, command digest, source-snapshot digest, passing lifecycle, exit, timeout,
and artifact bytes must agree. Fields that are absent from the versioned
artifact are not reconstructed. Legacy checked-import and ordinary check
artifacts retain their published shapes.

The result-quarantine capability receipt also binds the passing MLK-06Q,
MLK-06QR, and MLK-15 producer tasks. It includes each task's immutable check,
checked-import receipt when present, and evidence digests. This prevents a
Maestro consumer from treating quarantine support as ready when its recovery or
integrity proof is absent.

Symlinks, traversal, incomplete journals, missing evidence, non-passing or
partial runs, unresolved cleanup, and content-address collisions fail closed.
