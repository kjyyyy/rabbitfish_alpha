# v0.7 — point-in-time fundamentals, governance, and the full protocol audit

*Research output, not advice.*

## 1. The complete leakage league table

Everything fixed except one convention at a time; validation window 2021–24, CN A-shares.

| Protocol | Excess/yr | IR | Fiction vs causal baseline |
|---|---|---|---|
| **baseline (strictly causal)** | +7.85% | 0.56 | — |
| **zero costs** | +14.48% | 1.03 | **+6.63%/yr, IR +0.48** |
| **same-day execution** | +12.32% | 0.87 | **+4.47%/yr, IR +0.32** |
| global (whole-sample) normalisation | +1.20% | 0.09 | −6.65%/yr |
| survivors-only universe | +7.71% | 0.54 | −0.14%/yr |
| centred feature windows | −31.49% | −2.30 | −39.34%/yr |
| punitive costs (3×) | −5.41% | −0.37 | −13.26%/yr |

Two conventions between them manufacture **over 11 percentage points a year**: assuming zero
costs (+6.6%) and trading the close you used to build the signal (+4.5%). Neither has anything
to do with signal quality. Meanwhile 3× costs takes the same strategy to −5.4%, so whatever
edge exists lives inside a narrow band of cost assumptions — which is itself the finding.

## 2. Fundamentals timing, measured before any download

The equivalent mistake for fundamental data is joining on the **period end** rather than the
**filing date**, which grants foresight over the reporting lag. Measured on synthetic data where
the answer is known by construction (`alphalab audit` runs this offline):

| Reporting lag | IC joining on filing date | IC joining on period end | Foresight gained |
|---|---|---|---|
| 30 days | 0.136 | 0.190 | +0.054 |
| 45 days | 0.107 | 0.190 | +0.083 |
| 90 days | 0.016 | 0.190 | **+0.174** |

At a 90-day lag the honest signal is worth almost nothing (IC 0.016) while the leaky version
looks excellent. This is why `PITFundamentals.as_of()` filters on `filed <= date` and why the
period-end join exists only inside the audit, never in research code.

## 3. What was built

**Point-in-time fundamentals layer** (`sources/fundamentals.py`): a tidy table of
`cik, tag, period, filed, value` with reporting lag, restatement-aware ordering (a later filing
of the same period is new information, not a correction to the past), an `as_of(date)` query,
and per-date winsorising for the denominator blow-ups that ratios produce.

**Eight pre-registered fundamental hypotheses** (`factors/fundamental.py`), each with its
economic reason and expected sign written down before testing: earnings yield, book-to-market,
return on equity, operating margin, accruals, asset growth, leverage, cash-to-assets.

**Data QA** (`sources/qa.py`): reporting-lag distribution, tag coverage, restatement counts,
outlier counts, and a `problems()` list that flags the impossible (rows filed before their
period ended, implausibly short lags).

**Governance** (`governance.py`): an assumption register generated from the config — execution
timing, cost model, universe, data provenance, the point-in-time rule, trial-counting policy —
written automatically on every model run, plus an append-only exception log
(`alphalab exception --kind ... --reason ...`). Logged deviations now appear on every validity card.

## 4. What could not be done here

The US fundamental research block cannot be **run** in this environment: it has no network
access to sec.gov. The machinery is built and unit-tested offline against fixtures (74 tests),
so the sequence locally is:

1. `python -c "from alphalab.sources.sec_fsds import download_quarter; ..."` for a few quarters.
2. Spot-check 5–10 well-known names against their actual 10-K/10-Q on EDGAR.
3. Run `alphalab.sources.qa.report` and read `problems()` before computing a single factor.
4. Only then run the fundamental hypotheses through the existing hierarchical test.

Doing step 2 by hand is not optional: the SEC does not guarantee accuracy, and filer-chosen
tags mean the same concept appears under different names across companies.
