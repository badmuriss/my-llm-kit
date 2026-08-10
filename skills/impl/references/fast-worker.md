# Fast worker dispatch

Use for boilerplate, test scaffolding, formatting, simple edits, repetitive changes, and difficult tasks with a narrow scope and objective checks. Choose the fastest available coding subagent with a clean context.

On Codex, follow [model-routing.md](model-routing.md). Prefer Luna for this lane. Use `xhigh` only for a bounded hard task, not as a blanket default.

Instruct the worker to:

1. Execute only the assigned task.
2. Match surrounding style, naming, and idioms.
3. Stop on ambiguity, external effects, or scope expansion.
4. Run the assigned checks and return changed files plus evidence.
5. Avoid essays and design expansion.
