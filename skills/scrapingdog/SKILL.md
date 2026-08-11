---
name: scrapingdog
description: "Default paid provider for live public web data: scraping, rotating proxies, Google (Search, Maps, News, Trends, Shopping, Images, Flights, Jobs, Scholar), YouTube, TikTok, X, Instagram, LinkedIn, Amazon and marketplaces. use_when: SCRAPINGDOG_API_KEY exists and the task needs live web data, SERP, transcript, review mining, lead enrichment or price monitoring. do_not_use_when: the data is already local or the site needs an authenticated session."
---

# ScrapingDog

81 endpoints under one key. The failure mode is not knowing they exist and falling back to `/scrape` or a web search, which costs more and returns worse data. Route by intent first, generic scrape last.

## Provider priority

ScrapingDog is the kit's primary paid provider for live public web data. When
`SCRAPINGDOG_API_KEY` exists, a task must attempt the matching ScrapingDog
endpoint before Firecrawl, native web search or another scraper.

Use the `scrapingdog` MCP server first. Select the matching tool from its live
tool catalog and call it directly. This keeps API-key injection, URL building,
timeouts and response handling outside task code. Do not write a new HTTP call
when the MCP already exposes the endpoint.

Fallback is explicit. If the key is absent, state that in the work log. If a
request fails, make only the bounded retry allowed by the status code, record
the failure, then use an existing project helper or the HTTP fallback below.
Use Firecrawl only after the ScrapingDog paths fail. Never expose the key or
repeat an invalid credential.

## First Checks

1. Run `scripts/key-env-check.sh`. Never conclude that `SCRAPINGDOG_API_KEY` is missing from one non-interactive environment check.
   - `current`: use the current shell.
   - `interactive`: the key exists in shell startup files. Run ScrapingDog calls inside `bash -ic '...'` so that shell loads the key.
   - `missing`: only then record the key as absent and follow the fallback policy.
2. Never print, grep, copy, persist or hardcode the key. The checker reports only where the key became available, never its value.
3. Inspect the `scrapingdog` MCP tool catalog and use its dedicated tool when present. Tool names use snake case, such as `google_search`, `youtube_search` and `web_scrape`.
4. If the MCP lacks the endpoint, reuse the project's existing ScrapingDog helper. Write a direct HTTP call only when neither path exists.
5. Generic `web_scrape` or `/scrape` is the last resort, not the default.
6. For an HTTP fallback, build the query with `URLSearchParams` or a params object, never string concatenation.
7. Timeout around 60s (120s for `/chatgpt` and `/google/ai_mode`).
8. Before a batch job, check remaining credits through a local redacting helper. Never place the raw `/account` response in model context because it may echo credentials.

## Routing Table

Credits per successful request, taken from the official docs. `?` means the doc page does not state it; check `/account` before a batch.

| Intent | Endpoint | Cred |
|---|---|---|
| Generic page, JS rendered | `/scrape` (default `dynamic=true`) | 5 |
| Generic page, static HTML | `/scrape?dynamic=false` | 1 |
| Page behind Cloudflare | `/scrape?stealth_mode=true` | 10 |
| Proxy for Playwright/Puppeteer/any HTTP client | `proxy.scrapingdog.com:8081` | see doc |
| Page screenshot | `/screenshot` | 5 |
| Google organic SERP, dorks, rank check | `/google` | 5 |
| Is my brand cited by Google AI | `/google/ai_overview` | 5 |
| Google AI Mode answer + cited sources | `/google/ai_mode` | 10 |
| Is my brand cited by ChatGPT | `/chatgpt` | 30 |
| Long-tail keyword ideas | `/google_autocomplete` | ? |
| Search demand, seasonality, comparison | `/google_trends` | 5 |
| What is hot right now | `/google_trends/trending_now` | ? |
| Trend term suggestions | `/google_trends/autocomplete` | ? |
| News monitoring, brand mentions | `/google_news`, `/google_news/v2` | 5 |
| Local businesses, phone, site, rating | `/google_maps` | ? |
| Place details by place_id | `/google_maps/places` | ? |
| Review mining, voice of customer | `/google_maps/reviews` | ? |
| Place photos / posts | `/google_maps/photos`, `/google_maps/posts` | ? |
| Local pack results | `/google_local` | 5 |
| Yelp businesses | `/yelp/search` | 4 |
| Product prices across stores | `/google_shopping` | 10 |
| One product, variants and sellers | `/google_immersive_product` | ? |
| **Flight prices, routes, airlines** | `/google_flights` | 5 |
| **Hotel prices and availability** | `/google_hotels` | 5 |
| Stock, ticker, market data | `/google_finance` | ? |
| Job market, salaries, hiring signal | `/google_jobs` | 5 |
| Indeed listings | `/indeed` | 1 |
| Real estate listings | `/zillow` | 2 |
| Image search / visual reference | `/google_images` | 10 |
| Video results / Shorts | `/google_videos`, `/google_shorts` | 5 / ? |
| Reverse image, find similar product | `/google_lens` | 5 |
| Competitor ad creatives on Google | `/google/ads_transparency` | 5 |
| Academic papers, citations | `/google_scholar` (+ `/profiles`, `/author`, `/cite`) | 5 |
| Patents | `/google_patents`, `/google_patents/details` | 5 |
| Bing / DuckDuckGo / Baidu SERP | `/bing/search`, `/duckduckgo/search`, `/baidu/search` | 5 |
| Several engines at once | `/search` | 20 |
| **YouTube transcript of a video** | `/youtube/transcripts` | 1 |
| YouTube search / video / channel / comments | `/youtube/search`, `/youtube/video`, `/youtube/channel`, `/youtube/comments` | 5 |
| TikTok profile / post / ad library | `/tiktok/profile`, `/tiktok/post`, `/tiktok/ads` | 5 |
| X profile / post | `/x/profile`, `/x/post` | 5 |
| Instagram profile | `/instagram` | ? |
| Facebook | `/facebook` | ? |
| LinkedIn company | `/profile?type=company` | 10 |
| LinkedIn person | `/profile?type=person` | 50-100 |
| LinkedIn post | `/profile/post` | 5 |
| LinkedIn jobs | `/jobs` | 5 |
| Amazon product / search | `/amazon/product`, `/amazon/search` | 1 |
| Amazon offers / reviews / autocomplete | `/amazon/offers`, `/amazon/reviews`, `/amazon/autocomplete` | ? / 5 / 5 |
| Walmart, eBay, Flipkart, Myntra, Apple | see `references/commerce-travel.md` | 5 |
| Credits and concurrency left | `/account` | ? |

Two entries deserve a second look before you fire them: `/profile?type=person` at up to 100 credits, and `/chatgpt` at 30. Everything else is cheap enough to use freely.

Instagram and Facebook doc pages are stubs that only publish the endpoint, no parameters. Smoke test them before wiring into production.

Amazon Reviews is flagged in the docs as temporarily unavailable because Amazon moved reviews behind a login wall.

## Reference Files

Read only the family you need:

- `references/core-tools.md`: `/scrape` full parameter and cost matrix, screenshot, rotating proxies, `/account`, universal search, webhook
- `references/google-serp.md`: Search, AI Mode, AI Overview, autocomplete, Ads Transparency, ChatGPT, Trends, News, Bing/DDG/Baidu
- `references/local-maps.md`: Maps family, Local, Yelp, Zillow
- `references/social-video.md`: YouTube, TikTok, X, Instagram, Facebook, Google Images/Videos/Shorts/Lens
- `references/commerce-travel.md`: Shopping, Flights, Hotels, Finance, Amazon, Walmart, eBay, Flipkart, Myntra, Apple
- `references/b2b-research.md`: LinkedIn, jobs, Scholar, Patents

Those files were extracted from `https://www.scrapingdog.com/documentation/` on 2026-08-05. Docs move: verify against the live page before changing a production integration or quoting an exact price.

## Cost And Reliability Rules

- `/scrape` renders JavaScript by default. Always send `dynamic` explicitly; `dynamic=false` is 1 credit instead of 5.
- `410` is ScrapingDog timing out after its internal retry window. Retryable, treat as unbilled.
- `429` is concurrency pressure. Back off with jitter and cut in-flight requests.
- Failed requests are not charged, per the pricing page. Successful `200` responses are, so avoid blind URL floods.
- Concurrency is per plan: Lite 5, Standard 50, Pro 100. Verify the active plan before batch jobs.
- Amazon reviews and any high-cost endpoint: single concurrency, cache aggressively.
- Cap calls per lead in enrichment. One SERP plus at most two scrapes, Firecrawl only as fallback.
- `session_number` reuses the same IP across requests, free, expires 60s after last use.

## HTTP Fallback Pattern

Use this only when the MCP tool catalog and the project's existing helpers do
not cover the required endpoint.

```ts
const baseUrl = "https://api.scrapingdog.com";

async function scrapingdogGetJson<T>(
  path: string,
  params: Record<string, string | number | boolean | undefined>,
  signal?: AbortSignal,
): Promise<T> {
  const apiKey = process.env.SCRAPINGDOG_API_KEY;
  if (!apiKey) throw new Error("missing_scrapingdog_api_key");

  const qs = new URLSearchParams({ api_key: apiKey });
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) qs.set(key, String(value));
  }

  const res = await fetch(`${baseUrl}${path}?${qs}`, { signal });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`scrapingdog_http_${res.status}: ${body.slice(0, 200)}`);
  }
  return (await res.json()) as T;
}
```

## Proxy Mode

When a task needs a real browser (Playwright, Puppeteer, Selenium) instead of the REST API, route the browser through the rotating proxy. Same backend, same key.

```
http://scrapingdog:<API_KEY>@proxy.scrapingdog.com:8081
```

The docs require disabling SSL verification and using `http://` for the target URL. In Playwright: `browser.launch({ proxy: { server: "http://proxy.scrapingdog.com:8081", username: "scrapingdog", password: key } })` with `ignoreHTTPSErrors: true` on the context.
