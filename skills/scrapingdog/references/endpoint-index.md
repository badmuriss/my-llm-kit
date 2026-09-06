# Endpoint index

Consult only when choosing a public-data endpoint. Values are historical hints;
verify current documentation before quoting prices or planning a paid batch.

## Routing Table

Credits per successful request, taken from the official docs. `?` means the doc page does not state it; run `scripts/account_summary.sh` before a batch.

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
| Credits and concurrency left | `scripts/account_summary.sh` (wraps `/account`) | 0 |

Two entries deserve a second look before you fire them: `/profile?type=person` at up to 100 credits, and `/chatgpt` at 30. Everything else is cheap enough to use freely.

Instagram and Facebook doc pages are stubs that only publish the endpoint, no parameters. Smoke test them before wiring into production.

Amazon Reviews is flagged in the docs as temporarily unavailable because Amazon moved reviews behind a login wall.
