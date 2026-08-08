# ADR-007: Trunk-based development during the solo phase

Status: Accepted

## Context

Habitsmith is built by a single engineer right now. Mandatory PR review with one
approver is impossible with a team of one and just blocks the only committer.

## Decision

During the solo build phase, commit directly to `main` using fast-forward merges
from short-lived local branches. PR review is waived until the team grows past
one engineer, at which point this ADR is revisited.

## Consequences

CI still runs on every push to `main`. The branch-protection rule requiring an
approval is disabled for the solo phase.
