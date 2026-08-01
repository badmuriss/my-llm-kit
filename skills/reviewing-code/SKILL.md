---
name: reviewing-code
description: Code review workflow for evaluating changes against standards. Use when reviewing pull requests, commits, or diffs.
---

# Code Review Standards

Systematic review for quality and consistency.

## Review Checklist

### Type Safety
- [ ] No `any` types
- [ ] Minimal `as` casting
- [ ] E2E type coverage

### Clarity
- [ ] Descriptive names
- [ ] Early returns
- [ ] Flat code structure
- [ ] No magic strings/numbers

### React (if applicable)
- [ ] Pure components
- [ ] React Query for data
- [ ] Suspense/Error boundaries

### Security
- [ ] Input validation
- [ ] Query builders (no raw SQL)
- [ ] No exposed secrets

### Accessibility
- [ ] Semantic HTML
- [ ] ARIA labels
- [ ] Keyboard navigation

### Testing
- [ ] Tests behavior
- [ ] Bug fixes have tests

## Output Format

```
## Summary
[What changed]

## Issues
### Critical (blocks merge)
- [Issue]: [Fix]

### Suggested (improve quality)
- [Issue]: [Fix]

## Status
✅ Approved | ⚠️ Minor changes | ❌ Needs work
```

## Priority

1. **Critical**: Security, type-safety, breaking changes
2. **High**: Maintainability, readability
3. **Medium**: Naming, minor refactoring
4. **Low**: Style preferences
