# EU ETS carbon: what fits, what does not, and what it cost to find out

Companion to `HARVESTING.md` and `docs/crypto-and-futures.md`. Research notes:
`research_notes/Crypto and futures alpha fit/eu_ets_data_and_specs.md`.

## The short version

EU ETS is a good fit for the lab's **gates** and a poor fit for its **evaluation geometry**. One
tradable instrument plus a curve means `evaluate.py` — which requires more than 30 names per date
and silently produces nothing below that — is **undefined** on this market. That is why v0.15 adds
`alphalab.timeseries`.

The second constraint is harder: **the futures curve is not available free**, so carry and
calendar spreads — the best-evidenced commodity mechanisms — cannot be computed. What *is* free is
the auction data, and that turns out to be the interesting part.

## Contract mechanics (verified against exchange specifications, 2026)

| | ICE Endex EUA Future (symbol `C`) |
|---|---|
| Size | **1,000 allowances per lot** |
| Currency | EUR |
| Tick | €0.01/tonne = **€10.00 per lot** |
| Settlement | **Physical** — allowance transfer, not cash |
| Last trading day | Last Monday of the contract month, pushed for GB bank holidays |
| Listed | Up to 7 December, 9 quarterly, 3 August and 2 monthly contracts |

EEX mirrors this (1,000 EUA/lot, €0.01 tick, delivery T+2 ECC business days).

**Roll trap:** December-only is a market *convention*, not a contract constraint. Monthlies,
quarterlies, July and August contracts all list, so a roll rule that assumes annual December
vintages will silently mishandle them. Physical delivery also means the last trading day functions
like a first notice day — the roll engine's `first_notice` column is the right place to put it.

## What is free, and what it forbids

| Source | Contents | Licence reality |
|---|---|---|
| **EEX auction reports** | Public year-parameterised XLSX, no login | Terms bar "systematic republication or dissemination of a substantial amount of the Data" — fetch for research, do not redistribute |
| **Zenodo EU ETS Data Package** | CC-BY-4.0, CSV + schema, Zenodo REST API | Redistributable with attribution — but its prices are **auction clearing prices, not futures settlements**, so there is no term structure in it |
| **Union Registry** | Installation-level verified emissions, allocations, surrenders (XLSX) | Public |
| **Futures settlement curve** | — | **No free, licence-clean, machine-readable source was found** |

These terms attach to the data, not to this MIT-licensed code. See
[`NOTICE.md`](../NOTICE.md#data-licences) for the full record (EEX, ENTSO-E,
Zenodo, Open-Meteo / ECMWF, TTF gas and API2 coal). This repository ships no
data; users are responsible for the terms of whatever they fetch.

**The auction report schema is unverified.** The outbound proxy returned 403 on
`public.eex-group.com`, and no EEX page documents the columns. `parse_auction_report` therefore
**refuses to guess**: it raises and names what it found rather than accepting a near-match, because
a silently mis-mapped column produces a plausible series that is wrong. Enumerate the real columns
once and pin them in `COLUMN_CANDIDATES`; `SCHEMA_UNVERIFIED` stays `True` until someone does.

## Point-in-time discipline, which is unusually easy to get wrong here

Verified emissions for calendar year *Y* appear in early April of *Y+1* — but **the date moves**:
1 April in 2019, 9 April in 2026 (for CY2025). A fixed lag is therefore itself a look-ahead bug, of
exactly the kind this lab measured to be worth +0.054 to +0.174 of IC in the fundamentals timing
test. `PolicyCalendar` stores the **actual release date** of every figure and refuses to answer as
of a date before it.

Compliance data follows in early October of *Y+1*; transaction data lags about **three years**.

## The Market Stability Reserve

Intake of 24% of TNAC above 1,096m; a taper down to 833m inside the band from 2024; 100m released
below 400m; permanent invalidation above 400m. TNAC is published **by 1 June** (moved from 15 May
by the 2023 revision), on a September–August cycle.

This is the one part of the market where the forward supply path is genuinely *knowable* — the
rule is published and mechanical — which makes it the rare place a modelling edge is plausible
without a data edge. Thresholds are policy and have been revised before: `msr_state` treats them
as data and says so.

## The hypotheses, and what is deliberately absent

Five pre-specified ideas with stated mechanisms, **not a search**: auction cover ratio, auction
discount to secondary, bidder breadth, the compliance seasonal, and MSR scarcity.

Absent, and recorded rather than backlogged: **carry, calendar spreads, basis momentum and
fuel switching** — each needs either a futures curve or energy prices, and neither is free. On real
data these are the mechanisms with the best evidence, which is why the free-data route is a genuine
constraint here rather than an inconvenience.

Two facts the research could not settle, both of which affect a signal's meaning:

- **The surrender deadline** (30 April or 30 September under the revised Directive) is
  unconfirmed. `days_to_surrender` takes it as a parameter, because a seasonal built on the wrong
  date measures the wrong thing.
- **ETS2's start** — the Commission's own July 2026 auction-calendar note says January 2027;
  several February 2026 sources say it was postponed to 2028. Unresolved.

## What the demonstration showed

`scripts/euets_demo.py` runs the whole path on synthetic data with one genuine relationship
planted in the cover ratio. Two results, neither of them the one I expected:

**1. A signal only works at a horizon that matches its own memory.** The planted effect has a
one-day impact on a signal whose autocorrelation reaches zero in about eleven days. Its IC runs
0.021 → 0.027 → 0.028 at horizons of 1, 5 and 10 days, then collapses to 0.002 at 20 days and turns
negative at 60. My first two attempts at this fixture failed because I planted a one-day effect and
tested a twenty-day horizon, and then because I planted on the *level* of a series whose signal is
a rolling z-score — nearly orthogonal quantities. Both failures are in the commit history because
they are the same mistake a researcher makes on real data.

**2. The horizon sweep is itself a search, and it is expensive.** Four signals across five horizons
is **twenty trials, not four**. The best result the sweep found was `compliance_seasonal@60d` at
Sharpe 0.54 — a signal with *nothing planted in it*, being a deterministic calendar countdown. It
scores:

| | DSR | Sharpe needed for DSR 0.95 |
|---|---|---|
| As if it had been the only hypothesis | **0.837** | 0.82 |
| Counting the 20 trials the sweep spent | **0.060** | 1.58 |

That is the lab's entire argument in one line: **a pure-noise signal looks like a discovery until
you count the search that found it.** It is also the argument for choosing a horizon from the
signal's own memory rather than trying them all.

## Verdict

Worth building on, with clear eyes:

- **Fits:** the gates, the trial counting, the point-in-time machinery, the roll engine (physical
  delivery and last-trading-day rules map onto it directly), and the new time-series path.
- **Does not fit:** cross-sectional search. Breadth here is a handful of independent bets a year,
  so the GP refiner and a wide expression space are the wrong tools — the right shape is a few
  pre-specified structures evaluated hard, which is what `euets.HYPOTHESES` is.
- **Blocked on data:** anything involving the curve. Settle whether you can obtain a licensed
  settlement curve before spending research time, exactly as with front-month-only CFDs.
