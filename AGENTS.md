Shared instructions for any coding agent (Claude Code, Codex, OpenCode, Gemini CLI, Copilot CLI) running on this machine.

## Skills
Reusable skills live in `~/.agents/skills/`, the cross-agent convention. Each is a directory holding a `SKILL.md` (YAML frontmatter: `name`, `description`) plus optional reference files. When a task matches a skill's description, read that `SKILL.md` and follow it.

## Git workflow
- Never name the agent in a commit message (no "Claude Code", no "Codex", no co-author trailer)
- Use conventional commits (be brief and descriptive)

## Important concepts
Focus on these principles in all code:
- e2e type-safety
- error monitoring/observability
- automated tests
- readability/maintainability

## Resource discipline
The machine-wide `agent-resource-guard` keeps concurrent agent work below a safe budget.

- Before spawning subagents, run `agent-resource-guard check --intent agent --demand <count> --prune`. Exit code 75 means no capacity. Reduce the batch, work locally, or wait for an existing worker. Never bypass a denial by launching another terminal.
- Before a build, typecheck, test suite, browser run, or development server, run `agent-resource-guard check --intent heavy --prune`. Do not start the command when capacity is denied.
- The global default admits up to 20 active agent sessions. Memory and heavy-command limits can still deny work earlier.
- Keep no more than two subagents active from one root agent. Global capacity may be lower.
- Never run the same build or typecheck concurrently in one worktree. Reuse an active development server instead of starting another.
- Stop every background command when its task ends. Cancellation must terminate the full child process tree.
- After a crash or resumed session, inspect existing work before restarting commands. Do not restore interrupted builds, tests, browsers, or development servers automatically.
- The periodic guard removes stale workloads tagged with an exited session. When the machine is over budget, it also closes the oldest agent sessions after 30 idle minutes. It does not kill untagged manual processes or terminal shells.
- Under critical memory pressure, the guard stops the largest agent tree before the desktop session reaches the system OOM killer.

## Scope discipline
Default assumption: a project has no external users, no live data and no paying client. Under that assumption:
- Do not preserve backward compatibility. Delete the obsolete path instead of adding a compat layer, a fallback or a migration.
- Choose the simplest implementation that fully meets the current requirement. No speculative abstraction, configuration or indirection.
- Grow in layers. Smallest version that works end to end first, each new capability on top of something that already works. Never trade a working product for unfinished complexity.
- Lean on dependencies already in the project before writing your own or adding a package. Check the library's docs and types before assuming a capability is missing.
- Architectural decisions are long-term. No stopgap that only works for now and is meant to be replaced later.

When the project is live (real users, paying client, production data) or the ask implies it, say so in one line and ask whether backward compatibility is required before removing anything. The rest of the rules still hold.

Detailed guidelines live in the skills:
- Use `writing` skill for documentation and commit messages
- ScrapingDog is the primary paid provider for live public web data. When `SCRAPINGDOG_API_KEY` is available, use the `scrapingdog` skill and attempt its dedicated endpoint before Firecrawl, native web search or a generic scraper.
- Never fall back from ScrapingDog silently. If the key is missing or a bounded attempt fails, record the exact reason, then use Firecrawl. Native web search remains the last fallback.

## Testing

- Test behavior, never implementation.
- Name tests with a third-person verb, never "should".
- Every bug fix ships with a test that fails without the fix.
- Segment the test file by feature behavior with `describe` clauses.

## Frontend visual validation

Every change that affects rendered UI must be inspected in the running application with a vision-capable tool. Unit tests, DOM snapshots, accessibility trees and successful builds do not replace visual inspection.

- Cover every changed route or component in each changed state, including loading, empty, error, populated and interactive states when applicable.
- Capture controlled desktop and mobile viewports unless the product has a documented single-viewport target.
- Inspect every screenshot with `view_image` or `computer-use`. Record concrete observations about layout, clipping, overflow, hierarchy, typography and state correctness.
- Store PNG evidence and its manifest under `.visual-evidence/<change>/`. Do not declare the work complete while any expected surface is missing or failed.
- OpenSpec frontend tasks must contain `Visual:` lines using `<id> | <route-or-component> | <width>x<height> | <state>`. The `impl` state blocks a passing grade without a matching vision-reviewed manifest.
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
