# Progress Mode — forwards to `/l3io-util-doctor stats`

`stats` is the one plan-aware progress view. It renders the same phase → epic → sprint →
story tree from `pm-status.py report` — including the live-view hint, the stale-lock
`clear-lock` remedy, and the dwell-time explanation this mode used to add on its own — and
additionally reports backlog size by severity, last closed sprint/epic, and calibration
state.

Invoke `skill:l3io-util-doctor` with `stats`, passing through any scope argument the user
gave (`active`, `queued`, `everything`). Report its output unchanged; add no second summary.

If `l3io-util-doctor` is not installed, say so in one line and stop — do not re-implement
the tree here. That duplication is what this forwarder removed.
