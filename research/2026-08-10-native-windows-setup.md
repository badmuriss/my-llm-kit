# Native Windows setup research

Access date: 2026-08-10

## Protocol

Question: Can `my-llm-kit` install natively on Windows without WSL while preserving the existing security and skill workflow?

Decision criterion: use native Windows primitives for filesystem links and dependency installation, consume one shared manifest across operating systems, and skip a component only when its implementation is inherently Linux-specific and the skip is explicit.

Falsifier: if a required dependency has no native Windows installation path, the native installer cannot claim end-to-end support.

## Findings

The repository already contains every vendored skill, including `grill-me`. The full `setup.sh` discovers all directories under `skills/`, but the reduced `install.sh` named only `spec` and `impl`. Since `spec` explicitly invokes `grill-me`, the reduced path had a real missing dependency. Source: repository files `skills/spec/SKILL.md`, `skills/grill-me/SKILL.md`, `setup.sh`, and `install.sh`, accessed 2026-08-10.

The destructive-command guard supports native Windows through an official PowerShell installer. Its documented command installs `dcg.exe`, verifies the download, updates the user path in easy mode, and configures detected agent hooks. This removes the need to run its Bash installer through WSL. Source: [dcg README](https://github.com/Dicklesworthstone/destructive_command_guard/blob/main/README.md), [dcg PowerShell installer](https://github.com/Dicklesworthstone/destructive_command_guard/blob/main/install.ps1), accessed 2026-08-10.

The existing resource guard depends on Linux cgroups, `/proc`, and a systemd user timer. Porting that component inside the installer would be a separate resource-control design, not an installation translation. The Windows installer must skip it explicitly instead of reporting a false success. Source: repository files `scripts/agent_resource_guard.py` and `systemd/agent-resource-guard.timer`, accessed 2026-08-10.

## Decision

Add `setup.ps1` for native Windows. Use directory junctions for skill directories, managed copies for instruction files, Python's normal Windows `pip` invocation, the existing host CLIs for MCP and plugins, and the official native dcg installer. Keep repositories, plugins, and reduced workflow dependencies in `install-manifest.json`, consumed by both operating-system installers.

Add `grill-me` to the reduced installer through that manifest. Do not add a second hardcoded list.

## Disagreements and open points

No primary-source disagreement was found for dcg's Windows support. Native Windows resource limiting remains open and is not represented as implemented.

## Sources consulted

- [dcg README](https://github.com/Dicklesworthstone/destructive_command_guard/blob/main/README.md), accessed 2026-08-10.
- [dcg PowerShell installer](https://github.com/Dicklesworthstone/destructive_command_guard/blob/main/install.ps1), accessed 2026-08-10.
- Local `my-llm-kit` repository files named above, accessed 2026-08-10.
