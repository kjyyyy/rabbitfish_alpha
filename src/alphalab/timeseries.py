"""Time-series evaluation, for markets with one instrument or a handful.

The lab's evaluation path is cross-sectional: it ranks instruments each day and
measures whether the ranking predicts relative returns. `evaluate.py` requires
more than 30 names per date and silently produces nothing below that. On EU ETS
carbon, where the tradable universe is one allowance plus a curve, that path is
not merely weak - it is undefined.

So this is the other half: does a signal predict the FORWARD RETURN OF ONE
INSTRUMENT over time? Same discipline, different geometry, and three statistical
consequences that the cross-sectional path gets for free and this one does not:

* **Overlapping windows.** A 20-day forward return sampled daily shares 19 days
  with its neighbour, so the observations are not independent and a naive t-stat
  is inflated by roughly sqrt(horizon). Newey-West standard errors with a lag of
  at least the horizon are the minimum correction, and `tstat_nw` applies them.
* **Breadth of one.** A cross-sectional signal on 500 names makes 500 bets a day.
  A timing signal on one instrument makes one bet per holding period - perhaps 12
  a year at a monthly horizon. IR = IC*sqrt(BR) is brutal here: the same skill
  earns a fraction as much, and the number of effectively independent decisions
  is reported alongside every result so it cannot be forgotten.
* **No market-neutral escape.** A cross-sectional book cancels the market factor.
  A single-instrument timing strategy IS a directional bet on that market, and
  its Sharpe must be compared against simply holding the thing.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def tstat_nw(x: pd.Series, lags: int | None = None) -> float:
    """t-statistic with Newey-West correction for overlapping observations.

    With a horizon of h sampled every period, consecutive observations share
    h-1 periods of data. Ignoring that autocorrelation inflates the t-statistic
    by roughly sqrt(h) - which turns a t of 1.3 into a "significant" 2.9 at a
    20-day horizon, out of nothing but bookkeeping.
    """
    s = pd.Series(x).dropna().astype(float)
    n = len(s)
    if n < 10 or s.std(ddof=1) == 0:
        return float("nan")
    lags = int(lags if lags is not None else np.floor(4 * (n / 100) ** (2 / 9)))
    e = (s - s.mean()).to_numpy()
    gamma0 = float(e @ e / n)
    var = gamma0
    for k in range(1, min(lags, n - 1) + 1):
        w = 1.0 - k / (lags + 1)                       # Bartlett kernel
        gamma = float(e[k:] @ e[:-k] / n)
        var += 2.0 * w * gamma
    if var <= 0:
        return float("nan")
    return float(s.mean() / np.sqrt(var / n))


def independent_decisions(signal: pd.Series, horizon: int, periods_per_year: int = 252) -> dict:
    """How many genuinely independent bets a timing signal makes per year.

    Two corrections to the naive count. The holding horizon means overlapping
    positions are one bet, not h bets; and a slow-moving signal makes fewer
    decisions than its sampling frequency suggests, which is what its own
    autocorrelation measures.
    """
    s = pd.Series(signal).dropna()
    if len(s) < 30:
        return dict(bets_per_year=float("nan"), note="too few observations")
    rho = float(s.autocorr(lag=1)) if s.std() > 0 else 0.0
    rho = 0.0 if rho != rho else max(min(rho, 0.999), 0.0)
    # an AR(1) signal with autocorrelation rho has an effective sample size of
    # roughly n*(1-rho)/(1+rho)
    shrink = (1 - rho) / (1 + rho)
    naive = periods_per_year / max(horizon, 1)
    return dict(bets_per_year=round(float(naive * shrink), 1), naive_bets_per_year=round(naive, 1),
                signal_autocorrelation=round(rho, 3),
                note="IR = IC*sqrt(BR). A timing signal on one instrument makes a handful of "
                     "independent bets a year, so it needs a far higher IC than a "
                     "cross-sectional signal to reach the same information ratio")


def evaluate_ts(signal: pd.Series, forward_return: pd.Series, horizon: int = 20,
                periods_per_year: int = 252, benchmark: pd.Series | None = None) -> dict:
    """Does this signal predict the forward return of one instrument?

    `signal` and `forward_return` are date-indexed. The forward return must
    already be the return the signal is trying to predict, computed so that it
    starts AFTER the signal is known.
    """
    d = pd.concat([pd.Series(signal).rename("s"),
                   pd.Series(forward_return).rename("y")], axis=1).dropna()
    if len(d) < 30:
        return dict(n=len(d), note="too few overlapping observations to evaluate")

    ic = float(d["s"].corr(d["y"], method="spearman"))
    pearson = float(d["s"].corr(d["y"]))

    # the strategy: position proportional to the standardised signal, capped,
    # so a single extreme reading cannot dominate the record
    z = (d["s"] - d["s"].mean()) / (d["s"].std(ddof=1) or 1.0)
    pos = z.clip(-2, 2) / 2.0
    strat = (pos * d["y"]).rename("strategy")

    # non-overlapping sample, as a cross-check on the overlapping statistics
    nonover = strat.iloc[::max(horizon, 1)]

    out = dict(
        n=int(len(d)), horizon=horizon,
        ic_spearman=round(ic, 4), ic_pearson=round(pearson, 4),
        hit_rate=round(float((np.sign(d["s"]) == np.sign(d["y"])).mean()), 4),
        mean_return=float(strat.mean()),
        t_naive=round(float(strat.mean() / (strat.std(ddof=1) / np.sqrt(len(strat)))), 2)
        if strat.std(ddof=1) else float("nan"),
        t_newey_west=round(tstat_nw(strat, lags=max(horizon, 1)), 2),
        t_non_overlapping=round(float(nonover.mean() / (nonover.std(ddof=1) / np.sqrt(len(nonover))))
                                if len(nonover) > 5 and nonover.std(ddof=1) else float("nan"), 2),
        **independent_decisions(d["s"], horizon, periods_per_year))

    # the honest comparison for a directional strategy: just holding the thing
    bench = pd.Series(benchmark).reindex(d.index).dropna() if benchmark is not None else d["y"]
    if len(bench) > 10 and bench.std(ddof=1) > 0:
        out["buy_and_hold_t"] = round(tstat_nw(bench, lags=max(horizon, 1)), 2)
        out["beats_buy_and_hold"] = bool(out["t_newey_west"] > out["buy_and_hold_t"])

    infl = (out["t_naive"] / out["t_newey_west"]) if out["t_newey_west"] else float("nan")
    out["overlap_inflation"] = round(float(infl), 2) if infl == infl else None
    out["note"] = (
        f"the naive t-statistic is {out['overlap_inflation']}x the Newey-West one; the "
        f"difference is entirely the overlapping-window artefact, and the corrected figure is "
        f"the one to gate on" if out["overlap_inflation"] else "")
    return out


def forward_return(price: pd.Series, horizon: int = 20, lag: int = 1) -> pd.Series:
    """The return a signal observed today could actually capture.

    `lag` is execution delay: a signal computed from today's close is traded at
    tomorrow's, so the return starts one period later. Omitting it is the
    same-day-execution error that this lab measured to be worth 4.5% a year.
    """
    p = pd.Series(price).astype(float)
    return (p.shift(-(horizon + lag)) / p.shift(-lag) - 1.0).rename("forward_return")
