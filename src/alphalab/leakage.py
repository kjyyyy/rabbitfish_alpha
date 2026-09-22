"""Dynamic look-ahead test: future-noise perturbation.

The static AST check (expr.py) blocks the obvious forms - negative Ref shifts,
future fields. It cannot catch leakage that arises from how an expression is
computed. So every candidate also faces an empirical test:

  1. evaluate the factor on a synthetic panel
  2. replace ALL data after a cut date with noise
  3. re-evaluate

A past-only factor is bit-identical up to the cut date. Anything that moves
has seen the future, and is rejected before it ever reaches real data.

(Truncating the end date does NOT work as a test with Qlib: it computes over
the whole stored series and slices afterwards, so a leaky formula looks clean.
Verified experimentally - hence this module.)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .evalexpr import evaluate, synthetic_panel


def future_noise_test(expr: str, cut: float = 0.6, seed: int = 0, tol: float = 1e-8):
    """Returns (passed, detail)."""
    panel = synthetic_panel(seed=seed)
    dates = panel["close"].index
    k = int(len(dates) * cut)
    cut_date = dates[k]
    rng = np.random.default_rng(seed + 1)
    scrambled = {}
    for f, df in panel.items():
        d = df.copy()
        future = d.index > cut_date
        d.loc[future] = d.loc[future].values * rng.uniform(0.5, 1.5, d.loc[future].shape)
        scrambled[f] = d
    try:
        a = evaluate(expr, panel).loc[:cut_date]
        b = evaluate(expr, scrambled).loc[:cut_date]
    except Exception as e:                       # noqa: BLE001 - any failure is a rejection
        return False, f"evaluation failed: {type(e).__name__}: {e}"
    both_nan = a.isna() & b.isna()
    diff = (a - b).abs().where(~both_nan)
    nan_mismatch = (a.isna() != b.isna()).to_numpy().sum()
    worst = float(np.nanmax(diff.to_numpy())) if diff.notna().to_numpy().any() else 0.0
    if nan_mismatch or worst > tol:
        return False, (f"values before {cut_date.date()} changed when the future was scrambled "
                       f"(max diff {worst:.3g}, {int(nan_mismatch)} NaN mismatches) - LOOK-AHEAD")
    return True, "no dependence on future data"


def numerical_checks(values: pd.Series | pd.DataFrame, max_invalid_ratio: float = 0.30,
                     min_coverage: float = 0.30, min_unique_ratio: float = 0.10):
    """XAlpha-style numerical validation: reject degenerate factors.
    - invalid (NaN/inf) or extreme-value ratio above 30%
    - too few names covered per day
    - near-constant cross-sections (no information to rank on)"""
    # Do not use DataFrame.stack() for the invalid ratio: on pandas 2.x the default
    # stack drops NaNs, so a mostly-missing factor looks clean.
    if isinstance(values, pd.DataFrame):
        frame = values.replace([np.inf, -np.inf], np.nan)
        flat = frame.to_numpy().ravel()
        by_date = frame
    else:
        series = values.replace([np.inf, -np.inf], np.nan)
        flat = series.to_numpy()
        by_date = series.unstack()
    n = flat.size
    if n == 0:
        return False, "empty"
    invalid = float(np.isnan(flat).mean())
    finite = flat[~np.isnan(flat)]
    if finite.size == 0:
        return False, "all values invalid"
    q1, q99 = np.quantile(finite, [0.01, 0.99])
    spread = q99 - q1
    med = float(np.median(finite))
    extreme = float((np.abs(finite - med) > 1e6 * max(abs(spread), 1e-12)).mean())
    if invalid + extreme > max_invalid_ratio:
        return False, f"invalid+extreme ratio {invalid + extreme:.2f} > {max_invalid_ratio}"
    present = by_date.notna().sum(axis=1)
    cover = present / max(float(present.max()), 1.0)   # relative to the fullest day
    if float(cover.mean()) < min_coverage:
        return False, f"mean daily coverage {cover.mean():.2f} < {min_coverage}"
    nunique = by_date.apply(lambda r: r.dropna().nunique(), axis=1)
    uniq = nunique / by_date.notna().sum(axis=1).clip(lower=1)
    if float(nunique.median()) <= 2 or float(uniq.mean()) < min_unique_ratio:
        return False, (f"near-constant cross-sections (median distinct values "
                       f"{nunique.median():.0f}, unique ratio {uniq.mean():.3f}) - nothing to rank")
    return True, "ok"
