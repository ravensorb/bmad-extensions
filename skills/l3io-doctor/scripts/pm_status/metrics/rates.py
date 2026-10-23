"""pm_status.metrics.rates -- token classes, the per-model rate table, and pricing.

The four token classes (`input`, `output`, `cache_write`, `cache_read`), the
USD-per-1M table with its config overrides, `cost_from_tokens`, the fresh-token
subset the estimate bands are measured against, and `tokens_block`.

`cost` is DERIVED here and nowhere else: the HARD RULE says it is never entered,
so `set-actual`/`set-estimate` reject a `--cost*` flag and `verify` recomputes
through `cost_from_tokens`. Keeping the rate table in one module is what makes
that single derivation point real rather than a convention.

`COLD_START_TOKEN_MIX` sits here, not in `estimates`, because it is a statement
about token CLASSES -- it only ever splits a total across the four names this
module defines. Putting it with the estimate engine made `rates` and `estimates`
reference each other in both directions.
"""

from __future__ import annotations

import json
import sys

from ..core import (
    _die_usage,
    _is_number,
    _num_or_none,
)

TOKEN_CLASSES = ("input", "output", "cache_write", "cache_read")

# USD per 1M tokens, Anthropic first-party API rates as of 2026-06-24.
# cache_write is 1.25x input; cache_read is 0.1x input.
# Partner-operated platforms (Bedrock, Vertex) price separately and need a
# config override at modules.l3io-pm.token_rates.
TOKEN_RATES = {
    "claude-opus-5":      {"input": 5.00,  "output": 25.00, "cache_write": 6.25,  "cache_read": 0.50},
    "claude-opus-5-fast": {"input": 10.00, "output": 50.00, "cache_write": 12.50, "cache_read": 1.00},
    "claude-fable-5":     {"input": 10.00, "output": 50.00, "cache_write": 12.50, "cache_read": 1.00},
    "claude-sonnet-5":    {"input": 3.00,  "output": 15.00, "cache_write": 3.75,  "cache_read": 0.30},
    "claude-sonnet-4-6":  {"input": 3.00,  "output": 15.00, "cache_write": 3.75,  "cache_read": 0.30},
    "claude-haiku-4-5":   {"input": 1.00,  "output": 5.00,  "cache_write": 1.25,  "cache_read": 0.10},
    # OpenAI — verify at https://openai.com/api/pricing before use.
    # Retired models retained for historical actuals verification:
    "codex-1":            {"input": 5.00,  "output": 30.00, "cache_write": 6.25,  "cache_read": 2.50},  # retired; original o3-based Codex Cloud
    "gpt-5":              {"input": 5.00,  "output": 30.00, "cache_write": 6.25,  "cache_read": 2.50},  # ambiguous; verify before use
    "gpt-5.4":            {"input": 2.50,  "output": 10.00, "cache_write": 3.13,  "cache_read": 1.25},  # retired 2026-08-31; succeeded by gpt-5.6-terra/luna in Codex
    # GPT-5.6 family (GA 2026-07-09): Sol/Terra/Luna.
    # Sol input/output/cache_read are promotional through 2026-11-21; cache_write is 1.25×
    # the original $5.00 standard input rate and did not move with the promotion.
    "gpt-5.6-sol":        {"input": 4.00,  "output": 20.00, "cache_write": 6.25,  "cache_read": 0.40},
    "gpt-5.6-terra":      {"input": 2.00,  "output": 12.00, "cache_write": 2.50,  "cache_read": 0.20},
    "gpt-5.6-luna":       {"input": 0.20,  "output":  1.20, "cache_write": 0.25,  "cache_read": 0.02},
}


def resolve_rates(model: str, overrides=None) -> dict:
    """The rate card for `model`, config overrides winning per model.

    An unknown model is a KeyError, never a default. A silently-wrong rate is
    exactly the failure this whole change exists to remove: the same token count
    prices 2x apart between a $5/M and a $10/M tier.
    """
    table = dict(TOKEN_RATES)
    if overrides:
        for k, v in overrides.items():
            table[k] = {**table.get(k, {}), **v}
    if model not in table:
        raise KeyError(f"unknown model {model!r} — add it to modules.l3io-pm.token_rates "
                       f"or use one of {sorted(table)}")
    return table[model]


def cost_from_tokens(tokens: dict, model: str, overrides=None) -> float:
    """USD for a per-class token count. `tokens` values are in THOUSANDS, rates
    are per million, hence the /1000."""
    rates = resolve_rates(model, overrides)
    total = 0.0
    for cls in TOKEN_CLASSES:
        v = _num_or_none((tokens or {}).get(cls))
        if v is None:
            continue
        # An override-only model can define a subset of the four classes. A bare
        # rates[cls] would surface as KeyError('cache_read') — which callers
        # print verbatim as e.args[0], giving the user the single word
        # "cache_read". Same hard-error policy as an unknown model, but with a
        # message that says what to do.
        if cls not in rates:
            raise KeyError(f"model {model!r} has no {cls!r} rate — modules.l3io-pm.token_rates "
                           f"must define all of {list(TOKEN_CLASSES)} for a model it adds")
        total += v * rates[cls]
    return round(total / 1000.0, 2)


FRESH_TOKEN_CLASSES = ("input", "output", "cache_write")
"""The classes a story's SIZE predicts.

`cache_read` is deliberately absent. It is a function of corpus size times agent
count -- how much context each dispatched agent re-reads -- not of how much work
the story asks for. A story that touches one file in a large repo reads the same
corpus as one that touches ten. Folding it into the scope basis made the ratio
measure the repo, not the story.

This is not theoretical. BASE_BANDS' tokens_k numbers (20-200k) were authored as
fresh-token bands, but actuals are captured cache-inclusive: one observed story
measured 182,121k with 97.4% of it cache reads. Dividing a cache-inclusive actual
by a fresh-scale band gave a scope ratio absorbing a ~1000x basis gap in silence,
and the per-class evidence is unambiguous about it being a basis error rather
than a real signal -- the complex bucket read 285.291 across five samples that
straddled the accounting change, while standard read 7.386 across three that did
not. Only the poisoned bucket moved.

cache_read is still captured, still priced, and still rolled up. It is simply not
what `scope` learns from; it belongs to the orchestration term, which is measured
as a fraction of children rather than predicted from a band.
"""


def fresh_tokens(block) -> float:
    """Sum of the fresh classes in a tokens_k mapping. 0.0 for a non-mapping."""
    if not hasattr(block, "get"):
        return 0.0
    return sum(_num_or_none(block.get(c)) or 0.0 for c in FRESH_TOKEN_CLASSES)


def fresh_share(mix: dict) -> float:
    """The fraction of a token mix that is fresh. Guarded against a degenerate mix."""
    f = sum(float(mix.get(c, 0.0)) for c in FRESH_TOKEN_CLASSES)
    return f if f > 0 else sum(COLD_START_TOKEN_MIX[c] for c in FRESH_TOKEN_CLASSES)


def tokens_block(counts: dict):
    """A tokens_k mapping: the four classes plus their validated total.

    `total` is stored rather than recomputed on read so that a node remains
    self-describing when read by anything that does not know the class list.
    It is always the sum — never an independently-entered number.
    """
    from ruamel.yaml.comments import CommentedMap

    tk = CommentedMap()
    total = 0.0
    for cls in TOKEN_CLASSES:
        v = _num_or_none(counts.get(cls)) or 0.0
        tk[cls] = int(v) if float(v).is_integer() else v
        total += v
    out = CommentedMap()
    out["total"] = int(total) if float(total).is_integer() else round(total, 2)
    for cls in TOKEN_CLASSES:
        out[cls] = tk[cls]
    return out


def rate_overrides(args):
    """Parse --token-rates into the overrides dict resolve_rates expects."""
    raw = getattr(args, "token_rates", "") or ""
    if not raw.strip():
        return None
    try:
        return json.loads(raw)
    except ValueError as e:
        _die_usage(f"--token-rates is not valid JSON: {e}")


def cmd_rates(args) -> int:
    """Print the effective rate table. Read-only; exists so the value actually in
    force — including any --token-rates override — is inspectable without
    reading source or guessing."""
    overrides = rate_overrides(args)
    # The EFFECTIVE table, per design §5 — so an override-only model (one that
    # exists solely in modules.l3io-pm.token_rates, e.g. a Bedrock or Vertex
    # rate card) is listed rather than silently omitted. Listing sorted(TOKEN_RATES)
    # alone made `rates` report the shipped defaults while pricing used something
    # else, which is the one thing this read-only subcommand exists to prevent.
    models = [args.model] if args.model else sorted(set(TOKEN_RATES) | set(overrides or {}))
    for m in models:
        try:
            r = resolve_rates(m, overrides)
        except KeyError as e:
            # e.args[0], not str(e) — KeyError.__str__ repr-quotes its argument,
            # which would double-wrap a message that already reads as prose.
            sys.stderr.write(f"pm-status.py: {e.args[0]}\n")
            return 2
        # `r.get`, not `r[...]`: an override-only model (one this table has no
        # shipped defaults to merge over) can legitimately define a subset of
        # the four classes, and listing it must report the gap rather than
        # raise KeyError on the model the user added by hand.
        cells = "  ".join(f"{c}=" + (f"{r[c]:.2f}" if _is_number(r.get(c)) else "n/a")
                          for c in TOKEN_CLASSES)
        sys.stdout.write(f"{m:<22} {cells}\n")
    return 0


# Cold-start assumption about a healthy, cache-warm run. NOT a calibrated
# ratio and not a component of its own: it is replaced by the observed mean
# once three story samples carry class data (see observed_mix below). It
# affects only how a banded TOTAL is SPLIT across classes — the banded total
# itself is untouched by it.
COLD_START_TOKEN_MIX = {"input": 0.15, "output": 0.05,
                        "cache_write": 0.30, "cache_read": 0.50}
