<p align="center"><img src="docs/banner.png" width="720" alt="my-llm-kit wordmark in white with mint-green hyphens on a near-black background, with the tagline: a personal, versioned coding-agent setup"></p>

<p align="center"><b>One clone and one script turn a fresh machine into the exact same coding-agent environment.</b></p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="MIT license"></a>
  <a href="https://github.com/badmuriss/my-llm-kit/stargazers"><img src="https://img.shields.io/github/stars/badmuriss/my-llm-kit?style=flat-square" alt="GitHub stars"></a>
  <a href="https://github.com/badmuriss/my-llm-kit/commits/main"><img src="https://img.shields.io/github/last-commit/badmuriss/my-llm-kit?style=flat-square" alt="last commit"></a>
</p>

<p align="center">
  <a href="#install">Install</a> ·
  <a href="#which-agents-this-works-with">Which agents</a> ·
  <a href="#the-full-stack">The full stack</a> ·
  <a href="#workflow-spec-and-impl">Workflow</a> ·
  <a href="#what-setupsh-does">What setup.sh does</a> ·
  <a href="#credits">Credits</a>
</p>

## Install

```bash
git clone https://github.com/badmuriss/my-llm-kit
cd my-llm-kit
./setup.sh --dry-run   # preview every change before running for real
./setup.sh
```

A personal, versioned setup for coding agents: a writing system, a research system, coding standards, audit skills, a shared `AGENTS.md`, and one idempotent script that wires it into the directories your agents actually read.

## Why this exists

Agent config rots quietly. Skills drift out of sync between machines, the global instructions file forks into local edits nobody remembers making, and every new agent you try wants its own copy of everything. This repo pins the whole setup to git, so a fresh machine is one clone and one script away from the same environment, on whichever agent you happen to be running that week.

## Which agents this works with

Skills install into **`~/.agents/skills/`**, the cross-agent convention. Several hosts read it natively; the ones that only look in their own directory get a per-skill symlink pointing back at the same files. One copy on disk, every agent sees it.

| Host | Reads `~/.agents/skills` natively | Skills | Plugins | MCP | dcg hooks |
|---|---|---|---|---|---|
| Claude Code | no | symlinked into `~/.claude/skills/` | yes | yes | yes |
| Codex CLI | project scope only | symlinked into `~/.codex/skills/` | yes | yes | yes |
| Gemini CLI | yes | nothing needed | no marketplace | by hand | yes |
| GitHub Copilot CLI | yes | nothing needed | no marketplace | by hand | yes |
| OpenCode | yes | nothing needed | no marketplace | prints the JSON | not supported by dcg |

The script only touches a host directory when that host is actually installed, and it never overwrites a real directory that is already sitting there: it reports it and moves on.

Nothing in this kit is Claude Code only. Every skill describes the action it wants (navigate, click, screenshot, search the web) and leaves the tool name to the host, so the same file works wherever it lands.

The same logic covers the instructions file. `AGENTS.md` lives once at `~/.agents/AGENTS.md`, and `~/.claude/CLAUDE.md` plus `~/.codex/AGENTS.md` become symlinks to it. Edit one file, every agent picks it up.

**MCP servers are the exception, and there is no way around it.** Claude Code, Codex and OpenCode use three different config files in three different formats with no shared path between them, so `setup.sh` branches per host instead of pretending a single command exists. For OpenCode it prints the JSON block rather than editing your config.

### Installing a single skill without the script

Any skill here also installs standalone through [skills.sh](https://skills.sh), which handles the same fan-out:

```bash
npx skills add badmuriss/site-audit --global --agent '*' -y
```

## The full stack

Everything `setup.sh` installs, in one table.

### Skills vendored in this repo (`skills/`, linked into `~/.agents/skills/`)

| Skill | What it does | Origin / credit |
|---|---|---|
| research | Research cycle: primary sources first, disagreements reported, weak samples flagged, auditable output | Adapted from [research-stack](https://github.com/nett0eth/research-stack) (Netto, MIT) |
| ingest | Routes PDF/Word/Excel/repos to the right converter before any analysis | Adapted from [research-stack](https://github.com/nett0eth/research-stack) (Netto, MIT) |
| writing | Technical writing standards based on Zinsser | Own |
| grill-me | Relentless interview about a plan until shared understanding | Own |
| grill-with-docs | Same grilling, but updates CONTEXT.md and ADRs as decisions land | Own |
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

### Plugins (Claude Code and Codex)

Both hosts read a git plugin marketplace, and Codex accepts the `.claude-plugin/marketplace.json` layout, so the same four entries install on either one. Only the subcommand differs: `claude plugin install` against `codex plugin add`. `setup.sh` runs whichever hosts it finds and installs the same list on each.

Verified on codex-cli 0.146.0: all four marketplace repos below resolve through `codex plugin marketplace add`, and `codex plugin add last30days@last30days-skill` installs.

Gemini CLI, Copilot CLI and OpenCode have no plugin marketplace. They still get every skill through `~/.agents/skills/`, so what they lose is the slash commands and hooks a plugin bundles, not the knowledge.

| Plugin | What it does | Marketplace repo |
|---|---|---|
| claude-code-harness | Plan/work/review/release loop with team orchestration | [Chachamaru127/claude-code-harness](https://github.com/Chachamaru127/claude-code-harness) |
| chrome-devtools-mcp | Browser debugging, automation, performance traces via Chrome DevTools | [anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official) |
| cloudflare | Workers, Pages, KV, D1, R2, Durable Objects, wrangler skills | [cloudflare/skills](https://github.com/cloudflare/skills) |
| last30days | Community pulse over the last 30 days (Reddit, HN, X, GitHub, arXiv), plugs into the research skill | [mvanhorn/last30days-skill](https://github.com/mvanhorn/last30days-skill) (MIT) |

### Destructive-command guard (dcg)

[dcg](https://github.com/Dicklesworthstone/destructive_command_guard) sits in front of every shell command the agent runs and blocks the destructive ones. It wires its own hooks into Claude Code, Codex CLI, Gemini CLI, Copilot CLI and Cursor, so this is the one piece of the kit that is genuinely host-agnostic without any help from `setup.sh`.

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

`setup.sh` asserts all 25 verdicts after installing the config, so a calibration that quietly stops protecting something fails the install instead of passing in silence.

### MCP servers

`setup.sh` registers only `paper-search` (scientific literature on arXiv, PubMed, Semantic Scholar, Crossref, OpenAlex, Unpaywall), on each host that is present. Other generic public MCPs worth adding by hand: `playwright` (browser automation) and `shadcn` (component registry). Paid or account-bound MCPs are not part of this kit; see below.

### Config

| Component | What it does |
|---|---|
| AGENTS.md | Shared agent instructions. Installed at `~/.agents/AGENTS.md`, aliased from `~/.claude/CLAUDE.md` and `~/.codex/AGENTS.md`, with a backup of anything already there |
| setup.sh | Installs everything above; idempotent, supports `--dry-run` |
| commands/, agents/ | The plan → implement workflow below, installed by `install.sh` |

## Workflow: /spec and /impl

Two slash commands and the two subagents they dispatch to. They live in `commands/` and `agents/`, and used to be a separate repo (`claude-harness`), now folded in here so there is one public surface instead of two.

| File | What it is |
|---|---|
| `commands/spec.md` | `/spec <change>` — plans with an architecture lens (deep modules, deletion test, YAGNI), grills the decisions with you, and emits an openspec change (`proposal.md`, `design.md`, self-contained `tasks.md`). A new permanent rule has to name which existing rule it replaces. |
| `commands/impl.md` | `/impl <change>` — dumb dispatcher: delegates each task to a subagent, reads the diff instead of the summary, and grades every task `pass`, `fail`, `unobserved` or `blocked`. Missing evidence is never `pass`. |
| `agents/deep-reasoner.md` | Frontier-tier subagent with a clean, unanchored context. For architecture, debugging, algorithm design. |
| `agents/fast-worker.md` | Fast-tier subagent for mechanical work: boilerplate, tests, formatting, simple edits. |

`setup.sh` does not install these, because they are Claude Code slash commands rather than cross-agent skills. Install them on their own:

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

unslop lives in its own repo, [badmuriss/unslop](https://github.com/badmuriss/unslop). `setup.sh` clones it to `~/Documents/unslop` and links it into the skill root.

v2 has four modes: write, edit, detect and score. A dedicated Brazilian Portuguese layer catches the tells the English list misses (the em dash splice, "no cenário atual", "é importante ressaltar", call-center gerund). A rubric grades every draft from 0 to 50 with a cut line at 35: below that, the text goes back for a rewrite before it ships. A self-eval runs at the end of each generation to catch relapses before the user sees them.

## Research: research + ingest

Two skills adapted from [research-stack](https://github.com/nett0eth/research-stack) by Netto (@nett0eth), MIT license.

`research` enforces four non-negotiable rules on every investigation:

1. Primary sources first: official docs and the project repository before papers, papers before third-party analysis. Aggregator blogs are leads, never the final stop.
2. When sources disagree, both versions are reported with their dates, never resolved silently.
3. A pattern seen in fewer than 5 cases is flagged as a weak sample, never stated as a conclusion.
4. Every number, monetary value and superlative ships with a URL and access date next to it.

`ingest` routes each file (PDF, Word, Excel, code repository) to the right converter before anything gets read, because a two-column PDF read raw produces scrambled conclusions.

## What setup.sh does

1. Checks required binaries (git, python3, pip3, node, npx) and reports which agent hosts it found.
2. Installs `markitdown[all]`, `paper-search-mcp` and `mcp<2.0.0` via pip (mcp 2.0.0 broke fastmcp, so the version is pinned).
3. Registers the `paper-search` MCP on each host present, using that host's own command and config format.
4. Links every skill under `skills/` into `~/.agents/skills/`, then fans out per-skill symlinks to the host dirs that need them, backing up anything real in the way.
5. Clones the own skill repos (unslop, incredibly-pretty-websites, site-audit) to `~/Documents/` if missing and links them the same way.
6. Clones the community skills into the skill root, skipping anything already there.
7. Installs the Firecrawl CLI and its skill suite if missing.
8. Installs `AGENTS.md` at `~/.agents/AGENTS.md` and points each host's expected filename at it, with backups.
9. Fans every skill in the canonical root out to each host that needs its own copy, whatever put the skill there: this repo, a community clone, the Firecrawl CLI, or a plain `npx skills add --global`. This is the step that makes adding a host later a no-op, so installing Codex on a machine that already ran the script is one rerun away from parity. Real directories a host already owns are reported and left alone.
10. Adds each plugin marketplace and installs the plugins on every host that has one (Claude Code, Codex), skipping what is already installed.
11. Installs [dcg](https://github.com/Dicklesworthstone/destructive_command_guard), copies the calibrated `dcg/config.toml` and `dcg/allowlist.toml` into `~/.config/dcg/` (backing up anything different that was already there), and lets dcg wire its own hooks. dcg 0.9.4 covers Claude Code, Codex CLI, Gemini CLI, Copilot CLI and Cursor, emitting the right protocol per host.
12. Asserts the 25 expected verdicts in `dcg/regression.txt`, so a broken calibration fails the install.

Heavy converters (MinerU, docling) are opt-in and not installed by the script. The whole thing is idempotent: a second run changes nothing.

## Credits

- Research and ingestion skills: adapted from [research-stack](https://github.com/nett0eth/research-stack) by Netto (@nett0eth), MIT.
- Community pulse: [last30days-skill](https://github.com/mvanhorn/last30days-skill) by mvanhorn, MIT.
- Writing system: [unslop](https://github.com/badmuriss/unslop), own work, CC BY-SA.
- Cross-agent skill layout and the `skills` CLI: [vercel-labs/skills](https://github.com/vercel-labs/skills).
- Community skills credited inline in the table above; each keeps its own license file.

## License

MIT. See [LICENSE](LICENSE). Community skills cloned by the script keep their own licenses in their own repos.
