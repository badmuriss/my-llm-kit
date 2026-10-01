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

Keep implementation decisions traceable and ownership cohesive. Simplify real
branches and duplicated behavior; do not move the same complexity into thin
wrappers merely to improve a metric. Respect project complexity gates without
raising ceilings or adding suppressions to make a change pass.

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
access date. Prefer repository evidence for local questions.
Use configured Scrapinho MCP tools directly for generic web discovery and public-page
acquisition, following the research skill's capability, scope and refusal policy.
Do not substitute acquisition scripts or REST clients, or silently fall back
to the removed generic scraper. Specialized methods without verified parity
retain their existing providers; do not substitute generic search for them.
Scientific literature starts with the
free Firecrawl Research Index when available. Use `research` when available for a research
workflow, not as a prerequisite for every local fact or number. Convert documents
when extraction is needed and check reading order and tables before analysis.

## Resources and resumption

Keep implementation work that must integrate together in one shared worktree,
including its coordinator and workers. Separate write ownership by file or task;
do not create a worktree merely because another worker starts. Use another
worktree when a review, experiment or other task actually needs an isolated
revision or environment. A read-only review does not automatically require one.
State the isolation reason and how its result returns to the main work before
creating it. Honor the user's explicit placement choice.

Use one writer unless independent tasks justify delegation. Choose the cheapest
available model and effort sufficient for the role; consult the task's routing
policy for both direct dispatch and graph work. Read the active harness's native
configuration for available roles, models and effort. Use its supported dispatch
interface and check the resolved selection before accepting a dispatch. If the
host cannot honor the selection, report the limitation instead of silently
substituting a model.
Do not raise effort automatically after failure.

Never overlap the same build or typecheck in one worktree. Reuse development
servers. Track processes started for the task and settle them before finishing,
including child processes. After interruption, inspect real state before retrying.
Retain the objective, decisions, evidence and pending work across context changes.

For unusually high fan-out or overlapping heavy work on Linux, use
`agent-resource-guard` if installed and honor a denial. It is optional; other
systems use host controls. Reduce concurrency when observed capacity requires it.

## Harness and capabilities

Keep shared instructions and reusable skills independent of the coding agent.
OMP is the user's current preference; it may change. A switch of harness must not
require rewriting project rules or domain knowledge.

Shared skills live at `~/.agents/skills/<name>/SKILL.md`; shared instructions live
at `~/.agents/AGENTS.md`. Host instruction aliases use `AGENTS.md`. Keep models,
roles, effort, credentials, MCP servers and hooks in the active harness's native
configuration. Preserve explicit user choices; do not copy one host's configuration
into another or invent a second configuration surface.

Choose tools by the capability and evidence the task requires, using what is
available in the current session. Generic skills must not require OMP, Codex or
Claude tools. Host-specific integrations remain conditional on that host and must
state their dependency. Do not launch another coding agent merely to obtain a tool.

Prefer the configured subscription-backed inference. Do not route model inference
through OpenRouter or other pay-as-you-go endpoints, including optional skill
scripts, without explicit authorization for that exception. A disabled host
provider does not prevent external scripts from making network calls. Model
availability follows the authenticated account, not manually registered names.
Use the lowest sufficient effort; raise model cost only for a concrete task need.

## Cloudflare and video preferences

For Cloudflare work, prefer `cf` for new projects and keep Wrangler in projects
that already use it unless migration is requested. Check the selected CLI's
current help rather than translating commands by guesswork. Preserve the
framework, deployment path and bindings; follow the relevant Cloudflare skill
for runtime, build and migration details.

For the user's video workflow, use plain Playwright. Do not introduce Refero,
HyperFrames, Remotion or creative-generation skills unless the user changes
that choice. This does not exclude document, diagram or frontend-design skills.

## Writing and Git

Use conventional commits without agent names or co-author trailers. Documentation,
commits and PR descriptions lead with the concrete change, relevant evidence and
limitations, using plain language. When installed, use `unslop` only
for requested standalone prose or an explicit rewrite/audit of prose, never ordinary responses,
status, implementation summaries or code review. Preserve facts when rewriting.
When using `unslop` for Portuguese, load its pt-br layer. Without that skill,
write directly from the user's brief. For Portuguese authored prose, spell out
“para”, avoid hashtags in captions and use commas, periods or colons instead of
em dashes.
