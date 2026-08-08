---
name: rule-curator
description: Use when auditing, pruning, or cleaning up an agent's entire existing rule set in one bulk pass across every rule source at once (all CLAUDE.md files, all memory entries, AGENTS.md, ADRs, COORDINATION). This is whole-corpus hygiene; NOT for adding, editing, or fixing an individual rule (just edit that file directly).
---

# Rule Curator

## Overview

Agents accumulate behavioral rules across many files. Nobody prunes them, so they
go stale, duplicate each other, duplicate installed skills, restate default
behavior, or impose rituals whose friction exceeds their value.

**Core principle: every rule is a permanent tax.** It costs context tokens every
session and dilutes instruction-following attention across more directives. A
rule earns its place only if its behavioral payoff beats that ongoing cost. This
skill audits the rule set against that bar and acts on the result.

This skill exists because a capable model, left to its own devices, finds the
*loud* defects (conflicts, staleness, duplication) but skips the *quiet* ones
(brittle rules, misfiled entries), never separates a rule's neutral effect from
the critique of it, and produces prose instead of a usable deliverable. The
workflow below forces all four.

## When to use

- "Audit / clean up / prune my CLAUDE.md / rules / memory"
- After a big refactor or decision, to find rules that went stale
- The rule set has grown and instruction-following feels diluted
- Periodic hygiene on the directives an agent operates under

**Not for:** authoring new rules (this curates existing ones), or auditing PRDs
and feature specs (those are bounded deliverable specs, not standing rules).

## Workflow

Copy this checklist and track progress:

```
Rule Curator progress:
- [ ] 1. Discover rule sources (+ enumerate installed skills and ADRs; pin each repo's commit)
- [ ] 2. SCOPE GATE: confirm/narrow/expand sources + emphasis (default: all, full)
- [ ] 3. Extract rules into rules.json
- [ ] 4. Analyze each rule against the whole corpus (impact + conditional audit note)
- [ ] 5. PRE-CURATE CHECKPOINT: report "N rules, K flagged"; proceed
- [ ] 6. Build the curation UI (run build_curator.py)
- [ ] 7. Human curates in browser, exports decisions.json
- [ ] 8. Build the apply-plan from decisions.json
- [ ] 9. APPLY GATE: confirm, then execute the edits
```

### 1. Discover

A **rule** is a *standing directive that shapes behavior across tasks* (do /
never / prefer / always / use X not Y). That is the inclusion test, not a file
list. A bounded deliverable spec (PRD, feature spec) is not a rule. Neither is a
**work-status entry** — a ship log, phase tracker, or "next step" note (common in
memory systems, often `type: project`): it is bounded work-tracking that ages
into noise, not a standing directive.

**But a work-status entry often buries one durable directive** ("never query the
legacy table", "don't re-add X", "this finals refresh must clear the sticky
field"). When it does, the entry as a whole is *not* a standing rule, yet the
buried directive must survive. The correct verdict is **extract the directive to
a clean rule entry and archive/trim the surrounding log** — neither keep the
whole log (dead weight, and a weak model will rubber-stamp it as healthy) nor
drop it wholesale (loses the directive).

Auto-detect the sources that exist and contain standing directives:
- Global `~/.claude/CLAUDE.md` and project `CLAUDE.md` (including nested)
- Memory: `MEMORY.md` plus every entry it points to
- Project rule docs: `AGENTS.md`, `COORDINATION.md`, primers, conventions
- **ADR-type decision records, however named** (`docs/adr/*`, `docs/decisions/*`,
  RFCs). Extract only the *binding constraint*, not the narrative.

Also enumerate **installed skills** (names + descriptions) and the ADRs found,
so "duplicates a skill / duplicates an ADR" findings are grounded, not guessed.
PRDs and feature specs are excluded by default; a user may add sources at the
scope gate. If nothing is found, report and stop. Never fabricate a rule set.

**Search wider than the repo before declaring anything missing.** Rule sources,
and the trackers they cite, often sit *above* the project root or outside it
entirely (`~/.claude/`, a parent directory, a sibling checkout). A repo-scoped
search returning nothing is not evidence a file is absent. Widen the search
before writing "does not exist" into an audit note, and record the resolved
absolute path so the next reader does not repeat the hunt. An unqualified
filename in a rule is itself a finding — flag it Brittle and qualify it.

**Pin the corpus.** A corpus routinely spans more than one repo — the global
`~/.claude` config and the project repo are usually two — plus files under no
repo at all, so one commit cannot pin it. For every distinct repo that
contributes sources, record a pin (`git rev-parse --short HEAD`, branch,
dirty-tree state) and carry the list as `meta.commits` in rules.json. The UI
header displays the pins and both exports embed them, so a `decisions.json`
that comes back days later can be checked against the trees it was computed
from. Rule files outside any repo (a memory directory, an untracked global
config) have no pin — say so in `meta.sources` rather than implying the whole
corpus is pinned.

### 2. Scope gate (required, defaults to proceed)

Present the discovered sources and a rough rule count, tagging each source
tracked or untracked — an untracked source has no history, so a drop there is
unrecoverable, and the human should know that before curating, not after.
Offer to confirm, narrow,
or expand the source set, and optionally to focus ("general health audit" vs
"hunting duplicates / staleness / bloat"). **If the user just says go: all
sources, full audit.** Running unattended: take that default.

### 3. Extract

Normalize each rule into the schema `build_curator.py` consumes:

```json
{
  "meta": { "title": "...", "generated": "YYYY-MM-DD",
            "commits": [ { "root": "~/.claude", "hash": "abc1234", "branch": "main", "dirty": false } ],
            "sources": ["..."] },
  "categories": [ { "id": "global-claudemd", "label": "Global · CLAUDE.md", "color": "#c0392b" } ],
  "rules": [
    {
      "id": "G1", "category": "global-claudemd",
      "title": "short title", "summary": "one-line plain-English statement",
      "source": "path:line", "why": "optional origin",
      "agentImpact": "see step 4", "auditNote": "see step 4 (omit if healthy)",
      "auditCategory": "see step 4 (omit when auditNote is omitted)"
    }
  ]
}
```

Group `categories` by source/kind (global vs project, CLAUDE.md vs memory vs ADR
vs convention). One rule per standing directive.

### 4. Analyze (against the whole corpus)

Two outputs per rule, **explicitly separated** so the human gets facts and
critique as distinct things. This separation is mandatory; do not fuse verdict
and reasoning into one blob.

- **`agentImpact` — always.** Neutral-diagnostic, first person. What following
  this rule actually changes about your behavior, plus its side effect / cost.
  When a rule merely restates default behavior, **say so plainly** ("restates
  default behavior; changes nothing distinctive"). That is the finding the human
  cannot see for themselves.
- **`auditNote` — only when something is wrong.** The opinionated health/cost
  judgment, drawn from the fixed taxonomy below. **Omit it when the rule is
  healthy.** Forcing a note onto every rule manufactures fake problems.
- **`auditCategory` — whenever `auditNote` is present.** The taxonomy row's name
  verbatim from the left column below, nothing invented. The UI renders it as
  the flag tag on the card, which is what makes an unhealthy rule findable while
  scrolling; without it the card still flags, just with the generic word.

| Audit category | Fires when |
|----------------|-----------|
| Redundant | Duplicates another rule, or an installed skill / ADR |
| Stale / superseded | References changed files or decisions; a newer rule overrides it |
| Misfiled | Wrong home (a template stored as "feedback"; a project rule in global config) |
| Low-yield ritual | Friction exceeds value |
| Not actionable | Too vague to change behavior |
| Brittle | Will rot (hardcoded word lists, dates, paths) |
| Conflicts | Contradicts another rule |

Run the **whole taxonomy** against every rule. The easy categories (Conflicts,
Stale) get found on their own; **Brittle and Misfiled are the ones routinely
missed**, so check them explicitly. Redundancy, Conflicts, and Supersession are
only visible across the corpus, so analyze with all rules and the skill/ADR list
in view, never each rule in isolation.

**Use version history as evidence where it exists.** History turns two
categories from judgment into fact: for **Stale / superseded**, `git log -S`
finds the superseding commit — exactly the evidence the no-invented-staleness
discipline demands you name; for **Brittle**, repeated edits to the same
hardcoded list, path, or count document the rot. Either way the note cites what
changed, never the bare count: history is corroboration, not the finding, and
age alone (or churn alone) is not an audit note. Where sources are untracked,
say so rather than silently applying a weaker standard to half the corpus.
Command-level detail and the guards live in the Stale and Brittle sections of
the analysis contract.

**Full rubric, category tests, and worked good/bad examples:** see
[references/analysis-contract.md](references/analysis-contract.md).

### 5. Pre-curate checkpoint (informational)

Report "analyzed N rules, flagged K" with the per-category breakdown. Then name
any **cross-cutting patterns** — the same defect or structure recurring across
**3+ rules**, which the per-rule notes fragment into separate line-items. Each
pattern is one line: the habit, the rule IDs it spans, and the single fix that
applies corpus-wide. The common ones:

- **Systemic over-specification** — many rules pair a durable one-line directive
  with rot-prone provenance (commit hashes, line numbers, counts, dates). Fix:
  keep the directive, move provenance to a footer or drop it.
- **Duplicate / overlap cluster** — 3+ rules covering the same territory; candidates
  for one consolidated rule the others point to.
- **Misfiling habit** — several entries of one type carrying another type's content.
- **Work-status habit** — multiple logs burying standing directives.

**No invented patterns.** A pattern must name 3+ real rules; a 2-rule overlap is
already a per-rule Redundant/Conflicts note and needs no roll-up. Don't promote a
one-off to look thorough — same discipline as "no invented staleness." If nothing
recurs across 3+ rules, say "no cross-cutting patterns" and move on.

Then proceed. Offer a last chance to re-scope; do not block waiting for input.

### 6. Build the curation UI

Run the bundled script (standard library only, no install):

```bash
python build_curator.py rules.json -o rule-curator.html
```

It injects the data into `curator-template.html` and writes one self-contained
file. The user double-clicks it; decisions persist locally; it exports
`decisions.json` and a markdown summary.

### 7. Curate (human)

Per rule, the human marks **Reviewed**, **Drop**, or **Modify** (with optional
replacement text and notes), then exports `decisions.json`. Keep is the default:
a rule left untouched stays unchanged. "Reviewed" records that the human looked
at it and kept it (so an untouched rule reads as not-yet-examined, not as an
implicit decision). Only Drop and Modify change files.

### 8-9. Apply-plan and apply gate

Read `decisions.json`, compute the exact edits against **current** file contents,
and emit an auditable apply-plan. Then confirm once ("apply these N edits?") and
execute. Per-verdict edits, drift handling, and the plan format: see
[references/apply-plan-format.md](references/apply-plan-format.md).

Where sources are pinned, `meta.commits` makes drift detection a lookup instead
of a diff — but only for files clean at both ends. Per pinned repo,
`git log --oneline <hash>..HEAD -- <sources>` names committed drift and
`git status --porcelain -- <sources>` names uncommitted drift; only a file
absent from **both** is unchanged. Any file dirty now, or belonging to a pin
recorded `dirty`, gets the textual comparison instead — the commit range proves
nothing about content that was never committed. Curation happens on human time
— hours or days — so drift is the normal case, not the edge case.

**If the corpus is not version-controlled, say so before applying.** Dropping a
rule is destructive and unrecoverable without history; a memory entry deleted
from an untracked directory is simply gone. One sentence at the apply gate is
enough ("these sources have no version history — drops are unrecoverable"), and
recommending `git init` on the rule directory afterward is usually the highest-
value follow-up this skill can leave behind: the next audit gets to see what
changed and whether the last pruning held.

## Disciplines (hold these)

**No rubber-stamping.** The default failure is "good rule, keep it." Every rule
gets its honest cost named in `agentImpact`. A rule that restates default
behavior is dead weight; say so even when it sounds wise.

**No invented staleness.** An `auditNote` of "stale" / "superseded" /
"duplicates X" must be tied to actual corpus evidence (the conflicting rule, the
superseding ADR, the duplicated skill). Never guess a problem onto a healthy,
current rule to look thorough. A healthy rule gets no audit note.

## Red flags — stop and recheck

- You gave a rule a verdict without writing its `agentImpact`.
- You wrote an `auditNote` on every rule (manufactured problems).
- You praised a rule's specificity without checking if its list/date/path will rot (Brittle).
- You judged a memory entry's content but not whether its *type* fits (Misfiled).
- You called something stale without naming what supersedes it.
- You wrote "does not exist" into an audit note after only a repo-scoped search.
- You treated a rule's age — or its churn — as an audit note without naming a superseding change or the value that kept rotting.
- You fused "what it does" and "what's wrong with it" into one verdict blob.
- You marked a work-status entry (ship log / phase tracker) as a standing rule and kept it whole, instead of extracting its buried directive and archiving the log.
- You reported the checkpoint as counts only, without checking whether the flagged rules share a cross-cutting pattern (3+ recurrence) the per-rule notes fragment.

## Common mistakes

- **Analyzing rules one at a time.** Cross-rule findings need the whole corpus loaded at once.
- **Skipping the skill/ADR enumeration**, then guessing at duplication.
- **Treating PRDs as rule sources** and flooding the audit with feature requirements.
- **Writing back blind.** Recompute the apply-plan against current files; skip rules whose text drifted since curation.
- **Concluding a cited file is missing from a repo-scoped search.** Trackers and rule sources routinely live above the project root; widen before you write it down.
- **Applying drops to an untracked corpus without saying so.** The human should know a drop is unrecoverable before they approve it, not after.
- **Declaring "no drift" from a commit-range lookup alone.** Uncommitted edits never appear in `git log`; check `git status` too, and textual-compare dirty files.
