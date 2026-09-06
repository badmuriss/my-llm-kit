# Portable model routing

`RoutingPolicy v1` is the versioned source of route defaults. It is external JSON, not scheduler code. It maps roles, risk, tools, context bands, Check strength, abstract lanes, and ordered provider candidates to a requested effort. Provider catalogs separately advertise the agents, models, efforts, tools, context limits, launch modes, and available observations.

The next Canvas run starts from [`routing-policy.seed.json`](./routing-policy.seed.json). Its concrete Luna, Terra, Sol, and Astra entries are policy data. A provider catalog must still advertise an entry before the router can select it.

Use only the concrete Codex IDs below, for direct child dispatch as well as graph work. GPT-5.5 and its dash-suffixed variants are excluded, including fallback. Pass model and effort explicitly and check the resolved profile; do not rely on an inherited host default. If the host cannot honor the route, report that limitation.

| Model | Starting effort | Use and escalation |
|---|---|---|
| `gpt-5.6-luna` | `low` for extraction/checks; `medium` for mechanical edits; `high` for bounded implementation | Clear scope and decisive acceptance. Consider `xhigh` for bounded adversarial review with role-specific evidence and acceptable latency; never a universal default. |
| `gpt-5.6-terra` | `medium`; `low` for straightforward tool work | Everyday implementation and related files. Use `high` for demonstrated reasoning difficulty; consider a stronger model before `xhigh`. |
| `gpt-5.6-sol` | `low`, `medium` | Complex work where more judgment than Terra is useful but Astra's cost is not justified. Prefer Astra low/medium over Sol high/xhigh. |
| `gpt-6-astra` | `low` for bounded difficult work; `medium` for ambiguity, coordination and risk | Architecture, difficult debugging and complete workflows. `high` needs a concrete reason; `xhigh` and `max` remain exceptional. |

These are operating defaults, not measured equivalences between model/effort pairs. The repository research record `research/2026-09-06-codex-model-value.md` contains the evidence and billing assumptions; it is not required for dispatch. Official [Codex model guidance](https://learn.chatgpt.com/docs/models), accessed 2026-09-06, supports the workload distinctions and starting with the lowest sufficient effort.

Sol low/medium remains a cost option: Astra's Standard per-token rates are 2.5 times Sol's in both [API pricing](https://developers.openai.com/api/docs/pricing) and [Codex token-based credits](https://learn.chatgpt.com/docs/pricing), accessed 2026-09-06. Better quality at low effort does not establish lower total task cost. Count reasoning, context, tools and repairs; distinguish API dollars, credits, included allowances and Fast mode. Do not run duplicate full implementations just to benchmark.

The owner requested Astra low/medium for former Sol high/xhigh work using an employee-attributed message on 2026-09-06. Its attribution and comparison are unverified. Preserve this calibration as the owner's choice; do not claim it is a controlled benchmark. The [Astra API migration guide](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-6-astra), accessed 2026-09-06, provides a different starting baseline: preserve effective effort except when migrating from none/minimal.

The graph seed requests at least `medium` for implementation, coordination, integration, material/high risk and checks that are not decisive. Graph low routes must satisfy all minimums; direct dispatch follows the task-based table. `candidate_order` records planner preferences; the portable router selects by lane, effort and catalog cost rank, so the planner must pass model and effort overrides to enforce a specific route. The optional `excluded_models` field is enforced by the router before automatic selection and coordinator fallback, and also blocks explicit overrides. It matches each excluded ID and its dash-suffixed variants. Older policies without this field retain their existing behavior.

Community evidence, reviewed 2026-09-06, supports this task split but is mixed. The [revised adversarial-review benchmark](https://github.com/EveryInc/compound-engineering-plugin/blob/main/docs/solutions/skill-design/benchmark-review-peer-model-and-reasoning-tier.md) favors Luna xhigh on API cost for that bounded persona, with slower turnaround; it supersedes the older Sol-only report. The [Astra workflow experiment](https://dev.to/shinpr/switching-from-gpt-56-sol-to-gpt-6-astra-start-with-medium-effort-25ao) supports medium for broad work and high for specific state/retry interactions. Neither generalizes to every task. A [Luna long-session issue](https://github.com/openai/codex/issues/41318) reports runtime-specific compaction problems: inspect host/version and context behavior before raising effort on a looping task. Do not delegate a tiny task merely to use a cheaper model when the handoff duplicates context.

Before reserving its first attempt, a run validates and copies the policy to `artifacts/routing-policy-v1.json`, records its canonical SHA-256 digest, and resolves later attempts from that immutable snapshot. Editing the source policy cannot alter an active run.

Each persisted routing decision records requested and resolved routing, fallback or escalation reason, policy digest, available usage fields, elapsed time, Check result, retry identity, and grade linkage. An unavailable usage, token, cache, quota, or cost observation is `unavailable`, never zero. Effort labels are provider-specific and are not comparable across providers.

```json
{
  "profiles": [
    {
      "agent": "runtime-agent-id",
      "model": "runtime-model-id",
      "lane": "fast",
      "efforts": ["low", "medium"],
      "tools": ["files", "shell"],
      "max_context_tokens": 32000,
      "cost_rank": 0
    }
  ]
}
```

The planner derives the minimum lane and effort from the pinned policy. It then selects the lowest compatible catalog entry. Catalog cost rank and stable agent and model IDs break ties.

User overrides constrain selection when the runtime advertises them and they meet the policy minimum. An unsupported or unsafe override returns a blocked result. `xhigh` requires an explicit exceptional escalation reason for workers. `max` is supported by the portable contract but is not a default candidate; it is available only through an explicit, exceptional override. `ultra` remains outside the portable contract until it appears in the public model documentation; it is never an alias for `max`. A failed Check does not raise price automatically. `RoutingDecision.to_dict()` carries the fallback or escalation reason; `execution_profile()` remains limited to the strict execution-profile schema.

Refresh the source policy every fourteen days, or early for provider removal, catalog incompatibility, a known price or quota change, a route failure, or an owner request. A refresh uses official provider evidence and bounded local approved-task telemetry. It proposes a new immutable artifact and never changes an active run. Owner-directed calibration may update the seed with its stated source, without claiming measured improvement. An automatic telemetry-based refresh records `insufficient_evidence` unless at least five comparable approved cases support a default change, except for a concrete security or integrity failure. It never runs duplicate full implementations to benchmark routes.

Automatic decomposition uses these roles: coordinator, research,
documentation, implementation, review, verification, and integration. It is a
bounded planning result, not a fixed fan-out. Select the smallest useful
path-safe wave, keep one heavy worker active, and use dynamic delegation only
when the coordinator can narrow the parent's allowance.

Routing resolves one attempt profile. It does not choose a worker count. The coordinator derives the smallest useful wave from ready work, path conflicts, host capacity, and observed resource pressure.
