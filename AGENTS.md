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
- Use `scrapingdog` skill for scraping, Google Search/SERP, Google Maps, Google Trends, Google News, Amazon, LinkedIn, Instagram, market research, and lead enrichment when `SCRAPINGDOG_API_KEY` is available

## Testing

- Test behavior, never implementation.
- Name tests with a third-person verb, never "should".
- Every bug fix ships with a test that fails without the fix.
- Segment the test file by feature behavior with `describe` clauses.

## Writing (prose for humans)
Every piece of prose meant for readers (post, newsletter, script, caption, blog, e-mail, document) goes through the `unslop` skill's system:
- Generate from scratch: WRITE mode (`escrever`). Revise an existing draft: EDIT (`editar`). Audit without changing: DETECT (`detectar`). Grade: SCORE (`avaliar`).
- Portuguese text must load the skill's pt-br layer. The English tell list does not cover Brazilian slop.
- House rules, in any register: never an em dash (—/–), use comma, period or colon; in Portuguese always "para" spelled out, never "pra"/"pro"/"pros"; no hashtags in captions; empty punchlines are banned, every claim carries concrete substance (a number, an example, a mechanism).
- A rewrite never introduces a fact, name, number or date that was not in the original.

## Research
Never answer a number, statistic or superlative from memory with a confident face. Before publishing any data point, use the `research` skill. These rules apply even outside the skill:
1. Primary sources first: official documentation and the repository before papers, papers before third-party analysis. Aggregator blogs are leads, never the final stop.
2. Disagreement between sources is reported with each one's date, never silently resolved.
3. A pattern seen in fewer than 5 cases goes in as a weak sample, never as a conclusion.
4. Every number, value and superlative ships with a URL and access date next to it.

Received documents (PDF, spreadsheet, deck, epub) go through the `ingest` skill before any analysis. A two-column PDF read without conversion produces scrambled conclusions.
