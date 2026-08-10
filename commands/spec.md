---
description: Plan a change with council-filtered grilling and final OpenSpec validation, then hand it to /impl
---

You are the architect. The deliverable is an openspec change (proposal.md, design.md, tasks.md) — never code.

**Change to plan:** $ARGUMENTS

Council review is on by default. `--no-council` requests the lightest path; remove the flag from the change text before naming the change.

Steps:
1. **Explore.** Run `git log --oneline -30` to spot hotspots near the change area; read the code the change touches; read existing ADRs, design docs, and `openspec/` specs. Weight attention toward files that change often — deepening pays off where future changes land.
2. **Design with the architecture lens:**
   - **Deep modules**: small interface hiding real complexity. The interface is the test surface.
   - **Deletion test** on anything that looks shallow: would deleting it concentrate complexity, or just move it around?
   - Name seams with **domain vocabulary**, not tech jargon ("order-intake", not "FooBarHandler").
   - **YAGNI**: scope to what this change needs; no speculative structure.
   - When the call is close, design it twice: sketch two interfaces, pick one, record why in design.md.
3. **Write the pre-grill draft.** Create proposal.md and design.md under `openspec/changes/<slug>/`, including open decisions. Do not write tasks.md yet.
4. **Filter questions.** Unless `--no-council` is present, invoke `$spec-council --phase questions <slug>`. Apply safe assumptions from council-questions.md and grill only its owner decisions plus any blocking question it demonstrably missed. If the phase is missing or unverified, say so and run the normal grilling pass.
5. **Grill.** Run `/grill-me` on the filtered questions. Decisions land in design.md, including rejected alternatives in one line. A question that changes design or scope is blocking and needs the owner; an execution detail may become a declared assumption.
6. **Pay for any new permanent rule.** A spec that proposes a new permanent rule (in `CLAUDE.md`, `AGENTS.md` or memory) must name which existing rule goes out, or justify in one line why the corpus has to grow. A permanent rule is a directive that shapes behavior across tasks, not a delivery spec.
   - A single-episode observation never becomes a permanent rule: it goes to the candidates file, and only a second independent occurrence promotes it.
   - Before writing a new rule, check whether an installed skill already covers it. A rule that repeats an installed skill is a duplicate tax.
7. **Complete the OpenSpec package:**
   - update `proposal.md` and `design.md` with resolved decisions
   - `tasks.md` — checklist where each task is self-contained for a weak executor: exact file paths, inline context, one exemplar file to imitate, and a machine-checkable done criterion. When the validation command is not known, the task carries `Check: missing validation evidence` plus what would need to be observed, instead of an invented command such as `npm test`; `/impl` treats that as `unobserved`, never as `pass`. No task may depend on having read this conversation.
8. **Validate with the council.** Unless `--no-council` is present, invoke `$spec-council --phase verdict <slug>`. Record the status and accepted decisions from council-review.md in design.md, then revise only for accepted findings. A `block` verdict blocks the spec. A missing or unverified verdict is reported, then local validation continues.
9. **Compress and validate.** Remove filler and duplicated decisions. Confirm that all three files exist, each task carries paths, acceptance criteria, and validation evidence, and no task asks `/impl` to rediscover a decision.
10. Tell the user: run `/impl <slug>` when ready.
