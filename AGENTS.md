# my-llm-kit development

This repository distributes agent instructions, skills and optional integrations.
The shared policy lives in `instructions/AGENTS.md`; the README installation
prompt installs that file as the global policy. This file contains only
repository-specific constraints.

- Preserve unrelated worktree changes. Verify distribution using temporary user
  and consumer directories; do not change the real machine installation as a test.
- Keep installation instructions in README.md and the default install small.
  Optional integrations require a user selection; already installed user skills
  and guards remain untouched. Do not add machine setup scripts or a second
  installation catalog.
- Resolve installed scripts from their skill directory and pass the consumer
  project separately. Do not assume a consumer has `skills/` in its checkout.
- Keep journal generation, task ownership, check provenance and resource cleanup
  intact when changing graph execution. Scope changes amend the existing task
  contract; do not add another ledger or scheduler.
- Do not add GitHub Actions,
  test suites, test fixtures or development test/lint dependencies. Verify changes
  by inspecting the affected files, links and necessary runtime behavior. Shared
  instructions about tests govern consumer projects, not this collection.
- Keep installation outcomes independent of the shell and harness. Report
  untested operating systems or hosts as unverified, not supported by inference.
- Skill edits use `skill-creator`; preserve licenses, reference links and implicit
  invocation policy. Keep domain-specific detail out of shared instructions.
- Commits use conventional format without agent names or co-author trailers.
