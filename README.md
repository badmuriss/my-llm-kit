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

The harness separates decisions from code. It researches uncertain facts, writes an explicit plan, implements approved tasks, and keeps evidence for the result.

```text
research, when facts are uncertain
        ↓
$spec: proposal.md + design.md + tasks.md
        ↓
$impl: code + checks + evidence grades
```

| Skill | Job | Output |
|---|---|---|
| `research` | Checks changing facts and compares sources before they shape the code. | An auditable finding under `research/`. |
| `spec` | Resolves decisions and writes an executable plan. A `--council` flag adds one bounded review. | `proposal.md`, `design.md`, `tasks.md`, and an optional council report. |
| `impl` | Executes localized work directly, delegates when isolation or parallelism pays, and grades recorded checks. | Code, checks, evidence grades, and resumable state. |
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

### What `impl` records

Every run stores crash-safe state under `openspec/impl-state/`. A resumed run reports interrupted tasks, current diffs, and active processes before work continues.

Each OpenSpec task carries one `Check:` command. The state records its result, exit code, duration, and attempt count. `Check: missing validation evidence` remains `unobserved` and cannot become `pass`.

The loop stops when no verified, unchecked, in-scope task remains.

After normal completion, `learning.py` can snapshot those observed checks and compile recurring support or opposition into `openspec/impl-learning/DRAFT_CANDIDATES.md`. This shadow-mode file is never loaded by `impl`, never creates a rule or skill, and never blocks completion. Activation requires a reviewed change or a validated executable gate; paired `memory_off` and `memory_on` states can be compared without an automatic verdict. See the [trajectory-learning audit](research/2026-08-10-agent-trajectory-learning-audit.md).

### Codex model routing

`impl` keeps one localized task in the current context. It uses Luna for independent mechanical work, Terra for ambiguous integration, and Sol for architecture, security, or unresolved high-risk failures. Effort rises after observed failure or increased risk; `xhigh` is not a default lane.

## What's included

### Core skills in this repo

| Skill | Purpose |
|---|---|
| `research` | Source-first research with an audit trail. |
| `ingest` | Converts received documents and repos before analysis. |
| `writing` | Technical writing rules based on Zinsser. |
| `spec` | Architecture-first OpenSpec planning. |
| `impl` | Evidence-graded implementation with executable task checks. |
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

### Web fallback

| Skill | Purpose | Source |
|---|---|---|
| `firecrawl` suite | Search, scrape, crawl, and map through the Firecrawl CLI. | [firecrawl/cli](https://github.com/firecrawl/cli) |

Credentials are optional during setup. A skill stays dormant until its key or login is available.

### Optional plugins

Claude Code and Codex receive these plugins when the host is installed:

| Plugin | Purpose | Marketplace |
|---|---|---|
| `cloudflare` | Workers, Pages, storage, Durable Objects, and Wrangler workflows. | [cloudflare/skills](https://github.com/cloudflare/skills) |
| `last30days` | Recent community research across Reddit, HN, X, GitHub, and arXiv. | [mvanhorn/last30days-skill](https://github.com/mvanhorn/last30days-skill) |

## Supported agents

Skills live once in `~/.agents/skills/`. Hosts that need their own directory receive links to the same files. Unix uses symlinks; Windows uses directory junctions.

| Host | Skill setup | Plugins | MCP | dcg hooks |
|---|---|---|---|---|
| Claude Code | linked to `~/.claude/skills/` | yes | yes | yes |
| Codex CLI | linked to `~/.codex/skills/` | yes | yes | yes |
| Gemini CLI | reads shared root | no marketplace | manual | yes |
| GitHub Copilot CLI | reads shared root | no marketplace | manual | yes |
| OpenCode | reads shared root | no marketplace | JSON printed | not supported |

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
3. Clone the owned and community skill repos when missing.
4. Install Firecrawl, optional plugins, and the `paper-search` MCP where supported.
5. Verify the `paper-search` executable, version, and one real arXiv query. A failure declares the web fallback.
6. Install the shared `AGENTS.md`, with backups for different existing files.
7. Install and verify `dcg`, the destructive-command guard.
8. Install `agent-resource-guard` on Linux. Windows records an explicit skip.

### Safety tools

`dcg` blocks destructive shell commands before they run. This repo installs a shared configuration from `dcg/`.

`agent-resource-guard` allows up to 20 active agent sessions by default and can still deny work earlier for memory or heavy-command pressure. It also cleans up tagged child processes after their owner exits. Manual processes and persistent terminal shells are excluded.

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

## Not included

The setup skips private, client-specific, account-bound, and narrow single-workflow skills. Install those separately when a project needs them.

Heavy converters such as MinerU and docling are opt-in.

## Credits

- `research` and `ingest` are adapted from [research-stack](https://github.com/nett0eth/research-stack) by Netto, under MIT.
- `last30days` comes from [mvanhorn/last30days-skill](https://github.com/mvanhorn/last30days-skill), under MIT.
- `unslop` is original work under CC BY-SA.
- The cross-agent skill layout follows [vercel-labs/skills](https://github.com/vercel-labs/skills).

Community projects keep their own licenses.

## License

MIT. See [LICENSE](LICENSE).
