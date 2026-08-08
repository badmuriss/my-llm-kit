# Rule Curator

A skill that audits the behavioral rules an agent operates under and helps you
keep, drop, or rewrite them.

Agents accumulate rules across many files: global and project `CLAUDE.md`, a
memory system, project docs like `AGENTS.md`, ADRs, conventions. Nobody prunes
them. Rules go stale, contradict each other, duplicate installed skills, or
restate things the model already does by default. Every rule also costs context
tokens each session, and the more rules there are, the less attention each one
gets.

Rule Curator gathers the rules, analyzes each one against the whole set, and
builds a page in your browser where you mark each rule keep, drop, or modify.
It then turns your decisions into a reviewable edit plan and, once you confirm,
applies the edits to the source files.

## What it does

Every rule gets two separate write-ups:

1. A **behavioral impact** statement: what following the rule actually changes
   about the agent's behavior, and what it costs. Every rule gets one.
2. An **audit note**, only when something is wrong, from a fixed set of
   categories: redundant, stale or superseded, misfiled, low-yield ritual, not
   actionable, brittle, or conflicting.

The skill checks the categories that audits usually skip (brittle rules,
misfiled entries), and it does not invent problems on healthy rules to look
thorough.

If your rule files live in git, the audit records the commit it ran against
(`meta.commits` in rules.json, shown in the UI header and included in both
exports). When you come back to your decisions days later, that record shows
exactly which files changed in the meantime. If your rule files are not in git,
the skill says so up front and warns you before applying anything that a
deleted rule cannot be recovered.

## Repo contents

- `SKILL.md` — the workflow, the analysis contract, and the disciplines
- `references/analysis-contract.md` — the full rubric with worked examples
- `references/apply-plan-format.md` — the edit-plan format and per-verdict rules
- `build_curator.py` — standard-library script that builds the self-contained UI
- `curator-template.html` — the UI template (data is injected at build time)
- `evals/` — a synthetic test corpus with planted issues, its answer key, and
  recorded test runs; `evals/make_history.py` rebuilds the corpus with a
  reproducible git history for the version-history test cases (not yet run)
- `docs/specs/` — the design spec

## Install

Clone into your Claude Code skills directory:

```bash
git clone https://github.com/bwdurst/rule-curator.git ~/.claude/skills/rule-curator
```

or copy the folder there manually. Then ask Claude to audit, prune, or clean up
your rules, or run `/rule-curator`.

One thing worth doing first: if your rule files are not under version control,
run `git init` in the directory that holds them (your memory directory, for
example). With history, the audit can pin exact commits, detect edits made
while you were deciding, and revert a bad prune. Without it, a deleted rule is
gone for good.

## Build the curation UI directly

You can also run the build step yourself once you have a `rules.json`:

```bash
python build_curator.py rules.json -o rule-curator.html
```

This injects the data into `curator-template.html` and writes one self-contained
file you can open offline. It uses the standard library only, so there is nothing
to install.

## How it was built

This skill was developed test-first. The `evals/` directory holds a synthetic
rule corpus with planted issues across every audit category, an answer key, and
the recorded baseline (without the skill) and verification (with the skill) runs
on both a strong and a weak model. See `evals/RED-baseline-findings.md` and
`evals/GREEN-verification-findings.md`.
