<p align="center"><img src="docs/banner.png" width="720" alt="my-llm-kit wordmark in white with mint-green hyphens on a near-black background, with the tagline: a personal, versioned coding-agent setup"></p>

<p align="center"><b>A portable coding-agent harness for research, planning, implementation, and clear technical writing.</b></p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="MIT license"></a>
  <a href="https://github.com/badmuriss/my-llm-kit/stargazers"><img src="https://img.shields.io/github/stars/badmuriss/my-llm-kit?style=flat-square" alt="GitHub stars"></a>
  <a href="https://github.com/badmuriss/my-llm-kit/commits/main"><img src="https://img.shields.io/github/last-commit/badmuriss/my-llm-kit?style=flat-square" alt="last commit"></a>
</p>

<p align="center">
  <a href="#install">Install</a> ·
  <a href="#how-the-harness-works">How it works</a> ·
  <a href="#whats-included">What's included</a> ·
  <a href="#supported-agents">Supported agents</a> ·
  <a href="#setup-details">Setup details</a>
</p>

## Install

The default setup installs the core skills and shared instructions. It does not
install provider integrations, plugins or specialist skill collections. Existing
skills and guards remain installed; core setup is not an uninstall operation.

Paste this into your coding agent:

```text
Install my-llm-kit from https://github.com/badmuriss/my-llm-kit.
Detect the operating system and preserve existing local changes and configuration.
Read AGENTS.md and the installation section of README.md.
Preview with ./setup.sh --dry-run on Linux/macOS or .\setup.ps1 -DryRun on Windows.
Install the default core, resolve required prerequisites, and verify it from a
separate project directory. Repeat setup to check idempotence.
Report changes, backups, failures and capabilities that remain unverified.
Use the full profile only if I request the optional integrations.
```

Linux or macOS:

```bash
git clone https://github.com/badmuriss/my-llm-kit
cd my-llm-kit
./setup.sh --dry-run
./setup.sh
```

Native Windows PowerShell:

```powershell
git clone https://github.com/badmuriss/my-llm-kit
Set-Location my-llm-kit
.\setup.ps1 -DryRun
.\setup.ps1
```

The core needs Git, Python and the Agent Graph `jsonschema` dependency. Setup
checks the dependency before installing it into Python's user package directory.
Unix setup uses the existing user-install policy for managed Python environments;
activate your preferred Python environment first if you manage these dependencies
separately. Runtime requirements live in
[`skills/agent-graph/requirements.txt`](skills/agent-graph/requirements.txt).

To include the optional collection, preview and run `./setup.sh --full` or
`.\setup.ps1 -Full`, adding `--dry-run` or `-DryRun` for the preview. Full setup
also needs the Node/npm and Python package tools used by its integrations.

For a Claude-only core copy, run `./install.sh`. Use `./install.sh --link` to link
to this clone instead. It includes the graph runtime and verifies that the CLI
loads. It no longer installs unrelated external skill repositories.

## How the harness works

The harness keeps scope, acceptance and remaining work visible. It uses the least
process that can verify the task:

| Mode | Use | Durable artifacts |
|---|---|---|
| `direct` | A bounded edit and relevant check | None required |
| `verified_single` | One writer investigating and repairing behavior | None required |
| `light_spec` | A material architectural decision | An existing or new decision record |
| `graph` | Independent work needing ownership, integration and recovery | OpenSpec contracts and a run journal |

A request to implement does not require a separate planning phase or intake CLI.
For a simple change, use `$impl` or ask for the change directly. Use `$spec` when
you want planning before implementation. Graph planning uses executable intake
to validate observed signals and packet contracts; it does not infer permission
from substrings in repository prose.

For substantial work, the plan maps requested outcomes to observable evidence.
Missing, blocked or deferred work remains visible. A check proves only what it
measures. Evidence is reused until relevant inputs or acceptance change, then the
affected checks run again. Completion means the current request is satisfied and
owned resources are settled, not that an agent returned a successful exit code.

The acceptance discipline borrows useful ideas from gate-based workflows such as
`unlazy`, without installing another scheduler, ledger or Stop hook. Polishing
continues only while needed to meet the accepted scope.

### Graph execution

The portable core owns task contracts, generations, ownership, checks and cleanup.
The Host adapter can use local execution or native workers. Orca adds supervised
workers, worktrees and visible surfaces when those capabilities are available.

Bootstrap freezes a control runtime and transfers ownership to a coordinator
capsule. The current session can claim that capsule. A new visible session is
used when the task's context or host workflow needs a handoff. Both paths enforce
the same coordinator identity and generation; a missing handoff UI is not itself
a reason to stop an otherwise executable graph.

Task dependencies must pass before dispatch, overlapping writes are serialized,
and reports are independently checked before grading. Request amendments update
the existing contract. Resume reconciles current task and resource state before
retrying. See [graph execution](skills/impl/references/graph-execution.md) and the
[task contract](skills/agent-graph/references/task-graph.md) for the protocol.

Invoke an installed runtime by its resolved location, with the consumer project
passed separately:

```text
python3 "<installed-agent-graph>/scripts/agent_graph.py" intake --repo "<project>" --request "<change>" --check "<relevant-command>" --signals-json "<observed-signals-json>" --json
```

Use `py -3` on Windows. Do not copy the harness into a consumer project merely to
make a relative command work. Use the returned pinned entrypoint after bootstrap.

## What's included

| Core skill | Purpose |
|---|---|
| `spec` | Plan scope and sufficient acceptance evidence |
| `impl` | Implement, verify and report concrete blockers |
| `agent-graph` | Durable ownership, integration and recovery; optional [Jev worker advice](skills/agent-graph/references/jev-integration.md) through OpenRouter |
| `writing` | Clear technical documentation, commits and PRs |
| `frontend-visual-validation` | Inspect rendered changes with reproducible PNG evidence |

Rendered changes require vision review of affected states on supported platforms.
Visual evidence remains useful outside graph mode; graph submission is required
only when a graph run exists. A missing platform or unavailable vision is reported
as unobserved. See the [visual skill](skills/frontend-visual-validation/SKILL.md).

| Optional vendored skill (`--full`) | Use |
|---|---|
| `research` | Source-based lookups and research reports |
| `computer-use` | Jev via OpenRouter for bounded browser tasks; Orca for desktop and general UI |
| `scrapingdog` | Dedicated public-web data collection |
| `ingest` | Extract documents that cannot be read reliably as text |
| `grill-me` | Explicit adversarial planning interview |
| `grill-with-docs` | Interview against documented domain decisions |
| `thermo-nuclear-code-quality-review` | Requested or consequential independent review |
| `rule-curator` | Audit or prune a standing instruction corpus |
| `trim-code-comments` | Remove redundant comments when requested |
| `readme-pass` | Improve README structure and presentation |
| `remove-ai-marks` | Requested metadata or invisible-mark cleanup |

Full setup also installs the repositories and plugins declared in
[`install-manifest.json`](install-manifest.json): `unslop`,
`incredibly-pretty-websites`, `site-audit`, `spec-council`, `refero-design`,
`drawio-skill` and `revenue-centric-design`, plus the declared Cloudflare and
last30days plugins. Firecrawl provides its own core skills. These are optional
capabilities; installation does not make them prerequisites for ordinary work.

## Supported agents

Skills share `~/.agents/skills`, which OMP reads natively. Setup creates per-skill
links for detected Claude and Codex hosts where needed. Full setup also distributes
existing shared skills; core setup only links its selected skills. An already
unified skill directory may expose additional user-installed skills. Nothing
prunes those automatically.

Shared instructions come from [`instructions/AGENTS.md`](instructions/AGENTS.md).
The repository's root [`AGENTS.md`](AGENTS.md) contains development constraints,
so the same global policy is not repeated as project instructions.

| Capability | Installed/configured by this repository | Verification boundary |
|---|---|---|
| Shared skills | Shared directory read by OMP; Claude and Codex aliases | Check discovery in the actual host |
| Global instructions | Shared file read by OMP; Claude/Codex aliases and an OMP alias when its directory exists on Unix | Native OMP discovery does not require the alias |
| MCP (`--full`) | Claude, Codex and OpenCode | OMP MCP configuration is currently local, not provisioned by setup |
| Graph workers | Host and Orca adapters | Optional capabilities need runtime receipts |
| UI evidence | Browser capture and vision-capable host | Not replaced by unit tests or a build |
| Resource guard | Optional Linux enhancement | Not required on other systems |

The presence of files does not certify all host versions. Gemini, Copilot and
OpenCode can be skill consumers, but global-instruction discovery and execution
must be verified in those hosts. Native Windows, macOS and Linux installers have
different filesystem behavior; report platform checks actually performed.

OMP is the primary local harness, using ChatGPT/Codex subscription models.
Its effective roles, models, agents, hooks and MCP configuration live under
`~/.omp/agent/`. Setup does not install the OMP executable or reproduce those
machine-local settings. Do not copy credential-bearing MCP files into the repository.
See the [migration record](research/2026-09-22-omp-gpt6-routing.md) and
[repository/harness audit](research/2026-09-22-omp-harness-audit.md) for verified
behavior and remaining gaps.

## Setup details

Default setup installs the core skills, runtime dependency, shared instructions
and visual-artifact ignore entry. Unix uses links; Windows uses managed files and
junctions where available. Different existing instruction files are backed up.
A skipped user-owned directory is reported and must not be treated as an update.

Full setup additionally installs and preflights public-web and document tooling,
registers supported MCP servers, installs the declared plugins, and configures
the safety tools below. It never copies API credentials into host configuration.

### Safety tools

`dcg` checks destructive commands at supported host hooks. Full setup installs the
calibrated configuration in `dcg/`; Windows uses its PowerShell-aware profile.
Verify behavior in the actual agent host with `dcg doctor` and a throwaway target.
A hook file's presence is not proof that the host invokes it.

Pipelock is installed from the pinned release and verified checksum. It wraps
configured Codex MCP servers and adds supported Claude hooks. This is application
boundary coverage, not interception of every child process or network connection.
Rerun full setup after adding an MCP server that needs wrapping.

`agent-resource-guard` is optional even in full setup. On Linux, request it with
`./setup.sh --with-resource-guard` for machine-wide admission and stale-workload
cleanup. Other systems use host process controls. Missing optional tooling never
blocks unrelated work.

Heavy converters remain opt-in. `rule-curator` has no monitoring daemon or hook;
its browser curation workflow is optional, not required to deliver an audit.

## Development checks

Install development dependencies with `python3 -m pip install -r requirements-dev.txt`
or Windows `py -3 -m pip install -r requirements-dev.txt`. Use the relevant existing
unittest module for a change. For Python changes, run the configured complexity gate:

```bash
ruff check .
```

Installer tests use temporary user and project directories. They exercise repeat
core installation and the installed runtime from a separate consumer directory.
Do not run full machine setup as a test. Native platform and host behavior remains
unverified until exercised on that platform and host.

## Credits

- `research` and `ingest` are adapted from [research-stack](https://github.com/nett0eth/research-stack) by Netto, under MIT.
- `last30days` comes from [mvanhorn/last30days-skill](https://github.com/mvanhorn/last30days-skill), under MIT.
- `unslop` is original work under CC BY-SA.
- `thermo-nuclear-code-quality-review` is adapted from [Cursor Team Kit](https://github.com/cursor/plugins/tree/main/cursor-team-kit/skills/thermo-nuclear-code-quality-review), under MIT.
- `revenue-centric-design` comes from [heliocosta-dev/revenue-centric-design](https://github.com/heliocosta-dev/revenue-centric-design), distilled from [@richardrx](https://x.com/richardrx) with permission, under a source-available license that forbids gambling, betting, and casino use.
- The cross-agent skill layout follows [vercel-labs/skills](https://github.com/vercel-labs/skills).

Community projects keep their own licenses.

## License

MIT. See [LICENSE](LICENSE).
