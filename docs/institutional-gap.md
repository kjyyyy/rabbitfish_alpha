# What institutions do that this lab does (and cannot do)

From the research in `docs/research/04-institutional-arbitrage.md`.

## The dividing line

An edge is reachable to the extent its profit comes from **knowing something**, and unreachable to
the extent it comes from **being somewhere, being large, or being licensed**.

| Institutional edge | Reachable? | Why |
|---|---|---|
| Market making: quoting, spread capture, inventory skewing | No | Needs colocation, direct feeds, exchange membership and flow |
| Payment for order flow / internalised retail flow | No | Requires being the wholesaler (Citadel Securities paid $2.6bn for flow in 2020–21) |
| ETF creation/redemption arbitrage | No | Requires authorised-participant status; only 3–5 APs per ETF |
| Balance-sheet dislocation trades (March 2020 bond ETFs) | No | Needs capital and dealer inventory |
| Index-rebalance and expiry flow trading | Mostly no | Needs size and, as the Jane Street India case showed, the ability to move the underlying |
| Cross-sectional signals at daily horizon | **Yes** | Research-dependent, not latency-dependent |
| Factor/style neutralisation and risk modelling | **Yes** | Built in `risk.py` — a price-only substitute for Barra |
| Cost-aware construction: bands, caps, impact models | **Yes** | Built in `portfolio.py`; the largest measured gain in this project |
| Post-trade cost analysis and crowding monitoring | **Yes** | `crowding_r2` here; TCA needs live fills |
| Capacity as a *weapon* | **Yes, uniquely** | Impact scales with √size: at ¥100k impact was 0.14%/yr vs 4.3%/yr at ¥100m |

## The uncomfortable finding

Running the lab's own signal through this layer showed that **62% of its predictive power was
style exposure** (low beta, small size, low volatility). Institutions separate "alpha" from
"factor beta" precisely so they do not pay fees for something buyable cheaply. Any signal here
should be reported both raw and style-neutral; if it dies when neutralised, it is a factor tilt,
which is a legitimate thing to own — but own it cheaply, not through a high-turnover book.

## What is still missing

| Gap | Status | Note |
|---|---|---|
| Point-in-time fundamentals | Not built | Price-only signals have a low ceiling; SEC XBRL is the free substitute for US |
| Delisting-return handling | Partly | The CN dataset has point-in-time membership; US via Yahoo does not (Shumway: omitted delisting returns average −30%) |
| Execution algos, live fills, TCA | Not built | Backtests assume trading at the next close; live slippage is unmeasured until paper trading runs |
| Borrow availability for shorts | Not modelled per name | Borrow is bimodal (25bp general collateral to >100% for hard-to-borrow); a flat 50bp is assumed |
| Intraday data | Not used | Daily bars only |
| Vendor risk model | Substituted | Price-only factors instead of Barra/Axioma |

## UK-specific costs to remember

- **Cash shares:** 0.5% stamp duty on purchases (AIM exempt) — configured in `uk_ftse350.yaml`.
- **CFDs:** financing is roughly base rate +3% on longs and base rate −3% on shorts, so a
  dollar-neutral CFD book pays about **3% of gross per year in financing regardless of rate
  levels**. At the edge sizes measured here, that alone would erase the strategy.
- **Spread bets** are free of CGT but losses are not relievable.
