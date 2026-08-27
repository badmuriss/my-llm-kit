# Cyclomatic complexity audits for `my-llm-kit`

## Protocol

- Question: How can the Hunk complexity audit be adapted to `my-llm-kit` to reduce decision-path complexity and code bloat without creating noisy gates?
- Decision criterion: Recommend an audit only when it measures a risk present in this repository, identifies actionable hotspots, and supports a low-noise baseline or ratchet.
- Falsifier: Reject the recommendation if the Hunk change does not support the cited reduction, if the technique does not transfer to Python, or if local hotspots are only size or cohesion problems that cyclomatic complexity cannot detect.
- Risk: material
- Credits used: 18

## Provider trail

| Intent | Provider | Tool or endpoint | Outcome | Credits | Fallback reason |
|---|---|---|---|---:|---|
| Reuse prior local research | local | `rg` in `research/` | One related harness brief found; no prior Hunk or Oxc finding | 0 | None |
| ScrapingDog account preflight | ScrapingDog | `account_summary.sh` | Key present; starting balance recorded | 0 | None |
| Inspect the supplied PR and its prerequisite | GitHub | `gh pr view` and `gh pr diff` | Primary PR metadata and patches opened | 0 | None |
| Discover Oxc documentation | Oxc | `llms.txt` preflight | Official machine-readable index found; primary rule page selected | 0 | None |
| Discover Ruff documentation | Astral | `llms.txt` and sitemap preflight | Official indexes found; primary rule and settings pages selected | 0 | None |
| Locate the creator wording supplied by the user | ScrapingDog | Google Search API | Exact wording was not located; it remains user-supplied context | 5 | No fallback because provenance was not needed to assess the technical argument |
| Snapshot primary web sources | ScrapingDog | `/scrape?dynamic=false` | All five requested pages collected | 5 | MCP catalog did not expose ScrapingDog tools; used the repository's required snapshot helper |
| Measure the local Python source | local | Ruff C901 via `uvx` | Repository-wide reports produced at several thresholds | 0 | None |
| ScrapingDog account postflight | ScrapingDog | `account_summary.sh` | Account-wide delta recorded; it exceeded the direct task estimates | 0 | None |

The account-wide credit delta was `18`. The direct calls in this task estimated `10`. The account endpoint cannot attribute the remaining delta to this process, so the protocol records the larger account-wide value.

## Claim ledger

| Claim | Source | Accessed | Snapshot | Primary | Direct | Current | Independent | Verdict |
|---|---|---|---|---|---|---|---|---|
| The Hunk refactor reduced `parseSessionCommand` complexity from 91 to 12 while preserving behavior. | https://github.com/modem-dev/hunk/pull/857 | 2026-08-27 | research/sources/hunk-pr-857/page.md | yes | yes | yes | no | accepted |
| The Hunk refactor extracted focused parsers but increased `src/app/cli.ts` by 453 additions and 385 deletions. | https://github.com/modem-dev/hunk/pull/857 | 2026-08-27 | research/sources/hunk-pr-857/page.md | yes | yes | yes | no | accepted |
| The follow-up added an Oxlint complexity ceiling of 80 to the existing lint command. | https://github.com/modem-dev/hunk/pull/861 | 2026-08-27 | research/sources/hunk-pr-861/page.md | yes | yes | yes | no | accepted |
| Hunk chose 80 as a regression ceiling above existing scores of 78 and 76, not as its long-term target. | https://github.com/modem-dev/hunk/pull/861 | 2026-08-27 | research/sources/hunk-pr-861/page.md | yes | yes | yes | no | accepted |
| Oxlint defines complexity as independent control-flow paths, defaults its maximum to 20, and supports classic and modified variants. | https://oxc.rs/docs/guide/usage/linter/rules/eslint/complexity | 2026-08-27 | research/sources/oxc-complexity-rule/page.md | yes | yes | yes | no | accepted |
| Ruff C901 measures McCabe complexity as one plus a function's decision points and defaults its maximum to 10. | https://docs.astral.sh/ruff/rules/complex-structure/ | 2026-08-27 | research/sources/ruff-complex-structure/page.md | yes | yes | yes | no | accepted |
| At repository commit `6037fb8`, Ruff reports `apply_event` at 385 and reports 75 production violations at its default maximum of 10. | https://github.com/badmuriss/my-llm-kit/commit/6037fb8dbfa59ec6f072ebe17a89d1d1d083b3b8 | 2026-08-27 | local Ruff C901 output | yes | yes | yes | no | accepted |
| At the same commit, a maximum of 50 leaves only `apply_event` failing; a maximum of 40 leaves five failing functions. | https://github.com/badmuriss/my-llm-kit/commit/6037fb8dbfa59ec6f072ebe17a89d1d1d083b3b8 | 2026-08-27 | local Ruff C901 output | yes | yes | yes | no | accepted |
| `apply_event` spans 1,902 lines and dispatches every one of the 50 core event types. | https://github.com/badmuriss/my-llm-kit/blob/6037fb8dbfa59ec6f072ebe17a89d1d1d083b3b8/skills/agent-graph/scripts/graph_core.py#L2064-L3965 | 2026-08-27 | skills/agent-graph/scripts/graph_core.py | yes | yes | yes | no | accepted |
| Per-run control-runtime copies are intentional immutable snapshots and are not canonical source files. | https://github.com/badmuriss/my-llm-kit/blob/6037fb8dbfa59ec6f072ebe17a89d1d1d083b3b8/skills/agent-graph/scripts/runtime_pin.py#L128-L183 | 2026-08-27 | skills/agent-graph/scripts/runtime_pin.py | yes | yes | yes | no | accepted |

## Findings

### Conclusion

Adopt the audit, but treat it as a refactor trigger, not a bloat score. The Hunk sequence has two separate changes:

- The refactor reduced one function from `91` paths to `12`. It moved control flow into focused handlers and preserved behavior. [Hunk refactor PR, accessed 2026-08-27](https://github.com/modem-dev/hunk/pull/857).
- The follow-up added a ceiling of `80` after the refactor. Its own description calls this a regression ceiling and says it must be lowered later. [Hunk lint PR, accessed 2026-08-27](https://github.com/modem-dev/hunk/pull/861).

This distinction matters. The linter did not perform the simplification. It created a deterministic failure that forced another inspection and repair loop.

The audit also does not prove bloat reduction. The Hunk production file gained `453` lines and lost `385`, a net increase of `68`, while the maximum function score fell. This is an inference from the primary diff, not a criticism of the refactor. [Hunk refactor PR, accessed 2026-08-27](https://github.com/modem-dev/hunk/pull/857).

### How to read the creator's opinion

The creator's wording supplied by the user is technically sound: a failed metric forces the model to re-open unfamiliar code instead of accepting the first generated structure. The model may then delete unnecessary branches, replace a branch chain with data, or extract cohesive handlers.

The risk is metric gaming. A model can lower the maximum score by moving each branch into a new helper while preserving the same total decisions, lines, and coupling. The harness must ask what logic disappeared, not only which function became smaller.

The exact creator wording was not found by the bounded search. It is treated as user-supplied interpretation, not as an independently verified public claim.

### Deep modules do not conflict with this technique

A deep module exposes a small interface and hides substantial coherent work. It does not require one long function.

`apply_event(projection, event)` already has a deep public interface. Its internal implementation can use private reducers grouped by event family while callers keep the same interface. The bad outcome would be a public helper for every branch or thin wrappers that only move lines.

The Hunk refactor follows the same pattern at its boundary. Callers still invoke one session parser. The extracted command handlers are private implementation details.

### Local audit: the main problem is real and concentrated

[high] `skills/agent-graph/scripts/graph_core.py:2064` contains the clearest target. `apply_event` scores `385`, spans `1,902` lines, and handles `50` event types. [Pinned source, accessed 2026-08-27](https://github.com/badmuriss/my-llm-kit/blob/6037fb8dbfa59ec6f072ebe17a89d1d1d083b3b8/skills/agent-graph/scripts/graph_core.py#L2064-L3965).

Evidence: one `if` and `elif` reducer owns run startup, coordinator fencing, driver state, attempts, delegation, checks, grading, cleanup, browser surfaces, and completion. Any new event makes the same function harder to review.

Remedy: keep `apply_event` as the only public reducer. Move cohesive event families into private reducers with one shared precondition and postcondition layer. Validate that the private handler registry covers the canonical event set.

Why simpler: the public module stays deep, while each internal reducer owns one state-machine area. This removes central control-flow fan-in without exposing new public concepts.

[medium] The next hard-ceiling candidates are `command_sync` at `46`, `validate_record` at `46`, `import_checked_task` at `45`, and the research finding `audit` at `41`. [Pinned repository snapshot, accessed 2026-08-27](https://github.com/badmuriss/my-llm-kit/commit/6037fb8dbfa59ec6f072ebe17a89d1d1d083b3b8).

Evidence: these functions mix lifecycle phases or validate several nested record families. They are smaller than `apply_event`, so they should follow it rather than join the same rewrite.

Remedy: extract lifecycle phases and nested validators only where a private helper owns a complete invariant. Do not create one helper per condition.

Why simpler: each function gains one reason to change. Shared state and error wording remain local to the owning module.

[review trigger] `route` scores `32`, but its branches form one coherent selection policy. The score warrants inspection, not an automatic split. [Pinned source, accessed 2026-08-27](https://github.com/badmuriss/my-llm-kit/blob/6037fb8dbfa59ec6f072ebe17a89d1d1d083b3b8/skills/agent-graph/scripts/routing.py#L481-L679).

This is where the deep-module check prevents slop. A refactor is useful only if it deletes duplicate candidate construction or expresses the policy as clearer data. Thin wrappers would make this function worse.

Generated control-runtime copies must stay outside the audit. Each graph run freezes a read-only runtime for replay safety, so those files are evidence, not canonical source. [Runtime pin implementation, accessed 2026-08-27](https://github.com/badmuriss/my-llm-kit/blob/6037fb8dbfa59ec6f072ebe17a89d1d1d083b3b8/skills/agent-graph/scripts/runtime_pin.py#L128-L183).

### Recommended harness policy

Use two layers:

- Hard repository ceiling: refactor `apply_event`, then set Ruff C901 to `50`. At the pinned repository state, `50` would leave only that outlier failing. After it is removed, the next-highest observed score is `46`. [Pinned repository snapshot, accessed 2026-08-27](https://github.com/badmuriss/my-llm-kit/commit/6037fb8dbfa59ec6f072ebe17a89d1d1d083b3b8).
- Changed-code review: new Python functions should meet Ruff's default maximum of `10`. Modified legacy functions must not increase. Functions still above the default require a reviewer decision, not an inline suppression. [Ruff setting, accessed 2026-08-27](https://docs.astral.sh/ruff/settings/#lint_mccabe_max-complexity).
- Language-native tools: use Ruff C901 for Python and Oxlint `complexity` for JavaScript or TypeScript. Oxlint's documented default is `20`; its score must not be compared directly with Ruff's score. [Oxc rule, accessed 2026-08-27](https://oxc.rs/docs/guide/usage/linter/rules/eslint/complexity).
- Ratchet: lower the hard ceiling only after the repository is green at the next level. Never raise the threshold, add `noqa`, or disable the rule to pass a change.

Pair the score with an anti-gaming review for behavior-preserving refactors:

- maximum function complexity before and after;
- total decision complexity in the touched module before and after;
- production line delta;
- new helper and public-symbol delta;
- branches deleted versus branches moved;
- the smallest behavior check that protects the refactor.

Only the maximum score should start as a hard gate. The other deltas are review evidence. A line or helper increase can be justified when it creates a real domain boundary.

### Where this belongs in `my-llm-kit`

Do not add a new broad skill first. Extend the existing `impl` and `thermo-nuclear-code-quality-review` flow:

- Run the project's native complexity command after the task check passes and before the final thermo review.
- Attach the machine-readable findings to the implementation evidence.
- Use `audit-reject-attempt` when a changed function introduces or worsens a violation.
- Require the repair attempt to state whether it deleted logic, converted it to data, or moved it behind a cohesive private boundary.
- Reject new suppressions and threshold changes in the same diff unless the task explicitly changes policy.

For this repository, add a small Ruff configuration and a pinned developer or CI invocation. Do not install Ruff into every harness user's environment. The audit protects development of `my-llm-kit`; it is not a runtime dependency of the installed harness.

### Suggested implementation order

- Refactor `apply_event` behind private event-family reducers. Preserve journal envelopes, projection output, error behavior, and the public entrypoint.
- Enable the clean hard ceiling after that refactor. Exclude immutable run snapshots, not tests or canonical scripts.
- Add changed-code complexity evidence to the thermo review and `impl` repair loop.
- Ratchet the next cluster only after the first refactor and its focused checks pass.

This order gets the creator's intended effect: the model must re-investigate a concrete failure, but the harness also checks whether complexity disappeared or only moved.

## Disagreements

- Oxc documents a default maximum of `20`, while Hunk chose `80`. These values serve different purposes: a general default versus a temporary repository regression ceiling. [Oxc rule, accessed 2026-08-27](https://oxc.rs/docs/guide/usage/linter/rules/eslint/complexity). [Hunk lint PR, accessed 2026-08-27](https://github.com/modem-dev/hunk/pull/861).
- The ScrapingDog account delta was `18` credits while the task's direct calls estimated `10`. The account summary is machine-wide and does not expose per-request attribution. [ScrapingDog account documentation, accessed 2026-08-27](https://www.scrapingdog.com/documentation/account-api/).

## Open questions

- Whether the first implementation should stop at the local Ruff gate or also add cross-language changed-code detection for repositories that use Oxlint.
- Whether module-wide total complexity should become a future executable gate after the first refactor provides a stable baseline.

## Council review

- Status: not run
- Reason: material conclusions rest on opened primary sources and a reproducible local audit; no primary-source conflict triggered council review
- Accepted findings: None.
- Rejected findings: None.

## Sources consulted

- https://github.com/modem-dev/hunk/pull/857, accessed 2026-08-27.
- https://github.com/modem-dev/hunk/pull/861, accessed 2026-08-27.
- https://oxc.rs/docs/guide/usage/linter/rules/eslint/complexity, accessed 2026-08-27.
- https://docs.astral.sh/ruff/rules/complex-structure/, accessed 2026-08-27.
- https://docs.astral.sh/ruff/settings/#lint_mccabe_max-complexity, accessed 2026-08-27.
- https://github.com/badmuriss/my-llm-kit/commit/6037fb8dbfa59ec6f072ebe17a89d1d1d083b3b8, accessed 2026-08-27.
- https://github.com/badmuriss/my-llm-kit/blob/6037fb8dbfa59ec6f072ebe17a89d1d1d083b3b8/skills/agent-graph/scripts/graph_core.py#L2064-L3965, accessed 2026-08-27.
- https://github.com/badmuriss/my-llm-kit/blob/6037fb8dbfa59ec6f072ebe17a89d1d1d083b3b8/skills/agent-graph/scripts/routing.py#L481-L679, accessed 2026-08-27.
- https://github.com/badmuriss/my-llm-kit/blob/6037fb8dbfa59ec6f072ebe17a89d1d1d083b3b8/skills/agent-graph/scripts/runtime_pin.py#L128-L183, accessed 2026-08-27.
- https://www.scrapingdog.com/documentation/account-api/, accessed 2026-08-27.

## Trial by fire

- Primary-source claims: Hunk PR behavior and lint policy, Oxc and Ruff rule semantics, pinned repository source, and reproducible local Ruff output.
- Secondary-only claims: None. The creator wording is user-supplied context and is not treated as a verified claim.
- Volatile claims: Local complexity scores depend on commit `6037fb8dbfa59ec6f072ebe17a89d1d1d083b3b8` and must be rerun before implementation.
