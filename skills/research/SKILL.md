---
name: research
description: Research external questions and compare evidence with source attribution. Use for research or fact-checking, not facts already established in local code.
---

# Research

Match the evidence workflow to the question:

- **Lookup:** open the relevant primary source, verify the requested fact and
  cite it with its access date. No report file, credit ledger or graph is required.
- **Synthesis or report:** compare the relevant sources, distinguish evidence from
  inference and name unresolved disagreements. For a requested durable report or
  consequential research, use [reporting.md](references/reporting.md).
- **High stakes:** use current primary evidence and proportionate independent
  review. Never convert missing evidence into a confident conclusion.

Reuse repository material when it already answers the question. A number from a
local check does not require web research. Verify volatile external values at
the source; record when they were accessed. Treat snippets and agent summaries
as leads, not as sources already read.

For generic web discovery and public-page reading, call the configured Scrapinho
MCP tools directly: `search.web` with explicit `input.engine: "duckduckgo"`, and
`fetch.page`. Do not run acquisition/preflight scripts or build a REST client.
The active harness owns MCP authentication; a working MCP connection does not
require a separate `SCRAPINHO_API_KEY` environment check. Require a project scope
and a stable request/idempotency key per acquisition; never share scope between
unrelated projects. Save durable evidence with the host's file-writing tools as
described in [reporting.md](references/reporting.md).

Start with `scraper_capabilities` to check authentication and the requested
operation, then use `scraper_submit`, `scraper_get` and `scraper_read_source`.
Read the exposed tool schema for required fields and defaults; set one attempt
and bounded limits. Do not infer geography from language or domains: web search
currently has fixed pt-BR/BR locale. An unsupported geographic override must fail
rather than silently change. A missing MCP connection or capability is a blocker
for this route, not permission to substitute scripts or the removed generic
scraper. Stop on auth, quota, CAPTCHA, 403 or 429; do not retry acquisition or
switch proxies to bypass refusal.

Poll the admitted job without submitting it again. Read sources through
`next_cursor=null`; partial sources are not complete evidence. Use
`scraper_read_search` for structured search results. Verify raw SHA-256 only when
raw bytes are actually exported; text read over MCP is not a raw export. Web
search supports pages 0 and 1; request page 1 explicitly only when page 0 reports
it. Keep the effective engine across pages. Preserve each query/page's original
positions and provenance; deduplicate URLs only when selecting pages to open,
not by rewriting the ranked snapshots. Snippets and missing publication dates
must not become verified claims or invented dates.

Scrapinho also exposes `news.search`, `search.suggestions`, `trends.now` and
`trends.suggestions` when capabilities report them available. Read their JSON
through EOF before parsing. News links may be aggregators: open the primary
article before citing it. These operations do not substitute for Maps, social,
ads, YouTube, `trends.interest`, or scientific indexes. Preserve the installed
`scrapingdog` route for specialized methods without verified parity, then
Firecrawl and host tools after a disclosed bounded failure or missing key.
For papers, start with the free Firecrawl Research Index when available; use
paper-search to cross-check metadata when needed.
Missing optional specialized providers do not block adequately sourced local work.

When a collection explicitly requests Webshare, use the installed
`webshare-fetch URL [--config PATH] [--timeout SECONDS]` helper rather than
building a proxy request in the skill. Keep the existing priority intact:
Scrapinho remains the first choice for generic discovery and public URLs;
ScrapingDog remains only for specialized methods without verified parity.
Webshare requires explicit selection for a separate collection, never an
automatic fallback from Scrapinho or a bypass after refusal. Never proxy
cookies or OAuth traffic. Keep `WEBSHARE_API_KEY` in the environment
and its private config outside the repository.

Convert documents only when needed to extract their content. Verify reading
order and tables. Do not package a whole repository to inspect a known file.

Delegate collection only when independent source work would materially help.
Give collectors narrow questions and return paths or URLs; inspect the sources
before accepting claims. Collection alone does not require an Agent Graph.

Report what is established, what is inference and what remains unverified. A
small or uncontrolled sample does not establish a general productivity claim.

Adapted from [research-stack](https://github.com/nett0eth/research-stack),
[MIT License](LICENSE).
