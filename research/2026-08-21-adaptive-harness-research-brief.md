# Research brief: adaptive harness without ceremony

## User concern

The user agrees with much of an essay arguing that “harness engineering,” graph engineering, loop engineering, and spec-driven development are often inflated into universal disciplines. They still see value in specs and orchestration, but fear that `my-llm-kit` can become rigid: a simple task might trigger a large plan, many agents, a frozen graph, and coordination overhead that costs more than it helps.

The goal is not to defend the current harness. Determine, from primary research and real evidence, how it should decide the minimum useful process for each problem and remain malleable as uncertainty is discovered during implementation.

## Material claims from the essay to verify, not assume

- A strong frontier coding model receives little or no quality benefit from changing harnesses, while weaker models may benefit more.
- Harness choice can materially affect cost through native prompt caching and transport behavior.
- Multi-agent reliability compounds across dependent steps, and cohesive coding tasks are often poor candidates for parallel agents.
- Cognition has published an argument against multi-agent coding based on hidden/implicit decisions diverging across workers.
- Anthropic has reported that its multi-agent research architecture consumes roughly fifteen times more tokens, that coding is less parallelizable than research, and that most measured gains came from extra token spend rather than architecture.
- A production-agent study reportedly examined 86 systems across 26 domains and found that 68% run at most 10 steps before human intervention.
- Thoughtworks placed spec-driven development in the “Assess” ring and warned about detailed rules or ceremony that do not scale.
- Gartner reportedly estimated that only about 130 “agentic AI” vendors are substantively agentic and forecast that 40% of agentic projects will be canceled by the end of 2027.
- The essay cites private benchmark results and project counts. Treat these as unverified unless the underlying dataset, protocol, repetitions, variance, raw runs, and repository history are publicly inspectable.
- The simple `0.9^10` example is arithmetic, not empirical proof that a ten-agent system succeeds 35% of the time; assess what real reliability models say about dependent, correlated, retried, and verified steps.

## Exact research question

What evidence-backed adaptive policy should `my-llm-kit` use to choose among direct execution, a verified single-agent loop, a lightweight spec, and multi-agent graph orchestration, so that complexity is proportional to task risk and parallelism rather than imposed by default?

## Required decisions

1. Separate what the essay gets right, overstates, or leaves unsupported.
2. Identify empirical research on single-agent versus multi-agent software engineering, coordination cost, context loss, error propagation, planning under uncertainty, iterative/specification-first development, and human supervision.
3. Prefer official repositories/docs and original papers. Open every source used. Record DOI/arXiv/official URLs and access date.
4. Define a practical complexity/risk classifier using observable inputs, not vague labels. Candidate inputs include task size, architectural uncertainty, reversibility, blast radius, validation strength, number of independently parallel work packets, shared-state coupling, context size, expected duration, credentials, and unattended execution.
5. Propose the smallest-mode ladder, with an explicit no-orchestration default for small/reversible work and escalation only when evidence crosses thresholds.
6. Define de-escalation and emergence: the plan must be revisable during work, discoveries can shrink or reshape the graph, and a worker is never spawned merely because a template has a role for it.
7. Define budgets and stop conditions for agents, tokens, context, wall time, retries, and cleanup. Do not invent universal numeric thresholds unless evidence supports them; mark configurable hypotheses clearly.
8. Explain how specs can be executable and disposable rather than prose treated as eternal source of truth: checks, evidence, short decision records, amendment rules, and code/runtime feedback must outrank stale prose.
9. Compare project memory generated from actual work with up-front specification. Analyze complementarity rather than assuming one replaces the other.
10. Map the proposed policy to concrete future changes in `my-llm-kit`, but do not edit code, skills, OpenSpecs, journal, state, or any frozen graph in this session.

## Process and output contract

- Use the `research` skill exactly, starting with its finding template.
- Risk is `material` because the result can change architecture, cost, and daily workflow.
- Check for `SCRAPINGDOG_API_KEY` without exposing it and follow the required provider order. For papers, use an available paper-search provider first; use primary paper pages or PDFs as evidence.
- Maintain a claim ledger and provider trail. Report disagreements by source and date. Label samples below five independent cases as weak.
- Use one bounded council only if the skill’s trigger is met. Do not create a large research swarm.
- Save the audited final finding only to `research/2026-08-21-adaptive-harness-evidence.md` and supporting converted sources under `research/sources/adaptive-harness/` when needed.
- Run the research finding auditor before completion.
- End the session with a concise Portuguese handoff containing: strongest supported conclusions, rejected/limited claims, recommended adaptive mode ladder, unresolved questions, report path, and sources that still require verification.

## Non-goals

- Do not implement or modify the harness.
- Do not modify either Maestro OpenSpec.
- Do not touch any `openspec/runs/` artifact.
- Do not claim that visible complexity is useful merely because Maestro can visualize it.
- Do not turn the answer into a defense of SDD, graphs, or multi-agent systems.
