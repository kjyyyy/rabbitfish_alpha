# v0.3 results — CSI 300, data to 18 Sep 2026

*Research output, not advice. The 2025–26 holdout was viewed in v0.1, so it is reported as
descriptive only and can never raise a claim tier.*

## 1. Discovery (2012–2020 only)

| | v0.2 gates |
|---|---|
| Candidates generated (12 hypotheses + 120 random + 3 GP generations) | 132 → **212 evaluated** |
| Rejected by AST / complexity / originality screen before any data was touched | 29 |
| Pass the naive test (IC t ≥ 2) | 109 |
| Pass t ≥ 3 | 72 |
| Pass Deflated Sharpe ≥ 0.95 against all 212 trials | **0** (best 0.80) |
| Held on probation (t ≥ 3, original, non-redundant) | 33 |
| PBO (CSCV) | 0.30 |

Decay is again the headline: the top 20 candidates averaged **IC 0.040 in discovery and 0.019
afterwards**, and across all candidates discovery IC explains little of later IC (corr 0.37).

**Per-source ablation** — does the machinery earn its keep?

| Source | Evaluated | t ≥ 3 | Probation | Mean later IC of the t ≥ 3 group |
|---|---|---|---|---|
| Written hypotheses | 12 | 7 | 7 | **0.021** |
| Random formulas | 91 | 16 | 6 | 0.009 |
| GP refinement | 109 | 49 | 20 | 0.010 |
| LLM | 0 | – | – | – (needs an API key; see README) |

The GP refiner produced the most statistically strong factors and the **weakest survivors**:
it is an efficient way to fit the discovery window. Written hypotheses decayed least.

## 2. Strategy variants (walk-forward 2021–24)

| Variant | Excess/yr | IR | IR @2× costs | Holdout (descriptive) |
|---|---|---|---|---|
| A hypothesis composite | +7.1% | 0.63 | **0.24** ← chosen by rule | −14.9% |
| C LightGBM on hypotheses | +6.1% | 0.65 | 0.01 | +3.7% |
| E library, dynamic IC weights | −2.4% | −0.24 | −0.92 | −18.3% |
| F LightGBM on hypotheses + library | +1.9% | 0.21 | −0.53 | +4.0% |

The dynamic-IC combiner (the AlphaForge-style mechanism from the paper review) **made things
worse**. Adding the 33 probation factors to the model (F) also underperformed the 12 hypotheses
alone (C). More machinery, less performance.

## 3. What the institutional portfolio layer adds (new in v0.3)

Same alpha, six constructions, ¥1m book, costs include commission, spread, stamp duty and
square-root market impact (10bp at 1% of daily volume, AQR's live-trade estimate).

| Construction | Result | Max DD | Turnover/rebal | Impact |
|---|---|---|---|---|
| 1 Naive top-30 equal weight | +2.0%/yr vs index, IR 0.18 | −31.9% | 99% | 0.54%/yr |
| 2 **+ no-trade bands** | **+3.3%/yr vs index, IR 0.30** | −30.2% | **79%** | 0.43%/yr |
| 3 + style-neutralised alpha | −3.6%/yr, IR −0.37 | −53.1% | 101% | 0.42%/yr |
| 4 + volatility-scaled weights | −2.7%/yr, IR −0.30 | −51.0% | 102% | 0.46%/yr |
| 5 Dollar-neutral long/short | −1.2%/yr **vs cash**, Sharpe −0.08 | −20.1% | 83% | 0.17%/yr |
| 6 Neutral + neutralised + vol-scaled | −7.3%/yr vs cash, Sharpe −1.11 | −29.6% | 103% | 0.23%/yr |

Three findings:

- **Banding is free money.** Holding a name while it stays inside a wider rank band cut turnover
  by a fifth and raised the IR from 0.18 to 0.30 — the cheapest improvement in the whole project,
  and it matches Novy-Marx & Velikov's published result.
- **62% of the "alpha" was style exposure.** Style-neutralising the signal cut its IC from 0.062
  to 0.024. The raw signal correlates −0.50 with volatility, −0.39 with size and −0.38 with beta:
  it is a low-beta, small, low-volatility bet. A pod shop would call that factor beta and not pay
  for it. Once neutralised, what is left does not survive costs.
- **The long/short book only looked good against a falling index.** Judged against cash, which is
  the right benchmark for a market-neutral book, it lost money. Its drawdown was much smaller
  (−20% vs −32%), so the construction does control risk; there just isn't alpha to harvest.

## 4. Capacity

Running the same book at increasing size (chart: `chart_capacity.png`):

| Book size | Excess/yr | Impact cost | Trades hitting the 5%-of-volume cap |
|---|---|---|---|
| ¥100k | +3.5% | 0.14%/yr | 0% |
| ¥1m | +3.3% | 0.43%/yr | 0% |
| ¥10m | +2.3% | 1.37%/yr | 0% |
| ¥100m | −0.6% | 4.28%/yr | 1% |
| ¥1bn+ | not meaningful | — | 54–85% |

Capacity for this strategy is roughly **¥10–100m (about £1–10m)**. Beyond ¥1bn the participation
caps bind on most trades, so the book stops being the same strategy — those rows are marked
`faithful=False` and should not be read as a return forecast. This is the one structural
advantage a small trader has: at ¥100k the impact cost is 0.14%/yr, against 4.3%/yr at ¥100m.

## 5. Crowding

The Khandani–Lo crowding proxy (R² of a cross-sectional regression of turnover on style
exposures; they flagged >10% before the August 2007 quant quake) is computed in
`crowding_r2.csv` as a monitoring input. It is reported, never traded on.

## Honesty log

- Discovery was rerun after a crash in the deflated-Sharpe code (series shorter than 20
  observations). Gates unchanged.
- The first portfolio trial was wrong: daily volume in this dataset is in lots of 100 shares,
  so impact costs were ~10× too high and participation caps bound at the wrong level. Fixed by
  using the `$amount` field; the corrected run is the one above.
- The first version of no-trade banding did nothing because it only compared names already held.
  It now works on rank bands.
- All 36 unit tests pass, including engine sanity checks on real data (oracle +423%/yr excess,
  random −11.6%/yr ≈ the cost drag, 6-day-stale signal unprofitable).
