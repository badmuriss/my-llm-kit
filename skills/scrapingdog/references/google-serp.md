# Google Search, AI, Trends, News e outros buscadores

Fonte: doc oficial ScrapingDog, coletada 2026-08-05. `api_key` em query param em toda chamada (omitido abaixo). Base: `https://api.scrapingdog.com`.

Perfil Brasil: em `/google`, `/google_news`, `/google_shopping` e `/google_jobs` passe `country=br`, `language=pt` e `domain=google.com.br`; em `/google_trends` use `geo=BR`.


## Google Search + AI

### `/google`: Google Search API Documentation
Using the Google Search API, you can scrape Google search results without worrying about proxy rotation and data parsing. Each successful request costs 5 credits for standard search, or 10 credits for advanced search (advance_search=true) and mobile search (mob_search=true).
- Créditos: Each successful request costs 5 credits for standard search, or 10 credits for advanced search (advance_search=true) and mobile se
- Doc: `https://www.scrapingdog.com/documentation/google-search-api/`
- Obrigatórios: `query` The parameter specifies the search query you want to execute, just like a standard Google searc
- Opcionais: `results` Number of results to return per page.; `page` This is the page number of Google searches. Its value can be 0 for the first page, 1 for the se; `advance_search` This can be used to get advanced feature snippets from Google. If true, will cost 10 credits pe; `mob_search` Use this parameter to get mobile search results. If true, it will cost 10 credits per request. ; `html` This will return the full HTML of the Google page. Default: false; `domain` To obtain local results from a specific country, for example, for India it will be google.co.in; `country` Specifies the country for the Google search using a two-letter country code (e.g., us, uk, fr).; `language` Language of the results. Possible values: en, es, fr, de, etc. Default: en. For a full list, se; `location` Specifies the origin location of the search. Recommended at city level. Cannot be used with the; `uule` Specifies the geographic location or locale for which search results should be tailored (e.g., ; `cr` Allows you to restrict the search to specific countries using format countryFR or multiple with; `lr` Limit search to one or multiple languages using format lang_en or multiple with lang_en|lang_fr; `tbs` An advanced parameter to filter search results (e.g. time ranges, verbatim mode).; `safe` To filter adult content set to active, or to disable it set to off. Default: off; `nfpr` Excludes results from auto-corrected misspelled queries. Set to 1 to exclude or 0 to include. D; `filter` Controls whether "Similar Results" and "Omitted Results" filters are enabled. Set to 1 (default; `ludocid` Specifies the ID (CID) of the Google My Business listing, also referred to as the Google Place ; `lsig` May be required for knowledge graph map view. Obtain via Google Local API or Google My Business; `kgmid` Specifies the ID (KGMID) of the Google Knowledge Graph listing. May override other parameters e; `si` Specifies cached search parameters of the Google Search you want to scrape. May override other ; `ibp` Controls rendering of specific layouts and expansion of certain elements (e.g., gwp;0,7 expands; `uds` Allows filtering search results using a string provided by Google.

### `/google/ai_mode`: Google AI Mode API
The Google AI Mode API lets you search Google with AI Mode enabled, returning structured results with references and text blocks. Each successful request costs 10 API credits.
- Créditos: Each successful request costs 10 API credits
- Doc: `https://www.scrapingdog.com/documentation/google-ai-mode-api/`
- Obrigatórios: `query` The query you want to search in Google AI Mode
- Opcionais: `country` Specifies the country for the Google search using a two-letter country code (e.g., us, uk, fr).; `language` Language of the results. Possible values: en, es, fr, de, etc. Default: en. For a full list, se; `uule` A parameter that specifies the geographic location or locale for which the search results shoul; `location` Specifies the origin location of the search. It cannot be used in combination with the uule par; `safe` To filter adult content set to active, or to disable it set to off. Default: off; `html` This will return the full HTML of the Google page. Default: false

### `/google/ai_overview`: Google AI Overview API
This API is used only when Google requires a separate request to fetch AI Overview results. Pass the url field returned by the Google Search API response. The URL expires after 2 minutes. Each successful request costs 5 API credits.
- Créditos: Each successful request costs 5 API credits
- Doc: `https://www.scrapingdog.com/documentation/google-ai-overview-api/`
- Obrigatórios: `url` This URL is used to fetch the AI Overview Results. You will get this from the Google Search API

### `/google_autocomplete`: Google Autocomplete API
The Google Autocomplete API returns autocomplete suggestions from Google search based on specified query terms, geographic location, and language preferences, including relevance scores.
- Créditos: não declarado na doc
- Doc: `https://www.scrapingdog.com/documentation/google-autocomplete-api/`
- Obrigatórios: `query` This is a Google Search Query. Example1 - query=pizza
- Opcionais: `country` This parameter specifies the country for the Google search using a two-letter country code (e.g; `language` Language of the results. Possible Values - en, es, fr, de, etc.

### `/google/ads_transparency`: Google Ads Transparency API
The Google Ads Transparency API lets you pull ad data from the Google Ads Transparency Center. You can look up ads by advertiser ID or keyword, and narrow results by platform, region, date range, or creative format.
- Créditos: Costs 5 API credits per request
- Doc: `https://www.scrapingdog.com/documentation/google-ads-transparency-api/`
- Opcionais: `html` Set to true to receive the raw HTML of the page instead of parsed JSON.; `advertiser_id` The unique ID assigned to a Google advertiser. You can find it in the Ads Transparency Center U; `text` A keyword or domain to search within the Google Ads Transparency Center: works the same way as; `platform` Filters results to a specific Google platform. Leave blank to get ads from all platforms.; `political_ads` Set to true to include only political advertisements. Political ads are tracked separately and ; `region` Limits results to a specific geographic region. When omitted, results are returned globally. Us; `start_date` The earliest date for which ads should be returned. Use the format YYYYMMDD.; `end_date` The latest date for which ads should be returned. Use the format YYYYMMDD.; `creative_format` Filters ads by their creative type. Only ads matching the chosen format will appear in the resp; `num` Maximum number of ad results to return per request.; `next_page_token` Token for fetching the next page of results. Obtain this value from the previous response to pa

### `/chatgpt`: ChatGPT Scraper API
The ChatGPT Scraper API lets you send any prompt to ChatGPT and receive structured JSON responses including the full conversation with user and assistant roles. No browser automation required. Scrapingdog handles all the complexity. Each successful request costs 30 API credits.
- Créditos: Each successful request costs 30 API credits
- Doc: `https://www.scrapingdog.com/documentation/chatgpt-scraper-api/`
- Obrigatórios: `prompt` The prompt to send to ChatGPT (e.g., What is web scraping?). The API returns the full conversat
- Opcionais: `html` Set to true to return the full HTML of the ChatGPT page instead of parsed JSON. Default: false.


## Google Trends

### `/google_trends`: Google Trends API
The Google Trends API lets you retrieve search trend data including interest over time, regional breakdowns, and comparative analyses across up to 5 queries. Each request costs 5 API credits.
- Créditos: Each request costs 5 API credits
- Doc: `https://www.scrapingdog.com/documentation/google-trends-api/`
- Opcionais: `query` The parameter specifies the query or queries you want to search. You can use any term or topic ; `data_type` The parameter specifies the type of search to perform.; `geo` The parameter specifies the location from which the search originates. By default, it is set to; `region` The region parameter allows you to obtain more specific results for the "Compared Breakdown by ; `language` Language of the results. Possible values: en, es, fr, de, etc. Default: en; `date` This parameter specifies the date range for the search.; `cat` This parameter specifies the search category. Default: 0 (All categories); `gprop` This parameter determines how results are sorted based on the selected property. Default: Web S; `tz` This parameter specifies the time zone offset. The default value is 420 minutes (PDT: -07:00). 

### `/google_trends/autocomplete`: Google Trends Autocomplete API
The Google Trends Autocomplete API returns autocomplete suggestions based on a search query, including relevant topics and entities with categorization and Google Trends exploration links.
- Créditos: não declarado na doc
- Doc: `https://www.scrapingdog.com/documentation/google-trends-autocomplete-api/`
- Opcionais: `query` This is a Google Search Query. Example1 - query=pizza; `language` Language of the results. Possible Values - en, es, fr, de, etc. Default: en

### `/google_trends/trending_now`: Google Trends Trending Now API
The Google Trends Trending Now API retrieves currently trending searches from Google, filtered by location, time range, and language preferences.
- Créditos: não declarado na doc
- Doc: `https://www.scrapingdog.com/documentation/google-trends-trending-now-api/`
- Obrigatórios: `geo` This parameter specifies the location from which the search originates. Default: US
- Opcionais: `hours` By default, it is set to 24 (Past 24 hours). Google provides the following predefined values: 4; `language` This parameter specifies the language for the Google Trends Trending Now search. It accepts a t


## Google News

### `/google_news`: Google News Search API
The Google News Search API retrieves news search results from Google News, returning headlines, snippets, source names, and timestamps. Costs 5 API credits per request.
- Créditos: Costs 5 API credits per request
- Doc: `https://www.scrapingdog.com/documentation/google-news-search-api/`
- Obrigatórios: `query` This is a Google Search Query. Example: query=pizza
- Opcionais: `results` Number of results you want to scrape. Its value could be anything between 1 and 100. Default: 1; `country` ISO code of the country from which you are seeking Google search results. Default: us. For a fu; `page` Page number of Google searches. Its value can be 0 for the first page, 1 for the second page, a; `domain` To obtain local results from a specific country, for example, for India it will be google.co.in; `language` Language of the results. Possible Values: en, es, fr, de, etc. Default: en. For a full list, se; `lr` Limit the search to one or multiple languages. Used as lang_{language_code} (e.g., lang_en). Fo; `uule` A parameter that specifies the geographic location or locale for which the search results shoul; `tbs` Time-Based Search parameter to filter results based on a specific time range (qdr:h past hour, ; `safe` To filter adult content set to active, or to disable it set to off. Default: off; `nfpr` Excludes results from auto-corrected queries that are spelled wrong. Set to 1 to exclude or 0 t; `html` This will return the full HTML of the Google page. Default: false

### `/google_news/v2`: Google News API (v2)
The Google News API (v2) is faster than the search API and returns images as URLs instead of base64, and provides actual dates instead of relative durations. Supports topic tokens, publication tokens, and section tokens.
- Créditos: não declarado na doc
- Doc: `https://www.scrapingdog.com/documentation/google-news-api/`
- Opcionais: `query` Specifies the query you want to search for, just like a standard Google News search. You can in; `country` Specifies the country for the Google search using a two-letter country code (e.g., us, uk, fr).; `language` Language of the results. Possible Values: en, es, fr, de, etc. Default: en. For a full list, se; `topic_token` Specifies the Google News topic token, which allows access to news results for a particular top; `publication_token` Specifies the Google News publication token, allowing retrieval of news results from a specific; `section_token` Defines the Google News section token, which is used to access a subsection of a specific topic; `so` Defines the sorting method: 0 (Relevance, default) or 1 (Date). Can only be used with story_tok


## Outros buscadores

### `/bing/search`: Bing Search Scraper API
The Bing Search Scraper API retrieves search results from Bing with customizable parameters for geographic location, localization, pagination, and content filtering.
- Créditos: Costs 5 API credits per request
- Doc: `https://www.scrapingdog.com/documentation/bing-search-api/`
- Obrigatórios: `query` The parameter specifies the search query, allowing you to use any terms or operators you would 
- Opcionais: `lat` Specifies the GPS latitude as the starting point for the search.; `lon` Specifies the GPS longitude as the starting point for the search.; `mkt` Specifies the market from which the results originate (e.g., en-US). Market should be formatted; `cc` Specifies the country from which the search is conducted. Follows the two-character ISO 3166-1 ; `first` Adjusts the starting position of organic search results. Default: 1. Setting first=10 shifts th; `count` Determines the number of results displayed per page, ranging from 1 to 50 maximum. Actual resul; `safeSearch` Controls filtering level for adult content: Off, Moderate, or Strict.; `filters` Enables advanced filtering options such as date range filtering or specific display filters. Co

### `/bing/shopping`: Bing Shopping API
The Bing Shopping API retrieves shopping results from Bing with support for market targeting, country localization, pagination, and advanced filters.
- Créditos: Costs 5 API credits per request
- Doc: `https://www.scrapingdog.com/documentation/bing-shopping-api/`
- Obrigatórios: `query` Parameter defines the search query. You can enter any term you would normally use in a Bing Sho
- Opcionais: `mkt` Parameter defines the market from which the results are returned. The value should be in the <l; `cc` Parameter defines the country from which the search results are returned. It uses the 2-charact; `efirst` Parameter controls the offset of the shopping results. For example, efirst=10 starts the result; `filters` Parameter allows you to apply advanced filters, such as date range filters like ex1:"ez5_18169_

### `/duckduckgo/search`: DuckDuckGo Search API
The DuckDuckGo Search API retrieves organic search results from DuckDuckGo with support for region codes, date filters, and pagination via next page tokens.
- Créditos: não declarado na doc
- Doc: `https://www.scrapingdog.com/documentation/duckduckgo-search-api/`
- Obrigatórios: `query` This parameter specifies the search query. You can enter any terms or operators you would norma
- Opcionais: `html` This will return the full HTML of the Google page.; `kl` This parameter sets the region for the DuckDuckGo search. For example: us-en for the United Sta; `df` This parameter filters results by date. Options include: d (Past day), w (Past week), m (Past m; `next_page_token` This parameter specifies the next page token, used to fetch subsequent results. Each page retur

### `/baidu/search`: Baidu Search API
Using the Baidu Search API you can scrape Baidu search results without worrying about proxy rotation and data parsing. Supports advanced Baidu search operators and localization options. Each successful request costs 5 API credits.
- Créditos: Each successful request costs 5 API credits
- Doc: `https://www.scrapingdog.com/documentation/baidu-search-api/`
- Obrigatórios: `query` This parameter specifies the search query and supports all Baidu search operators (e.g., inurl:
- Opcionais: `html` This will return the full HTML of the Google page.; `ct` Language restriction. Values: 1 = All languages, 2 = Simplified Chinese, 3 = Traditional Chines; `pn` Result offset for pagination. 0 = first page, 10 = second page, 20 = third page, etc.; `rn` Maximum number of results to return. Maximum value is 50. Default: 10; `gpc` This parameter specifies the time range for the results using Unix timestamps.; `q5` Functions similarly to using inurl: or intitle:. For example, use 1 to search by page title, an; `q6` Similar to using site: (e.g., q6=scrapingdog.com).; `bs` Specifies the preceding search query.; `oq` Indicates the original search query when the user arrives via a related search.; `f` Specifies the source of the search. For example, 8 indicates a standard search, 3 comes from th
