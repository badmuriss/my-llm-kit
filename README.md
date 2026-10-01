<p align="center"><img src="docs/banner.png" width="720" alt="my-llm-kit wordmark in white with mint-green hyphens on a near-black background, with the tagline: a personal, versioned coding-agent setup"></p>

<p align="center"><b>Shared instructions and skills for the coding agent you choose.</b></p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="MIT license"></a>
  <a href="https://github.com/badmuriss/my-llm-kit/stargazers"><img src="https://img.shields.io/github/stars/badmuriss/my-llm-kit?style=flat-square" alt="GitHub stars"></a>
  <a href="https://github.com/badmuriss/my-llm-kit/commits/main"><img src="https://img.shields.io/github/last-commit/badmuriss/my-llm-kit?style=flat-square" alt="last commit"></a>
</p>

<p align="center">
  <a href="#install">Install</a> ·
  <a href="#how-it-works">How it works</a> ·
  <a href="#whats-included">What's included</a> ·
  <a href="#harness-integration">Harness integration</a> ·
  <a href="#optional-integrations">Optional integrations</a>
</p>

## Install

Paste this prompt into your coding agent. The agent reads this README and adapts
the installation to your operating system and active harness.

```text
Install my-llm-kit from https://github.com/badmuriss/my-llm-kit.
Read README.md and AGENTS.md, then follow the installation instructions below.
Install the shared policy and the research and frontend-visual-validation skills.
Detect my operating system and active harness, using its native discovery mechanism.
Preserve my existing skills, instructions, credentials and harness configuration.
Verify discovery in the active harness and exercise the configured research MCP
with a separate project scope. Report changes, backups and anything unverified.
Install optional skills or integrations only when I select them.
```

For an update, change the first sentence to "Update my existing my-llm-kit
installation." Add the names of any optional capabilities you want. The
[catalog](#whats-included) lists them; installing the core keeps your other skills
and integrations in place.

### Installation instructions for the agent

1. Inspect the operating system, active harness and existing installation. Reuse
   an existing checkout while preserving its local changes, or obtain the
   repository in a stable user directory. Read the active harness's native
   configuration and supported discovery mechanism before choosing aliases or
   registration commands. Install only the core and user-selected options.
2. Install the complete `skills/research/` and
   `skills/frontend-visual-validation/` packages under
   `~/.agents/skills/<name>/`. Link to a stable checkout when the filesystem
   supports it; otherwise copy the package, including its references, scripts
   and licenses. Keep user-owned skill directories in place and report conflicts.
   An existing link to this checkout can be updated; a copy needs comparison
   before replacement. Repeating installation should leave matching files alone.
3. Install [`instructions/AGENTS.md`](instructions/AGENTS.md) as the shared policy
   at `~/.agents/AGENTS.md`. The repository's root [`AGENTS.md`](AGENTS.md) contains
   development rules for this repository. Back up conflicting instructions before
   merging, retaining the user's own rules and accompanying licenses. Configure
   discovery for the active harness and any other explicitly requested hosts.
   Prefer native shared-directory
   discovery; add per-skill links or instruction aliases where that host requires
   them. Instruction aliases use `AGENTS.md`. Verify the installed files are
   actually loaded by the active harness.
4. Resolve dependencies for the selected capabilities using the user's existing
   environment and package tools. Core research calls the configured MCP directly;
   it requires no Python collector or Node preflight. Optional local validators
   and other selected integrations retain their own runtime requirements. API
   keys stay in private environment variables or native credential storage.
   Roles, model selection, effort, hooks and MCP servers stay in the active
   harness's native configuration. The kit does not pin model identities. Preserve
   existing guards and provider choices. Add `.visual-evidence/` to the user's
   existing global Git excludes file if needed, preserving its entries and path.
5. Verify from a separate temporary consumer project using the resolved installed
   paths. Check package references and instruction discovery, then exercise the
   direct MCP check below. Inspect the installation a second time to confirm that
   it needs no duplicate links or destructive replacement. Report installed,
   preserved and conflicting paths, backups, checks and unavailable capabilities.
   A file on disk proves placement; host discovery and runtime checks need their
   own observed evidence.

Use filesystem operations appropriate to the platform. A host that needs a native
registration mechanism can use it while the shared policy and skill packages keep
the same contents. Consult that host's current help or documentation instead of
assuming every agent reads the same global paths. Preserve unique `CLAUDE.md`
instructions; retire redundant copies only after confirming their replacement
is loaded. Switching harness should require discovery changes, with domain
knowledge staying in the shared files.

### Verify the core

Check that the installed [research skill](skills/research/SKILL.md) is discovered
and its references resolve from a consumer project. For a selected Scrapinho
integration, call its native `scraper_capabilities` tool and check the requested
operation. This verifies the configured MCP connection without acquiring a source
or requiring a separate API-key environment check.

When live acquisition is authorized, use the exposed `scraper_submit` schema for
one bounded public-page request with a project-specific scope, stable request key
and one attempt. Follow `scraper_get` to terminal status and `scraper_read_source`
through `next_cursor=null`. For discovery, use `search.web` with explicit
DuckDuckGo and `scraper_read_search` for ranked results. Save observed evidence
with the host's file-writing tools as described in
[the report protocol](skills/research/references/reporting.md).

No collector dry-run or scripted MCP preflight is required. If the MCP is absent,
unauthenticated or lacks the requested capability, report that limitation rather
than creating a Python/REST replacement.

Local Linux check, 2026-09-30: the installed skill and shared policy resolve to the
canonical files. Direct MCP `fetch.page` and DuckDuckGo `search.web` each succeeded
with one attempt; both sources were read through EOF, and structured search
results retained their original positions. See the
[direct-MCP smoke evidence](research/evidence/research-mcp-direct-20260930.json).
Raw export and browser page acquisition were not exercised.

Additional Linux smoke checks, 2026-09-30: temporary user and consumer directories
preserved package licenses and resolved the neutral routing seed against a
supplied host catalog, including explicit unavailable-model and unjustified
escalation blocks. The installed graph CLI and deterministic text cleanup ran
from the separate consumer; prompt-only rewriting required no inference. The
installed X parser also preserved title, rich text and divider position from a
temporary consumer without opening an editor or clipboard. Real curl requests
through a loopback proxy stopped on 403/407/429, retained the 408/5xx fallback
signal and delivered a 200 response body. No paid inference, live publication,
account authentication or Cloudflare deployment was exercised.

Native Windows and macOS installation and host discovery remain unverified here.
An installing agent must report the platform and host it actually checked.

## How it works

The shared policy keeps scope, acceptance and remaining work visible. It uses the least
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
checks and cleanup. Select it as an optional skill when durable coordination
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

Use `py -3` on Windows. Do not copy the kit into a consumer project merely to
make a relative command work. Use the returned pinned entrypoint after bootstrap.

The routing seed contains role requirements, not a model catalog. Resolve concrete
models and effort from the active harness's native configuration and authenticated
catalog. Preserve the selected runtime snapshot and provenance when dispatching.

## What's included

| Core skill | Purpose |
|---|---|
| `research` | Direct MCP source acquisition, evidence comparison and research reports |
| `frontend-visual-validation` | Inspect rendered changes with reproducible PNG evidence |

Rendered changes require vision review of affected states on supported platforms.
Visual evidence remains useful outside graph mode; graph submission is required
only when a graph run exists. A missing platform or unavailable vision is reported
as unobserved. See the [visual skill](skills/frontend-visual-validation/SKILL.md).

| Optional skill | Use |
|---|---|
| `agent-graph` | Durable ownership, integration and recovery; [Jev advice](skills/agent-graph/references/jev-integration.md) requires explicit authorization for paid inference |
| `computer-use` | Available browser or desktop backend; Jev remains conditional on authorization for paid inference |
| `stagehand-browser` | Local Stagehand 4 scripts and real-browser smoke checks without a second model API; optional OMP extension |
| `scrapingdog` | Dedicated public-web data collection |
| `rule-curator` | Audit or prune a standing instruction corpus |
| `remove-ai-marks` | Requested metadata or invisible-mark cleanup |

The following repositories extend the optional collection. Read their own
instructions and licenses before installing the selected packages.

| Optional package | Source and package location |
|---|---|
| `unslop` | [badmuriss/unslop](https://github.com/badmuriss/unslop), repository root |
| `incredibly-pretty-websites` | [badmuriss/incredibly-pretty-websites](https://github.com/badmuriss/incredibly-pretty-websites), repository root |
| `site-audit` | [badmuriss/site-audit](https://github.com/badmuriss/site-audit), repository root |
| `spec-council` | [badmuriss/spec-council](https://github.com/badmuriss/spec-council), repository root |
| `proxy-manager` | [webshare-proxy/skills](https://github.com/webshare-proxy/skills/tree/main/skills/proxy-manager), `skills/proxy-manager/` |
| `drawio-skill` | [Agents365-ai/drawio-skill](https://github.com/Agents365-ai/drawio-skill/tree/main/skills/drawio-skill), `skills/drawio-skill/` |
| `revenue-centric-design` | [heliocosta-dev/revenue-centric-design](https://github.com/heliocosta-dev/revenue-centric-design), repository root |

Cloudflare and last30days integrations are available from
[cloudflare/skills](https://github.com/cloudflare/skills) and
[mvanhorn/last30days-skill](https://github.com/mvanhorn/last30days-skill).
Use portable skill packages or the selected host's supported plugin mechanism.
For scientific literature, the optional Firecrawl Research Index retains its
specialized provider route. Generic web discovery and acquisition use configured
Scrapinho.

The [September 2026 audit](research/2026-09-30-skills-audit.md) records the retired
skills and the consolidation owners. Installation preserves existing user skills;
the one-time cleanup archives retired packages outside the active skill root.

Webshare uses its official
[`proxy-manager` skill](https://github.com/webshare-proxy/skills/tree/main/skills/proxy-manager),
not an MCP server. The skill requires the
[`webshare` CLI](https://github.com/webshare-proxy/webshare-cli#install) and
`WEBSHARE_API_KEY`. Resolve the CLI separately when selecting this integration,
keeping credentials private.
Use the proxy per collection or browser session, not as a global OMP/OAuth proxy.
Refero and Stock Images MCPs are not provisioned by this kit.

### Webshare public collection

When selecting Webshare collection, use the repository's
[`scripts/webshare_fetch.py`](scripts/webshare_fetch.py) directly or expose it as
`webshare-fetch` in the user's existing executable directory. Preserve an existing
user-owned command and adapt a launcher to the operating system if needed. The
helper requires Python 3, `curl`, the official `webshare` CLI v0.2.0, and the
`WEBSHARE_API_KEY` environment variable.

Keep private plan IDs outside the repository and pass their file through `--config`:

```json
{
  "datacenter_plan_id": 123,
  "residential_plan_id": 456
}
```

Both values must be positive integers. Run a public HTTPS/HTTP collection with:

```bash
python3 "<kit-checkout>/scripts/webshare_fetch.py" https://example.com --config "<private-config>" --timeout 30
```

The helper obtains one rotating datacenter proxy and performs one request. It
uses the single residential fallback only for connection/timeout failures,
HTTP 408 or 5xx responses. A refusal (403, 407 or 429) stops collection; changing
proxies must not bypass it. It never retries, falls back for 400/401/404 or local
configuration errors, uses cookies or a global proxy, or prints proxy credentials.
Successful response bodies go to stdout; safe plan/status and fallback information
goes to stderr.
The helper's existing default remains `~/.omp/agent/webshare.json` for the local
installation that already uses it. An explicit `--config` works in any harness.

### Stagehand browser automation

When selecting `stagehand-browser`, install its complete skill package and run
the following command with the installed skill's `tools/` directory as the
working directory:

```bash
npm ci --ignore-scripts --no-audit --no-fund
```

The [package](skills/stagehand-browser/tools/package.json) and
[lockfile](skills/stagehand-browser/tools/package-lock.json) pin Stagehand 4.1.0.
Its local scripts need Node >=22.18,
npm and an existing Chrome installation. Import `openSession` from
`<installed-skill>/tools/session.mjs` in a local script and close the session in
`finally`. OMP users can also select the optional `stagehand` tool. Follow the
[skill's extension instructions](skills/stagehand-browser/SKILL.md#installation-and-ownership)
and verify discovery after reloading extensions. The tool provides
`run`, `snapshot`, `screenshot` and `close`, retaining one isolated tab across
calls. The OMP model chooses actions; deterministic Stagehand APIs perform them.
No Browserbase account or extra inference API key is needed. An explicitly authorized
dedicated profile can preserve login state. Borrowed-browser CDP attachment is disabled:
the pinned SDK closes the host browser on `browser.close()`, and the reconnection probe
timed out. The kit must not terminate a user's browser to claim successful cleanup.
Use only browser capabilities available and authorized in the active environment.
A Stagehand-owned isolated Chrome can be shared with Browser Harness when that
integration is already available; it does not authorize a separate inference service.
For video, use plain Playwright. Refero, HyperFrames, Remotion and creative-generation
skills are not part of the user's selected workflow.

Verify the requested browser actions through observed DOM state or durable results.
Capture and inspect PNG evidence for rendered changes using
`frontend-visual-validation`. The existing Linux observations are recorded in the
[migration evidence](research/2026-09-23-stagehand-migration.md); native Windows
and macOS browser execution remain unverified.

Stagehand is **not** Playwright Test and supports neither Firefox nor WebKit.
Existing application suites keep their runner, fixtures, assertions and engine
coverage where no equivalent exists. OMP's built-in Puppeteer browser, Orca,
agent-browser, Jev and Mermaid internals are external boundaries, not migrated
by renaming a package. AI `act`/`observe`/`extract` are not enabled by this
subscription-only integration. See the [skill](skills/stagehand-browser/SKILL.md)
and [migration evidence](research/2026-09-23-stagehand-migration.md).

## Harness integration

Shared instructions and skill packages stay under `~/.agents/`. OMP is the current
local preference and can be replaced without rewriting them. The installing agent
adapts discovery to its active host; each optional capability needs its own check.

| Capability | Installation outcome | Verification boundary |
|---|---|---|
| Shared skills | Complete selected packages under `~/.agents/skills/` | Discovery in the active harness |
| Global instructions | Shared `~/.agents/AGENTS.md` with required native registration or aliases | Instructions actually loaded in that host/version |
| MCP and plugins | User-selected integrations in native host configuration | Tool discovery, authentication and bounded preflight |
| Graph workers | Optional Host or Orca adapter | Runtime capability receipts |
| UI evidence | Available browser capture and vision | Rendered states on the observed platforms |
| Stagehand | Portable local SDK/scripts, with an OMP extension if selected | Real Chrome and actual tool discovery |
| Resource guard | Optional Linux enhancement | Admission and cleanup in the actual environment |

The current local installation uses subscription-backed inference.
Its effective roles, models, agents, hooks and MCP configuration live under
`~/.omp/agent/`. Keep these machine-local choices in the active harness's native
configuration. Credentials stay outside this repository. A different harness
resolves the same requirements using its own available capabilities; no OMP model
catalog or configuration is copied into shared skills.

## Optional integrations

Selecting the optional collection includes the vendored skills and external skill
packages listed above. Enable MCP servers, plugins, browser tools and guards only
when requested and compatible with the active harness. Read each selected skill's
requirements and the integration's current upstream instructions; use native host
configuration and preserve existing entries. Missing credentials leave that
capability unavailable. Use the configured subscription-backed inference;
additional paid inference requires explicit authorization.

For an existing local ScrapingDog MCP server, the optional
[`preflight_scrapingdog_mcp.mjs`](scripts/preflight_scrapingdog_mcp.mjs) accepts
its absolute server entrypoint. Keep specialist provider checks tied to their
configured route.

When selecting `agent-graph`, keep the complete checkout so its installed link
resolves to the sibling `skills/spec/` and `skills/impl/` resources. For a copied
installation, copy all three directories into the same parent, including scripts,
references and routing-policy resources. Only `agent-graph` has a skill entrypoint.
Install [`requirements.txt`](skills/agent-graph/requirements.txt) into the selected
Python environment and exercise the installed CLI with `--help` from a separate
consumer directory. PDF/HTML rendering has its own optional dependencies and checks.

`dcg`, Pipelock and [`agent-resource-guard`](scripts/agent_resource_guard.py) remain
optional. Reuse existing installations; if selected, follow their upstream
installation and native hook/configuration instructions. The calibrated `dcg/`
profiles remain available, including the Windows profile. Verify guards in the
actual host with throwaway targets. A hook file's presence is not proof that the
host invokes it. Resource guard is a Linux enhancement; other systems use host
process controls.

Heavy converters remain opt-in. `rule-curator` has no monitoring daemon or hook;
its browser curation workflow is optional, not required to deliver an audit.

Historical research and task records retain evidence from the former scripted
installation and automated checks. This collection is maintained through its
instructions, skill packages and runtime helpers.

## Credits

- `research` is adapted from [research-stack](https://github.com/nett0eth/research-stack) by Netto, under [MIT](skills/research/LICENSE); the retired `ingest` source remains in the cleanup archive.
- `remove-ai-marks` is adapted from [watermarks-remover](https://github.com/guillaumemeyer/watermarks-remover), with its [MIT notice preserved](skills/remove-ai-marks/LICENSE).
- `last30days` comes from [mvanhorn/last30days-skill](https://github.com/mvanhorn/last30days-skill), under MIT.
- `unslop` is original work under CC BY-SA.
- Maintainability guidance consolidated from `thermo-nuclear-code-quality-review` comes from [Cursor Team Kit](https://github.com/cursor/plugins/tree/main/cursor-team-kit/skills/thermo-nuclear-code-quality-review), with its [MIT license preserved](instructions/LICENSE.cursor-team-kit).
- `revenue-centric-design` comes from [heliocosta-dev/revenue-centric-design](https://github.com/heliocosta-dev/revenue-centric-design), distilled from [@richardrx](https://x.com/richardrx) with permission, under a source-available license that forbids gambling, betting, and casino use.
- The cross-agent skill layout follows [vercel-labs/skills](https://github.com/vercel-labs/skills).

Community projects keep their own licenses.

## License

MIT. See [LICENSE](LICENSE).
