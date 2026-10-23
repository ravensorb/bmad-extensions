"""pm_status.metrics.spend -- spend attribution, the three buckets of §6.

`rollup_sprint` and `rollup_epic` walk the state tree and attribute actuals to
`stories`, `closure` and `orchestration` -- the same three terms the estimate has,
so that the largest one cannot go missing from a report that only sums children.

A leaf: it reads `core` and `nodes` and nothing else in `metrics`. `report`
consumes it, not the other way round.
"""

from __future__ import annotations

import os

from .. import nodes
from ..core import (
    METRIC_FIELDS,
    _actual_metric,
)
from ..nodes import (
    _sprint_key_from_dir,
    list_sprint_dirs,
    list_story_files,
    load_node,
    sprint_file,
)


def _accumulate_actuals(totals: dict, node) -> None:
    actual = (node or {}).get("actual") or {}
    for m in METRIC_FIELDS:
        v = _actual_metric(actual, m)
        if v is None:
            continue
        totals[m] = totals.get(m, 0.0) + v


# --------------------------------------------------------------------------- #
# spend attribution — the three buckets metrics-contract.md §6 defines
#
# The estimate has three terms (children + closure band + orchestration band), so
# a report of what was actually spent has to have the same three, or the largest
# term stays invisible: on the run that motivated this model, orchestration was
# 72% of total spend and stories were 24%. Recording it on disk and omitting it
# from every rendered report leaves the number nobody can act on. Design §9's CLI
# table specifies this breakout for `report`; `show` carries it too, since it is
# the per-node view of the same three buckets.
# --------------------------------------------------------------------------- #
SPEND_BUCKETS = ("stories", "closure", "orchestration")


def _block_totals(node, block: str = "actual") -> dict:
    """One metric block's numeric values. Absent and `N/A` entries are omitted
    rather than coerced to zero — a missing measurement is not a measured zero."""
    b = (node or {}).get(block) or {}
    out = {}
    for m in METRIC_FIELDS:
        v = _actual_metric(b, m)
        if v is not None:
            out[m] = v
    return out


def _add_totals(dst: dict, src: dict) -> None:
    for k, v in (src or {}).items():
        dst[k] = dst.get(k, 0.0) + v


def _closure_totals(parent_actual: dict, children_total: dict) -> dict:
    """A node's own closure-phase spend: its `actual` minus its children's sum.

    The same residual `derive_closure_sample` measures its component from, so the
    report and the calibration loop can never disagree about what "closure" means.
    Only metrics BOTH sides carry are reported — a parent metric with no comparable
    children sum has no residual, not a residual equal to the whole parent. Clamped
    at zero for display: a negative residual is a wall-clock overlap or a miscount
    (`derive_closure_sample` names which), not negative spend.
    """
    out = {}
    for m, pv in (parent_actual or {}).items():
        cv = (children_total or {}).get(m)
        if cv is None:
            continue
        out[m] = max(0.0, pv - cv)
    return out


def _new_spend() -> dict:
    return {b: {} for b in SPEND_BUCKETS}


def _merge_spend(dst: dict, src: dict) -> None:
    for b in SPEND_BUCKETS:
        _add_totals(dst[b], (src or {}).get(b) or {})


def _spend_total(spend: dict) -> dict:
    """The three buckets summed — what the level actually cost, end to end."""
    out = {}
    for b in SPEND_BUCKETS:
        _add_totals(out, (spend or {}).get(b) or {})
    return out


def _sprint_spend(story_totals: dict, snode) -> dict:
    return {"stories": dict(story_totals),
            "closure": _closure_totals(_block_totals(snode, "actual"), story_totals),
            "orchestration": _block_totals(snode, "orchestration")}


def _has_spend(spend: dict) -> bool:
    return any((spend or {}).get(b) for b in SPEND_BUCKETS)


def rollup_sprint(state_root: str, epic_key: str, sprint_key: str) -> dict:
    by_status, totals, stories = {}, {}, []
    blocked_details, cumulative_blocks = [], 0
    for p in list_story_files(state_root, epic_key, sprint_key):
        _, node = load_node(p)
        if node is None:
            continue
        st = str(node.get("status", "unknown"))
        by_status[st] = by_status.get(st, 0) + 1
        _accumulate_actuals(totals, node)
        row = {"key": node.get("key", os.path.basename(p)), "status": st}
        if st == "blocked":
            row["blocked_reason"] = str(node.get("blocked_reason", "") or "")
            blocked_details.append(
                {"key": row["key"], "reason": row["blocked_reason"]})
        # completion_evidence.blocks_seen counts events over the story's whole life,
        # not current state; a story currently unblocked can still contribute here.
        ce = node.get("completion_evidence") or {}
        cumulative_blocks += int(ce.get("blocks_seen", 0) or 0)
        stories.append(row)
    sp = sprint_file(state_root, epic_key, sprint_key)
    _, snode = load_node(sp) if sp else (None, None)
    return {
        "key": sprint_key,
        "status": str((snode or {}).get("status", "unknown")),
        "story_count": len(stories),
        "by_status": by_status,
        "blocked_stories": len(blocked_details),
        "blocked_details": blocked_details,
        "blocks_seen_cumulative": cumulative_blocks,
        "actual_totals": totals,
        "node_actual": _block_totals(snode, "actual"),
        "spend": _sprint_spend(totals, snode),
        "stories": stories,
    }


def rollup_epic(state_root: str, epic_key: str) -> dict:
    by_status, totals, sprints, story_count = {}, {}, [], 0
    spend, sprint_actual_sum = _new_spend(), {}
    blocked_stories_total, cumulative_blocks_total = 0, 0
    blocked_details_all = []
    for sd in list_sprint_dirs(state_root, epic_key):
        skey = _sprint_key_from_dir(sd)
        r = rollup_sprint(state_root, epic_key, skey)
        sprints.append(r)
        story_count += r["story_count"]
        for k, v in r["by_status"].items():
            by_status[k] = by_status.get(k, 0) + v
        for k, v in r["actual_totals"].items():
            totals[k] = totals.get(k, 0.0) + v
        _merge_spend(spend, r["spend"])
        _add_totals(sprint_actual_sum, r["node_actual"])
        blocked_stories_total += r.get("blocked_stories", 0)
        cumulative_blocks_total += r.get("blocks_seen_cumulative", 0)
        for detail in r.get("blocked_details", []):
            blocked_details_all.append({**detail, "sprint": r["key"]})
    ep = nodes.epic_file(state_root, epic_key)
    _, enode = load_node(ep) if ep else (None, None)
    # The epic's OWN closure residual sits on top of its sprints' — one bucket,
    # two levels, because both are "the closing level's own closure phases".
    _add_totals(spend["closure"],
                _closure_totals(_block_totals(enode, "actual"), sprint_actual_sum))
    _add_totals(spend["orchestration"], _block_totals(enode, "orchestration"))
    return {
        "key": epic_key,
        "status": str((enode or {}).get("status", "unknown")),
        "sprint_count": len(sprints),
        "story_count": story_count,
        "by_status": by_status,
        "blocked_stories": blocked_stories_total,
        "blocked_details": blocked_details_all,
        "blocks_seen_cumulative": cumulative_blocks_total,
        "actual_totals": totals,
        "node_actual": _block_totals(enode, "actual"),
        "spend": spend,
        "sprints": sprints,
    }


def _fmt_actuals(totals: dict) -> str:
    """Render an actuals dict in stable METRIC_FIELDS order."""
    return "  ".join(f"{m}={_norm_spend(totals.get(m))}" for m in METRIC_FIELDS)


def _norm_spend(v):
    """Display form for a summed metric: 0 when absent, trimmed of float noise.

    Summing floats produces 3.9000000000000004; a report that prints that is
    reporting its own arithmetic rather than the number. Rounded to 4 places
    (well past any metric's real precision) and shown as an int when integral.
    """
    if v is None:
        return 0
    try:
        f = round(float(v), 4)
    except (TypeError, ValueError):
        return v
    return int(f) if f.is_integer() else f
