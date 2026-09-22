"""Does a wide search over a thin universe manufacture false positives?

The 2026 review claimed the lab's gates port to crypto and futures but its
search engine does not, because IR = IC*sqrt(BR) and breadth collapses from a
3,000-name equity cross-section to a handful of independent bets. That is an
argument. This measures it.

Design: pure noise, so every "discovery" is false by construction. For each
universe width, generate correlated instrument returns, run K random
cross-sectional factors, keep the best by in-sample Sharpe, then score that same
factor out of sample. Nothing here can work; the question is how convincing the
best thing found looks, and how much of that survives.

Run: python scripts/breadth_experiment.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from alphalab import breadth, stats  # noqa: E402

N_TRIALS = 200
N_REPS = 30
REFERENCE_IC = 0.03
N_PERIODS = 520                       # ~10 years of weekly rebalances
SPLIT = 260
CASES = [
    ("equity-like cross-section", 300, 0.15),
    ("crypto perps", 100, 0.55),
    ("commodity futures", 25, 0.35),
    ("a thin book", 8, 0.45),
]


def universe(n_inst: int, rho: float, rng) -> pd.DataFrame:
    """Correlated instrument returns with NO predictability whatsoever."""
    common = rng.normal(0, 0.02, N_PERIODS)
    idio = rng.normal(0, 0.02, (N_PERIODS, n_inst))
    r = np.sqrt(rho) * common[:, None] + np.sqrt(1 - rho) * idio
    return pd.DataFrame(r, columns=[f"i{j}" for j in range(n_inst)])


def search(rets: pd.DataFrame, rng) -> dict:
    """Run N_TRIALS random factors; keep the in-sample best; score it out of sample."""
    is_r, oos_r = rets.iloc[:SPLIT], rets.iloc[SPLIT:]
    best = None
    for _ in range(N_TRIALS):
        # a random cross-sectional factor: a fixed random loading per instrument
        w = rng.normal(0, 1, rets.shape[1])
        w = w / np.abs(w).sum()
        pnl_is = pd.Series(is_r.to_numpy() @ w, index=is_r.index)
        s = stats.sharpe(pnl_is, 52)
        if best is None or s > best["sharpe_is"]:
            best = dict(w=w, sharpe_is=float(s))
    pnl_oos = pd.Series(oos_r.to_numpy() @ best["w"], index=oos_r.index)
    return dict(sharpe_is=best["sharpe_is"], sharpe_oos=float(stats.sharpe(pnl_oos, 52)))


def main() -> dict:
    rng = np.random.default_rng(7)
    rows = []
    for label, n_inst, rho in CASES:
        rets = universe(n_inst, rho, rng)
        b = breadth.effective_breadth(rets, rebalances_per_year=52)
        reps = [search(universe(n_inst, rho, rng), rng) for _ in range(N_REPS)]
        is_ = np.array([r["sharpe_is"] for r in reps])
        oos = np.array([r["sharpe_oos"] for r in reps])
        # What a REAL, modest skill of IC = 0.03 would earn in this universe.
        # IR = IC * sqrt(BR). This is the reward side of the trade-off; the
        # false-positive columns are the risk side.
        ir_if_skilled = REFERENCE_IC * np.sqrt(b["breadth_per_year"])
        rows.append(dict(
            case=label, instruments=n_inst, avg_correlation=b["avg_correlation"],
            bets_long_only=b["independent_bets"],
            bets_neutral=b["independent_bets_neutral"],
            trials_per_bet=round(N_TRIALS / max(b["independent_bets_neutral"], 1), 1),
            best_sharpe_in_sample=round(float(is_.mean()), 3),
            same_factor_out_of_sample=round(float(oos.mean()), 3),
            ir_if_ic_is_0_03=round(float(ir_if_skilled), 3),
            ic_needed_for_ir_0_7=round(breadth.required_ic(0.7, b["breadth_per_year"]), 4),
        ))
    df = pd.DataFrame(rows)

    print(f"Pure noise. {N_TRIALS} random factors per search, "
          f"{len(df)} universes, {N_REPS} repetitions each.")
    print("Every 'discovery' below is false by construction.\n")
    print(df.to_string(index=False))

    print("""
What this does and does not show.

DOES NOT: the best-of-200 in-sample Sharpe is roughly the same (about 0.9 to 1.2)
whatever the universe width, and out-of-sample it is roughly zero everywhere. A
narrow universe does NOT make the search more prone to false positives - the
hypothesis this experiment was built to test is not supported.

DOES, and it is a refinement of the usual claim: the breadth penalty depends on
what KIND of book you run.

  long-only / directional   the market is the first eigenvalue, so 25 futures are
                            ~6 bets and 100 perps are ~3. This is the figure the
                            CTA literature's "4-8 independent bets" refers to.
  cross-sectional / neutral the common factor cancels, so the same 25 futures are
                            ~23 bets and the 100 perps ~83.

Both are correct; they answer different questions. Quoting the long-only number
at a market-neutral strategy understates its breadth by an order of magnitude,
and quoting the neutral number at a trend follower flatters it by the same.

The residual penalty is still real. For an identical IC of 0.03, the information
ratio runs 2.98 in the wide equity cross-section, 1.04 in commodity futures and
0.57 in a thin eight-instrument book. Same skill, a third of the living. And the
trial count that deflates the result is identical in each. That asymmetry - the
risk of self-deception constant, the payoff falling - is the case for a narrow,
pre-specified search in a thin market.""")
    out = dict(n_trials=N_TRIALS, n_periods=N_PERIODS, split=SPLIT,
               n_repetitions=N_REPS, reference_ic=REFERENCE_IC, cases=rows,
               hypothesis_tested="a narrower universe inflates the in-sample best of a fixed "
                                 "search budget",
               hypothesis_supported=False,
               conclusion=(
                   "Not supported: the best-of-N in-sample Sharpe is roughly constant across "
                   "universe widths and out-of-sample is roughly zero in all of them. The "
                   "experiment instead establishes that the breadth penalty depends on the kind "
                   "of book: a common factor collapses LONG-ONLY breadth (25 futures -> ~6 bets, "
                   "matching the CTA literature) but cancels for a CROSS-SECTIONAL book (~23 "
                   "bets). Quoting one at the other misstates breadth by an order of magnitude. "
                   "The residual penalty is real: an identical IC of 0.03 earns an IR of 2.98 in "
                   "the wide equity cross-section, 1.04 in commodity futures and 0.57 in a thin "
                   "book, while the trial count deflating the result is the same in each."))
    return out


if __name__ == "__main__":
    res = main()
    d = Path("results") / "breadth-experiment"
    d.mkdir(parents=True, exist_ok=True)
    (d / "breadth_experiment.json").write_text(json.dumps(res, indent=2))
    print(f"\nwritten: {d / 'breadth_experiment.json'}")
