---
name: checkin-dedup
description: De-dup check-ins before counting
metadata:
  type: domain
---

A user can submit two check-ins for the same habit on the same local day; count
distinct `(user_id, habit_id, local_date)`, never raw check-in rows.

Implemented in `services/streaks.py:compute_streak()` lines 88-126 (migration
0042, commit a1b2c3d). Verified against user 7741's 2026-01 data: 412 raw rows
collapse to 388 distinct days.
