"""pm_status.metrics.estimates -- the estimate engine (references/metrics-contract.md).

`compute_story_estimate` (band midpoint x scope ratio x fix factor, per metric)
and `rollup_parent_estimate` (sum of children + a calibrated closure band + a
calibrated orchestration band), plus the cold-start bands and the token-mix split
the roll-up prices through.

TWO OF THIS MODULE'S EXPORTS ARE mock.patch TARGETS -- `compute_story_estimate`
and `rollup_parent_estimate` -- so they are reached as
`metrics.estimates.<name>(...)` from every caller outside this file and are NOT
re-exported anywhere. Inside this file they are plain global lookups, which is
what `patch.object(pm.metrics.estimates, ...)` rebinds, so same-module callers
see the patch too. `_promote_issue` (today in `__main__.py`, `issues/promote`
after the next extraction) is the one external caller of each: it must keep
calling them module-qualified or the patch stops biting, silently.

`nodes.epic_file` and `nodes.save_node` are module-qualified for the same reason.
"""

from __future__ import annotations

import sys

from .. import nodes
from ..core import (
    PMError,
    _die_notfound,
    _die_usage,
    _now_iso,
    _num_or_none,
    epic_node_lock,
)
from ..nodes import (
    _sprint_key_from_dir,
    list_sprint_dirs,
    list_story_files,
    load_node,
    sprint_file,
    story_file,
)
from .calibration import (
    CLOSURE_RANGE_KEYS,
    COLD_START_FIX_FACTOR,
    COLD_START_SCOPE_RATIO,
    MIN_SAMPLES,
    ORCH_SPREAD,
    _child_estimate_value,
    active_closure_ratio,
    active_fix_factor,
    active_orchestration_fraction,
    active_scope_ratio,
    load_calibration,
)
from .rates import (
    COLD_START_TOKEN_MIX,
    FRESH_TOKEN_CLASSES,
    TOKEN_CLASSES,
    cost_from_tokens,
    fresh_share,
    rate_overrides,
    tokens_block,
)

# The estimate-time model. Skills pass modules.l3io-pm.default_model through
# --model; this is the fallback for a direct CLI call, and it is a REAL model
# id so an unknown-model error can never be produced by the default itself.
DEFAULT_ESTIMATE_MODEL = "claude-opus-5"


def observed_mix(cal) -> dict:
    """Mean observed token mix, or the cold-start assumption below MIN_SAMPLES."""
    samples = ((cal or {}).get("token_mix") or {}).get("samples") or []
    # hasattr(s, "get") first: a stray non-mapping entry (hand-edit, bad
    # merge, partial corruption of the committed, shared calibration file)
    # must fall back to cold-start like every other malformed shape here —
    # not crash `estimate-story` for the whole project. Same guard as the
    # tokens_k mapping check in record_story_sample above.
    usable = [s for s in samples if hasattr(s, "get") and
              all(_num_or_none(s.get(c)) is not None for c in TOKEN_CLASSES)]
    if len(usable) < MIN_SAMPLES:
        return dict(COLD_START_TOKEN_MIX)
    mix = {c: sum(float(s[c]) for s in usable) / len(usable) for c in TOKEN_CLASSES}
    total = sum(mix.values())
    if total <= 0:
        return dict(COLD_START_TOKEN_MIX)
    return {c: v / total for c, v in mix.items()}   # renormalize; means need not sum to 1


def split_tokens(total: float, mix: dict) -> dict:
    """Split a banded total across classes, preserving the total exactly.

    Rounding drift goes to the largest class rather than being dropped, so
    `sum(classes) == total` is an invariant a test can assert and a reader can
    trust.
    """
    out = {c: round(total * float(mix.get(c, 0.0))) for c in TOKEN_CLASSES}
    drift = round(total) - sum(out.values())
    if drift:
        biggest = max(TOKEN_CLASSES, key=lambda c: out[c])
        out[biggest] += drift
    return out


# Cold-start base bands (low, high) per classification; the single source (formerly a
# markdown table in steps/shared/step-estimate.md). No `cost` row: cost is derived from the
# tokens_k total and priced per model, see cmd_estimate_story -- a separate cost band drifted
# from the token estimate it should follow. `tokens_k` is a FRESH-token band (input + output
# + cache_write); see FRESH_TOKEN_CLASSES. Do not raise it to meet a cache-inclusive actual:
# cache_read is projected from the observed mix and belongs to orchestration, not scope.
BASE_BANDS = {
    "simple":   {"man_hours": (2, 4),  "hitl_hours": (0.1, 0.3), "elapsed_hours": (0.5, 1.5),
                 "tokens_k": (20, 50)},
    "standard": {"man_hours": (4, 8),  "hitl_hours": (0.2, 0.5), "elapsed_hours": (1, 3),
                 "tokens_k": (40, 100)},
    "complex":  {"man_hours": (8, 16), "hitl_hours": (0.3, 1.0), "elapsed_hours": (2, 6),
                 "tokens_k": (80, 200)},
}


def compute_story_estimate(state_root, node, cls, model, overrides, confidence=None):
    """Compute and write a story's estimate block: band midpoint x scope ratio x fix
    factor, per metric. Classification is the model's judgment; everything after it
    is arithmetic, done here so it's error-checked and reproducible.

    Each metric queries its own calibrated scope ratio — man_hours and tokens_k may
    be calibrated independently once each has >=3 samples, so ratios are looked up
    per metric, never hoisted out and reused across all four in BASE_BANDS.

    All four applied ratios are recorded as `estimate.scope_ratios`, per metric.
    This is load-bearing, not provenance: `derive_story_sample` divides the applied
    ratio back out to measure the next sample against the base band, and one
    scalar cannot reconstruct four metrics' corrections.

    `cost` is not one of the banded/calibrated metrics: it is priced from the
    banded tokens_k TOTAL, split across classes by `observed_mix` (or the
    cold-start assumption below three samples), then run through
    `cost_from_tokens` for `--model` (falling back to DEFAULT_ESTIMATE_MODEL).
    This keeps cost arithmetically bound to the token estimate it prices —
    the two can no longer drift apart the way a separately-banded,
    separately-calibrated cost could.

    Never saves and never exits: cmd_estimate_story saves after it; promote-issue
    writes the new node and its estimate in one save.
    """
    _, cal = load_calibration(state_root)
    fix = active_fix_factor(cal, cls)
    fix = COLD_START_FIX_FACTOR if fix is None else fix

    from ruamel.yaml.comments import CommentedMap

    # Every value below is computed into locals first, including the token
    # split and the priced cost -- node/est is not touched until all of that
    # (in particular cost_from_tokens, the one call that can raise) has
    # succeeded. An in-process caller must be able to catch PMError and keep
    # going without finding a half-written estimate block behind it.
    applied = CommentedMap()
    raw = {}
    for metric, (lo, hi) in BASE_BANDS[cls].items():
        mid = (lo + hi) / 2.0
        ratio = active_scope_ratio(cal, cls, metric)
        if ratio is None:
            ratio = COLD_START_SCOPE_RATIO
        applied[metric] = round(ratio, 4)
        value = mid * ratio * fix
        raw[metric] = round(value) if metric == "tokens_k" else round(value, 2)

    # The band produces FRESH tokens, matching what the scope ratio now measures.
    # cache_read is then projected from the observed mix rather than banded: it
    # tracks corpus x agent count, so a story-size band cannot predict it, but the
    # ratio it bears to fresh tokens is exactly what token_mix samples record.
    fresh_total = raw["tokens_k"]
    mix = observed_mix(cal)
    fshare = fresh_share(mix)
    counts = split_tokens(fresh_total, {c: mix.get(c, 0.0) / fshare for c in FRESH_TOKEN_CLASSES})
    counts["cache_read"] = round(fresh_total * (mix.get("cache_read", 0.0) / fshare))
    tokens_est = tokens_block(counts)
    try:
        cost = cost_from_tokens(counts, model, overrides)
    except KeyError as e:
        # e.args[0], not str(e) — KeyError.__str__ repr-quotes its argument,
        # which would double-wrap a message that already reads as prose.
        raise PMError(2, e.args[0])

    # Everything above is a local computation; only now, with cost already
    # priced successfully, do we touch node. Get the existing estimate block
    # or create one -- in place, so any other keys and ruamel comments on an
    # existing block survive -- then write the computed values into it in the
    # same key order cmd_estimate_story has always produced.
    est = node.get("estimate")
    if est is None:
        est = CommentedMap()
        node["estimate"] = est
    for metric, value in raw.items():
        est[metric] = value
    est.pop("tokens_k")
    est["tokens_k"] = tokens_est
    est["cost"] = cost
    est["model"] = model

    est["fix_factor"] = round(fix, 4)
    est["scope_ratios"] = applied
    est.pop("scope_ratio", None)   # the superseded single-value form
    if confidence:
        est["confidence"] = confidence
    node["classification"] = cls
    node["updated_at"] = _now_iso()
    return applied


def cmd_estimate_story(args) -> int:
    """CLI wrapper over compute_story_estimate: resolve, compute, save, report."""
    path = story_file(args.state_root, args.story)
    if path is None:
        _die_notfound(f"story {args.story}")
    y, node = load_node(path)
    if node is None:
        _die_notfound(f"story {args.story} — file is empty")
    try:
        applied = compute_story_estimate(args.state_root, node, args.classification,
                                         args.model or DEFAULT_ESTIMATE_MODEL,
                                         rate_overrides(args), args.confidence)
    except PMError as e:
        _die_usage(e.msg)
    nodes.save_node(y, node, path)
    shown = " ".join(f"{m}={v}" for m, v in applied.items())
    sys.stdout.write(f"OK estimate-story {args.story} class={args.classification} "
                     f"scope_ratios[{shown}] fix_factor={node['estimate']['fix_factor']}\n")
    return 0


# Closure overhead as a fraction of children, used when no calibrated ratio is
# active yet. Deliberately a band, not a point: closure cost is variable.
COLD_START_CLOSURE_BAND = (0.10, 0.25)


def rollup_parent_estimate(state_root, epic, sprint, model, overrides):
    """Roll a sprint's story estimates, or an epic's sprint estimates, up to
    the parent as a range: sum(children) + a closure band + an orchestration
    band. Output is always range form, even when every child estimate is
    single-value (the story form).

    The closure band scales by the calibrated closure ratio for level/metric
    once active (>=3 samples), else the cold-start band applies (equivalently,
    ratio 1.0). The orchestration band scales by the calibrated orchestration
    FRACTION for level/metric once active, else it contributes nothing — there
    is no cold-start prior for orchestration (see ORCH_SPREAD, and
    active_orchestration_fraction's docstring for why). Both bands widen by a
    fixed spread (COLD_START_CLOSURE_BAND, ORCH_SPREAD respectively) rather
    than landing on a single point.

    The applied ratios/fractions are recorded as `estimate.closure_ratios` and
    `estimate.orchestration_ratios`, per metric, so `derive_closure_sample` and
    a future orchestration-sample reader can divide them back out — the same
    reason `estimate.scope_ratios` exists on a story.

    `cost` is not one of the banded metrics (see CLOSURE_RANGE_KEYS): it is
    derived from the rolled-up tokens_k range, split across classes by
    `observed_mix`, then priced for `--model` (falling back to
    DEFAULT_ESTIMATE_MODEL) — the sprint/epic-level mirror of what
    `cmd_estimate_story` already does for a story. This keeps the rolled-up
    cost arithmetically bound to the rolled-up token estimate it prices,
    instead of banding and calibrating a second, independently-drifting cost.

    Never exits: raises PMError(3) for a missing parent, PMError(2) for
    nothing to roll up or an unpriceable model.

    The epic-level roll-up rewrites epic.yaml, so it runs under that epic's
    epic_node_lock -- re-entrantly when promote-issue, which already holds it,
    is the caller. An epic the pre-check cannot find raises PMError(3) right
    there, with no lock file created for it. It is never handed to the body
    unlocked: find_epic_dir scans active -> planned -> archived, so a move-epic
    the other way can land mid-scan and hide an epic that exists, and the body's
    own re-resolve would then find it and reach save_node without the lock.
    """
    if sprint:
        return _rollup_parent_estimate(state_root, epic, sprint, model, overrides)
    if nodes.epic_file(state_root, epic) is None:
        raise PMError(3, f"epic {epic}")
    with epic_node_lock(state_root, epic):
        return _rollup_parent_estimate(state_root, epic, sprint, model, overrides)


def _rollup_parent_estimate(state_root, epic, sprint, model, overrides):
    """rollup_parent_estimate's body; the caller holds the epic lock for an epic roll-up."""
    level = "sprint" if sprint else "epic"
    if level == "sprint":
        ppath = sprint_file(state_root, epic, sprint)
        child_paths = list_story_files(state_root, epic, sprint)
    else:
        ppath = nodes.epic_file(state_root, epic)
        child_paths = [sprint_file(state_root, epic, _sprint_key_from_dir(d))
                       for d in list_sprint_dirs(state_root, epic)]
    if ppath is None:
        raise PMError(3, f"{level} {sprint or epic}")
    y, pnode = load_node(ppath)
    if pnode is None:
        raise PMError(3, f"{level} file is empty")

    _, cal = load_calibration(state_root)
    from ruamel.yaml.comments import CommentedMap
    est = CommentedMap()
    applied = CommentedMap()
    orch_applied = CommentedMap()
    counted = 0
    for metric, (lo_key, hi_key) in CLOSURE_RANGE_KEYS.items():
        total = 0.0
        seen = 0
        for cp in child_paths:
            if cp is None:
                continue
            _, cn = load_node(cp)
            v = _child_estimate_value(cn, metric)
            if v is not None:
                total += v
                seen += 1
        if seen == 0:
            continue
        counted = max(counted, seen)
        ratio = active_closure_ratio(cal, level, metric)
        if ratio is None:
            ratio = 1.0            # cold start: the closure band applies unscaled
        applied[metric] = round(ratio, 4)

        frac = active_orchestration_fraction(cal, level, metric)
        orch_applied[metric] = round(frac, 4) if frac is not None else 0
        of = frac or 0.0
        lo = total * (1 + ratio * COLD_START_CLOSURE_BAND[0] + of * ORCH_SPREAD[0])
        hi = total * (1 + ratio * COLD_START_CLOSURE_BAND[1] + of * ORCH_SPREAD[1])
        if metric == "tokens_k":
            est[lo_key], est[hi_key] = round(lo), round(hi)
        else:
            est[lo_key], est[hi_key] = round(lo, 2), round(hi, 2)

    if counted == 0:
        raise PMError(2, f"{level} {sprint or epic} has no child estimates to roll up")

    est["closure_ratios"] = applied
    est["orchestration_ratios"] = orch_applied
    # ANY inactive metric warns, not just "every metric inactive" (`not any(...)`
    # would under-fire: orchestration calibrates per metric, and a metric is
    # sampled only when every child carries a numeric actual for it, so under a
    # mixed runtime man_hours can activate while tokens_k never does — `any()`
    # would then be true and stay silent on exactly the metric the warning
    # exists to flag). Named, not blanket: listing which metrics are still
    # unestimated makes the warning actionable instead of a caveat that is
    # "always true anyway" once any single metric has activated.
    inactive = [m for m, v in orch_applied.items() if not v]
    if inactive:
        sys.stderr.write(
            "pm-status.py: warning — orchestration is unestimated for "
            f"{', '.join(inactive)} (component has <{MIN_SAMPLES} samples at "
            f"{level} level); this estimate is known-low on those metrics.\n")

    mix = observed_mix(cal)
    try:
        for bound, key in (("tokens_k_min", "cost_low"), ("tokens_k_max", "cost_high")):
            tv = _num_or_none(est.get(bound))
            if tv is not None:
                est[key] = cost_from_tokens(split_tokens(tv, mix), model, overrides)
    except KeyError as e:
        # e.args[0], not str(e) — KeyError.__str__ repr-quotes its argument,
        # which would double-wrap a message that already reads as prose.
        raise PMError(2, e.args[0])
    est["model"] = model

    est["confidence"] = "medium"
    pnode["estimate"] = est
    pnode["updated_at"] = _now_iso()
    nodes.save_node(y, pnode, ppath)
    return level, counted


def cmd_estimate_rollup(args) -> int:
    """CLI wrapper over rollup_parent_estimate."""
    try:
        level, counted = rollup_parent_estimate(args.state_root, args.epic, args.sprint,
                                                args.model or DEFAULT_ESTIMATE_MODEL,
                                                rate_overrides(args))
    except PMError as e:
        if e.code == 3:
            _die_notfound(e.msg)
        _die_usage(e.msg)
    sys.stdout.write(f"OK estimate-rollup {level} {args.sprint or args.epic} "
                     f"from {counted} children\n")
    return 0
