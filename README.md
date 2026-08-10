<p align="center"><img src="docs/banner.png" width="720" alt="my-llm-kit wordmark in white with mint-green hyphens on a near-black background, with the tagline: a personal, versioned coding-agent setup"></p>

<p align="center"><b>One clone and one agent prompt turn a fresh machine into the same coding-agent environment.</b></p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="MIT license"></a>
  <a href="https://github.com/badmuriss/my-llm-kit/stargazers"><img src="https://img.shields.io/github/stars/badmuriss/my-llm-kit?style=flat-square" alt="GitHub stars"></a>
  <a href="https://github.com/badmuriss/my-llm-kit/commits/main"><img src="https://img.shields.io/github/last-commit/badmuriss/my-llm-kit?style=flat-square" alt="last commit"></a>
</p>

<p align="center">
  <a href="#install">Install</a> ·
  <a href="#the-harness">The harness</a> ·
  <a href="#which-agents-this-works-with">Which agents</a> ·
  <a href="#the-full-stack">The full stack</a> ·
  <a href="#what-the-installers-do">What the installers do</a> ·
  <a href="#credits">Credits</a>
</p>

## Install

Copy this prompt into your coding agent. It detects the operating system, previews the changes, installs the kit, and verifies the result:

```text
Install my-llm-kit from https://github.com/badmuriss/my-llm-kit.

1. Detect whether this machine is native Windows, macOS, or Linux. Do not use WSL for a native Windows install.
2. Clone the repository if it is absent. If it already exists, preserve local changes and update it only when the worktree is clean.
3. Read AGENTS.md and the README before changing the machine.
4. Run the matching preview: .\setup.ps1 -DryRun on Windows or ./setup.sh --dry-run on macOS/Linux.
5. Inspect the preview for missing dependencies, real directories that would be preserved, and failed steps. Resolve safe prerequisites without deleting user-owned configuration.
6. When the preview has no blocker, run the real installer for this operating system.
7. Verify that ~/.agents/skills contains spec, impl, and grill-me; verify the detected agent hosts can see those skills; run the installer a second time to confirm idempotence.
8. Report what changed, what was skipped, every backup path, and any step that remains unverified. Never report success for a skipped or failed check.
```

Manual fallback for Linux and macOS:

```bash
git clone https://github.com/badmuriss/my-llm-kit
cd my-llm-kit
./setup.sh --dry-run   # preview every change before running for real
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

A personal, versioned harness for coding agents. It turns research into an explicit spec, executes that spec with evidence, learns from repeated implementation needs, and keeps the result readable.

## Why this exists

Agent config rots quietly. Skills drift out of sync between machines, the global instructions file forks into local edits nobody remembers making, and every new agent you try wants its own copy of everything. This repo pins the whole setup to git, so a fresh machine is one clone and one script away from the same environment, on whichever agent you happen to be running that week.

## The harness

The core of this repo is its own plan, work, review, and learning loop. It does not depend on `claude-code-harness` or another orchestration plugin. The same harness runs as `$spec` and `$impl` across supported agents, with `/spec` and `/impl` wrappers available for Claude Code.

The working loop is:

```text
research when facts are uncertain
        ↓
$spec turns decisions into proposal.md, design.md, and tasks.md
        ↓
$impl executes tasks, checks the diff, runs evidence, and grades the result
        ↓
verified lessons become project-local rules, gate candidates, or skills
```

Four skills carry most of the system:

| Skill | Role in the harness | Concrete result |
|---|---|---|
| `research` | Grounds claims before architecture or implementation. It starts with primary sources, preserves disagreements, and records an auditable trail. | A finding under `research/` with source URLs, access dates, and explicit confidence limits. |
| `spec` | Reads the affected code, resolves product and architecture decisions, and uses `grill-me` when the plan still has open branches. It plans but never implements. | `openspec/changes/<slug>/proposal.md`, `design.md`, and self-contained `tasks.md`. |
| `impl` | Executes an approved OpenSpec change through bounded, clean-context work. It persists crash-safe state, reviews every diff, verifies behavior, and grades the evidence for each task. | Implemented code, test evidence, task grades, incident records, and a resumable run state. |
| `writing` | Keeps technical documentation, commit messages, PR descriptions, and errors short and concrete. It is the communication layer around the work, not a generic prose generator. | Documentation and handoffs that say what changed, why, and how it was verified. |

`research` is conditional: the agent uses it when the work depends on external facts, changing APIs, numbers, or source comparison. `spec` and `impl` form the required delivery path. `writing` applies whenever that work must be explained.

The `impl` loop also improves itself without changing global state behind your back. After a run, it records only lessons supported by repository evidence. Recurring lessons across distinct changes can become active project rules, reviewable gate candidates, or valid project-local skills. Nothing is installed or published automatically.

### Running it

Ask any supported agent:

```text
Use $spec to plan <change>. Resolve the important decisions with me and create the OpenSpec files. Do not implement yet.
```

Then execute the approved change:

```text
Use $impl <slug> to implement the OpenSpec change. Verify every task and report the evidence grades and learned candidates.
```

On Claude Code, `/spec` and `/impl` invoke native wrappers for the same files and workflow.

## Which agents this works with

Skills install into **`~/.agents/skills/`**, the cross-agent convention. Several hosts read it natively; the ones that only look in their own directory get a per-skill link pointing back at the same files. Unix uses symlinks. Native Windows uses directory junctions, which do not require Developer Mode.

| Host | Reads `~/.agents/skills` natively | Skills | Plugins | MCP | dcg hooks |
|---|---|---|---|---|---|
| Claude Code | no | linked into `~/.claude/skills/` | yes | yes | yes |
| Codex CLI | project scope only | linked into `~/.codex/skills/` | yes | yes | yes |
| Gemini CLI | yes | nothing needed | no marketplace | by hand | yes |
| GitHub Copilot CLI | yes | nothing needed | no marketplace | by hand | yes |
| OpenCode | yes | nothing needed | no marketplace | prints the JSON | not supported by dcg |

The script only touches a host directory when that host is actually installed, and it never overwrites a real directory that is already sitting there: it reports it and moves on.

Nothing in this kit is Claude Code only. Every skill describes the action it wants (navigate, click, screenshot, search the web) and leaves the tool name to the host, so the same file works wherever it lands.

The same logic covers the instructions file. On Unix, `AGENTS.md` lives once at `~/.agents/AGENTS.md`, and each host path becomes a symlink. Windows installs managed copies because file symlinks may require extra privileges. Rerun `setup.ps1` after editing the repository copy.

**MCP servers are the exception, and there is no way around it.** Claude Code, Codex and OpenCode use different config formats, so each setup script branches per host instead of pretending a shared command exists. For OpenCode it prints the JSON block rather than editing your config.

### Installing a single skill without the script

Any skill here also installs standalone through [skills.sh](https://skills.sh), which handles the same fan-out:

```bash
npx skills add badmuriss/site-audit --global --agent '*' -y
```

## The full stack

Everything the setup scripts install, in one table.

### Skills vendored in this repo (`skills/`, linked into `~/.agents/skills/`)

| Skill | What it does | Origin / credit |
|---|---|---|
| research | Research cycle: primary sources first, disagreements reported, weak samples flagged, auditable output | Adapted from [research-stack](https://github.com/nett0eth/research-stack) (Netto, MIT) |
| ingest | Routes PDF/Word/Excel/repos to the right converter before any analysis | Adapted from [research-stack](https://github.com/nett0eth/research-stack) (Netto, MIT) |
| writing | Technical writing standards based on Zinsser | Own |
| grill-me | Relentless interview about a plan until shared understanding | Own |
| grill-with-docs | Same grilling, but updates CONTEXT.md and ADRs as decisions land | Own |
| spec | Plans a change with an architecture lens and emits an OpenSpec package ready for implementation | Own |
| impl | Executes an OpenSpec change, grades evidence, and turns recurring needs into rules, gate candidates, or reviewable skills | Own |
| scrapingdog | ScrapingDog as default paid scraper: SERP, Maps, Trends, News, Amazon, LinkedIn, Instagram | Own; needs `SCRAPINGDOG_API_KEY` in the environment |
| readme-pass | Top-starred presentation pass for a repo README: banner, badges, anchor nav, install up top, prose untouched | Own |

### Own skill repos (cloned to `~/Documents/`, then linked)

| Skill | What it does | Repo |
|---|---|---|
| unslop | Writing system, v2: write, edit, detect and score modes, pt-br layer, 0-50 rubric | [badmuriss/unslop](https://github.com/badmuriss/unslop) (CC BY-SA) |
| incredibly-pretty-websites | Research-driven frontend design system: dials, archetypes, motion engine, anti AI-slop list | [badmuriss/incredibly-pretty-websites](https://github.com/badmuriss/incredibly-pretty-websites) |
| site-audit | End-to-end audit of a running site: UX walkthrough, SEO/AEO/GEO, Core Web Vitals | [badmuriss/site-audit](https://github.com/badmuriss/site-audit) |

Those last two are built to hand off to each other: one decides every pixel, the other proves the deployed page holds up.

### Community skills (cloned into `~/.agents/skills/`)

| Skill | What it does | Origin |
|---|---|---|
| humanizer | Removes signs of AI writing, based on Wikipedia's guide | [blader/humanizer](https://github.com/blader/humanizer) |
| notebooklm | Queries Google NotebookLM notebooks for source-grounded answers | [PleasePrompto/notebooklm-skill](https://github.com/PleasePrompto/notebooklm-skill); needs Google auth on first run |
| llm-council | Runs a question through 5 AI advisors with anonymous peer review | [tenfoldmarc/llm-council-skill](https://github.com/tenfoldmarc/llm-council-skill) |
| firecrawl (suite) | Web scrape, crawl, search and map via the Firecrawl CLI | Installed by [firecrawl-cli](https://github.com/firecrawl/cli); needs `firecrawl login` (or `FIRECRAWL_API_KEY`) |

Skills that need credentials still install without them; they just stay dormant until the key or login exists.

### Optional plugins (Claude Code and Codex)

Both hosts read a git plugin marketplace, and Codex accepts the `.claude-plugin/marketplace.json` layout, so the same entries install on either one. Only the subcommand differs: `claude plugin install` against `codex plugin add`. Each setup script runs whichever hosts it finds and reads the list from the shared manifest.

The harness itself is not a plugin. These optional plugins add domain capabilities around it. They do not replace `spec`, `impl`, `research`, or `writing`.

Verified on codex-cli 0.146.0: both marketplace repos below resolve through `codex plugin marketplace add`, and `codex plugin add last30days@last30days-skill` installs.

Gemini CLI, Copilot CLI and OpenCode have no plugin marketplace. They still get every skill through `~/.agents/skills/`, so what they lose is the slash commands and hooks a plugin bundles, not the knowledge.

| Plugin | What it does | Marketplace repo |
|---|---|---|
| cloudflare | Workers, Pages, KV, D1, R2, Durable Objects, wrangler skills | [cloudflare/skills](https://github.com/cloudflare/skills) |
| last30days | Community pulse over the last 30 days (Reddit, HN, X, GitHub, arXiv), plugs into the research skill | [mvanhorn/last30days-skill](https://github.com/mvanhorn/last30days-skill) (MIT) |

### Destructive-command guard (dcg)

[dcg](https://github.com/Dicklesworthstone/destructive_command_guard) sits in front of every shell command the agent runs and blocks the destructive ones. It wires its own hooks into Claude Code, Codex CLI, Gemini CLI, Copilot CLI and Cursor, so its protection remains host-agnostic after installation.

What the kit adds is the calibration, in `dcg/`, with the reason for every entry written into the file:

| File | What it holds |
|---|---|
| `config.toml` | Enabled packs, hook timeout, and two `[overrides] block` rules that **tighten** the defaults |
| `allowlist.toml` | The two rules that are switched off, each with its cost stated |
| `regression.txt` | 25 commands and the verdict each must produce |

Two directions, because calibration is not the same as loosening:

- **Tightened.** `git checkout -- <file>` was denied but `git checkout .` was not, and the second discards the entire working tree instead of one file. Same gap on `git restore .`. Both are blocked now.
- **Loosened, narrowly.** `core.git:checkout-ref-discard` (restoring a file from a ref fires even when the path does not exist in the working tree) and a wrangler catch-all that denied every `npx -y <pkg>`, unrelated packages included. The other eight git protections and the concrete d1/r2/kv rules stay on.

What was deliberately **not** loosened: the redirect guard that blocks `> ~/.bashrc`. It over-triggers on creating a new file under `$HOME` and on heredocs whose text merely contains a `>`, which is annoying, but `| tee <file>` and the agent's file-write tool both work and are safer. Friction with a working alternative is not a reason to disable a rule.

Both setup scripts assert every verdict in `dcg/regression.txt` after installing the config, so a calibration that quietly stops protecting something fails the install instead of passing in silence.

### Agent resource guard

On Linux, `agent-resource-guard` prevents independent agent terminals from multiplying builds and subagents until the desktop runs out of memory. The shared instructions require a capacity check before new workers, builds, tests, browsers, and development servers when the command exists. Native Windows skips this Linux cgroup and systemd component explicitly.

The default machine-wide budget allows eight agent sessions and four heavy command trees. It also rejects new work when available memory falls below 20% or agent cgroups exceed 65% of physical memory. Each root agent may keep at most two subagents active.

A systemd user timer runs cleanup every ten seconds on Linux. It waits five minutes after an owning agent exits, then terminates its tagged workload tree. When more than eight agent sessions remain open, it also closes the oldest sessions after 30 idle minutes. Untagged manual processes and persistent terminal shells are excluded.

If agent cgroups pass 72% of physical memory or available memory drops below 12%, the timer terminates the largest agent tree before `systemd-oomd` can take down the desktop session.

```bash
agent-resource-guard status
agent-resource-guard check --intent agent --demand 2 --prune
agent-resource-guard check --intent heavy --prune
agent-resource-guard prune --dry-run
```

### MCP servers

The setup scripts register only `paper-search` (scientific literature on arXiv, PubMed, Semantic Scholar, Crossref, OpenAlex, Unpaywall), on each host that is present. Browser automation uses the Playwright CLI on demand instead of a long-lived browser MCP. The installers do not remove browser tools that a user added separately. `shadcn` remains a useful MCP to add by hand. Paid or account-bound MCPs are not part of this kit; see below.

### Config

| Component | What it does |
|---|---|
| AGENTS.md | Shared agent instructions. Installed at `~/.agents/AGENTS.md`, aliased from `~/.claude/CLAUDE.md` and `~/.codex/AGENTS.md`, with a backup of anything already there |
| setup.sh | Installs the kit on Linux and macOS; idempotent, supports `--dry-run` |
| setup.ps1 | Installs the kit on native Windows; idempotent, supports `-DryRun` |
| install-manifest.json | Shared repositories, plugins, and reduced-workflow dependencies consumed by both installers |
| skills/spec, skills/impl | Cross-agent form of the plan to implementation workflow, installed by both setup scripts |
| commands/, agents/ | Claude Code slash-command wrappers for the same workflow, installed by `install.sh` |

## Harness internals: /spec and /impl

The workflow ships in two forms. `skills/spec` and `skills/impl` work across agents and can be invoked as `$spec` and `$impl`. Claude Code keeps native `/spec` and `/impl` wrappers under `commands/`. Both forms emit and consume the same OpenSpec files.

| File | What it is |
|---|---|
| `skills/spec/SKILL.md` | Cross-agent spec workflow for Codex, Gemini, Copilot, OpenCode and Claude Code. |
| `skills/impl/SKILL.md` | Cross-agent implementation orchestrator with bounded dispatch, evidence grades, crash-safe state, and project-local learning. |
| `commands/spec.md` | `/spec <change>` — plans with an architecture lens (deep modules, deletion test, YAGNI), grills the decisions with you, and emits an openspec change (`proposal.md`, `design.md`, self-contained `tasks.md`). A new permanent rule has to name which existing rule it replaces. |
| `commands/impl.md` | `/impl <change>` — delegates each task, verifies the diff, grades evidence, and records integrator-observed lessons after the run. |
| `agents/deep-reasoner.md` | Frontier-tier subagent with a clean, unanchored context. For architecture, debugging, algorithm design. |
| `agents/fast-worker.md` | Fast-tier subagent for mechanical work: boilerplate, tests, formatting, simple edits. |

### Project-local learning

Each `$impl` or `/impl` run starts with atomic state under `openspec/impl-state/`. It records unchecked tasks, workers, repair hypotheses, evidence references, the running digest, and cleanup obligations. After a crash, `impl_state.py resume` marks unfinished dispatches interrupted and reports the real git and process state. It never restarts work automatically.

After the run, `impl_state.py export-run` copies task grades and evidence into `openspec/impl-learning/runs/`. The orchestrator adds only structured incidents and verified lessons. Evidence references must resolve to a repository file, immutable full commit SHA, passing task, or verified incident. Repeated run IDs from one change do not count as independent evidence.

The compiler generates project-local artifacts:

- `ACTIVE_RULES.md` contains recurring guidance proven across distinct OpenSpec changes.
- `GATE_CANDIDATES.md` contains recurring lessons that could become a test, guard, linter, or script. They require a normal reviewed change and never implement themselves.
- `QUALITY_SIGNALS.md` aggregates task evidence grades and incident categories such as conflicts, resource denials, stale processes, and crash recovery. It excludes PR throughput.
- `SKILLS.md` indexes recurring cross-task needs, while `skills/<name>/SKILL.md` materializes each one as a valid, reviewable skill.

The compiler rejects conflicting meanings, missing evidence, unverified incident links, and generated-file drift. It supports explicit supersession and writes the complete rule with its evidence. Generated skills require the same recurrence across distinct changes as active rules. Learning stays inside the project. The harness never installs or publishes a skill, writes host memory, changes global instructions, or modifies another repository.

The Python state and learning tools run on Windows, macOS, and Linux. A project can keep its local runtime in a git-ignored `.env` with `IMPL_OS` and `IMPL_PROJECT_DIR`; command-line `--repo` remains an explicit override. OS values are checked against the actual machine so a copied config fails clearly instead of running the wrong platform assumptions.

The loop has an explicit stop condition: if no unchecked, verified, in-scope task remains, it stops instead of inventing work.

The setup script for each OS installs the cross-agent skills. Claude Code users who also want the native slash-command wrappers can install them on their own. The reduced installer now includes `grill-me`, because `/spec` invokes it directly:

```bash
./install.sh          # copies commands and agents into ~/.claude, then installs the skills they lean on
./install.sh --link   # symlinks them back to this clone instead, so a git pull updates them in place
```

Both forms also work from a bare shell, cloning this repo into a temp dir first:

```bash
curl -fsSL https://raw.githubusercontent.com/badmuriss/my-llm-kit/main/install.sh | bash
```

## Not included

Left out on purpose, with the reason:

- single-workflow skills that only pay off for a narrow slice of people (resume tailoring, publishing to X Articles): install those directly with `npx skills add` if they match your week
- image-gen skill: depends on private helper scripts on my machine
- client and project skills (frontend-outis, gerar-conteudo, soymi-estampas): client work
- cs2-coach: personal, no public repo
- legal skill pack (contract-review, law-irac, lgpd-brasil and friends): untested outside my context
- paid or account-bound MCPs (magnific, refero, supabase, higgsfield): personal accounts, install by hand if you have them

## Writing: unslop

unslop lives in its own repo, [badmuriss/unslop](https://github.com/badmuriss/unslop). The setup scripts clone it into the user's Documents directory and link it into the skill root.

v2 has four modes: write, edit, detect and score. A dedicated Brazilian Portuguese layer catches the tells the English list misses (the em dash splice, "no cenário atual", "é importante ressaltar", call-center gerund). A rubric grades every draft from 0 to 50 with a cut line at 35: below that, the text goes back for a rewrite before it ships. A self-eval runs at the end of each generation to catch relapses before the user sees them.

## Research: research + ingest

Two skills adapted from [research-stack](https://github.com/nett0eth/research-stack) by Netto (@nett0eth), MIT license.

`research` enforces four non-negotiable rules on every investigation:

1. Primary sources first: official docs and the project repository before papers, papers before third-party analysis. Aggregator blogs are leads, never the final stop.
2. When sources disagree, both versions are reported with their dates, never resolved silently.
3. A pattern seen in fewer than 5 cases is flagged as a weak sample, never stated as a conclusion.
4. Every number, monetary value and superlative ships with a URL and access date next to it.

`ingest` routes each file (PDF, Word, Excel, code repository) to the right converter before anything gets read, because a two-column PDF read raw produces scrambled conclusions.

## What the installers do

`setup.sh` and `setup.ps1` consume the same `install-manifest.json`, so repository, plugin, and workflow dependency lists cannot drift by operating system.

1. Checks required binaries and reports which agent hosts it found.
2. Installs `markitdown[all]`, `paper-search-mcp` and `mcp<2.0.0` via pip (mcp 2.0.0 broke fastmcp, so the version is pinned).
3. Registers the `paper-search` MCP on each host present, using that host's own command and config format.
4. Links every skill under `skills/` into `~/.agents/skills/`, then fans it out to host directories with Unix symlinks or Windows junctions, backing up anything real in the canonical root.
5. Clones the own skill repos (unslop, incredibly-pretty-websites, site-audit) to `~/Documents/` if missing and links them the same way.
6. Clones the community skills into the skill root, skipping anything already there.
7. Installs the Firecrawl CLI and its skill suite if missing.
8. Installs `AGENTS.md` at `~/.agents/AGENTS.md` and updates each detected host's expected filename, with backups.
9. Fans every skill in the canonical root out to each host that needs its own copy, whatever put the skill there: this repo, a community clone, the Firecrawl CLI, or a plain `npx skills add --global`. This is the step that makes adding a host later a no-op, so installing Codex on a machine that already ran the script is one rerun away from parity. Real directories a host already owns are reported and left alone.
10. Adds each plugin marketplace and installs the plugins on every host that has one (Claude Code, Codex), skipping what is already installed.
11. Installs `agent-resource-guard` and enables its timer on Linux when a systemd user manager is available. Native Windows records an explicit skip.
12. Installs [dcg](https://github.com/Dicklesworthstone/destructive_command_guard), using its native PowerShell installer on Windows. It copies the calibrated config and allowlist into `~/.config/dcg/`, backs up different files, and wires detected hosts.
13. Asserts every expected verdict in `dcg/regression.txt`, so a broken calibration fails the install.

Heavy converters such as MinerU and docling are opt-in. Both installers are idempotent.

## Credits

- Research and ingestion skills: adapted from [research-stack](https://github.com/nett0eth/research-stack) by Netto (@nett0eth), MIT.
- Community pulse: [last30days-skill](https://github.com/mvanhorn/last30days-skill) by mvanhorn, MIT.
- Writing system: [unslop](https://github.com/badmuriss/unslop), own work, CC BY-SA.
- Cross-agent skill layout and the `skills` CLI: [vercel-labs/skills](https://github.com/vercel-labs/skills).
- Community skills credited inline in the table above; each keeps its own license file.

## License

MIT. See [LICENSE](LICENSE). Community skills cloned by the script keep their own licenses in their own repos.
