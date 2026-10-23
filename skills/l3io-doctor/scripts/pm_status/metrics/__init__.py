"""pm_status.metrics -- the measurement layer: calibration, estimates, spend, reporting.

Everything that MEASURES rather than changes state. It sits above `nodes` and below the
issue store, the status verbs and the plan operations: it reads and writes node files
through `nodes`, and nothing below it reads anything here.

The one bucket in this package that is a DIRECTORY rather than a single module, because
`calibration` alone is ~1,280 lines and the package's per-file budget is 1,500. The seven
modules are a strict layering, and the order below is the import order:

    events, rates     leaves -- the event log's readers; token classes and pricing
    calibration       reads both (blocked hours exclude a metric; fresh tokens band it)
    estimates         applies calibration's ratios to rates' prices
    spend             a leaf of its own -- attribution of actuals to the three buckets
    report            the progress model: reads events for dwell, spend for attribution
    actuals_usage     writes actuals, prices through rates, appends through calibration

There is no edge in the other direction anywhere, so a cycle between two of these files is
a design error, not a plumbing problem to route around with a deferred import.

THE EVENT-LOG WRITER IS NOT HERE. `append_event`, `events_path` and `_event_keys` are in
`core`: every status write appends, including the node layer below this one, so the writer
is a primitive. `metrics.events` holds the READERS only. Do not pull the writer up.

This file imports the seven submodules and re-exports NOTHING. That is deliberate: a name
re-exported here would sit beside `metrics.<mod>.<name>` as a second binding of the same
function, and `mock.patch` on one would not reach the other. `__main__.py` re-exports what
the facade needs, from the defining module, and leaves the three patch targets out.
"""
from __future__ import annotations

from . import (  # noqa: F401 -- submodule imports, so `metrics.<mod>` resolves on the package
    actuals_usage,
    calibration,
    estimates,
    events,
    rates,
    report,
    spend,
)
