"""Evaluation statistics: rank IC, non-overlapping t-stats, quantile long-short,
Deflated Sharpe Ratio (Bailey & Lopez de Prado 2014) and PBO via CSCV
(Bailey, Borwein, Lopez de Prado & Zhu 2015)."""
import itertools
import math

import numpy as np
import pandas as pd
from scipy import stats as st


def daily_rank_ic(factor: pd.Series, label: pd.Series) -> pd.Series:
    df = pd.concat([factor.rename("f"), label.rename("y")], axis=1).dropna()
    g = df.groupby(level=0)
    return g.apply(lambda d: d["f"].rank().corr(d["y"].rank()) if len(d) > 30 else np.nan).dropna()


def nonoverlap(s: pd.Series, step: int) -> pd.Series:
    return s.iloc[::step]


def tstat(x: pd.Series) -> float:
    x = x.dropna()
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else np.nan


def quantile_ls(factor: pd.Series, label: pd.Series, q=5) -> pd.Series:
    """Top-minus-bottom quintile mean forward return, per date (gross)."""
    df = pd.concat([factor.rename("f"), label.rename("y")], axis=1).dropna()

    def one(d):
        if len(d) < 50:
            return np.nan
        r = d["f"].rank(pct=True)
        return d.loc[r > 1 - 1 / q, "y"].mean() - d.loc[r <= 1 / q, "y"].mean()
    return df.groupby(level=0).apply(one).dropna()


def sharpe(x, periods_per_year):
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std(ddof=1) * math.sqrt(periods_per_year)) if x.std() > 0 else np.nan


def deflated_sharpe(returns, n_trials, sr_var_trials):
    """Probability that the true (per-period) Sharpe > the expected maximum
    Sharpe from n_trials of pure noise. returns: per-period returns of the
    chosen strategy. sr_var_trials: variance of per-period Sharpe across trials."""
    r = pd.Series(returns).dropna()
    T = len(r)
    if T < 20 or r.std(ddof=1) == 0:      # too few observations to deflate anything
        return 0.0, float("nan"), float("nan")
    sr = r.mean() / r.std(ddof=1)
    g3, g4 = st.skew(r), st.kurtosis(r, fisher=False)
    emc = 0.5772156649
    n = max(n_trials, 2)
    sr0 = math.sqrt(max(sr_var_trials, 1e-12)) * (
        (1 - emc) * st.norm.ppf(1 - 1 / n) + emc * st.norm.ppf(1 - 1 / (n * math.e)))
    denom = math.sqrt(max(1 - g3 * sr + (g4 - 1) / 4 * sr ** 2, 1e-12))
    return float(st.norm.cdf((sr - sr0) * math.sqrt(T - 1) / denom)), float(sr), float(sr0)


def hurdle_sharpe(n_trials: int, sr_var_trials: float, T: int, target_dsr: float = 0.95,
                  periods: int = 52) -> float:
    """The ANNUALISED Sharpe a new candidate must reach, after `n_trials`, to
    clear `target_dsr`. This is the bar the search itself has raised: it rises
    with every trial, whether or not anything was learned, which is why a
    trial budget is a research decision and not a compute one."""
    if T < 20:
        return float("nan")
    base = np.random.default_rng(0).standard_normal(T)
    base = (base - base.mean()) / base.std(ddof=1)      # exactly mean 0, sd 1
    lo, hi = 0.0, 3.0                                   # per-period Sharpe bracket
    for _ in range(50):                                 # bisection: DSR rises with SR
        mid = (lo + hi) / 2
        d, _, _ = deflated_sharpe(base + mid, n_trials, sr_var_trials)
        lo, hi = (mid, hi) if d < target_dsr else (lo, mid)
    return float((lo + hi) / 2 * math.sqrt(periods))


def pbo_cscv(M: pd.DataFrame, S=16, max_combos=3000, seed=0):
    """Probability of Backtest Overfitting. M: T x N matrix of per-period returns
    for N candidate strategies. Returns PBO and the logit distribution."""
    M = M.dropna(axis=1, thresh=int(0.8 * len(M)))     # drop short-history candidates
    M = M.dropna(how="any")
    if M.shape[1] < 2 or len(M) < 2 * S:
        return float("nan"), np.array([])
    T = len(M) - len(M) % S
    blocks = np.array_split(M.iloc[:T].values, S)
    combos = list(itertools.combinations(range(S), S // 2))
    rng = np.random.default_rng(seed)
    if len(combos) > max_combos:
        combos = [combos[i] for i in rng.choice(len(combos), max_combos, replace=False)]
    logits = []
    for c in combos:
        is_ = np.vstack([blocks[i] for i in c])
        oos = np.vstack([blocks[i] for i in range(S) if i not in c])
        sr_is = is_.mean(0) / (is_.std(0, ddof=1) + 1e-12)
        sr_oos = oos.mean(0) / (oos.std(0, ddof=1) + 1e-12)
        best = int(np.argmax(sr_is))
        rank = st.rankdata(sr_oos)[best] / (len(sr_oos) + 1)
        logits.append(math.log(rank / (1 - rank)))
    logits = np.array(logits)
    return float((logits <= 0).mean()), logits
