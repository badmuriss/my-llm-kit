# Deep reasoner dispatch

Use for architecture, complex debugging, algorithms, risky migrations, and trade-off analysis. Choose the least costly permitted model sufficient for the task, with a clean context.

On Codex, follow [model-routing.md](model-routing.md) and pass model plus effort explicitly. Use Sol low/medium when everyday implementation needs more judgment than Luna, but Astra's cost is not justified. Prefer Astra low for bounded difficult work and medium for architecture, ambiguity, security, cross-cutting debugging or final arbitration. Move former Sol high/xhigh work to Astra low/medium. Astra high and above require a concrete task-specific justification; xhigh/max remain exceptional. Never select GPT-5.5 or GPT-5.6 Terra as a fallback.

Instruct the worker to:

1. Derive an independent conclusion from the relevant code.
2. Challenge incorrect premises plainly.
3. Trace the affected flow end to end before changing it.
4. Return a concise decision, key reasons, changed files, and runnable evidence.
5. Stop on ambiguity, external effects, or scope expansion.
