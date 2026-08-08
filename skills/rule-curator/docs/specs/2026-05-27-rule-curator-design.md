# Rule Curator — Design Spec

**Date:** 2026-05-27
**Status:** Approved for build (pending final spec review)
**Skill name (dir):** `rule-curator` · **Human title:** Rule Curator

## Problem

Agents accumulate behavioral rules over time across many sources: a global
`CLAUDE.md`, a per-project `CLAUDE.md`, a memory system (`MEMORY.md` + entries),
and assorted project rule docs (`AGENTS.md`, ADRs, `COORDINATION.md`, primers).
Nobody prunes them. Rules go stale, duplicate each other, duplicate installed
skills, restate default behavior, or impose rituals whose friction exceeds their
value. Every rule is a permanent tax: context tokens spent every session,
instruction-following attention diluted across more directives, and sometimes
execution-time friction.

There is no polished, reusable tool for auditing that rule set and acting on the
findings. Adjacent tools exist (memory-prune commands, AGENTS.md generators,
one-off audit prompts) but none combine corpus-wide critical analysis with an
interactive curation UI and a safe write-back path.

## Goal

A public Claude Code skill that takes an agent's full rule set from idea to
clean: discover the rules, analyze each one honestly against the whole corpus,
let a human curate keep/drop/modify in a self-contained UI, then apply the
approved decisions back to the source files behind an auditable, gated plan.

## Non-goals

- Not agent-agnostic. Claude-first (CLAUDE.md + Claude memory system). Project
  rule docs are read generically, but the memory-system and skill-duplication
  logic are Claude-specific by design.
- Not a rule *generator*. It curates existing rules, it does not author new ones
  (beyond `modify` rewrites the human approves).
- Not a scheduler. Cadence/re-audit automation is explicitly out of scope for v1.
- Not a heavyweight plan executor. Apply is small text edits behind one
  confirmation, not a multi-checkpoint execution pipeline.

## Architecture (Approach A: script for mechanics, agent for judgment)

The skill is a pipeline. Judgment-heavy phases belong to the agent; the one
deterministic, token-wasteful, drift-prone phase (HTML assembly) belongs to a
bundled script.

```
1. Discover   (agent)   detect existing rule sources; enumerate skills + ADRs
   >>> SCOPE GATE (confirm/narrow/expand sources + audit emphasis; default = all + full)
2. Extract    (agent)   parse prose into a normalized rule list -> rules.json
3. Analyze    (agent)   per-rule outputs, judged against the whole corpus
   >>> PRE-CURATE CHECKPOINT (informational: "found N, flagged K"; chance to re-scope)
4. Build UI   (script)  build_curator.py: rules.json + template -> one HTML file
5. Curate     (human)   reviewed/drop/modify in browser (keep=default); export decisions.json
6. Apply-plan (agent)   decisions.json -> auditable markdown apply-plan
   >>> APPLY GATE (single confirmation: "apply these N edits?")
7. Execute    (gated)   on confirmation, make the edits
```

### Why this split

Discovery (which files are rule sources, pulling rules out of prose) and the
impact/audit analysis are exactly the judgment work an LLM should do; a regex
script would produce shallow, wrong results. HTML assembly is pure mechanics:
scripting it makes the output byte-identical every run, costs zero tokens to
re-derive, and removes drift between runs. This is the line writing-skills'
own guidance draws (automate the mechanical, reserve the doc for judgment).

## Directory structure

```
rule-curator/
  SKILL.md                 # workflow + analysis contract (compact) + disciplines
  build_curator.py         # rules.json + template -> self-contained HTML (deterministic)
  curator-template.html    # static UI, no data (today's artifact, de-personalized)
  references/
    analysis-contract.md   # full rubric + audit taxonomy + good/bad examples
    apply-plan-format.md    # exact apply-plan doc shape + per-verdict edit rules
  docs/
    superpowers/specs/      # this design doc lives here
```

`SKILL.md` stays lean (it loads on trigger, so token budget matters). The full
analysis rubric with worked examples and the apply-plan format move to
`references/` because each is heavy reference (100+ lines) and is only needed at
the moment of use.

## Phase detail

### 1. Discover (agent)

**What counts as a rule.** A rule is a *standing directive that shapes the
agent's behavior across tasks* (do / never / prefer / always / use X not Y).
This is the inclusion test for discovery, not a hardcoded file list. A *bounded
deliverable spec* (a PRD or feature spec defining one unit of work) is not a
rule and is excluded by default.

Auto-detect the Claude-first sources that exist and contain standing directives:
- Global `~/.claude/CLAUDE.md`
- Project `CLAUDE.md` (and nested ones)
- Memory dir: `MEMORY.md` plus every entry it points to
- Common project rule docs: `AGENTS.md`, `COORDINATION.md`, primers, conventions
- **ADR-type decision records, however named** (`docs/adr/*`, `docs/decisions/*`,
  RFCs, design-decision docs). Decisions routinely encode durable constraints
  that function as rules. Extract only the **binding constraint** from an ADR,
  not the whole narrative (context / consequences sections are not rules).

**Excluded by default:** PRDs and feature specs. They are bounded deliverable
definitions, not standing rules; sweeping them in floods the audit with
requirements miscast as rules and risks recommending edits to product specs. A
user may add them for a given run via the scope gate.

Also enumerate installed skills (names + descriptions) and the ADRs found above,
so "duplicates a skill / duplicates an ADR" findings in Analyze are grounded in
reality, not guessed. The user may name extra sources at the scope gate. If
nothing is found, report and stop; never fabricate a rule set.

### 2. Extract (agent)

Normalize each discovered rule into: `id`, `category`, `title`, `summary`,
`source` (file + line where determinable). Categories group by source/kind
(e.g. global-claudemd, global-memory, project-hard, project-adr, project-coord,
project-domain, project-style). Output is `rules.json` matching the schema the
template consumes.

### 3. Analyze (agent, against the whole corpus)

Two outputs per rule, deliberately asymmetric and explicitly separated so the
human gets facts and critique as distinct things:

**Behavioral impact — always present.** Neutral-diagnostic, first-person. What
following this rule actually changes about the agent's behavior, plus its side
effect / cost. Must state plainly when a rule merely restates default behavior
(does nothing distinctive). This is the finding the human cannot see for
themselves.

**Audit note — only when something is wrong.** The opinionated cost/health
judgment, drawn from a fixed taxonomy so it is consistent across runs rather
than freeform:

- **Redundant** — duplicates another rule, or an installed skill / ADR
- **Stale / superseded** — references changed files or decisions; a newer rule overrides it
- **Misfiled** — wrong home (a template stored as "feedback"; a project rule in global config)
- **Low-yield ritual** — friction exceeds value
- **Not actionable** — too vague to change behavior
- **Brittle** — will rot (hardcoded word lists, dates, paths)
- **Conflicts** — contradicts another rule

Absent audit note = the rule is healthy. Forcing a note onto every rule
manufactures fake problems, so it stays conditional.

**Disciplines (bulletproofed against rationalization):**
- **No rubber-stamping.** The default LLM failure is "good rule, keep it." Every
  rule gets its honest cost named; the skill forbids reflexive approval.
- **No invented staleness.** An audit note claiming "superseded" / "duplicates
  X" must be verified against the actual corpus, never guessed. Analysis runs
  against the whole gathered set plus the skills/ADR enumeration precisely
  because redundancy and conflict are only visible across rules.

### 4. Build UI (script)

`build_curator.py` takes `rules.json` and `curator-template.html` and writes one
self-contained HTML file with the data injected inline. The user double-clicks
to open offline; decisions persist in localStorage; exports JSON and markdown.
The injection safe-escapes content so a rule containing `</script>` cannot break
the page.

### 5. Curate (human)

Per rule, mark Reviewed, Drop, or Modify (with optional replacement text and
notes), then export `decisions.json`. Keep is the default: a rule left untouched
stays unchanged. "Reviewed" records an explicit looked-at-and-kept, so an
untouched rule reads as not-yet-examined rather than an implicit decision. Only
Drop and Modify change files.

### 6. Apply-plan (agent)

Read `decisions.json` and produce an auditable markdown apply-plan: for every
drop/modify verdict, the file, the exact before, and the exact after.

Per-verdict edits:
- `reviewed` / `unreviewed` → no-op (kept). Report the unreviewed count so the
  human knows what was left unexamined.
- `drop` → remove the rule. For a memory entry this means delete the entry file
  *and* remove its pointer line in `MEMORY.md` (both halves, one change set).
- `modify` → replace the rule text with the approved replacement.

### 7. Execute (gated)

Offer to apply the plan behind a single confirmation ("apply these N edits?").
On confirmation, make the edits. Recommend committing first where a git repo
exists, so the apply lands as a reviewable diff. This is a lightweight
confirm-then-edit, not the heavyweight executing-plans path.

## User interaction gates

Two purposeful gates plus one soft checkpoint. Gates are a tax too, so the skill
adds only the ones that change the outcome, and every gate is confirm-with-defaults
so the skill still runs when no human is steering it (e.g. inside an autonomous
agent).

- **Scope gate (after Discover, before Analyze) — required, defaults to proceed.**
  Present the discovered sources and a rough rule count, then offer to confirm,
  narrow, or expand the source set, plus an optional emphasis ("general health
  audit" vs "hunting something specific: duplicates / staleness / bloat"). This
  is the most valuable gate because Analyze is the expensive phase; narrowing
  here avoids analyzing out-of-scope rules and sharpens output. It also serves
  as the "revise / expand" checkpoint. **Default if the user just says go:** all
  discovered sources, full audit.

- **Pre-curate checkpoint (after Analyze, before Build UI) — informational, not
  blocking.** Report "analyzed N rules, flagged K (breakdown by audit category)"
  and proceed to build. Offers a last chance to re-scope if the result is
  obviously off, but does not stop the flow waiting for input.

- **Apply gate (before Execute) — required confirmation.** Single confirmation
  ("apply these N edits?"); recommend committing first where a git repo exists.

**Non-interactive degradation:** when run without a human in the loop, the scope
gate takes its default (all sources, full audit) and the apply gate is the one
place the skill stops, since writing back to source-of-truth files should never
happen unattended.

## Error handling / edge cases

- **Empty discovery:** no sources or no rules found → report and stop.
- **Injection hazard:** rule text containing `</script>` → safe-escaped on inject.
- **Drift guard:** the apply-plan is computed against *current* file contents at
  apply time. If a source changed since curation (the rule text no longer
  matches), flag that rule and skip rather than blind-edit.
- **Stale decisions:** decision IDs that no longer exist in the sources → flag
  and skip.

## Testing (writing-skills TDD: RED-GREEN-REFACTOR)

- **RED:** give a fresh agent a sample rule set with planted issues (a duplicate,
  a stale reference, a too-vague rule, and a "good"-looking rubber-stamp-bait
  rule) and no skill. Record what it misses and where it rubber-stamps.
- **GREEN:** with the skill present, verify it catches each planted issue, keeps
  the impact statement neutral, fires the right audit-note category, and refuses
  to rubber-stamp.
- **REFACTOR:** close whatever rationalizations surface; re-test until solid.

At least three distinct evaluation scenarios (not one rule set), e.g. a global
CLAUDE.md with duplication, a memory dir with a misfiled/stale entry, and a
project with an ADR-derived rule that conflicts with a CLAUDE.md rule. Test
across the models the skill will realistically run under (Haiku / Sonnet / Opus):
Haiku reveals whether guidance is sufficient, Opus whether it over-explains.

## Authoring conformance (Anthropic skill best-practices)

Build constraints carried over from Anthropic's official skill-authoring guide:

- **`build_curator.py` is standard-library only.** No third-party packages, so it
  runs in any skill environment (the Anthropic API environment has no network or
  package install). Handle errors in the script rather than punting; justify any
  constants.
- **Ship the template de-personalized.** `curator-template.html` carries empty or
  clearly-marked example bootstrap data, never a real rule set, and no
  hardcoded generation date (avoid time-sensitive content).
- **Forward-slash paths only** in SKILL.md, references, and scripts, even though
  authoring happens on Windows.
- **`references/analysis-contract.md` opens with a table of contents** (reference
  files over ~100 lines need one so partial reads still see full scope).
- **References stay one level deep** from SKILL.md; no reference file links to
  another reference file.
- **Naming:** `name` frontmatter = `rule-curator` (lowercase, hyphenated, no
  spaces), matching the directory. Claude Code derives the `/slash` command from
  the `name` field, so a space breaks invocation (`/Rule Curator` fails). The
  Anthropic doc's space-containing examples ("PDF Processing") are misleading for
  Claude Code use. Human-readable "Rule Curator" stays as the H1 and UI title.

## Build location

Standalone git repo at `c:\Projects\rule-curator\`, laid out as the skill dir
above so it is drop-in for a marketplace/plugin and can be pushed public when
ready.
