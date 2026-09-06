# Codex model and effort calibration

## Protocol

- Question: Which Luna, Terra, Sol and Astra routes offer useful cost/quality tradeoffs for this kit, with GPT-5.5 excluded?
- Decision criterion: Minimize cost and elapsed time per accepted task, including context, reasoning, checks and repairs. Treat API dollars and Codex credits separately.
- Falsifier: Comparable approved-task observations show the chosen route costs more after repairs or fails acceptance more often than another allowed route.
- Risk: material
- Credits used: 53

## Provider trail

| Intent | Provider | Tool or endpoint | Outcome | Credits | Fallback reason |
|---|---|---|---|---|---|
| Read known official pages | OpenAI | Direct HTML and Markdown | Read model pages, pricing, reasoning and Codex guidance | 0 | None; known official sources need no proxy |
| Discover effort guidance | ScrapingDog | Google, two bounded official-domain queries | Relevant official model and Codex pages found and opened | 10 | None |

ScrapingDog account usage increased from 125052 to 125062 during the two queries. Direct downloads were retained temporarily under `/tmp/my-llm-kit-model-research-20260906`; URLs and access dates below provide durable provenance.

## Claim ledger

| Claim | Source | Accessed | Snapshot | Primary | Direct | Current | Independent | Verdict |
|---|---|---|---|---|---|---|---|---|
| Standard API input/output rates per million: Luna $0.20/$1.20; Terra $2/$12; Sol $4/$20; Astra $10/$50 | https://developers.openai.com/api/docs/pricing | 2026-09-06 | /tmp/my-llm-kit-model-research-20260906/pricing.md | yes | yes | yes | no | volatile |
| Codex token-based credits per million input/output: Luna 5/30; Terra 50/300; Sol 100/500; Astra 250/1250 | https://learn.chatgpt.com/docs/pricing | 2026-09-06 | /tmp/my-llm-kit-model-research-20260906/codex-pricing.md | yes | yes | yes | no | volatile |
| Luna fits clear repeated work; Terra everyday work; Sol complex open-ended work; Astra difficult complete workflows | https://learn.chatgpt.com/docs/models | 2026-09-06 | /tmp/my-llm-kit-model-research-20260906/codex-models.md | yes | yes | yes | no | accepted |
| Lower effort favors speed and lower token use; xhigh should have demonstrated benefit | https://developers.openai.com/api/docs/guides/reasoning | 2026-09-06 | /tmp/my-llm-kit-model-research-20260906/reasoning.md | yes | yes | yes | no | accepted |
| Astra supports low through max; GPT-5.6 also supports none in the API | https://developers.openai.com/api/docs/models/gpt-6-astra and https://developers.openai.com/api/docs/models/gpt-5.6-luna | 2026-09-06 | /tmp/my-llm-kit-model-research-20260906/astra.md; luna.md | yes | yes | yes | no | accepted |

## Findings

Use this operating policy, inferred from the official positioning and current prices, rather than claiming a benchmark winner for every effort pair:

| Model | Starting effort | When it earns its cost | Escalation |
|---|---|---|---|
| Luna | low for extraction/check execution; medium for mechanical edits; high for bounded implementation | Clear inputs, narrow scope, decisive acceptance | xhigh for a demonstrated role-specific benefit, including bounded adversarial review |
| Terra | medium; low for straightforward tool work | Everyday implementation and several related files | high for demonstrated reasoning difficulty; consider a stronger model before xhigh |
| Sol | low or medium | More judgment than Terra when Astra's cost is not justified | Prefer Astra low/medium over Sol high/xhigh, per owner calibration |
| Astra | low for bounded difficult work; medium for ambiguity, coordination and risk | Architecture, difficult debugging and complete workflows with costly mistakes | high only with a concrete reason; xhigh/max exceptional |

No GPT-5.5 route, including fallback or dashed variants. Select concrete IDs among the four requested models and pass model plus effort explicitly for direct child dispatch. An inherited or host-selected model is not evidence that this policy was followed.

Astra's Standard API and token-credit rates are 2.5 times Sol's for the same token categories. Equal token counts therefore favor Sol on cost. Astra only offsets that premium through fewer billed tokens, fewer attempts, or a result valuable enough to justify it. For equal-priced token mixtures, it needs less than 40% of Sol's tokens to cost less; this is arithmetic, not an observed workload result. Luna costs one tenth of Terra per corresponding token category. All ratios derive from [API pricing](https://developers.openai.com/api/docs/pricing) and [Codex pricing](https://learn.chatgpt.com/docs/pricing), accessed 2026-09-06.

API rates above use short context, excluding tools, cache writes and Fast mode. Codex included allowances depend on the task and plan; token-based credits do not establish an exact message limit. Fast mode adds another premium: current docs list 2x for the Astra API and 2.5x for Codex credits. Keep the billing surface explicit. Sources: pricing pages above and [Astra model](https://developers.openai.com/api/docs/models/gpt-6-astra), accessed 2026-09-06.

## Disagreements

The owner supplied an employee-attributed claim that Astra low outperforms Sol high. Its attribution and benchmark conditions remain unverified. Official Astra API migration guidance says to preserve effective effort except when migrating from none/minimal; Codex guidance recommends trying lower effort and evaluating the result. These are different migration baselines, not a measured cost comparison. Keep the owner's low/medium calibration as an operating choice. Sources: [Astra guide](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-6-astra) and [Codex models](https://learn.chatgpt.com/docs/models), accessed 2026-09-06.

The previous local research used Sol's older $5/$30 rates. Current $4/$20 pricing is promotional through at least 2026-11-21. Source: [Sol model](https://developers.openai.com/api/docs/models/gpt-5.6-sol), accessed 2026-09-06.

## Open questions

No controlled local results compare Luna high against Terra medium or Sol medium against Astra low. The initial official-source pass established no measured model/effort matrix; the community follow-up below adds narrow experiments with stated limits. The reported GPT-5.5 dispatch has no receipt in this task; the repository permits it through unrestricted catalog selection and broad cheapest-model instructions, but that does not prove which path produced that dispatch.

## Council review

- Status: not run
- Reason: Primary sources establish prices and roles; unverified performance claims are not accepted as benchmark facts.
- Accepted findings: None.
- Rejected findings: None.

## Sources consulted

- https://developers.openai.com/api/docs/pricing, accessed 2026-09-06.
- https://developers.openai.com/api/docs/models/compare, accessed 2026-09-06.
- https://developers.openai.com/api/docs/models/gpt-5.6-luna, accessed 2026-09-06.
- https://developers.openai.com/api/docs/models/gpt-5.6-terra, accessed 2026-09-06.
- https://developers.openai.com/api/docs/models/gpt-5.6-sol, accessed 2026-09-06.
- https://developers.openai.com/api/docs/models/gpt-6-astra, accessed 2026-09-06.
- https://developers.openai.com/api/docs/guides/latest-model?model=gpt-6-astra, accessed 2026-09-06.
- https://developers.openai.com/api/docs/guides/reasoning, accessed 2026-09-06.
- https://learn.chatgpt.com/docs/models, accessed 2026-09-06.
- https://learn.chatgpt.com/docs/pricing, accessed 2026-09-06.

## Trial by fire

- Primary-source claims: Published prices, supported efforts and intended workloads; not independent quality benchmarks.
- Secondary-only claims: Employee-attributed Astra comparison remains unverified and is not used to claim universal cost dominance.
- Volatile claims: Prices, credits, available models and runtime efforts need refresh. No paid model benchmark was run.

## Implementation and checks

- [x] Research four-model costs and effort guidance, with uncertainty and billing scope.
- [x] Update shared dispatch instructions and skill routing guidance, preserving unrelated edits.
- [x] Exclude GPT-5.5 in new routing policies, including explicit overrides and coordinator fallbacks; preserve older pinned policies.
- [x] Verify routing regressions, policy pinning, schema, relevant integration checks and Ruff.
- [x] Report the selection rule and remaining host/installed-runtime limits.

Validation: 26 routing tests, 6 runtime-pinning tests and 1 Host E2E passed on Linux. Ruff 0.16.5, current/older-shape policy JSON Schema validation, both edited skills' validators, research audit and diff whitespace checks passed. No model calls were used as benchmarks. No real installer was run. Existing pinned runs keep their previous policy/runtime; the exclusion applies when the updated policy is loaded. Actual Orca UI dispatch and Windows execution were not observed. Direct tool dispatch outside the router follows the updated shared instructions, whose resolved-model requirement remains host-dependent.

## Community follow-up and publication

The owner requested a community-focused follow-up, especially Reddit, followed by commit and push of all current worktree changes. Compare firsthand task reports, opposing experiences and effort-specific observations; do not count reposts or configuration examples as independent performance evidence.

- [x] Read Reddit discussions and supporting community experiments/issues beyond search snippets.
- [x] Record sample limits and any evidence-backed routing adjustment.
- [x] Inspect all worktree changes and reuse applicable passing checks.
Publication is authorized for all current worktree changes on `main`; the final commit ID and verified push receipt are reported in the conversation to avoid a self-referential commit record.


### Community collection and evidence

Access date for every source below: 2026-09-06. This is a purposive sample of six Reddit discussions and selected visible comments, two GitHub issues plus the original and revised benchmark they reference, one DEV experiment, one Hacker News discussion (eight top-level comments via its API), and one X post. It is not a representative poll. Reddit pages expose relative ages and cached views; older Sol/Terra/Luna threads predate the Astra discussions. Expandable replies were not exhaustively loaded. Search-result recommendations and linked-but-unopened posts were not counted as evidence.

Seven ScrapingDog Google queries and three successful static page scrapes plus one X post request used 43 credits. Seven Reddit scrapes and one Hacker News scrape returned HTTP 400. Firecrawl status showed no remaining credits, so no scrape was submitted there. Host web retrieval read Reddit and the benchmark documents; Hacker News HTML failed there too, then its public Firebase API supplied the story and selected comments. The final ScrapingDog account usage was 125105, up from 125062 at the start of this follow-up, matching 43 credits; total collection across both passes was 53 credits. Raw responses stay in `/tmp/my-llm-kit-community-20260906`; this report retains the source URLs and adjudicated observations. X search found reposts of the supplied employee-attributed message, but did not establish the original author; its attribution remains unverified.

| Source | Observed evidence | Assessment |
|---|---|---|
| [Reddit: what actually worked](https://www.reddit.com/r/codex/comments/1uz7pua/sol_vs_terra_vs_luna_what_actually_worked_for_me/) | A monorepo user favors Luna high for bounded support work and stronger models for critical integration. Replies favoring Luna high implementation coexist with complaints about incompleteness, handoff overhead and Terra. | Firsthand anecdotes, mixed tasks and users; supports bounded use, not universal rankings. |
| [Reddit: are Luna/Terra worth it](https://www.reddit.com/r/codex/comments/1v8whla/is_luna_or_terra_even_worth_it/) | Several commenters use Luna high for specified implementation and Terra medium/high for broader work. Others describe subsequent cleanup by Sol. | Positive and negative reports retained; popularity and self-reported success rates are not measured reliability. |
| [Reddit: what about Terra](https://www.reddit.com/r/codex/comments/1vzo6lc/everyones_talking_about_sol_and_luna_but_what/) | Users praise Terra medium/high for fast pairing and iterative work; others prefer Luna's price or Sol's judgment. A commenter reports compaction-related incompleteness. | No consensus to remove Terra; speed-sensitive interactive work is a plausible niche. |
| [Reddit: Astra low versus Luna max experiment](https://www.reddit.com/r/codex/comments/1w8hmcz/astra_low_vs_luna_max_implementer_experiment_part/) | The author reports faster completion and no repairs with Astra low versus repeated repairs with Luna max on one prepared feature. Both used a Sol coordinator. | One task, author-judged quality, subscription-metered usage and context/coordinator confounds. Evidence against assuming Luna max always saves overall cost. |
| [Reddit: Astra low versus Sol high](https://www.reddit.com/r/codex/comments/1w7tiqk/gpt_6_astra_low_vs_gpt_56_sol_high/) | Positive Astra low reactions coexist with complaints about allowance consumption. One recommendation is explicitly based partly on other people's reports. | Low-confidence sentiment; do not count hearsay as an independent run. |
| [Reddit: more than Astra low](https://www.reddit.com/r/codex/comments/1w8v3up/do_you_really_need_more_than_astra_lowlight/) | The author finds low sufficient after Sol high and describes a modest cost increase. Replies name scientific/research work as reasons for higher effort. | Unspecified workload and no controlled telemetry; supports trying low, not banning higher effort. |
| [DEV: Astra effort comparison](https://dev.to/shinpr/switching-from-gpt-56-sol-to-gpt-6-astra-start-with-medium-effort-25ao) | One repository, one analysis/implementation/review per condition. Reported API-equivalent totals: Astra low $26.97, medium $25.67, high $37.23, Sol high $31.79. High's implementation handled persisted-state/retry interactions better; medium found a startup failure high missed. | Author-run experiment, non-blind model-assisted assessment; evaluator and later repairs excluded. Medium is a reasonable broad-task start, high can be justified by a specific integrity interaction. No general cost guarantee. |
| [GitHub: Luna long-session regression](https://github.com/openai/codex/issues/41318) | Reporter contrasts Windows CLI builds and describes xhigh/max context reprocessing, delay and nonconvergence. Completed runs improved correctness with effort. | Reported runtime-specific behavior, not a verified universal Luna defect or confirmed root cause. Check host version and context behavior before escalating a looping task. |
| [GitHub issue criticizing Luna xhigh](https://github.com/EveryInc/compound-engineering-plugin/issues/1261) | Cites an older Sol-medium recommendation as contrary to the shipped Luna-xhigh choice. | Superseded evidence chain; the original benchmark explicitly points to an update. Not independent evidence that Luna xhigh is the wrong choice. |
| [Original review benchmark](https://github.com/EveryInc/compound-engineering-plugin/blob/main/docs/plans/2026-07-18-adversarial-peer-benchmark-report.md) | Sol medium compared favorably with Sol high for this adversarial-review persona; no Luna arm in the original report. | Historical result; do not use it to reject an untested model. |
| [Revised review benchmark](https://github.com/EveryInc/compound-engineering-plugin/blob/main/docs/solutions/skill-design/benchmark-review-peer-model-and-reasoning-tier.md) | The update adopts Luna xhigh for adversarial review: similar detection in its corpus and estimated lower API spend, with slower median and tail latency. | Bounded persona, reversed-defect corpus, model judge and private harness. Useful exception for cost-sensitive read-only review; not evidence for long implementation or current universal savings. |
| [Hacker News comment](https://news.ycombinator.com/item?id=49426959) | A user describes Sol spending excessive effort on early steps of broad work. Adjacent pricing comments mix direct API and reseller discounts. | Effort not specified; qualitative warning about end-to-end completion, not a model/effort comparison. |
| [X: Nicholas Dunzelman](https://x.com/nicdunz/status/2096689004821319770) | Claims Astra low and Sol high cost the same per task, without showing workload or telemetry. | Opinion only; cannot override the official per-token rates or establish task-cost equality. |

### Community-informed routing decision

Keep the four-model restriction and GPT-5.5 exclusion. Give Luna high an explicit place for substantive but bounded implementation, while retaining low/medium for mechanical work. Allow Luna xhigh as a justified, cost-sensitive, bounded adversarial-review experiment when latency is acceptable; do not promote xhigh/max to a default or bypass graph risk/escalation checks. Keep Terra medium/high for interactive implementation, Sol low/medium for stronger judgment at lower per-token cost than Astra, and Astra low/medium for difficult work. Astra high remains justified for concrete cross-cutting state, retry or integrity concerns.

A model switch is not free: a stronger planner handing a tiny task to a cheap worker can duplicate context and coordination. Keep one sufficient worker unless independent work justifies delegation. When a task loops or repeatedly compacts, inspect the runtime and task boundary before increasing effort. These are bounded operating inferences from the sources above, not a measured population optimum.

The revised benchmark supersedes the issue's old evidence; it does not conflict with the Windows long-session report because the workload and runtime differ. The DEV experiment and Reddit reports likewise cover different tasks. No council is needed to resolve a same-condition primary-source disagreement: no such replicated comparison was established. No claim of community consensus or independently reproduced benchmark is made.
