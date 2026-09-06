---
name: impl
description: Implement a requested change or approved plan, verify its outcomes, and report concrete blockers. Use graph execution only for independent work that needs durable coordination.
---

# Impl

Complete the authorized change using the least process that can establish its
acceptance. A task does not require a separate spec or executable intake merely
because this skill was invoked.

## Select the working mode

Read the applicable repository instructions and code relevant to the request.
Use an existing decision when supplied. Otherwise choose from task evidence:

- `direct`: one bounded edit and its relevant check. No planning file or graph.
- `verified_single`: one writer with a hypothesis/check loop for uncertain behavior.
- `light_spec`: use an existing decision record, or write `decisions/<slug>.md`
  when a material architectural decision needs to survive the session.
- `graph`: use only for independently useful packets that need durable ownership,
  integration and recovery. Read [graph-execution.md](references/graph-execution.md).

Executable intake is optional outside graph. When needed, resolve the installed
`agent-graph` skill directory, then invoke its `scripts/agent_graph.py` with
`--repo <absolute-project-path>`. Use `python3` on Unix or `py -3` on Windows.
Never assume the consumer project contains the harness source.

## Keep acceptance visible

For substantial work, state the required outcomes, relevant constraints and how
each outcome will be checked. Use the current plan or task list, not another
ledger. Keep trivial edits in conversation. Separate required outcomes from
optional ideas; do not turn improvement opportunities into new requirements.

Continue through implementation, verification and repairs caused by the change.
Respect existing authorization. Ask only when an unresolved choice changes scope,
permissions or acceptance and cannot be settled from the available evidence.

After a request amendment, update affected outcomes and checks before continuing.
On resume, reconcile existing work and owned processes first. Read the objective,
decisions, evidence and pending work instead of replaying the whole transcript.

## Completion gates, all modes

- Reconcile the current request against delivered outcomes. Name anything missing,
  deferred or blocked; none of those counts as completed.
- Use a check that can fail for the relevant defect. Do not certify success by
  echoing an expected string, checking a box, or trusting a worker's report.
- Bind evidence to the actual result being delivered. Reuse passing checks while
  the checked inputs and acceptance remain unchanged; rerun affected checks after
  a repair. Test negative assertions against a known positive control when their
  failure could otherwise be silent.
- Review the affected diff and integration boundaries. Honor configured project
  gates without suppressing them. Use a separate read-only reviewer for a
  consequential contract, concurrency or integrity change, or when requested;
  use `thermo-nuclear-code-quality-review` for that deeper review when available.
- For rendered changes, follow `frontend-visual-validation`. Missing vision is
  unobserved evidence, not a passing build.
- Settle resources started for the task and report any explicitly retained ones.

Stop on demonstrated acceptance, a concrete blocker, or the declared budget.
Do not loop until every imaginable improvement is exhausted. When a repair no
longer has a distinct evidence-backed hypothesis, explain the blocker rather
than retrying the same approach or silently increasing model cost.

Report the delivered behavior, relevant checks and remaining limitations. In
non-graph modes this ends the task: no `digest`, journal or `complete` command.
