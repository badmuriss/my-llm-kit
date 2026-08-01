---
name: review-changes
description: Systematic code review workflow for evaluating changes against coding standards. Use when reviewing pull requests, commits, diffs, or code changes. Ensures type-safety, maintainability, readability, and adherence to best practices before code is merged.
---

# Review Changes

Systematic workflow for reviewing code changes against established standards.

## When to Use
- Reviewing pull requests
- Evaluating commits or diffs
- Pre-merge code validation
- Refactoring assessment
- Architecture review

## Review Process

### 1. Understand the Change
Read the changes completely before commenting:
- What problem does this solve?
- What is the scope of impact?
- Are tests included?

### 2. Type Safety Review
Check for:
- No `any` types (unless absolutely necessary with clear justification)
- Minimal use of `as` assertions
- Proper type inference usage
- e2e type-safety from API to UI

### 3. Code Organization
Verify:
- Named exports (no default exports unless required)
- No index files used only for re-exports
- Code proximity to usage (not prematurely abstracted)
- Single-file folders are flattened
- Proper file naming (kebab-case)

### 4. React-Specific Review
Check for:
- No constants/functions declared inside components
- Data fetching uses React Query (not useEffect)
- Minimal useEffect usage
- Proper use of `use`, `useTransition`, `startTransition`
- Cache tags use enums (no magic strings)
- Suspense boundaries with error boundaries

### 5. Naming & Clarity
Evaluate:
- Descriptive names (no abbreviations)
- Specific over vague (`retryAfterMs` vs `timeout`)
- No redundant terms (`users` vs `userList`)
- Proper nesting for context (`config.public.ENV_NAME`)
- No magic strings/numbers

### 6. Control Flow
Verify:
- Early returns (no if-else chains)
- Flat code (minimal indentation)
- Hash-lists instead of switch statements
- Proper async/await usage

### 7. Testing
Check for:
- Tests exist for new functionality
- Tests for bug fixes
- Behavior testing (not implementation)
- No "should" in test names (use 3rd person verbs)
- Good describe clause organization

### 8. Best Practices
Confirm:
- No premature optimization
- No over-engineering (KISS, YAGNI)
- No useless abstractions
- Comments converted to code
- Error monitoring/observability considered
- Accessibility (a11y) addressed
- Security (OWASP) followed

### 9. Git Hygiene
Check:
- Commit messages don't include "Claude Code"
- Clear, descriptive commit messages
- Logical commit organization

## Review Output Format

Structure feedback as:

### Required Changes (Blocking)
Critical issues that must be fixed:
- Type safety violations
- Security issues
- Breaking changes without migration path

### Suggested Improvements (Non-blocking)
Recommendations for better code:
- Naming improvements
- Structural optimizations
- Readability enhancements

### Positive Feedback
Highlight good practices:
- Excellent type safety
- Clear naming
- Good test coverage

## Example Review Comments

Good:
```
❌ Line 45: Using `any` type removes type safety.
Suggestion: Define proper interface for user data.
```

```
💡 Line 67: Consider using early return here to reduce nesting.
Current indentation: 4 levels
Target: 2 levels or less
```

```
✅ Excellent use of React Query with proper cache invalidation!
```

Bad:
```
This code is bad.
```

```
Fix the types.
```

## Priority Levels

1. **Critical** - Blocks merge: security, type-safety violations, breaking changes
2. **High** - Should fix before merge: maintainability issues, significant readability problems
3. **Medium** - Nice to have: naming improvements, minor refactoring
4. **Low** - Optional: style preferences, subjective improvements

## Review Checklist

Quick validation before approval:

- [ ] No `any` types without justification
- [ ] Named exports used
- [ ] Early returns implemented
- [ ] No magic strings/numbers
- [ ] Tests included for new features/fixes
- [ ] React best practices followed
- [ ] Proper error handling
- [ ] Clear naming conventions
- [ ] No over-engineering
- [ ] Git commits are clean
