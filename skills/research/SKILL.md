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

For known public URLs, use Scrapinho when configured: check
`scraper_capabilities`, submit `fetch.page`, poll the returned job, then read the
source through EOF. Use static acquisition unless rendering is needed; partial
sources do not prove complete content. For durable snapshots, use the collector
described in [reporting.md](references/reporting.md). After a bounded failure or
missing Scrapinho access, record why and use Firecrawl, then host tools.

Search and specialized methods without verified Scrapinho parity still use the
installed `scrapingdog` skill when keyed, then Firecrawl and host search after a
bounded failure or missing key. Do not infer search, transcript or social coverage
from `fetch.page`. For a known official document, direct reading is sufficient. For papers,
start with the free Firecrawl Research Index when available; use paper-search to
cross-check metadata when needed. Missing optional providers do not block local
work that already has adequate evidence.

Convert documents only when needed to extract their content. Verify reading
order and tables. Do not package a whole repository to inspect a known file.

Delegate collection only when independent source work would materially help.
Give collectors narrow questions and return paths or URLs; inspect the sources
before accepting claims. Collection alone does not require an Agent Graph.

Report what is established, what is inference and what remains unverified. A
small or uncontrolled sample does not establish a general productivity claim.

Adapted from [research-stack](https://github.com/nett0eth/research-stack), MIT.
