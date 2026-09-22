# Free data that is good enough for production

The constraint: **anything this lab depends on must be free, reliably published, and
licence-clean**, because a strategy that needs a paid feed you might not renew is not a
production strategy. This page is the registry. Each source lists what it buys, what it costs,
and what it is *not*.

## Tier 1 — regulator-published, free, licence-clean

| Source | What it buys | Format / cadence | Watch out for |
|---|---|---|---|
| [SEC Financial Statement Data Sets](https://www.sec.gov/data-research/sec-markets-data/financial-statement-data-sets) | **Point-in-time US fundamentals**, as filed, 2009Q2 onwards. Value, quality, growth, accruals, balance-sheet stress | Quarterly ZIPs (`sub.txt` + `num.txt`) | SEC states it cannot guarantee accuracy; filer-chosen tags vary; amendments arrive as new rows. Join to prices on `filed`, never on `period` |
| [SEC EDGAR full index](https://www.sec.gov/Archives/edgar/full-index/) (Forms 25 / 25-NSE) | **Delisting dates** — lets you keep dead names in the universe | Quarterly `form.idx`, plain text | Gives the date, not the delisting *return*. Apply a documented assumption (Shumway: ≈ −30% for performance delistings) and disclose it |
| [SEC company_tickers.json](https://www.sec.gov/files/company_tickers.json) | CIK ↔ ticker mapping | JSON, updated daily | Current mapping only; ticker reuse is real, so key on CIK |
| [FRED](https://fred.stlouisfed.org/) | Rates, spreads, macro regime inputs | CSV/API, free key | Some series are revised — use ALFRED vintages if a factor depends on the level |
| [CFTC Commitments of Traders](https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm) | Futures positioning | Weekly, free | Published Friday for Tuesday — a 3-day lag that must be modelled |
| [EIA](https://www.eia.gov/opendata/) | Energy inventories and production | Free API key | Revisions; release calendar matters |
| [Bank of England](https://www.bankofengland.co.uk/boeapps/database/) / [ONS](https://www.ons.gov.uk/) | UK rates and macro | Free | UK equity *prices* are not here — see Tier 3 |

SEC requests a descriptive `User-Agent` with contact details on every request; the adapters
in `src/alphalab/sources/` do that.

## Tier 2 — free prices, fine for research, not for redistribution

| Source | Reality check |
|---|---|
| [Qlib community CN dataset](https://github.com/chenditc/investment_data) | What this lab uses today. Free, includes **point-in-time index membership**, updated daily. Not official exchange data |
| Stooq | Free global daily OHLCV, permits personal/non-commercial use. **Delisted tickers disappear** |
| yfinance | Broad coverage, but scrapes an undocumented endpoint; personal research only, do not redistribute. Back-adjusted prices change whenever a dividend is paid, so two pulls on different dates disagree |
| Tiingo / Alpha Vantage free tiers | Explicit terms, attribution required, no resale. Tight rate limits (Alpha Vantage a few calls a minute) |

The honest summary from the survivorship literature: free price feeds are "good enough to build
a pipeline and learn a method" but are "not survivorship-bias-free and not point-in-time
correct". The fix is not a better free price feed — it is combining a free price feed with the
Tier 1 delisting calendar so dead names stay in the universe.

## Tier 3 — gaps with no good free answer

- **UK equity prices with point-in-time index membership.** No free, licence-clean source found.
  A UK book would need a paid feed, or to trade US/CN where free data is adequate.
- **Borrow availability and cost.** No free source; the lab assumes a flat rate and says so.
- **Intraday data.** Free tiers are too thin for a serious intraday study.
- **Analyst estimates and revisions.** Paid only.

## What this changes for the lab

Ranked by expected value, costing nothing but effort:

1. **Add PIT fundamentals for a US universe** (`sources/sec_fsds.py`). This is the one lever that
   moves the lab out of price-only signals, where the evidence says the edge is picked over.
2. **Build a delisting-aware universe** (`sources/delistings.py`) before trusting any US result.
3. **Keep the CN dataset as the control set.** It already has point-in-time membership, so it
   stays the place where portfolio mechanics and gates are tested.

Status: both adapters are implemented and unit-tested offline against fixtures
(`tests/test_sources.py`). They have **not** been run against the live SEC endpoints from this
environment, which has no network access to sec.gov — run `python -m alphalab.sources.sec_fsds`
style downloads locally and check the first quarter by hand before trusting a factor built on it.
