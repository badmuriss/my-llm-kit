# Astra and orchestration efficiency: implementation follow-up

Access date: 2026-09-10. Baseline: `e87810d881ed15ee3e32b7793cf3bf7db18d75f1`.
Decision: reduce avoidable control-plane work before changing model defaults.
This is a source/code audit, not a paid model benchmark or representative poll.

## Collection and limitations

Firecrawl searched Reddit and Hacker News, fetched six HN pages (one was a
subthread of the same discussion), searched five paper abstracts and retrieved
the full HTML of arXiv:2508.21433v1. Follow-up Reddit discovery targeted waiting,
instruction conflicts and excessive testing. Returned paid usage across this
pass totals 15 credits: searches with HN scraping, Reddit searches and one paper
scrape. The Research Index did not report paid credits. Known official sources
and accessible Reddit bodies were read through direct web retrieval.

Search snippets were leads, not read papers or independent experiments. The
original “Do NOT orchestrate with Astra” body remained inaccessible. Reddit ages
and HN timestamps can be cached; relative ages are not asserted as exact event
dates. The investigation below was read directly and provides a stronger lead.
No local user transcripts, paid model runs or private provider telemetry were
available. No employee attribution or unsupported effort tier is adopted.

## Evidence cards

### E1: Empty waiting can dominate a coordinator's input volume

Source: https://www.reddit.com/r/codex/comments/1wa9c9d/i_investigated_why_gpt6_astra_burns_quota_so_fast/

A firsthand Plus report names an Astra low coordinator and two Luna xhigh workers.
It reports 47 timeout-only waits, 7.13M raw parent input tokens, almost all cached,
and roughly 68% of parent input volume attributable to those waits. This is one
self-reported trace, not a controlled task-price comparison. The author's quota
attribution to workers uses extrapolation and is not accepted as measured cost.
Decision: internal bounded synchronization, no automatic interruption on timeout.
Do not turn 68% of raw input into a 68% bill-saving promise.

### E2: Over-testing is not resolved merely by choosing low

Source: https://www.reddit.com/r/codex/comments/1wasgkc/astra_is_overtesting_and_verifying_things_by/

The author describes broad database and UI validation and later specifies Astra
low. Replies disagree about what verification was actually warranted, especially
for database migrations. Some commenters make unsupported claims that effort
requires a fixed number of thinking turns. Decision: bound checks by acceptance
and risk; do not ban tests, assume low eliminates process excess, or adopt the
fixed-thinking-turn explanation.

### E3: Instruction migration is useful, but not evidence of a cheaper model

Source: https://www.reddit.com/r/codex/comments/1w7x57n/before_blaming_gpt6_astra_read_its_prompting_guide/

One user reports success using the official documentation skill and recommends
resolving conflicting instructions and unnecessary approval pauses. This is a
single unmetered workflow report. The relevant behavioral guidance was checked
against E6, rather than copying community instructions into the global corpus.

### E4: Review finds real bugs and can also manufacture follow-up work

Source: https://news.ycombinator.com/item?id=49572875

The code-review discussion includes firsthand praise for catching difficult bugs
and objections to false positives, overbroad rewrites and multipersona noise.
The linked vendor benchmark was not independently reproduced. Decision: review
cohesive consequential changes; distinguish blocking evidence from preferences;
never automatically repair every speculative finding. No universal review-quality
or price ranking follows from this discussion.

### E5: Delegation has positive reports too

Sources: https://news.ycombinator.com/item?id=49574227 and
https://news.ycombinator.com/item?id=49570545

The subthread's concrete workflow uses Sol as a lightweight supervisor and Luna
for bulk work; Astra applicability is proposed, not demonstrated. These URLs
belong to one discussion and are not independent experiments. Decision: retain
bounded delegation as an option, not a universal default or universal mistake.
Keep coordinator+worker+integration+repair cost together when comparing routes.

### E6: Official Astra behavior and API boundaries

Source: https://developers.openai.com/api/docs/guides/latest-model?model=gpt-6-astra

The guide warns about conflicting skills/instructions and overly extensive
verification, while recommending preserving an already effective reasoning
effort during migration. It documents async tool calling and configuration
updates that can preserve cache. Those are API capabilities with compatibility
constraints, not proof that the installed Codex/Orca host exposes them. Decision:
use existing portable lifecycle primitives; do not invent host APIs or silently
switch model/effort. No blanket Astra low or xhigh default is introduced.

### E7: Context compression depends on the surrounding harness

Source: https://arxiv.org/html/2508.21433v1
Title: The Complexity Trap: Simple Observation Masking Is as Efficient as LLM
Summarization for Agent Context Management. Version: v1, 2025-08-29.

The SWE-agent experiments compare retaining history, observation masking and
LLM summarization. Masking can match or improve the cost/quality tradeoff, but
some settings lose quality. Appendix E's smaller OpenHands experiment favors
summarization on solve rate rather than masking. Summaries can also lengthen
trajectories; changing old prefixes can interact with caching. These are not
Astra experiments. Decision: keep precise constraints/errors and artifact
locators; remove duplicate observations deliberately, not arbitrary old context.
Do not add another summarizer call after every tool operation.

## Implemented scope

- Coordinator fallback chooses the smallest sufficient effort. Exceptional
  coordinator effort needs an explicit override and reason. Worker protections,
  exclusions and frozen policy snapshots remain intact.
- New contracts declare hard/advisory budget handling. Atomic reservation checks
  prevent concurrent oversubscription from journal-observable counters. Missing
  provider totals are unavailable, not zero; hard unknown limits block new work.
- `wait` performs bounded synchronization in Python and yields on material state
  change, attention or its operational bound. It never launches workers, grades
  results, retries exceptions or adjusts effort. Empty unchanged Host polls no
  longer append receipt/journal noise. The enclosing host still owns tool timeout
  and model re-entry behavior.
- Worker wall-time merges overlapping completed intervals. Coordinator idle time
  remains unavailable rather than being copied from worker elapsed time. No
  token/dollar telemetry is fabricated.
- Execution/routing/research references explain the behavior without loading this
  report on every dispatch. CI exercises the graph runtime and the existing
  complexity gate. Legacy test formats use portable synthetic fixtures instead
  of unavailable ignored developer runs; negative controls remain.

## Remaining boundaries and calibration

This patch does not ingest all real Codex rollout billing, optimize the advisory
candidate order, replace risk minima with measured model recipes, or batch every
check/grade decision into an autonomous scheduler. Monetary budgets are admission
thresholds, not cancellation guarantees for in-flight requests. Old pinned runs
continue their old runtime; new bootstrap uses the installed new source.

Next calibration data should record exact host/version, requested and resolved
model/effort, uncached/cached/output/reasoning categories without double-counting,
coordinator and workers separately, first-pass acceptance, repair count and total
elapsed time. Missing categories stay unavailable. Evaluate equivalent historical
fixtures under explicit budget, not duplicate live production implementations.
Native Windows/macOS, live Orca and actual token savings require separate evidence.

Validation receipts and the final commit identity belong in the pull request,
not a self-referential research file. Runtime unit and local Host integration
checks are not paid-model quality benchmarks.
