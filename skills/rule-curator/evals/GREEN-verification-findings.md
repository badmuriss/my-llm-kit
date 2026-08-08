# GREEN verification — findings (with skill)

Three runs against the same baseline corpus, agents operating under the skill
(SKILL.md + references read as instructions). Scored against
`baseline-corpus/ANSWER-KEY.md`.

## Run 1 — analysis, strong model (Opus general-purpose)

Near-perfect. Every planted issue caught in the right category, including the two
the RED baseline missed:

- **Brittle** (forbidden-words denylist): caught.
- **Misfiled** (PR template stored as `type: feedback`): caught, named the wrong type.
- **Impact vs audit note separated** on every rule (the big baseline structural gap): present.
- Redundant, Stale (named ADR-003), both Conflicts (PR vs ADR-007; npm vs pnpm), Not-actionable: caught.
- 5 healthy rules got no audit note; no invented staleness.
- Produced a valid `rules.json` in schema + checkpoint summary.

The agent explicitly noted it "checked Brittle and Misfiled on purpose since the
contract flags them as routinely missed" — the skill drove the behavior the
baseline lacked.

## Run 2 — analysis, weak model (Haiku)

Carried the headline value: **caught Brittle and Misfiled**, held the
impact/audit separation, kept the healthy controls clean. This is the key
evidence that the skill, not the model, does the work.

Weaknesses (model-capability, not skill-clarity):
- Missed the cross-source npm/pnpm conflict (listed pnpm as healthy without
  connecting it to the npm command rule).
- Fuzzy rule count and did not inline the full rules.json as asked.

Decision: do NOT overfit the skill to force the cross-source conflict (the
general "conflicts are cross-source, analyze the whole corpus at once" guidance
is already present). Recorded as a known weak-model limitation.

## Run 3 — apply phase (strong model)

Produced a correct apply-plan from a crafted `apply-test/decisions.json`:

- **Memory drop did both halves** (delete entry file AND remove the MEMORY.md
  pointer line), citing "a dangling pointer is a broken state." This was the main
  thing to verify; passed.
- **Stale decision** (`Z9`, a rule absent from the sources) flagged and skipped.
- **keep** = no-op; **modify** = correct before/after.
- Reasoned correctly about paraphrase-vs-verbatim `original` (not a false drift-skip).

New, general finding (drove the one REFACTOR below): dropping the only rule under
a section heading **orphans the heading**. The agent removed it via general
surgical-change discipline, but the apply guidance did not name this case.

## REFACTOR applied

- `references/apply-plan-format.md`: added handling for structure orphaned by a
  drop (remove a heading left empty when its last rule is dropped). General, not
  fixture-specific. The Run-3 agent already exhibited this behavior via general
  discipline, so the edit codifies an observed-correct behavior.

## Verdict

Skill closes all RED baseline gaps (Brittle, Misfiled, separated structure,
deliverable) and holds the disciplines (no rubber-stamping, no invented
staleness) on both a strong and a weak model. Apply phase correct, including the
both-halves memory drop and stale-decision skip. Bulletproof for the tested
scenarios.

## Addendum 2026-06-18 — work-status entry burying a directive (planted finding #11)

Surfaced by a live test run on a real ~78-rule corpus: ~14 memory entries were
project work-status (ship logs / phase trackers) that buried a durable directive.
The skill had no explicit vocabulary for this; agents improvised off the
PRD-exclusion guidance.

Planted finding #11 added to the baseline corpus
(`memory/project_search_revamp.md`): a `type: project` ship log burying one hard
directive ("never query the legacy `search_index` table directly; go through
`SearchService.query()`").

**RED (current skill, before the edit):**
- **Strong model (Opus):** partial. Reached an acceptable verdict (keep directive,
  trim narrative) but only by shoehorning it into **Misfiled** (wrong category —
  the entry is not mis-typed) and marking the whole entry `isStandingRule: true`.
- **Weak model (Haiku):** clean failure. Marked the entry `isStandingRule: true`,
  wrote **no audit note**, verdict **KEEP as-is** — preserving the dated ship log
  (commit, p95, backfill count, Phase-3 follow-ups) as a "healthy rule" forever.

**GREEN (after the edit):** Haiku now writes the audit note ("work-status, not a
standing rule, ages into noise"), names the rotting status detail, and gives the
verdict "extract the directive to a clean entry; archive/trim the log. Do NOT keep
the whole entry." No regression on the other 10 findings or the healthy controls.

**Edit made (GREEN, minimal):**
- `SKILL.md` step 1 inclusion test: named **work-status entries** as a sibling of
  PRDs/specs (not standing rules), plus the **extract-the-buried-directive,
  archive-the-log** verdict.
- `SKILL.md` red-flags: added the "kept a work-status entry whole instead of
  extracting its directive" self-check.
- `references/analysis-contract.md`: added a worked example for the case.

## Addendum 2026-06-18 — corpus-level patterns at the checkpoint (planted findings #12-14)

Surfaced by the same live test run: on a large corpus the per-rule notes fragment
a systemic *habit* (e.g. ~22 separate Brittle notes that are really one
over-specification habit). The step-5 checkpoint reported counts only, never a
cross-cutting pattern.

Planted three standing rules that share one habit — a sound directive wrapped in
rot-prone provenance (commits, file:line, migrations, dates, counts):
`feedback_destructive_migrations`, `domain_checkin_dedup`,
`feedback_rate_limit_budget`.

**RED (weak model, before the edit):** marked all three entries **healthy / KEEP,
no audit note** — missed the per-rule provenance brittleness entirely — and the
step-5 checkpoint was a pure category-count table with **no cross-cutting pattern**.

**Edit (GREEN):** `SKILL.md` step 5 extended from counts to also name cross-cutting
patterns (same defect across **3+ rules**), with the common patterns enumerated
(systemic over-specification, duplicate cluster, misfiling habit, work-status
habit), a **"no invented patterns"** discipline (3+ real rules, never a one-off),
and a red-flag self-check.

**First GREEN run was partial** (the REFACTOR signal): the patterns section now
appeared, but the weak model still marked two of the three planted entries
healthy and coined a sub-threshold 2-rule "pattern." Root cause: the per-rule
**Brittle** category didn't tell the agent that a sound directive wrapped in
provenance is itself brittle.

**REFACTOR:** `references/analysis-contract.md` Brittle category — added the
"sound directive wrapped in rot-prone provenance" facet (flag the provenance, keep
the directive; don't wave it through as healthy). General, not fixture-specific.

**GREEN after refactor:** weak model now flags all three (M5/M6/M7) as
Brittle-provenance and reports the checkpoint pattern "systemic over-specification
of provenance (4 rules: M5, M6, M7, plus G5)" with the corpus-wide fix. Healthy
controls not swept in; no invented staleness.

**Known weak-model limitation (not chased, per no-overfit policy):** the weak
model occasionally labels a 2-rule conflict pair a "cluster" under patterns. It is
harmless over-inclusion (the conflict is correct and already captured per-rule),
and the 3+ threshold is stated; recorded rather than tuned further. A strong model
produces clean, correctly-thresholded patterns (verified on a real ~78-rule
corpus, where it surfaced four genuine 3+ patterns with no false ones).

## Addendum 2026-06-18 — description tightened (CSO)

Removed the workflow-summary tail from the `description` ("...to decide which
rules to keep, drop, or rewrite, then applying those decisions") per writing-skills
CSO guidance (a workflow summary in the description becomes a shortcut Claude
follows instead of reading the body). Kept the trigger keywords and the NOT-for
boundary. Discovery re-checked on a weak model: "clean up my whole rule set"
selects rule-curator; "reword just this one rule" correctly selects none.

## Addendum 2026-08-01 — version-history cases added, not yet run

The skill gained version-history guidance (per-repo pins in `meta.commits`,
history-as-evidence for Stale/Brittle, dirty-aware drift, untracked-source
warnings; upstream 687a457). Eval cases H1–H6 and the deterministic
history-wrapped corpus (`evals/make_history.py`) exist but have NOT been run on
either arm. Until both RED and GREEN runs cover them — on the same models as
the recorded baselines, or after a deliberate full re-baseline — the
version-history discipline is untested by this apparatus.
