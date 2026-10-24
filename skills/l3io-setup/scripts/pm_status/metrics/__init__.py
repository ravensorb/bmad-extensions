"""pm_status.metrics -- the measurement layer: calibration, estimates, spend, reporting.

Everything that MEASURES rather than changes state. It sits above `nodes` and below the
issue store, the status verbs and the plan operations: it reads and writes node files
through `nodes`, and nothing below it reads anything here.

A DIRECTORY rather than a single module, because `calibration` alone is ~1,280 lines and
the package's per-file budget is 1,500 — enforced since 2026-10-23 by `check:docs` check 12,
which until then was a number stated here and in the split plan and checked nowhere.
(`issues` is a directory for the same reason; this file used to claim to be the only one.)
The seven modules are a strict layering, and the order below is the import order:

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

This file imports the seven submodules and re-exports NOTHING OF THEIRS. That is
deliberate: a name re-exported here would sit beside `metrics.<mod>.<name>` as a second
binding of the same function, and `mock.patch` on one would not reach the other.
`__main__.py` re-exports what the facade needs, from the defining module, and leaves the
three patch targets out. The one name imported by name is `core.node_args` (a CLI helper
one level BELOW this bucket, so it cannot collide with a `metrics.<mod>.<name>` binding);
everything `register` wires is reached as `<submodule>.<name>`.
"""
from __future__ import annotations

import argparse

from ..core import node_args
from . import (  # noqa: F401 -- submodule imports, so `metrics.<mod>` resolves on the package
    actuals_usage,
    calibration,
    estimates,
    events,
    rates,
    report,
    spend,
)


# --------------------------------------------------------------------------- #
# CLI registration -- this bucket's nine verbs (design §3.2; the contract and the reason
# are in core's own register section).
#
# Written against the SUBMODULE OBJECTS (`actuals_usage.cmd_set_actual`, not a
# `from .actuals_usage import cmd_set_actual` at the top of this file) for the reason this
# module's docstring gives: a name re-exported here would sit beside `metrics.<mod>.<name>`
# as a second binding, and `mock.patch` on one would not reach the other. `register` is a
# function this file DEFINES, so it adds no such second binding.
# --------------------------------------------------------------------------- #
def register(sub):
    a = sub.add_parser("set-actual", help="write a validated actual block")
    a.add_argument("--state-root", required=True, help="path to {implementation_artifacts}/state")
    a.add_argument("--node", required=True, choices=["story", "sprint", "epic"])
    node_args(a)
    a.add_argument("--block", choices=["actual", "orchestration"], default="actual",
                   help="which metric block to write (orchestration: sprint/epic only)")
    a.add_argument("--elapsed-hours", dest="elapsed_hours")
    a.add_argument("--man-hours", dest="man_hours")
    a.add_argument("--hitl-hours", dest="hitl_hours",
                   help="human attention actually spent supervising (hours)")
    a.add_argument("--tokens-input", dest="tokens_input")
    a.add_argument("--tokens-output", dest="tokens_output")
    a.add_argument("--tokens-cache-write", dest="tokens_cache_write")
    a.add_argument("--tokens-cache-read", dest="tokens_cache_read")
    a.add_argument("--tokens-na", dest="tokens_na", action="store_true",
                   help="record tokens/cost as N/A (runtime=other only)")
    a.add_argument("--model", default="", help="model id that priced these tokens")
    a.add_argument("--token-rates", dest="token_rates", default="",
                   help="JSON object of per-model rate overrides")
    a.add_argument("--cost", default=None, help=argparse.SUPPRESS)
    a.add_argument("--runtime", choices=["claude", "codex", "copilot", "other"], default="other")
    a.add_argument("--flock", action="store_true", help="acquire exclusive flock before write")
    a.add_argument("--no-calibrate", dest="no_calibrate", action="store_true",
                   help="skip calibration sampling (backfills, replays)")
    a.add_argument("--no-events", dest="no_events", action="store_true",
                   help="skip the events.jsonl append for this call")
    a.add_argument("--session-id", dest="session_id", default=None,
                   help="recorded in the event payload; null when omitted")
    a.set_defaults(func=actuals_usage.cmd_set_actual)

    ia = sub.add_parser("import-actual",
                        help="record an actual observed elsewhere (migration); runtime=other, "
                             "tokens=N/A and no calibration sample are FIXED, not optional")
    ia.add_argument("--state-root", required=True)
    ia.add_argument("--node", required=True, choices=["story", "sprint", "epic"])
    ia.add_argument("--story")
    ia.add_argument("--epic")
    ia.add_argument("--sprint")
    ia.add_argument("--elapsed-hours", dest="elapsed_hours")
    ia.add_argument("--man-hours", dest="man_hours")
    ia.add_argument("--hitl-hours", dest="hitl_hours")
    ia.add_argument("--flock", action="store_true")
    ia.add_argument("--no-events", dest="no_events", action="store_true")
    ia.add_argument("--session-id", dest="session_id", default=None)
    ia.set_defaults(func=actuals_usage.cmd_import_actual)

    rp = sub.add_parser("report", help="plan-aware progress report (read-only unless --out)")
    rp.add_argument("--state-root", required=True)
    rp.add_argument("--plan", default="", help="path to plan-output-meta.yaml")
    rp.add_argument("--format", choices=["tree", "json", "md"], default="tree")
    rp.add_argument("--out", default="", help="write to this file instead of stdout")
    rp.add_argument("--all", action="store_true",
                    help="show every status folder (sugar for --status planned,active,archived)")
    rp.add_argument("--status", default="",
                    help="comma list of state folders to display: planned, active, archived "
                         "(default: planned,active). Counting is unaffected — phase "
                         "denominators always see the whole tree")
    rp.add_argument("--watch", type=int, default=0, metavar="SECS",
                    help="re-render on an interval (tree only in practice)")
    rp.add_argument("--stall-minutes", dest="stall_minutes", type=float,
                    default=events.DEFAULT_STALL_MINUTES,
                    help="flag dispatches open longer than this (default 15)")
    rp.set_defaults(func=report.cmd_report)

    dp = sub.add_parser("dispatch", help="record a subagent dispatch open/close")
    dp.add_argument("--state-root", required=True)
    dp.add_argument("--event", required=True, choices=["open", "close"])
    dp.add_argument("--agent", required=True)
    dp.add_argument("--epic", default="")
    dp.add_argument("--sprint", default="")
    dp.add_argument("--story", default="")
    dp.add_argument("--session-id", dest="session_id", default=None)
    dp.set_defaults(func=events.cmd_dispatch)

    up = sub.add_parser("usage", help="sum a session transcript's token usage, by class")
    up.add_argument("transcript", nargs="*",
                    help="transcript .jsonl file(s) or directory(ies); omit to resolve this "
                         "session's own transcript from $" + actuals_usage.CLAUDE_SESSION_ENV)
    up.add_argument("--claude-session", dest="claude_session", default="",
                    help="the Claude session id the transcript must belong to (NOT the l3io "
                         "run --session-id); defaults to $" + actuals_usage.CLAUDE_SESSION_ENV)
    up.add_argument("--state-root", default="", help="state root, to read events.jsonl")
    up.add_argument("--agent", default="", help="scope to this agent's dispatch bracket")
    up.add_argument("--epic", default="", help="scope to this epic")
    up.add_argument("--sprint", default="", help="scope to this sprint")
    up.add_argument("--story", default="", help="scope to this story")
    up.add_argument("--since", default="", help="ISO timestamp lower bound")
    up.add_argument("--until", default="", help="ISO timestamp upper bound")
    up.add_argument("--allow-unidentified", action="store_true",
                    help="sum a file that cannot be confirmed as this session's transcript")
    up.add_argument("--model", default="", help="also price the total at this model's rates")
    up.add_argument("--token-rates", dest="token_rates", default="",
                    help="JSON overrides for the rate table")
    up.add_argument("--format", choices=["text", "json"], default="text")
    up.set_defaults(func=actuals_usage.cmd_usage)

    cal = sub.add_parser("calibration", help="inspect the calibration file")
    cal.add_argument("action", choices=["show", "migrate-metrics", "redrive"])
    cal.add_argument("--state-root", required=True)
    cal.add_argument("--format", choices=["text", "json"], default="text")
    cal.set_defaults(func=calibration.cmd_calibration)

    es = sub.add_parser("estimate-story", help="compute and write a story estimate")
    es.add_argument("--state-root", required=True)
    es.add_argument("--story", required=True)
    es.add_argument("--classification", required=True, choices=list(calibration.CLASSIFICATIONS))
    es.add_argument("--confidence", choices=["low", "medium", "high"])
    es.add_argument("--model", default="",
                    help="model id to price the derived cost; falls back to DEFAULT_ESTIMATE_MODEL")
    es.add_argument("--token-rates", dest="token_rates", default="",
                    help="JSON object of per-model rate overrides")
    es.set_defaults(func=estimates.cmd_estimate_story)

    er = sub.add_parser("estimate-rollup", help="roll child estimates up to a sprint or epic")
    er.add_argument("--state-root", required=True)
    er.add_argument("--epic", required=True)
    er.add_argument("--sprint", default="")
    er.add_argument("--model", default="",
                    help="model id to price the derived cost; falls back to DEFAULT_ESTIMATE_MODEL")
    er.add_argument("--token-rates", dest="token_rates", default="",
                    help="JSON object of per-model rate overrides")
    er.set_defaults(func=estimates.cmd_estimate_rollup)

    rt = sub.add_parser("rates", help="print the effective token rate table (read-only)")
    rt.add_argument("--model", default="")
    rt.add_argument("--token-rates", dest="token_rates", default="",
                    help="JSON object of per-model rate overrides")
    rt.set_defaults(func=rates.cmd_rates)
