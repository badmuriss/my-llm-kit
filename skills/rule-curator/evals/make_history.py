#!/usr/bin/env python3
"""Wrap the baseline eval corpus in a deterministic git history.

The checked-in corpus at evals/baseline-corpus/ is plain files (a nested .git
cannot be committed), so the version-history cases H1-H6 in ANSWER-KEY.md need
this script: it copies the corpus into a work directory and fabricates a git
repo around it whose final tracked tree is byte-identical to the corpus, with:

  H1  a superseding commit ("ADR-003: migrate analytics to API v2") that
      postdates the v1 analytics rule, so `git log -S` can name it
  H2  rot churn - the forbidden-words denylist line extended in three separate
      commits (the diffs show the same hardcoded list growing)
  H3  decoy churn - the healthy migration rule reworded in three separate
      commits (same edit count as H2; the diffs show refinement, not rot)
  H4  age decoys - rules untouched since the 2025-06 initial commit
  H5  a dirty working tree - an uncommitted, non-rule prose edit to CLAUDE.md,
      so a corpus pin must record dirty and drift checks must not trust the
      commit range for that file
  H6  an untracked source - memory/ exists on disk but is gitignored, so drops
      there are unrecoverable

Commit hashes are reproducible: author, committer, and dates are fixed, and the
user's git config is ignored. Every intermediate file state is derived from the
final corpus text by exact string replacement, so corpus drift fails loudly
here instead of silently invalidating the history.

    python make_history.py [-o evals/history-corpus] [--force]
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

CORPUS = Path(__file__).resolve().parent / "baseline-corpus"

GIT_ENV = {
    "GIT_AUTHOR_NAME": "Rule Curator Evals",
    "GIT_AUTHOR_EMAIL": "evals@rule-curator.invalid",
    "GIT_COMMITTER_NAME": "Rule Curator Evals",
    "GIT_COMMITTER_EMAIL": "evals@rule-curator.invalid",
    # Isolate from the machine's git config (signing, autocrlf, templates)
    # so the fabricated hashes are identical everywhere.
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}

# Final-state lines in CLAUDE.md that the history rewrites. If the corpus text
# changes, the .replace() below stops matching and the script fails loudly.
DENY_FINAL = ('- Forbidden words in user-facing UI copy: "synergy", "leverage", '
              '"seamless", "robust", "cutting-edge", "delightful".')
DENY_V0 = '- Forbidden words in user-facing UI copy: "synergy", "leverage", "seamless".'
DENY_V1 = '- Forbidden words in user-facing UI copy: "synergy", "leverage", "seamless", "robust".'
DENY_V2 = ('- Forbidden words in user-facing UI copy: "synergy", "leverage", '
           '"seamless", "robust", "cutting-edge".')

MIG_FINAL = ('- Every database migration must be reversible: include a working '
             '`downgrade()` in each Alembic migration.')
MIG_V0 = '- Every database migration must be reversible.'
MIG_V1 = '- Every database migration must be reversible: include a downgrade path.'
MIG_V2 = '- Every database migration must be reversible: include a working `downgrade()`.'

INTRO_FINAL = "Habitsmith is a habit-tracking web app (Next.js + FastAPI + Postgres)."
INTRO_DIRTY = INTRO_FINAL + " Deployed on Fly.io."

GITIGNORE = "# memory/ deliberately has no history (eval case H6)\nmemory/\n"


def fail(message):
    print(f"make_history: error: {message}", file=sys.stderr)
    sys.exit(1)


def git(repo, *args, date=None, capture=False):
    env = dict(os.environ, **GIT_ENV)
    if date:
        env["GIT_AUTHOR_DATE"] = date
        env["GIT_COMMITTER_DATE"] = date
    result = subprocess.run(["git", "-C", str(repo), *args], env=env,
                            capture_output=True, text=True)
    if result.returncode != 0:
        fail(f"git {' '.join(args)} failed:\n{result.stderr.strip()}")
    return result.stdout if capture else None


def claude_md_state(final_text, deny, mig):
    """Derive an earlier CLAUDE.md from the final text by exact replacement."""
    for target, replacement in ((DENY_FINAL, deny), (MIG_FINAL, mig)):
        if final_text.count(target) != 1:
            fail(f"corpus drift: expected exactly one occurrence of:\n  {target}\n"
                 "in baseline-corpus/CLAUDE.md; update make_history.py to match "
                 "the corpus before regenerating history.")
        final_text = final_text.replace(target, replacement)
    return final_text


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build the history-wrapped eval corpus.")
    parser.add_argument("-o", "--output", type=Path,
                        default=Path(__file__).resolve().parent / "history-corpus")
    parser.add_argument("--force", action="store_true",
                        help="delete an existing output directory first")
    args = parser.parse_args(argv)
    out = args.output

    if not CORPUS.is_dir():
        fail(f"baseline corpus not found: {CORPUS}")
    if out.exists():
        if not args.force:
            fail(f"{out} already exists; pass --force to regenerate")
        shutil.rmtree(out)
    out.mkdir(parents=True)

    final_claude = (CORPUS / "CLAUDE.md").read_text(encoding="utf-8")
    adr_dir = out / "docs" / "adr"

    def write(rel, text):
        path = out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="")

    def copy_verbatim(rel):
        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(CORPUS / rel, dest)

    git(out, "init", "--quiet")
    git(out, "symbolic-ref", "HEAD", "refs/heads/main")

    def commit(subject, date):
        git(out, "add", "-A")
        git(out, "commit", "--quiet", "-m", subject, date=date)

    # C1 - initial rules. Denylist and migration rule at their first versions;
    # the v1 analytics rule is already present (H1: it never changes again).
    write(".gitignore", GITIGNORE)
    write("CLAUDE.md", claude_md_state(final_claude, DENY_V0, MIG_V0))
    commit("Project rules for Habitsmith", "2025-06-02T09:00:00+00:00")

    # C2-C3, C5 - rot churn on the denylist line (H2).
    write("CLAUDE.md", claude_md_state(final_claude, DENY_V1, MIG_V0))
    commit("Ban robust in UI copy", "2025-07-15T09:00:00+00:00")
    write("CLAUDE.md", claude_md_state(final_claude, DENY_V2, MIG_V0))
    commit("Ban cutting-edge in UI copy", "2025-08-21T09:00:00+00:00")

    # C4 - ADR-007 lands (party to the planted PR-rule conflict, finding #2).
    copy_verbatim("docs/adr/ADR-007-trunk-based-solo.md")
    commit("ADR-007: trunk-based development while solo", "2025-09-10T09:00:00+00:00")

    write("CLAUDE.md", claude_md_state(final_claude, DENY_FINAL, MIG_V0))
    commit("Ban delightful in UI copy", "2025-10-05T09:00:00+00:00")

    # C6-C7, C9 - decoy churn on the healthy migration rule (H3): same edit
    # count as the denylist, but the diffs show wording refinement, not rot.
    write("CLAUDE.md", claude_md_state(final_claude, DENY_FINAL, MIG_V1))
    commit("Clarify migration rule: require a downgrade path", "2025-10-20T09:00:00+00:00")
    write("CLAUDE.md", claude_md_state(final_claude, DENY_FINAL, MIG_V2))
    commit("Migration rule: require a working downgrade()", "2025-11-14T09:00:00+00:00")

    # C8 - the superseding commit (H1). The v1 rule in CLAUDE.md predates it.
    copy_verbatim("docs/adr/ADR-003-analytics-api-v2.md")
    commit("ADR-003: migrate analytics to API v2", "2026-01-08T09:00:00+00:00")

    # C9 - final wording; the tracked tree now matches the corpus exactly.
    write("CLAUDE.md", final_claude)
    commit("Migration rule: name Alembic explicitly", "2026-01-19T09:00:00+00:00")

    # Self-checks before dirtying anything.
    if git(out, "status", "--porcelain", capture=True).strip():
        fail("tree is not clean after the final commit")
    for rel in ("CLAUDE.md", "docs/adr/ADR-003-analytics-api-v2.md",
                "docs/adr/ADR-007-trunk-based-solo.md"):
        if (out / rel).read_bytes() != (CORPUS / rel).read_bytes():
            fail(f"final {rel} does not match the baseline corpus byte-for-byte")
    superseding = git(out, "log", "--format=%h %s", "-S", "v2/events", capture=True).strip()
    if "\n" in superseding or "ADR-003" not in superseding:
        fail(f"git log -S'v2/events' should find exactly the ADR-003 commit, got: {superseding!r}")
    claude_commits = git(out, "log", "--oneline", "--", "CLAUDE.md", capture=True).strip()
    if len(claude_commits.splitlines()) != 7:
        fail(f"expected 7 commits touching CLAUDE.md, got:\n{claude_commits}")

    # H6 - memory/ exists but is gitignored: no history, drops unrecoverable.
    for entry in sorted((CORPUS / "memory").iterdir()):
        copy_verbatim(Path("memory") / entry.name)

    # H5 - uncommitted, non-rule prose edit: the pin must record dirty and the
    # apply phase must textual-compare CLAUDE.md instead of trusting git log.
    if final_claude.count(INTRO_FINAL) != 1:
        fail("corpus drift: CLAUDE.md intro line changed; update INTRO_FINAL")
    write("CLAUDE.md", final_claude.replace(INTRO_FINAL, INTRO_DIRTY))

    head = git(out, "rev-parse", "--short", "HEAD", capture=True).strip()
    print(f"Wrote {out} (HEAD {head}, branch main, CLAUDE.md dirty, memory/ untracked)")
    print(git(out, "log", "--format=  %h %ad %s", "--date=short", "--reverse",
              capture=True).rstrip())
    print("Audit this directory (not baseline-corpus/) to exercise cases H1-H6.")


if __name__ == "__main__":
    main()
