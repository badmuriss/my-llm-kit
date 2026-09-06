---
name: scrapingdog
description: Collect live public web data through ScrapingDog when an API key is available. Use for search, scraping and dedicated public-data endpoints.
---

# ScrapingDog

Resolve this skill directory before running its `scripts/key-env-check.sh`.
The checker reports whether the key is available in the current or interactive
shell without printing it. Never expose a key, raw account response or
credential-bearing request URL.

Inspect the available MCP tools and select the dedicated endpoint for the task.
Use an existing HTTP helper when the endpoint is not exposed by MCP. Read only
the relevant endpoint family below. Generic scraping is for pages that have no
more appropriate dedicated endpoint; send the rendering mode explicitly.

For paid batches, use `scripts/account_summary.sh` before and after collection.
Respect an explicit budget. Bound retries and concurrency, cache useful results,
and record failures. After a missing key or bounded provider failure, disclose
the reason before using Firecrawl or host search. Do not submit private or
session-authenticated content to a public scraping provider.

- [endpoint-index.md](references/endpoint-index.md): choose an endpoint when the
  family is unclear; historical costs are not current price evidence.
- [core-tools.md](references/core-tools.md): static/dynamic pages, account and proxy.
- [google-serp.md](references/google-serp.md): search, news, trends and search answers.
- [local-maps.md](references/local-maps.md): places, reviews and local businesses.
- [social-video.md](references/social-video.md): public social data and transcripts.
- [commerce-travel.md](references/commerce-travel.md): products, travel and marketplaces.
- [b2b-research.md](references/b2b-research.md): jobs, company data and Scholar.

Use parameter objects or URL encoding for HTTP queries, a bounded timeout and
sanitized errors. Do not print arbitrary error bodies that may echo credentials.
Direct known official sources and local evidence need no proxy when they already
provide the requested information.
