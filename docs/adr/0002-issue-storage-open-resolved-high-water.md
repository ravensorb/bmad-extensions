# ADR-0002: Issue storage — open file, resolved file, per-epic high-water

- **Status:** Accepted (with the issue-lifecycle spec, 2026-09-10)
- **Date:** 2026-09-10
- **Deciders:** Package maintainer; reviewed by `l3io-arch-review` Mode B and `bmad-review`
- **Principle(s) in tension:** Core §3 design by contract (invariants, no silent key reuse) vs. minimal change to a shared file format

## Context

`state/issues.yaml` is a flat list of deferred findings (`BL-E{nnn}-{nnn}`). The documented
contract said resolved items are removed, but nothing removed them, and removing one by hand
reused its key: allocation was "highest surviving suffix + 1". Every existing reader
(`pm-help`, doctor `stats` and `backlog`, `list-issues`) treats every item in the file as open.

## Options considered

| Option | Pros | Cons | Standards fit |
|--------|------|------|---------------|
| A. Open items stay in `issues.yaml`; resolved items move to `issues-resolved.yaml`; per-epic `next:` high-water | Existing readers become correct unchanged; history preserved; no schema bump | Two files; a crash window between them; dedupe reads both | Strong §3: invariants checkable, keys never reused |
| B. One file; items gain `status: resolved` plus a resolution block | One file | Every reader must learn to filter, and a missed one silently overcounts; the shared hot file grows forever | Weak: correctness depends on every reader |
| C. Delete on resolve; record only in `events.jsonl` | Smallest change | `append_event` is best-effort by design and cannot be a record; dedupe against closed items needs a log scan | Fails §3 |

## Decision

Option A. Allocation is `max(next[epic], highest suffix in either file + 1)`, so keys are never
reused even when items were written by hand. Resolution appends to the resolved file before
removing from the open file; the one resulting intermediate state (a key in both files) is an
`audit-issues` integrity finding that a rerun of `resolve-issue` clears.

## Consequences

- Positive: readers need no change to stop inflating open counts; resolutions are auditable.
- Negative / trade-offs accepted: a crash window between the two writes, detected by audit 1a;
  keys reused before this change cannot be recovered.
- Follow-ups: GitHub sync of BL items will resolve through `resolve-issue`.
