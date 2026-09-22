"""Futures and perpetual costs: ticks, not basis points. Margin, not capital.

Two things equity daily-bar research lets you get away with and futures does not:

**Costs are per contract, in ticks.** A tick on Brent is not a tick on corn, and
a bid-ask of one tick is a different cost on every market. Charging a percentage
of notional silently overcharges the cheap markets and undercharges the
expensive ones, which biases every cross-sectional comparison between them.

**The roll is a round trip you pay for having an opinion at all.** A monthly
contract rolled every cycle pays twelve round trips a year - twenty-four legs -
before any signal has traded. A backtest that models signal turnover but not
roll turnover understates cost by more than most signals are worth.

And for perpetuals, funding is a cash flow that accrues while you hold, not a
transaction cost. It is charged here at the position level, on the schedule the
venue uses, so that a carry strategy's P&L is the funding it collects minus the
fees it pays rather than a price series that pretends funding does not exist.

`notional`, `margin` and `nav` are tracked as three separate quantities because
they answer three different questions, and conflating them is how a futures
backtest ends up reporting a return on a denominator that was never at risk.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ContractSpec:
    """What one contract of this market actually is."""
    symbol: str
    multiplier: float = 1.0          # currency per point
    tick_size: float = 0.01          # minimum price increment
    commission: float = 2.5          # currency per contract per side
    spread_ticks: float = 1.0        # typical bid-ask in ticks
    initial_margin: float = 0.0      # currency per contract; 0 = unknown
    currency: str = "USD"
    sector: str = ""

    @property
    def tick_value(self) -> float:
        return self.tick_size * self.multiplier

    def cost_per_side(self, slippage_ticks: float = 0.5) -> float:
        """Commission plus half the spread plus slippage, in currency per contract."""
        return self.commission + (self.spread_ticks / 2 + slippage_ticks) * self.tick_value

    def cost_bp(self, price: float, slippage_ticks: float = 0.5) -> float:
        """The same cost expressed in basis points of notional, for comparison only."""
        notional = price * self.multiplier
        return 1e4 * self.cost_per_side(slippage_ticks) / notional if notional else float("nan")


@dataclass
class PerpSpec:
    """A perpetual swap: no expiry, no roll, but a funding cash flow instead."""
    symbol: str
    maker_bp: float = 2.0
    taker_bp: float = 5.0
    funding_interval_hours: int = 8
    multiplier: float = 1.0

    def cost_bp(self, taker: bool = True) -> float:
        return self.taker_bp if taker else self.maker_bp


def trade_cost(spec: ContractSpec, contracts: float, slippage_ticks: float = 0.5) -> float:
    """Currency cost of trading `contracts` (absolute size) one way."""
    return abs(float(contracts)) * spec.cost_per_side(slippage_ticks)


def roll_cost(spec: ContractSpec, contracts: float, n_rolls: int,
              slippage_ticks: float = 0.5) -> float:
    """A roll closes one contract and opens another: two sides, every cycle.

    This is charged whether or not the signal changed, which is exactly why it
    is so often missed - it does not appear in a turnover calculation driven by
    signal changes.
    """
    return 2.0 * n_rolls * trade_cost(spec, contracts, slippage_ticks)


def funding_pnl(position_notional: pd.Series, funding_rate: pd.Series) -> pd.Series:
    """Cash flow from perpetual funding.

    Sign convention: a POSITIVE funding rate means longs pay shorts, so a long
    position with positive funding is a negative cash flow. Getting this
    backwards turns the most reliably negative carry in crypto into the most
    reliably positive one, which is why it is stated here rather than implied.
    """
    pos, fund = position_notional.align(funding_rate, join="inner")
    return (-pos * fund).rename("funding_pnl")


def annualised_funding(funding_rate: pd.Series, interval_hours: int = 8) -> pd.Series:
    """Per-interval funding expressed as an annual rate, for comparison with carry."""
    periods = 24 / interval_hours * 365
    return (funding_rate * periods).rename("funding_apr")


@dataclass
class Book:
    """Notional, margin and NAV, tracked separately.

    NAV is what you own. Notional is what you control. Margin is what the
    exchange has locked, and it moves with volatility - so a position that was
    comfortably financed can force a deleverage without the signal changing.
    Reporting a return on notional flatters; reporting one on margin flatters
    more; the denominator that means anything is NAV.
    """
    nav: float
    positions: dict = field(default_factory=dict)      # symbol -> contracts

    def notional(self, specs: dict, prices: dict) -> float:
        return float(sum(abs(n) * specs[s].multiplier * prices[s]
                         for s, n in self.positions.items() if s in specs and s in prices))

    def margin(self, specs: dict) -> float:
        return float(sum(abs(n) * specs[s].initial_margin
                         for s, n in self.positions.items() if s in specs))

    def leverage(self, specs: dict, prices: dict) -> float:
        return self.notional(specs, prices) / self.nav if self.nav else float("inf")

    def margin_utilisation(self, specs: dict) -> float:
        return self.margin(specs) / self.nav if self.nav else float("inf")

    def check(self, specs: dict, prices: dict, max_leverage: float = 3.0,
              max_margin_use: float = 0.5) -> dict:
        lev, use = self.leverage(specs, prices), self.margin_utilisation(specs)
        problems = []
        if lev > max_leverage:
            problems.append(f"leverage {lev:.1f}x exceeds {max_leverage}x")
        if use > max_margin_use:
            problems.append(f"margin utilisation {use:.0%} exceeds {max_margin_use:.0%} - a "
                            f"volatility spike raises initial margin and forces a deleverage "
                            f"at the worst moment")
        return dict(nav=self.nav, notional=self.notional(specs, prices),
                    margin=self.margin(specs), leverage=lev, margin_utilisation=use,
                    ok=not problems, problems=problems)


def vol_target_contracts(nav: float, target_vol: float, price: float, spec: ContractSpec,
                         instrument_vol: float) -> float:
    """Contracts to hold for a given annualised volatility target.

    The CTA convention: size by risk, not by capital. Returns a fractional
    contract count - rounding it to whole contracts is the real constraint for
    a small book, and `round_lots` reports what that rounding costs.
    """
    if instrument_vol <= 0 or price <= 0 or spec.multiplier <= 0:
        return 0.0
    notional_per_contract = price * spec.multiplier
    return float(nav * target_vol / (instrument_vol * notional_per_contract))


def round_lots(desired: float) -> dict:
    """What whole-contract rounding does to the intended position.

    For a small book this is often the binding constraint: a position of 0.4
    contracts is either 0 or a 150% overweight, and no amount of signal research
    changes that.
    """
    whole = float(np.trunc(desired))
    err = (whole - desired) / desired if desired else 0.0
    return dict(desired=float(desired), holdable=whole, rounding_error=float(err),
                untradeable=bool(abs(desired) < 1.0),
                note=("position rounds to zero - this market is not reachable at this account "
                      "size, and pretending otherwise is the most common way a small futures "
                      "backtest becomes fiction" if abs(desired) < 1.0 else ""))
