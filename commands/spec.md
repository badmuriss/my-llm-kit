---
description: Plan a change as an executable OpenSpec package; add --council for one bounded review
---

You are the architect. Produce `proposal.md`, `design.md`, and `tasks.md`, never implementation code.

**Change to plan:** $ARGUMENTS

`--council` requests one review after the draft is complete. Remove the flag before naming the change.

1. Read repository instructions, relevant history, touched code, ADRs, and existing OpenSpec files.
2. Design the smallest complete change. Treat the project as an MVP unless repository evidence shows an active external contract. Prefer a clean breaking change or focused rewrite over migrations, adapters, aliases, dual paths and fallbacks. Prefer deep interfaces, apply YAGNI, and record alternatives only when the choice is close.
3. Use `/grill-me` only for unresolved owner decisions that change behavior, architecture, or scope. Stop when such a decision remains unanswered.
4. Write the three files under `openspec/changes/<slug>/`. Every task needs a stable ID, exact paths, context, acceptance criteria, and one `Check:` line. Choose the smallest existing check that catches a realistic failure. Do not create test work merely to pin constants, defaults, toggles, deletions, trivial passthroughs or type-system guarantees. Add tests for requested coverage, likely regressions, non-trivial behavior, security, data integrity or public contracts. Load `frontend-visual-validation` for rendered UI. For each changed surface and state, declare `Visual-Scope: <route-or-component> | <state> | <platforms> | <reason>`, then add one `Visual: <id> | <route-or-component> | <platform> | <width>x<height> | <state>` per declared platform. General responsive UI uses every canonical profile; platform-specific UI uses only its real targets. Use one executable plus arguments; put shell pipelines in a reviewed script. Use `Check: missing validation evidence` when no real command is known.
5. If `--council` is present, run `$spec-council --phase verdict <slug>` once. Challenge the highest-risk decision and validation plan. Record accepted and rejected findings; never treat consensus as proof.
6. Remove filler and duplicated decisions. Confirm every task is executable without this conversation.
7. Tell the user to run `/impl <slug>`.
