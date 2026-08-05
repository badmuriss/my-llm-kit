# Core, proxy e utilitários

Fonte: doc oficial ScrapingDog, coletada 2026-08-05. `api_key` em query param em toda chamada (omitido abaixo). Base: `https://api.scrapingdog.com`.


## Scrape genérico + screenshot

### `/scrape` — Web Scraping API
The Web Scraping API lets you scrape any public webpage by sending a simple GET request. Pass your API key and target URL — Scrapingdog handles rotating proxies, CAPTCHA bypass, and optional JavaScript rendering automatically.
- Créditos: **5 por padrão**. JS rendering vem LIGADO por default. `dynamic=false` derruba para **1 crédito**. Sempre mande `dynamic` explícito.
- Doc: `https://www.scrapingdog.com/documentation/web-scraping-api/` + `/javascript-rendering/` + `/request-customization/`
- Obrigatórios: `url` URL alvo.
- Opcionais e custo (doc `request-customization`, `javascript-rendering`, `bypass-captcha`, `premium-residential-proxies`, `sessions`, `custom-headers`, `geotargeting`):
  - `dynamic` bool. `true` (default) = headless Chrome, 5 créditos; com `premium=true` = 25. `false` = 1 crédito.
  - `premium` bool. Proxy residencial (USA por default). 10 créditos; 25 se junto com `dynamic=true`.
  - `stealth_mode` bool. Bypass de Cloudflare/bot protection. 10 créditos por request.
  - `wait` ms extras antes de capturar, para página lenta (só faz sentido com `dynamic=true`).
  - `session_number` int. Reusa o mesmo IP entre requests; expira 60s após o último uso. Sem custo extra.
  - `custom_headers=true` + headers na request. Para conteúdo autenticado. Sem custo extra.
  - `country` ISO 3166-1. Geotargeting, disponível em todos os planos, do Free ao Enterprise.
  - POST: mande `api_key` e `url` na query e o corpo do POST no body da request.

### `/webhook` — Webhook Integration
Recebe o conteúdo raspado no seu endpoint em vez de você fazer polling. Webhook é configurado no dashboard.
- Doc: `https://www.scrapingdog.com/documentation/webhook-integration/`
- Obrigatórios: `url` página a raspar.
- Opcionais: `webhook_id` nome do webhook no dashboard (senão usa o default); `dynamic` default `true`.

### `/screenshot` — Screenshot API
The Screenshot API lets you capture screenshots of any webpage by sending a simple GET request. Control the viewport size, output format, image quality, and when the browser considers the page fully loaded. Each successful request costs 5 credits.
- Créditos: Each successful request costs 5 credits
- Doc: `https://www.scrapingdog.com/documentation/screenshot-api/`
- Obrigatórios: `url` The URL of the page for which you want to take a screenshot.
- Opcionais: `fullPage` Boolean that tells the server to take a full-page screenshot or just the visible portion withou; `width` The width of the browser viewport in pixels.; `height` The height of the browser viewport in pixels.; `wait_until` Determines when navigation is considered complete before taking a screenshot.; `format` Screenshot format option. Available: png, jpg, webp.; `quality` Image quality setting (0-100 range).


## Proxy rotativo (Playwright/browser/HTTP client)

### `http://proxy.scrapingdog.com:8081` — Rotating Proxies
Scrapingdog's rotating proxies let you use a standard HTTP proxy configuration instead of the REST API. All requests are forwarded to the same web scraping backend. Configure your HTTP client to route through proxy.scrapingdog.com:8081 using your API key as the password.
- Créditos: não declarado na doc
- Doc: `https://www.scrapingdog.com/documentation/rotating-proxies/`
- Obrigatórios: `Host` proxy.scrapingdog.com; `Port` 8081; `Username` scrapingdog; `Password` Your personal API key from your dashboard.


## Conta e busca multi-engine

### `/account` — The Account API lets you programmatically monitor your Scrapingdog account usage. Query your remaining API credits and the number of active concurrent connections at any time.
- Créditos: não declarado na doc
- Doc: `https://www.scrapingdog.com/documentation/account-api/`

### `/search` — Universal Search API
Using the Universal Search API, you can scrape various search engine results without worrying about proxy rotation and data parsing. Supports geographic targeting and language customization. Each successful request costs 20 API credits.
- Créditos: Each successful request costs 20 API credits
- Doc: `https://www.scrapingdog.com/documentation/universal-search-api/`
- Obrigatórios: `query` The parameter specifies the search query you want to execute, just like a standard search.
- Opcionais: `country` This parameter specifies the country for the search using a two-letter country code (e.g., US f; `language` Language of the results. Possible Values - en, es, fr, de, etc.
