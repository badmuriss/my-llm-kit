#!/usr/bin/env bash
# my-llm-kit :: instala dependencias, registra MCP e symlinka skills. idempotente.
# uso: ./setup.sh [--dry-run]
set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRY=0
for a in "$@"; do
  case "$a" in
    --dry-run) DRY=1 ;;
    *) echo "flag desconhecida: $a"; exit 2 ;;
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
    RESULTS+=("$(printf '%-28s FALHOU  %3ds' "$name" "$secs")")
  fi
  return 0
}

echo "my-llm-kit :: setup"
echo "repo: $REPO_DIR"
[ "$DRY" -eq 1 ] && echo "modo dry-run: nenhuma alteração será feita"
echo

# 1. checar binarios (somente leitura, roda mesmo em dry-run)
check_bins() {
  local missing=0
  for b in claude git python3 pip3 node npx; do
    if ! command -v "$b" >/dev/null 2>&1; then
      echo "  faltando: $b"
      missing=1
    fi
  done
  return $missing
}
run_step "checar binarios" check_bins

# 2. pip install
install_python_pkgs() {
  if [ "$DRY" -eq 1 ]; then
    echo "  [dry-run] pip3 install --user --break-system-packages markitdown[all] paper-search-mcp 'mcp<2.0.0'"
    return 0
  fi
  # paper-search-mcp declara mcp[cli]>=1.6.0 sem teto; mcp 2.0.0 quebrou fastmcp, entao fixamos <2.0.0
  pip3 install --quiet --user --break-system-packages "markitdown[all]" paper-search-mcp "mcp<2.0.0"
}
run_step "pip markitdown+paper-search" install_python_pkgs

# 3. registrar MCP paper-search (user scope), sem duplicar
register_mcp() {
  if claude mcp list 2>/dev/null | grep -q "^paper-search"; then
    echo "  paper-search já registrado, pulando"
    return 0
  fi
  if [ "$DRY" -eq 1 ]; then
    echo "  [dry-run] claude mcp add --scope user paper-search -- paper-search-mcp"
    return 0
  fi
  claude mcp add --scope user paper-search -- paper-search-mcp
}
run_step "registrar MCP paper-search" register_mcp

# 4. symlink das skills do repo
link_skills() {
  if [ "$DRY" -eq 1 ]; then
    echo "  [dry-run] symlink skills/pesquisa e skills/ingestao para ~/.claude/skills/"
    return 0
  fi
  mkdir -p "$HOME/.claude/skills"
  for skill in pesquisa ingestao; do
    ln -sfn "$REPO_DIR/skills/$skill" "$HOME/.claude/skills/$skill"
  done
}
run_step "symlink skills pesquisa+ingestao" link_skills

# 4b. sistema de escrita (unslop): clona se faltar, symlinka para ~/.claude/skills/unslop
setup_unslop() {
  local unslop_repo="$HOME/Documents/unslop"
  local target="$HOME/.claude/skills/unslop"

  if [ "$DRY" -eq 1 ]; then
    [ -d "$unslop_repo" ] || echo "  [dry-run] git clone https://github.com/badmuriss/unslop $unslop_repo"
    echo "  [dry-run] symlink $target -> $unslop_repo (com backup se necessário)"
    return 0
  fi

  if [ ! -d "$unslop_repo" ]; then
    git clone https://github.com/badmuriss/unslop "$unslop_repo" || return 1
  fi

  mkdir -p "$HOME/.claude/skills"
  if [ -e "$target" ] && [ ! -L "$target" ]; then
    local backup="$target.bak-$(date +%Y%m%d)"
    cp -r "$target" "$backup"
    echo "  backup salvo em $backup"
  fi

  ln -sfn "$unslop_repo" "$target"
}
run_step "sistema de escrita (unslop)" setup_unslop

# 5. symlink CLAUDE.md, com backup se ja existir arquivo normal
link_claude_md() {
  local repo_claude_md="$REPO_DIR/CLAUDE.md"
  local target="$HOME/.claude/CLAUDE.md"

  if [ ! -f "$repo_claude_md" ]; then
    echo "  $repo_claude_md ainda não existe, pulando (adicionado depois)"
    return 0
  fi

  if [ -L "$target" ] && [ "$(readlink "$target")" = "$repo_claude_md" ]; then
    echo "  já é o symlink correto, pulando"
    return 0
  fi

  if [ "$DRY" -eq 1 ]; then
    echo "  [dry-run] symlink $target -> $repo_claude_md (com backup se necessário)"
    return 0
  fi

  if [ -e "$target" ] && [ ! -L "$target" ]; then
    local backup="$target.bak-$(date +%Y%m%d)"
    cp "$target" "$backup"
    echo "  backup salvo em $backup"
  fi

  ln -sfn "$repo_claude_md" "$target"
}
run_step "symlink CLAUDE.md" link_claude_md

# 6. plugin last30days (pulso da comunidade na skill pesquisa), sem duplicar
install_last30days() {
  if claude plugin list 2>/dev/null | grep -q "last30days"; then
    echo "  plugin last30days já instalado, pulando"
    return 0
  fi
  if [ "$DRY" -eq 1 ]; then
    echo "  [dry-run] claude plugin marketplace add mvanhorn/last30days-skill + install"
    return 0
  fi
  claude plugin marketplace add mvanhorn/last30days-skill >/dev/null 2>&1
  claude plugin install last30days@last30days-skill
}
run_step "plugin last30days" install_last30days

echo
echo "dependências pesadas (mineru, docling) não são instaladas por este script."
echo "são opt-in: pip3 install --user mineru docling"

echo
echo "== sumário =="
for r in "${RESULTS[@]}"; do
  echo "$r"
done
