# LinkedIn, vagas, acadêmico e patentes

Fonte: doc oficial ScrapingDog, coletada 2026-08-05. `api_key` em query param em toda chamada (omitido abaixo). Base: `https://api.scrapingdog.com`.


## LinkedIn / perfis

### `/profile`: Person Profile Scraper
Scrape publicly available LinkedIn person profiles by their profile ID. Pass type=profile along with the person's LinkedIn ID to retrieve full profile data. Each successful request costs 50-100 credits.
- Créditos: Each successful request costs 50-100 credits
- Doc: `https://www.scrapingdog.com/documentation/person-profile-scraper/`
- Obrigatórios: `id` The ID of any person profile. This can be found inside the URL of any LinkedIn person profile (; `type` Must be set to profile to scrape a person profile.
- Opcionais: `premium` Set to true to use premium proxies to bypass LinkedIn's anti-bot measures. Default: false.; `webhook` Set to true to schedule profile scraping after 2-3 minutes, which increases the success rate. D

### `/profile`: Company Profile Scraper
Scrape publicly available LinkedIn company profiles by their company ID. Pass type=company along with the company's LinkedIn ID to retrieve full company data. Each successful request costs 10 credits.
- Créditos: Each successful request costs 10 credits
- Doc: `https://www.scrapingdog.com/documentation/company-profile-scraper/`
- Obrigatórios: `id` The unique identifier of the company or school profile. It is the last part of the profile URL ; `type` Defines the type of profile to scrape. Set to company for company profiles or school for educat

### `/profile/post`: Post Scraper
Scrape publicly available LinkedIn posts by their post ID. Each successful request costs 5 credits.
- Créditos: Each successful request costs 5 credits
- Doc: `https://www.scrapingdog.com/documentation/post-scraper/`
- Obrigatórios: `id` The post ID of any LinkedIn post. Found in the post's share URL (e.g., 6976499964512243712).


## Vagas

### `/jobs`: Job Search API
Search and scrape LinkedIn job listings by keyword, location, job type, experience level, and work model. Each successful request costs 5 API credits.
- Créditos: Each successful request costs 5 API credits
- Doc: `https://www.scrapingdog.com/documentation/scrape-jobs-search-results/`
- Obrigatórios: `field` Job title or company name to search for (e.g., Product Manager or Amazon).
- Opcionais: `geoid` Unique LinkedIn location ID. Use 92000000 to search for jobs globally. Default: 92000000.; `location` Geographic location string for job listings (e.g., New York, London).; `page` Page number of results. Must be greater than 0. Default: 1.; `sort_by` Filter by posting date. Accepted values: day, week, month.; `job_type` Filter by employment type. Accepted values: temporary, contract, volunteer, full_time, part_tim; `exp_level` Filter by experience level. Accepted values: internship, entry_level, associate, mid_senior_lev; `work_type` Filter by work model. Accepted values: at_work, remote, hybrid.; `filter_by_company` Filter results by a specific company's LinkedIn company ID.

### `/jobs`: Job Overview API
Retrieve detailed information about a specific LinkedIn job posting using its job ID. The job ID can be found via the Jobs Search Scraper or directly from a LinkedIn job URL. Each successful request costs 5 API credits.
- Créditos: Each successful request costs 5 API credits
- Doc: `https://www.scrapingdog.com/documentation/scrape-job-overview/`
- Obrigatórios: `job_id` The ID of the job listing. Can be found via the Jobs Search Scraper.

### `/google_jobs`: Google Jobs Scraping API
The Google Jobs Scraping API retrieves job listings from Google Jobs including job titles, company names, locations, salary ranges, and apply links. Costs 5 API credits per request.
- Créditos: Costs 5 API credits per request
- Doc: `https://www.scrapingdog.com/documentation/google-jobs-api/`
- Obrigatórios: `query` Google Search Query
- Opcionais: `country` Name of the country. The name should be in ISO 3166 Alpha-2 format.; `language` The language of the requested results.; `uule` It is a parameter that specifies the geographic location or locale for which the search results; `domain` To obtain local results from a specific country, for example, for India, it will be "google.co.; `next_page_token` The parameter specifies the next page token, which is used to fetch the subsequent page of resu; `chips` Extra query filters. Chips can be found at the top of the job search page.; `lrad` This parameter will help to search the job results within a particular radius.; `ltype` This parameter will help in filtering the results by work from home.; `uds` The parameter allows filtering of search results. It is a string provided by Google that acts a

### `/indeed`: Indeed Scraper API
The Indeed Scraper API extracts job listings from any Indeed search URL. Pass a valid Indeed search page URL and receive structured JSON with job titles, company names, locations, descriptions, salaries, and more. Each successful request costs 1 API credit.
- Créditos: Each successful request costs 1 API credit
- Doc: `https://www.scrapingdog.com/documentation/indeed-scraper-api/`
- Obrigatórios: `url` The full Indeed search URL to scrape (e.g., https://www.indeed.com/jobs?q=python&l=New+York,NY)


## Acadêmico

### `/google_scholar`: Google Scholar API
The Google Scholar API enables searching academic papers and scholarly content through Google Scholar with support for citation lookups, author searches, year filters, and pagination. Costs 5 API credits per request.
- Créditos: Costs 5 API credits per request
- Doc: `https://www.scrapingdog.com/documentation/google-scholar-api/`
- Obrigatórios: `query` The parameter specifies the search query you want to execute. You can enhance your query by usi
- Opcionais: `html` To render the response as raw HTML. Default: false; `language` Language of the results. Possible Values - en, es, fr, de, etc. For a complete list of supporte; `lr` Limit the search to one or multiple languages. It is used as lang_{language_code}. For a comple; `cites` The cites parameter specifies a unique article ID to initiate a Cited By search. Using this par; `as_ylo` The as_ylo parameter specifies the starting year for search results. For example, setting as_yl; `as_yhi` The as_yhi parameter specifies the ending year for search results. For example, setting as_yhi=; `scisbd` This parameter determines whether to include only abstract results (set to 1) or all results (s; `cluster` This parameter specifies a unique ID for an article to initiate searches for all available vers; `as_sdt` This parameter can function as either a search type or a filter.; `safe` To filter the adult content set safe to active or to disable it set off. Default: off; `filter` This parameter determines whether the filters for "Similar Results" and "Omitted Results" are e; `as_vis` This parameter specifies whether citations should be included in the results. Set it to 1 to ex; `as_rr` This parameter determines whether only review articles should be displayed. Review articles inc; `page` This is the page number of Google searches. Its value can be 0 for the first page, 1 for the se; `results` Number of results per page.

### `/google_scholar/profiles`: Google Scholar Profiles API
The Google Scholar Profiles API enables searching for academic researcher profiles on Google Scholar by author name, returning affiliation, citation counts, and research interests.
- Créditos: não declarado na doc
- Doc: `https://www.scrapingdog.com/documentation/google-scholar-profiles-api/`
- Obrigatórios: `mauthors` The author parameter specifies the author you wish to search for. Additionally, you can include
- Opcionais: `after_author` The parameter specifies the token used to fetch the next set of results. It takes precedence ov; `before_author` The parameter specifies the token used to retrieve the results from the previous page.

### `/google_scholar/author`: Google Scholar Author API
The Google Scholar Author API retrieves comprehensive author information including publication history, citation counts, co-authors, and research interests from Google Scholar profiles.
- Créditos: não declarado na doc
- Doc: `https://www.scrapingdog.com/documentation/google-scholar-author-api/`
- Obrigatórios: `author_id` Author ID of the person you want to get data for.
- Opcionais: `results` Number of results per page.; `language` Language of the results. Possible Values - en, es, fr, de, etc. Default Value - en. For a full ; `view_op` The parameter allows users to access specific sections of a page, offering two choices:Use view; `sort` The parameter is utilized to organize and narrow down articles. The available options are:title; `citation_id` The parameter is essential for fetching the citation of individual articles. It's mandatory whe

### `/google_scholar/author`: Google Scholar Author Citations API
Retrieve citation metrics (h-index, i10-index, yearly citation graph) and individual article citation details for a Google Scholar author using the view_op=view_citation parameter.
- Créditos: não declarado na doc
- Doc: `https://www.scrapingdog.com/documentation/google-scholar-author-citation-api/`
- Obrigatórios: `author_id` Author ID of the person you want to get data for.; `view_op` The parameter allows users to access specific sections of a page, offering two choices:Use view; `citation_id` The parameter is essential for fetching the citation of individual articles. It's mandatory whe
- Opcionais: `language` Language of the results. Possible Values - en, es, fr, de, etc. Default Value - en. For a full 

### `/google_scholar/cite`: Google Scholar Cite API
The Google Scholar Cite API retrieves formatted citations (MLA, APA, Chicago, Harvard, Vancouver) for academic papers using the paper's Google Scholar result ID.
- Créditos: não declarado na doc
- Doc: `https://www.scrapingdog.com/documentation/google-scholar-cite-api/`
- Obrigatórios: `query` This parameter is the ID of an individual Google Scholar organic search result. You can obtain 
- Opcionais: `language` Language of the results. Possible Values - en, es, fr, de, etc. Default Value - en. For a full 


## Patentes

### `/google_patents`: Google Patents API
The Google Patents API enables searching patent records across Google Patents with advanced filtering by inventor, assignee, date range, country, language, and patent status. Costs 5 API credits per request.
- Créditos: Costs 5 API credits per request
- Doc: `https://www.scrapingdog.com/documentation/google-patents-api/`
- Obrigatórios: `query` The parameter specifies the query you wish to search for. You can separate multiple search term
- Opcionais: `page` This is the page number of Google searches. Its value can be 0 for the first page, 1 for the se; `num` Number of results you want to scrape. Its value could be anything between 1 and 100.; `sort` The parameter specifies the sorting method. By default, the results are sorted by Relevance. Th; `clustered` The parameter determines how the results should be grouped. The available option is:true: Class; `dups` The parameter defines the deduplication method, which can either be by Family (default) or by P; `patents` This parameter determines whether Google Patents results are included. (Default is true); `scholar` This parameter determines whether Google Scholar results are included. (Default is false); `before` This parameter specifies the maximum date for the results. The format should be type:YYYYMMDD, ; `after` This parameter sets the minimum date for the results. The format should be type:YYYYMMDD, where; `inventor` This parameter specifies the inventors of the patents. Separate multiple inventors with a comma; `assignee` This parameter specifies the assignees of the patents. Separate multiple assignees with a comma; `country` This parameter filters patent results by country. Separate multiple country codes with a comma ; `language` This parameter filters patent results by language. Separate multiple languages with a comma (,); `status` This parameter filters patent results by their status.; `type` This parameter filters patent results by their type.; `litigation` This parameter filters patent results based on their litigation status.

### `/google_patents`: Google Patent Details API
The Google Patent Details API retrieves detailed information about a specific patent including title, inventors, assignees, filing dates, and prior art keywords. Costs 5 API credits per request.
- Créditos: Costs 5 API credits per request
- Doc: `https://www.scrapingdog.com/documentation/google-patent-details-api/`
- Obrigatórios: `patent_id` The patent ID of the patent (e.g., US11734097B1).
- Opcionais: `language` Language of the results. Possible Values - en, es, fr, de, etc. For a complete list of supporte; `html` This will return the full HTML of the Google page.
