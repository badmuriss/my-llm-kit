# Google Maps, local e imóveis

Fonte: doc oficial ScrapingDog, coletada 2026-08-05. `api_key` em query param em toda chamada (omitido abaixo). Base: `https://api.scrapingdog.com`.


## Google Maps

### `/google_maps` — Google Maps Search API
The Google Maps Search API returns business listings from Google Maps search results. Filter by GPS coordinates, country, and language. Each result includes rating, reviews, address, phone, website, and operating hours.
- Créditos: não declarado na doc
- Doc: `https://www.scrapingdog.com/documentation/google-maps-api/`
- Obrigatórios: `query` A Google Maps Search Query. Example: query=pizza
- Opcionais: `ll` GPS coordinates defining search origin. Format: @latitude,longitude,zoom/map_height. Zoom range; `domain` To obtain local results from a specific country, for example, for India it will be google.co.in; `language` Language of the results. Possible Values: en, es, fr, de, etc. Default: en. For a full list, se; `country` Specifies the country for the search using a two-letter country code (e.g., us, uk, fr). Defaul; `data` Filters search results; copy directly from Google Maps URLs. Required for place-specific search; `place_id` The parameter uniquely identifies a place on Google Maps. Place IDs are available for most loca; `type` Specifies search type: search for query-based results or place for specific location details. N; `page` Page number of results. Increment by 20 for each subsequent page: 0 (first page), 20 (second pa

### `/google_maps/places` — Google Maps Places API
The Google Maps Places API retrieves a complete business profile for a specific location. Returns ratings, GPS coordinates, operating hours, service options, amenities, accessibility features, and payment methods.
- Créditos: não declarado na doc
- Doc: `https://www.scrapingdog.com/documentation/google-maps-places-api/`
- Obrigatórios: `data_id` The Google Maps data ID for a specific location. You can retrieve it from our Google Maps Searc
- Opcionais: `place_id` Uniquely identifies a place on Google Maps. Available for most locations, including businesses,; `ludocid` The CID (Customer ID) of a Google Maps business listing, also known as the Google local busines; `country` This is the ISO code of the country from which you are seeking the results. Default: us. For a 

### `/google_maps/reviews` — Google Maps Reviews API
The Google Maps Reviews API retrieves customer reviews from any Google Maps listing. Sort by quality, newest, or rating. Filter by topic. Returns reviewer details, ratings, review text, images, and response metadata.
- Créditos: não declarado na doc
- Doc: `https://www.scrapingdog.com/documentation/google-maps-reviews-api/`
- Obrigatórios: `data_id` The Google Maps data ID. You can get this by entering the location name as the query in our Goo
- Opcionais: `language` Language of the results. Possible Values: en, es, fr, de, etc. Default: en. For a full list, se; `sort_by` Sort order for reviews. Options: qualityScore (most relevant, default), newestFirst (most recen; `topic_id` The ID of the topic to filter the reviews. You can find these IDs in our JSON response.; `results` Maximum number of results to return. Valid range: 1 to 20. Default: 10. Note: Cannot be used on; `next_page_token` The next_page_token is used to get the next page results.

### `/google_maps/photos` — Google Maps Photos API
The Google Maps Photos API retrieves high-quality photos from any Google Maps location. Filter by category and paginate through large photo sets using a data_id from the Google Maps Search API.
- Créditos: não declarado na doc
- Doc: `https://www.scrapingdog.com/documentation/google-maps-photos-api/`
- Obrigatórios: `data_id` The Google Maps data ID. You can get this by entering the location name as the query in our Goo
- Opcionais: `language` Language of the results. Possible Values: en, es, fr, de, etc. Default: en. For a full list, se; `category_id` This parameter specifies the category's unique identifier, which can be obtained from the categ; `next_page_token` The next_page_token is used to get the next page results.

### `/google_maps/posts` — Google Maps Posts API
The Google Maps Posts API retrieves posts and updates from Google Business listings. Pass a data_id obtained from the Google Maps Search API to get posts with descriptions, dates, images, and links.
- Créditos: não declarado na doc
- Doc: `https://www.scrapingdog.com/documentation/google-maps-posts-api/`
- Obrigatórios: `data_id` It is the Google Maps data ID. You can get this by entering the location name as the query in o
- Opcionais: `next_page_token` The next_page_token is used to get the next page results.


## Local e diretórios

### `/google_local` — Google Local API
The Google Local API retrieves local business listings from Google search including ratings, reviews, addresses, GPS coordinates, and business type. Costs 5 API credits per request.
- Créditos: Costs 5 API credits per request
- Doc: `https://www.scrapingdog.com/documentation/google-local-api/`
- Obrigatórios: `query` This is a Google Search Query. Example: query=coffee+in+manhattan
- Opcionais: `location` The location from where you want to scrape the local results. Example: Manhattan, New York; `uule` It is a parameter that specifies the geographic location or locale for which the search results; `country` ISO code of the country from which you are seeking Google search results.; `language` Language of the results. Possible Values - en, es, fr, de, etc.; `domain` To obtain local results from a specific country, for example, for India, it will be "google.co.; `ludocid` Google My Business listing ID (CID) you want to scrape, also known as the Google Place ID.; `tbs` to be searched - An advanced parameter to filter search results.; `page` This is the page number of Google searches. Its value can be 0 for the first page, 1 for the se

### `/yelp/search` — Yelp Scraper API
The Yelp Scraper API lets you extract business listings from Yelp by keyword and location, with support for category filters, sorting, and pagination. Each successful request costs 4 API credits.
- Créditos: Each successful request costs 4 API credits
- Doc: `https://www.scrapingdog.com/documentation/yelp-scraper-api/`
- Obrigatórios: `find_loc` Target location for the search (e.g., San Francisco, CA).
- Opcionais: `find_desc` The search query term (e.g., burger, pizza, coffee).; `cflt` Category filter to narrow results to a specific Yelp category (e.g., restaurants, bars).; `sortby` Sort method for results. Accepted values: recommended, rating, review_count. Default: recommend; `attrs` Refine results by business attributes (e.g., GoodForKids, WheelchairAccessible).; `l` Distance or map radius string to narrow results by geographic area.; `yelp_domain` The Yelp domain to scrape (e.g., yelp.com, yelp.co.uk).; `start` Pagination offset. Use multiples of 10 to paginate through results (e.g., 10, 20). Default: 0.

### `/zillow` — Zillow Scraper API
The Zillow Scraper API extracts real estate listings from any Zillow search page in real-time. Pass a valid Zillow URL and receive structured property data. Each successful request costs 2 API credits.
- Créditos: Each successful request costs 2 API credits
- Doc: `https://www.scrapingdog.com/documentation/zillow-scraper-api/`
- Obrigatórios: `url` The full Zillow URL to scrape (e.g., https://www.zillow.com/homes/for_sale/Brooklyn,-New-York,-
