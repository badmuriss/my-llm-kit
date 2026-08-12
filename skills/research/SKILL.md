---
name: research
description: "Research with verifiable grounding, claim-level source adjudication, provider routing, and an auditable markdown finding. Use when researching a topic, fact-checking, comparing sources, publishing a number/value/superlative, or when the user requests research --council. Do not use when the answer already lives in the repository."
---

# Research

Run the stations in order. Start from `assets/finding-template.md`. Keep discovery,
evidence quality, and synthesis separate.

## Non-negotiable rules

1. Prefer official documentation and repositories, then primary publications,
   then independent analysis. Use aggregators only to discover original sources.
2. Report disagreements with each source's date. Never resolve them silently.
3. Label a pattern from fewer than five independent cases as `weak sample`.
4. Put a URL and access date beside every number, monetary value, and
   superlative.
5. Open every source used in a finding. Search snippets and worker summaries are
   leads, not evidence.
6. Treat council agreement as criticism, not proof.

## Delegation

Delegate source discovery and ingestion to one fast collector when agent capacity
allows it. Keep protocol definition, source adjudication, synthesis, and council
adjudication with the orchestrator.

Require the collector to return only source URLs, access dates, local converted
paths, provider trail rows, and verification status. Do not accept conclusions or
paraphrased claims from the collector. Open the converted source before using it.

## Station 1: protocol and risk

Write these fields before searching:

- exact question, in one sentence
- decision criterion
- falsifier
- risk: `routine`, `material`, or `high`

Use `high` for medical, legal, financial, safety, security, or other decisions
where a wrong answer can cause material harm. Use `material` when the answer can
drive meaningful cost, architecture, or public claims. Otherwise use `routine`.

## Station 2: route and discover

Choose the narrowest provider that matches the intent. Record every attempt in
the provider trail with intent, provider, tool or endpoint, outcome, and fallback
reason. Never hide a fallback.

| Intent | First route | Fallback |
|---|---|---|
| Local or product fact | Repository, official docs, changelog | General web route |
| Scientific literature | `paper-search` MCP; retain DOI when present | ScrapingDog `google_scholar`, then general web route |
| General public web | ScrapingDog dedicated endpoint | Firecrawl, then host web search |
| Community pulse | `last30days` | ScrapingDog social/news endpoint, then general web route |
| Known document | Open the primary URL, then ingest | ScrapingDog `web_scrape`, then Firecrawl scrape |

For ScrapingDog, load the `scrapingdog` skill, check the key without exposing it,
inspect the live MCP catalog, and select the dedicated endpoint before
`web_scrape`. If the MCP lacks the endpoint, use the skill's documented HTTP
fallback. Use Firecrawl only after the key is absent or a bounded ScrapingDog
attempt fails.

For technology, use the project's repository, official documentation, and
changelog as primary sources. Read volatile values on the official page.

For community pulse, treat engagement as relevance, not truth. Confirm factual
claims against a primary source.

## Station 3: ingest

Run received PDFs, Office files, EPUBs, images, audio, and repositories through
the `ingest` skill before analysis. Return paths and verification status from
delegated ingestion, then open the converted files locally.

Never analyze a multi-column PDF before conversion.

## Station 4: adjudicate claims

Record each material claim in the claim ledger while researching. Include:

- the exact claim
- source URL and access date
- whether the source is primary
- whether it directly supports the claim
- whether it is current enough for the claim
- whether corroboration is independent
- verdict: `accepted`, `limited`, `volatile`, or `rejected`

Do not use one score that hides a fatal weakness. Reject a claim when the source
does not directly support it. Mark it `limited` when only secondary evidence or a
weak sample supports it. Mark it `volatile` when it requires reconfirmation near
publication or action time.

Cross-check material claims against at least one independent source when one is
reasonably available. A publication quoting the same upstream report is not
independent corroboration.

## Station 5: council

Run one bounded council after the first complete draft when any condition holds:

- the user requests `--council`
- risk is `high`
- credible primary sources disagree on a material claim
- a material conclusion rests only on secondary evidence

Before dispatching, run `agent-resource-guard check --intent agent --demand 2
--prune`. If capacity is denied, record the council as `unverified`; do not launch
workers elsewhere.

Dispatch at most two independent reviewers. Do not show either reviewer the
other's response.

1. Ask the source auditor to inspect claim-source entailment, primariness,
   recency, independence, and missing provenance.
2. Ask the falsifier to seek omitted counterevidence, alternate explanations,
   overclaiming, and unresolved uncertainty.

Give reviewers the draft and source artifacts, not the orchestrator's intended
verdict. Require finding-level evidence. Let the orchestrator accept or reject
each finding after reopening the cited source. Record both accepted and rejected
findings. Never decide by majority vote.

For routine or material research without a trigger, record `Status: not run` and
the reason. Allow the user to explicitly request `--no-council` unless the host's
high-stakes policy requires independent review.

## Station 6: save and audit

Save the finding under the project's `research/` directory unless the user names
another destination. Preserve the template sections even when a section says
`None`.

Run:

```bash
python3 skills/research/scripts/audit_finding.py <finding.md>
```

Use `py` instead of `python3` on Windows.

Fix audit failures before publishing. Report the finding's primary-source claims,
secondary-only claims, volatile claims, disagreements, and council status to the
user.

Store durable business insight in the host's persistent memory when available.
Keep research evidence in the finding file.

## Anti-patterns

- answer from memory without opening a source
- treat a search result or AI answer as the underlying source
- cite a number without its date
- confuse repeated reporting with independent corroboration
- present consensus when sources diverge
- use council agreement as evidence
- let the finding exist only in chat

---

Adapted from [research-stack](https://github.com/nett0eth/research-stack)
(Netto, @nett0eth), MIT license.
