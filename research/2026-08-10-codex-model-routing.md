# Codex model routing for `impl`

Access date: 2026-08-10.

## Question

Which GPT-5.6 model and reasoning effort should `impl` assign to each worker without wasting cost or weakening difficult work?

## Decision rule

Use the cheapest model that can complete a task reliably. Escalate for ambiguity, cross-cutting impact, or high consequences. A useful routing rule must survive two checks: it cannot make Luna `xhigh` the answer to every task, and it cannot assume every Codex runtime accepts Luna as a child.

## Findings

OpenAI's standard short-context API prices are:

| Model | Input per 1M tokens | Cached input | Output per 1M tokens |
|---|---:|---:|---:|
| GPT-5.6 Luna | $0.20 | $0.02 | $1.20 |
| GPT-5.6 Terra | $2.00 | $0.20 | $12.00 |
| GPT-5.6 Sol | $5.00 | $0.50 | $30.00 |

Luna is therefore one tenth of Terra and one twenty-fifth of Sol at these rates. Source: [OpenAI API pricing](https://developers.openai.com/api/docs/pricing), accessed 2026-08-10.

Recent community evidence supports Luna for clear, repetitive, and bounded work, including high reasoning efforts. It does not establish a broad consensus that Luna `xhigh` beats Terra or Sol across implementation work. The sample covered GitHub, Hacker News, Reddit, and YouTube. X was unavailable because the local Firefox profile had no X session, and Reddit collection was partial after HTTP 429 responses. Those gaps weaken any claim of community consensus.

Codex 0.147.0 includes a change that lets Multi-Agent V2 parents use legacy models as leaf workers. Sources: [Codex 0.147.0 release](https://github.com/openai/codex/releases/tag/rust-v0.147.0) and [the merged leaf-model change](https://github.com/openai/codex/commit/6d4d9442c7142c08ac5c5098dfd6e82d8cd9f65a), accessed 2026-08-10.

Compatibility remains uneven. The local Codex 0.147.0 catalog marks Sol and Terra as V2 but Luna as V1. An open issue contains reports through 2026-08-10 of desktop builds rejecting Luna children from Sol or Terra parents. Source: [open Luna child-model issue](https://github.com/openai/codex/issues/35097), accessed 2026-08-10.

## Routing

- Luna `low` or `medium`: search, formatting, boilerplate, and deterministic edits.
- Luna `high`: isolated implementation with a clear acceptance check.
- Luna `xhigh`: difficult but tightly bounded implementation. This is an escalation within the fast lane, not the default.
- Terra `medium` or `high`: multi-file integration, unfamiliar code, and ambiguous debugging.
- Terra `xhigh`: complex cross-cutting debugging.
- Sol `high` or `xhigh`: architecture, security, risky migrations, and final arbitration.

When a runtime rejects Luna as a child, retry with Terra at the same effort and report the fallback. Do not modify the user's model catalog automatically.

## Falsifier

Revisit this routing if task-level evidence across at least five comparable implementations shows Luna `xhigh` produces more repairs or higher total cost than Terra, or when current Codex releases consistently expose Luna as a V2-compatible leaf across CLI and desktop runtimes.
