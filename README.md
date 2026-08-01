# my-llm-kit

A personal, versioned Claude Code setup: writing system, research system, coding standards, audit skills, plugins, a global CLAUDE.md, and one idempotent script that wires it all into `~/.claude/`.

## Why this exists

Claude Code config rots quietly: skills drift out of sync between machines, and the global CLAUDE.md forks into local edits nobody remembers making. This repo pins the whole setup to git, so a fresh machine is one clone and one script away from the exact same environment.

## The full stack

Everything `setup.sh` installs, in one table.

### Skills vendored in this repo (`skills/`, symlinked into `~/.claude/skills/`)

| Skill | What it does | Origin / credit |
|---|---|---|
| research | Research cycle: primary sources first, disagreements reported, weak samples flagged, auditable output | Adapted from [research-stack](https://github.com/nett0eth/research-stack) (Netto, MIT) |
| ingest | Routes PDF/Word/Excel/repos to the right converter before any analysis | Adapted from [research-stack](https://github.com/nett0eth/research-stack) (Netto, MIT) |
| writing | Technical writing standards based on Zinsser | Own |
| grill-me | Relentless interview about a plan until shared understanding | Own |
| grill-with-docs | Same grilling, but updates CONTEXT.md and ADRs as decisions land | Own |
| ux-audit | Walks a live web app as a real user, with hard gates (console errors 0, a11y, perf budget) | Own |
| scrapingdog | ScrapingDog as default paid scraper: SERP, Maps, Trends, News, Amazon, LinkedIn, Instagram | Own; needs `SCRAPINGDOG_API_KEY` in the environment |

### Own skill repos (cloned to `~/Documents/`, symlinked)

| Skill | What it does | Repo |
|---|---|---|
| unslop | Writing system, v2: write, edit, detect and score modes, pt-br layer, 0-50 rubric | [badmuriss/unslop](https://github.com/badmuriss/unslop) (CC BY-SA) |
| incredibly-pretty-websites | Research-driven frontend design system: dials, archetypes, motion engine, anti AI-slop list | [badmuriss/incredibly-pretty-websites](https://github.com/badmuriss/incredibly-pretty-websites) |
| site-audit | End-to-end audit of a running site: UX walkthrough, SEO/AEO/GEO, Core Web Vitals | [badmuriss/site-audit](https://github.com/badmuriss/site-audit) |

### Community skills (cloned into `~/.claude/skills/`)

| Skill | What it does | Origin |
|---|---|---|
| humanizer | Removes signs of AI writing, based on Wikipedia's guide | [blader/humanizer](https://github.com/blader/humanizer) |
| notebooklm | Queries Google NotebookLM notebooks for source-grounded answers | [PleasePrompto/notebooklm-skill](https://github.com/PleasePrompto/notebooklm-skill); needs Google auth on first run |
| llm-council | Runs a question through 5 AI advisors with anonymous peer review | [tenfoldmarc/llm-council-skill](https://github.com/tenfoldmarc/llm-council-skill) |
| x-article-publisher | Publishes Markdown articles to the X Articles editor | [wshuyi/x-article-publisher-skill](https://github.com/wshuyi/x-article-publisher-skill) |
| resume-tailoring | Tailors resumes per job application with factual integrity | [varunr89/resume-tailoring-skill](https://github.com/varunr89/resume-tailoring-skill) |
| firecrawl (suite) | Web scrape, crawl, search and map via the Firecrawl CLI | Installed by [firecrawl-cli](https://github.com/firecrawl/cli); needs `firecrawl login` (or `FIRECRAWL_API_KEY`) |

Skills that need credentials still install without them; they just stay dormant until the key or login exists.

### Plugins (installed via marketplace)

| Plugin | What it does | Marketplace repo |
|---|---|---|
| claude-code-harness | Plan/work/review/release loop with team orchestration | [Chachamaru127/claude-code-harness](https://github.com/Chachamaru127/claude-code-harness) |
| chrome-devtools-mcp | Browser debugging, automation, performance traces via Chrome DevTools | [anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official) |
| frontend-design | Aesthetic direction for new UI, avoids templated defaults | [anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official) |
| cloudflare | Workers, Pages, KV, D1, R2, Durable Objects, wrangler skills | [cloudflare/skills](https://github.com/cloudflare/skills) |
| last30days | Community pulse over the last 30 days (Reddit, HN, X, GitHub, arXiv), plugs into the research skill | [mvanhorn/last30days-skill](https://github.com/mvanhorn/last30days-skill) (MIT) |

### MCP servers

`setup.sh` registers only `paper-search` (scientific literature on arXiv, PubMed, Semantic Scholar, Crossref, OpenAlex, Unpaywall). Other generic public MCPs worth adding by hand: `playwright` (browser automation) and `shadcn` (component registry). Paid or account-bound MCPs are not part of this kit; see below.

### Config

| Component | What it does |
|---|---|
| CLAUDE.md | Global Claude Code config, symlinked to `~/.claude/CLAUDE.md` with backup of any pre-existing file |
| setup.sh | Installs everything above; idempotent, supports `--dry-run` |

## Not included

Left out on purpose, with the reason:

- image-gen skill: depends on private helper scripts on my machine
- client and project skills (frontend-outis, gerar-conteudo, soymi-estampas): client work
- cs2-coach: personal, no public repo
- legal skill pack (contract-review, law-irac, lgpd-brasil and friends): untested outside my context
- paid or account-bound MCPs (magnific, refero, supabase, higgsfield): personal accounts, install by hand if you have them

## Writing: unslop

unslop lives in its own repo, [badmuriss/unslop](https://github.com/badmuriss/unslop). `setup.sh` clones it to `~/Documents/unslop` and symlinks it into `~/.claude/skills/unslop`.

v2 has four modes: write, edit, detect and score. A dedicated Brazilian Portuguese layer catches the tells the English list misses (the em dash splice, "no cenário atual", "é importante ressaltar", call-center gerund). A rubric grades every draft from 0 to 50 with a cut line at 35: below that, the text goes back for a rewrite before it ships. A self-eval runs at the end of each generation to catch relapses before the user sees them.

## Research: research + ingest

Two skills adapted from [research-stack](https://github.com/nett0eth/research-stack) by Netto (@nett0eth), MIT license.

`research` enforces four non-negotiable rules on every investigation:

1. Primary sources first: official docs and the project repository before papers, papers before third-party analysis. Aggregator blogs are leads, never the final stop.
2. When sources disagree, both versions are reported with their dates, never resolved silently.
3. A pattern seen in fewer than 5 cases is flagged as a weak sample, never stated as a conclusion.
4. Every number, monetary value and superlative ships with a URL and access date next to it.

`ingest` routes each file (PDF, Word, Excel, code repository) to the right converter before anything gets read, because a two-column PDF read raw produces scrambled conclusions.

## Install

```bash
git clone https://github.com/badmuriss/my-llm-kit
cd my-llm-kit
./setup.sh --dry-run   # preview what will change before running for real
./setup.sh
```

## What setup.sh does

1. Checks required binaries: claude, git, python3, pip3, node, npx.
2. Installs `markitdown[all]`, `paper-search-mcp` and `mcp<2.0.0` via pip (mcp 2.0.0 broke fastmcp, so the version is pinned).
3. Registers the `paper-search` MCP at user scope, skipping if already registered.
4. Symlinks every skill under `skills/` into `~/.claude/skills/`, backing up any real directory in the way.
5. Clones the own skill repos (unslop, incredibly-pretty-websites, site-audit) to `~/Documents/` if missing and symlinks them.
6. Clones the community skills into `~/.claude/skills/`, skipping anything already there.
7. Installs the Firecrawl CLI and its skill suite if missing.
8. Symlinks `~/.claude/CLAUDE.md` to the repo's CLAUDE.md, with backup.
9. Adds each plugin marketplace and installs the plugins, skipping what is already installed.

Heavy converters (MinerU, docling) are opt-in and not installed by the script. The whole thing is idempotent: a second run changes nothing.

## Credits

- Research and ingestion skills: adapted from [research-stack](https://github.com/nett0eth/research-stack) by Netto (@nett0eth), MIT.
- Community pulse: [last30days-skill](https://github.com/mvanhorn/last30days-skill) by mvanhorn, MIT.
- Writing system: [unslop](https://github.com/badmuriss/unslop), own work, CC BY-SA.
- Community skills credited inline in the table above; each keeps its own license file.

## License

MIT. See [LICENSE](LICENSE). Community skills cloned by the script keep their own licenses in their own repos.
