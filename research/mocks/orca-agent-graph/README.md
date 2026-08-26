# Orca Maestro functional mock

This mock explores a worktree-scoped infinite canvas as an embedded surface inside Orca. It deliberately renders only Maestro, because Orca already supplies the surrounding browser/tab chrome. It is interactive, but it does not modify Orca and it never starts or stops a real process.

The Canvas is a durable projection. Orca orchestration state and the Agent Graph journal remain authoritative for tasks, dispatches, checks, evidence, ownership, and cleanup.

## Run it

From this directory:

```bash
python3 -m http.server 4173 --bind 127.0.0.1
```

Open it in Orca:

```bash
orca tab create \
  --worktree active \
  --url 'http://127.0.0.1:4173/?state=overview' \
  --json
```

On Linux outside an Orca-managed terminal, use `orca-ide` instead of bare `orca`.

## What to try

1. Drag blank canvas space to pan and use the mouse wheel or bottom-right controls to zoom.
2. Drag a node by its header. Its position persists in `localStorage` under a worktree-specific key.
3. Right-click blank canvas to create an agent, Markdown note, task, artifact, or child-worktree portal.
4. Edit a note in place. Click its connector, then another node, to create a typed context link.
5. Choose `context`, `depends on`, `spawned`, or `produced` in the toolbar before connecting nodes.
6. Delegate to Codex or Claude with an explicit model, effort, parent agent, and execution boundary.
7. Open an agent node to see its simulated terminal stream and send input.
8. Select **Completed source review** and release its reclaimable terminal. The mock preserves its archived output and evidence node.

Child and cloud worktrees never import their nodes into the current Canvas. The parent keeps only a portal to the other worktree's Maestro tab.

## Terminal-card design lock

The Canvas keeps Orca's quiet, monochrome chrome and treats each agent card as a compact operational terminal, not a profile card. Provider identity uses the same recognizable marks as Orca's agent catalog. Model and reasoning effort remain visible as metadata, while lifecycle appears as an icon plus a concrete verb such as **Running**, **Input required**, **Ready to release**, or **Archived**. Collapsed cards never use letter monograms, pulsing dots, generic status pills, or a fake blinking cursor.

The output preview is a bounded list of execution steps. Completed steps use a restrained check, the current step receives one tonal row highlight, and a waiting worker names the required input. A full terminal renderer belongs only in the focused terminal surface so a large Canvas does not mount one expensive renderer per node.

Reference lock, accessed 2026-08-20:

- [Warp terminal](https://warp.dev/terminal): tonal near-black surfaces, low elevation, and terminal-first hierarchy.
- [GitHub Actions job log](https://github.com/referodesign/refero.design/actions/runs/3976048996/jobs/6816288132): explicit step rows and current/completed execution states.
- [n8n workflow Canvas](https://referodesign.app.n8n.cloud/workflow/lmd2SyYaHSiVkOK48XvmT): compact movable-node proportions and direct connection affordances.

The implementation in Orca must reuse its native `AgentIcon`, design tokens, shadcn primitives, and existing terminal preview infrastructure. The inline provider SVGs in this standalone mock exist only because it does not load Orca's React component tree.

## Deterministic review states

Append `static=1` to stop cursor and stream animation:

- Overview: `http://127.0.0.1:4173/?state=overview&static=1`
- Blank-canvas context menu: `http://127.0.0.1:4173/?state=menu&static=1`
- Terra delegation: `http://127.0.0.1:4173/?state=delegate&model=gpt-5.6-terra&static=1`
- Connection mode: `http://127.0.0.1:4173/?state=link&static=1`
- Focused terminal: `http://127.0.0.1:4173/?state=terminal&terminal=agent-runtime&static=1`
- Resource cleanup: `http://127.0.0.1:4173/?state=cleanup&static=1`

## Real Orca capabilities versus proposed Maestro behavior

| Capability | Status |
| --- | --- |
| Supervised worker with agent, model, effort, current/child/top-level worktree, and optional remote environment | Available through `orca orchestration worker-start` |
| Bounded worker output, stop, abandon, retain, and archive-before-release | Available through current orchestration worker commands |
| Terminal preview streaming and resource inspection | Available in current Orca internals |
| Native `maestro` tab type | Proposed and simulated |
| Runtime-owned Canvas store with revisions, receipts, and delta subscriptions | Proposed and simulated |
| Arbitrary Markdown notes and typed edges | Proposed and simulated |
| Agent-driven delegation projected automatically after a worker receipt | Proposed and simulated |
| Durable close-intent ledger and conservative auto-release after settle | Proposed and simulated |
| Kernel containment per PTY on Windows | Proposed; not present in the audited Orca commit |

The first line shown in the delegation dialog mirrors the current Orca CLI contract:

```bash
orca orchestration worker-start \
  --task TASK_ID \
  --worktree current \
  --agent codex \
  --model gpt-5.6-terra \
  --effort high \
  --json
```

The `orca maestro ...` line underneath is intentionally labeled **proposed**. Those commands do not exist yet.

Primary references: [Orca worker CLI contract](https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/src/cli/specs/orchestration-worker-specs.ts), [Orca model catalog](https://github.com/stablyai/orca/blob/4e058d4a52ea4653a5cf86fac271c8010334361e/src/shared/agent-session-option-catalog-claude-codex.ts), and [Open-Maestri interaction model](https://github.com/zlh-428/open-maestri/tree/6db452e5d1663bfdd4666f757987b0a1affe073d). Accessed 2026-08-20.
