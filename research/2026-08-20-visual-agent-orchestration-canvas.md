# Visual canvas for agent orchestration

## Protocol

- Question: What visual graph or canvas interface should Orca or `my-llm-kit` use to make durable agent orchestration observable and editable, based on Maestri and viable open-source precedents?
- Decision criterion: Recommend the smallest architecture that exposes live tasks, dependencies, sessions, artifacts, questions, evidence, and cleanup without making the canvas the canonical state or coupling the harness to Orca.
- Falsifier: Reject a canvas proposal if it cannot replay durable graph state, cannot distinguish worker reports from evidence grades, requires replacing the current Orca runtime, or depends on an unsuitable or unverifiable open-source license.
- Risk: material

## Provider trail

| Intent | Provider | Tool or endpoint | Outcome | Fallback reason |
|---|---|---|---|---|
| Inspect the portable graph | Local repository | Direct reads and a replayed Agent Graph run | Completed | None |
| Inspect current Orca code | GitHub primary repository | Shallow read-only clone pinned at `6e25a90085970498c772490d0659bf258ed18c17` | Completed | None |
| Inspect the installed Orca | Orca CLI and computer-use | `orca-ide status`, orchestration reads, and accessibility inspection | Runtime and orchestration were reachable; visual UI inspection remained unobserved because the Linux provider exposed neither screenshots nor a useful Electron accessibility tree | Source inspection used for the visual-surface claims |
| Discover Maestri and visual orchestration precedents | Agent Graph host collector | Read-only source discovery task | Completed and locally graded `pass` | None |
| Start collector graph | Agent Graph host driver | `validate`, `init`, `ready`, and `dispatch` | Initial attempt failed because proposal and design were absent | Added the required minimal OpenSpec package before retrying |
| Search live public sources | ScrapingDog | Environment key check plus bounded direct `/google` request | Succeeded after correcting a local JavaScript syntax error that occurred before the first request | None |
| Independent collector fallback | Firecrawl CLI | Bounded search attempt | Failed before retrieval because the account reported insufficient credits | Native web search used and every cited source was opened directly |
| Open and adjudicate sources | Native web search and direct GitHub/documentation reads | Official docs, repositories, source files, and licenses | Completed | A blank batched open was retried with direct searches and opens |

## Claim ledger

| Claim | Source | Accessed | Primary | Direct | Current | Independent | Verdict |
|---|---|---|---|---|---|---|---|
| The intended Maestri is a spatial orchestration layer around existing agents, terminals, notes, and files. | [Maestri introduction](https://www.themaestri.app/en/docs/intro) | 2026-08-20 | yes | yes | yes | no | accepted |
| Maestri notes are Markdown files; note-to-note links expose a context chain to a connected agent. | [Maestri notes](https://www.themaestri.app/en/docs/notes) | 2026-08-20 | yes | yes | yes | no | accepted |
| Maestri's manager can recruit terminals, assign roles, connect notes, and dismiss workers. | [Maestri Maestro mode](https://www.themaestri.app/en/docs/maestro) | 2026-08-20 | yes | yes | yes | no | accepted |
| Orca already has durable Run, Task, Dispatch, gate, messaging, and worker lifecycle primitives. | [Orca orchestration guide](https://github.com/stablyai/orca/blob/main/skill-guides/orchestration.md) | 2026-08-20 | yes | yes | yes | partial | accepted |
| Orca already ships an Agent Map with filters, worktree/project layout, attention state, terminal focus, and optional orchestration links. | [AgentDashboardMapView](https://github.com/stablyai/orca/blob/main/src/renderer/src/components/dashboard-popout/AgentDashboardMapView.tsx), [agent-map-layout](https://github.com/stablyai/orca/blob/main/src/renderer/src/components/dashboard-popout/agent-map-layout.ts) | 2026-08-20 | yes | yes | yes | no | accepted |
| The current Agent Map is agent-lineage-centric: its serialized card contract contains pane/worktree lineage but not task, gate, evidence-grade, cleanup, note, or artifact entities. | [dashboard-snapshot contract](https://github.com/stablyai/orca/blob/main/src/shared/dashboard-snapshot.ts), [agent-map-layout](https://github.com/stablyai/orca/blob/main/src/renderer/src/components/dashboard-popout/agent-map-layout.ts) | 2026-08-20 | yes | yes | yes | no | accepted |
| Orca's dashboard contract already carries linked review/PR identity and state for a workspace. | [dashboard-snapshot contract](https://github.com/stablyai/orca/blob/main/src/shared/dashboard-snapshot.ts), [dashboard snapshot builder](https://github.com/stablyai/orca/blob/main/src/renderer/src/components/dashboard/build-dashboard-snapshot.ts) | 2026-08-20 | yes | yes | yes | no | accepted |
| Orca is available under the MIT license. | [Orca license](https://github.com/stablyai/orca/blob/main/LICENSE) | 2026-08-20 | yes | yes | yes | no | accepted |
| React Flow is an MIT-licensed React library intended for node editors and interactive flow charts. | [React Flow package metadata](https://github.com/xyflow/xyflow/blob/main/packages/react/package.json) | 2026-08-20 | yes | yes | yes | yes | accepted |

## Findings

### Recommendation

Yes, this belongs in Orca, and it does not require replacing Orca with Maestri.

The best design is to evolve Orca's existing `Agent Map` into two coordinated modes:

- `Fleet`: keep the current view of agents, worktrees, status, attention, and terminal focus.
- `Task Graph`: add a task-first DAG showing dependencies, attempts, gates, reports awaiting evidence grade, pass/fail/unobserved grades, PRs/reviews, artifacts, questions, and pending cleanup.

The canvas must be a replayable projection, never the source of truth. Dragging a node changes layout only. A dependency or orchestration mutation must go through the validated CLI/RPC path and append to the canonical journal or Orca database.

Visual proposal: [`orca-agent-graph-canvas.pdf`](assets/orca-agent-graph-canvas.pdf). Editable source: [`orca-agent-graph-canvas.drawio`](assets/orca-agent-graph-canvas.drawio).

### Why copying Maestri literally would be misleading

Maestri solves spatial context management. A cable can connect a terminal to a note chain so the agent can traverse that context. Our harness graph has stronger semantics: `depends_on` controls readiness, a worker report is not an evidence grade, and cleanup can block completion.

The UI therefore needs visually distinct relations:

| Relation | Visual treatment | Meaning |
|---|---|---|
| `depends_on` | solid directed arrow | Enforced execution dependency |
| `context` | dashed cable | Note, spec, artifact, or reference available to the worker |
| `dispatch` | thin ownership line | Task attempt assigned to a terminal/session |
| `blocked_by` | gate marker on the task | Human decision or unresolved question |
| `produced` | dotted output edge | Report, PR/review, diff, check artifact, or evidence |

This preserves Maestri's useful spatial model without suggesting that every visible cable changes execution order.

### Proposed task node and inspector

A collapsed task node should show only the information needed to scan a large run:

- task ID and title;
- lifecycle state: pending, ready, running, reported, blocked, graded, or cleanup pending;
- evidence grade: pass, fail, or unobserved;
- active attempt and host/agent badge;
- attention marker for an open question or failed check.

Selecting it opens an inspector with the exact task contract, dependency digest, worker terminal, linked PR/review, report, check command and result, evidence references, changed files, receipts, questions, and cleanup ownership. Attempts remain collapsed under their task by default so a large spec does not turn into a terminal hairball.

A PR/review is a first-class navigable node, not a loose note. The useful chain is `task → attempt/worktree → PR/review → diff/checks`. Clicking it should reuse Orca's existing review and diff surfaces.

### Portable boundary

The reusable contract should be a versioned, derived JSON projection, tentatively `AgentGraphView v1`:

```text
OpenSpec + events.jsonl/state.json ─┐
                                    ├─> AgentGraphView v1 ─> Orca Task Graph
Orca Run/Task/Dispatch/Gate store ──┘                    └─> standalone viewer
```

This keeps `my-llm-kit` usable without Orca. The same view model can feed a small local browser viewer for Claude Code, Codex, OpenCode, or a host-native driver. Orca adds richer actions such as focusing a terminal, opening a diff, or resolving a gate, but the graph and its evidence remain repository-owned.

### Open-source precedents

| Project | Useful pattern | Why it is not the runtime to adopt |
|---|---|---|
| [open-maestri](https://github.com/zlh-428/open-maestri), accessed 2026-08-20 | Closest spatial UX: terminals, Markdown notes, files, portals, local CLI communication, minimap | Native Swift/AppKit, macOS-oriented, GPL-licensed; useful as an interaction reference, not as an Orca component |
| [termcanvas](https://github.com/lout33/termcanvas), accessed 2026-08-20 | Durable tmux terminals, live fleet state, spawn lineage, attention/status handling | Its sidebar intentionally omits peer edges and it does not model task evidence or gates |
| [RondoFlow](https://github.com/rondoflow/rondoflow), accessed 2026-08-20 | React Flow board, live agent execution, policies, readonly roles, audit surface | It owns a separate workflow runtime and server/data stack; adopting it would duplicate Orca and the harness |
| [Agent Canvas](https://github.com/TheSaiEaranti/agent-canvas), accessed 2026-08-20 | Clear per-node running/completed/error states, streamed node output, animated edges | Useful UI prototype, but it models prompt/tool/output execution rather than coding-agent attempts and evidence |
| [Cognograph](https://github.com/skovalik/cognograph), accessed 2026-08-20 | Semantic zoom, persistent context graph, task/note/artifact node vocabulary, plan-preview-apply | AGPL plus defensive patent terms require legal review before reuse in an MIT product |
| [Kudosflow](https://github.com/akudo7/kudosflow), accessed 2026-08-20 | Portable JSON workflow, React Flow editor, live execution, explicit approval nodes | Its VS Code/LangGraph/A2A execution model is a different runtime contract |

The common technical pattern is React plus a graph view model, typed nodes/edges, and live execution events. React Flow is compatible with Orca's React renderer and MIT license, but Orca currently does not list it as a dependency. A spec should compare adding it for `Task Graph` against extracting reusable viewport primitives from the existing custom SVG `Agent Map`; it should not rewrite the stable Fleet view just to standardize on a library.

### Implementation shape

The smallest coherent implementation is:

1. Define `AgentGraphView v1`, including stable IDs, typed nodes/edges, status, grade, attention, PR/review and artifact references, and optional Orca terminal/worktree handles.
2. Add a deterministic projector from the portable Agent Graph journal/state.
3. Add a read-only `Task Graph` mode to Orca's existing dashboard popout and a standalone viewer consuming the same projection.
4. Add node-to-terminal/PR/review/diff/artifact navigation.
5. Add explicit, journaled mutations only after the read-only graph is proven legible on large specs.

Notes should remain ordinary Markdown files and artifacts should remain ordinary files/receipts. The canvas persists only presentation metadata such as position, collapsed state, filters, and saved views.

## Disagreements

- “Maestri” is ambiguous on the public web because UiPath also has a product named Maestro. The user's description matches [themaestri.app](https://www.themaestri.app/en), not UiPath's BPMN product.
- `open-maestri` asserts compatibility with Maestri's workspace and CLI formats. That compatibility claim was not independently tested and is not needed for the recommendation.
- The open-source precedents disagree on whether the canvas is merely a view or the executable workflow definition. For this harness, durable replay and evidence grading make the view-only projection the safer canonical boundary.

## Open questions

- Should the first Orca `Task Graph` renderer reuse the custom SVG viewport or introduce React Flow only for the new mode?
- Should the standalone viewer be a generated single-file HTML artifact or a local live server watching `state.json` and `events.jsonl`?
- Which presentation metadata belongs in the repository, and which should remain per-user Orca state?

## Council review

- Status: not run
- Reason: the recommendation is grounded in official documentation, primary source code, licenses, and multiple primary open-source precedents; no unresolved source disagreement changes the decision.
- Accepted findings: n/a.
- Rejected findings: n/a.

## Sources consulted

- [Local `my-llm-kit` repository](https://github.com/badmuriss/my-llm-kit), accessed 2026-08-20.
- [Maestri introduction](https://www.themaestri.app/en/docs/intro), [canvas](https://www.themaestri.app/en/docs/canvas), [notes](https://www.themaestri.app/en/docs/notes), and [Maestro mode](https://www.themaestri.app/en/docs/maestro), accessed 2026-08-20.
- [Orca repository](https://github.com/stablyai/orca), [orchestration guide](https://github.com/stablyai/orca/blob/main/skill-guides/orchestration.md), [Agent Map view](https://github.com/stablyai/orca/blob/main/src/renderer/src/components/dashboard-popout/AgentDashboardMapView.tsx), [Agent Map layout](https://github.com/stablyai/orca/blob/main/src/renderer/src/components/dashboard-popout/agent-map-layout.ts), [dashboard snapshot contract](https://github.com/stablyai/orca/blob/main/src/shared/dashboard-snapshot.ts), [dashboard snapshot builder](https://github.com/stablyai/orca/blob/main/src/renderer/src/components/dashboard/build-dashboard-snapshot.ts), [package metadata](https://github.com/stablyai/orca/blob/main/package.json), and [license](https://github.com/stablyai/orca/blob/main/LICENSE), accessed 2026-08-20.
- [open-maestri](https://github.com/zlh-428/open-maestri), [termcanvas](https://github.com/lout33/termcanvas), [RondoFlow](https://github.com/rondoflow/rondoflow), [Agent Canvas](https://github.com/TheSaiEaranti/agent-canvas), [Cognograph](https://github.com/skovalik/cognograph), and [Kudosflow](https://github.com/akudo7/kudosflow), accessed 2026-08-20.
- [React Flow package metadata](https://github.com/xyflow/xyflow/blob/main/packages/react/package.json), accessed 2026-08-20.

## Trial by fire

- Primary-source claims: passed. Every adopted claim was checked against official docs, source, repository metadata, or license text.
- Secondary-only claims: none adopted.
- Volatile claims: Orca implementation details are pinned in the provider trail to source commit `6e25a90085970498c772490d0659bf258ed18c17`, inspected 2026-08-20. The installed UI itself remained visually unobserved because computer-use screen capture was unavailable; no screenshot-based claim is made.
- Falsifier check: passed. The proposed view replays durable state, keeps report and evidence grade separate, preserves Orca as the runtime, and does not require incorporating code under an incompatible license.
