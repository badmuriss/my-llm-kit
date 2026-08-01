---
name: software-engineering
description: Core engineering principles for quality, maintainable code.
---

# Software Engineering Standards

Apply these principles to all code.

## Core Principles

- Type-safety (aim for e2e type-safety)
- Monitoring/observability/profiling/tracing
- Simplicity (KISS, YAGNI, no clutter)
- Functional programming (immutability, high order functions)
- Automation (CI pipelines for builds and tests)

## Naming & Clarity

- Be concrete: `retryAfterMs` > `timeout`, `emailValidator` > `validator`
- Avoid vague terms: `data`, `item`, `list`, `component`, `info`
- Every character must earn its place
- Use nested objects for context: `config.public.ENV_NAME` instead of `ENV_NAME`

## Code Organization

- Keep code close to where it's used (unless used 2-3+ times)
- A folder with a single file should be a single file
- Comments are unnecessary 98% of the time (convert to functions/variables)
- Code is reference, history, and functionality - must be readable as a journal

## Error Handling

- Always provide user feedback
- Log errors with observability tools
- Use HighOrderFunctions for monitoring/error handling/profiling

## Testing

- Test behavior, not implementation
- Write test for each bug fixed (prevents re-occurrence)
- 3rd person verbs (not "should")
- Organize with describe blocks

## Security & Accessibility

- Follow OWASP best practices
- Strive for WCAG 2.0 guidelines
- Don't write pure SQL strings; use query-builders for injection protection

## Avoid

- Premature optimization
- Useless abstractions (functions that mainly call one function, helpers used only once)
- Over-engineering
