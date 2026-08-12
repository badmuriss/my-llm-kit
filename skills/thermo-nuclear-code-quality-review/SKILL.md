---
name: thermo-nuclear-code-quality-review
description: Perform a strict, read-only maintainability review of a completed implementation diff. Use after impl, before PR preparation, or when asked for a thermonuclear, harsh, deep code-quality, architecture, spaghetti, abstraction, or large-file review. Report evidence-backed findings; never edit code or turn subjective preferences into automatic blockers.
---

# Thermo-Nuclear Code Quality Review

Review the implementation diff as an independent, read-only critic. Favor a few high-confidence structural findings over style nits.

Adapted from Cursor Team Kit's MIT-licensed `thermo-nuclear-code-quality-review` at commit `6dbbdd50cef1bdbfb540f80df8b598d0a546e3aa`.

## Scope

1. Resolve the merge base and inspect the tracked implementation diff plus every untracked, non-ignored source file reported by `git status --porcelain`. Confirm that both sets were inspected, then read only the neighboring code needed to understand them.
2. Read repository instructions and canonical neighboring implementations.
3. Do not modify files, stage changes, commit, or run mutating tools.
4. Treat tests and linters as evidence, not proof of maintainable design.

## Review priorities

Review in this order:

1. Structural regressions and misplaced ownership.
2. A simpler design that deletes branches, modes, helpers, or indirection.
3. New special cases or scattered conditionals that make a shared path harder to reason about.
4. Weak type, API, state, concurrency, or failure boundaries.
5. Duplication of an existing canonical helper or abstraction.
6. Files pushed beyond roughly 1,000 lines by the diff without a strong cohesion reason.
7. Thin wrappers, premature generalization, magic behavior, and legibility problems with material maintenance cost.

Correctness, security, repository contracts, and delivered scope outrank aesthetic simplification. Never recommend a broad refactor without showing that it preserves behavior and reduces concrete complexity.

## Evidence bar

For every finding:

- cite the exact file and line;
- describe the maintenance failure, not a personal preference;
- trace the affected flow far enough to rule out an existing abstraction or constraint;
- propose a specific, semantics-preserving remedy;
- state why the remedy is materially simpler;
- omit the finding when evidence is ambiguous.

Do not flag formatting, naming taste, comments, or test quantity unless they expose a concrete structural problem. Do not demand abstraction merely because code is long. Do not treat the 1,000-line signal as a mechanical failure.

## Output

Return findings first, ordered by severity. Use this shape:

```text
[severity] path:line - concise finding
Evidence: concrete behavior or structure in the diff.
Remedy: bounded, semantics-preserving change.
Why simpler: complexity removed or boundary clarified.
```

If no finding meets the evidence bar, return `No material maintainability findings.` Include a short residual-risk note only when something could not be inspected.
