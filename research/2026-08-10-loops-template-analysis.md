# Loops template analysis

Access date: 2026-08-10

## Research protocol

Question: Which mechanisms in `loops-template` improve `my-llm-kit` beyond its current post-task learning and process resource guard?

Adoption criterion: recommend a mechanism only when it is generic, enforceable or testable, does not duplicate an existing mechanism, and has a clear failure boundary.

Falsifier: if the template adds only documentation scaffolding, duplicates current behavior, or relies on unsafe parallel execution, recommend no adoption.

## Conclusion

Do not copy `loops-template` into `my-llm-kit`. Extract a small set of mechanisms into the existing `$impl` lifecycle.

The strongest additions are crash-safe run state, structured incident records, verifiable evidence references, and promotion from repeated lessons to proposed mechanical gates. The existing `my-llm-kit` learning compiler is already stricter than the Loops active-rule compiler in important ways, but its independence check needs reinforcement.

The creator's throughput claim is not verifiable from the public repository. Treat it as a private testimonial, not evidence for an architectural decision.

## What changed in Loops

Commit `c10e50c` moved the previous tree unchanged into `loops-maturado` and added `loops-template`. The new template contains documentation and seed state, but no executable automation. Source: [reorganization commit](https://github.com/pedrogazil/loops/commit/c10e50cf6fc7c3c068d8f94fb87f1dd638029f92), accessed 2026-08-10.

The template is not generic enough to run unchanged. It still names a Windows path, Electron, Python, IPC, Tailwind, a specific visual theme, project-specific build commands, and a skill called `impeccable`. It also asks for up to twenty subagents. Source: [template prompt](https://github.com/pedrogazil/loops/blob/c10e50cf6fc7c3c068d8f94fb87f1dd638029f92/loops-template/PROMPT.md), [process rules](https://github.com/pedrogazil/loops/blob/c10e50cf6fc7c3c068d8f94fb87f1dd638029f92/loops-template/prompt/CRAFT_PROCESS.md), and [quality rules](https://github.com/pedrogazil/loops/blob/c10e50cf6fc7c3c068d8f94fb87f1dd638029f92/loops-template/prompt/CRAFT_QUALITY.md), accessed 2026-08-10.

The template references automation and project paths that it does not ship, including the active-rule compiler, integration scripts, round scaffolding, progress index, UI selfchecks, and design file. Its README says an explanation will be added later. Source: [template tree](https://github.com/pedrogazil/loops/tree/c10e50cf6fc7c3c068d8f94fb87f1dd638029f92/loops-template) and [README](https://github.com/pedrogazil/loops/blob/c10e50cf6fc7c3c068d8f94fb87f1dd638029f92/loops-template/README.md), accessed 2026-08-10.

This does not make the template useless. Pedro explicitly described an adaptation step. It does mean that “copy and prompt” has no mechanical completion criterion: an agent can leave stale paths, missing scripts, or contradictory rules and still claim adaptation succeeded.

## Evidence quality

The public GitHub repository exposes no GitHub pull requests and only two repository commits. Sources: [GitHub pulls API](https://api.github.com/repos/pedrogazil/loops/pulls?state=all&per_page=100) and [GitHub commits API](https://api.github.com/repos/pedrogazil/loops/commits?per_page=100), accessed 2026-08-10.

The matured snapshot contains fifty-three local PR report files. Fifty-one say `merged`, one says `open`, and one omits the status field. Eighteen of the reports marked merged contain pending or missing validation. Source: [local PR report tree](https://github.com/pedrogazil/loops/tree/c10e50cf6fc7c3c068d8f94fb87f1dd638029f92/loops-maturado/pull-requests), accessed 2026-08-10.

None of the fifty-one `merged_commit` hashes from those reports exists in the public Loops commit graph. This is consistent with the reports being copied from another repository, but prevents independent verification here. Sources: [local PR report tree](https://github.com/pedrogazil/loops/tree/c10e50cf6fc7c3c068d8f94fb87f1dd638029f92/loops-maturado/pull-requests) and [public commit graph](https://api.github.com/repos/pedrogazil/loops/commits?per_page=100), accessed 2026-08-10.

I inspected a stratified sample of eight reports across early, middle, late, merged, partial, and open states. The sample shows useful intent and validation notes, but also merged records with pending checks and records later corrected because a claimed merge was unreachable. Source: [matured PR reports](https://github.com/pedrogazil/loops/tree/c10e50cf6fc7c3c068d8f94fb87f1dd638029f92/loops-maturado/pull-requests), accessed 2026-08-10.

Therefore the artifacts support a qualitative conclusion: the author exercised and revised the workflow. They do not support the creator's throughput, review, approval, or impact claim as a public fact. Verifying that claim requires the source repository's PR metadata, review events, CI results, and timestamps.

## Comparison with the current `$impl` learning

### Already stronger in `my-llm-kit`

The current compiler validates a closed JSON shape, rejects conflicting meanings under one key, records task grades, retains concrete evidence, writes full rule text into generated active rules, detects generated-file drift, and supports explicit supersession. Source: [local learning compiler](/home/badmuriss/Documents/my-llm-kit/skills/impl/scripts/learning.py), inspected 2026-08-10.

Loops selects an entire round file when its frontmatter is active and proven, forced, or merely high impact. Its generated `ACTIVE_RULES.md` contains file names and metadata, not the actual candidate rules from those files. Source: [active-rule compiler](https://github.com/pedrogazil/loops/blob/c10e50cf6fc7c3c068d8f94fb87f1dd638029f92/loops-maturado/scripts/refresh-active-rules.mjs) and [generated rules](https://github.com/pedrogazil/loops/blob/c10e50cf6fc7c3c068d8f94fb87f1dd638029f92/loops-maturado/prompt_iterations/ACTIVE_RULES.md), accessed 2026-08-10.

This makes the current `my-llm-kit` representation more actionable and less vulnerable to an “impact: high” self-label bypassing recurrence evidence.

### Gaps worth fixing in `my-llm-kit`

1. **Independence is not mechanically enforced.** The compiler requires unique run IDs, but promotion only counts matching occurrences. It does not require distinct OpenSpec changes. Duplicate observations from the same change can therefore promote a rule. Source: [local learning compiler](/home/badmuriss/Documents/my-llm-kit/skills/impl/scripts/learning.py), inspected 2026-08-10.

2. **Evidence is free text.** The orchestrator is instructed to record only what it observed, but the compiler cannot confirm that a referenced check, diff, commit, or artifact exists. Loops adds an `evidence_ref` field in its templates, although its compiler does not validate that field either. Source: [Loops issue template](https://github.com/pedrogazil/loops/blob/c10e50cf6fc7c3c068d8f94fb87f1dd638029f92/loops-template/prompt_iterations/TEMPLATES/issues_template.md), accessed 2026-08-10.

3. **State is written mainly at the end.** A desktop or agent crash can lose the orchestrator's current grades, hypotheses, active worker ownership, and remaining integration work. Loops keeps a resumable round-state file. Source: [Loops current state](https://github.com/pedrogazil/loops/blob/c10e50cf6fc7c3c068d8f94fb87f1dd638029f92/loops-template/rounds/current_state.json), accessed 2026-08-10.

4. **Failures are flattened into task grades.** Loops' issue template distinguishes symptom, root-cause hypothesis, proposed fix, and verification plan. That distinction prevents a plausible explanation from becoming a learned rule before it is tested. Source: [Loops issue template](https://github.com/pedrogazil/loops/blob/c10e50cf6fc7c3c068d8f94fb87f1dd638029f92/loops-template/prompt_iterations/TEMPLATES/issues_template.md), accessed 2026-08-10.

5. **Learning only produces prompt rules.** Loops' best principle is “mechanical truth over remembered truth”: recurring process knowledge should become a test, guard, linter, or script when possible. Source: [reusable patterns](https://github.com/pedrogazil/loops/blob/c10e50cf6fc7c3c068d8f94fb87f1dd638029f92/loops-template/PATTERNS-LEARNED.md), accessed 2026-08-10.

## Recommended extraction

### Adopt

1. Add a crash-safe state file per active OpenSpec change. Persist task status, grade, current hypothesis, worker ownership, last observed commit, validation status, and cleanup obligations after every state transition. Resume only after reconciling it with the real diff, processes, and git state.

2. Add structured incident records to the learning run: `symptom`, `hypothesis`, `proposed_fix`, `verification_plan`, and `evidence_refs`. A hypothesis remains an incident until its verification plan passes.

3. Strengthen promotion. Require recurrence across distinct change identifiers, verified evidence references, and identical normalized rule semantics. Never let a self-assigned impact label bypass evidence.

4. Add an explicit promotion target. Keep `rule` for guidance. Add `gate_candidate` for recurring lessons that can become an executable check. A gate candidate should create a normal OpenSpec proposal; it must not rewrite harness code automatically.

5. Aggregate quality and safety signals, not vanity throughput. Useful signals include task grades, unobserved claims, conflicts, retries, resource-guard denials, stale-process cleanup, and crash recovery. PR volume is not a quality measure.

6. Add a convergence rule. Stop when no verified, in-scope, high-value candidate remains. Loops says every round must produce changes, which creates pressure to invent work. Source: [Loops quality rules](https://github.com/pedrogazil/loops/blob/c10e50cf6fc7c3c068d8f94fb87f1dd638029f92/loops-template/prompt/CRAFT_QUALITY.md), accessed 2026-08-10.

### Do not adopt

- Do not import the local PR Markdown bureaucracy. OpenSpec tasks, diffs, and end-of-run records already cover the useful parts.
- Do not adopt large fan-out, fixed worker quotas, or fixed timeout values. They conflict with the machine-wide resource guard and the recent desktop crash.
- Do not share mutable dependency directories across worktrees. The matured rounds record cross-worktree dependency corruption. Source: [round failure record](https://github.com/pedrogazil/loops/blob/c10e50cf6fc7c3c068d8f94fb87f1dd638029f92/loops-maturado/prompt_iterations/round_003/issues_detected.md), accessed 2026-08-10.
- Do not activate a rule because a model labels it high impact or forces it.
- Do not let learning mutate the global host instructions or other repositories.
- Do not make “a non-empty round” a success condition.

## Trial by fire

**Counterargument: the template is intentionally incomplete because an agent adapts it.** Accepted. Missing project-specific scripts are not by themselves a defect. The remaining problem is the lack of a schema, adaptation checklist, and executable validation that prove all stale assumptions were removed.

**Counterargument: public GitHub metadata is irrelevant because the real work happened elsewhere.** Accepted. The public repository cannot disprove private results. It also cannot verify them, so those results should not drive the design without access to the source evidence.

**Counterargument: local PR reports are enough evidence.** They are useful first-party records, but self-authored status and validation fields are not independent review or approval metadata. Several reports marked merged still contain pending checks, which proves the distinction matters.

**Counterargument: more fields will turn `$impl` into the same bureaucracy.** Valid. The smallest useful change is a compact machine-readable incident list and a resumable state file. Do not copy the three-document-per-round hierarchy.

## Final decision

The falsifier did not trigger completely: Loops adds useful concepts beyond documentation scaffolding. It did trigger against wholesale adoption. The selected implementation hardens `$impl` with resumability, incident evidence, true cross-change recurrence, and gate candidates while keeping orchestration resource-bounded.

Implementation: [impl state](/home/badmuriss/Documents/my-llm-kit/skills/impl/scripts/impl_state.py), [learning compiler](/home/badmuriss/Documents/my-llm-kit/skills/impl/scripts/learning.py), and [workflow contract](/home/badmuriss/Documents/my-llm-kit/skills/impl/SKILL.md), updated 2026-08-10.

## Source trail

Primary sources only:

- [Loops repository](https://github.com/pedrogazil/loops), accessed 2026-08-10.
- [Template snapshot](https://github.com/pedrogazil/loops/tree/c10e50cf6fc7c3c068d8f94fb87f1dd638029f92/loops-template), accessed 2026-08-10.
- [Matured snapshot](https://github.com/pedrogazil/loops/tree/c10e50cf6fc7c3c068d8f94fb87f1dd638029f92/loops-maturado), accessed 2026-08-10.
- [Current local `$impl` skill](/home/badmuriss/Documents/my-llm-kit/skills/impl/SKILL.md), inspected 2026-08-10.
- [Current local learning compiler](/home/badmuriss/Documents/my-llm-kit/skills/impl/scripts/learning.py), inspected 2026-08-10.
- Creator testimony supplied by the user in this conversation. No public source URL was provided.
