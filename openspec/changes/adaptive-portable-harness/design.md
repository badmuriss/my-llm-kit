# Design: adaptive portable harness

## Boundary

The harness makes two independent decisions in this order:

```text
request + repository
        |
        v
adaptive intake -----> ProcessDecision v1 -----> direct | verified_single | light_spec | graph
        |                                                        |
        v                                                        v
CapabilityReceipt v1 ----------------------------------> compatible execution profile
                                                                 |
                                                                 v
                                                        Host adapter | Orca adapter
                                                                            |
                                                                            v
                                                                     Maestro Canvas
```

The process decision answers what work is justified. The capability receipt
answers what the environment can truthfully execute. Neither depends on the
other. Missing Orca, OpenSpec, visible workers, browser surfaces, usage data,
or cache telemetry can reduce the available execution profile but cannot turn a
task into an error when a smaller compatible mode can run.

The existing graph journal remains canonical only for `graph` mode. Direct and
verified-single work do not create a graph merely to satisfy a runtime template.

## Contracts

### ProcessDecision v1

The decision capsule is a bounded repository artifact. It contains:

- request digest and repository scope;
- observed signals: coesion, architectural uncertainty, reversibility and
  blast radius, oracle strength, independent packets, shared-write coupling,
  context pressure, external effects, and unattended execution;
- each material question asked, the answer, and why it changed a decision;
- declared assumptions that did not need a question;
- selected mode, minimal acceptance check, task-local budget policy, and
  escalation/de-escalation triggers; and
- a compact amendment history carrying changed evidence and replacement check.

It never stores conversation transcripts, provider prompts, terminal output,
credentials, or a model name. There is no universal numeric score. The
classifier is a deterministic gate over declared observations, not a probability
or a hidden model judgment.

### CapabilityReceipt v1

An adapter writes a versioned receipt with its adapter identity, observed
capabilities, verification method, missing capabilities, chosen degradation,
and any provider telemetry fields actually available. Canonical capabilities
include local checks, user questions, process-tree cleanup, isolated workspace,
visible worker dispatch, durable worker handle, browser surface, usage metrics,
and cache metrics.

Provider names, commands, model IDs, terminal IDs, worktree IDs, and Canvas
layout remain adapter payloads. A core operation may request a capability but
never assumes a private CLI or fabricates a receipt. Auto selection records one
adapter and reason for the bounded operation; it cannot silently switch in the
middle.

### Canvas and driver boundary

`AgentGraphView` and `DelegationIntent` remain portable core protocol. The Orca
bridge translates them to and from `MaestroMutation`, terminal lifecycle, and
Canvas document state. Canvas layout is presentation state owned by Orca. It
does not enter the canonical journal unless a semantic, adapter-neutral intent
requires it.

The Host adapter is a first-class conformance target. It may create a capsule,
use a host-native worker, or execute one bounded task locally. Unsupported rich
features report `unsupported` or an explicit downgrade, not a guessed fallback.

## Mode policy

| Mode | Required observations | Minimum artifact | Runtime |
|---|---|---|---|
| `direct` | Small, known, reversible, coesive work with a proportionate check. | Objective and check result. | One local agent, no graph. |
| `verified_single` | Investigation or iteration is needed, but one writer can preserve the decision context. | Decision capsule, hypothesis/check per attempt. | One bounded agent loop. |
| `light_spec` | Interface, architecture, data, blast radius, user behavior, or acceptance is materially uncertain. | Short amendable Markdown decision record with invariants and checks. | One writer by default; OpenSpec is optional. |
| `graph` | At least two independently useful packets have disjoint ownership or isolation, individual checks, a defined integration owner, lifecycle cleanup, and a task-local budget. | Graph contracts plus decision and capability receipts. | Existing durable Agent Graph. |

The direct mode is the default when inspection establishes its preconditions.
An absent or weak oracle never authorizes more autonomy. It instead narrows the
scope, selects a spec, or asks the owner for a decision.

## Interview

The intake inspects the request, repository instructions, code, history, and
existing contracts before questioning. A question is eligible only if a
different answer would change behavior, scope, risk, acceptance, or the mode.
The intake groups independent eligible questions and stops when no material
uncertainty remains. The owner can explicitly choose a safe default.

`grill-me` remains a voluntary design stress test. It is not called by intake
or by `spec` automatically.

## Emergence and control

Every mode has escalation and reduction triggers. A discovery changing a
contract, risk, acceptance check, or independent-packet claim records one
amendment before more work starts. Checks, runtime observations, and evidence
outrank stale prose.

Escalating into graph mode first proves packet contracts. De-escalating cancels
only unstarted work, finishes owned cleanup, retains accepted evidence, and
assigns coupled writing to one integrator. No worker is created because a role
label appears in a template. External retries observe a post-condition before
repeating an action.

## Budgets and learning

For `verified_single` and `graph`, the decision declares configurable limits
for tokens or spend when observable, context, wall time, attempts, workers,
tool cost, and cleanup. A limit is task-local policy, not an invented universal
number. Stop on acceptance, a missing permission, an external effect without
safe post-condition, insufficient oracle for the blast radius, or a limit that
cannot buy a new verifiable hypothesis.

Telemetry is shadow-only: provider-resolved profile, input/output/cache fields
when exposed, tool cost when exposed, wall time, retries, accepted result,
detected failure, rework, and coordination overhead. It cannot change routing
or make a claim until a reviewer promotes repeatable, comparable evidence.

## Compatibility and migration

The completed Maestro change remains intact. This successor change adds entry
policy and contracts around it. Existing graph runs keep their recorded
semantics. New graph-mode runs use the adaptive intake result; non-graph modes
do not bootstrap the graph. Orca stays the reference rich adapter, with no
change to its external Canvas implementation required for the first slice.
