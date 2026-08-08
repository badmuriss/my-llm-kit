---
name: destructive-migrations
description: Review gate for destructive migrations
metadata:
  type: feedback
---

Every destructive migration (a DROP or data-losing ALTER) gets a second pair of
eyes before it runs against prod.

Origin: migration 0031 (commit 4f9a2c1, 2026-02-14) dropped `habit_logs.note`
without review and lost ~3,200 rows; reverted via the 0031b hotfix (commit
8c1d0e2) the same night. PR #214 added the review checklist.
