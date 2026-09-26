# Structured issue `source` — design

**Date:** 2026-09-26
**Status:** approved design, not yet planned
**Prompted by:** the four l3io-util-doctor defects fixed in `eb448c8`, `7492cfb`, `2bbe2c3`, `0e31428`

## 1. Why

`append-issue --source` takes a free-text string and stores it verbatim:

```python
item["source"] = args.source          # pm-status.py:5774
```

`--source` is `required=True` and its help text says "review phase + finding ID". That
convention is real — every call site in this package follows it — but **it is enforced
nowhere**, and the field it produces is the only link an issue has back to the artifact
that raised it.

**The cost is a reader patchwork.** `audit-backlog.py` now carries five regexes over this
one field, with mixed `.search`/`.match` and mixed anchors, each added when someone met a
shape that would not parse. Every one of the defects fixed this week was one of those
regexes being subtly wrong about a shape:

| Fixed in | The regex was wrong about |
|---|---|
| `7492cfb` (1) | `closure review (E001-S02)` — two-part sprint key, no `code-review` literal |
| `7492cfb` (2) | `E004-S03-001 development` — `$` anchor rejected the trailing word |
| `7492cfb` (3) | the lookup matched filenames where its sibling searched bodies |

**Measured on a real 517-item backlog:** over 100 distinct source shapes, and after all
three fixes **468 of 517 remain untraceable**. 49 is that project's ceiling.

**The package's own writer already strains the convention.**
`skills/_shared/steps/sprint/step-03-dev-loop.md:265` emits:

```
--source "code-review ({story_key}) — unresolved after {max_fix_iterations} fix iterations"
```

| Source | `PHASE_RE` |
|---|---|
| `code-review (E001-S01-005)` | MATCH |
| `code-review (E001-S01-005) — unresolved after 3 fix iterations` | **no** |

It resolves only because `REVIEW_RE` is checked earlier and uses `.search` rather than
`.match`. A writer in this repo produces a string its own primary reader rejects, and it
works by accident of ordering. That is the whole problem in one line: **over 100 free-text
shapes is not a regex problem, and adding a sixth regex is not the fix.**

## 2. What exists today

| | |
|---|---|
| Written by | `cmd_append_issue`, `pm-status.py:5774`, verbatim, unvalidated |
| Shapes in this package | 7 distinct, all `{phase} ({ref})` or that plus a trailing clause |
| Read by | `audit-backlog.py:151` (`pointer_for`), `:221` (`CODE_MARKER_RE`) |
| Also read by | `_content_matches`, `pm-status.py:5642` |

**`_content_matches` is the binding constraint.** Duplicate detection matches on all four
of normalised title + epic + sprint + **exact `source` string**, deliberately: the docstring
says over-matching loses a real finding and losing data is the worse failure. So the raw
string must keep being stored, byte for byte, or a re-run of the same story re-defers a
finding it should have recognised.

That rules out replacing `source`. Whatever we add must be **additive**.

## 3. Design

Two new flags on `append-issue`, as an **alternative** to `--source`, never alongside it:

```
--source-phase PHASE     # [A-Za-z][\w-]*  e.g. code-review, arch-gate, epic-redteam
--source-ref REF         # no parentheses  e.g. E001-S01-005, F-3, src/app.ts:42
--source-note NOTE       # optional free text, e.g. "unresolved after 3 fix iterations"
```

**`source` is derived from them, not passed beside them:**

```
source = f"{phase} ({ref})"                       # note absent
source = f"{phase} ({ref}) — {note}"              # note present
```

One source of truth per call. A caller cannot produce a structured pair that disagrees with
the string, because it does not write the string.

**Storage — additive, absence is meaningful:**

```yaml
- key: 'BL-E001-003'
  source: 'code-review (E001-S01-005) — unresolved after 3 fix iterations'   # unchanged
  source_phase: 'code-review'      # present only when written structurally
  source_ref: 'E001-S01-005'       # present only when written structurally
```

No schema version bump. An item without `source_phase` is a legacy item, parsed as today —
the same idiom as `origin` on inferred state nodes, and consistent with the standing "no
unapproved version bumps" rule.

**Validation, at the write boundary:**

- `--source-phase` must match `^[A-Za-z][\w-]*$`
- `--source-ref` must be non-empty and contain no `(` or `)`
- `--source` and `--source-phase` are mutually exclusive; exactly one is required
- `--source-note` requires `--source-phase`

These guarantee the derived `source` parses under `PHASE_RE`, so the structured path can
never produce a string the legacy reader chokes on.

## 4. The read path

`pointer_for` gains one branch **before** the existing five:

```
if item has source_phase:
    resolve (source_phase, source_ref) directly — no parsing
else:
    the existing regex chain, unchanged
```

**The regex chain is not deleted.** It is the only thing that reads the 468 legacy items,
and it stays until a project has no pre-structured items left — which for the reporting
project is never, since 76 of them point at artifacts that were never written.

## 5. Migration

**There is none, deliberately.** Existing items keep their `source` string and keep being
parsed. Nothing is rewritten.

This is stop-the-bleeding, not repair. Backfilling `source_phase` on legacy items would
mean running the same regex patchwork whose unreliability is the reason for this change,
then freezing its guesses into a field that reads as authoritative. A wrong `source_ref`
is worse than an absent one: absent routes to the fallback, wrong short-circuits it.

## 6. Testing

| What | Where |
|---|---|
| flag validation and mutual exclusion | `skills/_shared/tests/test-pm-status.py` |
| derived `source` string, both with and without a note | same |
| `source_phase`/`source_ref` absent unless written structurally | same |
| **dedup still matches a structured re-run** | same — the `_content_matches` constraint |
| `pointer_for` prefers the structured fields | `skills/l3io-util-doctor/scripts/tests/test-audit-backlog.py` |
| a legacy item still resolves through the regex chain | same |

Two that exist because of what went wrong this week:

- **A structurally-written item must never reach the regex chain.** Assert the fallback is
  not consulted, not merely that the answer is right — the answer can be right for the
  wrong reason.
- **Every derived `source` must parse under `PHASE_RE`.** Property-style over the validator's
  accepted inputs. This is the invariant the validation exists to buy, and the reason
  `step-03-dev-loop.md`'s string was a latent defect.

Both get a mutation check: break the preference, break the validator, confirm the test fails.

## 7. What this does not do

- **It does not fix the 468.** Nothing does; 76 of them have no artifact to point at.
- **It does not remove a regex.** The chain stays for legacy items.
- **It does not stop free text.** `--source` remains accepted, so a caller can still write
  an unparseable string. Making it non-required, or removing it, is a breaking change and a
  separate decision.

## 8. Scope

Four tasks, roughly:

1. `append-issue` flags, validation, derivation, storage — plus tests
2. `pointer_for` structured branch and fallback ordering — plus tests
3. The 7 call sites in `skills/_shared/steps/**` converted to structured flags
4. Docs: the issue schema in `status-files.md`, `CLAUDE.md`'s state-files section, and the
   `--source` guidance wherever it appears

Task 3 is where the `step-03-dev-loop.md` string gets fixed properly: phase `code-review`,
ref the story key, note the fix-iteration clause.

## 9. Out of scope

- Backfilling legacy items (§5).
- Making `--source` optional or removing it (§7) — breaking, needs its own decision.
- The closure-kind alias table and the `sprint-02 closure adversarial (CL-A1)` prefix
  variant: measured as low value on the reporting fixture, because the artifacts those
  sources name were largely never written.
