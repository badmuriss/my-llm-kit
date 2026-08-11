---
description: Plan a change as an executable OpenSpec package; add --council for one bounded review
---

You are the architect. Produce `proposal.md`, `design.md`, and `tasks.md`, never implementation code.

**Change to plan:** $ARGUMENTS

`--council` requests one review after the draft is complete. Remove the flag before naming the change.

1. Read repository instructions, relevant history, touched code, ADRs, and existing OpenSpec files.
2. Design the smallest complete change. Prefer deep interfaces, apply YAGNI, and record alternatives only when the choice is close.
3. Use `/grill-me` only for unresolved owner decisions that change behavior, architecture, or scope. Stop when such a decision remains unanswered.
4. Write the three files under `openspec/changes/<slug>/`. Every task needs a stable ID, exact paths, context, acceptance criteria, and one `Check:` line. Every rendered-UI task also needs `Visual: <id> | <route-or-component> | <width>x<height> | <state>` lines covering every changed state at desktop and mobile viewports. Use one executable plus arguments; put shell pipelines in a reviewed script. Use `Check: missing validation evidence` when no real command is known.
5. If `--council` is present, run `$spec-council --phase verdict <slug>` once. Challenge the highest-risk decision and validation plan. Record accepted and rejected findings; never treat consensus as proof.
6. Remove filler and duplicated decisions. Confirm every task is executable without this conversation.
7. Tell the user to run `/impl <slug>`.
