# Maestro harness orchestration

## Why

The portable Agent Graph established durable tasks, attempts, evidence, and a fresh-coordinator handoff, but it still exposes too much runtime state to the coordinator and does not provide the contracts required by a visual orchestration surface.

The current implementation also has concrete gaps:

- `Isolation: worktree` is parsed but the Orca driver still dispatches in its current worktree;
- agent, model, and reasoning effort are not durable per-attempt choices;
- a schema-valid reported result has no coordinator-owned audit rejection transition, so a passing command check can leave a task permanently non-retryable even when acceptance review finds a blocker;
- the Orca driver fixes the agent to Codex instead of resolving runtime capabilities;
- `status --watch` retains snapshots instead of emitting a bounded stream;
- mutations return full state, including context and reports, back into the coordinator session;
- the journal lock is process-local;
- checks and cleanup do not yet prove bounded output or full process-tree termination;
- public cleanup registration accepts descriptive process targets that its own finisher rejects and exposes only a string owner even when terminal verification requires typed ownership;
- checked task contracts can reappear as pending;
- a resumed Orca run can bind to a different current worktree;
- attempt reservation does not yet require the event workspace scope to equal the run pin;
- cleanup and recovery can resolve the ambient Orca workspace instead of the attempt's selected placement;
- public dispatch, recovery, and probe paths do not yet pass the complete persisted driver context;
- learning rejects valid cleanup receipt shapes that omit artifact metadata by contract, including pathless `unverifiable` receipts that correctly omit a kind;
- malformed-result quarantine is not yet a public command boundary: the real run reached it only through `sync`, stored evidence by attempt rather than digest, appended the rejection, and then returned an error because separately registered attempt cleanup was not discovered;
- a parent graph amendment can authorize wider work but the worker capsule omits the amended Paths, while `record-result` still validates only the frozen Paths and Host mode may silently substitute the canonical candidate for an explicitly supplied result;
- the repair-hypothesis cap can strand a latest `reported` attempt: audit rejection refuses both the repeated hypothesis and a third hypothesis, while abandon refuses reported attempts, leaving no public terminal transition even after cleanup is settled;
- the documented failed-check loop grades the task `fail` before `record-repair`, while the runtime rejects every repair after a terminal grade, so one ordinary check failure can permanently block the graph;
- the bounded graph projection has no canonical run-progress summary, so users still need to ask a coordinator what is happening;
- the public WorkerResult schema permits a no-change audit with no worker check, while the imperative validator rejects it and forces coordinators to invent ceremonial validation before recording a blocker.
- cohesive tasks are still dispatched as separate worker sessions, so terminals, full briefings, and audit cycles are recreated even when one writer must make the decisions serially;
- audit findings have no required blocking classification or contract citation, which lets a reviewer expand acceptance after a deterministic Check is green;
- the frozen graph can reduce only by cancelling ungraded work, rather than temporarily collapsing dispatch to one writer and later growing again;
- progress records product state but not bounded coordination overhead, so repeated dispatches, retries, audits, terminal failures, and waiting time are invisible.

Large implementations therefore still spend coordinator context on mechanics, and a Canvas would amplify the lifecycle bugs unless the Harness first exposes a compact, fenced control plane.

## Change

Evolve `agent-graph` into the portable orchestration control plane consumed by both the existing command-line workflow and Orca's native Maestro Canvas.

The change will:

- pin repository, execution host, folder/worktree, revision, run, coordinator generation, and attempt ownership;
- preserve every reported result immutably while allowing the current coordinator to reject it with structured audit evidence, settle its resources, and open a new attempt without fabricating a failed command check;
- pin an immutable control-runtime entrypoint and hash for the lifetime of each run, so a Harness implementation cannot change the coordinator beneath itself;
- make role, agent, model, reasoning effort, workspace placement, and fallback reason explicit per attempt;
- run the repository-first mode selector before starting graph orchestration, then open a fresh coordinator only for an approved graph-mode change and route its model and effort proportionally to observed risk;
- assign workers to the cheapest compatible capability lane from role, risk, task effort, and user overrides;
- generate bounded, immutable context capsules from versioned references instead of terminal or conversation transcripts;
- group serially dependent tasks from one subsystem into a reusable single-writer session while retaining separate task IDs, Checks, evidence, and grades;
- advance a reused session with only the next task contract, relevant approved dependencies, diff since the prior Check, live material findings, allowed Paths, validation command, and bounded session memory;
- accept dynamic delegation requests while preserving a single coordinator writer and path-scope constraints;
- bind graph amendments to an exact active attempt, carry their effective Paths and digest in the worker capsule, validate the result against that same scope, and make Host result-candidate conflicts explicit without rewriting evidence;
- classify every finding as `acceptance_violation`, `reproducible_regression`, `security_or_integrity`, `hardening`, or `advisory`; only the first three can reject an otherwise valid attempt;
- default to one implementation attempt and one repair attempt, then require an explicit coordinator decision before any third technical attempt;
- make dispatch reduction reversible: stop new dispatches, let the current writer finish its cohesive session, settle unnecessary workers, preserve pending tasks and accepted evidence, and re-expand only when independent packets are proven;
- make failed-check repair an explicit pre-grade transition and reserve terminal `fail` grading for an exhausted or intentionally final outcome;
- expose a versioned `AgentGraphView v1` projection and idempotent Maestro intent bridge;
- derive a bounded, versioned `RunProgressSummary v1` from journal events, grades, findings, and cleanup and publish it automatically through `AgentGraphView` and NDJSON watch output;
- add bounded journal-derived coordination telemetry to that summary: implementation, Check, worker-wait, and audit wall time; dispatches; operational terminal failures; technical attempts; token/cache observations when available; approved tasks; and blocking versus carry-forward findings;
- expose coordinator-fenced, lifecycle-atomic, content-addressed malformed-result quarantine that preserves the original bytes before `record-result` returns a schema error, also supports explicit idempotent quarantine, reports pending cleanup without a second mutation, and unblocks audited abandon/retry;
- apply that same quarantine boundary to Orca `worker_done` delivery by materializing deterministic candidate bytes before validation, withholding provider acknowledgement until public quarantine succeeds, and treating malformed delivery as transport failure rather than a technical retry;
- make quarantine consume the current attempt's result slot so corrected bytes require cleanup-gated abandonment and a fresh attempt instead of creating mixed evidence in one attempt;
- align the WorkerResult schema, imperative validator, Host sync, and public documentation so a no-change audit can report a blocker without fabricating a Check, while changed-file results still name a real worker check;
- request exact visible or offscreen browser surfaces from capable drivers, link them to tasks and visual evidence, and project only bounded browser receipts into the graph;
- return compact receipts and deltas, stream watch output incrementally, and add cross-process journal fencing;
- make check execution bounded, durable, single-flight, snapshot-addressed, and process-tree-cleaned across concurrent public CLI callers;
- make public source validation and bootstrap share one process-decision validator so a reported-valid spec cannot fail later on the same source enum or field;
- export a deterministic, content-addressed Maestro compatibility bundle from a completed pass run so Orca can verify real Harness capability evidence instead of trusting consumer-authored authority labels;
- validate cleanup target and typed owner at registration so every accepted record has a reachable verified, retained, unverifiable, or failed terminal transition;
- implement real current-workspace and child-worktree placement in the Orca adapter;
- require exact workspace scope at reservation and carry the selected placement and complete public driver context through dispatch, recovery, resume, and cleanup;
- normalize canonical cleanup receipts by their typed source before learning snapshots validate them;
- preserve the same graph, evidence, routing, and cleanup semantics without Orca through the host adapter;
- adapt `impl`, `spec`, and research so the Harness starts with the least complex sufficient mode, raises or lowers execution complexity from observed evidence, and never requires the user to arrange terminals by hand;
- let frontend validation open a real visible Orca Browser page when requested, while keeping offscreen automation explicit and preserving a capability-honest no-Orca path.

This is a focused evolution of the current MVP contract. Obsolete state shapes and silent fallbacks are replaced instead of kept behind compatibility layers.

## Outcomes

- The user gives the Harness an implementation or research goal; repository evidence selects direct, verified-single, light-spec, or graph execution before any worker topology is created.
- A proportionally routed coordinator can supervise cheaper workers without copying their transcripts into its context, and it need not remain `xhigh` merely because the source spec is large.
- A cohesive subsystem keeps one writer and one reusable session across consecutive tasks; durable task-level Checks and grades remain independent.
- Model and effort are independent, visible routing decisions. Concrete options such as Luna, Terra, or Sol are resolved only when the active runtime advertises them.
- Concrete provider/model preferences live in a versioned external policy whose digest is frozen per run, so market changes do not require a Harness code patch or silently reroute active work.
- Notes and evidence can become bounded context for selected tasks through typed graph links.
- Browser pages can become owned visual-validation surfaces linked to an attempt and immutable evidence without placing screenshots, DOM, or browser state in coordinator context.
- A worker can request another worker, but only the current coordinator generation can approve and start it.
- Orca can render and operate the graph without becoming its canonical state store.
- Users and CLI consumers receive automatic, truthful progress without prompting the coordinator; terminal decoration and apparent process idleness never determine it.
- Progress exposes bounded product-versus-coordination telemetry and the reason for reduction or expansion without turning those measurements into a score.
- Non-Orca users retain the same behavior through host-native workers, manual capsules, or local execution.
- Resume cannot silently move a run to another worktree, and cleanup cannot be declared complete from an unverified receipt.
- Pre-bootstrap dirty paths remain outside run-owned completion provenance unless a concrete attempt reports them; post-bootstrap unowned changes still fail closed.
- Orca can import exact Harness-produced capability receipt bytes for execution profiles, placement, cleanup, driver context, quarantine, graph views, and run progress; a locally fabricated compatibility fixture never unlocks integration work.
- A report-only worker audit can carry exact evidence and questions with no changed files or invented Check, but it still cannot grade or pass its task.

## First implementation bootstrap

This change updates the Agent Graph runtime that executes its own OpenSpec. The current baseline starts a new Python process from the live worktree for every control command and does not yet pin that runtime. Therefore the first implementation run must freeze the current `skills/agent-graph` runtime before dispatching any task and use that immutable entrypoint for the entire run. The new `ControlRuntimeRef` makes this automatic for subsequent `$impl` runs. A normal live-path `$impl` cutover is not safe for this one bootstrap run.

## Linked Orca change

The native tab, Canvas, terminal interaction, delegation UI, and Orca process lifecycle live in the separate Orca change `maestro-worktree-canvas`. The two repositories share versioned fixtures and a capability-negotiated protocol, but keep independent journals, checks, worktrees, and implementation runs.

One cross-repository OpenSpec run is deliberately not used. The current Agent Graph has one project directory, one repository-relative path namespace, one check working directory, and one journal. Pretending those are multi-repository would make path ownership and cleanup unverifiable.

## Source-graph adoption

Completed Harness runs and preserved Orca Canvas runs keep their frozen journals, states, and graphs. Harness run `maestro-harness-20260823T072820Z` completed all 31 frozen tasks with zero unresolved cleanup, then its first real compatibility export failed closed because MLK-13 treated the missing duplicate `status` field in an ordinary public Check artifact as evidence divergence. The journal and state already carry the authoritative pass status; the immutable artifact carries command, task, attempt, exit, timeout, and bounded output. Fresh run `maestro-harness-20260823T093217Z` stopped `partial` after the public checked import for MLK-08 proved that the shipped portable graph lacked the `process-decision.json` now required by MLK-14. Fresh run `maestro-harness-20260823T095018Z` also stopped `partial`, with verified cleanup, when MLK-09 proved that Host resume still treats an already abandoned historical quarantine as active and blocks its valid successor. Fresh run `maestro-harness-20260823T100831Z` repaired and passed MLK-08, then stopped `partial` with 20 pass tasks and 12 verified cleanups when MLK-09R's combined E2E reproduced the same MLK-15 defect before MLK-15 was schedulable. Fresh run `maestro-harness-20260823T104034Z` imported 25 checked tasks, then stopped `partial` with all five coordinator cleanups verified when MLK-16's Check imported MLK-15's still-red end-to-end resume case. Fresh run `maestro-harness-20260823T110556Z` proved the focused MLK-16 Check, then its first MLK-15 attempt failed because the repair left an earlier unfiltered Host quarantine scan in `resume` and `sync`; it closed `partial` with 26 pass tasks and all ten cleanups verified. Fresh run `maestro-harness-20260823T113841Z` then stopped at the MLK-04 checked import because that unfinished MLK-15 source broke four public-CLI quarantine regressions; it closed `partial` at revision 27 with five pass tasks and all five cleanups verified. Two localized workers then exposed and narrowed the remaining optional-evidence and journal-fence defects, and each full tree was closed before the coordinator applied the exact integration correction. MLK-15's 56-test Check now passes in 155.922 seconds. Completed pass run `maestro-harness-20260823T121943Z` then passed all 31 frozen tasks with all 23 cleanup records settled, but its real export exposed another MLK-13 verifier gap: three reducer-valid legacy terminal-incarnation cleanups project lifecycle `done` while preserving exact finish receipts whose observation status is `verified`. Fresh repair run `maestro-harness-20260823T131416Z` imported all 30 checked predecessors and passed the MLK-13 Check, then the required live export against `maestro-harness-20260823T121943Z` failed earlier at MLK-05. The current runtime's checked imports point to `CheckExecution v1` artifacts containing execution and source digests, exit, timeout, and bounded output; raw command, status, task, and attempt remain in the journal/state consumer binding instead of being duplicated in those bytes. The run closed `partial` at revision 94 with all 31 tasks approved and all ten owned cleanup records verified. Fresh run `maestro-harness-20260823T140739Z-r28` then exposed two MLK-12 contract failures before MLK-13 could start: `import-checked-task` launched MLK-15 while its declared predecessor MLK-16 was pending, and the 300-second MLK-15 timeout became a terminal shared failure with unverified residue and no public recovery or import-time timeout selection. The owner refused artifact surgery, MLK-16 subsequently passed, all five coordinator resources were verified, and the run closed `partial` at revision 75 with 29 pass tasks. Revision 29 reopens MLK-12 before MLK-15 and MLK-13. Checked import must enforce dependency readiness, bind its selected timeout to the execution policy, and recover a timed-out lease only from exact verified process cleanup. All prior journals, states, failed Check evidence, handoffs, and cleanup receipts remain frozen. A fresh Harness graph must first prove MLK-12; a later fresh runtime can then import MLK-15 with the repaired contract and prove MLK-13 before Orca starts its separate Canvas run.

Revision 30 records the outcome of fresh run `maestro-harness-20260823T144151Z-r29`. Its sole visible Terra/high YOLO worker produced a green two-case focal Check, but independent audit rejected the attempt: recovery changed the filesystem record without a journal transition, accepted a vanished root without proving the saved process group absent, published no running execution or registered cleanup before waiting, and omitted most of the executable acceptance matrix. The run closed `partial` at revision 66 with all four owned cleanups verified. MLK-12 remains open for one fresh repair run. MLK-15, MLK-13, the compatibility export, and the separate Orca Canvas run remain downstream.

Fresh run `maestro-harness-20260823T151343Z-r30` exposed a self-hosting schema drift before MLK-12 could become ready. The pinned runtime executed MLK-00 once, persisted passed execution `check-276ef477d595582f86d75791`, and then rejected its own `execution_policy_digest`, `timeout_seconds`, and `output_cap_bytes` as unknown checked-import evidence fields. The import did not commit, no capsule was delivered, all four observed terminal/process cleanups were verified, and the run closed `partial` at revision 15. Revision 31 first performs the smallest bootstrap repair: the checked-import evidence parser must accept and verify the exact fields emitted by `CheckExecution v1`, with a public bootstrap-to-import regression. A fresh graph run is still required for the complete MLK-12 lifecycle repair.

Fresh run `maestro-harness-20260823T152728Z-r31` proved the revision-31 bootstrap repair: its first checked import passed once and nine MLK-12 predecessors were approved. The MLK-06 import then failed in immutable execution `check-76e515bcb92669a0af3d167b` because an expected timeout-blocked `run-check` raised its recovery error before projecting `state.tasks.ROOT-01.check`, breaking the existing compact-output lifecycle contract. No retry or worker followed, both coordinator cleanups were verified, and the run closed `partial` at revision 29. Revision 32 restores that attempt-bound task-check projection as a second bounded bootstrap repair and adds the exact MLK-06 regression to the MLK-12 gate before another fresh graph run. This source correction supersedes the completed run finding's imprecise use of “successful”; the frozen evidence itself remains unchanged.

## Non-goals

- Make the Canvas canonical execution state.
- Copy terminal transcripts into notes, capsules, projections, or coordinator responses.
- Hardcode provider model catalogs in the graph runtime.
- Refresh prices or model rankings on every task, duplicate full implementations for benchmarking, or treat fewer than five comparable approved cases as a new routing default.
- Let a worker expand its own path scope or grade its parent task.
- Add a fixed global fan-out or require the optional Linux resource guard.
- Remove or defer Canvas, browser, terminal, lifecycle, federation, SSH, WSL, Windows, CLI, E2E, documentation, or security requirements in order to improve apparent completion percentage.
- Treat graph size, task numbering, or a reviewer preference as sufficient evidence for fan-out, a more expensive model, or another repair attempt.
- Build a generic multi-repository workflow engine.
- Implement Orca renderer or daemon code in this repository.
- Guess a browser executable, reuse an arbitrary user page, or treat a headless screenshot as proof that a requested visible Orca Browser session opened.
- Copy GPL source from Open Maestri into either repository.

## Evidence

The source audit and integration design are recorded in [the Orca Maestro research finding](../../../research/2026-08-20-orca-maestro-integration.md). The interactive visual contract is captured by [the browser mock](../../../research/mocks/orca-agent-graph/index.html), while the shipped UI remains owned by the linked Orca change.
