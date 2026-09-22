"""Validation corrections the 2026 review said were missing, and cheap.

Five checks, all compute-bound rather than data-bound, all applying to every
market. They exist because the review found the lab's *gates* institutional-grade
while its *evidence* rested on a single historical path and a Sharpe computed on
the wrong statistic.

1. `cpcv` - combinatorial purged cross-validation. Walk-forward tests one path
   through history; results depend heavily on that path, and early folds decide
   on almost no data. CPCV trains on every combination of blocks and yields a
   *distribution* of Sharpes instead of one number (Lopez de Prado).

2. `overfitting_factor` - Rej, Seager & Bouchaud (CFM, arXiv:1902.01802) model
   the iterative-refinement process itself rather than counting independent
   trials, and find the in-sample/out-of-sample Sharpe ratio is about 2 for
   typical CTA Sharpes: halve the backtest. This is complementary to the
   Deflated Sharpe, not a replacement - DSR deflates parallel search, OFF
   deflates the tweak-until-it-passes loop that a bandit is most exposed to.

3. `log_wealth_test` - under fat tails a strategy can show a significantly
   positive MEAN return and still compound to a loss (Jensen's inequality). A
   Sharpe computed on arithmetic returns is then the wrong statistic and the
   deflation applied to it is deflating the wrong number. Crypto makes this
   acute; it is cheap enough to run everywhere.

4. `lagged_signal_decay` - Maven Securities' test: re-run with deliberately
   delayed signals and measure what the delay costs. One test answers three
   questions - how urgent is execution, how much slippage tolerance exists, and
   is the edge decaying - and it needs no new data.

5. `cost_sweep` - performance at 1x, 2x, 3x and 5x assumed costs, with a
   pre-committed rule: an edge that dies by 3x was a cost assumption, not an
   edge.
"""
from __future__ import annotations

import itertools
import math

import numpy as np
import pandas as pd

from . import stats


# --------------------------------------------------------------------------
# 1. combinatorial purged cross-validation
# --------------------------------------------------------------------------
def cpcv_splits(n_obs: int, n_blocks: int = 8, n_test: int = 2, purge: int = 10,
                embargo: int = 5, max_paths: int = 60) -> list[tuple[np.ndarray, np.ndarray]]:
    """Train/test index pairs over every choice of `n_test` blocks out of `n_blocks`.

    Purging removes training observations whose label window overlaps the test
    block; the embargo removes a further stretch immediately after it. Without
    both, overlapping labels leak the test period into training and every
    resulting Sharpe is optimistic.
    """
    if n_obs < n_blocks * 3:
        return []
    edges = np.linspace(0, n_obs, n_blocks + 1).astype(int)
    blocks = [np.arange(edges[i], edges[i + 1]) for i in range(n_blocks)]
    out = []
    for combo in itertools.islice(itertools.combinations(range(n_blocks), n_test), max_paths):
        test = np.concatenate([blocks[i] for i in combo])
        banned = set()
        for i in combo:
            lo, hi = blocks[i][0], blocks[i][-1]
            banned.update(range(max(0, lo - purge), min(n_obs, hi + embargo + 1)))
        test_set = set(test.tolist())
        train = np.array([i for i in range(n_obs) if i not in banned and i not in test_set])
        if len(train) > n_obs // 4 and len(test) > 5:
            out.append((train, test))
    return out


def cpcv(returns: pd.Series, n_blocks: int = 8, n_test: int = 2, purge: int = 10,
         embargo: int = 5, periods: int = 52, max_paths: int = 60) -> dict:
    """Sharpe distribution across held-out block combinations.

    `returns` is the strategy's per-period return series. The distribution is
    what matters: a strategy whose 5th percentile is negative has not been shown
    to work, however good the single walk-forward path looked.
    """
    r = pd.Series(returns).dropna()
    splits = cpcv_splits(len(r), n_blocks, n_test, purge, embargo, max_paths)
    if not splits:
        return dict(paths=0, note="series too short for CPCV")
    sr = [stats.sharpe(r.iloc[test], periods) for _, test in splits]
    sr = [s for s in sr if s == s]
    if not sr:
        return dict(paths=0, note="no usable paths")
    a = np.asarray(sr)
    return dict(paths=len(a), sharpe_mean=float(a.mean()), sharpe_std=float(a.std(ddof=1)),
                sharpe_p05=float(np.percentile(a, 5)), sharpe_p50=float(np.percentile(a, 50)),
                sharpe_p95=float(np.percentile(a, 95)),
                prob_negative=float((a < 0).mean()),
                note="a single walk-forward path is one draw from this distribution")


# --------------------------------------------------------------------------
# 2. the overfitting factor (CFM)
# --------------------------------------------------------------------------
def overfitting_factor(sharpe_is: float, f: float = 0.1, n_tweaks: int = 20,
                       default: float = 2.0) -> dict:
    """Discount an in-sample Sharpe for the tweak-until-it-passes loop.

    CFM's result for typical CTA Sharpes (0.3-0.5) is a discount factor of
    about 2. `f` is the fraction of the P&L a researcher modifies per iteration
    (they cap it near 0.1) and `n_tweaks` how many iterations the candidate
    survived. The floor of 1.0 matters: a discount below 1 would mean refinement
    *improves* out-of-sample performance, which is the claim being tested.
    """
    if sharpe_is is None or sharpe_is != sharpe_is:
        return dict(sharpe_in_sample=None, factor=default, sharpe_discounted=None)
    factor = max(1.0, default * (1.0 + f * math.log1p(max(n_tweaks, 0)) / math.log(21)))
    return dict(sharpe_in_sample=float(sharpe_is), factor=round(float(factor), 3),
                sharpe_discounted=float(sharpe_is) / factor,
                acceptance_threshold=0.7,
                passes=bool(float(sharpe_is) / factor >= 0.7),
                note="CFM arXiv:1902.01802 - halve a CTA-like backtest Sharpe. Combined with "
                     "their acceptance threshold of ~0.7, a candidate needs roughly 1.4 "
                     "in backtest to be a credible 0.7 live.")


# --------------------------------------------------------------------------
# 3. log wealth vs mean return
# --------------------------------------------------------------------------
def log_wealth_test(returns) -> dict:
    """Does this strategy compound, or only average?

    Under fat tails a portfolio can have a significantly positive arithmetic
    mean and a negative cumulative log return - it averages up and compounds
    down. A Sharpe built on the arithmetic mean then describes something you
    cannot actually harvest, and deflating it deflates the wrong statistic.
    """
    r = pd.Series(returns).dropna().astype(float)
    if len(r) < 20:
        return dict(n=len(r), note="too few observations")
    if (r <= -1).any():
        return dict(n=len(r), total_loss=True,
                    note="a return of -100% or worse appears: wealth reaches zero and log "
                         "wealth is undefined. Any mean-return statistic here is meaningless.")
    log_r = np.log1p(r)
    t_mean = stats.tstat(r)
    out = dict(n=int(len(r)), mean_return=float(r.mean()), mean_t=float(t_mean),
               log_wealth=float(log_r.sum()), geometric_mean=float(np.expm1(log_r.mean())),
               variance_drag=float(r.mean() - np.expm1(log_r.mean())),
               skew=float(r.skew()), kurtosis=float(r.kurtosis()))
    out["compounds"] = bool(out["log_wealth"] > 0)
    out["mean_positive_but_compounds_negative"] = bool(t_mean > 2 and out["log_wealth"] <= 0)
    if out["mean_positive_but_compounds_negative"]:
        out["note"] = ("SIGNIFICANT POSITIVE MEAN, NEGATIVE COMPOUND RETURN. The arithmetic "
                       "mean is not harvestable here; size down or reject. This is the "
                       "failure mode fat-tailed markets produce and a t-test cannot see.")
    return out


# --------------------------------------------------------------------------
# 4. lagged-signal decay (Maven)
# --------------------------------------------------------------------------
def lagged_signal_decay(run_fn, lags=(0, 1, 2, 3, 5, 10)) -> dict:
    """What does being slow cost?

    `run_fn(lag)` must return an annualised excess return for a signal delayed
    by `lag` periods. The shape of the decay says whether the edge is a latency
    race (steep) or patient (flat) - and a signal that is only profitable at
    lag 0 is one a retail participant will lose.
    """
    curve, errors = {}, {}
    for lag in lags:
        try:
            curve[int(lag)] = float(run_fn(int(lag)))
        except Exception as e:                        # noqa: BLE001 - a lag may be infeasible
            curve[int(lag)] = float("nan")
            errors[int(lag)] = str(e)[:80]
    vals = {k: v for k, v in curve.items() if v == v}
    if len(vals) < 2:
        return dict(curve=curve, errors=errors, note="not enough successful runs")
    lo, hi = min(vals), max(vals)
    base = vals[lo]
    per_period = (base - vals[hi]) / max(hi - lo, 1)
    half = next((k for k in sorted(vals) if base > 0 and vals[k] <= base / 2), None)
    return dict(curve=curve, errors=errors, base=base,
                cost_per_period_of_delay=float(per_period),
                half_life_periods=half, worst_lag=int(min(vals, key=lambda k: vals[k])),
                latency_race=bool(half is not None and half <= 1),
                note="a signal that halves within one period is a speed race a retail "
                     "participant loses; a flat curve means execution urgency is low and "
                     "slippage tolerance is high")


# --------------------------------------------------------------------------
# 5. cost sensitivity
# --------------------------------------------------------------------------
def cost_sweep(run_fn, multipliers=(0.0, 1.0, 2.0, 3.0, 5.0)) -> dict:
    """Performance as assumed costs rise. `run_fn(mult)` returns annual excess.

    Pre-committed rule, stated before the numbers are seen: an edge that dies by
    3x costs was a cost assumption rather than an edge. The zero-cost figure is
    reported only to show how much of the result it was buying.
    """
    curve = {}
    for m in multipliers:
        try:
            curve[float(m)] = float(run_fn(float(m)))
        except Exception:                             # noqa: BLE001
            curve[float(m)] = float("nan")
    ok = {k: v for k, v in curve.items() if v == v}
    if not ok:
        return dict(curve=curve, note="no successful runs")
    base = ok.get(1.0, next(iter(ok.values())))
    breaks_at = next((m for m in sorted(ok) if m >= 1.0 and ok[m] <= 0), None)
    zero = ok.get(0.0)
    return dict(curve=curve, at_assumed_costs=base, breaks_at_multiple=breaks_at,
                zero_cost_uplift=(zero - base) if zero is not None else None,
                survives_3x=bool(ok.get(3.0, -1) > 0),
                verdict=("survives 3x costs" if ok.get(3.0, -1) > 0 else
                         f"dies at {breaks_at}x costs - this was a cost assumption, not an edge"
                         if breaks_at else "inconclusive"))
