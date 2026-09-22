# v0.6 — protocol audit and the free-data plan

*Research output, not advice.*

## 1. How much "alpha" is just evaluation convention?

Everything held fixed (data, the twelve hypothesis factors, the portfolio rule, costs), one
convention toggled at a time against a strictly causal baseline, validation window 2021–24.
All variants computed with the lab's own evaluator so the comparison is internally consistent.

| Protocol | Excess/yr | IR | Change vs causal baseline |
|---|---|---|---|
| **baseline (strictly causal)** | +7.85% | 0.56 | — |
| same-day execution | **+12.32%** | **0.87** | **+4.47%/yr, IR +0.32** |
| centred feature windows | −31.49% | −2.30 | −39.34%/yr |
| global (whole-sample) normalisation | +1.20% | 0.09 | −6.65%/yr |
| survivors-only universe | +7.71% | 0.54 | −0.14%/yr |

**The headline: trading at the same close you used to compute the signal manufactures about
4.5 percentage points a year and lifts the IR by more than half.** That single convention —
the most common error in hobby backtests — creates more apparent alpha than every combination
method tested in v0.5 put together. The lab's t+1 execution was already correct; now the size
of the error it avoids is measured.

Two results worth reading carefully:

- **Centred windows did not flatter, they destroyed** (−31%/yr). Leakage distorts rather than
  reliably inflating: the composite is dominated by reversal factors, so a peeking rolling mean
  systematically ranks the wrong names. It would flatter instead of hurt in any pipeline that
  *fits signs after seeing results*, which is exactly why the gate matters.
- **Survivorship bias barely registered here (−0.14%)** — because Chinese A-shares almost never
  delist. That is a property of this market, not evidence the lab is immune. Any US port must
  handle delisting properly before its numbers mean anything, which is why the delisting adapter
  landed in the same release.

A useful side-effect: the local evaluator's baseline (+7.85%, IR 0.56) is close to the Qlib
pipeline's variant A (+7.1%, IR 0.63). Two independent implementations agreeing within
0.7pp is the cross-check the second evaluator was built for.

## 2. Free data that survives production

`docs/data-sources.md` is the registry. The finding that matters for the roadmap:

- **SEC Financial Statement Data Sets** are free, quarterly, and **as filed** — genuine
  point-in-time US fundamentals back to 2009, with the filing date on every row. This is the
  free substitute for Compustat PIT and the one lever that moves the lab out of price-only
  signals.
- **SEC Form 25 / 25-NSE filings** in EDGAR's free full index give delisting dates, so dead
  names can stay in a universe instead of silently vanishing. They do not give the delisting
  *return*; the documented assumption (≈ −30% for performance delistings) has to be applied and
  disclosed.
- **No free, licence-clean source was found for UK equity prices with point-in-time index
  membership.** A UK-traded book would need a paid feed; US or CN is where free data is adequate.

Both adapters are implemented and unit-tested against fixtures. Neither has been run against
live SEC endpoints from this environment (no network access to sec.gov here), so the first
downloaded quarter should be checked by hand.

## 3. What was deliberately not built

- **Cross-asset regime engine.** Needs multi-asset price history; free sources (Stooq, yfinance)
  are adequate for prototyping but carry the survivorship and re-adjustment problems above.
  Worth doing after the data layer is fixed, not before.
- **Deep learning on richer features.** Adding model capacity to a feature set that has no edge
  adds trials, not alpha. The v0.5 result — three combination methods all beaten by twelve
  hand-written factors — is the argument.
- **"Only count pre-registered tests toward N".** Kept rejected: every candidate still counts.
  The ledger records the pre-registered/exploratory distinction for governance instead.
