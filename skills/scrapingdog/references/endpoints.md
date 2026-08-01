# ScrapingDog Endpoint Cheat Sheet

Base URL: `https://api.scrapingdog.com`

Authentication: send `api_key` as a query parameter on every request. Keep it in `SCRAPINGDOG_API_KEY`.

## Generic Web Scraping

Endpoint: `GET /scrape`

Use for arbitrary webpages when no dedicated structured endpoint exists.

Common params:

- `url` required: target URL.
- `dynamic`: JS rendering. Use `false` for static pages when possible; use `true` for SPAs/social pages.
- `country`: geotargeting when needed.

Notes:

- Prospecta converts returned HTML to plain text before field extraction.
- Avoid using generic scrape for Google, Maps, Trends, News, Amazon, and LinkedIn when a dedicated endpoint exists.

## Google Search

Endpoint: `GET /google`

Use for SERP, dorks, finding official websites/social URLs, SEO checks, and URL resolution.

Common params:

- `query` required.
- `country`: ISO-ish country selector, e.g. `br` or `us`.
- `domain`: Google domain, e.g. `google.com.br`.
- `results`: result count.
- `page`: result page/offset.
- `advance_search`: richer snippets; costs more.
- `mob_search`: mobile SERP; costs more.
- `html`: include raw HTML if needed.

Expected useful fields:

- `organic_results[]` with `title`, `link`, `snippet`/`description`.

Prospecta pattern:

- `country=br`
- `domain=google.com.br`
- `results` clamped to 1-20
- Map each hit to `{ url, title, description, snippet }`

## Google Maps

Endpoint: `GET /google_maps`

Use for local business prospecting and enrichment.

Common params:

- `query` required for search.
- `ll`: origin and zoom/height, e.g. `@-23.55052,-46.63331,14z`. Required for reliable pagination.
- `country`, `domain`, `language`.
- `page`: starts at `0`, then `20`, `40`, etc. Keep offsets sane; docs recommend staying around the first six pages.
- `place_id`, `data`, `type=place`: use for place details when current docs support it.

Expected useful fields in `search_results[]`:

- `title`, `place_id`, `data_id`, `data_cid`
- `address`, `phone`, `website`
- `rating`, `reviews`, `price`, `type`, `types`
- `gps_coordinates.latitude`, `gps_coordinates.longitude`
- `google_maps_url`, `reviews_link`, `photos_link`, `posts_link`
- `operating_hours`, `open_state`, `thumbnail`, `description`

Related endpoints from current docs:

- `/google_maps/reviews`
- `/google_maps/photos`
- `/google_maps/posts`

## Google Trends

Endpoint: `GET /google_trends`

Use for demand validation, seasonality, category comparison, topic research, and market timing.

Common params:

- `query`: one or more terms/topics. Multiple terms are comma-separated.
- `data_type`: `TIMESERIES`, `GEO_MAP`, or `GEO_MAP_0`.
- `geo`: location, e.g. `BR`, `US`, or blank worldwide.
- `region`: `COUNTRY`, `REGION`, `DMA`, or `CITY` where applicable.
- `date`: `now 7-d`, `today 3-m`, `today 12-m`, `today 5-y`, `all`, or a custom date range.
- `gprop`: web default, `images`, `news`, `froogle`, or `youtube`.
- `language`, `tz`, `cat`.

Related:

- `GET /google_trends/autocomplete` with `query`, optional `language`.
- `GET /google_trends/trending_now` with `geo`, optional `hours`.

## Google News

Endpoint: `GET /google_news`

Use for news monitoring, brand mentions, competitor monitoring, and recent-event research.

Common params:

- `query` required.
- `results`: 1-100.
- `country`: default `us`; use `br` for Brazil.
- `page`: starts at `0`.
- `domain`: e.g. `google.com.br`.

Expected useful fields:

- `news_results[]` with title/snippet/source/time/url/image fields.

## LinkedIn / Profile / Jobs

Company profile endpoint: `GET /profile`

Common params:

- `type=company`
- `id`: company slug from the LinkedIn company URL.

Jobs search endpoint: `GET /jobs`

Common params:

- `field`: job title or company name.
- `location` or `geoid`.
- `page`: starts at `1`.
- `sort_by`: `day`, `week`, or `month`.

Notes:

- LinkedIn profile scraping is expensive compared with SERP/Maps. Use it only when the specific profile/company fields are needed.
- For lead enrichment, first resolve LinkedIn URLs through `/google` dorks, then call LinkedIn/profile endpoints only for high-value leads.
- Keep LinkedIn scraping limited to public information and respect product/legal constraints in the target project.

## Instagram

Prospecta has a wrapper for `GET /instagram` with `profile=<username>`, mapping username, full name, bio, followers, following, post count, verification, external URL, and profile picture.

Before relying on this in a new project, verify the current official docs or run a tiny smoke test, because the public docs have changed over time. For generic social page text extraction, `/scrape?dynamic=true` remains the fallback.

## Amazon

Dedicated endpoints are preferable to `/scrape` for Amazon.

Offers endpoint: `GET /amazon/offers`

Common params:

- `domain`: Amazon TLD, e.g. `com`, `com.br`, `in`.
- `asin`: product ASIN.
- `country`: default `us`; other countries can cost more.
- `postal_code`: when location-sensitive prices/availability matter.

Reviews endpoint: `GET /amazon/reviews`

Common params:

- `domain`
- `asin`
- `sort_by`: `helpful` or `recent`.
- `filter_by_star`: `one_star`, `two_star`, `three_star`, `four_star`, `five_star`.
- `page` where supported.

Notes:

- Amazon Product/Search/Offers are cheap relative to reviews.
- Amazon Reviews can be high-cost and less consistent; use single concurrency and cache aggressively.

## Account / Usage

Endpoint: `GET /account`

Use to inspect remaining credits and active concurrency before big jobs. Never print the API key in logs.

## Error Handling

- Use retry with exponential backoff and jitter for transient failures.
- Treat `410` as retryable timeout.
- Treat `429` as concurrency pressure; reduce in-flight requests.
- Include status markers like `scrapingdog_http_429` so shared retry code can classify errors.
- Log only endpoint/path, status, and short body snippets; never log `api_key`.

