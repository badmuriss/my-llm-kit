---
name: spec
description: Plan a codebase change with an architecture lens, resolve decisions, and emit an OpenSpec change ready for implementation. Use when the user invokes "$spec" or "/spec", asks to spec or architect a change, or wants proposal.md, design.md, and tasks.md. The optional --council flag adds one bounded review. Do not implement code.
---

# Spec

Act as the architect. Produce an OpenSpec change, never implementation code.

Treat text following `$spec` or `/spec` as the change request. Otherwise use the current request. Remove the optional `--council` flag before naming the change.

## Workflow

1. Explore before designing.
   - Run `git log --oneline -30` near the change area.
   - Read the touched code, repository instructions, ADRs, design docs, and relevant OpenSpec files.
   - Spend more attention on files that change often.

2. Design the smallest complete change.
   - Prefer a small interface that hides real complexity.
   - Delete shallow abstractions that only move complexity around.
   - Use domain names, not placeholder architecture terms.
   - Record a second design only when the choice is genuinely close.
   - Keep assumptions and rejected alternatives concise.

3. Resolve owner decisions.
   - Use `$grill-me` only when an unresolved question changes behavior, architecture, or scope.
   - Ask those questions one at a time and record the answers in `design.md`.
   - Treat execution details as declared assumptions when they do not change scope.
   - Stop as `blocked` when a missing owner decision changes the design.

4. Write `openspec/changes/<slug>/proposal.md`, `design.md`, and `tasks.md`.
   - Give every task a stable ID, exact paths, inline context, an acceptance criterion, and one `Check:` line.
   - Load `$frontend-visual-validation` for every task that changes rendered UI.
   - For every changed route or component state, declare `Visual-Scope: <route-or-component> | <state> | <platforms> | <reason>`. Use every canonical profile for general responsive UI and only real targets for platform-specific UI.
   - Add `Visual: <id> | <route-or-component> | <platform> | <width>x<height> | <state>` for every platform in that scope. Do not omit a supported platform to make validation easier.
   - Include loading, empty, error, populated and interaction states when the task changes them. A build, unit test or DOM snapshot is not visual evidence.
   - Use a real machine-checkable command when known.
   - Use one executable plus arguments. Put pipelines, redirection, or multi-step checks in a reviewed repository script.
   - Otherwise write `Check: missing validation evidence` and name the observation still required.
   - Never invent a command such as `npm test`.
   - Make each task understandable without this conversation.

5. Run one council review only when `--council` is present.
   - Invoke `$spec-council --phase verdict <slug>` after the complete draft exists.
   - Keep reviewers independent and bounded by the resource guard.
   - Use the council to challenge the highest-risk decision, hidden assumptions, unnecessary scope, and weak validation.
   - Record accepted and rejected findings in a concise `Council review` section in `design.md`.
   - Treat consensus as advice. Tests and external artifacts decide acceptance.
   - If the council is missing, denied, or `unverified`, report that result without a silent substitute.

6. Compress and validate the package.
   - Remove filler and duplicated decisions.
   - Confirm all three files exist.
   - Confirm every task has scope, paths, acceptance criteria, and exactly one validation contract.
   - Confirm no task asks the executor to rediscover a decided question.

7. Tell the user to run `$impl <slug>` or `/impl <slug>`.

## Boundary

Council is optional because multi-agent debate has mixed results. Use it for explicit pressure-testing, not as routine proof. See [the paper audit](../../research/2026-08-10-stack-paper-audit-sol-review.md).
