#!/usr/bin/env bash
# my-llm-kit :: installs dependencies, registers MCP servers and links skills. idempotent.
# host-agnostic: skills land in ~/.agents/skills (the cross-agent convention) and are
# fanned out to the host dirs that don't read it natively.
# usage: ./setup.sh [--dry-run]
set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_MANIFEST="$REPO_DIR/install-manifest.json"
SCRAPINGDOG_MCP_PACKAGE="https://codeload.github.com/badmuriss/Scrapingdog-mcp/tar.gz/8084d8a77b5836f7c0ef7cfbaec5ab12f1fcb741"
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
HAD_FAILURE=0
manifest_rows() {
  python3 "$REPO_DIR/scripts/read_install_manifest.py" "$1" --manifest "$INSTALL_MANIFEST"
}

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
    HAD_FAILURE=1
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
  if [ "$canonical" != "$src" ] && [ -e "$canonical" ] && [ ! -L "$canonical" ]; then
    # the backup must land OUTSIDE the skill root. every host indexes every directory in
    # there, so a `foo.bak-20260807` sitting next to `foo` shows up as a second, stale
    # copy of the same skill in the picker.
    local backup_root="$HOME/.agents/skills-backup"
    local backup="$backup_root/$name-$(date +%Y%m%d)"
    mkdir -p "$backup_root"
    mv "$canonical" "$backup"
    echo "  backup saved at $backup"
  fi
  if [ "$canonical" != "$src" ]; then
    ln -sfn "$src" "$canonical"
  fi

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
  for section in own_repositories community_skills plugins reduced_install_skills; do
    if ! manifest_rows "$section" >/dev/null; then
      echo "  invalid install manifest section: $section"
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

install_scrapingdog_mcp() {
  if [ "$DRY" -eq 1 ]; then
    echo "  [dry-run] npm install --global $SCRAPINGDOG_MCP_PACKAGE"
    echo "  [dry-run] npm ci --include=dev --prefix <npm-global>/scrapingdog-mcp"
    return 0
  fi
  npm install --global "$SCRAPINGDOG_MCP_PACKAGE"
  npm ci --include=dev --prefix "$(npm root --global)/scrapingdog-mcp"
}
run_step "install MCP scrapingdog" install_scrapingdog_mcp

# ScrapingDog's MCP package exposes its public-web APIs directly to agents.
# The child process inherits SCRAPINGDOG_API_KEY at runtime, so setup never copies the
# secret into an agent config file.
register_scrapingdog_mcp() {
  local entrypoint details
  entrypoint="$(npm root --global)/scrapingdog-mcp/dist/index.js"

  if command -v claude >/dev/null 2>&1; then
    details="$(claude mcp get scrapingdog 2>/dev/null || true)"
    if grep -Fq "$entrypoint" <<<"$details"; then
      echo "  claude: scrapingdog already points to the pinned build, skipping"
    elif [ "$DRY" -eq 1 ]; then
      [ -z "$details" ] || echo "  [dry-run] claude mcp remove scrapingdog -s user"
      echo "  [dry-run] claude mcp add --scope user scrapingdog -- node $entrypoint"
    else
      [ -z "$details" ] || claude mcp remove scrapingdog -s user
      claude mcp add --scope user scrapingdog -- node "$entrypoint"
    fi
  fi

  if command -v codex >/dev/null 2>&1; then
    details="$(codex mcp get scrapingdog 2>/dev/null || true)"
    if grep -Fq "$entrypoint" <<<"$details"; then
      echo "  codex: scrapingdog already points to the pinned build, skipping"
    elif [ "$DRY" -eq 1 ]; then
      [ -z "$details" ] || echo "  [dry-run] codex mcp remove scrapingdog"
      echo "  [dry-run] codex mcp add scrapingdog -- node $entrypoint"
    else
      [ -z "$details" ] || codex mcp remove scrapingdog
      codex mcp add scrapingdog -- node "$entrypoint"
    fi
  fi

  if command -v opencode >/dev/null 2>&1; then
    echo "  opencode: add scrapingdog by hand in ~/.config/opencode/opencode.json"
    echo "           {\"mcp\":{\"scrapingdog\":{\"type\":\"local\",\"command\":[\"node\",\"$entrypoint\"]}}}"
  fi

  if [ -z "${SCRAPINGDOG_API_KEY:-}" ]; then
    echo "  scrapingdog registered without a key; export SCRAPINGDOG_API_KEY before starting an agent"
  fi
}
run_step "register MCP scrapingdog" register_scrapingdog_mcp

preflight_scrapingdog_mcp() {
  local entrypoint
  entrypoint="$(npm root --global)/scrapingdog-mcp/dist/index.js"
  if [ "$DRY" -eq 1 ]; then
    echo "  [dry-run] node scripts/preflight_scrapingdog_mcp.mjs $entrypoint"
    return 0
  fi
  node "$REPO_DIR/scripts/preflight_scrapingdog_mcp.mjs" "$entrypoint"
}
run_step "preflight MCP scrapingdog" preflight_scrapingdog_mcp

# An installed package is not proof that research works. Exercise the CLI against one
# stable arXiv title and fail visibly when the executable or query is unavailable.
preflight_paper_search() {
  if [ "$DRY" -eq 1 ]; then
    echo "  [dry-run] paper-search-mcp --version"
    echo "  [dry-run] paper-search search 'CodePlan repository-level coding' -s arxiv -n 1"
    return 0
  fi
  if ! command -v paper-search-mcp >/dev/null 2>&1; then
    echo "  paper-search-mcp executable is missing"
    echo "  web fallback active: ScrapingDog when keyed, then Firecrawl, then host web search"
    return 1
  fi
  if ! command -v paper-search >/dev/null 2>&1; then
    echo "  paper-search executable is missing"
    echo "  web fallback active: ScrapingDog when keyed, then Firecrawl, then host web search"
    return 1
  fi
  if ! paper-search-mcp --version; then
    echo "  paper-search-mcp version check failed"
    echo "  web fallback active: ScrapingDog when keyed, then Firecrawl, then host web search"
    return 1
  fi

  local query_output query_status
  if command -v timeout >/dev/null 2>&1; then
    query_output="$(timeout 25s paper-search search 'CodePlan repository-level coding' -s arxiv -n 1 2>&1)"
    query_status=$?
  else
    query_output="$(paper-search search 'CodePlan repository-level coding' -s arxiv -n 1 2>&1)"
    query_status=$?
  fi
  if [ "$query_status" -ne 0 ]; then
    echo "  paper-search query failed with exit code $query_status"
    echo "$query_output" | sed -n '1,4p'
    echo "  web fallback active: ScrapingDog when keyed, then Firecrawl, then host web search"
    return 1
  fi
  if [[ "$query_output" != *"CodePlan"* && "$query_output" != *"2309.12499"* ]]; then
    echo "  paper-search query returned no identifiable result"
    echo "$query_output" | sed -n '1,4p'
    echo "  web fallback active: ScrapingDog when keyed, then Firecrawl, then host web search"
    return 1
  fi
  echo "  paper-search query returned CodePlan"
}
run_step "preflight paper-search" preflight_paper_search

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
setup_own_repos() {
  local name url repo
  while IFS='|' read -r name url; do
    [ -n "$name" ] || continue
    repo="$HOME/Documents/$name"

    if [ "$DRY" -eq 1 ]; then
      [ -d "$repo" ] || echo "  [dry-run] git clone $url $repo"
      echo "  [dry-run] link $name -> $repo (+ host fan-out)"
      continue
    fi

    [ -d "$repo" ] || git clone "$url" "$repo" || return 1
    link_skill "$name" "$repo"
  done < <(manifest_rows own_repositories)
}
run_step "own skill repos" setup_own_repos

# 4c. community skills: clone into the canonical root, then fan out. skip what is already there.
install_community_skills() {
  local name url target
  [ "$DRY" -eq 1 ] || mkdir -p "$SKILLS_ROOT"
  while IFS='|' read -r name url; do
    [ -n "$name" ] || continue
    target="$SKILLS_ROOT/$name"
    if [ -L "$target" ] && [ ! -e "$target" ]; then
      [ "$DRY" -eq 1 ] || rm -f "$target"
    fi
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
  done < <(manifest_rows community_skills)
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

# 4e. the ingest skill shells out to `npx -y @firecrawl/anydoc`, no binary to install here,
# just a preflight check so a missing npx is a warning instead of a silent failure later.
check_anydoc_npx() {
  if ! command -v npx >/dev/null 2>&1; then
    echo "  warning: npx not found, the ingest skill needs npx for document conversion"
  fi
  return 0
}
run_step "ingest skill preflight (anydoc)" check_anydoc_npx

# 4f. every host dir gets a link for every skill in the canonical root, whatever put it there:
# this repo, a community clone, the firecrawl CLI, or a plain `npx skills add --global`.
# the installers above only link on FIRST install, so a host added later (the whole point of a
# portable kit: you install Codex on a machine that already ran this script) would never see
# the skills already sitting on disk. This step is what makes adding a host a no-op.
fan_out_all_skills() {
  if [ ${#HOST_SKILL_DIRS[@]} -eq 0 ]; then
    echo "  no host needs its own copy, the canonical root covers them"
    return 0
  fi
  local dir name host target linked=0 skipped=0
  for dir in "$SKILLS_ROOT"/*/; do
    [ -d "$dir" ] || continue          # skips broken symlinks too, -d follows the link
    name="$(basename "$dir")"
    for host in "${HOST_SKILL_DIRS[@]}"; do
      # host dir already IS the canonical root (unified via a directory symlink): nothing to do
      if [ -e "$host" ] && [ "$(readlink -f "$host")" = "$(readlink -f "$SKILLS_ROOT")" ]; then
        continue
      fi
      target="$host/$name"
      if [ -e "$target" ] && [ ! -L "$target" ]; then
        skipped=$((skipped + 1))       # a real directory the user owns, never clobber it
        continue
      fi
      if [ -L "$target" ] && [ "$(readlink -f "$target")" = "$(readlink -f "$dir")" ]; then
        continue                       # already points where it should
      fi
      if [ "$DRY" -eq 1 ]; then
        echo "  [dry-run] link $name into $host"
      else
        mkdir -p "$host"
        ln -sfn "${dir%/}" "$target"
      fi
      linked=$((linked + 1))
    done
  done
  echo "  $linked link(s) to create/update, $skipped real directory(ies) left alone"
}
run_step "fan out every skill to each host" fan_out_all_skills

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

# 6. plugins. Claude Code and Codex both read a git marketplace and both accept the
# `.claude-plugin/marketplace.json` layout, so the same three entries install on either host.
# Verified on codex-cli 0.146.0: `codex plugin marketplace add` resolves all three repos below
# and `codex plugin add <plugin>@<market>` installs them. Only the subcommand names differ
# (`claude plugin install` vs `codex plugin add`), so this branches on the verb, not the list.
# is "$plugin" already installed on "$host", given that host's `plugin list` output?
# the two hosts print different things and the difference is a trap:
#   claude lists ONLY installed plugins, so any match means installed.
#   codex lists EVERY known plugin with a STATUS column where "not installed" is a valid value,
#   and that string contains the word "installed", so match the comma in "installed, enabled".
plugin_installed() {
  local host="$1" plugin="$2" listing="$3"
  case "$host" in
    claude) echo "$listing" | grep -qF "$plugin" ;;
    codex)  echo "$listing" | grep -F "$plugin" | grep -q 'installed,' ;;
    *)      return 1 ;;
  esac
}

# install every plugin on one host. $1 host binary, $2 the install subcommand for that host.
install_plugins_for() {
  local host="$1" verb="$2"
  local installed market plugin marketplace_name add_output
  installed="$("$host" plugin list 2>/dev/null)"
  while IFS='|' read -r market plugin; do
    [ -n "$market" ] || continue
    if plugin_installed "$host" "$plugin" "$installed"; then
      echo "  $host: $plugin already installed, skipping"
      continue
    fi
    if [ "$DRY" -eq 1 ]; then
      echo "  [dry-run] $host plugin marketplace add $market && $host plugin $verb $plugin"
      continue
    fi
    if ! add_output="$("$host" plugin marketplace add "$market" 2>&1)"; then
      if [[ "$add_output" != *"already added from a different source"* ]]; then
        echo "  $host: could not add marketplace $market: $add_output"
        return 1
      fi
      marketplace_name="${plugin##*@}"
      echo "  $host: replacing stale marketplace $marketplace_name"
      "$host" plugin marketplace remove "$marketplace_name" || return 1
      "$host" plugin marketplace add "$market" || return 1
    fi
    "$host" plugin "$verb" "$plugin" || return 1
  done < <(manifest_rows plugins)
}

install_plugins() {
  local any=0 failed=0
  if command -v claude >/dev/null 2>&1; then
    install_plugins_for claude install || failed=1
    any=1
  fi
  if command -v codex >/dev/null 2>&1; then
    install_plugins_for codex add || failed=1
    any=1
  fi
  if [ "$any" -eq 0 ]; then
    echo "  neither claude nor codex installed, skipping plugins"
    echo "  (Gemini CLI, Copilot CLI and OpenCode have no plugin marketplace; the skills"
    echo "   in ~/.agents/skills already cover them)"
  fi
  return "$failed"
}
run_step "plugins (Claude Code + Codex)" install_plugins

# 7. install the cross-agent resource guard. The CLI admits new workers and heavy commands
# against machine-wide limits. A user timer removes orphaned workloads and excess idle
# agents; it leaves manual processes and persistent terminal shells alone.
install_resource_guard() {
  local source="$REPO_DIR/scripts/agent_resource_guard.py"
  local target="$HOME/.local/bin/agent-resource-guard"
  local unit_dir="$HOME/.config/systemd/user"

  [ -f "$source" ] || { echo "  $source is missing"; return 1; }
  if [ "$DRY" -eq 1 ]; then
    echo "  [dry-run] install agent-resource-guard into $target"
    if command -v systemctl >/dev/null 2>&1; then
      echo "  [dry-run] install and enable agent-resource-guard.timer"
    else
      echo "  systemd user manager unavailable; CLI only"
    fi
    return 0
  fi

  mkdir -p "$(dirname "$target")"
  install -m 0755 "$source" "$target"

  if ! command -v systemctl >/dev/null 2>&1 || ! systemctl --user show-environment >/dev/null 2>&1; then
    echo "  systemd user manager unavailable; installed CLI only"
    return 0
  fi

  mkdir -p "$unit_dir"
  install -m 0644 "$REPO_DIR/systemd/agent-resource-guard.service" "$unit_dir/"
  install -m 0644 "$REPO_DIR/systemd/agent-resource-guard.timer" "$unit_dir/"
  systemctl --user daemon-reload
  systemctl --user enable --now agent-resource-guard.timer
  "$target" prune --quiet
}
run_step "agent resource guard" install_resource_guard

# 8. dcg blocks destructive shell commands before execution. The calibrated config and
# allowlist live in dcg/ in this repo, with the reason for every entry written down.
install_dcg() {
  local dcg_bin="$HOME/.local/bin/dcg"
  local dcg_conf="$HOME/.config/dcg"

  if [ "$DRY" -eq 1 ]; then
    if [ -e "$dcg_bin" ]; then
      echo "  [dry-run] dcg already installed at $dcg_bin, skipping download"
    else
      echo "  [dry-run] curl -fsSL https://raw.githubusercontent.com/Dicklesworthstone/destructive_command_guard/main/install.sh | bash -s -- --no-configure --verify --no-gum"
    fi
    echo "  [dry-run] copy dcg/config.toml and dcg/allowlist.toml into $dcg_conf (backing up anything already there)"
    echo "  [dry-run] $dcg_bin install    # wires hooks into every supported host it finds"
    echo "  [dry-run] $dcg_bin doctor"
    return 0
  fi

  if [ -e "$dcg_bin" ]; then
    echo "  dcg already installed, skipping download"
  else
    curl -fsSL "https://raw.githubusercontent.com/Dicklesworthstone/destructive_command_guard/main/install.sh" | bash -s -- --no-configure --verify --no-gum || return 1
  fi

  # copy rather than symlink: this is a security config, and a symlink into a git
  # checkout means a `git pull` silently changes what the guard enforces.
  mkdir -p "$dcg_conf"
  local f
  for f in config.toml allowlist.toml; do
    [ -f "$REPO_DIR/dcg/$f" ] || continue
    if [ -f "$dcg_conf/$f" ] && ! cmp -s "$REPO_DIR/dcg/$f" "$dcg_conf/$f"; then
      cp "$dcg_conf/$f" "$dcg_conf/$f.bak-$(date +%Y%m%d)"
      echo "  backup saved at $dcg_conf/$f.bak-$(date +%Y%m%d)"
    fi
    cp "$REPO_DIR/dcg/$f" "$dcg_conf/$f"
  done

  # `dcg install` detects the hosts itself. As of dcg 0.9.4 it wires Claude Code, Codex CLI,
  # Gemini CLI, GitHub Copilot CLI and Cursor, emitting protocol-specific JSON per host, so
  # gating this on `claude` would have left every other host unguarded.
  "$dcg_bin" install
  "$dcg_bin" doctor || echo "  warning: dcg doctor reported issues"
}
run_step "dcg (destructive command guard)" install_dcg

# 9. Pipelock scans agent actions and wraps existing Codex MCP transports. The helper
# pins a release and verifies its published SHA-256 before atomically installing it.
install_pipelock() {
  local pipelock_bin="$HOME/.local/bin/pipelock"
  local -a install_args=("$REPO_DIR/scripts/install_pipelock.py" --target "$pipelock_bin")

  if [ "$DRY" -eq 1 ]; then
    install_args+=(--dry-run)
  fi
  python3 "${install_args[@]}" || return 1

  if [ "$DRY" -eq 1 ]; then
    if command -v codex >/dev/null 2>&1 || [ -d "$HOME/.codex" ]; then
      echo "  [dry-run] $pipelock_bin codex install --dry-run"
    fi
    if command -v claude >/dev/null 2>&1 || [ -d "$HOME/.claude" ]; then
      echo "  [dry-run] $pipelock_bin claude setup --dry-run"
    fi
    return 0
  fi

  [ -x "$pipelock_bin" ] || { echo "  Pipelock installer did not create $pipelock_bin"; return 1; }
  if command -v codex >/dev/null 2>&1; then
    "$pipelock_bin" codex install || return 1
  fi
  if command -v claude >/dev/null 2>&1; then
    "$pipelock_bin" claude setup || return 1
  fi
  if ! command -v codex >/dev/null 2>&1 && ! command -v claude >/dev/null 2>&1; then
    echo "  Pipelock installed; no Codex or Claude host found to configure"
  fi
}
run_step "pipelock agent traffic guard" install_pipelock

echo
echo "heavy dependencies (mineru, docling) are not installed by this script."
echo "they are opt-in: pip3 install --user mineru docling"

echo
echo "== summary =="
for r in "${RESULTS[@]}"; do
  echo "$r"
done

exit "$HAD_FAILURE"
