# Graph execution

Use only for an approved graph-mode change. Read the [completion gates](../SKILL.md).

## Bootstrap

A graph-mode `$impl <slug>` is a bounded bootstrap:

```text
python3 "<agent-graph-dir>/scripts/agent_graph.py" validate --repo "<project>" --change <slug> --json
python3 "<agent-graph-dir>/scripts/agent_graph.py" bootstrap --repo "<project>" --change <slug> --run-id <run-id> --driver host --json
```

Use `host` for the portable local/native-worker path. If Orca or automatic
selection is requested, obtain a valid `--workspace-receipt` from that host first;
do not fabricate one. Driver selection does not change the accepted scope.

The approved change must include
`openspec/changes/<slug>/process-decision.json`. Bootstrap fails closed unless
its current graph contract matches the task packets, checks, permission, budget,
integration owner, and cleanup plan.

Bootstrap freezes the control runtime and returns a coordinator capsule. Claim it
in the current session when that session can own integration and has enough
context. A new visible session is useful when context pressure or the requested
host workflow calls for it, not a requirement for every graph.

A claim uses the capsule's coordinator identity and generation even when it runs
in the bootstrap session. Never continue using the bootstrap identity after
transfer. If another coordinator already owns the run, reconcile through `resume`
or `takeover`; never launch a competing coordinator.

For a handoff, register the owned terminal and process resources before delivery,
verify receipt, then stop the sending session. A host without a handoff surface
continues locally when it can satisfy the contract. Do not invent a private API.
If neither path can satisfy the contract, report the specific missing capability.

Use the pinned absolute entrypoint for every later command. Inspect only the
capsule, current projection and relevant task artifacts after a handoff.

## Coordinator loop

Keep integrable implementation packets and their coordinator in the same
worktree by default, with disjoint file ownership or sequential writes. Worker
creation alone is not a reason to create a worktree. Use a separate worktree for
a review, experiment or other task only when it needs an isolated revision or
environment; record that reason and the integration path. A read-only review
may stay in the shared worktree. Follow an explicit user placement instruction.

Run `claim-coordinator`, then `resume`. Never bootstrap from a claimed coordinator. Every mutating command presents the current generation.

1. Query `ready`. Choose the smallest useful non-conflicting wave.
2. Classify ready work into only the roles it needs: research, documentation, implementation, review, verification, or integration. The coordinator filters review by cohesive package and material risk, rather than auditing every microtask. Before routing Codex workers, read [the model-routing policy](model-routing.md); select only Luna, Terra, Sol or Astra, never GPT-5.5, and verify the resolved model and effort; use [fast-worker](fast-worker.md) for bounded mechanical work and [deep-reasoner](deep-reasoner.md) for hard judgment. Resolve each attempt through the runtime catalog with the cheapest sufficient model and effort. Persist requested/resolved values independently with fallback, rationale, role, risk, and cost rank. Do not escalate model or effort automatically. Apply the `minimal-by-default-v1` artifact budget from `agent-graph`: no speculative tests or Markdown.
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

## Complete the graph

After the common completion gates pass, run `digest`, settle owned resources and
run `complete --outcome <pass|partial|blocked>`. A partial or blocked run is never
reported as complete. Keep request amendments in the existing process decision
and task contracts; do not add a second ledger.

For a blocking review finding, record it before `audit-reject-attempt`. Advisory
hardening remains outside the accepted scope. A configured complexity violation
introduced or worsened by the change requires repair; do not weaken the gate.

Shadow learning through `<impl-dir>/scripts/learning.py snapshot` is optional
and runs only after completion. Missing telemetry stays `unavailable` and never
changes policy automatically.
