# my-llm-kit development

This repository distributes agent instructions, skills and optional integrations.
The shared policy lives in `instructions/AGENTS.md`; setup installs that file as
the global policy. This file contains only repository-specific constraints.

- Preserve unrelated worktree changes. Do not run the real machine installer as
  a test; exercise copies in a temporary user directory or use dry-run.
- Keep the default install small. Optional integrations belong to `--full` /
  `-Full`; already installed user skills and guards remain untouched.
- Resolve installed scripts from their skill directory and pass the consumer
  project separately. Do not assume a consumer has `skills/` in its checkout.
- Keep journal generation, task ownership, check provenance and resource cleanup
  intact when changing graph execution. Scope changes amend the existing task
  contract; do not add another ledger or scheduler.
- Use the relevant existing `unittest` module for runtime or installer changes.
  Run `ruff check .` for Python changes; do not raise the complexity ceiling.
  Development dependencies are in `requirements-dev.txt`.
- Keep shell and native PowerShell install behavior aligned. Report untested
  operating systems or hosts as unverified, not supported by inference.
- Skill edits use `skill-creator`; preserve licenses, reference links and implicit
  invocation policy. Keep domain-specific detail out of shared instructions.
- Commits use conventional format without agent names or co-author trailers.
