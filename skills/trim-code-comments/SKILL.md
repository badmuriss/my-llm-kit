---
name: trim-code-comments
description: Review source comments and remove low-value comments that only narrate visible code while preserving rationale, constraints, safety context, public documentation, and tooling directives. Use when asked to trim code comments or remove dumb, redundant, obvious, excessive, or AI-generated comments. Do not run automatically after implementation.
---

# Trim Code Comments

Reduce comment noise without erasing context that future maintainers need.

## Scope

Inspect changed source files by default. Inspect the whole repository only when the user explicitly asks for all comments. Skip generated files, vendored code, dependencies, lockfiles, snapshots, fixtures, and prose documentation.

## Classification

Remove a comment only when the adjacent code expresses the same fact just as clearly. Typical candidates narrate assignments, loops, branches, calls, returns, or obvious names.

Keep comments that carry information the code cannot express directly:

- rationale, trade-offs, invariants, or failure semantics;
- security boundaries, threat assumptions, or fail-open/fail-closed behavior;
- compatibility constraints, workarounds, protocol rules, RFCs, issues, or TODO context;
- architecture, deployment, concurrency, ordering, performance, or lifecycle constraints;
- public API documentation required by the language or repository;
- lint, formatter, coverage, build, code-generation, or type-checker directives;
- non-obvious examples, units, ownership, or data provenance.

When uncertain, keep the comment.

## Workflow

1. Read repository instructions and identify the source diff.
2. Find at most 10 high-confidence candidates unless the user provides another limit.
3. Use adjacent code and `git blame` to understand intent and age.
4. Report each exact comment, path, line, age, and one-sentence reason.
5. Ask which candidates to remove. Do not edit before approval unless the user explicitly requested immediate removal.
6. Remove only approved comments. Do not rewrite useful comments merely to create activity.
7. Run the cheapest formatter, lint, typecheck, or compile check that can catch a damaged directive or syntax boundary.

## Output

Order candidates from most redundant to least. Distinguish `remove` from `keep`; include useful comments when they are close calls so the user can see why they survived.
