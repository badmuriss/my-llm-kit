# Tasks

- [ ] AGR-01 Build the graph parser, journal, projection, and deterministic scheduler.
  Depends: []
  Paths: [skills/agent-graph/SKILL.md, skills/agent-graph/agents/, skills/agent-graph/scripts/graph_core.py, skills/agent-graph/references/task-graph.md, skills/agent-graph/references/run-state.schema.json, skills/agent-graph/references/worker-result.schema.json, skills/agent-graph/references/coordinator-capsule.schema.json, skills/agent-graph/tests/test_graph_core.py]
  Mode: write
  Isolation: auto
  Context: Replace the flat task list with the task contract and single-writer event model in `design.md`. Use repository-relative file or directory prefixes, not globs. Keep the implementation in the Python standard library. The projection must rebuild from events and recover only a partial final line. Coordinator capsules and generations fence journal mutations after a handoff or takeover.
  Acceptance: Validation rejects malformed fields, unsafe paths, unknown dependencies, self-dependencies, cycles, and duplicate IDs. Readiness requires dependency grades of `pass`. Concurrent write eligibility rejects overlapping path prefixes. Worker reports remain distinct from task grades. Journal replay reproduces the saved projection and blocks corruption outside a final partial line. A stale coordinator generation cannot mutate state.
  Check: python3 -m unittest discover -s skills/agent-graph/tests -p test_graph_core.py

- [ ] AGR-02 Implement the Orca driver with supervised and tracked-terminal lifecycle tiers.
  Depends: [AGR-01]
  Paths: [skills/agent-graph/scripts/drivers/__init__.py, skills/agent-graph/scripts/drivers/base.py, skills/agent-graph/scripts/drivers/orca.py, skills/agent-graph/tests/test_orca_driver.py]
  Mode: write
  Isolation: auto
  Context: Follow the installed Orca skill contract summarized in `design.md`. Select one CLI, preflight capabilities, and mirror local Run, Task, dependency, Dispatch, question, and result identities. Prefer `worker-start`. On its recognized composition failure, use terminal creation plus injected Dispatch and emit `driver_degraded`. Never treat `worker_done` as evidence `pass`.
  Acceptance: Fake-CLI behavior covers full supervised success, selector failure with tracked-terminal fallback, bounded transcript reads, question/reply, resume reconciliation, and cleanup. The driver releases supervised workers through Orca. It closes a tracked terminal only when its receipt proves the harness created the same terminal incarnation. Explicit Orca mode fails instead of switching to the host driver.
  Check: python3 -m unittest discover -s skills/agent-graph/tests -p test_orca_driver.py

- [ ] AGR-03 Implement the host driver and structured task capsules.
  Depends: [AGR-01]
  Paths: [skills/agent-graph/scripts/drivers/host.py, skills/agent-graph/tests/test_host_driver.py]
  Mode: write
  Isolation: auto
  Context: The host driver supports Codex, Claude, and other hosts without guessing their private subagent APIs or shelling out to an agent CLI. It writes a bounded worker capsule, records the host worker handle when available, and accepts the shared worker-result schema. The repository graph supplies durable IDs. A nested native subagent may be a worker but never the implementation coordinator.
  Acceptance: A ready task produces a capsule containing only its task contract, dependency digest, driver instructions, and result path. A schema-valid result advances the attempt to `reported`; malformed, duplicate, mismatched, or out-of-scope results fail. Local execution uses the same result contract. The driver can resume from repository state without a live worker handle. Hosts without visible fresh-session handoff return an exact coordinator capsule invocation instead of continuing in the bootstrap context.
  Check: python3 -m unittest discover -s skills/agent-graph/tests -p test_host_driver.py

- [ ] AGR-04 Expose the graph runtime through one cross-platform CLI.
  Depends: [AGR-02, AGR-03]
  Paths: [skills/agent-graph/scripts/agent_graph.py, skills/agent-graph/scripts/runtime_config.py, skills/agent-graph/scripts/validation.py, skills/agent-graph/tests/test_agent_graph_cli.py]
  Mode: write
  Isolation: auto
  Context: Implement the CLI surface from `design.md`. Keep the event journal canonical. `bootstrap` creates a transcript-free coordinator capsule; `claim-coordinator` prevents recursive handoff; explicit `takeover` reconciles state and fences the prior generation. `--driver auto` records its selection once. `status --watch` reads projections without loading transcripts. Check execution must preserve the current direct executable behavior and reject shell operators.
  Acceptance: The CLI bootstraps and claims fresh coordinators, rejects stale generations, validates, starts, resumes, lists ready tasks, dispatches, syncs, records results, replies, runs checks, grades, tracks cleanup, prints status, and completes a run. Every agent-facing command has stable JSON output and actionable errors. Replaying the same external receipt is idempotent. A run cannot pass with ungraded tasks or pending cleanup.
  Check: python3 -m unittest discover -s skills/agent-graph/tests -p test_agent_graph_cli.py

- [ ] AGR-05 Replace the flat impl runtime and reconnect evidence, visual validation, and shadow learning.
  Depends: [AGR-04]
  Paths: [skills/impl/scripts/impl_state.py, skills/impl/scripts/runtime_config.py, skills/impl/scripts/visual_evidence.py, skills/impl/scripts/learning.py, skills/impl/references/impl-state.schema.json, skills/impl/references/visual-evidence.example.json, skills/impl/references/learning-run.schema.json, skills/impl/tests/test_impl_state.py, skills/impl/tests/test_runtime_config.py, skills/impl/tests/test_learning.py, skills/agent-graph/scripts/visual_evidence.py, skills/agent-graph/references/visual-evidence.example.json, skills/agent-graph/tests/test_impl_evidence.py]
  Mode: write
  Isolation: auto
  Context: Remove the old `impl_state.py`, its flat schema, and obsolete tests after their behavior is represented by `agent_graph.py`. Move shared runtime and visual evidence ownership into `agent-graph`. Update `learning.py` to snapshot completed graph projections. Do not add migration, aliases, or dual writes.
  Acceptance: Existing check grading, visual manifest validation, repair caps, cleanup enforcement, final outcome rules, and shadow-learning snapshots work against graph runs. Removed CLI paths no longer appear in active skills or tests. A completed graph run produces the data required by learning without reading terminal transcripts.
  Check: python3 -m unittest discover -s skills/agent-graph/tests -p test_impl_evidence.py

- [ ] AGR-06 Route `spec`, `impl`, and research through the portable graph contract.
  Depends: [AGR-05]
  Paths: [commands/spec.md, commands/impl.md, skills/spec/SKILL.md, skills/impl/SKILL.md, skills/research/SKILL.md, README.md, scripts/tests/test_harness_contracts.py]
  Mode: write
  Isolation: auto
  Context: `spec` must emit every graph field and validate without starting workers. A normal `$impl <slug>` must bootstrap a fresh top-level coordinator, then stop the invoking session after verified handoff. The internal coordinator-capsule invocation skips another bootstrap. `impl` must then use ready waves, provider tiers, structured results, evidence grading, and cleanup. Research must use read-mode collector tasks when delegation is useful while keeping source adjudication in the main researcher. Document Orca, host, auto, and future Maestri boundaries.
  Acceptance: Each skill names the exact `agent_graph.py` commands it owns. Orca starts the fresh coordinator in the current worktree as a full handoff, never as a worker Dispatch. Hosts without visible session handoff stop with an exact capsule invocation. Worker prompts use generated capsules instead of copying the whole spec. Driver degradation and host fallback are visible. No active documentation refers to `impl_state.py` or treats provider completion as proof. The contract test verifies fresh coordinator bootstrap, required task fields, and command references across shipped skills and commands.
  Check: python3 -m unittest scripts.tests.test_harness_contracts

- [ ] AGR-07 Validate installation and full portable execution without Orca.
  Depends: [AGR-06]
  Paths: [setup.sh, setup.ps1, scripts/tests/test_installers.py, skills/agent-graph/tests/test_end_to_end.py]
  Mode: write
  Isolation: auto
  Context: Setup already links every directory under `skills/`; change installers only if the new skill reveals a real platform gap. Exercise a host-driver run with coordinator bootstrap and claim, a dependency chain, two independent non-conflicting writes, one conflicting write, a report, a failing check, resume, takeover, cleanup, and final completion.
  Acceptance: Linux/macOS and Windows dry-run coverage discovers `agent-graph` without duplicating files. The end-to-end fixture proves transcript-free coordinator handoff, stale-generation fencing, durable IDs, readiness, conflict control, idempotent replay, evidence-only unblocking, crash resume, explicit takeover, and zero pending cleanup without an Orca process.
  Check: python3 -m unittest discover -s skills/agent-graph/tests -p test_end_to_end.py

- [ ] AGR-08 Run the implemented Orca adapter against the real local runtime and preserve the receipt.
  Depends: [AGR-07]
  Paths: [openspec/changes/portable-agent-graph-orchestration/evidence/orca-live.json]
  Mode: write
  Isolation: auto
  Context: Use `probe-orca` to hand off from a bootstrap session to a fresh coordinator terminal, then create a bounded read-only graph with dependent tasks and one ask/reply. The probe may use the tracked-terminal tier only after recording the supervised failure. It must not change repository source files. This task requires real Orca evidence; mocked output cannot pass it.
  Acceptance: The artifact proves that the fresh coordinator claimed the run, the bootstrap generation became stale, and the coordinator was not modeled as a worker Dispatch. It also records runtime capabilities, driver tier, local and Orca IDs, dependency transition, question/reply, worker reports, local evidence grades, every degradation, and cleanup receipts. The probe confirms its created terminals are gone. If Orca is unavailable or cleanup cannot be proven, grade the task `blocked` instead of manufacturing success.
  Check: python3 skills/agent-graph/scripts/agent_graph.py probe-orca --change portable-agent-graph-orchestration --artifact openspec/changes/portable-agent-graph-orchestration/evidence/orca-live.json
