#!/usr/bin/env bash
# Install the spec/impl skills into ~/.claude, plus the skills they rely on.
set -e

LINK=0
for arg in "$@"; do
  case "$arg" in
    --link) LINK=1 ;;
    -h|--help)
      cat <<'USAGE'
usage: install.sh [--link]

  (no flag)  copy agents/ into $HOME/.claude as regular files.
  --link     symlink them to this clone instead, so `git pull` updates them in
             place. Only useful if you keep the clone around.
  -h,--help  this text.
USAGE
      exit 0 ;;
    *) echo "unknown option: $arg (try --help)" >&2; exit 2 ;;
  esac
done

DIR="$HOME/.claude"
mkdir -p "$DIR/agents"

SRC="$(cd "$(dirname "$0")" && pwd)"
if [ ! -d "$SRC/skills" ]; then
  SRC="$(mktemp -d)"
  git clone --depth 1 https://github.com/badmuriss/my-llm-kit "$SRC"
fi
INSTALL_MANIFEST="$SRC/install-manifest.json"

install_one() {
  # $1 = source file, $2 = destination file
  rm -f "$2"
  if [ "$LINK" = 1 ]; then ln -s "$1" "$2"; else cp "$1" "$2"; fi
}
for f in "$SRC"/agents/*.md; do install_one "$f" "$DIR/agents/$(basename "$f")"; done

install_vendored_skill() {
  local name="$1"
  local source="$SRC/skills/$name"
  local canonical="$HOME/.agents/skills/$name"
  local claude_target="$HOME/.claude/skills/$name"

  mkdir -p "$HOME/.agents/skills" "$HOME/.claude/skills"
  if [ ! -e "$canonical" ] && [ ! -L "$canonical" ]; then
    if [ "$LINK" = 1 ]; then
      ln -s "$source" "$canonical"
    else
      cp -R "$source" "$canonical"
    fi
  elif [ "$LINK" = 1 ] && [ -L "$canonical" ]; then
    ln -sfn "$source" "$canonical"
  elif [ ! -L "$canonical" ]; then
    echo "$canonical is a real directory, leaving it alone"
  fi

  if [ ! -e "$claude_target" ] || [ -L "$claude_target" ]; then
    ln -sfn "$canonical" "$claude_target"
  else
    echo "$claude_target is a real directory, leaving it alone"
  fi
}

while IFS= read -r skill_name; do
  [ -n "$skill_name" ] || continue
  install_vendored_skill "$skill_name"
done < <(
  python3 "$SRC/scripts/read_install_manifest.py" core_install_skills \
    --manifest "$INSTALL_MANIFEST"
)

if ! python3 -c 'from jsonschema import Draft202012Validator' 2>/dev/null; then
  python3 -m pip install --user --break-system-packages -r "$SRC/skills/agent-graph/requirements.txt"
fi
python3 "$HOME/.agents/skills/agent-graph/scripts/agent_graph.py" --help >/dev/null
echo "done: core skills and graph runtime available in Claude Code"
echo "Use setup.sh --full for optional integrations and specialist skills."
