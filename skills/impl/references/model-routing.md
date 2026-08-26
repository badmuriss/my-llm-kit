# Portable model routing

`RoutingPolicy v1` is the versioned source of route defaults. It is external JSON, not scheduler code. It maps roles, risk, tools, context bands, Check strength, abstract lanes, and ordered provider candidates to a requested effort. Provider catalogs separately advertise the agents, models, efforts, tools, context limits, launch modes, and available observations.

The next Canvas run starts from [`routing-policy.seed.json`](./routing-policy.seed.json). Its concrete Luna, Terra, and Sol entries are policy data. A provider catalog must still advertise an entry before the router can select it.

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

User overrides constrain selection when the runtime advertises them and they meet the policy minimum. An unsupported or unsafe override returns a blocked result. Unsupported `max` remains blocked. It is never an alias for `xhigh`. A failed Check does not raise price automatically. `RoutingDecision.to_dict()` carries the fallback or escalation reason; `execution_profile()` remains limited to the strict execution-profile schema.

Refresh the source policy every fourteen days, or early for provider removal, catalog incompatibility, a known price or quota change, a route failure, or an owner request. A refresh uses official provider evidence and bounded local approved-task telemetry. It proposes a new immutable artifact and never changes an active run. It records `insufficient_evidence` unless at least five comparable approved cases support a default change, except for a concrete security or integrity failure. It never runs duplicate full implementations to benchmark routes.

Automatic decomposition uses these roles: coordinator, research,
documentation, implementation, review, verification, and integration. It is a
bounded planning result, not a fixed fan-out. Select the smallest useful
path-safe wave, keep one heavy worker active, and use dynamic delegation only
when the coordinator can narrow the parent's allowance.

Routing resolves one attempt profile. It does not choose a worker count. The coordinator derives the smallest useful wave from ready work, path conflicts, host capacity, and observed resource pressure.
