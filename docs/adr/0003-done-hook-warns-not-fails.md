# ADR-0003: The story `done` hook warns and never fails `set-status`

- **Status:** Accepted (with the issue-lifecycle spec, 2026-09-10)
- **Date:** 2026-09-10
- **Deciders:** Package maintainer; reviewed by `l3io-arch-review` Mode B
- **Principle(s) in tension:** Core §3 fail loudly vs. never reporting a durable transition as failed

## Context

When `set-status` moves a story to `done`, it resolves the backlog items the story's `resolves:`
field names. The status save happens first and is durable. The hook's own write to the issue
files can still fail — a malformed file, an I/O error.

## Options considered

| Option | Pros | Cons | Standards fit |
|--------|------|------|---------------|
| A. Warn on stderr; `set-status` exits 0 | A durable transition is never reported as failed; callers (dev loop, sprint closure, `pm-sync`) do not retry a transition that succeeded | A missed resolution is invisible until something checks | Matches the existing contract: `set-actual`'s calibration append and `sync-story-doc` never fail their caller |
| B. `set-status` exits non-zero | Loud | Reports an already-durable transition as failed; callers may retry or roll back work that is done | Contradicts the existing contract |

## Decision

Option A. The hook calls non-exiting core functions, catches every exception including
`SystemExit`, and warns on stderr.

## Consequences

- Positive: consistent with the package's other follow-on writes.
- Negative / trade-offs accepted: a missed resolution stays invisible until detected.
- Mitigation: `audit-issues` finding 1c detects it, health-check Check 13 flags it, and doctor
  `triage` repairs it through `resolve-issue`.
