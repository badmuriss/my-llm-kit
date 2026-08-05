# YouTube, TikTok, X, Instagram, Facebook e mídia visual

Fonte: doc oficial ScrapingDog, coletada 2026-08-05. `api_key` em query param em toda chamada (omitido abaixo). Base: `https://api.scrapingdog.com`.


## YouTube

### `/youtube/search` — YouTube Search API
The YouTube Search API lets you scrape YouTube search results for any query. Returns structured video data including titles, links, channel info, view counts, durations, thumbnails, and pagination tokens. Each successful request costs 5 API credits.
- Créditos: Each successful request costs 5 API credits
- Doc: `https://www.scrapingdog.com/documentation/youtube-search-api/`
- Obrigatórios: `search_query` This can be any YouTube query. Example: search_query=elon+musk
- Opcionais: `country` ISO code of the country from which you are seeking YouTube search results. Default: us; `language` Language of the results. Possible Values — en, es, fr, de, etc. Default: en; `sp` Used for pagination and filtering search results on YouTube. Supports upload date (CAI%3D), 4K 

### `/youtube/transcripts` — YouTube Transcripts API
The YouTube Transcripts API lets you extract the complete transcript (captions) from any YouTube video. Returns an array of text segments with start time and duration. Each successful request costs 1 API credit.
- Créditos: Each successful request costs 1 API credit
- Doc: `https://www.scrapingdog.com/documentation/youtube-transcripts-api/`
- Obrigatórios: `v` YouTube Video ID. You can find it in the video URL after ?v= (e.g., for youtube.com/watch?v=0e3
- Opcionais: `country` ISO code of the country from which you are seeking YouTube search results. Default: us; `language` Language of the results. Possible Values — en, es, fr, de, etc. Default: en

### `/youtube/video` — YouTube Video API
The YouTube Video API lets you scrape detailed metadata for any YouTube video including title, views, likes, description, keywords, channel info, key moments, and chapters. Each successful request costs 5 API credits.
- Créditos: Each successful request costs 5 API credits
- Doc: `https://www.scrapingdog.com/documentation/youtube-video-api/`
- Obrigatórios: `video_id` The YouTube Video ID. Found in the video URL after ?v= (e.g., for youtube.com/watch?v=0e3GPea1T
- Opcionais: `country` This parameter specifies the country for the YouTube Videos using a two-letter country code (e.; `language` Language of the results. Possible Values — en, es, fr, de, etc. Default: en

### `/youtube/channel` — YouTube Channel API
The YouTube Channel API lets you scrape comprehensive channel data including about info, subscriber counts, video sections, and YouTube Shorts. Each successful request costs 5 API credits.
- Créditos: Each successful request costs 5 API credits
- Doc: `https://www.scrapingdog.com/documentation/youtube-channel-api/`
- Obrigatórios: `channel_id` This is the YouTube Channel ID. You can find it in the channel URL (e.g., youtube.com/channel/U
- Opcionais: `country` ISO code of the country from which you are seeking YouTube search results. Default: us; `language` Language of the results. Possible Values — en, es, fr, de, etc. Default: en

### `/youtube/comments` — YouTube Comment API
The YouTube Comment API lets you scrape comments from any YouTube video. Returns comment text, likes, reply counts, author details, and pagination tokens for fetching additional pages. Each successful request costs 5 API credits.
- Créditos: Each successful request costs 5 API credits
- Doc: `https://www.scrapingdog.com/documentation/youtube-comment-api/`
- Obrigatórios: `v` Video ID of the YouTube video whose comments you want to scrape. Found in the video URL after ?
- Opcionais: `country` Two-letter country code specifying search location (e.g., us, uk, fr). Default: us; `language` Language of the results. Possible Values — en, es, fr, de, etc. Default: en; `next_page_token` The parameter defines the next page token for retrieving the next page of comments or replies. 


## TikTok

### `/tiktok/profile` — TikTok Profile API
The TikTok Profile API lets you scrape comprehensive profile data for any TikTok user including follower counts, engagement metrics, bio, avatar URLs, and account metadata. Each successful request costs 5 API credits.
- Créditos: Each successful request costs 5 API credits
- Doc: `https://www.scrapingdog.com/documentation/tiktok-profile-api/`
- Obrigatórios: `username` This is the username of the TikTok profile you want to scrape (e.g., nike, mrbeast).

### `/tiktok/post` — TikTok Post Scraper API
The TikTok Post Scraper API lets you extract detailed data for any TikTok post including play counts, likes, comments, shares, video quality details, music info, and full author stats. Each successful request costs 5 API credits.
- Créditos: Each successful request costs 5 API credits
- Doc: `https://www.scrapingdog.com/documentation/tiktok-post-scraper-api/`
- Opcionais: `username` The username of the TikTok profile whose post you want to scrape. Required unless using the url; `post_id` The ID of the post you want to get data for. Required unless using the url parameter.; `url` Full TikTok post URL if you don't want to pass username and post_id separately. Example: https:

### `/tiktok/ads` — TikTok Ads Scraper API
The TikTok Ads Scraper API lets you search and extract ad listings from TikTok's Ad Library by keyword or advertiser ID. Filter by country, date range, and sort order. Each successful request costs 5 API credits.
- Créditos: Each successful request costs 5 API credits
- Doc: `https://www.scrapingdog.com/documentation/tiktok-ads-scraper-api/`
- Opcionais: `query` The keyword you want to search for on TikTok Ads.; `advertiser_id` The unique advertiser ID to search for ads from a specific advertiser. Used together with query; `query_type` Type of search. 1 for keyword search (default), 2 for advertiser ID search.; `country` The parameter specifies the country you want to search from.; `time_period` Custom date range in YYYY-MM-DD..YYYY-MM-DD format. Defaults to the past 12 months.; `sort_by` Sort order for results. Options: last_shown_date_newest_to_oldest (default), last_shown_date_ol; `next_page_token` Token used to fetch the next page of results. Use the next_page_token value from the previous r


## X (Twitter)

### `/x/profile` — X Profile Scraper API
The X Profile Scraper API lets you scrape comprehensive profile data for any X (Twitter) user including follower counts, engagement metrics, bio, profile picture, and account metadata. Each successful request costs 5 API credits.
- Créditos: Each successful request costs 5 API credits
- Doc: `https://www.scrapingdog.com/documentation/x-profile-scraper-api/`
- Obrigatórios: `profileId` This is the user ID or username of the X (Twitter) profile you want to scrape (e.g., elonmusk, 

### `/x/post` — X Post Scraper API
The X Post Scraper API lets you extract detailed data for any X (Twitter) post including engagement metrics (views, retweets, quotes, likes, bookmarks), full post content, timestamp, and complete author profile information. Each successful request costs 5 API credits.
- Créditos: Each successful request costs 5 API credits
- Doc: `https://www.scrapingdog.com/documentation/x-post-scraper-api/`
- Obrigatórios: `tweetId` This is the tweet ID of the X post you want to scrape. You can find it in the post URL (e.g., f


## Instagram / Facebook (doc stub, testar antes)

### `/instagram` — Instagram Scraper API
Refer to the official Scrapingdog documentation for Instagram Scraper API parameters and usage.
- Créditos: não declarado na doc
- Doc: `https://www.scrapingdog.com/documentation/instagram-scraper-api/`

### `/facebook` — Facebook Posts Scraper API
Refer to the official Scrapingdog documentation for Facebook Posts Scraper API parameters and usage.
- Créditos: não declarado na doc
- Doc: `https://www.scrapingdog.com/documentation/facebook-scraper-api/`
- Obrigatórios: `id` This is the internal user ID of the Facebook profile, which you can get from Facebook Profile S
- Opcionais: `next_page_token` The next_page_token is used to get the next page of results.


## Mídia visual Google

### `/google_images` — Google Image Search API
The Google Image Search API lets you retrieve image search results from Google Images including titles, thumbnails, source links, and original dimensions. Each successful request costs 10 API credits.
- Créditos: Each successful request costs 10 API credits
- Doc: `https://www.scrapingdog.com/documentation/google-image-search-api/`
- Obrigatórios: `query` This is a Google Search Query. Example1 - query=pizza
- Opcionais: `html` This will return the full HTML of the Google Images page.; `domain` To obtain local results from a specific country, for example, for India, it will be "google.co.; `country` This parameter specifies the country for the Google search using a two-letter country code (e.g; `cr` The parameter allows you to restrict the search to specific countries. It follows the format co; `uule` It is a parameter that specifies the geographic location or locale for which the search results; `language` Language of the results. Possible Values - en, es, fr, de, etc. For a complete list of supporte; `lr` Limit the search to one or multiple languages. It is used as lang_{language code}. For a comple; `period_unit` This parameter specifies the time unit for retrieving recent images, such as the past minute, h; `period_value` This parameter specifies an optional time duration, used in combination with period_unit to def; `start_date` This parameter specifies the start date for limiting the image search within a specific time ra; `end_date` This parameter specifies the end date for restricting the image search within a specific time r; `chips` This parameter allows filtering of image search results using a suggested search term provided ; `tbs` to be searched - An advanced parameter to filter search results.; `imgar` This parameter specifies the aspect ratio for filtering images.; `imgsz` This parameter specifies the image size filter.; `image_color` This parameter specifies the color filter for images.; `image_type` This parameter specifies the type of images to filter.; `licenses` This parameter specifies the license type for filtering images.; `safe` To filter the adult content set safe to active or to disable it set off.; `nfpr` It excludes the result from an auto-corrected query that is spelled wrong. It can be set to 1 t; `filter` This parameter controls whether the "Similar Results" and "Omitted Results" filters are enabled; `page` This is the page number of Google searches. Its value can be 0 for the first page, 1 for the se

### `/google_videos` — Google Videos API
The Google Videos API retrieves video search results from Google, supporting geographic localization, language preferences, and advanced filtering. Costs 5 API credits per request.
- Créditos: Costs 5 API credits per request
- Doc: `https://www.scrapingdog.com/documentation/google-videos-api/`
- Obrigatórios: `query` This is a Google query.
- Opcionais: `country` This is the ISO code of the country from which you are seeking Google search results.; `page` This is the page number of Google searches. Its value can be 0 for the first page, 1 for the se; `domain` To obtain local results from a specific country, for example, for India, it will be "google.co.; `language` Language of the results. Possible Values - en, es, fr, de, etc.; `lr` Limit the search to one or multiple languages. It is used as lang_{language code}.; `result_time` The "tbs" parameter is often accompanied by additional parameters that define specific search o; `uule` It is a parameter that specifies the geographic location or locale for which the search results; `tbs` To be searched - An advanced parameter to filter search results.; `safe` To filter the adult content set safe to active or to disable it set off.; `nfpr` It can be set to 1 to exclude these results or 0 to include them.; `html` To render the response as raw HTML.

### `/google_shorts` — Google Shorts API
The Google Shorts API retrieves short video results from Google search with thumbnails, GIF previews, account names, and publication dates.
- Créditos: não declarado na doc
- Doc: `https://www.scrapingdog.com/documentation/google-shorts-api/`
- Obrigatórios: `query` This is a Google query. Example: query=shoes
- Opcionais: `html` This will return the full HTML of the Google page.; `domain` To obtain local results from a specific country, for example, for India, it will be "google.co.; `country` This parameter specifies the country for the Google search using a two-letter country code (e.g; `uule` It is a parameter that specifies the geographic location or locale for which the search results; `language` Language of the results. Possible Values - en, es, fr, de, etc. For a complete list of supporte; `lr` Limit the search to one or multiple languages. It is used as lang_{language code}. For a comple; `tbs` to be searched - An advanced parameter to filter search results.; `safe` To filter the adult content set safe to active or to disable it set off.; `nfpr` It excludes the result from an auto-corrected query that is spelled wrong. It can be set to 1 t; `start` Used for skipping a particular number of results (e.g., start=12 skips the first 12 results)

### `/google_lens` — Google Lens API
The Google Lens API enables reverse image search functionality through Scrapingdog, supporting product results, visual matches, and exact matches from Google Lens. Costs 5 API credits per request.
- Créditos: Costs 5 API credits per request
- Doc: `https://www.scrapingdog.com/documentation/google-lens-api/`
- Obrigatórios: `url` The Google Lens URL.
- Opcionais: `query` The parameter specifies the search query you want to execute, just like a standard Google searc; `country` This is the ISO code of the country from which you are seeking Google Lens results.; `language` Language of the results. Possible Values - en, es, fr, de, etc.; `product` This parameter is used to get product results from Google Lens. Set it true to enable it.; `visual_matches` This parameter is used to get visual match results from Google Lens. Set it true to enable it.; `exact_matches` This parameter is used to get exact match results from Google Lens. Set it true to enable it.
