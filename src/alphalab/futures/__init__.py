"""Futures and perpetuals: contract panels, roll construction, tick-based costs.

A continuous contract is a construction, not a fact. `roll` keeps the three
decisions that build one - timing, splicing, return computation - separate and
recorded, and refuses the two ways they are usually got wrong (look-ahead in a
liquidity-based roll rule, and percentage returns on a back-adjusted series).
`costs` prices trades in ticks per contract rather than basis points of
notional, charges the roll as the round trip it is, and tracks notional, margin
and NAV as three different numbers.
"""
from .costs import Book, ContractSpec, PerpSpec, funding_pnl, roll_cost, trade_cost
from .roll import chained_returns, continuous, invariant_check, roll_schedule, roll_sensitivity

__all__ = ["Book", "ContractSpec", "PerpSpec", "funding_pnl", "roll_cost", "trade_cost",
           "chained_returns", "continuous", "invariant_check", "roll_schedule",
           "roll_sensitivity"]
