#!/usr/bin/env bash
# Install the /spec + /impl workflow into ~/.claude, plus the skills it relies on.
set -e

LINK=0
for arg in "$@"; do
  case "$arg" in
    --link) LINK=1 ;;
    -h|--help)
      cat <<'USAGE'
usage: install.sh [--link]

  (no flag)  copy commands/ and agents/ into $HOME/.claude as regular files.
  --link     symlink them to this clone instead, so `git pull` updates them in
             place. Only useful if you keep the clone around.
  -h,--help  this text.
USAGE
      exit 0 ;;
    *) echo "unknown option: $arg (try --help)" >&2; exit 2 ;;
  esac
done

DIR="$HOME/.claude"
mkdir -p "$DIR/commands" "$DIR/agents"

SRC="$(cd "$(dirname "$0")" && pwd)"
if [ ! -d "$SRC/commands" ]; then
  SRC="$(mktemp -d)"
  git clone --depth 1 https://github.com/badmuriss/my-llm-kit "$SRC"
fi

install_one() {
  # $1 = source file, $2 = destination file
  rm -f "$2"
  if [ "$LINK" = 1 ]; then ln -s "$1" "$2"; else cp "$1" "$2"; fi
}
for f in "$SRC"/commands/*.md; do install_one "$f" "$DIR/commands/$(basename "$f")"; done
for f in "$SRC"/agents/*.md; do install_one "$f" "$DIR/agents/$(basename "$f")"; done

npx -y skills add badmuriss/incredibly-pretty-websites -g -y
npx -y skills add badmuriss/unslop -g -y
npx -y skills add mattpocock/skills --skill grill-with-docs -g -y
npx -y skills add badmuriss/site-audit -g -y
npx -y skills add vercel-labs/agent-skills --skill vercel-react-best-practices -g -y
echo "done — /spec and /impl available in Claude Code"
