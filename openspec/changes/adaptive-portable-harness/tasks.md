# Tasks

- [ ] APA-01 Define versioned adaptive decision and capability contracts.
  Depends: []
  Paths: [skills/agent-graph/references/process-decision.schema.json, skills/agent-graph/references/capability-receipt.schema.json, skills/agent-graph/references/task-graph.md, skills/agent-graph/scripts/validation.py, skills/agent-graph/tests/test_adaptive_intake.py]
  Mode: write
  Isolation: auto
  Context: Create bounded schemas for `ProcessDecision v1` and `CapabilityReceipt v1`. Encode only observable process signals, material-question provenance, mode, checks, task-local budgets, amendments, verified capability declarations, and explicit degradation. Keep provider and Canvas details in adapter extension fields.
  Acceptance: Valid fixtures cover all four modes, assumptions, material questions, amendments, absent optional capabilities, Host and Orca receipts, and unknown optional extension fields. Invalid mode changes, transcript-like payloads, hidden provider assumptions, unsupported capability claims, and universal numeric thresholds fail validation.
  Check: python3 -m unittest discover -s skills/agent-graph/tests -p test_adaptive_intake.py

- [ ] APA-02 Implement repository-first adaptive intake and proportional interview.
  Depends: [APA-01]
  Paths: [skills/agent-graph/scripts/adaptive_intake.py, skills/agent-graph/scripts/agent_graph.py, skills/agent-graph/tests/test_adaptive_intake.py]
  Mode: write
  Isolation: auto
  Context: Add a read-first intake command that produces a decision capsule without bootstrapping a run. It must collect observable signals, emit questions only when alternate answers lead to different actions, support an explicit safe-default choice, and return the smallest compatible mode. It must not invoke `grill-me` or infer a model/provider.
  Acceptance: Fixtures prove small reversible work selects direct with no graph; a coesive debugging loop selects verified_single; material interface uncertainty selects light_spec; and graph selection fails closed unless independent packets, ownership, checks, integrator, budget, and cleanup are all declared. Repository facts suppress redundant questions; a material ambiguity produces one decision-changing question; no graph artifacts exist before graph selection.
  Check: python3 -m unittest discover -s skills/agent-graph/tests -p test_adaptive_intake.py

- [ ] APA-03 Make Host and Orca capability discovery explicit and portable.
  Depends: [APA-01]
  Paths: [skills/agent-graph/scripts/drivers/base.py, skills/agent-graph/scripts/drivers/host.py, skills/agent-graph/scripts/drivers/orca.py, skills/agent-graph/scripts/agent_graph.py, skills/agent-graph/tests/test_driver_profiles.py, skills/agent-graph/tests/test_host_driver.py, skills/agent-graph/tests/test_orca_driver.py]
  Mode: write
  Isolation: auto
  Context: Adapt existing driver detection to emit `CapabilityReceipt v1` and separate a generic requested capability from adapter-specific resolution. Preserve Orca as the rich adapter and its lifecycle receipts. Keep Host capable of direct/local/manual execution without guessed private CLIs.
  Acceptance: Host and fake-Orca fixtures report the same core capability names with different truthful values. Missing browser, visible-worker, cache, or usage capabilities select a declared compatible downgrade or block only the operation that requires it. Core selection contains no Orca terminal, Canvas, or model identifier. Explicit Orca never silently becomes Host.
  Check: python3 -m unittest discover -s skills/agent-graph/tests -p test_driver_profiles.py

- [ ] APA-04 Route commands and skills through the selected minimum process.
  Depends: [APA-02, APA-03]
  Paths: [commands/spec.md, commands/impl.md, skills/spec/SKILL.md, skills/impl/SKILL.md, skills/agent-graph/SKILL.md, skills/agent-graph/scripts/agent_graph.py, scripts/tests/test_harness_contracts.py]
  Mode: write
  Isolation: auto
  Context: Make adaptive intake precede durable planning and implementation. Direct and verified-single modes remain usable without OpenSpec or a graph. Light spec uses an amendable record and promotes to OpenSpec only when durability is justified. Graph mode alone performs a fresh coordinator bootstrap. Effort and model are selected from the task-local decision and receipt, never prescribed as a fixed maximum default.
  Acceptance: Contract tests show the kit works with Host only, no OpenSpec, and no Canvas for direct and verified-single work; OpenSpec is optional in light_spec; graph mode produces the existing coordinator/receipt path; `grill-me` is never implicit; and skills never require a provider or Canvas name to choose a mode.
  Check: python3 -m unittest scripts.tests.test_harness_contracts

- [ ] APA-05 Add evidence-led escalation, de-escalation, and stop controls.
  Depends: [APA-02, APA-04]
  Paths: [skills/agent-graph/scripts/adaptive_intake.py, skills/agent-graph/scripts/graph_core.py, skills/agent-graph/scripts/agent_graph.py, skills/agent-graph/references/run-state.schema.json, skills/agent-graph/tests/test_adaptive_intake.py, skills/agent-graph/tests/test_graph_core.py, skills/agent-graph/tests/test_agent_graph_cli.py]
  Mode: write
  Isolation: auto
  Context: Implement decision amendments and graph-mode transition gates. A graph may start only after an intake decision and explicit packet contracts. Reduction cancels unstarted work, preserves accepted evidence, verifies or retains owned cleanup, and records the new single-integrator plan. Retrying external effects must require post-condition observation first.
  Acceptance: Tests cover an emerging independent read packet, discovery of shared-write coupling that prevents dispatch, graph reduction with no orphaned cleanup, stale decision rejection after a material amendment, and stop conditions for missing permission, weak oracle, and exhausted task-local budget. Role labels alone never create a task or worker.
  Check: python3 -m unittest discover -s skills/agent-graph/tests -p test_graph_core.py

- [ ] APA-06 Preserve the Canvas boundary and prove adapter conformance.
  Depends: [APA-03, APA-05]
  Paths: [skills/agent-graph/references/agent-graph-view.schema.json, skills/agent-graph/references/delegation-intent.schema.json, skills/agent-graph/references/maestro-mutation.schema.json, skills/agent-graph/scripts/maestro_bridge.py, skills/agent-graph/tests/test_maestro_bridge.py, skills/agent-graph/tests/test_end_to_end.py]
  Mode: write
  Isolation: auto
  Context: Keep `AgentGraphView` and generic delegation as portable semantics. Constrain Maestro mutation, terminal identifiers, layout, and document UI behavior to the Orca bridge. Add conformance fixtures for a no-Orca Host run and an Orca bridge run that consume the same core projection and report different truthful capabilities.
  Acceptance: Core schemas and projections do not require Maestro mutation, Canvas layout, terminal handles, or Orca identity. The Orca bridge still renders/accepts negotiated protocol traffic through its adapter. A complete Host graph run works with no Orca process; an unsupported visual request is explicit rather than fabricated.
  Check: python3 -m unittest discover -s skills/agent-graph/tests -p test_end_to_end.py

- [ ] APA-07 Add shadow-only process telemetry and document the portability contract.
  Depends: [APA-04, APA-05, APA-06]
  Paths: [skills/agent-graph/scripts/learning.py, skills/impl/scripts/learning.py, skills/impl/references/learning-run.schema.json, README.md, skills/agent-graph/SKILL.md, skills/impl/SKILL.md, scripts/tests/test_harness_contracts.py]
  Mode: write
  Isolation: auto
  Context: Record only provider-exposed usage/cache/profile fields with mode, result, retry, time, rework, and coordination overhead. Keep learning shadow-only and make the documentation distinguish portable core, optional OpenSpec, Host, Orca, and future adapters. Do not add price tables, provider constants, or automatic policy promotion.
  Acceptance: Missing telemetry serializes as unavailable rather than zero or estimated. Learning never changes the current run, routing, capability receipt, or evidence grade. Documentation states that Orca is the current rich adapter rather than a prerequisite, and validates every shipped command/skill reference.
  Check: python3 -m unittest scripts.tests.test_harness_contracts
