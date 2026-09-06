# Shared agent instructions

## Scope and completion

Complete the authorized task, verify its result and repair failures caused by the
change. For substantial work, keep the requested outcomes, constraints, checks
and pending work visible in the existing plan. Trivial edits need no plan file.
A missing, deferred or unobserved outcome is not complete. Stop when acceptance
is demonstrated, a concrete blocker remains or the declared budget is reached.

Read only context that can affect the task. Use relevant skill capabilities,
not every skill with a matching keyword. Skills must preserve the user's scope,
choices and existing authorization. Resolve ambiguity from available evidence;
ask only when a material decision remains. Do not run reviews, councils or
orchestration merely because they are installed.

Prefer a clean implementation for a local MVP. If code or project instructions
show an active external contract, determine the compatibility requirement before
removing it. Respect an existing answer; do not ask again. Preserve unrelated
changes and user-owned configuration. Do not add adapters, flags, abstractions
or dependencies for hypothetical consumers.

## Evidence and visibility

Use the smallest check that can catch a realistic failure. Add a regression for a
reproducible recurring bug or a meaningful branching, security, integrity or
contract change. Do not test constants, deleted behavior or type guarantees.
Test behavior and name tests with third-person verbs. Reuse passing evidence
until relevant inputs or acceptance change. Never weaken a gate to claim success.

Inspect rendered changes in the running application with vision. Follow
`frontend-visual-validation` for affected states and supported platforms; keep
PNG evidence and observations under `.visual-evidence/<change>/`. If vision or a
platform is unavailable, report that evidence as unobserved. A build is not
visual evidence.

Use sources for material external facts and volatile values; cite the source and
access date. Prefer repository evidence for local questions. For public web data,
use ScrapingDog when keyed; after a bounded failure or missing key, disclose the
reason and use Firecrawl, then host search. Scientific literature starts with the
free Firecrawl Research Index when available. Use `research` when available for a research
workflow, not as a prerequisite for every local fact or number. Convert documents
when extraction is needed and check reading order and tables before analysis.

## Resources and resumption

Use one writer unless independent tasks justify delegation. Choose the cheapest
available model and effort sufficient for the role; consult the task's routing
policy when graph mode needs it. Do not raise effort automatically after failure.

Never overlap the same build or typecheck in one worktree. Reuse development
servers. Track processes started for the task and settle them before finishing,
including child processes. After interruption, inspect real state before retrying.
Retain the objective, decisions, evidence and pending work across context changes.

For unusually high fan-out or overlapping heavy work on Linux, use
`agent-resource-guard` if installed and honor a denial. It is optional; other
systems use host controls. Reduce concurrency when observed capacity requires it.

## Writing and Git

Use conventional commits without agent names or co-author trailers. Use `writing`
for documentation, commits and PR descriptions. When installed, use `unslop` only
for requested standalone prose or an explicit rewrite/audit of prose, never ordinary responses,
status, implementation summaries or code review. Preserve facts when rewriting.
When using `unslop` for Portuguese, load its pt-br layer. Without that skill,
write directly from the user's brief. For Portuguese authored prose, spell out
“para”, avoid hashtags in captions and use commas, periods or colons instead of
em dashes.
