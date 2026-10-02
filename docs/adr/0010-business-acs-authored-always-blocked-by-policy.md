# ADR-0010: Business acceptance criteria — authored always, blocked by policy

## Status

Accepted — 2026-10-02.

Number allocated through `pm-status.py adr-reserve`, not chosen by hand; see ADR-0005.

## Context

Stories carried technical acceptance criteria and nothing saying what the story was *for*.
Stories now gain a `## Business acceptance criteria` section, above the technical one, with two
parts: `Outcome`, carrying a resolving `Spec:` pointer into the project's specs, and `Non-goals`,
which takes none — a negative scope statement has nothing to resolve against.

The open question was how a project turns the requirement on and off without the criteria ending
up written nowhere.

## Decision

**Authoring is unconditional; blocking is configurable.** The enricher writes business ACs for
every story regardless of policy. Only a story whose resolved policy is `required` **fails** the
gate on them.

If "not required" also meant "not written", the setting would decay into business ACs existing
nowhere — the exact outcome the change exists to prevent. Policy decides whether a missing or
weak section stops a story, never whether the section is produced.

### The setting is a scalar, in `modules.l3io-pm`

`business_ac_required` is a comma-separated scalar, default `"CODE,MIXED"`. Two reasons it is
neither an array nor per-skill:

1. **Merge semantics.** BMad core's resolver merges scalars by override and arrays by
   concatenation — `config_utils.py`'s `_merge_arrays` returns `list(base) + list(override)` for
   a non-keyed array. Verified against the installed core resolver rather than assumed. An array
   could therefore only ever be *widened* by a team overlay and never narrowed: once any layer
   added a work type, no project could turn the requirement off for it.
2. **One home.** A per-skill `customize.toml` setting would let the enriching skill (`l3io-plan`)
   and the gating skill (`l3io-execute`) disagree about the same story.

### Per-story resolution

1. The story is in `{ui_facing_stories}` → `required`.
2. Else its `work_type` is in `business_ac_required` → `required`.
3. Else `advisory`.

### An unrecognised work type halts

A work type in the setting that is not a known type **halts** rather than being dropped. A
silently dropped typo resolves to "advisory" and disables the gate precisely where someone meant
to enable it.

### `TAC_HEADING` must never be renamed

`check_story()` in `spec-align.py` treats any story lacking the exact h2 held in `TAC_HEADING` as
pre-provenance: its `technical` result is `None` and the function moves on. Renaming that
constant makes every story's technical section unrecognisable at once. Under `--story` (the
ready-for-dev gate) that fails loudly. Under `--all` (the epic-closure sweep) it goes **quiet**,
reporting only INFO — and because that branch skips the rest of the story, its business ACs go
unchecked too. It is the single most dangerous edit to that file. Changing the heading is a
migration, not a rename.

### Migration

A story with no business section is **pre-business**: reported as INFO under `--all`, and a
failure only under `--story --business required`. This mirrors the existing pre-provenance rule,
so existing projects do not newly go red.

## Consequences

- Every newly enriched story carries business ACs whatever the policy; a project setting
  `business_ac_required` narrower than the default still gets the text, just without the block.
- Existing stories are not failed retroactively — only at the moment they next pass the
  ready-for-dev gate under a `required` policy.
- Anyone touching `TAC_HEADING`, or the h2 text it matches, must treat it as a migration of every
  consuming project's stories.
- A typo in `business_ac_required` stops work loudly instead of weakening the gate quietly.
