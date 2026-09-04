# Fast worker dispatch

Use for boilerplate, test scaffolding, formatting, simple edits, repetitive changes, and difficult tasks with a narrow scope and objective checks. Choose the fastest available coding subagent with a clean context.

On Codex, follow [model-routing.md](model-routing.md). Prefer Luna at `high` for this lane and use `xhigh` for bounded hard work. Move to Terra when the task stops being mechanical instead of spending Astra on it.

Instruct the worker to:

1. Execute only the assigned task.
2. Match surrounding style, naming, and idioms.
3. Stop on ambiguity, external effects, or scope expansion.
4. Run the assigned checks and return changed files plus evidence.
5. Avoid essays and design expansion.
