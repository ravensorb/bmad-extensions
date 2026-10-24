"""pm_status.issues -- the deferred-issue lifecycle, and the ADR number allocator.

`state/issues.yaml` (open) and `state/issues-resolved.yaml` (resolved), every verb that
changes them, and the integrity audit over them. Spec:
docs/superpowers/specs/2026-09-10-issue-lifecycle-design.md; ADR-0002.

It sits ABOVE `nodes` (it loads and saves story nodes when promoting) and BELOW the status
verbs and the plan operations, which are its consumers. `promote` also reaches UP into
`metrics` for the estimate it writes onto a promoted story -- `metrics` sits between
`nodes` and `issues`, which is what keeps that edge one-way.

A directory rather than one module because the bucket is ~1,970 lines and the package's
per-file budget is 1,500 (check:docs check 12). The four modules are a strict layering,
and the order below is the import order:

    adr        standalone -- the ADR register allocator; `audit` reads it for finding 1k
    store      IssueStore, the schema constants, append / resolve / update
    promote    promote-issue, schedule-issue, the story-key allocator
    audit      audit-issues, repair-issue, the legacy normalisers, list-issues

There is no edge in the other direction anywhere, so a cycle between two of these files is
a design error, not a plumbing problem to route around with a deferred import.

This file imports the four submodules and re-exports NOTHING, for the same reason
`metrics/__init__.py` does not: a name re-exported here would sit beside
`issues.<mod>.<name>` as a second binding of the same function, and `mock.patch` on one
would not reach the other. `__main__.py` re-exports what the facade needs, from the
defining module, and leaves `resolve_issue_core` -- the one patch target in this bucket --
out of every re-export list.
"""
from __future__ import annotations

from ..metrics import calibration

# No `noqa: F401` here any more, unlike `metrics/__init__.py`: `register` below calls into all
# four, so ruff sees them used and a directive would be an unused one (RUF100 fails the lint).
# The submodule-import purpose is unchanged — `issues.<mod>` must resolve on the package for
# the suite's `pm.issues.store.<name>` patch target — it just no longer needs asserting.
from . import (
    adr,
    audit,
    promote,
    store,
)


# --------------------------------------------------------------------------- #
# CLI registration -- this bucket's nine verbs (design §3.2; the contract and the reason
# are in core's own register section).
#
# Written against the SUBMODULE OBJECTS (`store.cmd_append_issue`), never a
# `from .store import cmd_append_issue` at the top of this file, for the reason the
# docstring gives. `promote-issue`'s --classification choices come from `metrics`, which
# `promote` already depends on; that edge is unchanged by reading the constant here.
# --------------------------------------------------------------------------- #
def register(sub):
    ai = sub.add_parser("append-issue", help="append a BL item to state/issues.yaml")
    ai.add_argument("--state-root", dest="state_root", default="",
                    help="path to {implementation_artifacts}/state (preferred)")
    ai.add_argument("--file", default="",
                    help="compatibility alias for <state-root>/issues.yaml")
    ai.add_argument("--session-id", dest="session_id", default=None)
    ai.add_argument("--key", default="",
                    help="BL-E{nnn}-{nnn}; omit to auto-allocate the next number for "
                         "--epic under a lock. An explicit key that already exists "
                         "exits 2 rather than being silently reassigned.")
    ai.add_argument("--epic", required=True, help="zero-padded epic number, e.g. '001'")
    ai.add_argument("--sprint", default="", help="zero-padded sprint number; empty for epic-level")
    ai.add_argument("--title", required=True)
    ai.add_argument("--source", default=None,
                    help="free-text source, stored verbatim (legacy form; prefer --source-phase)")
    ai.add_argument("--source-phase", dest="source_phase", default=None,
                    help="structured source: the phase, e.g. code-review. With --source-ref it "
                         "DERIVES --source as '{phase} ({ref})', so the two cannot disagree")
    ai.add_argument("--source-ref", dest="source_ref", default=None,
                    help="structured source: the finding or story it points at; no parentheses")
    ai.add_argument("--source-note", dest="source_note", default="",
                    help="structured source: free text appended after the parens")
    ai.add_argument("--severity", required=True, choices=["Low", "Medium", "High", "Critical"])
    ai.add_argument("--description", default="")
    ai.add_argument("--kind", default="defect", choices=list(store.ISSUE_KINDS),
                    help="defect (default, not written) | spec-change | spec-proposal")
    ai.add_argument("--ref", default="",
                    help="spec kinds only: the docs(spec) commit SHA, or the proposal path")
    ai.add_argument("--allow-duplicate", dest="allow_duplicate", action="store_true",
                    help="append even if an existing item matches this title+epic+"
                         "sprint+source (default: skip and exit 0)")
    ai.set_defaults(func=store.cmd_append_issue)

    ri = sub.add_parser("resolve-issue",
                        help="resolve an open BL item into issues-resolved.yaml")
    ri.add_argument("--state-root", required=True)
    ri.add_argument("--key", required=True)
    ri.add_argument("--resolution", required=True, choices=list(store.RESOLUTIONS))
    ri.add_argument("--ref", default=None)
    ri.add_argument("--note", default=None)
    ri.add_argument("--session-id", dest="session_id", default=None)
    ri.add_argument("--cause", default="cli", choices=["cli", "triage", "plan-intake"])
    ri.set_defaults(func=store.cmd_resolve_issue)

    ui = sub.add_parser("update-issue", help="change an open BL item's severity")
    ui.add_argument("--state-root", required=True)
    ui.add_argument("--key", required=True)
    ui.add_argument("--severity", required=True, choices=["Low", "Medium", "High", "Critical"])
    ui.add_argument("--note", default=None)
    ui.add_argument("--session-id", dest="session_id", default=None)
    ui.add_argument("--cause", default="cli", choices=["cli", "triage", "plan-intake"])
    ui.set_defaults(func=store.cmd_update_issue)

    pi = sub.add_parser("promote-issue", help="turn open BL items into a new estimated story")
    pi.add_argument("--state-root", required=True)
    pi.add_argument("--artifacts-root", required=True,
                    help="implementation_artifacts root (NOT the state root)")
    pi.add_argument("--key", required=True, action="append", help="repeatable")
    pi.add_argument("--epic", required=True)
    pi.add_argument("--sprint", required=True)
    pi.add_argument("--classification", required=True, choices=list(calibration.CLASSIFICATIONS))
    pi.add_argument("--title", default="")
    pi.add_argument("--model", default="")
    pi.add_argument("--token-rates", dest="token_rates", default="")
    pi.add_argument("--session-id", dest="session_id", default=None)
    pi.add_argument("--cause", default="cli", choices=["cli", "triage", "plan-intake"])
    pi.set_defaults(func=promote.cmd_promote_issue)

    si = sub.add_parser("schedule-issue",
                        help="attach open BL items to a story that already exists")
    si.add_argument("--state-root", required=True)
    si.add_argument("--key", required=True, action="append", help="repeatable")
    si.add_argument("--story", required=True, help="an existing story key E{nnn}-S{nn}-{nnn}")
    si.add_argument("--session-id", dest="session_id", default=None)
    si.add_argument("--cause", default="cli", choices=["cli", "triage", "plan-intake"])
    si.set_defaults(func=promote.cmd_schedule_issue)

    au = sub.add_parser("audit-issues", help="structural integrity checks over the backlog")
    au.add_argument("--state-root", required=True)
    au.add_argument("--format", choices=["text", "json"], default="text")
    au.set_defaults(func=audit.cmd_audit_issues)

    rp = sub.add_parser("repair-issue", help="structural repair gated on an audit-issues finding")
    rp.add_argument("--state-root", required=True)
    rp.add_argument("--key", default=None,
                    help="the item; for reseed, any key of the epic; omit with --all-legacy")
    rp.add_argument("--action", required=True,
                    choices=["unschedule", "link", "repoint", "reseed", "reopen",
                             "normalize-status", "normalize-keys"])
    rp.add_argument("--story", default=None, help="with --action link")
    rp.add_argument("--all-legacy", dest="all_legacy", action="store_true",
                    help="with --action normalize-status: every legacy status in one pass")
    rp.add_argument("--session-id", dest="session_id", default=None)
    rp.add_argument("--cause", default="cli", choices=["cli", "triage", "plan-intake"])
    rp.set_defaults(func=audit.cmd_repair_issue)

    li = sub.add_parser("list-issues", help="list (with filters) open BL items, resolved ones "
                                            "(--resolved), or both (--all, JSON)")
    li.add_argument("--state-root", required=True, help="path to {implementation_artifacts}/state")
    li.add_argument("--epic", help="epic id — accepts 'E001' or '001'")
    li.add_argument("--sprint", help="sprint id — accepts 'S01' or '01'; never matches an epic-level (empty-sprint) item")
    li.add_argument("--severity", action="append", choices=["Low", "Medium", "High", "Critical"],
                    help="filter by severity; repeat to OR multiple severities")
    li.add_argument("--format", choices=["text", "json"], default="text")
    li.add_argument("--status", choices=["backlog", "scheduled"],
                    help="open items with this status")
    li.add_argument("--resolved", action="store_true", help="list issues-resolved.yaml instead")
    li.add_argument("--resolution", choices=list(store.RESOLUTIONS), help="with --resolved only")
    li.add_argument("--kind", choices=list(store.ISSUE_KINDS),
                    help="items of this kind; an item without `kind` is a defect")
    li.add_argument("--all", action="store_true",
                    help='JSON {"open": [...], "resolved": [...]} read under one lock')
    li.set_defaults(func=audit.cmd_list_issues)

    ar = sub.add_parser("adr-reserve",
                        help="reserve N sequential ADR numbers under a lock, before dispatch")
    ar.add_argument("--state-root", required=True)
    ar.add_argument("--epic", required=True)
    ar.add_argument("--slug", required=True)
    ar.add_argument("--count", type=int, default=1)
    ar.add_argument("--adr-dir", dest="adr_dir", default="",
                    help="the one ADR home to scan (default: <git top-level>/docs/adr)")
    ar.set_defaults(func=adr.cmd_adr_reserve)
