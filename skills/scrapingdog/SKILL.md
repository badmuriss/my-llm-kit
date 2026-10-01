---
name: scrapingdog
description: Collect specialized public data through ScrapingDog when its configured route is selected. Use for Maps, social, commerce, jobs and other dedicated endpoints; generic web discovery and public-page acquisition belong to research.
---

# ScrapingDog

Resolve this skill directory before running its `scripts/key-env-check.sh`.
The checker reports whether the key is available in the current or interactive
shell without printing it. Never expose a key, raw account response or
credential-bearing request URL.

Use `research` and its configured Scrapinho MCP for generic web discovery and
public-page acquisition. This package owns specialized endpoints without
verified parity, not an automatic fallback from a refused request.
Inspect the available MCP tools and select the dedicated endpoint for the task.
Use an existing HTTP helper when that specialized endpoint is not exposed by MCP.
Read only the relevant endpoint family below; send rendering mode explicitly.

For paid batches, use `scripts/account_summary.sh` before and after collection.
Respect the user's selected scope and budget; a low price is not authorization.
Bound retries and concurrency, cache useful results, and record failures.
After a missing key or non-refusal provider failure, disclose the reason before
using an available specialized alternative. Stop on CAPTCHA, 403 or 429; do not
change tools, providers or proxies to bypass refusal. Do not submit private or
session-authenticated content to a public scraping provider.

Prompt-based `/chatgpt` and other external inference modes are not substitutes
for the configured subscription. Invoke them only when the user explicitly
authorizes that service and its costs; a configured key does not grant permission.

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
