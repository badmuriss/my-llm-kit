# Research report protocol

Use this for a requested research report or consequential synthesis. Resolve
scripts from the installed research skill directory and write evidence in the
project. Start with the [finding template](../assets/finding-template.md).

## Protocol and sources

Record the exact question, decision criterion, falsifier and risk before searching.
Use `routine` for an ordinary lookup, `material` for consequential cost,
architecture or public claims, and `high` for medical, legal, financial, safety or
security decisions. Preserve the template sections so its validator can read them.

Reuse relevant local research before collecting the same sources. Prefer primary
sources and official repositories. For known documentation, use a direct page or
its available discovery index when helpful; do not probe a fixed list of URLs
when the authoritative page already answers the question.

Follow the provider routing in the skill entrypoint. Record attempted providers,
outcomes and fallback reasons. Use the installed provider's dedicated endpoint
when it matches the question. Endpoint prices belong in provider documentation,
not in this report protocol. For paid batches, use the sanitized account helper
before and after; respect an explicit budget. Do not invent a mandatory budget
approval for an already authorized lookup.

Convert source documents when extraction is required. Verify the resulting text,
tables and reading order. Read every source used to support a material claim;
search snippets and collector summaries do not count as an opened source.

For durable snapshots, resolve `scripts/collect_sources.py` from the installed
research skill, not the consumer project's checkout. Input is a JSON list of
`{slug, url, dynamic?}` for pages or `{slug, query, page?, limit?, engine?}` for search.
New searches use explicit DuckDuckGo, page 0 by default (0/1 supported), limit 10
by default (1–20). Supply page 1 only after checking `has_next_page` and carry
the effective `engine` from the first `search.json`; Bing is accepted only for
continuation, with limit at most 10. Preserve ranked snapshots unchanged and
deduplicate only the URLs selected for page acquisition.

```sh
python3 "$HOME/.agents/skills/research/scripts/collect_sources.py" \
  --input sources.json --out research/sources --project-scope my-project --dry-run
# Run without --dry-run to acquire with the private research identity.
```

`SCRAPINHO_BASE_URL` defaults to `https://scrapinho.dev`. `--project-scope` or
`SCRAPINHO_PROJECT_SCOPE` is required; there is no shared default namespace.
The collector reads `SCRAPINHO_API_KEY`, or only the `research.api_key` entry in
`~/.config/scrapinho/clients.json` (`--config` overrides that private path).
It never borrows another consumer's identity. Keep credentials out of inputs,
artifacts and version control. Dry-run validates without opening private
configuration or doing network I/O. Acquisition is sequential, one attempt per job, with a
`--timeout` deadline per acquisition and a bounded source-export phase.
No automatic fallback to a legacy scraper occurs. Refusal/auth/quota stops
further admissions; ordinary per-item failures retain successful siblings.

`dynamic: true` selects browser acquisition. Both input kinds preserve
`page.html` (raw bytes), `page.md` (normalized text through EOF), and
`record.json` with verified SHA-256, acquisition time, scope, job/source IDs,
cache metadata and usage. Search additionally writes `search.json`, preserving
the effective engine, original positions and pagination. For non-HTML sources,
`page.html` retains the raw representation despite its historical filename.
Sources are untrusted evidence, not editorial validation.

An acquisition deadline stops further admissions and sends one cancellation
request for an admitted job. The collector records the cancellation response's
latest status and usage; `execution_unknown` or a failed cancellation is marked
unconfirmed, not cancelled. The original deadline diagnostic is retained, and a
terminal response without a complete source does not count as successful evidence.

Usage survives
failure; proxy bytes and dollar cost remain unknown rather than zero. Cache reuse preserves the
original collection timestamp and service TTL, never invents a publication date.
Retain source and provenance from an already used provider without fetching again
solely for a template.

Before using a configured Scrapinho endpoint, resolve this installed skill’s
`scripts/preflight_scrapinho_mcp.mjs` and run it with Node. It checks
authentication, MCP tools, public static/browser page availability and returns
the schema-derived `requestDefaults` without acquiring a source. Reuse those
defaults when constructing `fetch.page` requests if the host omits them;
`available=true` does not prove every geographic override is supported, and an
explicit unsupported country must fail rather than being changed silently.
Unsupported operations or formats are reported, not silently routed back to
the removed generic scraper. The Node preflight takes `SCRAPINHO_API_KEY` from
the private environment, unlike the collector's optional private JSON loader.
When installing or updating a selected Scrapinho integration, run this preflight
only when credentials are configured; report a missing key as unavailable.
It covers pages, not full provider parity.

### Local cutover evidence, 2026-09-29

The installed Linux research skill and shared policy resolve by symlink to this
checkout. The collector now loads only the existing private research identity;
no installer, global MCP replacement, provider-secret deletion, commit, push or
remote deployment was required. Rollback snapshots of the pre-existing research
skill and shared policy are under `/tmp/my-llm-kit-research-before-20260929` and
`/tmp/my-llm-kit-instructions-before-20260929.md`; restore only these owned edits,
preserving any later user changes.

The live installed CLI completed DDG pages 0/1 and fetched the primary RFC found
by discovery. Its 454,437-character text matched the offline artifact after 28
source reads through EOF; raw SHA matched. A mixed batch kept the successful
source and returned exit 1 for a missing source. An information page hit
`body_limit`; it remained failed, with usage recorded and no page artifact.
Seven jobs were admitted, sequentially, with one attempt each. A repeated RFC
request did not hit cache; no cache-hit claim is made. Sanitized records and
artifact hashes are in
[`research/evidence/research-scrapinho-cutover-20260929.json`](../../../research/evidence/research-scrapinho-cutover-20260929.json).

This proves local activation against the live API, not a new Scrapinho release,
full production readiness, the 2.5-second target or mixed-capacity approval.
Windows/PowerShell, browser acquisition and specialized-provider flows were not
exercised in this cutover. Scientific and non-equivalent provider routes remain.


## Adjudicate claims

Keep a claim ledger containing the claim, source URL, access date, snapshot path,
primariness, direct support, currency, independence and verdict. The template
accepts `yes`, `no`, `partial` or `unknown` for evidence attributes, and `accepted`,
`limited`, `volatile` or `rejected` for verdicts.

Reject sources that do not support the claim. Mark weak samples or secondary-only
evidence as limited, and values requiring reconfirmation as volatile. Corroborate
material claims independently when a suitable source exists. Repeated reporting
of the same upstream finding is not independent evidence. Report disagreement
with the sources' dates rather than choosing a convenient answer silently.

Put source and access date beside external quantities and superlatives. Local
measurements cite their reproducible artifact or command; do not search the web
to substantiate a count produced by a local check.

## Independent review

Use one bounded council when requested, for high-risk research, when credible
primary sources disagree on a material conclusion, or when a material conclusion
rests only on secondary evidence. The main researcher adjudicates the review;
reviewer agreement is not evidence. If delegation is unavailable, report that
review as unverified rather than inventing a reviewer.

Give reviewers the draft and source artifacts. Ask them to inspect support,
provenance, omitted counterevidence and uncertainty. Record accepted and rejected
findings. No council is required for an ordinary source-backed lookup.

## Save and validate

Save a requested report under `research/YYYY-MM-DD-slug.md` unless the user chose
another location. Record the provider trail, ledger, findings, disagreements,
open questions, council status, sources and evidence limits using the template.
Use actual credit usage when observable. If no paid collection occurred, record
zero. If metering is unavailable, use the validator's numeric field for known
charges only and explain the missing metering in the provider trail and limits;
never present it as a measured total.

Run `python3 "<research-dir>/scripts/audit_finding.py" <finding.md>` (Windows:
`py -3`). Fix structural failures. The validator checks provenance structure, not
whether the sources entail the conclusion. Complete that judgment yourself.


## Reusable evidence cards

For comparative model or harness research, keep a compact card in the existing
report: source URL/version, access date, task and input scope, actual model/effort,
measurement basis (API billing, credits, allowance or raw tokens), outcome,
limitations and the decision it can affect. Unknown fields remain unknown.
Retain source locators rather than pasting full threads and papers into every
worker/coordinator context. Treat a comment quoted by several sites as one report.
Never equate raw cached input volume with its share of billed cost, or a
subscription percentage with API dollars. Abstract-only results are discovery
leads; read the method and contrary/appendix results before changing defaults.
