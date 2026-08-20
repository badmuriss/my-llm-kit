---
description: Implement an OpenSpec graph with a fresh coordinator and evidence grades
---

Implement the approved change. Inspect every diff and grade only observed evidence.

**Change to implement:** $ARGUMENTS

1. For a normal slug, run `python3 skills/agent-graph/scripts/agent_graph.py bootstrap --change <slug> --run-id <run-id> --driver auto --json`. Do not read the full package first.
2. Transfer the returned `$impl --coordinator-capsule <path>` invocation to one fresh top-level session in the current checkout. Orca uses a fresh terminal and a full handoff, never an orchestration Task or Dispatch. A host without visible session handoff prints the exact invocation and stops.
3. For `--coordinator-capsule`, run `claim-coordinator`, then `resume`. Never bootstrap again from the claimed coordinator. Reconcile incomplete reservations with `recover-driver-selection` or `recover-attempt`; use driver-owned `abandon-attempt` only when recovery cannot continue.
4. Query `ready`, dispatch the smallest useful wave from generated task capsules, then use `sync`, `record-result`, and `reply`. Provider completion only reports work; it never grades a task.
5. Run `run-check`, inspect the diff and evidence, then run `grade`. Record each failed repair hypothesis with `record-repair` before editing again.
6. Register and finish resources with `cleanup-register` and `cleanup-finish`.
7. Run the independent maintainability review for source changes. Verify findings and rerun affected checks.
8. Run `digest`, then `complete --outcome pass|partial|blocked`. A pass requires every task to pass and cleanup to be empty.
9. Optionally run `python3 skills/impl/scripts/learning.py snapshot --change <slug> --run-id <run-id>` after completion.

Use `--driver orca` for Orca, `--driver host` for repository-only native or local execution, and `--driver auto` for one recorded choice. Orca may visibly degrade from supervised to tracked-terminal lifecycle. It never switches to host after the run starts. Maestri remains a future driver with no guessed adapter.
