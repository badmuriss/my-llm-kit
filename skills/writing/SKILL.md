---
name: writing
description: Clear writing standards based on Zinsser's principles. Use for documentation, commit messages, PR descriptions, and technical communication.
---

# Writing Standards

Based on William Zinsser's "On Writing Well".

## Core Principles

### Clarity
- One idea per sentence
- Short sentences (<25 words)
- Active voice ("We fixed" not "was fixed")

### Brevity
- Every word must earn its place
- Cut redundant words
- Delete clutter

### Simplicity
- Simple words over complex
- Concrete over abstract
- Specific over vague

## Patterns

### Commit Messages
```
<verb> <what>
```
- `Add user authentication`
- `Fix payment validation`
- `Refactor database queries`

Never: "Fixed stuff", "Updates", "Claude Code"

### PR Descriptions
```
## Summary
[One sentence: what changed]

## Why
[One paragraph: motivation]

## Testing
[How to verify]
```

### Error Messages
```
<What happened>. <What to do>.
```
- `User not found. Check the email.`
- `Payment failed. Retry or contact support.`

### Documentation
1. What it does (one sentence)
2. Why it exists (one paragraph)
3. How to use it (clear steps)
4. Examples (if needed)

## Avoid

- Passive voice
- Redundant words ("in order to" → "to")
- Jargon without explanation
- Hedging ("might", "possibly")
- Long paragraphs (>5 sentences)

## Test Your Writing

- Can you cut 30%?
- Is every word necessary?
- Would you say this to a friend?
- Can someone skim and understand?
