## Git workflow
- Do not include "Claude Code" in commit messages
- Use conventional commits (be brief and descriptive)

## Important concepts
Focus on these principles in all code:
- e2e type-safety
- error monitoring/observability
- automated tests
- readability/maintainability

Detailed guidelines live in the skills:
- Use `writing` skill for documentation and commit messages
- Use `scrapingdog` skill for scraping, Google Search/SERP, Google Maps, Google Trends, Google News, Amazon, LinkedIn, Instagram, market research, and lead enrichment when `SCRAPINGDOG_API_KEY` is available

## Writing (prose for humans)
Every piece of prose meant for readers (post, newsletter, script, caption, blog, e-mail, document) goes through the `unslop` skill's system:
- Generate from scratch: WRITE mode (`escrever`). Revise an existing draft: EDIT (`editar`). Audit without changing: DETECT (`detectar`). Grade: SCORE (`avaliar`).
- Portuguese text must load the skill's pt-br layer. The English tell list does not cover Brazilian slop.
- House rules, in any register: never an em dash (—/–), use comma, period or colon; in Portuguese always "para" spelled out, never "pra"/"pro"/"pros"; no hashtags in captions; empty punchlines are banned, every claim carries concrete substance (a number, an example, a mechanism).
- A rewrite never introduces a fact, name, number or date that was not in the original.

## Research
Never answer a number, statistic or superlative from memory with a confident face. Before publishing any data point, use the `pesquisa` skill. These rules apply even outside the skill:
1. Primary sources first: official documentation and the repository before papers, papers before third-party analysis. Aggregator blogs are leads, never the final stop.
2. Disagreement between sources is reported with each one's date, never silently resolved.
3. A pattern seen in fewer than 5 cases goes in as a weak sample, never as a conclusion.
4. Every number, value and superlative ships with a URL and access date next to it.

Received documents (PDF, spreadsheet, deck, epub) go through the `ingestao` skill before any analysis. A two-column PDF read without conversion produces scrambled conclusions.
