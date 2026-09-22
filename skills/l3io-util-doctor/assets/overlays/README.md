# Overlays — empty by design (Phase 3)

This directory is where `l3io-util-doctor`'s `overlay` mode (`steps/overlay.md`) looks for
customization TOML this package ships for BMad core skills — `bmad-build`, `bmad-review`, and
the story skills. It is empty on purpose: this task (Phase 1/2, "scaffold the overlay owner")
creates the mode and its contract; the overlay **content** is Phase 3.

## What lands here, once Phase 3 ships it

Per `docs/superpowers/specs/2026-09-20-l3io-customization-layer-design.md` §5 (Phase 3):

- `review_layers` append, `id = "l3io-spec-alignment"` — runs `spec-align.py check-pointers`
  against the diff.
- `[[workflow.lenses]]` entries exposing `l3io-sec-redteam`'s threat lenses and
  `l3io-arch-review`'s standards.
- `persistent_facts` with `file:` globs — story technical ACs and `spec-index.md` as run facts.
- `implementation_handoff` override dispatching the l3io dev agent with `Files in scope` and
  read-scope discipline.
- `on_complete` writing back through `pm-status.py set-status`, replacing the flat-file write.

Each overlay is named `<skill>.toml` (e.g. `bmad-build.toml`), using the root key
(`[agent]` or `[workflow]`) that skill's own `customize.toml` requires — see root `CLAUDE.md`'s
Skill Authoring Conventions table.

## The one rule that does not change in Phase 3

**Nothing in this directory is ever written to `{project-root}/_bmad/custom/` by this
package.** BMad Builder is explicit: *"There is no supported pattern for modules to write into
`_bmad/custom/`"* — that space belongs to the end user. `overlay diff` renders a file from here
to a staging path and hands the user one `cp` command; `overlay verify` checks whether they ran
it. If Phase 3 ever needs to change that, it is a decision recorded in an ADR, not a quiet
addition to a script.
