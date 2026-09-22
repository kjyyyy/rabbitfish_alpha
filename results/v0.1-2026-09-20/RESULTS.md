# Results of the first run (China A-shares, CSI 300, data to 18 Sep 2026)

*Not financial advice. Research prototype; China A-shares are not easily tradable for UK retail investors.*

## Stage 1: discovery (2012–2020 only)

| | Count |
|---|---|
| Candidates generated (12 hypotheses + 240 random formulas) | 252 |
| Passed look-ahead auditor | 252 |
| Pass the naive test (IC t-stat ≥ 2) | **119** |
| Pass the stricter t ≥ 3 | 51 |
| Pass Deflated Sharpe ≥ 0.95 given 252 trials | **0** (best: 0.92, `pv_corr_20d`) |

- **Decay after discovery.** The 20 strongest candidates (by t-stat) had a mean IC of 0.031 in discovery and 0.011 in 2021–24, about a third as strong. Across all 252, discovery IC and later IC correlate at only 0.33 (`chart_alpha_decay.png`).
- **Regime flips.** The low-volatility, MAX and range hypotheses had the *wrong sign* in 2012–20, then became the strongest factors in 2021–24 (IC 0.06–0.08).
- **Stable within the discovery window, not after it.** PBO (CSCV) across all 504 signed candidates was about 0: whichever signal ranked best in half of 2012–20 also held up in the other half. Almost all of the decay came after 2020, which a single-period test cannot detect. (The PBO function returns about 0.5 on pure noise, so the zero is not a bug.)

## Stage 2: models (walk-forward, costs included)

Weekly top-30 equal-weight book. One-way cost: 13bp plus stamp duty on sells.

| Variant | Valid excess/yr | Valid IR | Valid IR @2× costs | **Holdout excess/yr** | Holdout IR | Turnover/wk |
|---|---|---|---|---|---|---|
| A: hypothesis composite (no ML) | +7.1% | 0.63 | **0.24** ← chosen | **−15.0%** | −1.02 | 27% |
| B: LightGBM on Alpha158 | +3.1% | 0.33 | −0.56 | −7.3% | −0.53 | 52% |
| C: LightGBM on 12 hypothesis factors | +6.1% | 0.65 | 0.01 | +3.7% | 0.26 | 36% |

CSI 300 returned −8.1%/yr over validation (2021–24) and +10.2%/yr over the holdout (2025 to Sep 2026).

**What the stage-2 numbers show:**

- The pre-registered rule (best validation IR at 2× costs) chose **A, which then lost 15%/yr against the index in the holdout.**
- **C** held up best in the holdout, but choosing it now would be hindsight. The holdout is spent; a new test needs new data (paper trading from here).
- Alpha158 with LightGBM, the standard Qlib recipe, had the highest turnover and did not survive 2× costs even in validation.
- None of these results supports trading real money.

## Honesty log

- **Stage 1 run twice.** It was rerun after fixing a sign leak in the PBO calculation and duplicate `Corr(a,b)`/`Corr(b,a)` candidates. The gates did not change.
- **Stage 2 run three times.** A backtest bug made the final rebalance of each period hold its positions to the end of the dataset. That inflated validation and picked C in the buggy run. The fixed run picks A. **I have therefore seen holdout numbers under both choices**, so the holdout is contaminated as a *selection* tool. Treat it as descriptive only.
- The first buggy output is kept as `outputs/stage2_results_BUGGY_run1.json`. `trial_log.csv` keeps every model evaluation, including the buggy runs.
- **Sanity checks after the fixes:**
  - An oracle signal returns +423%/yr excess, so trade timing is aligned.
  - Random scores lose 11.6%/yr, which matches the modelled cost drag at 80% weekly turnover.
  - A 6-day-stale oracle loses money, so there is no leakage.
