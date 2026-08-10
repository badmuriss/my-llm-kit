---
name: spec
description: Plan a codebase change with an architecture lens, use bounded council review to reduce owner questions and validate the draft, and emit an OpenSpec change ready for implementation. Use when the user invokes "$spec" or "/spec", asks to spec or architect a change, or wants proposal.md, design.md, and tasks.md. Use --no-council only when the user explicitly wants the lightest path. Do not implement code.
---

# Spec

Act as the architect. Produce an OpenSpec change, never implementation code.

Treat text following `$spec` or `/spec` as the change request. Otherwise use the current user request. Remove the optional `--no-council` flag from the request before naming the change.

## Workflow

1. Explore before designing.
   - Run `git log --oneline -30` to find hotspots near the change.
   - Read the code the change touches, existing ADRs, design docs, and relevant files under `openspec/`.
   - Spend more attention on files that change often.

2. Design with an architecture lens.
   - Prefer deep modules: a small interface that hides real complexity. Treat the interface as the test surface.
   - Apply the deletion test to shallow abstractions. Ask whether deletion concentrates complexity or only moves it.
   - Name seams with domain vocabulary, not technical placeholders.
   - Apply YAGNI. Scope only what this change requires.
   - When two interfaces are close, sketch both, select one, and record the reason in `design.md`.

3. Emit the pre-grill draft under `openspec/changes/<slug>/`.
   - Write `proposal.md` with why and what.
   - Write `design.md` with the initial architecture, constraints, assumptions, alternatives, and open decisions.
   - Do not write `tasks.md` until owner decisions are resolved.

4. Filter owner questions with the council unless `--no-council` is present.
   - Invoke `$spec-council --phase questions <slug>`.
   - Read `council-questions.md`. Apply its safe assumptions and send only its owner decisions, plus any blocking question it demonstrably missed, to grilling.
   - If the phase is missing or `unverified`, report that and continue with the normal grilling pass. Never claim the questions were council-filtered.

5. Grill the plan.
   - Use the installed `$grill-me` skill.
   - Resolve the filtered questions that change business behavior, design, or scope with the owner, one at a time.
   - Record accepted and rejected decisions in `design.md`; give each rejected alternative one line.
   - Stop with state `blocked` when an unanswered question changes design or scope.
   - Convert only execution-detail questions into declared assumptions, with the rejected alternative in one line.

6. Pay for permanent rules.
   - When proposing a rule for `AGENTS.md`, `CLAUDE.md`, or memory, name the rule it replaces or justify why the corpus must grow.
   - Put a first occurrence in a candidates file. Promote it only after a second independent occurrence.
   - Check installed skills first. Do not duplicate a skill as a permanent rule.

7. Complete the OpenSpec package.
   - Update `proposal.md` and `design.md` with the resolved decisions.
   - Write `tasks.md` as a checklist of self-contained tasks for a weak executor. Include exact paths, inline context, one exemplar file, and a machine-checkable done criterion.
   - When no validation command is known, write `Check: missing validation evidence` and state what must be observed. Never invent a command such as `npm test`.
   - Make every task understandable without access to the conversation.

8. Validate with the council unless `--no-council` is present.
   - Invoke `$spec-council --phase verdict <slug>`.
   - Read `council-review.md`. Record its status and accepted decisions in a concise `Council review` section in `design.md`, then revise only for accepted findings.
   - Stop with state `blocked` when the verdict is `block`. When it is missing or `unverified`, report that the package lacks council validation and continue with local validation.

9. Compress and validate the change package.
   - Delete filler, duplicated decisions, and prose that restates a heading or another file.
   - Confirm all three files exist.
   - Confirm every task has scope, paths, acceptance criteria, and validation evidence or the explicit missing-evidence marker.
   - Confirm no task asks the executor to rediscover a decision already made.

10. Tell the user to run `$impl <slug>` or `/impl <slug>` when ready.
