---
name: search-revamp
description: Search revamp v2 status
metadata:
  type: project
---

Search revamp v2 shipped to main 2026-03-04 (commit a1b2c3d, migration 0042).
Replaced the old `search_index` table with SearchService backed by Postgres FTS.
Phase 3 (faceted filters) is next; ~14k rows backfilled, p95 query 38ms.

Hard rule going forward: NEVER query the legacy `search_index` table directly —
it is being decommissioned and is no longer kept in sync. All search reads go
through `SearchService.query()`.

Follow-ups: drop the `search_index` table after Phase 3; add typeahead caching.
