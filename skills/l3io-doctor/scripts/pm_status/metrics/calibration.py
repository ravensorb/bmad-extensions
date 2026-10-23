"""pm_status.metrics.calibration -- the learning loop (references/calibration-model.md).

The largest module in the package, and deliberately whole: the schema and its two
migrations, the sample derivation for all three components (scope, closure,
orchestration), the weighted-ratio reader the estimate engine applies, the
`redrive` rebuild and `cmd_calibration`. Splitting it would put a migration in one
file and the schema constant it migrates TO in another.

`ORCH_SPREAD`, `ORCH_MID` and `_child_estimate_value` live here rather than with
the estimate engine that also reads them, because `derive_closure_sample` reads
all three to back the orchestration band out of a parent estimate. Calibration
sits BELOW estimates, so down here they are one edge; up there they were a cycle.

`core._load` and `core._atomic_dump` are reached through the MODULE OBJECT, and
so is `nodes.epic_file`: the suite patches all three, and a `from ..core import
_load` binding would be a private copy the patch could never reach.
"""

from __future__ import annotations

import json
import os
import sys

from .. import core, nodes
from ..core import (
    CALIBRATED_METRIC_FIELDS,
    STATUS_DIRS,
    PMError,
    _actual_metric,
    _estimate_metric,
    _indexable_key,
    _is_number,
    _iter_count,
    _mid,
    _now_iso,
    _num_or_none,
    _run_core,
    _yaml,
    calibration_lock,
    calibration_path,
    events_path,
)
from ..nodes import (
    _sprint_key_from_dir,
    list_sprint_dirs,
    list_story_files,
    load_node,
    sprint_file,
)
from .events import (
    _total_blocked_hours,
)
from .rates import (
    TOKEN_CLASSES,
    fresh_tokens,
)

# --------------------------------------------------------------------------- #
# Calibration — the learning loop. See references/metrics-contract.md §8.
# The file is a SHARED append target: every set-actual across parallel
# subagents may append to it, so the WHOLE read-modify-write cycle runs under
# one exclusive lock (`calibration_lock`) — not just the write. Locking only
# the write let two concurrent samplers each read the same pre-append state and
# the second one silently clobber the first's sample. Unlike node files, which
# are sharded per story precisely to avoid contention.
# --------------------------------------------------------------------------- #
CALIBRATION_SCHEMA_VERSION = 2
MIN_SAMPLES = 3          # a component below this is recorded but not applied
DECAY = 0.8              # exponential decay, applied oldest-first
COLD_START_SCOPE_RATIO = 1.0
COLD_START_FIX_FACTOR = 1.25
CLASSIFICATIONS = ("simple", "standard", "complex")
CLOSURE_LEVELS = ("sprint", "epic")


def new_calibration(granularity: str = "story"):
    from ruamel.yaml.comments import CommentedMap
    cal = CommentedMap()
    cal["version"] = CALIBRATION_SCHEMA_VERSION
    cal["granularity"] = granularity
    cal["scope"] = CommentedMap((c, CommentedMap()) for c in CLASSIFICATIONS)
    cal["closure"] = CommentedMap((lv, CommentedMap()) for lv in CLOSURE_LEVELS)
    cal["fix"] = CommentedMap((c, CommentedMap()) for c in CLASSIFICATIONS)
    # Unlike closure, orchestration has no estimated band to measure a ratio
    # against (it ships null by design — see record_orchestration_sample), so
    # it is seeded empty here and filled by set-actual --block orchestration.
    cal["orchestration"] = CommentedMap((lv, CommentedMap()) for lv in CLOSURE_LEVELS)
    return cal


def load_calibration(state_root: str):
    """Load the calibration file, or a fresh skeleton if absent. Never raises."""
    p = calibration_path(state_root)
    y, data = core._load(p)
    if data is None:
        return _yaml(), new_calibration()
    for key, default in (("scope", CLASSIFICATIONS), ("fix", CLASSIFICATIONS),
                         ("closure", CLOSURE_LEVELS), ("orchestration", CLOSURE_LEVELS)):
        if key not in data or data[key] is None:
            from ruamel.yaml.comments import CommentedMap
            data[key] = CommentedMap((k, CommentedMap()) for k in default)
    if "granularity" not in data:
        data["granularity"] = "story"
    return y, data


def save_calibration(y, cal, state_root: str) -> None:
    """Always locked — this file is written from every set-actual."""
    with calibration_lock(state_root):
        core._atomic_dump(y, cal, calibration_path(state_root))


def migrate_calibration(y, cal, state_root: str):
    """version 1 -> 2. Original preserved as .v1 and never read again."""
    if cal.get("version") == CALIBRATION_SCHEMA_VERSION:
        return cal
    p = calibration_path(state_root)
    backup = p + ".v1"
    if os.path.exists(p) and not os.path.exists(backup):
        import shutil
        shutil.copy2(p, backup)
    blended = cal.get("ratio")
    fresh = new_calibration(cal.get("granularity", "story"))
    # The old blended figure maps onto scope only. closure and fix start at
    # zero samples: the v1 file cannot separate them, and seeding from a
    # blended number would import exactly the bias the split removes.
    if isinstance(blended, (int, float)):
        from ruamel.yaml.comments import CommentedMap
        for c in CLASSIFICATIONS:
            entry = CommentedMap()
            entry["samples"] = [float(blended)]
            fresh["scope"][c] = CommentedMap((("man_hours", entry),))
    save_calibration(y, fresh, state_root)
    return fresh


def weighted_ratio(samples: list) -> float:
    """Exponential-decay weighted mean, oldest first (most recent weighs most)."""
    vals = [float(s) for s in samples if _is_number(s)]
    if not vals:
        return None
    n = len(vals)
    num = den = 0.0
    for i, v in enumerate(vals):
        w = DECAY ** (n - 1 - i)
        num += v * w
        den += w
    return num / den if den else None


# A calibration sample outside this range is not wrong by construction — it
# is a ratio (actual/estimate-ish, see derive_story_sample), and most real
# ratios sit near 1.0 — but one this far off is exactly the shape a story
# sample would have if orchestration-shaped overhead (a defect this rework
# separately isolates into its own `orchestration` component) leaked into
# it under the old rules. FLAG surfaces that suspicion for human review; it
# never drops or corrects the sample itself.
TOKENS_SANITY_RANGE = (0.5, 2.0)

# Stamped once, at the top level of the calibration file, when migrate_calibration_metrics
# finishes a real pass -- including one that finds nothing. NOT a version bump: `version`
# stays CALIBRATION_SCHEMA_VERSION == 2. This replaced a REJECTED design that inferred
# "already migrated" from the absence of the old `cost`/`time_hours` keys, which has a silent
# blind spot (a non-Claude project never accumulates `cost` samples), so old-definition
# samples went unquarantined and every future estimate was silently wrong. A positive marker
# has no such blind spot: its absence always means "run it".
CALIBRATION_METRICS_MARKER = "metrics_migrated_at"
TOKEN_BASIS_MARKER = "token_basis_migrated_at"


def migrate_calibration_metrics(y, cal, state_root: str) -> list:
    """Reshape a pre-metrics-rework calibration file in place. Returns a
    change log (empty when there was nothing to migrate).

    Gated on CALIBRATION_METRICS_MARKER, a positive marker stamped at the end
    of every real pass through this function — even a no-op one. A brand-new
    project has nothing to migrate on its first write, but still gets
    stamped right there, before that same write appends its first (entirely
    legitimate) sample: this is what stops a LATER real man_hours or fix
    sample from ever being revisited and wrongly quarantined (see
    test_man_hours_written_after_the_one_time_cutover_is_never_revisited).

    Once past the gate, `man_hours` and `fix` quarantine UNCONDITIONALLY —
    no corroborating cost/time_hours marker is required in the same bucket
    or file (see test_man_hours_quarantined_even_without_cost_or_time_hours_markers,
    the case that falsified an earlier key-presence-based design). `version`
    stays 2 throughout: compatibility is by shape-tolerant reads, never a
    version gate.
    """
    if cal.get(CALIBRATION_METRICS_MARKER):
        return []

    log = []
    p = calibration_path(state_root)
    backup = p + ".pre-metrics"
    if os.path.exists(p) and not os.path.exists(backup):
        import shutil
        shutil.copy2(p, backup)
        log.append(f"backup {os.path.basename(backup)}")

    def _reshape(component: str):
        buckets = cal.get(component) or {}
        for bucket, metrics in list(buckets.items()):
            if not hasattr(metrics, "items"):
                continue
            if "cost" in metrics:
                del metrics["cost"]
                log.append(f"DROP {component}.{bucket}.cost (derived from tokens x rates "
                           f"since Task 10 — never independently calibrated again)")
            if "time_hours" in metrics:
                metrics["elapsed_hours"] = metrics.pop("time_hours")
                log.append(f"RENAME {component}.{bucket}.time_hours -> elapsed_hours")
            if "man_hours" in metrics:
                from ruamel.yaml.comments import CommentedMap
                dest = (cal.setdefault("legacy", CommentedMap())
                           .setdefault(component, CommentedMap())
                           .setdefault(bucket, CommentedMap()))
                dest["man_hours"] = metrics.pop("man_hours")
                log.append(f"QUARANTINE {component}.{bucket}.man_hours (definition changed: "
                           f"human attention -> counterfactual developer effort — old "
                           f"samples are incomparable, preserved under legacy.{component}.{bucket})")
            samples = list((metrics.get("tokens_k") or {}).get("samples") or [])
            if samples:
                r = weighted_ratio(samples)
                if r is not None and not (TOKENS_SANITY_RANGE[0] <= r <= TOKENS_SANITY_RANGE[1]):
                    log.append(
                        f"FLAG {component}.{bucket}.tokens_k ratio={r:.2f} outside "
                        f"{TOKENS_SANITY_RANGE} — carried forward as-is, but review "
                        f"before trusting (possible orchestration overhead swept "
                        f"into story samples under the old rules)")

    for component in ("scope", "closure"):
        _reshape(component)

    fix = cal.get("fix") or {}
    fix_had_content = any(bool(v) for v in fix.values())
    if fix_had_content:
        from ruamel.yaml.comments import CommentedMap
        cal.setdefault("legacy", CommentedMap())["fix"] = fix
        cal["fix"] = CommentedMap((c, CommentedMap()) for c in CLASSIFICATIONS)
        log.append("QUARANTINE fix (wholesale — every cohort is measured in "
                   "mean_man_hours, the same definition change as scope/closure "
                   "man_hours; fix has no per-metric split to act on selectively, "
                   "preserved under legacy.fix)")

    # token_mix seeding stays tied to "did this pass actually find and move
    # legacy content" (log non-empty), NOT to the marker gate above: seeding
    # it unconditionally on every first-ever pass (including a no-op one on
    # a brand-new project) would recreate the exact conflict Task 9 hit and
    # routed around for new_calibration — see
    # test_record_skips_token_mix_when_actual_lacks_a_total, which asserts
    # token_mix stays ABSENT on a fresh project's first write when there is
    # nothing to observe yet.
    if log and "token_mix" not in cal:
        from ruamel.yaml.comments import CommentedMap
        cal["token_mix"] = CommentedMap((("samples", []),))
        log.append("SEED token_mix (empty — new component, nothing to migrate from)")

    cal[CALIBRATION_METRICS_MARKER] = _now_iso()
    return log


def migrate_calibration_token_basis(y, cal, state_root: str) -> list:
    """Drop scope tokens_k samples measured on the pre-fresh basis. Once, in place.

    Those samples are `cache_inclusive_actual / fresh_scale_band`, so they carry a
    basis error of roughly three orders of magnitude (see FRESH_TOKEN_CLASSES).
    They cannot be repaired here: a stored sample is a bare rounded ratio, with no
    raw counts to recompute from. Purging is the only honest option, and it is
    enough -- the nodes still hold their per-class actuals, so the buckets refill
    correctly on the next closes, now on the right basis.

    What deliberately SURVIVES:

    - `token_mix` samples. They are per-class FRACTIONS of a total, so they never
      depended on which classes the scope basis counted. They are also what now
      projects cache_read at estimate time, and they are the only measured record
      of how extreme the real split is -- discarding them would throw away the
      evidence that motivated this change.
    - every non-tokens_k component. man_hours, hitl_hours and elapsed_hours were
      never measured in tokens and are untouched by the basis error.

    `version` stays 2. Compatibility here is by shape-tolerant reads and a
    positive marker, never a version gate.
    """
    if cal.get(TOKEN_BASIS_MARKER):
        return []

    log = []
    p = calibration_path(state_root)
    backup = p + ".pre-token-basis"
    if os.path.exists(p) and not os.path.exists(backup):
        import shutil
        shutil.copy2(p, backup)
        log.append(f"backup {os.path.basename(backup)}")

    for bucket, metrics in list((cal.get("scope") or {}).items()):
        if not hasattr(metrics, "items"):
            continue
        entry = metrics.get("tokens_k")
        if not hasattr(entry, "get"):
            continue
        n = len(entry.get("samples") or [])
        if n:
            entry["samples"] = []
            log.append(f"PURGE scope.{bucket}.tokens_k ({n} sample(s) measured against a "
                       f"cache-inclusive actual over a fresh-token band — unrecoverable, "
                       f"the stored form is a bare ratio; the bucket refills on the next closes)")

    cal[TOKEN_BASIS_MARKER] = _now_iso()
    return log


def _component_samples(cal, component: str, bucket: str, metric: str) -> list:
    node = ((cal.get(component) or {}).get(bucket) or {}).get(metric) or {}
    return list(node.get("samples") or [])


def active_scope_ratio(cal, classification: str, metric: str):
    if metric == "tokens_k" and not (cal or {}).get(TOKEN_BASIS_MARKER):
        # Pre-basis file: any tokens_k scope samples here were measured as a
        # cache-inclusive actual over a fresh-token band and are wrong by orders
        # of magnitude (see FRESH_TOKEN_CLASSES). The purge runs on the next
        # WRITE, but read-only callers -- estimate-story, estimate-rollup,
        # calibration show -- must not migrate, and must not apply them either.
        # Cold start is the correct answer until a write cleans the file.
        return None
    s = _component_samples(cal, "scope", classification, metric)
    return weighted_ratio(s) if len(s) >= MIN_SAMPLES else None


def active_closure_ratio(cal, level: str, metric: str):
    """Learned closure overhead, with zero samples excluded.

    A zero residual is a skip, not a sample of 0.0 -- `derive_closure_sample`
    refuses to create one and says why at length. That guard is write-side
    only, so it cannot help a file that already contains a zero: written by a
    version predating the guard, or by any path not yet identified (the
    2026-08-25 production report observed one whose origin no code path in
    2.4.7 explains). Filtering here repairs every such file on the next read,
    with no migration to run and no schema change.

    Excluded from the average AND from the count: three zeros plus one real
    sample is one sample, not four, and must stay inactive.
    """
    s = [v for v in _component_samples(cal, "closure", level, metric)
         if _is_number(v) and abs(float(v)) > 1e-9]
    return weighted_ratio(s) if len(s) >= MIN_SAMPLES else None


def active_orchestration_fraction(cal, level: str, metric: str):
    """Learned orchestration overhead as a FRACTION of the children's total.

    Every other component here (scope, closure) learns a RATIO: actual over
    an estimate, correcting a number that already exists. Orchestration has
    no such number to correct — the band ships `null` (spec §6.4) because
    every measurement available at design time was contaminated by an
    operational defect (repeated cache-eviction on blocking waits), and
    sizing a prior on contaminated data would commit that bug to every future
    estimate. So there is nothing to measure a ratio against, and a
    ratio-based component could never bootstrap from its first sample.

    Instead the sample IS the band: orchestration_actual / sum(children
    actual), directly observable from the first closed sprint or epic. A
    future maintainer tempted to "fix" this into a ratio for consistency with
    closure would remove the one thing that lets it start learning at all.

    None until MIN_SAMPLES, same decay as every other component.
    """
    samples = _component_samples(cal, "orchestration", level, metric)
    return weighted_ratio(samples) if len(samples) >= MIN_SAMPLES else None


def active_fix_factor(cal, classification: str):
    """Needs BOTH cohorts at threshold — one cohort alone cannot form a ratio."""
    entry = (cal.get("fix") or {}).get(classification) or {}
    clean, rework = entry.get("clean") or {}, entry.get("reworked") or {}
    if int(clean.get("samples", 0)) < MIN_SAMPLES or int(rework.get("samples", 0)) < MIN_SAMPLES:
        return None
    cm, rm = clean.get("mean_man_hours"), rework.get("mean_man_hours")
    if not _is_number(cm) or not _is_number(rm) or float(cm) == 0:
        return None
    return float(rm) / float(cm)


def _applied_scope_ratio(est, metric):
    """The scope ratio that was applied to `metric` when this estimate was written.

    `estimate-story` records one ratio PER METRIC (`scope_ratios`), because the
    five metrics calibrate independently. A single scalar `scope_ratio` is the
    older/manual form (`set-estimate --scope-ratio`) and is accepted as a
    fallback for every metric. Missing entirely -> 1.0.
    """
    m = est.get("scope_ratios")
    if hasattr(m, "get"):
        v = _num_or_none(m.get(metric))
        if v is not None and v > 0:
            return v
    v = _num_or_none(est.get("scope_ratio"))
    return v if v is not None and v > 0 else 1.0


def derive_story_sample(node, blocked_hours: float = 0.0):
    """Compute a story's scope samples and its fix cohort. None when not derivable.

    When `blocked_hours > 0`, `elapsed_hours` is deliberately absent from the
    returned sample's `scope_ratios`: wall-clock during blocked time includes
    human wait, and folding that into calibration would poison the scope ratio
    for future stories. Other metrics are unaffected -- `man_hours`,
    `hitl_hours` and `tokens_k` are assessed or counted, not measured against
    a wall-clock, so blocked time does not poison them. Design:
    docs/superpowers/specs/2026-09-25-story-lifecycle-blocked-design.md §5.

    THE SAMPLE MUST BE MEASURED AGAINST THE BASE BAND, NOT AGAINST THE LAST
    ESTIMATE. The estimate is `band_mid x scope_ratio_applied x fix_factor`, so a
    raw `actual / estimate` (or `actual x fix / estimate`) measures error against
    an estimate that already contains the previous ratio. Feeding that back as
    the next ratio makes the loop converge to sqrt(truth / band_mid) — a
    permanent underestimate no volume of data closes — and means a perfect
    estimate never produces a neutral sample. Dividing the applied ratio back
    out fixes both:

      exact   (fix_iterations == 0, the actual is pure scope):
          sample = actual x scope_ratio_applied x fix_factor / estimate
                 = actual / band_mid
      backout (rework present or unknown — the actual mixes scope and rework):
          scope portion is actual / fix_factor, so the fix factor cancels:
          sample = actual x scope_ratio_applied / estimate
                 = actual / (band_mid x fix_factor)
      legacy  (estimate predates the recorded factors): both default to 1.0,
          sample = actual / estimate, labelled `legacy` so an audit can tell
          the imprecision apart.
    """
    if not node:
        return None
    est, act = node.get("estimate") or {}, node.get("actual") or {}
    if not est or not act:
        return None

    iters = _iter_count((node.get("completion_evidence") or {}).get("fix_iterations"))
    has_factors = _is_number(est.get("fix_factor"))
    fix_factor = float(est["fix_factor"]) if has_factors else 1.0

    if not has_factors:
        provenance = "legacy"
    elif iters == 0:
        provenance = "exact"
    else:
        provenance = "backout"

    ratios = {}
    for metric in CALIBRATED_METRIC_FIELDS:
        if metric == "elapsed_hours" and blocked_hours and blocked_hours > 0:
            continue     # excluded per §5: wall-clock includes human wait time
        e_num, a_num = _estimate_metric(est, metric), _actual_metric(act, metric)
        if metric == "tokens_k":
            # Measure SCOPE against the fresh classes only -- on BOTH sides.
            #
            # The actual side is the defect being fixed: a cache-inclusive actual
            # over a fresh-scale band, ~1000x apart (see FRESH_TOKEN_CLASSES).
            # The estimate side matters just as much and is easy to miss: the
            # cancellation that reduces this expression to `actual / band_mid`
            # only holds while the denominator IS `band_mid x applied x fix`.
            # Since estimate-story now adds a projected cache_read on top of the
            # banded fresh total, `tokens_k.total` is no longer that quantity, and
            # dividing by it would reintroduce a basis error in the other
            # direction. The estimate's fresh sum is the banded quantity.
            a_tk, e_tk = (act or {}).get("tokens_k"), (est or {}).get("tokens_k")
            a_num = fresh_tokens(a_tk) if hasattr(a_tk, "get") else None
            if hasattr(e_tk, "get"):
                e_fresh = fresh_tokens(e_tk)
                e_num = e_fresh if e_fresh > 0 else e_num
            if a_num is not None and a_num <= 0:
                a_num = None      # no fresh tokens recorded -> no scope signal
        if e_num is None or a_num is None:
            continue          # missing, N/A, or non-numeric — never coerced to zero
        if e_num == 0:
            continue
        applied = _applied_scope_ratio(est, metric) if has_factors else 1.0
        if provenance == "backout":
            # actual/fix_factor is the scope portion; the fix_factor cancels.
            ratios[metric] = a_num * applied / e_num
        else:
            ratios[metric] = a_num * applied * fix_factor / e_num

    if not ratios:
        return None
    return {
        "classification": str(node.get("classification", "standard")),
        "provenance": provenance,
        "fix_iterations": iters,
        "scope_ratios": ratios,
        "actual_man_hours": float(act["man_hours"]) if _is_number(act.get("man_hours")) else None,
    }


def _bump_cohort(entry, cohort: str, man_hours):
    """Running mean over a cohort, so a full sample history is not needed."""
    from ruamel.yaml.comments import CommentedMap
    c = entry.get(cohort)
    if c is None:
        c = CommentedMap()
        c["mean_man_hours"] = 0.0
        c["samples"] = 0
        entry[cohort] = c
    if man_hours is None:
        return
    n = int(c.get("samples", 0))
    mean = float(c.get("mean_man_hours", 0.0))
    c["mean_man_hours"] = round((mean * n + man_hours) / (n + 1), 4)
    c["samples"] = n + 1


CALIBRATION_MARKER = "calibration_sampled_at"
# The orchestration sample is a SEPARATE fact from the actual/closure sample,
# and a sprint or epic node can carry both — one marker cannot gate both
# without one silently suppressing the other (a closed sprint's closure
# sample would forever block its later orchestration sample, or vice versa).
# So orchestration gets its own marker, using the exact same guard mechanism
# below (a `marker` parameter), rather than a second copy of the mechanism.
ORCHESTRATION_MARKER = "orchestration_sampled_at"


def _already_sampled(node, marker=CALIBRATION_MARKER):
    """The replay guard: a node that already emitted its sample carries a marker."""
    v = (node or {}).get(marker)
    return str(v) if v else None


def _mark_sampled(node, node_path, y=None, marker=CALIBRATION_MARKER) -> None:
    """Stamp the node so a second set-actual on it cannot double-count.

    Idempotency lives on the node, not in the caller: `--no-calibrate` only
    helps someone who remembers to pass it, and a duplicated sample is
    invisible afterwards.
    """
    if node is None or not node_path:
        return
    node[marker] = _now_iso()
    core._atomic_dump(y or _yaml(), node, node_path)


def record_story_sample(state_root: str, node, node_path: str | None = None, y=None) -> str:
    """Derive a story's calibration sample and append it to the shared file.

    A write path, unlike load_calibration: migrates a stale schema version
    before appending, so a v1 file is never mistaken for v2 and corrupted by
    samples landing in a structure that doesn't exist there yet. The whole
    load->mutate->save runs under one exclusive lock so parallel samplers
    cannot clobber each other's appends.
    """
    prior = _already_sampled(node)
    if prior:
        return f"sample already recorded at {prior} — skipped (replay)"
    story_key = str(node.get("key", "") or "").strip()
    blocked_hours = _total_blocked_hours(state_root, story_key)
    sample = derive_story_sample(node, blocked_hours=blocked_hours)
    if sample is None:
        return "no sample (missing estimate or actual)"
    if blocked_hours > 0:
        # Inline duration lets an operator eyeball whether the exclusion was
        # warranted -- a 5-minute block resolves quickly; a 6-day block obviously
        # doesn't -- without cross-referencing the event log. Per §5 of the design.
        sys.stderr.write(
            f"pm-status.py: WARN blocked story {story_key} — elapsed_hours "
            f"sample deferred (event log shows {blocked_hours:.1f}h in blocked); "
            f"man_hours, hitl_hours, tokens_k still recorded\n")
    from ruamel.yaml.comments import CommentedMap
    with calibration_lock(state_root):
        y_cal, cal = load_calibration(state_root)
        if cal.get("version") != CALIBRATION_SCHEMA_VERSION:
            cal = migrate_calibration(y_cal, cal, state_root)
        for line in migrate_calibration_metrics(y_cal, cal, state_root):
            sys.stderr.write(f"pm-status.py: calibration migration: {line}\n")
        for line in migrate_calibration_token_basis(y_cal, cal, state_root):
            sys.stderr.write(f"pm-status.py: calibration migration: {line}\n")
        cls = sample["classification"]
        act_model = (node.get("actual") or {}).get("model")

        bucket = cal["scope"].setdefault(cls, CommentedMap())
        for metric, ratio in sample["scope_ratios"].items():
            entry = bucket.setdefault(metric, CommentedMap())
            entry.setdefault("samples", [])
            entry["samples"].append(round(ratio, 4))
            if act_model:
                seen = entry.setdefault("models_seen", [])
                if act_model not in seen:
                    seen.append(act_model)

        # The observed per-class split, as a fraction of the actual's total —
        # feeds observed_mix() once 3 samples accrue, superseding
        # COLD_START_TOKEN_MIX. Independent of the scope-ratio samples above:
        # this is about how a token total divides across classes, not about
        # how big the total itself is.
        tk = (node.get("actual") or {}).get("tokens_k")
        if hasattr(tk, "get"):
            total = _num_or_none(tk.get("total"))
            if total and total > 0:
                mix_bucket = cal.setdefault("token_mix", CommentedMap())
                mix_bucket.setdefault("samples", [])
                mix_entry = {c: round((_num_or_none(tk.get(c)) or 0.0) / total, 4)
                             for c in TOKEN_CLASSES}
                if act_model:
                    mix_entry["model"] = act_model
                mix_bucket["samples"].append(mix_entry)

        fix_entry = cal["fix"].setdefault(cls, CommentedMap())
        iters = sample["fix_iterations"]
        if iters is not None:
            _bump_cohort(fix_entry, "clean" if iters == 0 else "reworked",
                         sample["actual_man_hours"])

        save_calibration(y_cal, cal, state_root)
    _mark_sampled(node, node_path, y)
    return (f"scope+{len(sample['scope_ratios'])} metrics, "
            f"provenance={sample['provenance']}, class={cls}")


CLOSURE_RANGE_KEYS = {
    "man_hours":     ("man_hours_low", "man_hours_high"),
    "hitl_hours":    ("hitl_hours_low", "hitl_hours_high"),
    "elapsed_hours": ("elapsed_hours_low", "elapsed_hours_high"),
    "tokens_k":      ("tokens_k_min", "tokens_k_max"),
}
# No "cost" row: cost is derived from the rolled-up tokens_k range (see
# cmd_estimate_rollup) rather than banded and calibrated on its own — the
# story-level equivalent of this was already true (BASE_BANDS has no cost
# row either). Keeping a separate closure-cost band was the last place the
# old defect survived: a cost figure with no arithmetic tie to the token
# figure it should track, drifting apart as the two calibrated independently.


# Wall-clock metrics legitimately go NEGATIVE as a closure residual: if a closure
# node's children ever overlap in wall-clock time, the parent's wall-clock can be
# below the sum of its children's by design (today's step files run children
# strictly in order, so this does not arise in practice; the check stays
# defensive). That is topology, not a miscount, and must not be reported as one.
# Man-hours, tokens and cost are additive regardless of concurrency, so a
# negative residual there really is a miscount.
WALL_CLOCK_METRICS = ("elapsed_hours",)


def _closure_nodes(state_root: str, level: str, epic_key: str, sprint_key=None):
    """(parent path, child paths) for a closure sample at `level`."""
    if level == "sprint":
        return (sprint_file(state_root, epic_key, sprint_key),
                list_story_files(state_root, epic_key, sprint_key))
    return (nodes.epic_file(state_root, epic_key),
            [sprint_file(state_root, epic_key, _sprint_key_from_dir(d))
             for d in list_sprint_dirs(state_root, epic_key)])


def _skip_summary(skipped: dict) -> str:
    return "; ".join(f"{m}: {r}" for m, r in skipped.items()) or "no metrics available"


def derive_closure_sample(state_root: str, level: str, epic_key: str, sprint_key=None):
    """Closure overhead = parent actual - sum(children actuals). Returns (sample, reason).

    THE RATIO'S DENOMINATOR MUST BE THE QUANTITY THE RATIO IS APPLIED TO.
    `estimate-rollup` applies the learned ratio to the CLOSURE BAND alone
    (`total x (1 + ratio x closure_band + fraction x ORCH_SPREAD)`), so the
    residual has to be divided by the ESTIMATED CLOSURE OVERHEAD ALONE, never
    by the whole parent estimate and never by closure-plus-orchestration.
    Dividing by the whole parent made learn and apply different quantities,
    and a perfectly consistent history moved the estimate AWAY from its own
    observed truth.

    THE ORCHESTRATION BAND IS NOT PART OF THIS DENOMINATOR. Since the
    orchestration term joined the roll-up, `pmid - sum(child estimates)` is
    the closure band PLUS the orchestration band, while the residual it
    divides (`parent actual - sum(children actual)`) is closure-only —
    orchestration lives in its own `orchestration` block, outside `actual`.
    Leaving the orchestration band in the denominator understated every
    closure sample by exactly the factor the two bands differ by (with an
    active fraction of 0.5 and children summing to 20, a true overhead of 5
    recorded as 0.3704 instead of 1.4286 — 3.9x low, and worse as the
    fraction grows). So the applied fraction (`estimate.orchestration_ratios`,
    the same divide-it-back-out record `closure_ratios` and `scope_ratios`
    are) is subtracted back off at its band MIDPOINT (`ORCH_MID`), leaving
    exactly `est_total x closure_ratio_applied x mid(COLD_START_CLOSURE_BAND)`
    — the quantity the closure ratio is applied to and nothing else.

    And, as with the story scope ratio, the estimated overhead already contains
    the ratio that was applied when the parent estimate was written, so that
    ratio is divided back out (`closure_ratios` on the estimate block, 1.0 when
    absent). Without it the loop settles on a geometric mean instead of the
    truth. Concretely: children estimated 40, closure overhead truly 8 every
    time. Estimated overhead cold-start = 47 - 40 = 7, sample 8/7 = 1.143, and
    `40 x (1 + 1.143 x 0.175) = 48.0` — the observed total, and stable on every
    later generation because the applied ratio cancels.

    Guards, each skipping just THAT METRIC with a reason rather than aborting
    the whole sample: any child missing that metric's actual (a partial sum
    understates overhead and biases the ratio low, permanently); a negative
    residual (a miscount — except for wall-clock, where parallel execution makes
    it expected); a ZERO residual (see below); an estimated overhead <= 0
    (nothing to measure against); and N/A tokens, which skips just that metric
    while man-hours still record under non-Claude runtimes where tokens are
    legitimately absent.

    A ZERO RESIDUAL IS A SKIP, NOT A SAMPLE OF 0.0 — and "zero" means within a
    relative tolerance, on both signs, not exactly 0.0 in binary. A parent actual
    equal to the sum of its children means the closure phases' own spend
    (adversarial analysis, retrospective, QA generation — real, measurable
    work) was attributed to nothing. Recording that as a legitimate 0.0
    sample is worse than recording nothing: 0.0 is not None, so after three
    such sprints `active_closure_ratio` returns 0.0, `cmd_estimate_rollup`
    accepts it, and the closure band contributes nothing to any future
    estimate — permanently, with no marker saying why. The step files now
    instruct the parent actual as "sum of children PLUS this level's own
    closure-phase spend" precisely so this does not arise; when it does, it
    is a capture defect and must be reported as one, not learned from. Both
    signs route to that one reason because a bare sum over decimal inputs lands
    on either side of zero depending on the values (0.3 + 0.6 vs 0.9 leaves
    +1.11e-16; 1.1 + 2.2 vs 3.3 leaves -4.44e-16), and calling the second a
    "miscount" would tell the reader something false.

    Iterates CALIBRATED_METRIC_FIELDS, not CLOSURE_RANGE_KEYS or the full
    METRIC_FIELDS: `cost` never produces a closure sample (Task 10) — it is
    derived from the rolled-up tokens_k range at estimate-rollup time, so a
    residual measured against its own band would have nothing left to divide
    against and nothing calibrating it downstream would ever read the sample.
    """
    ppath, child_paths = _closure_nodes(state_root, level, epic_key, sprint_key)
    if ppath is None:
        return None, f"{level} node not found"
    _, pnode = load_node(ppath)
    pact = (pnode or {}).get("actual") or {}
    pest = (pnode or {}).get("estimate") or {}
    if not pact:
        return None, f"{level} has no actual yet"

    children = []
    for cp in child_paths:
        if cp is None:
            children.append(None)
            continue
        _, cn = load_node(cp)
        children.append(cn)

    applied_ratios = pest.get("closure_ratios")
    applied_orch = pest.get("orchestration_ratios")
    closure, ratios, skipped = {}, {}, {}
    for metric in CALIBRATED_METRIC_FIELDS:
        total = 0.0
        complete = True
        for cn in children:
            cv = _actual_metric((cn or {}).get("actual"), metric) if cn is not None else None
            if cv is None:
                complete = False   # missing, N/A, or non-numeric child actual
                break
            total += cv
        if not complete:
            skipped[metric] = "a child is missing this metric's actual"
            continue
        pv = _actual_metric(pact, metric)
        if pv is None:
            skipped[metric] = f"{level} actual is missing or N/A for this metric"
            continue
        residual = pv - total
        # Near-zero is checked FIRST, and on BOTH signs. `residual` is unrounded
        # float arithmetic over decimal inputs, so `== 0` only catches a residual
        # that happens to land exactly on zero in binary. Children of 0.3 and 0.6
        # against a parent written as the bare sum 0.9 leave +1.11e-16, which
        # sails past `== 0` and records three 0.0 samples — C2 reopened, on
        # ordinary tenths-of-an-hour input. The mirror (1.1 + 2.2 vs 3.3) leaves
        # -4.44e-16 and would otherwise be reported as a miscount that did not
        # happen. One relative tolerance, both signs, one reason. The tolerance is
        # relative to the parent so it stays meaningful at any magnitude, and
        # floored at 1.0 so it never collapses to nothing for small values; at
        # 1e-9 it is many orders below the smallest real closure overhead and many
        # above double-precision summation noise.
        if abs(residual) <= 1e-9 * max(1.0, abs(pv)):
            skipped[metric] = (
                f"zero residual (parent {pv} equals children sum {total} to within float "
                f"tolerance) — this {level}'s own closure-phase spend was attributed to "
                f"nothing; a 0.0 sample would train the closure component to zero "
                f"permanently. Re-capture the {level} actual as children + this level's "
                f"closure-phase spend (metrics-contract.md §6)")
            continue
        if residual < 0:
            if metric in WALL_CLOCK_METRICS:
                skipped[metric] = (f"negative wall-clock residual (parent {pv} below children "
                                   f"sum {total}) — expected under parallel execution, not a miscount")
            else:
                skipped[metric] = (f"negative residual (parent {pv} below children sum "
                                   f"{total}) — miscounted")
            continue
        closure[metric] = residual

        lo, hi = CLOSURE_RANGE_KEYS[metric]
        pmid = _mid(pest, lo, hi)
        if pmid is None:
            skipped[metric] = f"{level} has no estimate range for this metric"
            continue
        est_total, all_est = 0.0, True
        for cn in children:
            v = _child_estimate_value(cn, metric) if cn is not None else None
            if v is None:
                all_est = False
                break
            est_total += v
        if not all_est:
            skipped[metric] = "a child is missing this metric's estimate"
            continue
        # Back out the orchestration band before dividing: `pmid - est_total` is
        # closure band PLUS orchestration band, and `residual` is closure-only.
        orch_f = 0.0
        if hasattr(applied_orch, "get"):
            f = _num_or_none(applied_orch.get(metric))
            if f is not None and f > 0:
                orch_f = f
        expected = pmid - est_total - est_total * orch_f * ORCH_MID
        if expected <= 0:
            skipped[metric] = (f"estimated closure overhead is {round(expected, 4)} (<= 0) — "
                               f"nothing to measure the residual against")
            continue
        applied = 1.0
        if hasattr(applied_ratios, "get"):
            a = _num_or_none(applied_ratios.get(metric))
            if a is not None and a > 0:
                applied = a
        ratios[metric] = residual * applied / expected

    if not closure:
        return None, "no metric produced a closure residual — " + _skip_summary(skipped)
    return {"level": level, "closure_actual": closure, "ratios": ratios,
            "skipped": skipped}, "ok"


def record_closure_sample(state_root: str, level: str, epic_key: str, sprint_key=None) -> str:
    """Derive a sprint/epic's closure sample and append it to the shared file.

    A write path, unlike load_calibration: migrates a stale schema version
    before appending, so a v1 file is never mistaken for v2 and corrupted by
    samples landing in a structure that doesn't exist there yet.
    """
    ppath, _ = _closure_nodes(state_root, level, epic_key, sprint_key)
    y_node, pnode = load_node(ppath) if ppath else (None, None)
    prior = _already_sampled(pnode)
    if prior:
        return f"sample already recorded at {prior} — skipped (replay)"

    sample, reason = derive_closure_sample(state_root, level, epic_key, sprint_key)
    if sample is None:
        return f"no closure sample: {reason}"
    if not sample["ratios"]:
        return "no closure sample: " + _skip_summary(sample["skipped"])

    from ruamel.yaml.comments import CommentedMap
    with calibration_lock(state_root):
        y, cal = load_calibration(state_root)
        if cal.get("version") != CALIBRATION_SCHEMA_VERSION:
            cal = migrate_calibration(y, cal, state_root)
        for line in migrate_calibration_metrics(y, cal, state_root):
            sys.stderr.write(f"pm-status.py: calibration migration: {line}\n")
        for line in migrate_calibration_token_basis(y, cal, state_root):
            sys.stderr.write(f"pm-status.py: calibration migration: {line}\n")
        bucket = cal["closure"].setdefault(level, CommentedMap())
        for metric, ratio in sample["ratios"].items():
            entry = bucket.setdefault(metric, CommentedMap())
            entry.setdefault("samples", [])
            entry["samples"].append(round(ratio, 4))
        save_calibration(y, cal, state_root)
    _mark_sampled(pnode, ppath, y_node)
    note = f"closure {level} +{len(sample['ratios'])} metrics"
    if sample["skipped"]:
        note += f" (skipped — {_skip_summary(sample['skipped'])})"
    return note


def record_orchestration_sample(state_root: str, level: str, epic_key: str,
                                 sprint_key=None) -> str:
    """Append one closed sprint/epic's orchestration-vs-children fraction.

    THE FRACTION, NOT A RATIO. Every other component here (scope, closure)
    learns a ratio — actual over an ESTIMATE, correcting a number that
    already exists. Orchestration has nothing to correct: the band ships
    `null` by design, because every number available when this was built was
    contaminated by an operational defect (roughly thirty blocking waits each
    outlived the prompt cache and re-created a ~93k-token prefix), and sizing
    a prior on that would commit the bug to every future estimate. So there
    is no estimate to divide by, and a ratio-based component could never
    bootstrap — it would need the very thing it doesn't have. Instead the
    sample IS the band: orchestration_actual / sum(children actual), directly
    observable from the first closed sprint or epic. Do not "fix" this into a
    ratio for consistency with closure — that would remove the one thing
    that lets it start learning at all.

    THE DENOMINATOR MUST BE COMPLETE, per metric, the same guard
    derive_closure_sample applies to its residual: if any child that exists
    is missing that metric's actual, the sum silently understates the true
    total and the fraction is inflated — a wrong number that looks right, and
    permanently so once it feeds calibration. So a metric is sampled only
    when EVERY child carries a numeric actual for it; a partial sum is
    treated as no sample, not as a smaller one.

    `cost` is deliberately absent from CALIBRATED_METRIC_FIELDS: it is
    derived from tokens x rates, so its fraction is already implied by the
    tokens_k fraction and a second, independently-drifting copy would add
    nothing but disagreement.

    REPLAY-GUARDED, like every other record_*_sample here: a second
    `set-actual --block orchestration` on the same node (a retry, a
    corrected number, a replayed closure step) must not append a second
    sample and skew the learned fraction with nothing on disk to explain it.
    Gated on its own ORCHESTRATION_MARKER rather than the closure/story
    CALIBRATION_MARKER, because a sprint or epic node carries both an
    actual/closure sample and an orchestration sample — one marker would let
    whichever writes first silently suppress the other. `_closure_nodes`
    resolves the same parent path for both sprint and epic level, so this
    one guard covers both without a level-specific branch.
    """
    ppath, cpaths = _closure_nodes(state_root, level, epic_key, sprint_key)
    if ppath is None:
        return ""
    y_node, pnode = load_node(ppath)
    prior = _already_sampled(pnode, marker=ORCHESTRATION_MARKER)
    if prior:
        return f"sample already recorded at {prior} — skipped (replay)"
    orch = (pnode or {}).get("orchestration") or {}
    if not orch:
        return ""

    children = []
    for cp in cpaths:
        if cp is None:
            children.append(None)
            continue
        _, cn = load_node(cp)
        children.append(cn)

    from ruamel.yaml.comments import CommentedMap
    recorded, skipped = {}, {}
    for metric in CALIBRATED_METRIC_FIELDS:
        over = _actual_metric(orch, metric)
        if over is None:
            continue  # orchestration itself has no actual for this metric
        total, complete = 0.0, True
        for cn in children:
            cv = _actual_metric((cn or {}).get("actual"), metric) if cn is not None else None
            if cv is None:
                complete = False
                break
            total += cv
        if not complete:
            skipped[metric] = "a child is missing this metric's actual"
            continue
        if total <= 0:
            skipped[metric] = "children's total is zero or negative — nothing to divide by"
            continue
        recorded[metric] = round(over / total, 4)

    if not recorded:
        return "" if not skipped else "no orchestration sample: " + _skip_summary(skipped)

    with calibration_lock(state_root):
        y, cal = load_calibration(state_root)
        if cal.get("version") != CALIBRATION_SCHEMA_VERSION:
            cal = migrate_calibration(y, cal, state_root)
        for line in migrate_calibration_metrics(y, cal, state_root):
            sys.stderr.write(f"pm-status.py: calibration migration: {line}\n")
        for line in migrate_calibration_token_basis(y, cal, state_root):
            sys.stderr.write(f"pm-status.py: calibration migration: {line}\n")
        bucket = cal.setdefault("orchestration", CommentedMap()).setdefault(level, CommentedMap())
        for metric, frac in recorded.items():
            entry = bucket.setdefault(metric, CommentedMap())
            entry.setdefault("samples", [])
            entry["samples"].append(frac)
        save_calibration(y, cal, state_root)
    _mark_sampled(pnode, ppath, y_node, marker=ORCHESTRATION_MARKER)

    note = f"orchestration {level} +{len(recorded)} metrics"
    if skipped:
        note += f" (skipped — {_skip_summary(skipped)})"
    return note


def actual_event_times(state_root: str) -> dict:
    """{story key: ts of its latest `actual` event}, from state/events.jsonl.

    The one honest source for "when did this story close". `updated_at` is not:
    any field write overwrites it, so it dates the last edit rather than the
    closure. Used by `redrive_story_samples` to rebuild calibration samples in
    the chronological order the original appends had -- see the refusal there
    for why an incomplete answer is not usable.
    """
    idx: dict = {}
    p = events_path(state_root)
    if not os.path.isfile(p):
        return idx
    try:
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue  # a torn or hand-mangled line must not kill the rebuild
                if not isinstance(ev, dict):
                    continue
                if ev.get("event") != "actual" or ev.get("node") != "story":
                    continue
                k = ev.get("key")
                if not k:
                    continue
                k = _indexable_key(k)              # `k not in idx` raises on an unhashable k
                if k is None:
                    continue
                ts = str(ev.get("ts", ""))
                if k not in idx or ts >= idx[k]:
                    idx[k] = ts
    except OSError as e:
        raise PMError(2, f"could not read the event log at {p}: {e}") from e
    return idx


def redrive_story_samples(state_root: str) -> dict:
    """Rebuild `scope` and `fix` from the nodes on disk. Returns a report.

    Unlike the token-basis purge, this recovers rather than discards: a stored sample is
    a bare ratio with nothing behind it, but the NODES still hold every input
    `derive_story_sample` needs -- estimate, actual, and completion_evidence. So a batch
    of samples derived under a bug can simply be derived again, correctly, instead of
    being thrown away and waited for.

    Which is what this is for. `set-field` stored `fix_iterations` as text, and the
    provenance test depended on that text parsing as an int: a story that needed no rework
    was read as `backout`, its scope ratio divided by the 1.25 fix factor it never
    incurred, and the `clean` cohort never filled -- so the `fix` component could not
    activate at all. Every story closed under that behaviour is wrong in the same
    direction, and every one of them is repairable from disk.

    Only `scope` and `fix` are rebuilt. `closure`, `orchestration` and `token_mix` derive
    from different inputs and were never affected, so they are left exactly as they are.

    Samples are re-appended in CLOSURE order, taken from each story's `actual` event in
    state/events.jsonl -- not in the order the tree walk visits them. `weighted_ratio`
    weights the last entry most, so order is load-bearing, and directory order is not a
    neutral substitute for it. Raises PMError(2) without writing anything when that order
    cannot be established for every sampled story.
    """
    from ruamel.yaml.comments import CommentedMap
    report = {"stories": 0, "sampled": 0, "provenance": {}, "skipped": 0}
    with calibration_lock(state_root):
        # Pass 1 -- gather, mutating nothing. The refusal below has to be able to
        # leave the file and the backup untouched, so no write happens until the
        # ordering is known to be establishable.
        gathered = []
        for status in STATUS_DIRS:
            base = os.path.join(state_root, status)
            if not os.path.isdir(base):
                continue
            for ed in sorted(os.listdir(base)):
                if not ed.startswith("epic-"):
                    continue
                ekey = "E" + ed.split("-", 1)[1]
                for sd in sorted(list_sprint_dirs(state_root, ekey) or []):
                    skey = _sprint_key_from_dir(sd)
                    for sf in sorted(list_story_files(state_root, ekey, skey) or []):
                        report["stories"] += 1
                        try:
                            _, node = load_node(sf)
                        except Exception:                     # noqa: BLE001
                            report["skipped"] += 1
                            continue
                        sample = derive_story_sample(node)
                        if sample is None:
                            report["skipped"] += 1
                            continue
                        key = str(node.get("key") or
                                  os.path.splitext(os.path.basename(sf))[0])
                        gathered.append((key, sample))

        # Pass 2 -- restore chronological order, or refuse. `weighted_ratio` weighs the LAST
        # sample most, and the originals were appended in closure order. Rebuilding by walking
        # the tree gives key order, and STATUS_DIRS puts archived epics LAST, so the oldest work
        # would collect the highest weight -- observed as a ~16% rise on `complex`, from a
        # command that advertises itself as a repair. Refusing on an incomplete answer, not
        # falling back to directory order, follows `adr-reserve`/`AdrHomeUnresolved`: a
        # confidently wrong result with a success code is worse than none, and `--no-events`
        # means a log can exist without covering every story.
        if gathered:
            times = actual_event_times(state_root)
            missing = sorted({k for k, _ in gathered if not times.get(k)})
            if missing:
                shown = ", ".join(missing[:5]) + ("..." if len(missing) > 5 else "")
                raise PMError(2,
                    f"redrive: cannot establish closure order for {len(missing)} of "
                    f"{len(gathered)} sampled stories -- no `actual` event in "
                    f"{events_path(state_root)} for: {shown}. Calibration ratios are "
                    f"recency-weighted, so rebuilding in directory order would invert "
                    f"the weighting rather than repair it (archived epics sort last "
                    f"and would weigh most). Nothing written; the calibration file is "
                    f"unchanged. This is expected on a project predating the event log, "
                    f"or one whose actuals were written with --no-events.")
            gathered.sort(key=lambda g: (times[g[0]], g[0]))

        # Pass 3 -- write.
        y, cal = load_calibration(state_root)
        backup = calibration_path(state_root) + ".pre-redrive"
        if os.path.exists(calibration_path(state_root)) and not os.path.exists(backup):
            import shutil
            shutil.copy2(calibration_path(state_root), backup)
            report["backup"] = os.path.basename(backup)

        cal["scope"] = CommentedMap()
        cal["fix"] = CommentedMap()

        for _key, sample in gathered:
            cls = sample["classification"]
            bucket = cal["scope"].setdefault(cls, CommentedMap())
            for metric, ratio in sample["scope_ratios"].items():
                entry = bucket.setdefault(metric, CommentedMap())
                entry.setdefault("samples", [])
                entry["samples"].append(round(ratio, 4))
            iters = sample["fix_iterations"]
            if iters is not None:
                _bump_cohort(cal["fix"].setdefault(cls, CommentedMap()),
                             "clean" if iters == 0 else "reworked",
                             sample["actual_man_hours"])
            report["sampled"] += 1
            pv = sample["provenance"]
            report["provenance"][pv] = report["provenance"].get(pv, 0) + 1
        save_calibration(y, cal, state_root)
    return report


def cmd_calibration(args) -> int:
    if getattr(args, "action", "show") == "redrive":
        # Through _run_core: redrive refuses with PMError(2) when it cannot establish
        # closure order, and main() has no PMError handler of its own -- without this
        # the refusal would surface as a traceback and exit 1 instead of the documented
        # exit 2 with its message.
        def _redrive() -> int:
            rep = redrive_story_samples(args.state_root)
            if rep.get("backup"):
                sys.stdout.write(f"backup {rep['backup']}\n")
            prov = " ".join(f"{k}={v}" for k, v in sorted(rep["provenance"].items()))
            sys.stdout.write(
                f"OK calibration redrive — stories seen {rep['stories']}, "
                f"samples rebuilt {rep['sampled']}, skipped {rep['skipped']}"
                + (f" [{prov}]" if prov else "") + "\n")
            sys.stdout.write("scope and fix rebuilt from the nodes in closure order (from "
                             "events.jsonl); closure, orchestration and token_mix untouched.\n")
            sys.stdout.write("Ratios are recency-weighted, so estimates for unstarted stories "
                             "may move even where no sample changed — re-run estimate-story to "
                             "see current numbers.\n")
            return 0
        return _run_core(_redrive)
    if getattr(args, "action", "show") == "migrate-metrics":
        with calibration_lock(args.state_root):
            y, cal = load_calibration(args.state_root)
            if cal.get("version") != CALIBRATION_SCHEMA_VERSION:
                cal = migrate_calibration(y, cal, args.state_root)
            log = migrate_calibration_metrics(y, cal, args.state_root)
            # Same explicit entry point, because an operator reaching for a migration
            # wants the file correct, not correct-except-for-one-component. Both are
            # separately marker-gated, so running this on an already-migrated file is
            # a no-op rather than a second purge.
            log = log + migrate_calibration_token_basis(y, cal, args.state_root)
            save_calibration(y, cal, args.state_root)
        for line in log:
            sys.stdout.write(line + "\n")
        sys.stdout.write(f"OK calibration migrate-metrics ({len(log)} changes)\n")
        return 0

    _, cal = load_calibration(args.state_root)
    exists = os.path.exists(calibration_path(args.state_root))

    mixed_buckets = []
    for c in CLASSIFICATIONS:
        for m in CALIBRATED_METRIC_FIELDS:
            entry = ((cal.get("scope") or {}).get(c) or {}).get(m) or {}
            seen = entry.get("models_seen") or []
            if len(seen) > 1:
                mixed_buckets.append(f"{c}/{m} ({', '.join(seen)})")
    if mixed_buckets:
        sys.stdout.write(
            "WARN: scope calibration contains mixed-model samples — ratios may be unreliable.\n"
            "Consider `calibration redrive` after settling on one model:\n"
        )
        for b in mixed_buckets:
            sys.stdout.write(f"  {b}\n")

    rows = []
    for c in CLASSIFICATIONS:
        for m in CALIBRATED_METRIC_FIELDS:  # cost never scope-calibrates (derived, see above)
            n = len(_component_samples(cal, "scope", c, m))
            r = active_scope_ratio(cal, c, m)
            rows.append(("scope", f"{c}/{m}", n, r))
    for lv in CLOSURE_LEVELS:
        # Closure no longer calibrates `cost` on its own (Task 10): the rolled-up
        # cost is now derived from the rolled-up tokens_k range, so this loop
        # moves onto CALIBRATED_METRIC_FIELDS like the scope loop above, rather
        # than the full METRIC_FIELDS it used while closure cost was still real.
        for m in CALIBRATED_METRIC_FIELDS:
            n = len(_component_samples(cal, "closure", lv, m))
            r = active_closure_ratio(cal, lv, m)
            rows.append(("closure", f"{lv}/{m}", n, r))
    for lv in CLOSURE_LEVELS:
        # Orchestration never calibrates `cost` (derived from tokens x
        # rates — see record_orchestration_sample), so this loop uses
        # CALIBRATED_METRIC_FIELDS, exactly like the scope and closure loops
        # above. All three agree; none of them iterates the full METRIC_FIELDS
        # any more.
        for m in CALIBRATED_METRIC_FIELDS:
            n = len(_component_samples(cal, "orchestration", lv, m))
            r = active_orchestration_fraction(cal, lv, m)
            rows.append(("orchestration", f"{lv}/{m}", n, r))
    for c in CLASSIFICATIONS:
        entry = (cal.get("fix") or {}).get(c) or {}
        n = min(int((entry.get("clean") or {}).get("samples", 0)),
                int((entry.get("reworked") or {}).get("samples", 0)))
        rows.append(("fix", c, n, active_fix_factor(cal, c)))

    if getattr(args, "format", "text") == "json":
        import json
        sys.stdout.write(json.dumps({
            "exists": exists,
            "granularity": cal.get("granularity", "story"),
            "components": [{"component": a, "bucket": b, "samples": n,
                            "active_ratio": r} for a, b, n, r in rows],
        }, indent=2) + "\n")
        return 0

    if not exists:
        sys.stdout.write("No calibration file yet — all components cold-start.\n")
    sys.stdout.write(f"granularity: {cal.get('granularity', 'story')}\n")
    sys.stdout.write(f"{'COMPONENT':<14} {'BUCKET':<22} {'SAMPLES':>7}  RATIO\n")
    for a, b, n, r in rows:
        shown = f"{r:.3f}" if r is not None else f"(cold-start, needs {MIN_SAMPLES})"
        sys.stdout.write(f"{a:<14} {b:<22} {n:>7}  {shown}\n")
    return 0


# The orchestration fraction (active_orchestration_fraction) is a point
# estimate; these widen it into a range the same way COLD_START_CLOSURE_BAND
# widens the closure ratio. There is NO cold-start pair here, unlike closure
# — and that asymmetry is deliberate, not an oversight to "fix" by adding one.
# While the component is inactive (< MIN_SAMPLES) the fraction is 0 and the
# band contributes nothing to the roll-up at all; a cold-start orchestration
# band would put a number on a quantity this rework explicitly refuses to
# guess (see active_orchestration_fraction's docstring — every pre-existing
# measurement was contaminated by a cache-eviction defect). The stderr
# warning `cmd_estimate_rollup` emits while unseeded is what stands in for
# that number instead.
ORCH_SPREAD = (0.8, 1.2)

# The orchestration band's contribution to the roll-up MIDPOINT, per unit of
# applied fraction. `derive_closure_sample` subtracts `est_total x fraction x
# ORCH_MID` off the parent estimate midpoint so what remains is the closure
# band alone — the quantity the closure ratio is actually applied to. Derived
# from ORCH_SPREAD rather than restated as `1.0`, so widening the spread
# asymmetrically can never silently desynchronise the two.
ORCH_MID = (ORCH_SPREAD[0] + ORCH_SPREAD[1]) / 2.0


def _child_estimate_value(node, metric):
    """A child's value for `metric`: single-value form first (a story), else
    the midpoint of its range form (a sprint). None if neither is present.

    Reuses CLOSURE_RANGE_KEYS (metric -> parent low/high key names) rather
    than a second near-duplicate mapping, and `_estimate_metric` (not a local
    unwrap) for the single-value read — see that function's docstring for why
    duplicating the tokens_k unwrap here is exactly the mistake to avoid.
    """
    est = (node or {}).get("estimate") or {}
    v = _estimate_metric(est, metric)
    if v is not None:
        return v
    lo, hi = CLOSURE_RANGE_KEYS[metric]
    return _mid(est, lo, hi)
