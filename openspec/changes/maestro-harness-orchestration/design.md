# Design

## System boundary

`my-llm-kit` remains the canonical planner, journal, scheduler, evidence grader, and context composer. Orca is an execution host and a visual client. A host without Orca implements the same attempt contract without pretending to offer Orca-specific terminal ownership.

```text
OpenSpec task graph and user intent
                 |
                 v
fresh strong coordinator, fenced by generation
                 |
      +----------+-----------+
      |                      |
      v                      v
routing planner       context composer
      |                      |
      +----------+-----------+
                 v
        canonical event journal
                 |
        +--------+---------+
        |                  |
        v                  v
 compact AgentGraphView   ready attempts
        |                  |
        v                  v
 Orca Maestro client   Orca or host driver
        |                  |
        +---- intents -----+
```

The Canvas records document edits and delegation intents. It never appends canonical graph events or launches an agent directly. The current coordinator validates an intent, reserves a mutation, calls the selected driver, persists the external receipt, and only then publishes the resulting node and edges.

## Workspace and ownership identity

Every run pins a `WorkspaceScope`:

- repository identity and canonical root;
- execution host identity;
- workspace key for a folder workspace or Git worktree;
- worktree path when applicable;
- base revision and dirty-path snapshot;
- orchestration home and execution workspace;
- run ID and coordinator generation.

It also pins a `ControlRuntimeRef` containing the immutable entrypoint, directory digest, protocol version, source revision, and creation receipt used for every coordinator command in that run. Resume rejects a missing or divergent runtime instead of importing whatever Python files are currently in the worktree.

`orchestration_home` is where the canonical run is coordinated. `execution_workspace` is where an attempt executes. They may differ for a child worktree. Resume uses the pinned identities and fails closed when the runtime cannot resolve them. It never redetects the current checkout and silently rebinds the run.

The initial binding comes from a host-authored `WorkspaceBootstrapReceipt v1`, never from a path-derived repository or workspace ID. It contains exactly `schema_version`, `repository_id`, `canonical_root`, `execution_host`, `orchestration_home`, `execution_workspace`, `base_revision`, `dirty_paths`, and `authority { kind, scope, issued_for_run_id }`. `bootstrap` accepts an absolute host-local receipt path, or a repository-relative path for portability, validates it before creating the run directory, then atomically copies and hashes only the canonical object under the run. The source path is not durable state. `WorkspaceScope.binding_receipt_ref` points to that saved artifact, and every claim, resume, takeover, check, import, and dispatch verifies the saved binding without rereading the source or calling a current-workspace detector.

Explicit portable Host mode may create a cryptographically random `host-run-<uuid>` folder identity when no external receipt exists. That authority is scoped to one run, binds both workspace identities and the canonical root to the resolved repository, and is never presented as an Orca or globally stable workspace. `auto` and `orca` do not fall back to this identity. A receipt for a remote host or a different execution workspace may be preserved by `bootstrap`, but until the selected driver can resolve it, `init`, coordinator claim, driver selection, checks, checked imports, and dispatch fail with `execution_scope_unsupported` before journaling, provider invocation, subprocess execution, or evidence writes. MLK-05 replaces that temporary execution gate with exact driver resolution from the saved host/workspace pin.

An attempt owns only the resources listed in its receipt. Terminal ID alone is insufficient. Cleanup identity includes execution host, workspace key, terminal ID, terminal or PTY incarnation, process root when observable, attempt ID, and ownership provenance.

`attempt_reserved` requires a complete `workspace_scope` equal to the run pin and an execution profile whose placement request is valid inside that scope. `attempt_started` reuses the reserved scope and profile exactly. It cannot omit, fabricate, redetect, or replace either value from the coordinator's ambient checkout.

## Execution profiles and routing

`ExecutionProfile` and placement are attempt-level state:

```json
{
  "role": "implementation",
  "requested": {
    "lane": "fast",
    "agent": null,
    "model": null,
    "effort": "low"
  },
  "resolved": {
    "agent": "codex",
    "model": "runtime-model-id",
    "effort": "low"
  },
  "fallback_reason": null,
  "placement_request": {
    "kind": "create-child-worktree",
    "execution_host_id": "host-id",
    "parent_workspace_key": "workspace-key",
    "name_hint": "api-worker"
  },
  "resolved_placement": {
    "execution_host_id": "host-id",
    "workspace_key": "child-workspace-key",
    "kind": "git-worktree",
    "path": "host-native-path",
    "receipt_ref": "artifact:placement-receipt.json"
  }
}
```

`PlacementRequest` is discriminated: use the current pinned workspace, select an advertised existing workspace, or create a child worktree under an exact parent. Remote selection always names the target `ExecutionHostId`; a boundary enum alone is insufficient. `ResolvedPlacement` contains the host, workspace key, folder/worktree kind, host-native path where disclosure is safe, and verifiable placement receipt.

Portable lanes are `fast`, `balanced`, and `strong`. Provider names and model IDs come from runtime capability catalogs. If a current Codex catalog advertises Luna, Terra, and Sol, those can satisfy the lanes; their names are not embedded into graph scheduling logic.

The planner applies these rules in order:

1. Explicit user overrides win when supported and safe.
2. The pinned external policy selects the coordinator lane and effort for the current role and risk. A large source graph alone cannot raise either one.
3. If the requested route is unavailable, the runtime follows only the policy's ordered compatible candidates and records the requested value, resolved value, and reason; otherwise it blocks.
4. Workers start at the cheapest lane and lowest effort compatible with their role, task risk, required tools, context size, and acceptance check.
5. Security, data integrity, broad architecture, cross-cutting integration, and ambiguous failure recovery raise the lane or effort deterministically.
6. Documentation, bounded research collection, mechanical edits, and focused verification may use cheaper profiles when their checks contain the risk.
7. Model and effort remain independent. A cheaper model at high effort and a stronger model at low effort are distinct choices.
8. Provider-specific effort choices live in the policy. The scheduler does not assume that `xhigh` is globally superior or equivalent across providers. An exceptional expensive route still requires a concrete persisted reason, and no retry raises cost automatically.
9. Provider price or catalog changes alter capability data, not graph semantics.

Concrete routing preferences live in a strict `RoutingPolicy v1` artifact outside the scheduler. The policy maps abstract lanes and task requirements to ordered provider, agent, model, and effort candidates. A provider catalog remains the authority for what is actually launchable and which usage, token, cache, quota, and cost fields are observable. Missing observations are `unavailable`; effort labels from different providers are never silently equated.

Before the first attempt route is reserved, the run validates and copies the selected policy, pins its canonical digest, and uses only that snapshot for the rest of the run. Editing the source policy can affect a later run but cannot reroute an active one. Policy refresh is periodic rather than per-task, defaults to no more than once every fourteen days, and may happen earlier only for an observed provider/catalog/price/quota incompatibility or an owner request. External research proposes a new artifact; it never mutates an active run. Local telemetry changes a default only after at least five comparable approved tasks, except for a concrete security or integrity failure. The comparison target is cost or quota per task approved by its real Check, including latency, retries, operational failures, intervention, and visual quality when applicable, not token price alone.

Default worker roles are research collector, documentation, implementation, review, verification, and integration. This is not a fixed team template: the coordinator creates only roles justified by ready work.

## Fresh coordinator and bounded planning

The repository-first intake runs before graph bootstrap. Direct, verified-single, and light-spec work stays in the invoking session. A normal `$impl <slug>` for an approved graph-mode change validates the spec, captures the pinned workspace, creates a transcript-free coordinator capsule, and opens a fresh visible top-level session when the host supports it. The old session stops after a verified handoff. A large spec alone does not justify graph mode, fan-out, or a strong coordinator profile.

The coordinator capsule contains IDs, paths, capability summary, user routing overrides, and an exact resume command. It does not contain the invoking conversation. The new coordinator claims a monotonically increasing generation before any mutation.

The coordinator first computes a bounded execution plan:

- ready tasks and path conflicts;
- role and risk classification;
- requested and fallback profiles;
- context references and budgets;
- expected resource owners;
- the smallest useful dispatch wave.

There is no fixed worker count. Host concurrency, available capacity, observed system pressure, path conflicts, and actual independent work determine fan-out.

### Cohesive execution sessions

The durable task graph is an evidence and dependency model, not a requirement to open one terminal per task. The scheduler groups consecutive ready tasks into one execution session when they belong to the same subsystem, share architectural decisions or Paths, form an essentially serial dependency chain, and would otherwise repeat most of the briefing. One writer owns a cohesive subsystem at a time. Parallel agents are limited to independent write packets or read-only research, inspection, and review.

Session reuse extends the existing driver lifecycle. It does not add another worker protocol. A new attempt may bind the exact already-owned terminal or native worker handle only when execution host, workspace, agent, model, effort, permission mode, owner, and process incarnation still match. Codex remains `--yolo`; Claude remains `--dangerously-skip-permissions`. Any profile drift, ownership mismatch, settled lease, context exhaustion, remote uncertainty, or missing capability forces a fresh routed session rather than implicit resume.

Provider task metadata is reconciled at the launch boundary, not treated as an independent scheduler. In Orca, the Harness may transition the exact external task to `ready` only after the journal proves the corresponding local task ready. If the provider rejects a start before returning any dispatch, terminal, process, or residual-resource identity, a public zero-residual receipt allows the same attempt to retry without inventing a pinned terminal. Missing or ambiguous post-condition evidence remains cleanup-blocked. This closes the observed r36 deadlock in which the provider task stayed `pending`, the start created no worker, abandonment assumed a possible resource, and recovery required a terminal that never existed.

The next capsule in a reused session contains only the current task and acceptance, relevant approved dependency summaries, diff since the previous Check, unresolved material finding references, allowed Paths, the validation command, and a bounded session memory. That memory contains decisions, invariants, central files, observed traps, green Checks, and carry-forward findings. Full state, transcripts, prior reports, and the complete spec are never resent. Every task still receives its own attempt, Check artifact, evidence, grade, and cleanup attribution.

The coordinator evaluates execution topology after each terminal task transition. It reduces to `single_writer` when only one write packet is ready, packets share decisions or files, integration costs more than the expected parallel gain, a worker continuously depends on its predecessor, audits create more work than concrete failures, or the full context would need to be repeated. Reduction blocks new dispatches, lets the current writer finish its group, settles unnecessary workers, and preserves pending tasks plus accepted evidence. It may expand again only after at least two independently useful packets have isolated write ownership and individual integration Checks. The reason and transition are journaled and projected in progress.

## Pinned control runtime

Bootstrap atomically copies the minimal Agent Graph control runtime, schemas, and driver modules into a run-owned immutable directory before creating the journal. It hashes the complete snapshot, stores its entrypoint in the capsule and state, and invokes that entrypoint for every later control command. Worker capsules continue to reference the project worktree, not the control snapshot.

This prevents a self-hosted Harness change from loading half-written modules or interpreting an old journal through a new schema. A takeover uses the same verified snapshot. Upgrading the control runtime starts a new run; it does not replace an active run's executable.

The implementation run for this change is the one bootstrap exception because the baseline does not yet know how to pin itself. Before its first dispatch, the fresh coordinator must create and verify a frozen copy of the baseline runtime and use its absolute entrypoint plus the project `--repo` for every graph command. Merely choosing a separate worktree does not solve this cutover.

## Checked task import

A source checkbox is not evidence. A new run rejects `[x]` tasks by default. An explicit checked-task import asks the current coordinator to execute each task's recorded check against the pinned workspace and append an import receipt, check evidence, and `task_graded(pass)` only on success. There is no path from `checked: true` directly to a passing grade.

### Audit rejection and retry

A valid worker report and a passing executable Check are the default acceptance evidence. Independent review runs after a cohesive package or a materially risky change, not automatically after each microtask. A finding is a bounded public record classified as `acceptance_violation`, `reproducible_regression`, `security_or_integrity`, `hardening`, or `advisory`. Only the first three are blocking. `hardening` becomes `carry_forward`; `advisory` remains non-material. A reviewer cannot expand the product contract by relabeling a preference as a rejection.

Before grading, the current coordinator may append `attempt_audit_rejected` only for a stored blocking finding that names the exact acceptance text or stable acceptance reference, affected file and identity, reproduction or verifiable reasoning, smallest repair hypothesis, and why the selected Check does not detect the violation. The coordinator filters the finding before rejection. The rejected attempt, its result, receipts, finding, and Check artifact remain immutable history. The transition removes the rejected attempt from the active-write set and returns the ungraded task to pending, but it does not settle resources itself. Independent cleanup transitions must reach done, verified, or explicitly retained before a repair attempt becomes dispatchable.

A failed executable Check also remains attempt evidence rather than forcing an immediate terminal task grade. Before grading, `record-repair` may append one fenced `attempt_check_rejected` event for the latest reported, ungraded attempt with its own failed Check and settled or explicitly retained cleanup. The event preserves the report and failed Check, records one bounded hypothesis, removes the attempt from active writes, and returns the task to pending for the single default repair attempt. The coordinator uses `task_graded(fail)` only when failure is intentionally terminal.

The default technical budget is one implementation attempt plus one repair attempt. A provider, terminal, or transport failure before any edit or Check is operational, not a technical hypothesis, but its authoritative post-condition must be observed and every resource that may exist must settle before another launch. After the repair attempt, no third attempt becomes ready automatically. One public coordinator decision must instead choose: amend acceptance or Paths, regroup the package, grade from the existing Check while carrying nonblocking findings, request human input, or block the task. External-effect retries first observe the authoritative post-condition and reuse an already-completed effect when its exact identity matches.

Every normal `check_recorded` event names the attempt it validates. The attempt retains that immutable check artifact; task-level check state is only a latest-attempt projection and retry counter. Grade and audit decisions resolve the latest reported attempt and its own check, so a successor can neither inherit an earlier pass nor overwrite rejected evidence.

Audit rejection is fenced by coordinator generation and workspace binding. It is valid only for the latest reported, ungraded attempt with its own recorded passing check. It cannot rewrite a worker result, relabel a passing check as failed, grade the task, claim cleanup was settled, exceed the repair-hypothesis cap, or dispatch the successor before cleanup reaches a verified or explicitly retained outcome. Replaying the same rejection ID is idempotent; different evidence under the same ID fails closed.

The budget boundary is a decision gate, not automatic `audit-exhausted`. It preserves the report, Check, tried hypothesis, classified findings, and cleanup references while preventing dispatch until the coordinator records one allowed decision. A repeated hypothesis is never a new attempt. Same decision ID and byte-equivalent payload replay idempotently; changed evidence fails closed. The bounded run projection exposes `input_required` or `blocked` only when the recorded decision warrants it.

### Malformed result quarantine

A malformed canonical result candidate is immutable evidence, but it is not a worker report. The public `quarantine-result` command reads the exact candidate bytes without normalizing them, verifies the current coordinator generation, run binding, task, attempt, canonical result path, and idempotency key, then atomically moves the bytes to a run-confined digest-addressed path. Its durable receipt records the original path, quarantine path, SHA-256, byte length, validation error code, task, attempt, coordinator generation, and journal revision. The journal and command response never contain the invalid body. A digest, not an attempt ID, names stored content; attempt receipts retain provenance when identical invalid bytes recur.

`record-result` uses that same fenced transition atomically when the canonical candidate fails serialization or schema validation. It preserves the exact bytes and consumes the attempt's result slot before returning a bounded quarantine receipt; it never leaves an invalid canonical file available for a worker or coordinator to overwrite between the validation error and a later command. The explicit `quarantine-result` command remains an idempotent recovery and inspection entry point for candidates discovered before ingestion. Both entries converge on one event and receipt identity.

The quarantine event does not grade, reject, repair, reconcile, release, abandon, or reinterpret the candidate. It only proves that the exact invalid bytes remain preserved outside the canonical result slot. Pending cleanup is a successful quarantine outcome with a bounded `cleanup_pending` reference, not a reason to append a later-invalid abandonment or return an error after mutation. A replay for the same attempt, key, and digest is idempotent; a changed candidate, path escape, stale generation, mismatched attempt, or conflicting receipt fails before mutation. Once the receipt is durable, public reconciliation and `abandon-attempt` ignore that quarantined candidate and use the canonical ownership helper to find every attempt-owned cleanup record, including cleanup registered separately from driver start. They may abandon only after those records are verified or explicitly retained. A pre-report serialization or schema failure is a transport failure, not an implementation hypothesis: it cannot consume the audit-repair hypothesis budget, increment an implementation-failure counter, or auto-grade the task blocked.

Quarantine also consumes that attempt's write-once result slot. The worker may not place a corrected canonical report into the same attempt after invalid bytes have been quarantined. Cleanup-gated abandonment and a fresh attempt ID are mandatory, so projection consumers never have to interpret a mixed quarantined-candidate plus accepted-report history for one attempt.

The Orca provider boundary follows the same protocol. `sync` first serializes the provider message into deterministic canonical WorkerResult candidate bytes and only then validates them. A malformed candidate is materialized once in the canonical result slot and returned as a bounded `quarantine_required` observation, not as an exception after an unrelated observation event. The provider delivery remains unacknowledged until the coordinator invokes `quarantine-result`; after that receipt is durable, `sync` acknowledges the exact delivery idempotently and never exposes or reconstructs its invalid body. Provider transport failure remains distinct from a technical implementation attempt.

## Context graph

Notes, files, decisions, dependency reports, and evidence are represented as `ContextRef` objects with origin, repository-relative snapshot path, content hash, revision, media type, title, and optional bounded excerpt.

A Maestro note remains editable inside Orca, but it never enters a capsule inline. When a `context_for` link or delegation pins a note revision, Orca creates a bounded immutable context snapshot under its authenticated document transaction. The coordinator fetches that exact revision through the actor-authenticated bridge, verifies its hash, and materializes Markdown under `openspec/runs/<change>/<run-id>/artifacts/maestro-notes/<note-id>/<revision>.md`. The resulting repository-relative artifact becomes the `ContextRef`. Orca retains referenced revisions until the owning run releases them. A missing, changed, unauthorized, or expired revision blocks composition.

An attempt receives an immutable context capsule built by deterministic traversal of typed edges. Traversal is cycle-safe and stops at both item and byte/token budgets. Priority is:

1. task contract and acceptance;
2. direct user instructions and selected note links;
3. dependency digests and decisions;
4. scoped source files and evidence references;
5. optional lower-priority background.

Terminal transcripts and full worker reports never enter automatically. Capsules include artifact references and short digests. A note edited after dispatch receives a new revision and affects only later attempts.

The bridge understands these semantic edges:

- `depends_on` between tasks;
- `context_for` from notes or evidence to tasks and attempts;
- `spawned_by` from a parent attempt to a requested child;
- `executes` from an attempt to its terminal receipt;
- `reports_to` from an attempt to its owning task or parent attempt;
- `produces` from an attempt to evidence;
- `portals_to` from the orchestration home to another workspace Canvas.

## Dynamic delegation

A user or worker may propose a child task. The proposal becomes `delegation_requested` and includes parent attempt, purpose, role, requested profile, context references, path subset, check, and `PlacementRequest`.

Only the active coordinator generation can transition it through:

- `delegation_approved` or `delegation_rejected`;
- `delegation_started` after a driver receipt exists;
- `delegation_reported` after a schema-valid child result;
- `delegation_released` after verified cleanup.

The coordinator may narrow paths, context, effort, or capabilities. It cannot approve a child with paths outside the parent task unless it first records an explicit task-graph amendment owned by the coordinator. A child never grades its parent, mutates the journal directly, or recursively launches an untracked process.

A loose user-created terminal remains an Orca terminal. It becomes a tracked graph attempt only after a task and delegation intent anchor it. This keeps ad hoc exploration useful without inventing ownership.

### Attempt-bound graph amendments and results

A graph amendment names one active parent attempt, its task, the current coordinator generation, normalized Paths, and a reason. It does not mutate the frozen task contract. The reducer derives that attempt's effective Paths as the union of the frozen Paths and its amendments. The immutable worker capsule carries that union, the ordered amendment IDs, and their digest. Delegation approval and the parent worker result use the same effective set. Another attempt, task, or coordinator generation cannot inherit it. Dispatch fails before launch if the capsule cannot encode the effective scope. The report event records the same amendment IDs and digest used for validation, so replay cannot reinterpret an old result through later scope.

`record-result --result` validates the explicitly supplied candidate before Host write-once recovery. If the canonical slot is empty, Host stores that validated object. If the slot already contains the same semantic result, the command recovers idempotently. If it contains different bytes or meaning, the command returns both bounded digests and fails closed. It never ignores the supplied path and substitutes the canonical candidate. Malformed canonical bytes use the public quarantine flow. A valid result that still exceeds its effective Paths remains immutable rejected evidence; the coordinator must add a valid attempt-bound amendment before the report or reject the attempt and retry. It cannot rewrite or adjudicate the candidate in place.

WorkerResult transport and task evidence remain separate. Every accepted result uses `outcome: reported`; a worker cannot write a grade or terminal task status. A result with changed files names at least one real worker check. A no-change audit may keep both `files_changed` and `checks_run` empty while carrying confined evidence, questions, and a bounded blocker summary. That report records what the worker found, but it cannot satisfy the task Check or authorize a pass. Schema validation, the imperative validator, Host sync, resume, and quarantine enforce the same closed shape.

## Compact control plane

Canonical state remains an append-only journal plus a reconstructable projection. The writer uses an operating-system-aware interprocess lock and expected revision. Process-local locks are insufficient when the CLI, coordinator, and Canvas bridge operate concurrently.

Mutation commands return a compact receipt containing mutation ID, event IDs, new revision, affected entity IDs, and warnings. Full state is available only through an explicit bounded query.

`status --watch` emits newline-delimited JSON as revisions arrive. It does not accumulate snapshots, terminal output, or reports in memory. Slow consumers resume from a cursor; a compact reset tells them to request a fresh view when retained deltas no longer cover that cursor.

Every graph revision also derives one `RunProgressSummary v1`. The summary is a pure projection of the canonical journal, attempt-bound checks, coordinator grades, unresolved questions, material findings, and cleanup outcomes. It never consults a spinner, terminal title, prompt shape, TUI readiness, process CPU use, or an apparently idle process.

The summary declares `schema_version: 1` and contains mutually exclusive task counts for `approved`, `running`, `input_required`, `blocked`, `pending`, and `failed`; at most three current and three next task references; bounded `pending`, `unverifiable`, `failed`, and `retained` cleanup counts and IDs; the last canonical activity sequence, time, and event type; and at most five blocker and five material-finding references. Each reference carries exact task, attempt, finding, or cleanup identity so a client can request the authoritative detail without receiving it inline. Transcripts, reports, prompts, terminal tails, file bodies, and continuously generated prose are excluded.

One bounded `coordination` block is derived from journal timestamps, immutable Check artifacts, dispatch and cleanup events, classified findings, and optional driver usage receipts. It reports implementation wall time, Check wall time, coordinator wait-for-worker wall time, audit wall time, dispatch count, operational provider or terminal start failure count, technical attempt count, approved task count, blocking finding count, carry-forward finding count, and input/output/cache token observations when the provider supplies them. Missing usage is `unavailable`, never zero. The durations may overlap and are explicitly diagnostic rather than additive or a score. The block also carries the current `single_writer|parallel` execution mode and its latest bounded reduction or expansion reason.

The run state vocabulary is `active`, `input_required`, `blocked`, `partial`, `complete`, `failed`, and `outcome_unknown`. The reducer applies one deterministic precedence: a clean terminal pass that satisfies every completion gate is `complete`; a terminal failed outcome is `failed`; a terminal partial outcome or otherwise settled work with carry-forward findings is `partial`; explicit canonical uncertainty that prevents adjudication is `outcome_unknown`; an unresolved material blocker that stops progress is `blocked`; unresolved required input is `input_required`; all other runnable, pending, or executing work is `active`. `complete` and a displayed 100 percent require every required task approved, no blocked or failed task, no unresolved input, no unresolved owned cleanup, and no material or `carry_forward` finding. Terminal silence cannot create any state. If a client renders a percentage before the complete predicate holds, it remains below 100 even when the approved-task numerator equals the task total.

`AgentGraphView v1` carries the complete bounded summary. `status --watch` emits it or its versioned delta in each relevant NDJSON frame with revision and cursor. Mutation responses may include the same bounded summary. The graph runtime publishes these projections as part of normal `impl`, research, and other coordinator events, so no coordinator must answer a progress prompt or write narrative status. The same CLI stream works without Orca.

`AgentGraphView v1` is a bounded derived projection containing:

- workspace and run identity;
- coordinator and capability summary;
- task, attempt, note-reference, terminal-receipt, evidence, cleanup, and portal nodes;
- typed edges;
- compact status, profile, resource, and blocker fields;
- one bounded `RunProgressSummary v1` with exact detail references;
- revision and cursor.

It excludes transcripts, full file bodies, prompts, and unbounded reports. Versioned JSON fixtures are the cross-repository conformance contract.

## Driver behavior

### Orca

The Orca driver resolves capabilities before each attempt profile. It removes the fixed Codex choice and passes requested agent, model, effort, and placement through `worker-start` or the existing tracked-terminal fallback. The returned receipt stores what Orca actually resolved.

Current-workspace placement requires an exact pinned workspace match. Existing-workspace placement resolves the requested host and workspace key. Child-worktree placement asks Orca to create under the exact parent and records the stable child key. A target that cannot be resolved or created fails before dispatch; it never degrades to the current checkout or another host.

On resume, reconciliation uses stored host, workspace, terminal, incarnation, and external Run/Task/Dispatch references. Explicit Orca mode does not switch to host mode silently.

Public dispatch passes the reserved `workspace_scope` and `execution_profile` to the driver. Public recovery, resume, probe, and cleanup also pass the persisted resolved placement and pinned external references. A fresh CLI process resolves the exact saved host/workspace through the driver's authoritative `show` operation. It never substitutes `current`, reroutes the attempt, or compares cleanup ownership with an ambient workspace.

### Host without Orca

The host adapter writes the same capsule and requested profile. A native host integration may return a worker handle and resolved profile. Otherwise it provides the exact manual invocation or executes one bounded task locally. It does not shell out to guessed agent CLIs.

The graph still enforces coordinator generation, path scope, result schema, evidence grading, and cleanup. Capabilities absent from the host produce a visible fallback or a blocked attempt, never fabricated support.

## Browser surfaces and visual-validation evidence

A task or coordinator may request a `BrowserSurface` from the selected driver. The request pins task, attempt, execution host, workspace key, initial URL or artifact route, viewport, `visible|offscreen` mode, retention, and an idempotency key. The response is a versioned receipt, not a guessed process handle. It records requested versus observed mode, exact browser page binding when available, focus and paint observation, capture artifact reference and hash, and release authority.

The Orca driver consumes the composed browser-surface operation advertised through its managed CLI context. It does not race unrelated `tab create`, focus, screenshot, and close commands. A `visible` request succeeds only when Orca proves that the exact native Browser page became paintable in the pinned workspace. An offscreen result cannot satisfy it. The Host driver may use an explicitly supplied host-native capability; otherwise it returns `unsupported` or `unobserved` without guessing Chrome, Chromium, Playwright, or a desktop session. Browser support is therefore additive and normal non-visual Harness work remains portable without Orca.

`AgentGraphView` projects a bounded `browser-surface` node plus links to its task, attempt, and evidence. It may include title, sanitized origin, viewport, lifecycle, requested/observed mode, retention, and artifact reference. Screenshot bytes, cookies, storage, authorization data, complete DOM, accessibility trees, and live frame streams never enter the journal projection, capsule, mutation response, or coordinator context.

Visual evidence remains evidence-graded. A receipt that opened or captured a page is not itself a pass. The coordinator verifies the artifact hash, declared route/component, state, theme, dimensions, source revision, capture mode, vision-review record, and task `Visual` contract before grading. When a `Visual-Scope` or user request requires a visible browser and the driver cannot prove it, evidence is `unobserved` or the task blocks; the scheduler never silently substitutes headless output. Explicit offscreen validation remains available where the task permits it.

Browser lifecycle follows attempt ownership. Deselecting a Canvas node is presentation-only. A Harness-owned page may release only after evidence is durable, the attempt is settled, retention is false, and the driver verifies the exact binding closed. Retained, user-owned, mismatched, remote-disconnected, or unverifiable pages are never closed. Cleanup and learning retain bounded receipts and artifact references, not browser contents.

## Checks and lifecycle

Check execution has an explicit timeout, bounded stdout/stderr artifact, and an owned process group or platform-equivalent job. Cancellation terminates the complete child tree and records what could not be verified.

Every public Check also has a durable single-flight identity derived from normalized direct argv and the exact workspace source snapshot. The snapshot includes the saved workspace binding, base revision, tracked diff bytes, and untracked source bytes, while excluding only artifacts owned by the current run. Journal or receipt growth therefore cannot invalidate reuse, but any tracked or untracked source mutation does. The first caller owns the process and cleanup; concurrent callers join its durable lease and consume the same immutable bounded artifact. Completed evidence may be shared by multiple task attempts or checked imports only when both identities match, while each consumer keeps its own event binding. Caller output timeout, terminal idleness, or a quiet process never authorizes a second subprocess. Crash recovery verifies the exact owned process tree and cleanup before transferring or retrying the lease.

Public source validation and bootstrap share one canonical parser and semantic validator for `process-decision.json`. Run-specific bootstrap checks may be stricter about runtime state and workspace effects, but bootstrap cannot reject a source field, enum, amendment, packet, or budget that public `validate` just accepted. Source rejection always happens before run artifacts exist and reports the same stable field path and error code through both commands.

The optional `agent-resource-guard` remains a Linux enhancement for unusually high fan-out or overlapping heavy commands. Normal runs do not require it. The runtime records observed capacity and guard admission when available but retains portable behavior on macOS and Windows.

Cleanup has requested, in-progress, verified, unverifiable, and failed outcomes. A declared provider receipt is evidence of a request, not proof that the process tree or workspace is gone. A run completes only when required evidence is graded and all owned cleanup is verified or explicitly retained by the user.

Public cleanup registration validates the same discriminated target that its finisher consumes. A process cleanup stores one numeric PID plus structured external identity fields; descriptive concatenations fail before `cleanup_registered`. Terminal cleanup accepts a typed owner envelope with attempt or coordinator identity, execution host, workspace, handle, incarnation, and optional process root. The CLI never degrades that envelope to a string. A record accepted by `cleanup-register` must always have an append-only path to `verified`, `retained`, `unverifiable`, or `failed`; it cannot become permanently unfinishable because registration and finish disagree about shape. Legacy malformed records remain immutable and can be explicitly retained with a replacement verification reference.

Learning normalizes cleanup evidence by its typed origin. A canonical cleanup receipt without an artifact path projects null artifact metadata instead of failing. A pathless `unverifiable` receipt may contain only a bounded reason and omit `kind`; if it supplies a kind, that kind must match the cleanup record. Verified typed cleanup requires its exact kind. When a confined receipt path exists, learning derives its hash and byte length and verifies any supplied metadata. Routing, delegation, and other signed artifact receipts retain their stricter required metadata. Normalization never upgrades `unverifiable` cleanup to verified.

Completion evaluates only run-owned change provenance. The bootstrap `workspace_scope.dirty_paths` snapshot is the lower boundary: a pre-existing tracked or untracked path cannot become this run's frontend output merely because it is still dirty at completion. The coordinator then intersects post-bootstrap changes with concrete task/attempt `files_changed` and declared Paths before enforcing `Visual` contracts. A new changed path that no attempt owns is a provenance error, not silently ignored evidence. This prevents an unrelated pre-existing mock or local experiment from making an otherwise complete run impossible to finish, while still failing closed when the run produces unclaimed frontend work.

## Harness integration

`spec` emits execution hints, context references, and worktree isolation only when they add concrete value. It validates but never materializes a worker.

`impl` runs adaptive intake first. Direct, verified-single, and light-spec work does not create a durable agent graph. An approved graph-mode change bootstraps a fresh proportionally routed coordinator, which defaults to one writer, forms cohesive sessions, dispatches only independently useful work, reviews package-level risk, runs task-level Checks, grades evidence, and releases owned resources. When a frontend task declares `Visual` expectations and the selected driver advertises browser surfaces, the coordinator requests the declared visible or offscreen mode, links the resulting artifact and vision review, and preserves exact page lifecycle. Lack of that capability is reported honestly and does not cause the Host driver to invent a browser.

`impl`, research, and other graph-backed coordinators publish progress by advancing canonical events. The runtime updates `RunProgressSummary v1` automatically in `AgentGraphView` and NDJSON watch frames. Skills may render or link that summary, but they never manufacture a separate progress truth or ask a model to narrate it continuously.

Research may create read-only collectors for independent source retrieval. The primary researcher remains responsible for source adjudication, disagreements, and the final finding. Collector results enter as cited artifacts and bounded context references, not transcripts.

The learning snapshot records routing decisions, fallbacks, evidence outcomes, and lifecycle receipts. It does not retain raw prompts or terminal output.

## Cross-repository handshake

This change publishes one `maestro-protocol-v1` conformance fixture set covering `AgentGraphView v1`, its bounded adaptive-execution and coordination-progress fields, `MaestroMutation v1`, `DelegationIntent v1`, `BrowserSurfaceRequest v1`, `BrowserSurfaceReceipt v1`, actor envelopes, placement, note snapshots, deltas, and expected failures. Orca freezes the same fixtures with a source digest and runs them in its own contract tests. Orca advertises supported protocol versions and consumes the newest mutual version. Unknown optional fields are ignored; incompatible major versions produce an explicit unavailable state.

## Authoritative compatibility export

Protocol fixtures prove shape compatibility, but they do not prove that a concrete Harness run implemented and passed the capabilities Orca is about to consume. A separate public exporter reads one completed `pass` run and emits a canonical Maestro compatibility bundle. It never accepts an `authoritative: true` assertion from its caller. Authority comes from the immutable run itself: exact journal and state digests, pinned control-runtime digest, workspace binding, zero unresolved cleanup, and pass grades with their real Check or checked-import evidence for MLK-05, MLK-05R, MLK-06R, MLK-06D, MLK-06Q, MLK-06QR, MLK-15, MLK-07, MLK-07P, and MLK-19. The graph/progress capability receipt binds MLK-19 together with MLK-07 and MLK-07P so a consumer never infers adaptive scheduling or overhead telemetry from a locally modified fixture.

Check authority has multiple published artifact shapes. A legacy ordinary artifact need not duplicate `status: passed`; the exact `check_recorded` event and byte-identical task projection own that status. Its artifact must still match the projected command, task, attempt, zero exit, and non-timeout outcome. A present status must be `passed`. A legacy checked-import artifact may duplicate its published pass fields. A current shared `CheckExecution v1` artifact instead carries `execution_id`, `command_digest`, `source_snapshot_digest`, exit, timeout, and bounded output. For that shape the exporter resolves exactly one byte-identical `state.check_executions` entry by artifact ref and checked-import consumer ref, requires `lifecycle: passed`, verifies the artifact fields against that projection, and relies on canonical journal replay for the raw command/task/import binding. It never requires absent legacy fields, manufactures them, or trusts a caller label to select the shape. Export tests use real completed public-CLI runs for both the ordinary and shared-execution paths rather than cloning checked-import evidence into a synthetic task.

Cleanup lifecycle state and cleanup receipt observations also have distinct schemas. The exporter replays the reducer contract over each exact registration and finish event, then compares the projected receipt with the journal receipt. Typed cleanup projects `verified`. A preserved legacy string-owned cleanup projects terminal lifecycle state `done` even when its receipt records the exact observation `status: verified`; this is settled evidence, not a reason to rewrite history or reject the producer. Pending, retained, failed, unverifiable, missing, duplicate, or reducer-inconsistent cleanup remains ineligible.

The bundle contains one receipt per required capability and one manifest that names the exact receipt byte digests. The directory is addressed by the canonical manifest digest. Export is deterministic for unchanged evidence and fail-closed for partial runs, missing evidence, identity disagreement, tampering, symlinks, traversal, or a colliding non-identical output. An explicit output directory may be an independent consumer repository; this is a byte-preserving export, not a shared multi-repository journal. Orca must validate and pin those producer bytes before its runtime-integrated tasks become ready.

The final Orca integration probe runs both repositories in their own worktrees and links them by run and workspace IDs. It is external evidence, not a single cross-repository journal.

## Follow-up gaps observed during fresh runs

The `maestro-harness-20260822T134605Z` run exposed five contract gaps. These observations belong to the OpenSpec source and do not mutate that run's frozen task graph.

- Deduplicate identical Checks by command digest and workspace snapshot. A retry may reuse one completed Check only when both identities match.
- Record mutation provenance during `import-checked-task`. The import receipt must identify the workspace mutations covered by the imported evidence.
- MLK-16 aligns the published `WorkerResult` schema with its canonical validator. A no-change audit can report exact evidence without a ceremonial Check, while a changed-file result still names a real worker check and neither form can grade its task.
- Distinguish transport attempts from work-bearing attempts. A dispatch that never receives a capsule or prompt must not consume the same retry budget as an attempt that performs useful work.
- Let delegation cleanup reflect the resource a portable Host can actually observe. A verified process tree must support honest child release without fabricating a verified terminal, while observed Orca terminals retain exact handle and incarnation checks.
- Run `maestro-harness-20260822T193956Z` proved that event serialization alone does not prevent duplicate Check subprocesses. MLK-12 turns the earlier Check-deduplication design into an executable public contract with cross-process join, completed-result reuse, source invalidation, and cleanup-gated recovery.
- Run `maestro-harness-20260822T204300Z` reproduced the same defect while importing MLK-04: a false absence observation launched a second PGID before the original completed. Only the newer duplicate was terminated, and the original produced the sole durable import. This confirms process observation by a coordinator is not a substitute for the MLK-12 lease.
- Orca run `maestro-worktree-canvas-20260822T202019Z` proved that a consumer can build a self-consistent verifier and still fabricate every claimed Harness receipt. MLK-13 adds the missing producer boundary; the rejected Orca attempt remains blocked evidence and is never promoted by replacing labels in place.
- Orca run `maestro-worktree-canvas-20260822T215848Z` proved the WorkerResult parity gap three ways: attempt 003 carried an invalid evidence scheme and was quarantined, attempt 004 was a valid no-change blocker audit rejected only for empty `checks_run`, and attempt 005 needed a ceremonial source validation plus shape repairs before acceptance. MLK-16 turns that sequence into one executable public contract for a fresh run.
- Orca run `maestro-worktree-canvas-20260823T071651Z` exposed a remaining quarantine race: `record-result` rejected malformed `checks_run`, then the coordinator asked the worker to correct the same canonical path before calling `quarantine-result`, losing the original bytes. MLK-15 therefore makes invalid-result ingestion quarantine atomically; coordinator ordering is no longer the only protection.
- Completed Harness run `maestro-harness-20260823T072820Z` proved that MLK-13's original ordinary-grade test was not ordinary: it copied checked-import evidence and therefore required a duplicate status field absent from real `run-check` artifacts. The failed export remains evidence; a fresh run must repair and prove the exact public artifact boundary before any Orca gate is updated.
- Fresh Harness run `maestro-harness-20260823T093217Z` proved that MLK-14's required process decision invalidated the shipped portable graph example used by MLK-08. The checked import preserved `check-2e2dcc8b5d0996d7d0bbfff2`, the run closed `partial` with verified cleanup, and the source repair adds a real graph-mode decision to that eight-task example. Validation remains fail-closed; neither the failed artifact nor the frozen run is rewritten.
- Fresh Harness run `maestro-harness-20260823T095018Z` proved that result-slot quarantine remained globally blocking after its attempt had been cleanup-gated and abandoned. MLK-09 artifact `check-720c5198d27c287773c90013` failed because `resume` scanned historical `attempt-root-01-001` instead of reconciling only active attempts. MLK-15 now distinguishes an active quarantined slot, which remains fail-closed, from an abandoned historical slot, whose immutable receipt survives without blocking a fresh successor. MLK-09 depends on the repaired MLK-15 Check before its checked import may run again.
- Fresh Harness run `maestro-harness-20260823T100831Z` proved the dependency must also fence MLK-09R. Its combined lifecycle/E2E import created immutable failed Check execution `check-a4a71b8e940d9ae541bc8b63` before MLK-15 was schedulable, even though the failure was exactly MLK-15's abandoned-quarantine resume case. The run closed `partial` at revision 84 with 20 pass tasks, 11 pending tasks, and all 12 cleanup records verified. MLK-09R therefore depends on MLK-15 in the source graph; coordinator ordering text is not a substitute for an executable dependency.
- Fresh Harness run `maestro-harness-20260823T104034Z` exposed the inverse coupling inside MLK-16's checked import. MLK-16 is a predecessor of MLK-15, but its combined Check also executed `test_end_to_end.py`, including MLK-15's abandoned-quarantine resume regression. Check execution `check-c91a067026dcc92d9319fc87` therefore failed before MLK-15 could legally run. The frozen run closed `partial` at revision 68 with 25 pass tasks, 6 pending tasks, and all five coordinator cleanups verified. MLK-16 now uses focused graph-core, public-CLI, and quarantine parity suites; MLK-15 alone owns the downstream E2E resume regression.
- Fresh Harness run `maestro-harness-20260823T110556Z` proved MLK-16's focused import, then exposed an incomplete MLK-15 implementation hypothesis. Attempt `attempt-mlk-15-001` aligned the inner Host reconciliation branch but left an earlier Host loop in both `resume` and `sync` scanning every quarantined attempt. The declared Check failed because abandoned `attempt-root-01-001` still returned `result_slot_quarantined`. The worker was stopped without retry or WorkerResult, all five worker and five coordinator resources were verified absent, and the frozen run closed `partial` at revision 84. The repair now requires one shared active-attempt predicate at every Host quarantine gate, including the pre-driver scan and later recovery loop.
- Fresh Harness run `maestro-harness-20260823T113841Z` proved that the partial MLK-15 source cannot be hidden behind task ordering. MLK-04's public-CLI import failed `test_sync_replays_a_quarantined_malformed_candidate_after_a_crash`, the candidate-evidence collision and disappearing-evidence cases, and unowned-terminal cleanup rejection because generic quarantine gating ran before the more specific replay and integrity branches. The frozen run stopped without a worker at revision 27, with five pass imports and zero unresolved cleanup. MLK-15's selected Check now includes `test_agent_graph_cli.py`; a localized source repair must restore predecessor safety before the next fresh graph imports any checked task.
- The first revision-22 localized repair in visible terminal `term_5f904612-81d8-4690-8229-8bd3d20cbbc4` centralized active quarantine but made the optional legacy evidence directory mandatory and appended a replay rejection without adopting the returned projection. Its single 56-test Check therefore ended with four failures and three errors after 271.273 seconds. The second hypothesis must treat unreferenced legacy evidence as absent, keep referenced evidence fail-closed, update projection after every append, and leave ordinary non-quarantine abandon/sync/delegation untouched. The worker terminal, PTY, Codex, code-mode host, Check process, and observed descendants were all absent before retry authority was considered.
- The revision-24 final bounded worker fixed optional lookup and reduced the same 56-test Check to three errors, but exposed a journal-owner boundary. `command_quarantine_result` creates a separate `EventJournal`, appends `attempt_result_quarantined`, and returns a revision-10 projection; assigning that object does not update the caller's original journal fence from revision 9. The helper must refresh or reuse one journal authority before any rejection or abandonment append. It must also copy the first invalid bytes into the established legacy evidence path before moving the canonical file to content-addressed quarantine, so missing and collision integrity tests still have the exact referenced evidence. The worker's terminal and every observed process descendant were absent after the failed Check.
- The coordinator integration correction materialized the legacy bytes before canonical relocation and called verified replay on the caller-owned journal after the nested public quarantine command. That preserves one exact evidence body in both the compatibility path and the content-addressed receipt while advancing the original journal fence before rejection or abandonment. The complete MLK-15 Check then passed all 56 tests in 155.922 seconds. The next fresh graph may import MLK-15 as checked; it still cannot infer the MLK-13 compatibility bundle until that task runs against a completed pass run.
- Completed pass run `maestro-harness-20260823T121943Z` passed all 31 frozen tasks and settled all 23 cleanup records. Its real public export then rejected legacy terminal-incarnation cleanup because the state correctly projected `done` while the preserved finish receipt recorded `verified`. MLK-13 now verifies cleanup through the reducer's discriminated transition instead of equating unrelated status enums. The completed journal, state, and graph remain frozen; this source repair requires another fresh Harness run before the Orca bundle can be updated.
- Fresh repair run `maestro-harness-20260823T131416Z` passed MLK-13's fixture suite but the mandatory live export against `maestro-harness-20260823T121943Z` failed at MLK-05 before cleanup replay. MLK-12 had replaced the legacy checked-import artifact with a shared `CheckExecution v1` artifact, while MLK-13 still required legacy duplicate fields. The run closed `partial` at revision 94 with all tasks approved and all ten cleanup records verified. Revision 28 reopens only MLK-13 to bind the shared execution projection and immutable bytes without weakening journal authority.
- Fresh run `maestro-harness-20260823T140739Z-r28` proved that MLK-12's source contract was broader than its implementation. The public checked import started MLK-15 before pending predecessor MLK-16, then cached a 300-second timeout as the terminal result for that command and source snapshot even though process residue was unverified. There was no public import timeout option, exact process identity persisted for recovery, or audited transition that could retire the failed lease and authorize another policy. The owner preserved the failed artifact, imported MLK-16 only, verified all coordinator cleanup, and closed `partial`. Revision 29 reopens MLK-12. It makes readiness a command boundary, binds timeout and output cap to the execution policy, and allows a new execution only after the old timed-out tree has an exact verified cleanup receipt.
- Fresh run `maestro-harness-20260823T144151Z-r29` proved that a filesystem lease alone is not a durable control-plane lifecycle. Its sole worker added policy identity and a recovery command, and the focused Check passed, but independent audit rejected the attempt. A blocked execution could become `failed_verified` only in the side record while the journal stayed blocked; recovery checked the root PID but not a surviving saved process group; no public running event or owner-bound cleanup existed before the wait; and only two acceptance branches were tested. Revision 30 requires one append-only running registration, one fenced recovery transition, full process-authority absence proof, and the minimal public-CLI regression matrix before MLK-12 can pass.
- Fresh run `maestro-harness-20260823T151343Z-r30` could not import its first predecessor because the new Check producer wrote policy fields that the checked-import evidence parser still rejected as unknown. This is a control-runtime bootstrap boundary, not authorization to bypass task readiness. Revision 31 aligns that parser and its numeric/digest validation with the emitted `CheckExecution v1` artifact and proves bootstrap followed by checked import before opening another MLK-12 graph attempt.
- Fresh run `maestro-harness-20260823T152728Z-r31` proved the policy-evidence parser and imported nine checked predecessors, then failed the MLK-06 lifecycle suite because a timeout-blocked execution raised its recovery error before appending the attempt-bound task Check projection. Revision 32 requires `run-check` to persist that failed, timed-out Check exactly once before preserving the same fail-closed recovery error, keeps the shared execution artifact compact, and runs both the single-flight suite and the lifecycle regression before another graph bootstrap.

## Decisions

- The event journal, not the Canvas, is canonical.
- A normal implementation always starts a fresh visible coordinator.
- The coordinator route comes from the pinned external policy; all fallback and escalation are explicit.
- Workers use the cheapest compatible profile and only the smallest useful fan-out.
- Every run pins one external routing-policy digest; changing providers or concrete models does not patch scheduler code or rewrite an active run.
- Attempt profiles and workspace placement are durable state.
- Every run executes through one immutable verified control runtime.
- A checked source box never implies an evidence grade.
- Notes provide versioned bounded context, never automatic transcripts.
- Browser surfaces are exact driver-owned resources; visible and offscreen observations are never interchangeable.
- Dynamic delegation is an intent approved by one fenced coordinator.
- WorkerResult reports work but never grades it; a no-change audit does not fabricate a Check.
- Mutation responses and watches are compact and incremental.
- Run progress is journal-derived, bounded, versioned, and published automatically on Orca and portable CLI paths.
- Orca and non-Orca execution share semantics but report different capabilities honestly.
- The Orca UI and lifecycle implementation remain a separate spec and run.

## Rejected alternatives

- One coordinator inside the already-full invoking conversation: keeps the context bottleneck.
- Let the Canvas call terminal or worker APIs directly: bypasses graph policy and ownership.
- One xterm instance per visible card: scales memory and rendering work with agent count.
- Hardcode current model names in task contracts: couples durable plans to a changing provider catalog.
- Copy child graphs into the parent Canvas: mixes workspace ownership and creates unbounded documents.
- Permit recursive native subagent spawning: loses fencing, evidence, and cleanup identity.
- Make the current graph multi-repository during this change: expands every path, check, driver, and journal invariant without being needed for the Maestro integration.

## Assumptions

- `my-llm-kit` remains an MVP without external state consumers that require the old projection shape.
- Runtime adapters can advertise supported agent, model, effort, placement, and streaming capabilities.
- Concrete cost tables may change; capability lanes and persisted resolved profiles are sufficient for deterministic routing.
