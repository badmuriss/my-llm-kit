---
description: Implement through the minimum verified mode; bootstrap only approved graphs
---

Implement the approved change through its selected process. Inspect every diff and trust only observed evidence.

**Change to implement:** $ARGUMENTS

1. Read repository instructions and the supplied decision. If no valid `ProcessDecision v1` exists, run `agent_graph.py intake` before implementation. Do not invoke `grill-me` implicitly.
2. Follow the selected mode:
   - `direct`: use one local writer, make the bounded change, run the selected check, and report the result. Do not create OpenSpec or a graph.
   - `verified_single`: keep one writer in a bounded hypothesis/check loop. Record each new hypothesis and stop condition. Do not create OpenSpec or a graph.
   - `light_spec`: implement from the amendable Markdown decision record with one writer. OpenSpec is optional. Promote only after a material amendment selects `graph` and proves its packet contracts.
   - `graph`: require `openspec/changes/<slug>/process-decision.json`, validate the approved OpenSpec change, then bootstrap its durable run.
3. For `graph`, run `python3 skills/agent-graph/scripts/agent_graph.py bootstrap --change <slug> --run-id <run-id> --driver auto --json`.
4. Before delivering the capsule invocation, register the owned terminal, Codex
   process tree, and PTY root. Transfer it to one fresh top-level session. Orca
   uses a fresh terminal and a full handoff, never an orchestration Task or
   Dispatch. A host without visible handoff prints the exact invocation and
   stops.
5. For `--coordinator-capsule`, run `claim-coordinator`, then `resume`. Never bootstrap from a claimed coordinator. Recover incomplete reservations before retrying.
6. Query `ready`, dispatch the smallest useful wave, then use `sync`, `record-result`, and `reply`. A worker report never grades a task.
7. Run `run-check`, inspect the diff, then run `grade`. Use `record-repair` before each repair.
8. Register and finish resources with `cleanup-register` and `cleanup-finish`.
9. Run the independent maintainability review for source changes. Verify findings and rerun affected checks.
10. For `graph`, run `digest`, then `complete --outcome pass|partial|blocked`. Optionally snapshot shadow learning after completion.

Graph bootstrap freezes the control runtime before handoff. The task-local
decision and verified capability receipt select model, effort, placement, and
any explicit fallback. The coordinator derives the smallest useful
non-conflicting wave and keeps one heavy worker at a time. Later commands use
the pinned entrypoint.

`--driver host`, `--driver orca`, and `--driver auto` apply only to graph execution. Adapter capability changes execution, not the selected process mode. An explicit adapter never changes silently.
