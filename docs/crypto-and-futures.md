# Crypto and commodity futures: what the lab needs that equities did not

Companion to `HARVESTING.md`. The full research behind this is in
`docs/research/05-crypto-and-futures-alpha-fit.md`; this page is the engineering consequence.

## The verdict in one line

**Commodity futures is the better destination; crypto is the better laboratory.** Commodity carry
paid roughly 10%/yr in both the 1959–2004 and 2005–2014 samples, while crypto's flagship
mechanism — perpetual funding — has collapsed to a formula floor near 11% APR that prints as a
*constant* 78% of the time on BTC, and is barred to UK retail by the FCA's still-standing
crypto-derivatives ban. But free **per-contract** commodity data no longer exists (Nasdaq Data
Link's CHRIS continuous futures is deprecated with no replacement; Stooq began requiring a key in
March 2026), whereas Binance publishes bulk history for individual dated COIN-M quarterly
contracts for nothing.

So build and prove the roll engine on free crypto dated futures, then point it at commodities —
and deliver the data bill only once the engineering works.

## What equities let us get away with

| Assumption | Equities | Crypto | Futures |
|---|---|---|---|
| Calendar | business days | **24/7, no close convention** | exchange-specific, with holidays |
| Instrument identity | stable ticker | listings and delistings churn | **a contract expires; you must roll** |
| Carry | none modelled | **funding, every 8h** | **the term structure is the signal** |
| Costs | bp of notional | bp, but maker/taker differ sharply | **ticks per contract, not bp** |
| Capital | cash | cash + funding | **notional ≠ margin ≠ NAV** |
| Survivorship | index membership history | **catastrophic; no free delisting register** | contract universes silently curated |
| Sizing | fractional shares | fractional | **whole contracts only** |

## The roll engine (`alphalab.futures.roll`)

A continuous contract is a construction, not a fact. Three decisions, kept separate because
conflating them hides the errors:

1. **Timing** — `calendar` (N days before expiry, or **first notice day** when the panel supplies
   it, because a physically delivered contract must be exited before FND or you risk assignment),
   `open_interest`, or `volume`.
2. **Splicing** — `ratio` (default; stays strictly positive), `back` (the Panama convention; **can
   go negative**), or `none`.
3. **Return computation** — chained **within** a contract, never across a roll.

### Three traps the code refuses to let you walk into

**Look-ahead in liquidity-based roll rules.** Deciding today's roll on today's open interest uses
a number published after the close you are trading. `lag_days` defaults to 1 and the schedule
records it.

**Back-adjusted prices crossing zero.** In persistent contango each roll subtracts a positive gap,
and enough rolls drive old prices through zero. Log returns become undefined, ratio momentum
becomes nonsense, and volatility scaling silently inverts near the crossing. `continuous(...,
adjust="back")` warns when it happens.

**Fabricated P&L at the roll.** Differencing across an unadjusted series invents a jump equal to
the inter-contract spread. And because that spread *is* the roll return, adding a separate "roll
yield" term to a correctly chained series **double-counts it**.

### The invariant that catches most of it

```python
from alphalab.futures import roll
sched = roll.roll_schedule(panel, method="calendar", offset_days=5)
assert roll.invariant_check(panel, sched)["ok"]
```

A ratio-adjusted price series and the wealth curve from chained returns describe the same
exposure, so they can differ only by a constant multiplier. If they drift, one of them is
fabricating P&L at a roll boundary. This is the cheapest test that catches continuous-contract
errors, and it runs on any panel.

`roll_sensitivity()` then sweeps timing rules. If the annualised result swings across them, the
finding is about the roll rule rather than the market — and reporting only the best setting is the
same error as reporting only the best factor.

## Costs (`alphalab.futures.costs`)

Charged **per contract in ticks**. A one-tick spread on Brent (tick value $10) is a different cost
from a one-tick spread on corn (tick value $12.50) at a completely different notional; charging a
percentage of notional silently overcharges cheap markets and undercharges expensive ones, which
biases every cross-market comparison.

**The roll is a round trip paid every cycle** whether or not the signal moved — twelve monthly
rolls is twenty-four legs a year before any signal trades. A turnover model driven by signal
changes alone misses all of it.

**Funding is a holding cash flow, not a transaction cost.** Sign convention, stated because
getting it backwards turns crypto's most reliably negative carry into its most reliably positive
one: **positive funding means longs pay shorts**.

**Three denominators.** `Book` tracks NAV (what you own), notional (what you control) and margin
(what the exchange has locked, which *rises with volatility* and can force a deleverage without
the signal changing). Returns are reported on NAV.

**Whole-contract rounding is the binding constraint for a small book.** `round_lots` reports when a
volatility-targeted position rounds to zero — that market is simply not reachable at that account
size, and pretending otherwise is the most common way a small futures backtest becomes fiction.

## Connectivity (`alphalab.connect`)

Three layers, and this repo implements two:

```
data       read-only credentials, or none
research   ZERO exchange credentials; emits timestamped target positions
execution  holds every credential, contains no strategy logic     <-- NOT BUILT
```

`connect.targets` writes a **target book**: what the portfolio should hold, as of a timestamp,
content-hashed. State, not events — replay it twice and nothing happens twice; a process that dies
halfway leaves a reconcilable state rather than a half-sent order sequence.

Nothing in the package can place, cancel or amend an order, and no function accepts a credential.
A test asserts this against the parsed syntax tree. That is a decision, not an unfinished feature:
no factor has passed a fully-counted Deflated Sharpe and there are zero clean forward weeks, so an
execution path would be plumbing for a decision the evidence has not supported.

### On MetaMask

MetaMask is a browser extension that holds keys for a **human** to approve transactions one at a
time. There is no supported way for a headless research process to use it. The usual workaround —
putting the private key in an environment variable so a script can sign — removes every protection
MetaMask exists to provide.

The blast radii are not comparable:

| Credential | Worst case if leaked |
|---|---|
| Read-only API key | your data |
| Trade-enabled key, no withdrawal | account drained by contra-trading illiquid pairs |
| **Hot private key** | **total, irreversible loss** |

A server-side system that genuinely needs on-chain execution uses a scoped session or delegated
key that cannot withdraw, a hardware signer, or a custody service. This lab needs none of them.

## Data

**Crypto — free and deep.** Binance's bulk archive (`data.binance.vision`) publishes zipped CSVs
per symbol per month including `fundingRate` and `metrics`, with `.CHECKSUM` files. Two documented
traps, both handled in `connect.sources`: spot archive timestamps switched to **microseconds from
1 January 2025** (a silent mid-series unit change), and the archive **retains delisted symbols** —
which, diffed against the live symbol list, is the only free survivorship register found.
CoinGecko states plainly that historical data for inactive or delisted coins is not available
through its API, so a universe built from a live listing has already deleted the left tail.

**Commodities — not free per contract.** CHRIS is dead; CME website settlements are not clearly
licensed for a pipeline; the licence-clean route is a paid feed. What *is* free and stable is
positioning and fundamentals: CFTC Commitments of Traders (futures-only back to 1986) and EIA.

**The asymmetry to exploit:** crypto gives you dated contracts for free, so you can own your roll
methodology at zero cost. Commodities do not. Build the engine where the data is free.

## Access, which eliminates strategy classes before signals do

The **FCA ban on selling crypto derivatives to retail consumers** (effective January 2021) has not
been lifted — only the crypto ETN portion was, in October 2025, with derivatives explicitly "under
review". That rules out the funding, basis and perp-momentum family through UK-regulated channels
before any strategy analysis matters.

For commodities the decisive question is whether you can reach real exchange contracts at all:
**CFD and spread-bet accounts typically expose a front-month synthetic price only, and carry,
basis and basis-momentum — the three best-evidenced signals — cannot be computed from it.** If the
implementation route is CFDs, what remains is trend, which is a two-parameter structure rather
than a search problem. That determination costs a phone call and reshapes the entire programme.

## Open gaps, stated rather than filled

The research could not verify, and this page does not assert: the survivorship-bias uplift in
crypto backtests as a number (every practitioner source asserts it matters; none publishes a
with-versus-without comparison); current CME tick sizes and fees; a minimum viable UK account
size; IBKR market-data pricing (the figures retrieved appear to be a page-extraction artefact);
and UK tax treatment, which was not checked against HMRC primary sources.
