#!/usr/bin/env bash
# my-llm-kit :: installs dependencies, registers MCP servers and links skills. idempotent.
# host-agnostic: skills land in ~/.agents/skills (the cross-agent convention) and are
# fanned out to the host dirs that don't read it natively.
# usage: ./setup.sh [--dry-run]
set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRY=0
for a in "$@"; do
  case "$a" in
    --dry-run) DRY=1 ;;
    *) echo "unknown flag: $a"; exit 2 ;;
  esac
done

# canonical skill root. read natively by Codex (project scope), Gemini CLI, GitHub Copilot
# CLI and OpenCode; fanned out below to the hosts that only read their own directory.
SKILLS_ROOT="$HOME/.agents/skills"

# host skill dirs that need per-skill symlinks, only for hosts actually present
HOST_SKILL_DIRS=()
if command -v claude >/dev/null 2>&1 || [ -d "$HOME/.claude" ]; then
  HOST_SKILL_DIRS+=("$HOME/.claude/skills")
fi
if command -v codex >/dev/null 2>&1 || [ -d "$HOME/.codex" ]; then
  HOST_SKILL_DIRS+=("$HOME/.codex/skills")
fi

RESULTS=()
run_step() {
  local name="$1"; shift
  local start end secs rc
  start=$(date +%s)
  "$@"
  rc=$?
  end=$(date +%s)
  secs=$((end - start))
  if [ $rc -eq 0 ]; then
    RESULTS+=("$(printf '%-28s ok      %3ds' "$name" "$secs")")
  else
    RESULTS+=("$(printf '%-28s FAILED  %3ds' "$name" "$secs")")
  fi
  return 0
}

# link one skill into the canonical root, then into every host dir that needs its own copy.
# never clobbers a real directory: if a host already has a non-symlink skill of that name,
# it is left alone and reported.
link_skill() {
  local name="$1" src="$2"
  local canonical="$SKILLS_ROOT/$name"
  local host target

  mkdir -p "$SKILLS_ROOT"
  if [ -e "$canonical" ] && [ ! -L "$canonical" ]; then
    local backup="$canonical.bak-$(date +%Y%m%d)"
    mv "$canonical" "$backup"
    echo "  backup saved at $backup"
  fi
  ln -sfn "$src" "$canonical"

  for host in "${HOST_SKILL_DIRS[@]}"; do
    # host dir already IS the canonical root (unified via a directory symlink): nothing to do
    if [ -e "$host" ] && [ "$(readlink -f "$host")" = "$(readlink -f "$SKILLS_ROOT")" ]; then
      continue
    fi
    mkdir -p "$host"
    target="$host/$name"
    if [ -e "$target" ] && [ ! -L "$target" ]; then
      echo "  $target is a real directory, leaving it alone"
      continue
    fi
    ln -sfn "$canonical" "$target"
  done
}

echo "my-llm-kit :: setup"
echo "repo:        $REPO_DIR"
echo "skill root:  $SKILLS_ROOT"
if [ ${#HOST_SKILL_DIRS[@]} -gt 0 ]; then
  echo "fan out to:  ${HOST_SKILL_DIRS[*]}"
else
  echo "fan out to:  (none detected, the canonical root covers Codex/Gemini/Copilot/OpenCode)"
fi
[ "$DRY" -eq 1 ] && echo "dry-run mode: no changes will be made"
echo

# 1. check binaries (read-only, runs even in dry-run)
check_bins() {
  local missing=0
  for b in git python3 pip3 node npx; do
    if ! command -v "$b" >/dev/null 2>&1; then
      echo "  missing: $b"
      missing=1
    fi
  done
  local hosts=""
  for b in claude codex opencode gemini copilot cursor-agent; do
    command -v "$b" >/dev/null 2>&1 && hosts="$hosts $b"
  done
  if [ -n "$hosts" ]; then
    echo "  agent hosts found:$hosts"
  else
    echo "  no agent host binary found: skills still install, nothing will read them yet"
  fi
  return $missing
}
run_step "check binaries" check_bins

# 2. pip install
install_python_pkgs() {
  if [ "$DRY" -eq 1 ]; then
    echo "  [dry-run] pip3 install --user --break-system-packages markitdown[all] paper-search-mcp 'mcp<2.0.0'"
    return 0
  fi
  # paper-search-mcp declares mcp[cli]>=1.6.0 with no upper bound; mcp 2.0.0 broke fastmcp, so we pin <2.0.0
  pip3 install --quiet --user --break-system-packages "markitdown[all]" paper-search-mcp "mcp<2.0.0"
}
run_step "pip markitdown+paper-search" install_python_pkgs

# 3. register the paper-search MCP on every host present.
# there is no shared MCP config across hosts: Claude Code, Codex and OpenCode each use a
# different file and format, so this branches per host instead of writing one path.
register_mcp() {
  if command -v claude >/dev/null 2>&1; then
    if claude mcp list 2>/dev/null | grep -q "^paper-search"; then
      echo "  claude: paper-search already registered, skipping"
    elif [ "$DRY" -eq 1 ]; then
      echo "  [dry-run] claude mcp add --scope user paper-search -- paper-search-mcp"
    else
      claude mcp add --scope user paper-search -- paper-search-mcp
    fi
  fi

  if command -v codex >/dev/null 2>&1; then
    if codex mcp list 2>/dev/null | grep -q "paper-search"; then
      echo "  codex: paper-search already registered, skipping"
    elif [ "$DRY" -eq 1 ]; then
      echo "  [dry-run] codex mcp add paper-search -- paper-search-mcp"
    else
      codex mcp add paper-search -- paper-search-mcp
    fi
  fi

  if command -v opencode >/dev/null 2>&1; then
    echo "  opencode: add paper-search by hand in ~/.config/opencode/opencode.json"
    echo '           {"mcp":{"paper-search":{"type":"local","command":["paper-search-mcp"]}}}'
  fi
}
run_step "register MCP paper-search" register_mcp

# 4. skills vendored in this repo
link_vendored_skills() {
  if [ "$DRY" -eq 1 ]; then
    echo "  [dry-run] link every directory under skills/ into $SKILLS_ROOT (+ host fan-out)"
    return 0
  fi
  local dir
  for dir in "$REPO_DIR/skills/"*/; do
    link_skill "$(basename "$dir")" "${dir%/}"
  done
}
run_step "vendored skills" link_vendored_skills

# 4b. own skill repos: clone if missing, then link
OWN_REPOS=(
  "unslop|https://github.com/badmuriss/unslop"
  "incredibly-pretty-websites|https://github.com/badmuriss/incredibly-pretty-websites"
  "site-audit|https://github.com/badmuriss/site-audit"
)
setup_own_repos() {
  local entry name url repo
  for entry in "${OWN_REPOS[@]}"; do
    name="${entry%%|*}"
    url="${entry#*|}"
    repo="$HOME/Documents/$name"

    if [ "$DRY" -eq 1 ]; then
      [ -d "$repo" ] || echo "  [dry-run] git clone $url $repo"
      echo "  [dry-run] link $name -> $repo (+ host fan-out)"
      continue
    fi

    [ -d "$repo" ] || git clone "$url" "$repo" || return 1
    link_skill "$name" "$repo"
  done
}
run_step "own skill repos" setup_own_repos

# 4c. community skills: clone into the canonical root, then fan out. skip what is already there.
COMMUNITY_SKILLS=(
  "humanizer|https://github.com/blader/humanizer"
  "notebooklm|https://github.com/PleasePrompto/notebooklm-skill"
  "llm-council|https://github.com/tenfoldmarc/llm-council-skill"
)
install_community_skills() {
  local entry name url target
  mkdir -p "$SKILLS_ROOT"
  for entry in "${COMMUNITY_SKILLS[@]}"; do
    name="${entry%%|*}"
    url="${entry#*|}"
    target="$SKILLS_ROOT/$name"
    if [ -e "$target" ]; then
      echo "  $name already present, skipping"
      continue
    fi
    if [ "$DRY" -eq 1 ]; then
      echo "  [dry-run] git clone $url $target (+ host fan-out)"
      continue
    fi
    git clone "$url" "$target" || return 1
    link_skill "$name" "$target"
  done
}
run_step "community skills" install_community_skills

# 4d. firecrawl CLI + its skills (needs `firecrawl login` afterwards to actually work)
install_firecrawl() {
  if [ -e "$SKILLS_ROOT/firecrawl" ] || [ -e "$HOME/.claude/skills/firecrawl" ]; then
    echo "  firecrawl skills already present, skipping"
    return 0
  fi
  if [ "$DRY" -eq 1 ]; then
    echo "  [dry-run] npm install -g firecrawl-cli && firecrawl setup skills"
    return 0
  fi
  command -v firecrawl >/dev/null 2>&1 || npm install -g firecrawl-cli || return 1
  firecrawl setup skills
}
run_step "firecrawl CLI + skills" install_firecrawl

# 5. AGENTS.md: one file, read by every host through its own expected filename
link_agents_md() {
  local src="$REPO_DIR/AGENTS.md"
  local shared="$HOME/.agents/AGENTS.md"

  if [ ! -f "$src" ]; then
    echo "  $src does not exist, skipping"
    return 0
  fi

  # every host path that should end up pointing at the shared file
  local -a aliases=("$HOME/.claude/CLAUDE.md" "$HOME/.codex/AGENTS.md")

  if [ "$DRY" -eq 1 ]; then
    echo "  [dry-run] symlink $shared -> $src (with backup if needed)"
    local a
    for a in "${aliases[@]}"; do echo "  [dry-run] symlink $a -> $shared"; done
    return 0
  fi

  mkdir -p "$HOME/.agents"
  if [ -e "$shared" ] && [ ! -L "$shared" ]; then
    local backup="$shared.bak-$(date +%Y%m%d)"
    cp "$shared" "$backup"
    echo "  backup saved at $backup"
  fi
  ln -sfn "$src" "$shared"

  local alias_path dir
  for alias_path in "${aliases[@]}"; do
    dir="$(dirname "$alias_path")"
    [ -d "$dir" ] || continue          # host not installed, don't create its config dir
    if [ -e "$alias_path" ] && [ ! -L "$alias_path" ]; then
      cp "$alias_path" "$alias_path.bak-$(date +%Y%m%d)"
      echo "  backup saved at $alias_path.bak-$(date +%Y%m%d)"
    fi
    ln -sfn "$shared" "$alias_path"
  done
}
run_step "AGENTS.md" link_agents_md

# 6. plugins: Claude Code only, no equivalent on the other hosts. skipped when claude is absent.
PLUGINS=(
  "Chachamaru127/claude-code-harness|claude-code-harness@claude-code-harness-marketplace"
  "anthropics/claude-plugins-official|chrome-devtools-mcp@claude-plugins-official"
  "anthropics/claude-plugins-official|frontend-design@claude-plugins-official"
  "cloudflare/skills|cloudflare@cloudflare"
  "mvanhorn/last30days-skill|last30days@last30days-skill"
)
install_plugins() {
  if ! command -v claude >/dev/null 2>&1; then
    echo "  claude not installed, skipping plugins (Claude Code only)"
    return 0
  fi
  local installed entry market plugin
  installed="$(claude plugin list 2>/dev/null)"
  for entry in "${PLUGINS[@]}"; do
    market="${entry%%|*}"
    plugin="${entry#*|}"
    if echo "$installed" | grep -qF "$plugin"; then
      echo "  $plugin already installed, skipping"
      continue
    fi
    if [ "$DRY" -eq 1 ]; then
      echo "  [dry-run] claude plugin marketplace add $market && claude plugin install $plugin"
      continue
    fi
    claude plugin marketplace add "$market" >/dev/null 2>&1
    claude plugin install "$plugin"
  done
}
run_step "plugins (Claude Code)" install_plugins

echo
echo "heavy dependencies (mineru, docling) are not installed by this script."
echo "they are opt-in: pip3 install --user mineru docling"

echo
echo "== summary =="
for r in "${RESULTS[@]}"; do
  echo "$r"
done
