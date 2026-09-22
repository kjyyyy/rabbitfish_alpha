"""The fundamental law, and what it says about searching a narrow universe.

Grinold's IR = IC * sqrt(BR) makes breadth the multiplier on skill. A 3,000-name
A-share cross-section forgives a weak IC because there are thousands of roughly
independent bets per year. Roughly 25 liquid commodity contracts - which the
literature reduces to an estimated 4-8 *independent* bets once sector
correlation is accounted for - does not.

That changes what a research system should do, not just what it should expect:

* A wide search over a narrow universe inflates the trial count (the denominator
  of every Deflated Sharpe here) while the achievable information ratio is
  capped by breadth. It is the configuration that manufactures exactly the false
  positives the gates exist to catch.
* So in a thin universe the lab should run FEWER, pre-specified, economically
  grounded structures, and let the bandit allocate across implementations of
  those rather than across an open expression space.

This module computes the breadth actually available, the IC a universe would
need to reach a target IR, and a warning when the configured search is wider
than the universe can support. It gates nothing by itself - it is a diagnostic
that belongs on screen before a search is launched, not a threshold that
silently rejects.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Structural ceilings from the literature, used only to flag implausible results.
# A commodity-only book reduces to a handful of macro bets, so a gross Sharpe far
# above ~1.0 is more likely a methodology error than a discovery - most often
# percentage returns computed on a back-adjusted series, look-ahead in the roll
# rule, or a survivorship-filtered contract universe.
SANITY_CEILING = {"futures": 1.0, "crypto": 1.5, "equity": 2.0}


def _participation_ratio(R: pd.DataFrame) -> tuple[float, float]:
    C = np.nan_to_num(R.corr().to_numpy(), nan=0.0)
    ev = np.linalg.eigvalsh(C)
    ev = ev[ev > 1e-10]
    n_eff = float(ev.sum() ** 2 / (ev ** 2).sum()) if len(ev) else float(R.shape[1])
    off = C[~np.eye(len(C), dtype=bool)]
    return n_eff, (float(np.mean(off)) if off.size else 0.0)


def effective_breadth(returns: pd.DataFrame, rebalances_per_year: int = 52) -> dict:
    """Independent bets per year, from the correlation structure of the universe.

    `returns` is date x instrument. The eigenvalue participation ratio answers
    "how many independent things am I really holding?" - 25 commodity contracts
    across six sectors is not 25 bets, and pretending otherwise is how a thin
    book gets sized as if it were diversified.

    Reported twice, and the difference matters. On RAW returns the first
    eigenvalue is the market, so the count collapses toward one however many
    instruments there are - which is the right number for a long-only book and
    badly wrong for a market-neutral one. `independent_bets_neutral` removes the
    cross-sectional mean each period, which is what a dollar-neutral book
    actually holds, and is the figure to use when the strategy is a spread.
    """
    R = pd.DataFrame(returns).dropna(axis=1, how="all")
    R = R.loc[:, R.std() > 0]
    if R.shape[1] < 2 or len(R) < 20:
        return dict(n_instruments=int(R.shape[1]), independent_bets=float(R.shape[1]),
                    independent_bets_neutral=float(R.shape[1]),
                    breadth_per_year=float(R.shape[1]) * rebalances_per_year,
                    note="too few instruments or observations to estimate correlation")
    n_eff, avg_corr = _participation_ratio(R)
    # the same universe with the market factor taken out
    neutral = R.sub(R.mean(axis=1), axis=0)
    neutral = neutral.loc[:, neutral.std() > 0]
    n_eff_n, avg_corr_n = _participation_ratio(neutral) if neutral.shape[1] > 1 else (n_eff, avg_corr)
    return dict(n_instruments=int(R.shape[1]),
                independent_bets=round(n_eff, 2), avg_correlation=round(avg_corr, 3),
                independent_bets_neutral=round(n_eff_n, 2),
                avg_correlation_neutral=round(avg_corr_n, 3),
                breadth_per_year=round(n_eff_n * rebalances_per_year, 1),
                collapse_ratio=round(n_eff_n / R.shape[1], 3),
                note="independent bets from the eigenvalue participation ratio. The raw figure "
                     "is dominated by the market factor and is the right one for a long-only "
                     "book; the neutral figure removes the cross-sectional mean and is the "
                     "right one for a dollar-neutral book. Breadth per year uses the neutral "
                     "count times the rebalance count, which assumes successive rebalances are "
                     "independent - they are not, so treat it as an upper bound")


def required_ic(target_ir: float, breadth_per_year: float) -> float:
    """The IC a universe of this breadth needs to reach `target_ir`. IR = IC*sqrt(BR)."""
    if breadth_per_year <= 0:
        return float("nan")
    return float(target_ir / np.sqrt(breadth_per_year))


def assess(returns: pd.DataFrame, n_trials_planned: int, target_ir: float = 0.7,
           rebalances_per_year: int = 52, market: str = "equity") -> dict:
    """Is the planned search proportionate to the universe it will search?

    `n_trials_planned` is how many distinct formulas a run intends to evaluate.
    Every one raises the Deflated-Sharpe bar for all of them, so the question is
    whether the universe can deliver an information ratio worth that price.
    """
    b = effective_breadth(returns, rebalances_per_year)
    br = b.get("breadth_per_year", 0.0)
    bets = b.get("independent_bets_neutral", b["independent_bets"])
    ic_needed = required_ic(target_ir, br)
    out = dict(**b, target_ir=target_ir, ic_required=round(ic_needed, 4),
               trials_planned=int(n_trials_planned),
               trials_per_independent_bet=round(n_trials_planned / max(bets, 1), 1),
               sanity_ceiling_sharpe=SANITY_CEILING.get(market, 2.0))
    ratio = out["trials_per_independent_bet"]
    if ratio > 25:
        out["verdict"] = "wide search, narrow universe"
        out["warning"] = (
            f"{n_trials_planned} trials against {bets} independent bets (market-neutral) is "
            f"{ratio:.0f} trials per bet. Breadth caps the achievable information ratio while "
            f"every trial raises the bar all of them must clear. Prefer a small number of "
            f"pre-specified, economically grounded structures over an open expression search, "
            f"and let the allocator choose among implementations of those.")
    elif ratio > 8:
        out["verdict"] = "search is on the wide side for this universe"
    else:
        out["verdict"] = "search width is proportionate to the universe"
    return out


def implausible(sharpe_gross: float, market: str) -> dict | None:
    """Flag a backtest Sharpe above the structural ceiling for its market.

    Pre-committed before any result is seen, which is the only time such a rule
    can be set honestly. It does not reject - it demands an explanation, and
    names the three explanations that are usually correct.
    """
    ceiling = SANITY_CEILING.get(market)
    if ceiling is None or sharpe_gross is None or sharpe_gross != sharpe_gross:
        return None
    if sharpe_gross <= ceiling:
        return None
    return dict(
        sharpe_gross=float(sharpe_gross), ceiling=ceiling, market=market,
        message=(f"gross Sharpe {sharpe_gross:.2f} exceeds the {ceiling} structural ceiling for "
                 f"{market}. Before treating this as a discovery, rule out the three usual "
                 f"causes: percentage returns computed on a back-adjusted (Panama) series, "
                 f"look-ahead in the roll rule, and a contract or instrument universe that "
                 f"silently excludes what died."))
