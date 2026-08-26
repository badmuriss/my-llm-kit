<p align="center"><img src="docs/banner.png" width="720" alt="my-llm-kit wordmark in white with mint-green hyphens on a near-black background, with the tagline: a personal, versioned coding-agent setup"></p>

<p align="center"><b>A portable coding-agent harness for research, planning, implementation, and clear technical writing.</b></p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="MIT license"></a>
  <a href="https://github.com/badmuriss/my-llm-kit/stargazers"><img src="https://img.shields.io/github/stars/badmuriss/my-llm-kit?style=flat-square" alt="GitHub stars"></a>
  <a href="https://github.com/badmuriss/my-llm-kit/commits/main"><img src="https://img.shields.io/github/last-commit/badmuriss/my-llm-kit?style=flat-square" alt="last commit"></a>
</p>

<p align="center">
  <a href="#install">Install</a> ·
  <a href="#how-the-harness-works">How it works</a> ·
  <a href="#whats-included">What's included</a> ·
  <a href="#supported-agents">Supported agents</a> ·
  <a href="#setup-details">Setup details</a>
</p>

## Install

Paste this into your coding agent:

```text
Install my-llm-kit from https://github.com/badmuriss/my-llm-kit.

1. Detect native Windows, macOS, or Linux. Do not use WSL for a native Windows install.
2. Clone the repo, or preserve local changes if it already exists.
3. Read AGENTS.md and README.md.
4. Preview with .\setup.ps1 -DryRun on Windows or ./setup.sh --dry-run on macOS/Linux.
5. Fix safe prerequisites. Do not delete user-owned configuration.
6. Run the matching installer, then run it again to verify idempotence.
7. Confirm that spec, impl, grill-me, and spec-council are available to the installed agents.
8. Report changes, skips, backups, failures, and anything left unverified.
```

Manual fallback for Linux and macOS:

```bash
git clone https://github.com/badmuriss/my-llm-kit
cd my-llm-kit
./setup.sh --dry-run
./setup.sh
```

Manual fallback for native Windows PowerShell:

```powershell
git clone https://github.com/badmuriss/my-llm-kit
Set-Location my-llm-kit
Set-ExecutionPolicy -Scope Process Bypass
.\setup.ps1 -DryRun
.\setup.ps1
```

## How the harness works

The harness separates process choice from execution. Adaptive intake inspects the request and repository, then chooses the smallest mode that can produce trustworthy evidence.

```text
adaptive intake
  ├─ direct: one bounded change and check
  ├─ verified_single: one hypothesis and check loop
  ├─ light_spec: one amendable Markdown decision
  └─ graph: OpenSpec tasks, journal, coordinator, and adapters
```

OpenSpec is optional for the first three modes. Graph mode requires an approved
OpenSpec task graph and a saved `process-decision.json` whose packet contracts
match the tasks.

| Skill | Job | Output |
|---|---|---|
| `research` | Routes each query to the narrowest provider, adjudicates sources per claim, and optionally runs one bounded council. | An audited finding under `research/` with credit usage, source snapshots (`collect_sources.py`) and semantic audit. |
| `spec` | Runs adaptive intake and records only the planning depth the evidence requires. A `--council` flag adds one bounded review. | A direct decision, lightweight record, or OpenSpec graph. |
| `impl` | Executes the selected mode. Graph mode transfers to a fresh coordinator and grades every recorded check. | Code and evidence, plus a replayable journal only for graph work. |
| `writing` | Keeps docs, commits, PR descriptions, and errors short and concrete. | A clear record of what changed, why, and how it was checked. |

Start a change:

```text
Use $spec to plan <change>. Resolve the important decisions with me and create the OpenSpec files. Do not implement yet.
```

Implement the approved plan:

```text
Use $impl <slug> to implement the OpenSpec change. Execute every task check and report its evidence grade.
```

Claude Code also has `/spec` and `/impl` wrappers for the same workflow. Council review is opt-in with `$spec --council <change>`. It challenges the completed draft once and remains advisory; executable checks decide acceptance.

### Portable core and adapters

The portable core owns process decisions, task contracts, execution profiles,
`AgentGraphView`, generic delegation, checks, evidence grades, and cleanup
semantics. It does not require OpenSpec for non-graph work, a Canvas, terminal
handles, or an Orca process.

The Host adapter is the baseline conformance path. It writes bounded repository
capsules and can use a host-native worker or one local execution. Orca is the
current rich adapter: it adds supervised workers, durable terminal receipts,
worktree placement, browser surfaces, and Maestro Canvas state when those
capabilities are verified. Orca is not a prerequisite. A future adapter can
implement the same capability receipt and driver contracts without changing
task truth or evidence grades. Unsupported capabilities block or downgrade only
the operation that requested them.

### What graph-mode `impl` records

Every run stores an append-only journal and rebuilt projection under `openspec/runs/<change>/<run-id>/`. A resumed coordinator reads task, attempt, driver, evidence, question, and cleanup state without loading terminal transcripts.

Each OpenSpec task carries one `Check:` command. The state records its result, exit code, duration, and attempt count. `Check: missing validation evidence` remains `unobserved` and cannot become `pass`.

Validation is proportional to risk. The harness reuses the smallest relevant check and does not add tests merely to pin constants, defaults, toggles, deletions, trivial passthroughs or guarantees already enforced by the type system. MVP changes prefer a clean rewrite over compatibility layers unless the repository shows an active external contract.

Frontend tasks pair a reasoned `Visual-Scope:` with `Visual:` contracts for each changed route and state. General responsive UI covers desktop, notebook, tablet and mobile; platform-specific UI covers only its declared targets. `impl` requires PNG screenshots inspected by a vision-capable tool and a validated manifest before the task can pass. A final guard detects frontend file changes and blocks a successful run when the plan omitted visual expectations entirely. The `frontend-visual-validation` skill defines the capture and review workflow.

Tasks declare dependencies, read or write mode, repository path prefixes, and isolation. A task becomes ready only after every dependency has grade `pass`. Concurrent writes require non-overlapping path prefixes. Provider completion creates a report, never a passing grade.

Orca and host-native execution share the same graph semantics. Auto mode records one adapter choice and its reason for the full run.

The loop stops when no verified, unchecked, in-scope task remains and every cleanup obligation has a receipt.

After normal completion, `skills/impl/scripts/learning.py` can snapshot observed process facts and compile recurring support or opposition into `openspec/impl-learning/DRAFT_CANDIDATES.md`. Missing provider usage, cache, or timing data is recorded as `unavailable`, never as zero or an estimate. Learning is shadow-only: it never changes the completed run, routing, capability receipt, evidence grade, rule, or skill. Activation requires a reviewed change or a validated executable gate. See the [trajectory-learning audit](research/2026-08-10-agent-trajectory-learning-audit.md).

### Runtime-aware orchestration

Graph-mode `impl` freezes an immutable control runtime and hands off to one
fresh visible coordinator using the profile selected by the task-local decision
and verified adapter capabilities. The coordinator derives only the roles and smallest useful wave that
ready work requires. Workers resolve the cheapest sufficient catalog profile
for their role, risk, tools, context, and check, persisting requested/resolved
model and effort independently with rationale, fallback, and cost rank. Concrete
provider names are catalog data, not scheduler policy.

Orca and Host-native execution share the same capsules, placement identity,
evidence rules, and cleanup semantics. Canvas actions, checkboxes, provider
completion, and process exit never grade work. Learning snapshots are bounded
canonical graph facts and exclude prompts, reports, terminal output, notes, and
conversation transcripts.

## What's included

### Core skills in this repo

| Skill | Purpose |
|---|---|
| `research` | Source-first research with provider provenance, claim adjudication, and optional council review. |
| `ingest` | Converts received documents and repos before analysis. |
| `writing` | Technical writing rules based on Zinsser. |
| `spec` | Architecture-first OpenSpec planning. |
| `agent-graph` | Durable dependencies, task capsules, driver receipts, evidence grades, and cleanup. |
| `impl` | Fresh-coordinator implementation over the portable graph runtime. |
| `grill-me` | Decision interview used by `spec`. |
| `grill-with-docs` | Decision interview that also updates context and ADRs. |
| `scrapingdog` | Paid public-web data provider. Requires `SCRAPINGDOG_API_KEY`. |
| `readme-pass` | Concise, scannable README with agent-first installation. |

### Skills linked from their own repos

| Skill | Purpose | Repo |
|---|---|---|
| `unslop` | Writes, edits, detects, and scores prose, including Brazilian Portuguese. | [badmuriss/unslop](https://github.com/badmuriss/unslop) |
| `incredibly-pretty-websites` | Research-driven frontend design system. | [badmuriss/incredibly-pretty-websites](https://github.com/badmuriss/incredibly-pretty-websites) |
| `site-audit` | UX, SEO, AEO, GEO, and Core Web Vitals audit for a running site. | [badmuriss/site-audit](https://github.com/badmuriss/site-audit) |
| `spec-council` | Bounded multi-perspective review for OpenSpec drafts. | [badmuriss/spec-council](https://github.com/badmuriss/spec-council) |

### Community design and diagram skills

| Skill | Purpose | Repo |
|---|---|---|
| `refero-design` | Leads UI research through Refero styles, screens, and flows, then produces a reference lock and decision ledger. `$incredibly-pretty-websites` consumes that direction for implementation craft and frontend constraints. | [referodesign/refero_skill](https://github.com/referodesign/refero_skill) |
| `drawio-skill` | Creates editable architecture, flow, UML, ER, and system diagrams, validates their structure, exports common formats, and requires visual review. | [Agents365-ai/drawio-skill](https://github.com/Agents365-ai/drawio-skill) |

### Web fallback

| Skill | Purpose | Source |
|---|---|---|
| `firecrawl` suite | Search, scrape, crawl, and map through the Firecrawl CLI. | [firecrawl/cli](https://github.com/firecrawl/cli) |

### Web MCP

The setup installs and registers [`scrapingdog-mcp`](https://github.com/Darshan972/Scrapingdog-mcp) with Claude Code and Codex. Until [the YouTube Search fix](https://github.com/Darshan972/Scrapingdog-mcp/pull/1) ships in an npm release, installation is pinned to the immutable tarball for the tested fork commit. It performs an MCP handshake and checks the tool catalog without consuming API credits. OpenCode receives the equivalent JSON to add manually.

The server reads `SCRAPINGDOG_API_KEY` from the agent process at runtime. The installer never writes the key to host configuration. Export the variable before starting the agent.

Credentials are optional during setup. A skill stays dormant until its key or login is available.

### Optional plugins

Claude Code and Codex receive these plugins when the host is installed:

| Plugin | Purpose | Marketplace |
|---|---|---|
| `cloudflare` | Workers, Pages, storage, Durable Objects, and Wrangler workflows. | [cloudflare/skills](https://github.com/cloudflare/skills) |
| `last30days` | Recent community research across Reddit, HN, X, GitHub, and arXiv. | [mvanhorn/last30days-skill](https://github.com/mvanhorn/last30days-skill) |

## Supported agents

Skills live once in `~/.agents/skills/`. Hosts that need their own directory receive links to the same files. Unix uses symlinks; Windows uses directory junctions.

| Host | Skill setup | Plugins | MCP | dcg hooks | Pipelock |
|---|---|---|---|---|---|
| Claude Code | linked to `~/.claude/skills/` | yes | yes | yes | action hooks |
| Codex CLI | linked to `~/.codex/skills/` | yes | yes | yes | MCP proxy |
| Gemini CLI | reads shared root | no marketplace | manual | yes | not configured |
| GitHub Copilot CLI | reads shared root | no marketplace | manual | yes | not configured |
| OpenCode | reads shared root | no marketplace | JSON printed | not supported | not configured |

The installer only configures hosts it finds. It reports real directories instead of overwriting them.

`AGENTS.md` also has one source. Unix links host-specific instruction files to it. Windows installs managed copies because file symlinks may require extra privileges.

To install one public skill without the full setup:

```bash
npx skills add badmuriss/site-audit --global --agent '*' -y
```

## Setup details

`setup.sh` handles Linux and macOS. `setup.ps1` handles native Windows. Both read `install-manifest.json`, support a preview mode, preserve user-owned configuration, and can run more than once.

The installers:

1. Detect installed agent hosts and required tools.
2. Install the shared skills and link them into each host.
3. Clone the owned and community skill repos when missing, including skills stored in a repository subdirectory.
4. Install Firecrawl, optional plugins, and the `paper-search` and ScrapingDog MCP servers where supported.
5. Verify the ScrapingDog MCP handshake and tool catalog without API credits.
6. Verify the `paper-search` executable, version, and one real arXiv query. A failure declares the web fallback.
7. Install the shared `AGENTS.md`, with backups for different existing files.
8. Install and verify `dcg`, the destructive-command guard.
9. Leave resource management to the host and operating system by default. Linux users may opt into `agent-resource-guard` with `./setup.sh --with-resource-guard`.
10. Install the pinned Pipelock release after verifying its checksum, then configure detected Codex and Claude hosts.

### Safety tools

`dcg` blocks destructive shell commands before they run. This repo installs a shared configuration from `dcg/`.

`agent-resource-guard` is an optional Linux-only enhancement for machines that regularly run many concurrent agents or overlapping heavy commands. Install it explicitly with `./setup.sh --with-resource-guard`. When present, the harness can use it for machine-wide admission and stale-workload cleanup. Normal Linux installs, macOS and native Windows use their host's process controls instead; a missing guard never blocks work.

`Pipelock` scans agent actions at supported host boundaries. The Codex installer wraps existing MCP servers with `pipelock mcp proxy`. The Claude installer adds its action hooks. Run setup again after adding a Codex MCP server so Pipelock can wrap the new entry.

This integration does not intercept every process on the machine. A child process that opens its own connection can bypass an application proxy. Use Pipelock sandbox or operating-system containment when all outbound traffic must be mediated.

### Reduced Claude Code install

Claude Code users can install only the native commands, worker profiles, and their required skills:

```bash
./install.sh
./install.sh --link
```

From a bare shell:

```bash
curl -fsSL https://raw.githubusercontent.com/badmuriss/my-llm-kit/main/install.sh | bash
```

The reduced install includes [`$trim-code-comments`](https://github.com/badmuriss/trim-code-comments) for manual comment cleanup and an independent, read-only maintainability review that `$impl` runs after code changes.

## Not included

The setup skips private, client-specific, account-bound, and narrow single-workflow skills. Install those separately when a project needs them.

Heavy converters such as MinerU and docling are opt-in.

## Credits

- `research` and `ingest` are adapted from [research-stack](https://github.com/nett0eth/research-stack) by Netto, under MIT.
- `last30days` comes from [mvanhorn/last30days-skill](https://github.com/mvanhorn/last30days-skill), under MIT.
- `unslop` is original work under CC BY-SA.
- `thermo-nuclear-code-quality-review` is adapted from [Cursor Team Kit](https://github.com/cursor/plugins/tree/main/cursor-team-kit/skills/thermo-nuclear-code-quality-review), under MIT.
- The cross-agent skill layout follows [vercel-labs/skills](https://github.com/vercel-labs/skills).

Community projects keep their own licenses.

## License

MIT. See [LICENSE](LICENSE).
