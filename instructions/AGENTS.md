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
access date. Prefer repository evidence for local questions. For known public URLs, use configured Scrapinho page acquisition; after a bounded
failure or missing access, disclose the reason and use Firecrawl, then host tools.
Search and specialized methods without verified Scrapinho parity still use
ScrapingDog when keyed, then Firecrawl and host search after a bounded failure or
missing key. Scientific literature starts with the
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
policy for both direct dispatch and graph work. OMP role aliases are assigned in
`~/.omp/agent/config.yml`, so dispatch with `@slow`, `@plan`, `@smol` or a
concrete `provider/model:effort` selector, and check the resolved model before
accepting a dispatch. If the host cannot honor the selection, report the
limitation instead of silently substituting a model.
Do not raise effort automatically after failure.

Never overlap the same build or typecheck in one worktree. Reuse development
servers. Track processes started for the task and settle them before finishing,
including child processes. After interruption, inspect real state before retrying.
Retain the objective, decisions, evidence and pending work across context changes.

For unusually high fan-out or overlapping heavy work on Linux, use
`agent-resource-guard` if installed and honor a denial. It is optional; other
systems use host controls. Reduce concurrency when observed capacity requires it.

## Harness

`omp` (Oh My Pi) is the primary coding agent and runs on the ChatGPT/Codex
subscription models. Keep one configuration surface: OMP-native files under
`~/.omp/agent/`.

| What | Where |
|---|---|
| Models, roles, effort | `~/.omp/agent/config.yml` (`modelRoles`, `retry.fallbackChains`) |
| Extra model ids | `~/.omp/agent/models.yml` |
| Skills | `~/.agents/skills/<name>/SKILL.md`, shared by every host |
| Instructions | `~/.agents/AGENTS.md` (this file, symlinked into each host) |
| MCP servers | `~/.omp/agent/mcp.json` |
| Hooks | `~/.omp/agent/hooks/{pre,post}/*.ts` |
| Subagents | `~/.omp/agent/agents/*.md` |

Use GPT-6 Sol for ordinary work, GPT-6 Luna for mechanical execution and GPT-6
Astra for difficult reasoning. These are starting recommendations, not a second
configuration surface: read `modelRoles` for the current selection and preserve
explicit user changes. Configured chat roles and fallbacks stay on
`openai-codex/*`. Do not route model inference through OpenRouter or other
pay-as-you-go endpoints, including optional skill scripts, without explicit
authorization for that exception. Disabling an OMP provider does not block
network calls made by external scripts.

| Role | Model | Use |
|---|---|---|
| `default`, `task` | GPT-6 Sol medium, unless explicitly changed | interactive work, bounded implementation |
| `plan` | GPT-6 Sol high | planning, multi-file design |
| `slow` | GPT-6 Astra medium | architecture, hard debugging, coordination |
| `smol` | GPT-6 Luna medium | mechanical edits, extraction, check execution |
| `vision` | GPT-6 Sol medium | screenshots, rendered UI, image reading |
| `tiny`, `commit` | GPT-6 Luna low | titles, commit messages, classification |
| `image` | `gpt-image-1` | `generate_image` output |

Effort follows complexity: Luna low or medium for mechanical work, Sol medium for
ordinary implementation, Sol high or Astra medium when the task is ambiguous or
costly to get wrong; xhigh and max only with a demonstrated benefit. Astra bills
about five times Sol and a hundred times Luna per token, so it earns its place
through fewer attempts, not habit.

`deep-reasoner` (`@slow`, clean context, reasoning-heavy phases) and `fast-worker`
(`@smol`, mechanical work) are the dispatchable subagents, alongside the bundled
`scout`, `reviewer`, `security-reviewer`, `sonic` and `task`. Image generation is
available through the `generate_image` tool.

## Writing and Git

Use conventional commits without agent names or co-author trailers. Use `writing`
for documentation, commits and PR descriptions. When installed, use `unslop` only
for requested standalone prose or an explicit rewrite/audit of prose, never ordinary responses,
status, implementation summaries or code review. Preserve facts when rewriting.
When using `unslop` for Portuguese, load its pt-br layer. Without that skill,
write directly from the user's brief. For Portuguese authored prose, spell out
“para”, avoid hashtags in captions and use commas, periods or colons instead of
em dashes.
