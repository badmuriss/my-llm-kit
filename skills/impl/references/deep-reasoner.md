# Deep reasoner dispatch

Use for architecture, complex debugging, algorithms, risky migrations, and trade-off analysis. Choose the strongest available coding subagent with a clean context.

On Codex, follow [model-routing.md](model-routing.md). Start with Terra for implementation judgment. Use Sol for demanding implementation and high-stakes review. Reserve Astra for frontier architecture, security, cross-cutting debugging, or final arbitration. Use `max` only for a bounded exceptional case with an explicit reason.

Instruct the worker to:

1. Derive an independent conclusion from the relevant code.
2. Challenge incorrect premises plainly.
3. Trace the affected flow end to end before changing it.
4. Return a concise decision, key reasons, changed files, and runnable evidence.
5. Stop on ambiguity, external effects, or scope expansion.
