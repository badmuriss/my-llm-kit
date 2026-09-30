# Adversarial plan validation

Find concrete ways the proposed plan could miss the user's outcome before
implementation starts. Review the real consumers and constraints, not only the
plan's internal consistency. Do not promise a plan has no remaining edge cases.

## Scope the pass

Read the canonical spec and relevant local instructions. Preserve the user's
decisions, authorization and acceptance gates. Define what completion means,
including words such as all, retire, replace, preserve and compatible. A named
future phase is not evidence that its required capability has a viable design.

Choose narrow, independent review questions. One reviewer is enough for one
cohesive risk; two or three may suit different consumer, runtime and migration
boundaries. The main author remains the only plan writer and performs a useful
independent check while reviewers work. No review cascade or new worktree just
for read-only inspection. Select model/effort using the applicable routing policy
and report unavailable or unobservable selections rather than inventing identity.

Give each reviewer the user outcome, canonical plan, raw source locations,
constraints and its bounded question. Ask for evidence, not endorsement. Do not
send only the author's summary. Reviewers must not edit, implement, buy, deploy,
run paid/live experiments or spawn more reviewers. If tools or authorization
are unavailable, perform a labeled self-review and report independent review as
unobserved; do not block unrelated useful planning work.

## Questions that expose gaps

Select those that can affect the actual task:

- Coverage: which real caller, dynamic dispatch, CLI, MCP, scheduled job,
  configuration, install path or generated artifact is missing? Is a supposedly
  optional capability required by a current consumer?
- Contracts: which fields, errors, ordering, pagination, identity, timestamps,
  cache semantics or billing rules would change? Who consumes persisted older
  versions, and can mixed-version operation occur?
- Failure paths: what happens on saturation, timeout, partial success, retry,
  duplicate delivery, cancellation, crash or lost response? Are limits global or
  accidentally multiplied? Who owns each state and budget reservation?
- Migration: can an old job, installed client, fallback or environment setting
  reactivate the retired dependency? Does rollback still require it after final
  retirement? Do historical records need a reader without retaining a writer?
- Feasibility: which external capability, access, cost, policy or runtime claim
  is only assumed? Which needs a finite future spike, and what would falsify it?
- Acceptance: does every required outcome have an observable check? Are gates
  weakened, unsupported results treated as success, or absence of traffic used
  as proof without exercising the workflow?

For each material finding require: severity, exact evidence locator, failing
scenario, effect on the user's outcome, smallest necessary amendment and a
falsifying/acceptance check. Separate observed facts from inference. Reject
generic checklists, speculative consumers and architecture growth without a
real requirement.

## Adjudicate and close

The author reads the cited evidence, merges duplicate findings and records each
material finding as accepted, rejected with reason, or unresolved with a named
proof obligation. Amend the canonical plan with concrete responsibilities,
dependencies and acceptance, not just a list of concerns. An external unknown
can be a bounded spike with a stop criterion; it is not a proven solution.

Use one review round by default. Request targeted re-review only when an
accepted blocker materially changed a contract or architecture, or reviewers
disagree on a consequential fact. Recheck affected boundaries, not the whole
plan; stop when findings are adjudicated or a concrete external/user decision
remains. Do not iterate until everyone says approved.

Before handoff, distinguish plan-ready work from unresolved requirements and
unexecuted validation. Record reviewer scope, evidence limits and model identity
only when observable. Refresh the visual brief after changing the spec. A PDF,
clean validator or unanimous review does not prove runtime acceptance. Never
declare a full retirement planned or achieved by silently dropping a required
consumer, leaving it permanently unsupported or deferring it past cutover.
