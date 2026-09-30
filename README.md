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

The core needs Git and Python. The optional graph runtime also needs `jsonschema`;
full setup checks it before installing missing requirements into Python's user
package directory. Unix full setup uses the existing user-install policy for
managed Python environments; activate your preferred Python environment first
if you manage these dependencies separately. Graph requirements live in
[`skills/agent-graph/requirements.txt`](skills/agent-graph/requirements.txt).

To include the optional collection, preview and run `./setup.sh --full` or
`.\setup.ps1 -Full`, adding `--dry-run` or `-DryRun` for the preview. Full setup
also needs the Node/npm and Python package tools used by its integrations.

For a Claude-only core copy with the legacy Claude agent templates, run
`./install.sh`. Use `./install.sh --link` to link to this clone instead.

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
Ask for the change or planning directly; shared `AGENTS.md` carries the common
workflow. Optional graph planning uses executable intake
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

The optional `agent-graph` package owns task contracts, generations, ownership,
checks and cleanup. Install it with the full profile when durable coordination
is useful. Its support resources remain in `skills/spec` and `skills/impl`,
without standalone skill entrypoints, to preserve runtime and learning paths.
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
| `research` | Source-based lookups, acquisition helpers and research reports |
| `frontend-visual-validation` | Inspect rendered changes with reproducible PNG evidence |

Rendered changes require vision review of affected states on supported platforms.
Visual evidence remains useful outside graph mode; graph submission is required
only when a graph run exists. A missing platform or unavailable vision is reported
as unobserved. See the [visual skill](skills/frontend-visual-validation/SKILL.md).

| Optional vendored skill (`--full`) | Use |
|---|---|
| `agent-graph` | Durable ownership, integration and recovery; [Jev advice](skills/agent-graph/references/jev-integration.md) requires explicit authorization for paid inference |
| `computer-use` | Available browser or desktop backend; Jev remains conditional on authorization for paid inference |
| `stagehand-browser` | Local Stagehand 4 scripts and real-browser smoke checks without a second model API; optional OMP extension |
| `scrapingdog` | Dedicated public-web data collection |
| `rule-curator` | Audit or prune a standing instruction corpus |
| `remove-ai-marks` | Requested metadata or invisible-mark cleanup |

Full setup also installs the repositories and plugins declared in
[`install-manifest.json`](install-manifest.json): `unslop`,
`incredibly-pretty-websites`, `site-audit`, `spec-council`, `proxy-manager`,
`drawio-skill` and `revenue-centric-design`, plus the declared Cloudflare and
last30days plugins. Firecrawl setup adds only its specialized Research Index
skill; generic web discovery and acquisition use configured Scrapinho. These are optional
capabilities; installation does not make them prerequisites for ordinary work.

The [September 2026 audit](research/2026-09-30-skills-audit.md) records the retired
skills and the consolidation owners. Existing user skills are preserved by setup;
the one-time cleanup archives retired packages outside the active skill root.

Webshare uses its official
[`proxy-manager` skill](https://github.com/webshare-proxy/skills/tree/main/skills/proxy-manager),
not an MCP server. The skill requires the
[`webshare` CLI](https://github.com/webshare-proxy/webshare-cli#install) and
`WEBSHARE_API_KEY`; setup installs the skill, not the CLI or account credentials.
Use the proxy per collection or browser session, not as a global OMP/OAuth proxy.
Refero and Stock Images MCPs are not provisioned by this kit.

### Webshare public collection

Full setup installs the repository helper as `~/.local/bin/webshare-fetch` on
Unix and as `~\.local\bin\webshare-fetch.cmd` on Windows, without requiring
administrator privileges. It does not install or update the external CLI, copy
credentials, or overwrite an existing executable that is not managed by this
kit. The helper requires Python 3, `curl`, the official `webshare` CLI v0.2.0,
and the `WEBSHARE_API_KEY` environment variable.

Configure the private plan IDs at `~/.omp/agent/webshare.json` (never commit
this file):

```json
{
  "datacenter_plan_id": 123,
  "residential_plan_id": 456
}
```

Both values must be positive integers. Run a public HTTPS/HTTP collection with:

```bash
webshare-fetch https://example.com
webshare-fetch https://example.com --config ~/.omp/agent/webshare.json --timeout 30
```

The helper obtains one rotating datacenter proxy and performs one request. It
uses the single residential fallback only for connection/timeout failures or
HTTP 403, 407, 408, 429, or 5xx responses. It never retries, falls back for
400/401/404 or local configuration errors, uses cookies or a global proxy, or
prints proxy credentials. Successful response bodies go to stdout; safe
plan/status and fallback information goes to stderr.

### Stagehand browser automation

Full setup installs Stagehand 4.1.0 under the installed `stagehand-browser` skill.
Its local scripts work independently of the coding agent. When `~/.omp/agent/`
already exists, setup also links `extensions/stagehand-browser.mjs` there.
It needs Node >=22.18, npm and an existing Chrome installation; it does not upgrade OMP, download a
browser, register an MCP or change model/authentication settings.

To install only this optional integration:

```bash
node skills/stagehand-browser/tools/install.mjs --dry-run
node skills/stagehand-browser/tools/install.mjs
```

In any harness, import `openSession` from `<installed-skill>/tools/session.mjs`
in a local script and close the session in `finally`. In OMP, reload extensions
or start a new session to use the optional `stagehand` tool. It provides
`run`, `snapshot`, `screenshot` and `close`, retaining one isolated tab across
calls. The OMP model chooses actions; deterministic Stagehand APIs perform them.
No Browserbase account or extra inference API key is needed. An explicitly authorized
dedicated profile can preserve login state. Borrowed-browser CDP attachment is disabled:
the pinned SDK closes the host browser on `browser.close()`, and the reconnection probe
timed out. The kit must not terminate a user's browser to claim successful cleanup.
Jev remains preferred for its supported, authorized goals; a Stagehand-owned isolated
Chrome can be shared with Browser Harness for Jev actions and deterministic verification.

Run `node <installed-skill>/tools/smoke.mjs <project>/.visual-evidence/stagehand-browser`
for navigation, form submission, extraction, negative assertions, PNG capture,
synthetic cookie/localStorage preservation across profile reopens in actual Chrome. Inspect the
PNG as well as `result.json`. Linux is exercised; native Windows and macOS remain
unverified.

Stagehand is **not** Playwright Test and supports neither Firefox nor WebKit.
Existing application suites keep their runner, fixtures, assertions and engine
coverage where no equivalent exists. OMP's built-in Puppeteer browser, Orca,
agent-browser, Jev and Mermaid internals are external boundaries, not migrated
by renaming a package. AI `act`/`observe`/`extract` are not enabled by this
subscription-only integration. See the [skill](skills/stagehand-browser/SKILL.md)
and [migration evidence](research/2026-09-23-stagehand-migration.md).

## Supported agents

Skills and shared instructions are independent of the harness. Skills share
`~/.agents/skills`, which OMP reads natively. Setup creates per-skill
links for detected Claude and Codex hosts where needed. Full setup also distributes
existing shared skills; core setup only links its selected skills. An already
unified skill directory may expose additional user-installed skills. Nothing
prunes those automatically.

Shared instructions come from [`instructions/AGENTS.md`](instructions/AGENTS.md).
The repository's root [`AGENTS.md`](AGENTS.md) contains development constraints,
so the same global policy is not repeated as project instructions. Host aliases
also use `AGENTS.md`. Setup retires a redundant Claude `CLAUDE.md` when it is
empty or matches the managed policy; unique user instructions stay in place
for explicit migration.

| Capability | Installed/configured by this repository | Verification boundary |
|---|---|---|
| Shared skills | Shared directory read by OMP; Claude and Codex aliases | Check discovery in the actual host |
| Global instructions | Shared AGENTS.md with Claude/Codex aliases and an OMP alias when its directory exists | Verify instruction discovery in the actual host/version |
| MCP (`--full`) | Claude, Codex and OpenCode | OMP MCP configuration is currently local, not provisioned by setup |
| Graph workers | Host and Orca adapters | Optional capabilities need runtime receipts |
| UI evidence | Browser capture and vision-capable host | Not replaced by unit tests or a build |
| Stagehand (`--full`) | Portable local SDK/scripts; OMP extension when its configuration directory exists | Real Chrome required; no claim of WebKit/Firefox or upstream Pi-extension compatibility |
| Resource guard | Optional Linux enhancement | Not required on other systems |

The presence of files does not certify all host versions. Gemini, Copilot and
OpenCode can be skill consumers, but global-instruction discovery and execution
must be verified in those hosts. Native Windows, macOS and Linux installers have
different filesystem behavior; report platform checks actually performed.

OMP is the current local preference and can be replaced without rewriting shared
skills or project rules. The current installation uses ChatGPT/Codex subscription models.
Its effective roles, models, agents, hooks and MCP configuration live under
`~/.omp/agent/`. Setup does not install the OMP executable or reproduce those
machine-local settings. Do not copy credential-bearing MCP files into the repository.
See the [migration record](research/2026-09-22-omp-gpt6-routing.md) and
[repository/harness audit](research/2026-09-22-omp-harness-audit.md) for verified
behavior and remaining gaps.

## Setup details

Default setup installs the two core skills, shared instructions
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
core installation and the installed research helper from a separate consumer directory.
Do not run full machine setup as a test. Native platform and host behavior remains
unverified until exercised on that platform and host.

## Credits

- `research` is adapted from [research-stack](https://github.com/nett0eth/research-stack) by Netto, under MIT; the retired `ingest` source remains in the cleanup archive.
- `last30days` comes from [mvanhorn/last30days-skill](https://github.com/mvanhorn/last30days-skill), under MIT.
- `unslop` is original work under CC BY-SA.
- Maintainability guidance consolidated from `thermo-nuclear-code-quality-review` comes from [Cursor Team Kit](https://github.com/cursor/plugins/tree/main/cursor-team-kit/skills/thermo-nuclear-code-quality-review), with its [MIT license preserved](instructions/LICENSE.cursor-team-kit).
- `revenue-centric-design` comes from [heliocosta-dev/revenue-centric-design](https://github.com/heliocosta-dev/revenue-centric-design), distilled from [@richardrx](https://x.com/richardrx) with permission, under a source-available license that forbids gambling, betting, and casino use.
- The cross-agent skill layout follows [vercel-labs/skills](https://github.com/vercel-labs/skills).

Community projects keep their own licenses.

## License

MIT. See [LICENSE](LICENSE).
