# Codex worker routing

Use the cheapest model that can finish the task reliably. Set `fork_turns="none"` for a clean worker context.

| Work | Model | Effort |
|---|---|---|
| Search, boilerplate, formatting, deterministic edits | `gpt-5.6-luna` | `low` or `medium` |
| Isolated implementation with a clear check | `gpt-5.6-luna` | `high` |
| Difficult but tightly bounded implementation | `gpt-5.6-luna` | `xhigh` |
| Multi-file integration, unfamiliar code, ambiguous debugging | `gpt-5.6-terra` | `medium` or `high` |
| Complex cross-cutting debugging | `gpt-5.6-terra` | `xhigh` |
| Architecture, security, risky migration, final arbitration | `gpt-5.6-sol` | `high` or `xhigh` |

Do not default every worker to `xhigh`. Raise effort after the task proves harder than its initial classification. Prefer a stronger model when ambiguity or consequence matters more than raw execution speed.

Before dispatch, use the host's exposed model list. If a Sol or Terra parent rejects Luna as a child, retry the same task with Terra at the same effort and report the routing fallback. Do not patch the user's model catalog automatically.

These defaults reflect current OpenAI pricing and Codex behavior as checked on 2026-08-10. Luna costs one tenth of Terra and one twenty-fifth of Sol per standard short-context token, for both input and output. Codex 0.147.0 includes leaf-model support, but some desktop runtimes still expose Luna as Multi-Agent V1 and reject it under a V2 parent.

Sources:

- [OpenAI API pricing](https://developers.openai.com/api/docs/pricing), accessed 2026-08-10.
- [Codex 0.147.0 release](https://github.com/openai/codex/releases/tag/rust-v0.147.0), accessed 2026-08-10.
- [Leaf-model support change](https://github.com/openai/codex/commit/6d4d9442c7142c08ac5c5098dfd6e82d8cd9f65a), accessed 2026-08-10.
- [Open Codex Luna child-model report](https://github.com/openai/codex/issues/35097), accessed 2026-08-10.
