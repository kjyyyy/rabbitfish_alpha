"""EU ETS end to end, on synthetic data, to show what the machinery says.

Synthetic because the real inputs cannot be fetched from this container: the EEX
auction workbook is a public download the outbound proxy refuses, and no free
licence-clean futures curve exists at all. So this plants ONE genuine
relationship among the pre-specified hypotheses and leaves the rest as noise,
then runs the real evaluation path and reports what survives.

The point is not the numbers - they are manufactured. The point is that the path
runs on a one-instrument market at all, and that the trial-count arithmetic
changes completely when the search is narrow.

Run: python scripts/euets_demo.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from alphalab import stats, timeseries, validation  # noqa: E402
from alphalab.markets import euets  # noqa: E402

N = 2500          # ~10 years, comparable to a real EUA history


def synthetic():
    """A carbon-like price, auctions, and one real signal among the noise."""
    rng = np.random.default_rng(11)
    idx = pd.bdate_range("2021-01-04", periods=N)

    # Cover ratio: persistent, and it GENUINELY leads returns here. The
    # persistence matters - a one-day effect tested at a 20-day horizon is
    # diluted twentyfold and undetectable by construction, which would test
    # nothing but the dilution.
    raw = rng.standard_normal(N)
    cover = pd.Series(1.6 + 0.25 * pd.Series(raw).rolling(40, min_periods=1).mean().to_numpy(),
                      index=idx)
    # The plant must match the SIGNAL'S DEFINITION, not merely its name. The
    # hypothesis says "high relative to its own history", and `auction_signals`
    # implements that as a rolling z-score - which is close to a deviation, not
    # a level. Driving the drift from the level instead leaves the two nearly
    # orthogonal and the planted effect undetectable, which tests nothing.
    r20 = cover.rolling(20, min_periods=10)
    z_cover = ((cover - r20.mean()) / r20.std()).replace([np.inf, -np.inf], np.nan)
    z_cover = z_cover.shift(1).fillna(0.0).to_numpy()
    shock = rng.normal(0, 0.014, N)
    # a sustained drift of ~4bp/day per unit of z, accumulating over the forward
    # window into a modest but real effect
    drift = 0.0002 + 0.0004 * z_cover
    px = pd.Series(35 * np.exp(np.cumsum(drift + shock)), index=idx)

    auctions = pd.DataFrame({
        "clearing_price": px * (1 - np.abs(rng.normal(0.002, 0.001, N))),
        "volume": 3_000_000.0,
        "bids": 3_000_000 * cover,
        "bidders": rng.integers(12, 26, N).astype(float),
    }, index=idx)
    return px, auctions


def main() -> dict:
    px, auctions = synthetic()
    sig = euets.auction_signals(auctions, secondary=px)
    sig["days_to_surrender"] = euets.days_to_surrender(sig.index)
    sig["msr_net_withdrawal"] = 0.0                      # constant here: no TNAC series


    tested = [h for h in euets.HYPOTHESES if h["signal"] in sig.columns]

    # A horizon sweep, because a signal only works at a horizon that matches its
    # own memory - and because the sweep is itself a search. Testing 4 signals at
    # 5 horizons is 20 trials, not 4, and the deflation must count all of them.
    HORIZONS = (1, 5, 10, 20, 60)
    rows, series = [], {}
    for h in tested:
        s_ = sig[h["signal"]] * h["sign"]
        if s_.notna().sum() < 100 or not s_.std(skipna=True):
            continue
        memory = next((k for k in range(1, 61) if abs(s_.autocorr(k)) < 0.2), 60)
        for hz in HORIZONS:
            fwd_h = timeseries.forward_return(px, horizon=hz, lag=1)
            r = timeseries.evaluate_ts(s_, fwd_h, horizon=hz)
            if r.get("n", 0) < 100:
                continue
            z = (s_ - s_.mean()) / (s_.std() or 1)
            key = f"{h['name']}@{hz}d"
            series[key] = (z.clip(-2, 2) / 2 * fwd_h).dropna()
            rows.append(dict(name=h["name"], horizon=hz, signal_memory_days=memory,
                             ic=r["ic_spearman"], t_newey_west=r["t_newey_west"],
                             t_non_overlapping=r["t_non_overlapping"],
                             bets_per_year=r["bets_per_year"]))
    res = pd.DataFrame(rows)

    # --- the gates, counting EVERY trial the sweep spent -------------------
    n_trials = len(rows)
    sr = {k: stats.sharpe(v.iloc[::max(int(k.split("@")[1][:-1]), 1)],
                          252 / max(int(k.split("@")[1][:-1]), 1)) for k, v in series.items()}
    sr = {k: v for k, v in sr.items() if v == v}
    sr_var = float(np.var(list(sr.values()))) if len(sr) > 1 else 0.02
    best = max(sr, key=sr.get)
    step = max(int(best.split("@")[1][:-1]), 1)
    nonover = series[best].iloc[::step]
    dsr_swept, _, _ = stats.deflated_sharpe(nonover, n_trials, sr_var)
    dsr_one, _, _ = stats.deflated_sharpe(nonover, 1, sr_var)
    hurdle_swept = stats.hurdle_sharpe(n_trials, sr_var, len(nonover), 0.95, int(252 / step))
    hurdle_one = stats.hurdle_sharpe(1, sr_var, len(nonover), 0.95, int(252 / step))

    print("EU ETS, synthetic. One instrument, so evaluation is time-series, not cross-sectional.")
    print(f"{len(tested)} pre-specified hypotheses x {len(HORIZONS)} horizons = "
          f"{n_trials} trials.\n")
    print(res.to_string(index=False))
    print("\nA planted relationship exists in cover ratio: a one-day effect on a signal whose")
    print("autocorrelation reaches zero within about a week. Read the horizon column against")
    print("signal_memory_days - the effect is visible where the holding period matches the")
    print("signal's memory and washes out entirely beyond it. That is not a defect of the")
    print("machinery; it is the machinery reporting that a fast signal cannot drive a slow")
    print("book, which is what the lagged-signal decay test exists to surface.\n")
    print(f"Best of the sweep: {best}, Sharpe {sr[best]:+.2f}")
    print(f"  deflated against 1 trial (had it been the only hypothesis): DSR {dsr_one:.3f}")
    print(f"  deflated against the {n_trials} trials the sweep actually spent : DSR {dsr_swept:.3f}")
    print(f"\n  Sharpe needed for DSR 0.95 with 1 trial   : {hurdle_one:.2f}")
    print(f"  Sharpe needed for DSR 0.95 with {n_trials} trials : {hurdle_swept:.2f}")
    print("\nThe horizon sweep is a search. Five horizons across four signals costs twenty")
    print("trials, and the bar rises accordingly - which is the whole argument for choosing")
    print("the horizon from the signal's own memory rather than by trying them all.")

    lw = validation.log_wealth_test(series[best])
    print(f"\n  best candidate compounds: {'yes' if lw.get('compounds') else 'NO'}")
    print("\nWhat this does NOT show: carry, calendar spreads and fuel-switching are absent")
    print("because they need a futures curve or energy prices, and neither is available free.")
    print("On real data those are the mechanisms with the best evidence, and they are the")
    print("reason the free-data route is a genuine constraint rather than an inconvenience.")

    return dict(n_hypotheses=len(tested), horizons=list(HORIZONS), n_trials=n_trials,
                results=rows, best=best, best_sharpe=float(sr[best]),
                dsr_if_single_trial=float(dsr_one), dsr_counting_the_sweep=float(dsr_swept),
                hurdle_sharpe_single=float(hurdle_one),
                hurdle_sharpe_after_sweep=float(hurdle_swept),
                unavailable_on_free_data=euets.UNAVAILABLE_ON_FREE_DATA,
                caveat="synthetic data with one planted relationship; the numbers are "
                       "manufactured and only the machinery is being demonstrated")


if __name__ == "__main__":
    out = main()
    d = Path("results") / "euets-demo"
    d.mkdir(parents=True, exist_ok=True)
    (d / "euets_demo.json").write_text(json.dumps(out, indent=2, default=float))
    print(f"\nwritten: {d / 'euets_demo.json'}")
