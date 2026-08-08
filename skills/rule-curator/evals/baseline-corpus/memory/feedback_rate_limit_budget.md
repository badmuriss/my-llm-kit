---
name: rate-limit-budget
description: Read rate-limit budget from the response header
metadata:
  type: feedback
---

When calling the analytics API, read the remaining budget from the
`X-RateLimit-Remaining` response header and back off when it hits 0; never
hardcode the per-minute limit.

Context: a hardcoded `RATE_LIMIT = 600` in `clients/analytics.py:41` (commit
d7e4f08, 2026-02-28) went stale when the plan changed to 1000/min and caused a
batch of 429s on 2026-03-19. Fixed in commit 0bb91a4.
