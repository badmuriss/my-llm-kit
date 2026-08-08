---
description: Plan a change with an architecture lens + grilling, then emit an openspec change ready for /impl
---

You are the architect. The deliverable is an openspec change (proposal.md, design.md, tasks.md) — never code.

**Change to plan:** $ARGUMENTS

Steps:
1. **Explore.** Run `git log --oneline -30` to spot hotspots near the change area; read the code the change touches; read existing ADRs, design docs, and `openspec/` specs. Weight attention toward files that change often — deepening pays off where future changes land.
2. **Design with the architecture lens:**
   - **Deep modules**: small interface hiding real complexity. The interface is the test surface.
   - **Deletion test** on anything that looks shallow: would deleting it concentrate complexity, or just move it around?
   - Name seams with **domain vocabulary**, not tech jargon ("order-intake", not "FooBarHandler").
   - **YAGNI**: scope to what this change needs; no speculative structure.
   - When the call is close, design it twice: sketch two interfaces, pick one, record why in design.md.
3. **Grill.** Run `/grill-me` on the plan to close business and scope questions with the user. Decisions land in design.md — including rejected alternatives, one line each, so future planning doesn't re-litigate them. Grilling is over when no open question would change the design or the scope. A question that changes design or scope is blocking and needs an answer from the owner; a question that only changes an execution detail goes to `design.md` as a declared assumption, with the alternative not taken in one line. Running without the owner present, a blocking question gets state `blocked` and `/spec` stops without dispatching `/impl`; only an execution detail may become a declared assumption.
4. **Pay for any new permanent rule.** A spec that proposes a new permanent rule (in `CLAUDE.md`, `AGENTS.md` or memory) must name which existing rule goes out, or justify in one line why the corpus has to grow. A permanent rule is a directive that shapes behavior across tasks, not a delivery spec.
   - A single-episode observation never becomes a permanent rule: it goes to the candidates file, and only a second independent occurrence promotes it.
   - Before writing a new rule, check whether an installed skill already covers it. A rule that repeats an installed skill is a duplicate tax.
5. **Emit the openspec change** at `openspec/changes/<slug>/`:
   - `proposal.md` — why + what
   - `design.md` — decided architecture, grilling decisions, rejected alternatives
   - `tasks.md` — checklist where each task is self-contained for a weak executor: exact file paths, inline context, one exemplar file to imitate, and a machine-checkable done criterion. When the validation command is not known, the task carries `Check: missing validation evidence` plus what would need to be observed, instead of an invented command such as `npm test`; `/impl` treats that as `unobserved`, never as `pass`. No task may depend on having read this conversation.
6. Tell the user: run `/impl <slug>` when ready.
