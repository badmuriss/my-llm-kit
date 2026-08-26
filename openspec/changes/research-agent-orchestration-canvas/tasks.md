# Tasks

- [x] RAC-01 Discover primary sources for Maestri, Orca visual surfaces, and open-source agent graph canvases.
  Depends: []
  Paths: [research/]
  Mode: read
  Isolation: auto
  Context: Return only source URLs, access date 2026-08-20, whether each source is official or primary, and verification status. Cover the Maestri canvas intended for agent orchestration, official Orca docs or source, and open-source projects with a node canvas or live execution graph. Do not synthesize recommendations. Do not edit files.
  Acceptance: The result includes at least one verified primary source for Maestri or records why the identity is ambiguous, one official Orca source, and primary repositories or docs for viable open-source precedents. Search snippets are leads only.
  Check: python3 -c "import json,pathlib; p=pathlib.Path('openspec/runs/research-agent-orchestration-canvas/canvas-research-20260820/results/collect-sources.json'); d=json.loads(p.read_text()); assert d['outcome']=='reported' and 'https://' in d['summary']"

- [ ] RAC-02 Collect primary source locations for Open-Maestri behavior and Orca resource lifecycle.
  Depends: []
  Paths: [research/]
  Mode: read
  Isolation: auto
  Context: Return only URLs and access date 2026-08-20. Cover Open-Maestri source files for infinite-canvas movement, notes, edges, terminal or agent creation, persistence and licensing. Cover Orca source, issues, PRs or official discussions for PTY termination, process-tree cleanup, terminal close, worktree removal, memory/resource accounting and CLI lifecycle. Include exact source-file URLs or issue/PR URLs and verification status. Do not synthesize recommendations. Do not edit files.
  Acceptance: The result includes verified primary URLs for Open-Maestri canvas/note/edge behavior and at least one verified Orca lifecycle source file. If no official Orca issue or PR directly supports reported process leaks, state that explicitly instead of inferring one.
  Check: python3 -c "import json,pathlib; p=pathlib.Path('openspec/runs/research-agent-orchestration-canvas/maestro-runtime-20260820/results/collect-runtime-sources.json'); d=json.loads(p.read_text()); assert d['outcome']=='reported' and 'https://' in d['summary']"
