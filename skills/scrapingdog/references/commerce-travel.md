# Shopping, ecommerce, viagem e finanças

Fonte: doc oficial ScrapingDog, coletada 2026-08-05. `api_key` em query param em toda chamada (omitido abaixo). Base: `https://api.scrapingdog.com`.


## Google Shopping / produto

### `/google_shopping` — Google Shopping Scraper API
The Google Shopping API lets you scrape shopping results without dealing with proxy rotation or data parsing. Fast, reliable, and each successful request costs 10 credits.
- Créditos: Fast, reliable, and each successful request costs 10 credits
- Doc: `https://www.scrapingdog.com/documentation/google-shopping-api/`
- Obrigatórios: `query` This can be any Google query or a complete Google URL. Example: query=shoes
- Opcionais: `country` Specifies the country for the Google Shopping search using a two-letter country code (e.g., us,; `page` This is the page number of Google searches. Its value can be 0 for the first page, 1 for the se; `domain` To obtain local results from a specific country, for example, for India, it will be "google.co.; `language` Language of the results. Possible Values - en, es, fr, de, etc.; `lr` Limit the search to one or multiple languages.; `shoprs` This parameter specifies the helper ID used to apply search filters. To ensure filters work cor; `uule` It is a parameter that specifies the geographic location or locale for which the search results; `tbs` to be searched - An advanced parameter to filter search results.; `safe` To filter the adult content set safe to active or to disable it set off.; `nfpr` It can be set to 1 to exclude these results or 0 to include them.; `html` To render the response as raw HTML.

### `/google_immersive_product` — Google Immersive Product API
The Google Immersive Product API scrapes Google product results from the immersive popup view, returning brand info, price range, and store-level listings with ratings and reviews.
- Créditos: não declarado na doc
- Doc: `https://www.scrapingdog.com/documentation/google-immersive-product-api/`
- Obrigatórios: `page_token` This parameter specifies the token required to display additional product details in Google's i
- Opcionais: `stores` This parameter enables the pagination to get more sellers. Pass true to enable it. It can only ; `sori` This parameter works together with the stores parameter to fetch the next page of seller result; `country` This parameter specifies the country for the Google search using a two-letter country code (e.g; `language` Language of the results. Possible Values - en, es, fr, de, etc. For a complete list of supporte


## Viagem

### `/google_flights` — Google Flights API
The Google Flights API retrieves flight data from Google Flights supporting one-way, round-trip, and multi-city searches with filtering and sorting capabilities. Costs 5 API credits per request.
- Créditos: Costs 5 API credits per request
- Doc: `https://www.scrapingdog.com/documentation/google-flights-api/`
- Obrigatórios: `departure_id` The parameter sets the departure point using either an airport code or a location kgmid. Airpor; `arrival_id` An airport code is a 3-letter uppercase identifier. Location kgmids begin with "/m/". Multiple 
- Opcionais: `html` This will return the full HTML of the Google page.; `country` This parameter specifies the country for the Google search using a two-letter country code (e.g; `language` Language of the results. Possible Values - en, es, fr, de, etc.; `currency` This parameter sets the currency for the returned prices. For a complete list, see the Supporte; `type` This parameter specifies the flight type.; `outbound_date` This parameter sets the outbound travel date. The value must be in YYYY-MM-DD format. Example: ; `return_date` This parameter sets the return travel date. The value must be provided in YYYY-MM-DD format, fo; `travel_class` This parameter specifies the travel class.; `multi_city_json` This parameter is used to provide flight details for multi-city trips. It should be passed as a; `adults` Number of adult passengers.; `children` Number of child passengers.; `infants_in_seat` Number of infants travelling in their own seat.; `infants_on_lap` Number of infants traveling on an adult's lap.; `sort_by` This parameter sets how the flight results are sorted.; `stops` This parameter specifies the maximum number of stops for the flight.; `exclude_airlines` This parameter lets you exclude specific airlines from the results. Each airline must be provid; `include_airlines` This parameter lets you include only specific airlines in the results. Each airline must be pro; `bags` This parameter sets the number of carry-on bags.; `max_price` This parameter sets the maximum ticket price allowed in the results. By default, there is no pr; `outbound_times` This parameter sets the preferred time range for the outbound flight. Each number represents th; `return_times` This parameter sets the preferred time range for the return flight. Each number represents the ; `emissions` This parameter filters flights based on emission level.; `layover_duration` This parameter sets the preferred layover duration in minutes. Example: 75,240 means 1 hour 15 ; `exclude_conns` This parameter lets you exclude specific connecting airports from the results. You can exclude ; `max_duration` This parameter sets the maximum total flight duration in minutes. Example: 960 means up to 16 h; `departure_token` This parameter is used to select a departure flight and retrieve the next set of results: for R; `booking_token` This parameter retrieves booking options for the selected flight. It cannot be used together wi

### `/google_hotels` — Google Hotels API
The Google Hotels API retrieves hotel search results from Google Hotels including property listings, pricing, ratings, amenities, and detailed property information. Costs 5 API credits per request.
- Créditos: Costs 5 API credits per request
- Doc: `https://www.scrapingdog.com/documentation/google-hotels-api/`
- Obrigatórios: `query` This parameter specifies the search query. You can enter anything you would normally use in a s; `check_in_date` This parameter specifies the check-in date in the format YYYY-MM-DD (e.g., 2025-08-15).; `check_out_date` This parameter specifies the check-out date, using the format YYYY-MM-DD (e.g., 2025-08-16).
- Opcionais: `html` This will return the full HTML of the Google page.; `country` This parameter specifies the country for the Google search using a two-letter country code (e.g; `language` Language of the results. Possible Values - en, es, fr, de, etc.; `currency` This parameter sets the currency for the returned prices. For a complete list, see the Supporte; `adults` This parameter specifies the number of adults, with a default value of 2.; `children` This parameter specifies the number of children, with a default value of 0.; `children_ages` This parameter specifies the ages of children. The valid range is 1 to 17. Examples: single chi; `sort_by` Parameter specifies how the results should be sorted. By default, results are sorted by Relevan; `min_price` Parameter sets the minimum price in the range.; `max_price` Specifies the maximum price in the range.; `property_types` Specifies the property type(s) to include in the results. For a complete list, see Supported Go; `amenities` This parameter allows you to filter results so that only listings with the selected amenities a; `rating` Parameter is used for filtering the results to a certain rating.; `brands` This parameter specifies the brands you want to focus your search on. Examples: single: 33; mul; `hotel_class` This parameter filters results to include only hotels of specific star ratings.; `free_cancellation` This parameter filters results to include only listings that offer free cancellation.; `special_offers` This parameter limits results to listings that include special offers.; `eco_certified` This parameter filters results to include only listings that are eco-certified.; `vacation_rentals` This parameter specifies whether to search for Vacation Rentals. By default, the search is set ; `bedrooms` This parameter sets the minimum number of bedrooms.; `bathrooms` This parameter specifies the minimum number of bathrooms.; `next_page_token` The next_page_token is used to get the next page results.; `property_token` This parameter retrieves detailed property information, including name, address, phone number, 


## Finanças

### `/google_finance` — Google Finance API
The Google Finance API lets you retrieve financial market data including stock prices, price movements, market news, and related financial instruments across multiple markets and asset classes.
- Créditos: não declarado na doc
- Doc: `https://www.scrapingdog.com/documentation/google-finance-api/`
- Obrigatórios: `query` The stock you want to search for (e.g., NIFTY_50:INDEXNSE)
- Opcionais: `language` Language of the results. Possible Values - en, es, fr, de, etc. Default: en; `html` To render the response as raw HTML. Default: false


## Amazon

### `/amazon/product` — Amazon Product Scraper
The Amazon Product Scraper API retrieves comprehensive product data from any Amazon product page using its ASIN. Supports 20+ Amazon domains globally with localization options. Each successful request costs 1 API credit.
- Créditos: Each successful request costs 1 API credit
- Doc: `https://www.scrapingdog.com/documentation/amazon-product-scraper/`
- Obrigatórios: `asin` This is the Amazon product ID (ASIN). Found in the product URL (e.g., B00AP877FS).; `domain` The TLD extension of the Amazon domain to scrape. Examples: com, in, de, fr, co.uk. For a compl; `country` ISO country code for targeting a specific Amazon marketplace. Costs 5 credits per request excep
- Opcionais: `language` Standard ISO 639-1 language codes (e.g., en, de, fr) to specify the language for product data.; `postal_code` To get data from a particular postal code.

### `/amazon/search` — Amazon Search Scraper
The Amazon Search Scraper API retrieves search result listings from Amazon for any query. Returns an object with results (product titles, prices, ratings, review counts, sponsored status, ASINs) and pagination (array of next-page URLs). Each successful request costs 1 API credit.
- Créditos: Each successful request costs 1 API credit
- Doc: `https://www.scrapingdog.com/documentation/amazon-search-scraper/`
- Obrigatórios: `query` The search query string to look up on Amazon.; `domain` The TLD extension of the Amazon domain. Examples: com, in, de, fr, co.uk. For a complete list o; `page` The page number of results to retrieve. Starts at 1.; `country` ISO country code for targeting a specific Amazon marketplace. Costs 5 credits per request excep
- Opcionais: `language` Standard ISO 639-1 language codes (e.g., en, de, fr) to specify the language for product data.; `postal_code` To get data from a particular postal code.; `premium` Set to true to use premium proxies for scraping Amazon, which increases the chances of retrievi

### `/amazon/offers` — Amazon Offers Scraper API
Get detailed product offer data with pricing, availability, seller details and delivery options. The Amazon Offers API scrapes every active offer for a given ASIN and returns structured JSON.
- Créditos: não declarado na doc
- Doc: `https://www.scrapingdog.com/documentation/amazon-offers-api/`
- Obrigatórios: `asin` The Amazon Standard Identification Number (ASIN) of the product whose offers you want to retrie; `domain` The Amazon domain to scrape. Pass the TLD only — e.g. com, co.uk, de, co.jp. For a complete lis; `country` ISO country code for targeting a particular country. Affects price, delivery estimates, and off
- Opcionais: `postal_code` ZIP / postal code for hyper-local delivery filtering. When set, the API returns shipping dates 

### `/amazon/reviews` — Amazon Reviews API
⚠️ Temporarily unavailable: Amazon has moved its reviews section behind a login wall, which means this API cannot retrieve review data at this time.The Amazon Reviews API enables scraping of customer reviews from any Amazon product page. Supports filtering by star rating, reviewe
- Créditos: Each successful request costs 5 API credits
- Doc: `https://www.scrapingdog.com/documentation/amazon-reviews-api/`
- Obrigatórios: `asin` Amazon product ID (ASIN) of the product whose reviews you want to scrape.; `domain` The TLD extension of the Amazon domain. Examples: com, in, de, fr. For a complete list of suppo; `page` The page number of reviews to retrieve. Starts at 1.
- Opcionais: `sort_by` Sort order for reviews. Values: helpful (default), recent.; `filter_by_star` Filter reviews by star rating. Values: all_stars (default), five_star, four_star, three_star, t; `reviewer_type` Filter by reviewer type. Values: all_reviews (default), avp_only_reviews (verified purchases on; `media_type` Filter by media type. Values: all_contents (default), media_reviews_only.; `format_type` Filter by format. Values: all_formats (default), current_format.; `url` Alternative to passing asin, domain, and page separately — pass the full Amazon reviews URL dir

### `/amazon/autocomplete` — Amazon Autocomplete Scraper
The Amazon Autocomplete Scraper API retrieves keyword suggestions from Amazon's autocomplete feature based on partial search terms. Useful for keyword research and building search-driven features. Each successful request costs 5 API credits.
- Créditos: Each successful request costs 5 API credits
- Doc: `https://www.scrapingdog.com/documentation/amazon-autocomplete-scraper/`
- Opcionais: `prefix` The partial search term that Amazon uses to generate keyword suggestions (e.g., spoon, iph).; `last_prefix` Indicates previously typed characters. For example, if user typed "i" then "phone", set last_pr; `suffix` Assists with search query completion and predictions.; `mid` Merchant ID for identifying a specific seller to scope suggestions.; `domain` The TLD extension of the Amazon domain. Examples: com, in, de, fr. For a complete list of suppo; `language` Language code for suggestions (e.g., en, es, fr, de). Default: en


## Walmart / eBay / Flipkart / Myntra / Apple

### `/walmart/search` — Walmart Search Scraper
Scrape Walmart search result pages by passing any Walmart search URL. Returns product titles, prices, ratings, review counts, availability, and seller info. Each successful request costs 5 API credits.
- Créditos: Each successful request costs 5 API credits
- Doc: `https://www.scrapingdog.com/documentation/walmart-search-scraper/`
- Obrigatórios: `url` The full Walmart search URL to scrape. You can build this URL directly from the Walmart website

### `/walmart/product` — Walmart Product Scraper
Scrape any Walmart product page by URL to retrieve title, price, images, ratings, reviews, seller info, and more. Each successful request costs 5 API credits.
- Créditos: Each successful request costs 5 API credits
- Doc: `https://www.scrapingdog.com/documentation/walmart-product-scraper/`
- Obrigatórios: `url` The full Walmart product page URL to scrape (e.g., https://www.walmart.com/ip/46480251).

### `/walmart/reviews` — Walmart Reviews Scraper
Scrape Walmart product reviews by passing any Walmart reviews page URL. Returns ratings distribution, individual reviews, and top positive/negative feedback. Each successful request costs 5 API credits.
- Créditos: Each successful request costs 5 API credits
- Doc: `https://www.scrapingdog.com/documentation/walmart-reviews-scraper/`
- Obrigatórios: `url` The full Walmart reviews page URL (e.g., https://www.walmart.com/reviews/product/317408869).

### `/walmart/autocomplete` — Walmart Autocomplete API
Retrieve Walmart autocomplete search suggestions for any query. Returns a list of suggested search terms along with category navigation data. Each successful request costs 5 API credits.
- Créditos: Each successful request costs 5 API credits
- Doc: `https://www.scrapingdog.com/documentation/walmart-autocomplete-api/`
- Obrigatórios: `query` The Walmart search query to get autocomplete suggestions for (e.g., football, laptop).

### `/ebay/search` — eBay Search API
The eBay Search Scraper API lets you scrape eBay search result pages by passing any eBay search URL. Returns product titles, item IDs, prices, seller info, condition, and shipping details. Each successful request costs 5 API credits.
- Créditos: Each successful request costs 5 API credits
- Doc: `https://www.scrapingdog.com/documentation/ebay-search-api/`
- Obrigatórios: `url` URL of the eBay search page to scrape (e.g., https://www.ebay.com/sch/i.html?_nkw=laptop). You 
- Opcionais: `html` Set to true to return the full HTML of the eBay page instead of parsed JSON. Default: false.

### `/ebay/product` — eBay Product API
Scrape any eBay product listing page by URL to retrieve title, item ID, pricing, seller details, images, specifications, shipping and return policies. Each successful request costs 5 API credits.
- Créditos: Each successful request costs 5 API credits
- Doc: `https://www.scrapingdog.com/documentation/ebay-product-api/`
- Obrigatórios: `url` URL of the eBay product listing page to scrape (e.g., https://www.ebay.co.uk/itm/305209925234).
- Opcionais: `html` Set to true to return the full HTML of the eBay page instead of parsed JSON. Default: false.

### `/flipkart/search` — Flipkart Search API
Scrape Flipkart search result pages by passing any Flipkart search URL. Returns product titles, URLs, prices, discounts, ratings, and product IDs. Each successful request costs 5 API credits.
- Créditos: Each successful request costs 5 API credits
- Doc: `https://www.scrapingdog.com/documentation/flipkart-search-api/`
- Obrigatórios: `url` URL of the Flipkart search page to scrape (e.g., https://www.flipkart.com/search?q=laptops).
- Opcionais: `html` Set to true to return the full HTML of the Flipkart page instead of parsed JSON. Default: false

### `/flipkart/product` — Flipkart Product API
Scrape any Flipkart product page by URL to retrieve title, brand, pricing, specifications, images, customer ratings, reviews, payment options, and available offers. Each successful request costs 5 API credits.
- Créditos: Each successful request costs 5 API credits
- Doc: `https://www.scrapingdog.com/documentation/flipkart-product-api/`
- Obrigatórios: `url` URL of the Flipkart product page to scrape (e.g., https://www.flipkart.com/product/p/itm909c820
- Opcionais: `html` Set to true to return the full HTML of the Flipkart page instead of parsed JSON. Default: false

### `/myntra/search` — Myntra Search API
Scrape Myntra search result pages by passing any Myntra search URL. Returns product IDs, names, brands, prices, discounts, ratings, and images. Each successful request costs 5 API credits.
- Créditos: Each successful request costs 5 API credits
- Doc: `https://www.scrapingdog.com/documentation/myntra-search-api/`
- Obrigatórios: `url` URL of the Myntra search page to scrape (e.g., https://www.myntra.com/nike-shoes?rawQuery=nike%
- Opcionais: `html` Set to true to return the full HTML of the Myntra page instead of parsed JSON. Default: false.

### `/myntra/product` — Myntra Product API
Scrape any Myntra product page by URL to retrieve product name, brand, MRP, pricing, available sizes, color options, ratings, images, seller details, and available offers. Each successful request costs 5 API credits.
- Créditos: Each successful request costs 5 API credits
- Doc: `https://www.scrapingdog.com/documentation/myntra-product-api/`
- Obrigatórios: `url` URL of the Myntra product page to scrape (e.g., https://www.myntra.com/jeans/powerlook/.../3107
- Opcionais: `html` Set to true to return the full HTML of the Myntra page instead of parsed JSON. Default: false.

### `/apple/app_store` — Apple App Store Search API
The Apple App Store Search API returns structured search results from the Apple App Store for any query — app titles, developers, ratings, prices and more. Supports country and language localization, category and developer filters, and device simulation. Each successful request c
- Créditos: Each successful request costs 5 API credits
- Doc: `https://www.scrapingdog.com/documentation/apple-app-store-api/`
- Obrigatórios: `term` The search query to look up on the App Store (e.g., coffee, netflix, testflight).
- Opcionais: `country` Two-letter country code for the App Store region (e.g., us, uk, fr). Default: us.; `lang` Language code used to localize results (e.g., en-us, fr-fr, uk-ua). Default: en-us.; `num` Number of results to return per request. Accepts 1–200; values above 200 are capped at 200. Def; `disallow_explicit` Set to true to exclude apps marked as explicit. Accepted values: true, false. Default: false.; `property` Restrict the search to a specific attribute. For example, property=developer matches the search; `category_id` Filter results to a specific App Store category/genre by its numeric id (e.g., 6014 for Games).; `device` Device type to simulate the search from. Accepted values: desktop, mobile, tablet. Default: des; `html` Set to true to return the raw HTML of the App Store page instead of parsed JSON. Default: false

### `/apple/product` — Apple Product API
The Apple Product API returns the complete App Store product page for a given app id — title, developer, ratings, price, in-app purchases, screenshots, description, version history and privacy details. Each successful request costs 5 API credits.
- Créditos: Each successful request costs 5 API credits
- Doc: `https://www.scrapingdog.com/documentation/apple-product-api/`
- Obrigatórios: `product_id` The numeric App Store product id of the app. It is the number after id in an app URL (e.g., 534
- Opcionais: `type` The type of Apple product page to return. Default: app.; `country` Two-letter country code for the App Store region (e.g., us, uk, fr). Default: us.; `html` Set to true to return the raw HTML of the product page instead of parsed JSON. Default: false.

### `/apple/reviews` — Apple Reviews API
The Apple Reviews API returns customer reviews for any App Store app by its product id, with pagination and sorting. Each review includes the rating, title, body, author, app version and date. Each successful request costs 5 API credits.
- Créditos: Each successful request costs 5 API credits
- Doc: `https://www.scrapingdog.com/documentation/apple-reviews-api/`
- Obrigatórios: `product_id` The numeric App Store product id of the app whose reviews you want. It is the number after id i
- Opcionais: `country` Two-letter country code for the App Store region (e.g., us, uk, fr). Default: us.; `page` Pagination index used to fetch reviews on a specific page. Default: 0.; `sort` Sort order for the reviews (iOS App Store only). Accepted values: mostrecent, mosthelpful, most; `html` Set to true to return the raw HTML of the reviews page instead of parsed JSON. Default: false.
