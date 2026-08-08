---
name: streak-timezone
description: compute streak rollover in the user's local tz, not UTC
metadata:
  type: project
---

Streak rollover happens at local midnight in the user's stored timezone, not at
UTC midnight. A user in UTC-8 who checks in at 11pm local must not lose the
streak because it is already past midnight UTC. Read `users.timezone` and roll
over there.
