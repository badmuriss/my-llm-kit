# Fast worker dispatch

Use for boilerplate, test scaffolding, formatting, simple edits, repetitive changes, and difficult tasks with a narrow scope and objective checks. Choose the fastest available coding subagent with a clean context.

On Codex, follow [model-routing.md](model-routing.md). Prefer Luna `low` for extraction and check execution, or `medium` for mechanical edits. Use `high` for substantive bounded implementation with decisive acceptance. Reserve `xhigh` for role-specific evidence, such as cost-sensitive bounded adversarial review when latency is acceptable; it is not a default for long implementation. Move to Sol `low` or `medium` when the work needs broader implementation judgment. Pass model and effort explicitly; never fall back to GPT-5.5 or GPT-5.6 Terra.

Instruct the worker to:

1. Execute only the assigned task.
2. Match surrounding style, naming, and idioms.
3. Stop on ambiguity, external effects, or scope expansion.
4. Run the assigned checks and return changed files plus evidence.
5. Avoid essays and design expansion.
