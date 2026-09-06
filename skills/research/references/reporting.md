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

For durable web snapshots, the existing `scripts/collect_sources.py` accepts a
JSON list of `{slug, url, dynamic?}` and an output directory. Its `--dry-run` lists
requests first. Use it when its ScrapingDog route is appropriate; otherwise retain
the source and provenance from the provider already used, without paying to fetch
it again solely for a template.

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
