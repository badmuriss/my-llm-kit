Shared instructions for any coding agent (Claude Code, Codex, OpenCode, Gemini CLI, Copilot CLI) running on this machine.

## Skills
Reusable skills live in `~/.agents/skills/`, the cross-agent convention. Each is a directory holding a `SKILL.md` (YAML frontmatter: `name`, `description`) plus optional reference files. When a task matches a skill's description, read that `SKILL.md` and follow it.

## OpenCode delegation
Subagents are defined globally in `~/.config/opencode/agent/*.md` with an explicit `model` + `variant` (reasoning effort). Pick by cost tier, strongest model only where it pays:

| Agent | Model | Effort | Use for |
|---|---|---|---|
| `deep-reasoner` | `opencode-go/deepseek-v4-pro` | high | architecture, hard debugging, tradeoff analysis |
| `builder` | `opencode-go/deepseek-v4-pro` | high | multi-file features, tricky migrations |
| `frontend-expert` | `opencode-go/kimi-k3` | high | UI/frontend polish only (K3 tops Frontend Code Arena; also the priciest model on the provider) |
| `fast-worker` | `opencode-go/deepseek-v4-flash` | low | boilerplate, tests, mechanical edits |
| `cheap-worker` | `opencode-go/glm-5.3-flash` | — | fan-out grunt work, throwaway scripts |

Effort is set via custom variants in `~/.config/opencode/opencode.json` (`provider.opencode-go.models.<id>.variants`). Do not delegate a premium model to mechanical work.

## Codex delegation
Use the smallest model and effort that safely fit the task. The default ladder is:

| Model | Preferred effort | Use for |
|---|---|---|
| `gpt-5.6-luna` | high, xhigh | mechanical edits, narrow checks, high-volume work |
| `gpt-5.6-terra` | medium, high | everyday implementation, multi-file work |
| `gpt-5.6-sol` | high, xhigh | demanding implementation, review, risky analysis |
| `gpt-6-astra` | high, xhigh | frontier coordination, architecture, hardest end-to-end work |

Do not place Astra `max` in default routing because its reasoning budget is too costly for routine use. Keep it available only as a bounded exceptional override with an explicit reason. Do not raise effort merely because a newer model exists. When migrating an existing workload to Astra, preserve its effective effort, then use the table above for new work. Source: [official model comparison](https://developers.openai.com/api/docs/models/compare) and [Astra migration guide](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-6-astra), accessed 2026-09-04.


## Git workflow
- Never name the agent in a commit message (no "Claude Code", no "Codex", no co-author trailer)
- Use conventional commits (be brief and descriptive)

## Important concepts
Focus on these principles in all code:
- e2e type-safety
- error monitoring/observability
- risk-proportional validation
- readability/maintainability

## Resource discipline
Resource management is capability-driven and operating-system aware. `agent-resource-guard` is an optional Linux enhancement, never a prerequisite for normal harness work.

- Do not invoke the guard for a routine single worker, build, browser run or test command. Before unusually high fan-out or overlapping heavy commands, check whether `agent-resource-guard` exists. If it does, use the matching `check --intent agent --demand <count> --prune` or `check --intent heavy --prune` command and honor exit code 75. If it does not exist, continue without treating that as an error.
- On Linux, the optional guard may provide machine-wide admission and stale-workload cleanup. On macOS and Windows, do not expect it; use the host's own process controls and reduce concurrency only when observed memory, load or responsiveness calls for it.
- The harness imposes no fixed subagent count. Start with the smallest useful fan-out, obey the active host or tool's own concurrency limit, and add workers only when the tasks are genuinely independent.
- Never run the same build or typecheck concurrently in one worktree. Reuse an active development server instead of starting another.
- Stop every background command when its task ends. Cancellation must terminate the full child process tree.
- After a crash or resumed session, inspect existing work before restarting commands. Do not restore interrupted builds, tests, browsers, or development servers automatically.

## Scope discipline
Default assumption: a project is an MVP with no external users, live data or paying client. Under that assumption:
- Prefer a clean breaking change or a focused rewrite. Delete the obsolete path instead of adding a migration, adapter, compatibility layer, deprecated alias, dual read/write, feature flag or fallback.
- Do not preserve an old API, schema, default or behavior unless the repository contains evidence that an active consumer still needs it.
- Choose the simplest implementation that fully meets the current requirement. No speculative abstraction, configuration or indirection.
- Grow in layers. Smallest version that works end to end first, each new capability on top of something that already works. Never trade a working product for unfinished complexity.
- Lean on dependencies already in the project before writing your own or adding a package. Check the library's docs and types before assuming a capability is missing.
- Architectural decisions are long-term. No stopgap that only works for now and is meant to be replaced later.

When the project is live (real users, paying client, production data) or the repository shows an active external contract, say so in one line and ask whether backward compatibility is required before removing it. Do not ask for an MVP or local tool without such evidence.

Detailed guidelines live in the skills:
- Use `writing` skill for documentation and commit messages
- Use the free Firecrawl Research Index first for scientific literature discovery,
  passage lookup and citation expansion. Use `paper-search` to cross-check metadata,
  then ScrapingDog Google Scholar when the free routes are insufficient.
- ScrapingDog is the primary paid provider for live public web data. When `SCRAPINGDOG_API_KEY` is available, use the `scrapingdog` skill and attempt its dedicated endpoint before Firecrawl, native web search or a generic scraper.
- Never fall back from ScrapingDog silently. If the key is missing or a bounded attempt fails, record the exact reason, then use Firecrawl. Native web search remains the last fallback.

## Testing

- Do not add a test by default. First choose the cheapest evidence that can catch a realistic failure.
- Add a test when the user asks for one, when fixing a reproducible bug likely to recur, or when changing non-trivial branching, invariants, security, data integrity or a public contract.
- Do not add a test only to pin a constant, default value, configuration toggle, removed behavior, trivial passthrough, type-system guarantee or implementation detail.
- Prefer the smallest relevant existing check. Run a full suite only for broad or risky changes, releases, or when repository instructions require it.
- Keep the case set minimal. Add boundary cases only when the boundary carries a plausible distinct failure.
- Test behavior, never implementation.
- Name tests with a third-person verb, never "should".
- A regression test must fail on the known-bad behavior without the fix. If reproducing it in a test would cost more than its recurrence risk, record direct validation instead.
- Segment the test file by feature behavior with `describe` clauses.

## Frontend visual validation

Every change that affects rendered UI must be inspected in the running application with a vision-capable tool. Unit tests, DOM snapshots, accessibility trees and successful builds do not replace visual inspection.

- Cover every changed route or component in each changed state, including loading, empty, error, populated and interactive states when applicable.
- Load the `frontend-visual-validation` skill. Declare the platforms that each changed surface and state actually supports, with a concrete reason, then capture every declared platform.
- Inspect every screenshot with `view_image` or `computer-use`. Record concrete observations about layout, clipping, overflow, hierarchy, typography and state correctness.
- Store PNG evidence and its manifest under `.visual-evidence/<change>/`. Do not declare the work complete while any expected surface is missing or failed.
- OpenSpec frontend tasks must pair `Visual-Scope: <route-or-component> | <state> | <platforms> | <reason>` with `Visual: <id> | <route-or-component> | <platform> | <width>x<height> | <state>` lines. Use all canonical profiles for general responsive UI, only the supported profiles for platform-specific UI, and never omit a supported platform to avoid a failure. The `impl` state blocks mismatched scope or missing vision-reviewed evidence.
- If the environment cannot run the UI or provide vision, grade visual evidence `unobserved` or the task `blocked`. Never silently substitute a code-only check.

## Writing (authored prose deliverables only)
Use the `unslop` skill only when the requested deliverable is standalone prose meant for publication or direct human consumption, such as a post, newsletter, script, caption, blog, e-mail, document or marketing copy.

Do not invoke `unslop`, run its rubric or run its text eval for ordinary agent responses. This exclusion covers conversation, status updates, plans, technical answers, explanations, code-review findings, implementation summaries and handoffs. Apply `unslop` to one of those only when the user explicitly asks to rewrite, audit or grade that text.

For qualifying prose deliverables:
- Generate from scratch: WRITE mode (`escrever`). Revise an existing draft: EDIT (`editar`). Audit without changing: DETECT (`detectar`). Grade: SCORE (`avaliar`).
- Portuguese text must load the skill's pt-br layer. The English tell list does not cover Brazilian slop.
- House rules, in any register: never an em dash (—/–), use comma, period or colon; in Portuguese always "para" spelled out, never "pra"/"pro"/"pros"; no hashtags in captions; empty punchlines are banned, every claim carries concrete substance (a number, an example, a mechanism).
- A rewrite never introduces a fact, name, number or date that was not in the original.
- Run the rubric and text eval as internal quality gates. Do not append rubric scores or eval checklists to the delivered prose unless the user explicitly asks to see the assessment.

## Research
Never answer a number, statistic or superlative from memory with a confident face. Before publishing any data point, use the `research` skill. These rules apply even outside the skill:
1. Primary sources first: official documentation and the repository before papers, papers before third-party analysis. Aggregator blogs are leads, never the final stop.
2. Disagreement between sources is reported with each one's date, never silently resolved.
3. A pattern seen in fewer than 5 cases goes in as a weak sample, never as a conclusion.
4. Every number, value and superlative ships with a URL and access date next to it.

Received documents (PDF, spreadsheet, deck, epub) go through the `ingest` skill before any analysis. A two-column PDF read without conversion produces scrambled conclusions.
