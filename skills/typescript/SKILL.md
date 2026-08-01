---
name: typescript
description: TypeScript/JavaScript standards for type-safe, maintainable code.
---

# TypeScript/JavaScript Standards

## Type Safety

- Use strict TypeScript, never use `any`
- Almost never use `as` casting
- Aim for e2e type-safety (API to Database to UI)
- Let the compiler infer response types whenever possible
- Use query-builders instead of raw SQL for type-safety and injection protection

## Code Structure

- Always use named exports; avoid default exports unless required
- Don't create index files only for exports
- Prefer `await/async` over `Promise().then()`
- Prefer types over interfaces
- Leave types close to where they're used
- Unused vars should start with `_` (or don't exist at all)

## Naming & Clarity

- Don't abbreviate; use descriptive names
- Always use early return over if-else
- Prefer hash-lists over switch-case
- Follow conventions: `SNAKE_CAPS` for constants, `camelCase` for functions, `kebab-case` for files
- Avoid indentation levels, strive for flat code
- Prefer string literals over string concatenation

## Avoid

- Redundant names: `users` not `userList`
- Suffixes like Manager, Helper, Service unless essential
- Over-long names: `retryCount` over `maximumNumberOfTimesToRetryBeforeGivingUpOnTheRequest`
- Magic strings/numbers: extract to named constants or enums

## Tooling

- Use pre-commit hooks for linting/parsing/removing dead code
