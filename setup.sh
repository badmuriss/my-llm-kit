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

# 4. symlink the repo's skills
link_skills() {
  if [ "$DRY" -eq 1 ]; then
    echo "  [dry-run] symlink skills/pesquisa and skills/ingestao into ~/.claude/skills/"
    return 0
  fi
  mkdir -p "$HOME/.claude/skills"
  for skill in pesquisa ingestao; do
    ln -sfn "$REPO_DIR/skills/$skill" "$HOME/.claude/skills/$skill"
  done
}
run_step "symlink skills pesquisa+ingestao" link_skills

# 4b. writing system (unslop): clone if missing, symlink to ~/.claude/skills/unslop
setup_unslop() {
  local unslop_repo="$HOME/Documents/unslop"
  local target="$HOME/.claude/skills/unslop"

  if [ "$DRY" -eq 1 ]; then
    [ -d "$unslop_repo" ] || echo "  [dry-run] git clone https://github.com/badmuriss/unslop $unslop_repo"
    echo "  [dry-run] symlink $target -> $unslop_repo (with backup if needed)"
    return 0
  fi

  if [ ! -d "$unslop_repo" ]; then
    git clone https://github.com/badmuriss/unslop "$unslop_repo" || return 1
  fi

  mkdir -p "$HOME/.claude/skills"
  if [ -e "$target" ] && [ ! -L "$target" ]; then
    local backup="$target.bak-$(date +%Y%m%d)"
    cp -r "$target" "$backup"
    echo "  backup saved at $backup"
  fi

  ln -sfn "$unslop_repo" "$target"
}
run_step "writing system (unslop)" setup_unslop

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

# 6. last30days plugin (community pulse for the pesquisa skill), without duplicating
install_last30days() {
  if claude plugin list 2>/dev/null | grep -q "last30days"; then
    echo "  last30days plugin already installed, skipping"
    return 0
  fi
  if [ "$DRY" -eq 1 ]; then
    echo "  [dry-run] claude plugin marketplace add mvanhorn/last30days-skill + install"
    return 0
  fi
  claude plugin marketplace add mvanhorn/last30days-skill >/dev/null 2>&1
  claude plugin install last30days@last30days-skill
}
run_step "last30days plugin" install_last30days

echo
echo "heavy dependencies (mineru, docling) are not installed by this script."
echo "they are opt-in: pip3 install --user mineru docling"

echo
echo "== summary =="
for r in "${RESULTS[@]}"; do
  echo "$r"
done
