---
name: scrapingdog
description: Use this whenever a task needs web scraping, SERP/search results, Google Maps business data, Google Trends, Google News/news monitoring, Amazon product/review data, LinkedIn/company/profile/job data, Instagram profile data, or a cheaper fallback to Firecrawl/Serper/Google Places. Prefer ScrapingDog when SCRAPINGDOG_API_KEY is available, especially for prospecting, market research, lead enrichment, competitor monitoring, ecommerce scraping, and structured search extraction.
---

# ScrapingDog

Use ScrapingDog as the default paid scraping provider when the task asks for data extraction from public webpages, Google, Google Maps, Google Trends, Google News, Amazon, LinkedIn, Instagram, or similar structured targets.

## First Checks

1. Check `SCRAPINGDOG_API_KEY` in the environment. Do not hardcode the key in source files, markdown, logs, or examples.
2. If working inside Prospecta, inspect/reuse `src/lib/scrapingdog-client.ts` before writing a new client.
3. Prefer a dedicated structured endpoint over generic `/scrape`; it returns parsed JSON and usually costs fewer credits for the same result.
4. Use `URLSearchParams` or an HTTP client params object. Do not concatenate query strings by hand.
5. Set request timeout to about 60 seconds. ScrapingDog can retry internally up to that window.

## Retrieval

Your stored knowledge can drift. Before changing production integrations or citing exact parameters/prices, verify the official docs:

- Main docs: `https://docs.scrapingdog.com/`
- Web scraping: `https://docs.scrapingdog.com/web-scraping-api`
- Google Search: `https://docs.scrapingdog.com/google-search-scraper-api`
- Google Maps: `https://docs.scrapingdog.com/google-maps-api`
- Google Trends: `https://docs.scrapingdog.com/google-trends-api`
- Google News: `https://docs.scrapingdog.com/google-news-scraper-apis`
- LinkedIn/company/profile: `https://docs.scrapingdog.com/linkedin-scraper-api/company-profile-scraper`
- Amazon: `https://docs.scrapingdog.com/amazon-scraper-api/amazon-offers-api`

If you need an implementation cheat sheet, read `references/endpoints.md`.

## Endpoint Selection

Use this decision order:

1. Need normal webpage HTML/text: `/scrape`.
2. Need Google organic results, dorks, or URLs for enrichment: `/google`.
3. Need local businesses, phones, websites, ratings, coordinates, reviews/photos/posts links: `/google_maps`.
4. Need search demand, seasonality, trend comparison, or what is rising now: `/google_trends`, `/google_trends/autocomplete`, or `/google_trends/trending_now`.
5. Need news monitoring or brand mentions in news: `/google_news`.
6. Need Amazon product/offers/reviews: Amazon dedicated endpoints.
7. Need LinkedIn company/profile/jobs: `/profile` or `/jobs`.
8. Need Instagram profile enrichment: use the official Instagram endpoint if verified in current docs; otherwise follow the Prospecta pattern only after testing behind a feature flag.

## Cost And Reliability Rules

- `410` means ScrapingDog timed out after its internal retry window; it is safe to retry and should not be treated as charged work.
- `429` means concurrency/rate pressure; back off with jitter and reduce in-flight requests.
- Successful `200` responses are charged. Docs also note `404` may count as a completed request, so avoid blind URL floods.
- Keep concurrency below the active plan limit. Prospecta used Lite as 5 concurrent and Standard as materially higher; verify the active plan before batch jobs.
- For Amazon reviews, use low/single concurrency because the endpoint is less consistent.
- For lead enrichment, cap calls per lead. Prospecta's pattern is one SERP plus up to two scrape calls, with Firecrawl/Alterlab only as fallback.

## TypeScript Pattern

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


