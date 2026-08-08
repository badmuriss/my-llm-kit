# Apply-plan format

Steps 8-9 of the workflow: turn `decisions.json` (exported from the curation UI)
into an auditable plan, then apply it behind one confirmation.

## Contents

- Input: decisions.json
- Per-verdict edits
- Drift and staleness handling
- The apply-plan document
- The apply gate and execution

## Input: decisions.json

The curation UI exports one decision per rule:

```json
{
  "meta": { "title": "...", "exported": "...",
            "commits": [ { "root": "~/.claude", "hash": "abc1234", "branch": "main", "dirty": false } ] },
  "decisions": [
    { "id": "G1", "source": "path:line", "verdict": "drop",
      "original": "...", "modifiedText": "", "notes": "" }
  ]
}
```

`verdict` is `reviewed`, `drop`, `modify`, or `unreviewed`. Keep is the default
outcome: only `drop` and `modify` change files.

## Per-verdict edits

- **reviewed** — no-op. The human examined the rule and kept it. Do not touch the file.
- **unreviewed** — no-op. Kept by default (not examined). Do not touch the file,
  but report the count of unreviewed rules so the human knows what was left
  unexamined.
- **drop** — remove the rule from its source. For a memory entry, this means
  **both** deleting the entry file **and** removing its pointer line in
  `MEMORY.md`. One change set, both halves; a dangling pointer is a broken state.
- **modify** — replace the rule's text with `modifiedText`. If `modifiedText` is
  empty for a modify verdict, flag it and skip rather than guess the rewrite.

Treat any verdict that is not `drop` or `modify` as a no-op keep.

**Orphaned structure.** When dropping a rule empties the structure around it (a
section heading whose last rule you just removed, a now-empty list), remove that
orphaned structure in the same edit. Remove only the orphan your own drop
created; leave unrelated nearby structure alone.

## Drift and staleness handling

Compute every edit against the **current** contents of the source files at apply
time, not against the snapshot captured during curation.

Where `meta.commits` carries pins, resolve them first — per pinned repo,
`git log --oneline <hash>..HEAD -- <sources>` names committed drift and
`git status --porcelain -- <sources>` names uncommitted drift. Only a file
absent from **both** is unchanged; `git log` alone is not enough, because
uncommitted edits never appear in it. Any file dirty now, or belonging to a pin
recorded `dirty: true`, gets the textual `original` comparison below instead —
the commit range proves nothing about content that was never committed. The
textual comparison is also the fallback when pins are absent or a source is
untracked.

- **Drifted rule:** the rule text in the file no longer matches `original`. The
  file changed since curation. Flag it, skip it, do not blind-edit.
- **Stale decision:** the `id` / rule no longer exists in the sources. Flag and
  skip.
- **Missing file:** the source file is gone. Flag and skip.

Skipped items go in the apply-plan so nothing fails silently.

## The apply-plan document

Markdown, one entry per non-keep verdict, exact before/after so a human can
review it as a diff:

```markdown
# Apply plan — <title>

## Edits (N)

### DROP · G1 · CLAUDE.md
- File: CLAUDE.md
- Remove:
  > Never commit directly to main. Every change goes through a PR.

### MODIFY · S3 · CLAUDE.md
- File: CLAUDE.md
- Before:
  > Run `npm run lint` and `npm test` before every commit.
- After:
  > Run `pnpm lint` and `pnpm test` before every commit.

### DROP · M1 · memory
- Delete file: memory/feedback_pr_template.md
- Remove pointer line in memory/MEMORY.md:
  > - [PR description template](feedback_pr_template.md) — ...

## Skipped (M)
- D4 (drifted: file text no longer matches the curated original)

## Sources without history
- memory/ is not version-controlled — the drops above are unrecoverable once applied.

## Not reviewed (K) — kept unchanged
- 12 rules were left unreviewed and remain as-is.
```

Omit the "Sources without history" section when every touched source is
tracked; when present, it must name each untracked source that a drop or modify
touches.

## The apply gate and execution

Present the plan, then ask once: "apply these N edits?" **If any touched source
is untracked, the gate line says so before asking** ("these sources have no
version history — drops are unrecoverable"), and recommending `git init` on the
rule directory afterward is usually the highest-value follow-up. On
confirmation, make the edits exactly as listed. Where the sources live in a git
repo, recommend committing or stashing first so the apply lands as one
reviewable diff. This is a lightweight confirm-then-edit; it does not need a
multi-checkpoint execution framework.

Running unattended, do **not** auto-apply: writing back to source-of-truth rule
files is the one place the skill always stops for a human.
