# Portable model routing

The native configuration and catalog of the active host are the concrete sources for model, role, effort, credentials, tools and dispatch choices. This policy supplies only abstract role/risk/check/tool/context minimums; it does not name providers or models. Prefer the least effort and smallest worker set sufficient for the task, and honor the host's configured choices rather than overriding them with repository-wide preferences.

[`routing-policy.seed.json`](./routing-policy.seed.json) is the schema-compatible starting policy. The runtime validates and copies the selected policy to `artifacts/routing-policy-v1.json` before the first attempt and records its canonical SHA-256 digest. Later attempts use that immutable snapshot; changing the source does not affect an active run.

The provider catalog advertises available agents, models, efforts, tools, context limits, launch modes and observations. The router selects only compatible advertised entries that meet policy minimums. An empty `candidate_order` leaves selection to the runtime and native catalog. User overrides constrain selection only when supported and compatible; unsupported or unsafe overrides are blocked. Effort labels are provider-specific and are not comparable across providers.

Each persisted routing decision records requested and resolved routing, fallback or escalation reason, policy digest, available usage fields, elapsed time, Check result, retry identity and grade linkage. An unavailable usage, token, cache, quota or cost observation is `unavailable`, never zero. Snapshot and journal contracts remain runtime-owned; this guide does not define or modify them.

The planner derives the minimum lane and effort from the pinned policy, then selects the lowest compatible catalog entry. Routing resolves one attempt profile, not a worker count. The coordinator derives the smallest useful wave from ready work, path conflicts, host capacity and observed resource pressure. Use the active harness's native dispatch interface and verify the resolved profile when the host exposes it.
