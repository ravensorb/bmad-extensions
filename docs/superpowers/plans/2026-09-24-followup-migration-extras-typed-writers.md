# Follow-up: typed writers for migration extras (`depends_on`, `estimate`, `actual`)

**Date:** 2026-09-24
**Tracking:** The `WARN <kind> <key>: skipping <field>=<value>` lines the
migration engine now prints when the reader sees a field pm-status.py cannot
yet write typed. Wired in the `feat(l3io-util): extras carry-through`
commit; this file is what those WARN lines point to.

## Background

The migration engine now consumes the `extras` field on every record. Scalar
fields (`goal`, `superseded_by`) land on disk via `pm-status.py set-field`, so a
migration preserves them. Three fields do not have a typed writer yet and are
currently WARNed instead:

- **`depends_on`** — a list of story/backlog keys. `set-field --value` takes a
  single string; storing a list as a stringified `"[E001-S01-002]"` would be
  worse than not writing it because a later reader would treat it as a scalar.
- **`estimate`** — a mapping. `set-estimate` exists but requires per-field
  flags (`--man-hours 5 --tokens-k 40 ...`); it does not accept a whole block.
  Wiring the engine to translate a source estimate mapping into that flag set
  is straightforward but not the shape today's `_apply_extras` supports.
- **`actual`** — the same shape problem as `estimate`, plus a harder one: my
  `set-actual` requires `--runtime` and, under `runtime=claude`, rejects
  anything short of the full four-class tokens breakout. A migration import
  cannot invent a runtime or a token split for legacy data, so this needs
  either a runtime=other pathway or a permissive migration mode on set-actual.

## What would clear the debt

Three focused pieces, roughly in order of value / complexity:

### 1. `set-field` grows a `--json-value` mode for list values

Or a sibling verb — `set-depends-on --add KEY [--add KEY ...]` — that appends
to the node's `depends_on:` list under the epic write lock. Either shape lets
`_apply_extras` write `depends_on` typed. The sibling-verb option is safer
because it stays list-shaped end to end.

### 2. `_apply_extras` translates an `estimate` mapping into `set-estimate` flags

The mapping is already the exact shape `set-estimate` writes; the engine can
walk the keys and emit `--man-hours 5 --tokens-k-min 40 --tokens-k-max 40` etc.
Story vs. sprint/epic ranges are a translation layer.

### 3. Migration-mode `set-actual` (or `import-actual`)

Two options:

- **`set-actual --runtime other --tokens-na`** on a per-field basis, so a
  legacy actual with no tokens data lands without pretending to have Claude
  provenance. Requires the caller to explicitly pass `--tokens-na`.
- A new verb `import-actual` that mirrors `import-node`'s
  cmd_set_actual-with-one-swap shape, whose whole purpose is "the actual was
  observed elsewhere, take it verbatim, do NOT derive a calibration sample."

Option 2 is cleaner but bigger; option 1 works today.

## When this is done

1. Implement the missing writers per the three pieces above, in
   `skills/_shared/pm-status.py` and its `tests/`.
2. Extend `_apply_extras` in `migrate-engine.py` to dispatch each field to the
   new typed writer instead of WARNing.
3. Update the test suite: the WARN-focused tests convert to landed-on-disk
   assertions.
4. Remove this follow-up file.
5. Confirm `npm run test:scripts` and `uv run test-engine.py` still pass.
