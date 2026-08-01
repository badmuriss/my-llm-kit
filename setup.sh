#!/usr/bin/env bash
# my-llm-kit :: installs dependencies, registers MCP servers and symlinks skills. idempotent.
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

echo "my-llm-kit :: setup"
echo "repo: $REPO_DIR"
[ "$DRY" -eq 1 ] && echo "dry-run mode: no changes will be made"
echo

# 1. check binaries (read-only, runs even in dry-run)
check_bins() {
  local missing=0
  for b in claude git python3 pip3 node npx; do
    if ! command -v "$b" >/dev/null 2>&1; then
      echo "  missing: $b"
      missing=1
    fi
  done
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

# 3. register the paper-search MCP (user scope), without duplicating
register_mcp() {
  if claude mcp list 2>/dev/null | grep -q "^paper-search"; then
    echo "  paper-search already registered, skipping"
    return 0
  fi
  if [ "$DRY" -eq 1 ]; then
    echo "  [dry-run] claude mcp add --scope user paper-search -- paper-search-mcp"
    return 0
  fi
  claude mcp add --scope user paper-search -- paper-search-mcp
}
run_step "register MCP paper-search" register_mcp

# 4. symlink every skill vendored in this repo
link_skills() {
  if [ "$DRY" -eq 1 ]; then
    echo "  [dry-run] symlink every directory under skills/ into ~/.claude/skills/"
    return 0
  fi
  mkdir -p "$HOME/.claude/skills"
  local dir name target backup
  for dir in "$REPO_DIR/skills/"*/; do
    name="$(basename "$dir")"
    target="$HOME/.claude/skills/$name"
    if [ -e "$target" ] && [ ! -L "$target" ]; then
      backup="$target.bak-$(date +%Y%m%d)"
      mv "$target" "$backup"
      echo "  backup saved at $backup"
    fi
    ln -sfn "${dir%/}" "$target"
  done
}
run_step "symlink vendored skills" link_skills

# 4b. own skill repos: clone if missing, symlink into ~/.claude/skills/
OWN_REPOS=(
  "unslop|https://github.com/badmuriss/unslop"
  "incredibly-pretty-websites|https://github.com/badmuriss/incredibly-pretty-websites"
  "site-audit|https://github.com/badmuriss/site-audit"
)
setup_own_repos() {
  local entry name url repo target backup
  for entry in "${OWN_REPOS[@]}"; do
    name="${entry%%|*}"
    url="${entry#*|}"
    repo="$HOME/Documents/$name"
    target="$HOME/.claude/skills/$name"

    if [ "$DRY" -eq 1 ]; then
      [ -d "$repo" ] || echo "  [dry-run] git clone $url $repo"
      echo "  [dry-run] symlink $target -> $repo (with backup if needed)"
      continue
    fi

    if [ ! -d "$repo" ]; then
      git clone "$url" "$repo" || return 1
    fi

    mkdir -p "$HOME/.claude/skills"
    if [ -e "$target" ] && [ ! -L "$target" ]; then
      backup="$target.bak-$(date +%Y%m%d)"
      cp -r "$target" "$backup"
      echo "  backup saved at $backup"
    fi

    ln -sfn "$repo" "$target"
  done
}
run_step "own skill repos" setup_own_repos

# 4c. community skills: clone straight into ~/.claude/skills/, skip anything already there
COMMUNITY_SKILLS=(
  "humanizer|https://github.com/blader/humanizer"
  "notebooklm|https://github.com/PleasePrompto/notebooklm-skill"
  "llm-council|https://github.com/tenfoldmarc/llm-council-skill"
  "x-article-publisher|https://github.com/wshuyi/x-article-publisher-skill"
  "resume-tailoring|https://github.com/varunr89/resume-tailoring-skill"
)
install_community_skills() {
  mkdir -p "$HOME/.claude/skills"
  local entry name url target
  for entry in "${COMMUNITY_SKILLS[@]}"; do
    name="${entry%%|*}"
    url="${entry#*|}"
    target="$HOME/.claude/skills/$name"
    if [ -e "$target" ]; then
      echo "  $name already present, skipping"
      continue
    fi
    if [ "$DRY" -eq 1 ]; then
      echo "  [dry-run] git clone $url $target"
      continue
    fi
    git clone "$url" "$target" || return 1
  done
}
run_step "community skills" install_community_skills

# 4d. firecrawl CLI + its skills (needs `firecrawl login` afterwards to actually work)
install_firecrawl() {
  if [ -e "$HOME/.claude/skills/firecrawl" ]; then
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

# 5. symlink CLAUDE.md, with backup if a regular file already exists
link_claude_md() {
  local repo_claude_md="$REPO_DIR/CLAUDE.md"
  local target="$HOME/.claude/CLAUDE.md"

  if [ ! -f "$repo_claude_md" ]; then
    echo "  $repo_claude_md does not exist yet, skipping (added later)"
    return 0
  fi

  if [ -L "$target" ] && [ "$(readlink "$target")" = "$repo_claude_md" ]; then
    echo "  already the correct symlink, skipping"
    return 0
  fi

  if [ "$DRY" -eq 1 ]; then
    echo "  [dry-run] symlink $target -> $repo_claude_md (with backup if needed)"
    return 0
  fi

  if [ -e "$target" ] && [ ! -L "$target" ]; then
    local backup="$target.bak-$(date +%Y%m%d)"
    cp "$target" "$backup"
    echo "  backup saved at $backup"
  fi

  ln -sfn "$repo_claude_md" "$target"
}
run_step "symlink CLAUDE.md" link_claude_md

# 6. plugins: add each marketplace and install the plugin, skipping what is already there
PLUGINS=(
  "JuliusBrussee/caveman|caveman@caveman"
  "DietrichGebert/ponytail|ponytail@ponytail"
  "Chachamaru127/claude-code-harness|claude-code-harness@claude-code-harness-marketplace"
  "openai/codex-plugin-cc|codex@openai-codex"
  "anthropics/claude-plugins-official|chrome-devtools-mcp@claude-plugins-official"
  "anthropics/claude-plugins-official|frontend-design@claude-plugins-official"
  "cloudflare/skills|cloudflare@cloudflare"
  "mvanhorn/last30days-skill|last30days@last30days-skill"
)
install_plugins() {
  local installed entry market plugin
  installed="$(claude plugin list 2>/dev/null)"
  for entry in "${PLUGINS[@]}"; do
    market="${entry%%|*}"
    plugin="${entry#*|}"
    if echo "$installed" | grep -q "$plugin"; then
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
run_step "plugins" install_plugins

echo
echo "heavy dependencies (mineru, docling) are not installed by this script."
echo "they are opt-in: pip3 install --user mineru docling"

echo
echo "== summary =="
for r in "${RESULTS[@]}"; do
  echo "$r"
done
