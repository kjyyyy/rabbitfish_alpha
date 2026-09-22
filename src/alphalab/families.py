"""Mechanism families (Hubble / XAlpha B-layer).

Grouping factors by the mechanism they express does three things:
  * diagnostics: which families actually survive out of sample
  * diversity: cap how many near-identical mechanisms enter the library
  * search allocation: the bandit scheduler spends effort per family

The classifier is deliberately simple and deterministic - it reads the AST,
not an LLM - so a factor's family never changes between runs."""
from __future__ import annotations

import ast
import re

from .expr import OPS, parse

FAMILIES = ("trend", "reversal", "volatility", "range", "price_volume", "liquidity", "other")

_VOL_OPS = {"Std", "Var", "Skew", "Kurt", "Mad"}
_TREND_OPS = {"Slope", "EMA", "WMA", "Rsquare", "Resi", "Sum", "Mean"}
_EXTREME_OPS = {"Max", "Min", "IdxMax", "IdxMin", "Quantile", "Med", "Rank"}


def classify(expr: str) -> str:
    tree = parse(expr)
    ops = [n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call)]
    fields = {n.id[2:] for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id.startswith("F_")}
    has_vol_field = bool(fields & {"volume", "amount"})
    has_range = bool(fields & {"high", "low"}) or bool(_EXTREME_OPS & set(ops))
    corr_like = any(o in ("Corr", "Cov") for o in ops)
    horizon = max([int(m) for m in re.findall(r",\s*(\d+)\s*\)", expr)] or [0])

    if corr_like and has_vol_field:
        return "price_volume"
    if has_vol_field and not has_range:
        return "liquidity" if any(o in ("Mean", "Sum", "Med") for o in ops) else "price_volume"
    if set(ops) & _VOL_OPS:
        return "volatility"
    if has_range:
        return "range"
    if set(ops) & _TREND_OPS or "Ref" in ops:
        # short look-backs on price are reversal bets; long ones are trend bets
        return "reversal" if 0 < horizon <= 20 else "trend"
    return "other"


def diagnostics(rows) -> dict:
    """Per-family counts and survival, for the run summary."""
    out = {}
    for f in FAMILIES:
        sub = [r for r in rows if r.get("family") == f]
        if not sub:
            continue
        strong = [r for r in sub if r["ic_t"] >= 3]
        out[f] = dict(
            evaluated=len(sub), t_ge_3=len(strong),
            kept=sum(r.get("status") in ("active", "probation") for r in sub),
            mean_ic=float(sum(r["ic_mean"] for r in sub) / len(sub)),
            mean_later_ic_of_t3=(float(sum(r["later_ic_mean"] for r in strong) / len(strong))
                                 if strong else None))
    return out


def family_cap(rows, per_family: int) -> list:
    """Keep at most `per_family` survivors per mechanism family (diversity)."""
    seen, kept = {}, []
    for r in sorted(rows, key=lambda r: -abs(r["ic_t"])):
        f = r.get("family", "other")
        if seen.get(f, 0) < per_family:
            seen[f] = seen.get(f, 0) + 1
            kept.append(r)
    return kept


assert set(OPS)                      # keep the import meaningful for linters
