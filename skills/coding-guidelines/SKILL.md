---
name: coding-guidelines
description: Comprehensive coding standards for TypeScript/JavaScript projects with React. Use when writing new code, refactoring, or setting up project structure. Focuses on e2e type-safety, readability, and maintainability. Apply to any code creation, file structuring, or technical decision-making tasks.
---

# Coding Guidelines

Apply these standards to all TypeScript/JavaScript code. Focus on type-safety, readability, and maintainability.

## Core Principles

### Type Safety
- Never use `any`; almost never use `as`
- Let the compiler infer response types whenever possible
- Use e2e type-safety across the entire stack
- Use query-builders instead of pure SQL strings for type-safety and SQL-injection protection

### Code Organization
- Always use named exports; don't use default exports unless required
- Don't create index files only for exports
- Keep code close to where it's used unless reused 2-3 times
- A folder with a single file should be a single file

### Async/Await
- Prefer `await`/`async` over `Promise().then()`
- Handle errors with try-catch blocks

### Variable Management
- Unused vars should start with `_` (or not exist at all)
- Don't declare constants or functions inside React components; keep them pure

## Naming Conventions

### General Rules
- Don't abbreviate; use descriptive names
- Every character must earn its place
- Follow language conventions:
  - `SNAKE_CAPS` for constants
  - `camelCase` for functions
  - `kebab-case` for file names

### Specificity
- Be concrete: `retryAfterMs` > `timeout`
- `emailValidator` > `validator`
- Avoid vague terms: `data`, `item`, `list`, `component`
- Examples:
  - `userPayment` instead of `userPaymentData`
  - `users` instead of `userList`

### Brevity
- Remove redundancy: `users` not `userList`
- Avoid suffixes like `Manager`, `Helper`, `Service` unless essential
- Prefer: `retryCount` over `maximumNumberOfTimesToRetryBeforeGivingUpOnTheRequest`

### Context Through Nesting
- Use nested objects to provide context
- Example: `config.public.ENV_NAME` instead of `ENV_NAME`

## String Handling
- Prefer string literals over string concatenation
- Don't use magic strings; extract to named constants or enums

## Control Flow

### Early Returns
- Always use early return over if-else
- Avoid indentation levels; strive for flat code

### Switch Alternatives
- Prefer hash-lists over switch-case

Example:
```typescript
// Good
const handlers = {
  create: handleCreate,
  update: handleUpdate,
  delete: handleDelete,
} as const;

const handler = handlers[action];
```

## React Guidelines

### Component Purity
- Don't declare constants or functions inside components; keep them pure
- Extract logic outside component scope

### Data Fetching
- Don't fetch data in `useEffect`; use React Query
- You probably shouldn't use `useEffect`
- Use `use`, `useTransition`, and `startTransition` instead of `useEffect`

### React Query
- Don't use magic strings for cache tags; use an enum/factory
- Use enum for React Query cache strings
- Prefer `<Suspense>` and `useSuspenseQuery` over React Query `isLoading`

### Error Handling
- Use `errorBoundary` with retry button

## Software Engineering Principles

### Focus Areas
- e2e type-safety
- Error monitoring/observability
- Accessibility (a11y, WCAG 2.0 guidelines)
- Security (OWASP best practices)
- Automated tests

### Avoid Over-Engineering
- Don't pre-mature optimize
- KISS (Keep It Simple, Stupid) and YAGNI (You Aren't Gonna Need It)
- Avoid useless abstractions:
  - Helper functions used only once
  - Functions that mainly call one function

### Comments
- Comments are unnecessary 98% of the time
- Convert comments to functions or variables instead
- Code is reference, history, and functionality; it must be readable as a journal

### Monitoring and Error Handling
- Use Higher Order Functions for monitoring/error handling/profiling

## Testing

### Testing Philosophy
- Always test behavior, never test implementation
- Write a test for each bug you fix; you'll never have to fix it again

### Test Writing
- Don't use "should"; use 3rd person verbs
- Abuse the `describe` clauses for organization

## Git Workflow
- Do not include "Claude Code" in commit messages
