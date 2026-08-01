# my-llm-kit

A personal, versioned Claude Code setup: a writing system, a research system, a global CLAUDE.md, and one idempotent script that wires it all into `~/.claude/`.

## Why this exists

Claude Code config rots quietly: skills drift out of sync between machines, and the global CLAUDE.md forks into local edits nobody remembers making. Research and writing had the same problem, no method, just vibes. This repo pins the whole setup to git, so a fresh machine is one clone and one script away from the exact same environment.

## Inventory

| Component | What it does | Origin / credit |
|---|---|---|
| skills/pesquisa | Research cycle with primary sources first, disagreements reported, weak samples flagged and auditable output | Adapted from [research-stack](https://github.com/nett0eth/research-stack) (Netto, MIT) |
| skills/ingestao | Routes PDF/Word/Excel/repos to the right converter before any analysis | Adapted from [research-stack](https://github.com/nett0eth/research-stack) (Netto, MIT) |
| unslop | Writing system (humanizer), v2 | Own repo: [github.com/badmuriss/unslop](https://github.com/badmuriss/unslop) |
| last30days plugin | Community pulse over the last 30 days (Reddit, HN, X, Polymarket, GitHub, arXiv), scored by engagement; plugs into the pesquisa skill as a station | [last30days-skill](https://github.com/mvanhorn/last30days-skill) (mvanhorn, MIT), installed via marketplace |
| CLAUDE.md | Global Claude Code config, versioned | Own |
| setup.sh | Installs dependencies, registers MCP, clones unslop and symlinks everything into `~/.claude/` | Own, adapted from the research-stack setup |

## Writing: unslop

unslop lives in its own repo, [badmuriss/unslop](https://github.com/badmuriss/unslop). `setup.sh` clones it to `~/Documents/unslop` and symlinks it into `~/.claude/skills/unslop`.

v2 has four modes: write, edit, detect and score. A dedicated Brazilian Portuguese layer catches the tells the English list misses (the em dash splice, "no cenário atual", "é importante ressaltar", call-center gerund). A rubric grades every draft from 0 to 50 with a cut line at 35: below that, the text goes back for a rewrite before it ships. A self-eval runs at the end of each generation to catch relapses before the user sees them.

## Research: pesquisa + ingestao

Two skills adapted from [research-stack](https://github.com/nett0eth/research-stack) by Netto (@nett0eth), MIT license.

`pesquisa` enforces four non-negotiable rules on every investigation:

1. Primary sources first: official docs and the project repository before papers, papers before third-party analysis. Aggregator blogs are leads, never the final stop.
2. When sources disagree, both versions are reported with their dates, never resolved silently.
3. A pattern seen in fewer than 5 cases is flagged as a weak sample, never stated as a conclusion.
4. Every number, monetary value and superlative ships with a URL and access date next to it.

`ingestao` routes each file (PDF, Word, Excel, code repository) to the right converter before anything gets read, because a two-column PDF read raw produces scrambled conclusions.

Two extras round out the research side. The `paper-search` MCP finds scientific literature on arXiv, PubMed, Semantic Scholar, Crossref, OpenAlex and Unpaywall; `setup.sh` registers it at user scope without duplicating an existing entry. The `last30days` plugin adds a community-pulse station for questions about current sentiment, scored by real engagement, with the caveat that engagement measures relevance, not truth.

## Versioned global CLAUDE.md

The `CLAUDE.md` in this repo is the global Claude Code config. `setup.sh` symlinks `~/.claude/CLAUDE.md` to it, backing up any regular file already in place (`~/.claude/CLAUDE.md.bak-<date>`). Running the script again neither duplicates the backup nor touches a symlink that is already correct.

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
4. Symlinks `skills/pesquisa` and `skills/ingestao` into `~/.claude/skills/`.
5. Clones unslop to `~/Documents/unslop` if missing and symlinks it into `~/.claude/skills/unslop`.
6. Symlinks `~/.claude/CLAUDE.md` to the repo's CLAUDE.md, with backup.
7. Installs the last30days plugin from its marketplace, skipping if present.

Heavy converters (MinerU, docling) are opt-in and not installed by the script. The whole thing is idempotent: a second run changes nothing.

## Credits

- Research and ingestion skills: adapted from [research-stack](https://github.com/nett0eth/research-stack) by Netto (@nett0eth), MIT.
- Community pulse: [last30days-skill](https://github.com/mvanhorn/last30days-skill) by mvanhorn, MIT.
- Writing system: [unslop](https://github.com/badmuriss/unslop), own work, CC BY-SA.

## License

MIT. See [LICENSE](LICENSE).
