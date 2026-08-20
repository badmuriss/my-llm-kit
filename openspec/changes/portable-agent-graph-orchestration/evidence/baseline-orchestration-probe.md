# Baseline orchestration probe

## Scope

The probe ran against the local `my-llm-kit` checkout. Both worker tasks were read-only. No source file changed, and the created Orca terminal was closed at the end.

This is a weak sample from one Orca runtime and one Codex native subagent. It defines recovery requirements but does not measure general product reliability.

## Orca runtime

- Run: `run_975769b8ef5b`
- Root task: `task_6326d2a08edc`
- Dependent task: `task_b3a8c7065ef3`
- First Dispatch: `ctx_c32672ad75f6`
- Reused-terminal Dispatch: `ctx_8d58b3267012`
- Created terminal: `term_e0ab40f2-3ab3-4236-9a3e-ec397fb8c373`

The runtime reported ready and advertised the orchestration contract. The repository and exact current worktree were discoverable.

## Observed sequence

1. The root task entered `ready`.
2. The dependent task remained `pending` and did not appear in `task-list --ready`.
3. `worker-start` failed with `selector_not_found` for the exact full worktree ID returned by `worktree current`.
4. `terminal create`, `terminal wait --for tui-idle`, and `dispatch --inject` succeeded.
5. The worker opened an Orca question. The coordinator received it through `check --wait`, replied `yes`, and acknowledged the Delivery.
6. The worker sent one successful `worker_done`. Orca completed the root Task and Dispatch.
7. The dependent task changed to `ready` only after the root completion.
8. `worker-show` and `worker-start --terminal` did not recognize the low-level Dispatch and returned `dispatch_not_found` or `selector_not_found`.
9. A second low-level `dispatch --inject` reused the same terminal and completed the dependent task.
10. `dispatch-show` exposed the completed Dispatch, but `worker-read` and `worker-release` reported that no supervised agent terminal existed.
11. The coordinator acknowledged the final Delivery, verified the exact terminal identity, closed the terminal it had created, and confirmed that the worktree had no remaining terminal.

## Orca conclusion

Run, Task, dependencies, Dispatch, ask/reply, Delivery acknowledgment, and `worker_done` worked through the tracked-terminal path. The supervised composition and ownership APIs did not work for this checkout.

The driver therefore needs explicit lifecycle tiers. It may use low-level Dispatch as a visible degradation, but it cannot pretend that worker inspection or release exists in that tier. It must track and clean only resources it created.

## Native Codex comparison

A native read-only subagent inspected the same harness material and returned a compact structured result. It exposed a live agent path during the conversation but no durable, repository-backed Task, Dependency, or Dispatch IDs.

The useful native invariant was: a task becomes ready only after every dependency has evidence-approved grade `pass`.

## Design consequence

The repository graph supplies durable identity, readiness, evidence state, and resume. Orca adds a richer transport and visible lifecycle when its capabilities work. Native subagents remain a valid execution path but do not replace the canonical journal.

The baseline did not transfer the implementation coordinator to a fresh session. The implementation probe must validate that separately. The desired lifecycle is a full handoff to a new top-level coordinator, not a worker Dispatch supervised by the old session.
