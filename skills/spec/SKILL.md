---
name: spec
description: Plan a codebase change with an architecture lens, resolve blocking product decisions, and emit an OpenSpec change ready for implementation. Use when the user invokes "$spec" or "/spec", asks to spec or architect a change, or wants proposal.md, design.md, and tasks.md. Do not implement code.
---

# Spec

Act as the architect. Produce an OpenSpec change, never implementation code.

Treat text following `$spec` or `/spec` as the change request. Otherwise use the current user request.

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

3. Grill the plan.
   - Use the installed `$grill-me` skill.
   - Resolve questions that change business behavior, design, or scope with the owner, one at a time.
   - Record accepted and rejected decisions in `design.md`; give each rejected alternative one line.
   - Stop with state `blocked` when an unanswered question changes design or scope.
   - Convert only execution-detail questions into declared assumptions, with the rejected alternative in one line.

4. Pay for permanent rules.
   - When proposing a rule for `AGENTS.md`, `CLAUDE.md`, or memory, name the rule it replaces or justify why the corpus must grow.
   - Put a first occurrence in a candidates file. Promote it only after a second independent occurrence.
   - Check installed skills first. Do not duplicate a skill as a permanent rule.

5. Emit `openspec/changes/<slug>/`.
   - `proposal.md`: explain why the change exists and what it changes.
   - `design.md`: capture architecture, decisions, assumptions, and rejected alternatives.
   - `tasks.md`: create a checklist of self-contained tasks for a weak executor. Include exact paths, inline context, one exemplar file, and a machine-checkable done criterion.
   - When no validation command is known, write `Check: missing validation evidence` and state what must be observed. Never invent a command such as `npm test`.
   - Make every task understandable without access to the conversation.

6. Validate the change package.
   - Confirm all three files exist.
   - Confirm every task has scope, paths, acceptance criteria, and validation evidence or the explicit missing-evidence marker.
   - Confirm no task asks the executor to rediscover a decision already made.

7. Tell the user to run `$impl <slug>` or `/impl <slug>` when ready.
