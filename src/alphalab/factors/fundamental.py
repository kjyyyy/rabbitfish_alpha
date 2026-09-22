"""Pre-registered fundamental hypotheses.

Each is written down with its economic reason, expected sign and the SEC tags
it needs, BEFORE any of them is tested - that is what makes the trial count in
the Deflated Sharpe honest. They are computed from `PITFundamentals`, so every
value is one that had already been filed on the day it is used.

Ratios are formed against market data (price, shares outstanding) so they move
daily; the fundamental numerator only changes when a new filing arrives.
"""
from __future__ import annotations

import pandas as pd

from ..sources.fundamentals import PITFundamentals, winsorise

HYPOTHESES = [
    dict(name="earnings_yield", sign=+1, tags=("NetIncomeLoss",),
         rationale="Value: cheap earnings outperform. The oldest documented cross-sectional "
                   "effect; the other side is investors extrapolating growth."),
    dict(name="book_to_market", sign=+1, tags=("StockholdersEquity",),
         rationale="Value: high book-to-market outperforms (Fama-French HML)."),
    dict(name="return_on_equity", sign=+1, tags=("NetIncomeLoss", "StockholdersEquity"),
         rationale="Quality: profitable firms earn higher returns, and profitability is "
                   "persistent in a way price momentum is not."),
    dict(name="operating_margin", sign=+1, tags=("OperatingIncomeLoss", "Revenues"),
         rationale="Quality: margin is a cleaner profitability signal than net income, which "
                   "carries one-off items."),
    dict(name="accruals", sign=-1, tags=("NetIncomeLoss", "NetCashProvidedByUsedInOperatingActivities"),
         rationale="Accruals anomaly (Sloan 1996): earnings not backed by cash flow reverse; "
                   "investors fixate on the headline number."),
    dict(name="asset_growth", sign=-1, tags=("Assets",),
         rationale="Asset-growth anomaly: firms that expand the balance sheet fastest "
                   "subsequently underperform (empire building, overinvestment)."),
    dict(name="leverage", sign=-1, tags=("Liabilities", "Assets"),
         rationale="Distress: highly levered firms carry risk that is not compensated at "
                   "this horizon."),
    dict(name="cash_to_assets", sign=+1, tags=("CashAndCashEquivalentsAtCarryingValue", "Assets"),
         rationale="Balance-sheet strength: cash cushions provide optionality and survive "
                   "funding shocks."),
]


def compute(name: str, fun: PITFundamentals, dates, price: pd.DataFrame,
            shares: pd.DataFrame | None = None, leaky_period_join: bool = False) -> pd.DataFrame:
    """Compute one named hypothesis as a date x cik frame."""
    def tag(t):
        return fun.panel(t, dates, ciks=price.columns, leaky_period_join=leaky_period_join)

    mcap = (price * shares.reindex(index=price.index, columns=price.columns)
            if shares is not None else price)
    if name == "earnings_yield":
        out = tag("NetIncomeLoss") / mcap
    elif name == "book_to_market":
        out = tag("StockholdersEquity") / mcap
    elif name == "return_on_equity":
        out = tag("NetIncomeLoss") / tag("StockholdersEquity")
    elif name == "operating_margin":
        out = tag("OperatingIncomeLoss") / tag("Revenues")
    elif name == "accruals":
        out = (tag("NetIncomeLoss") - tag("NetCashProvidedByUsedInOperatingActivities")) / tag("Assets")
    elif name == "asset_growth":
        a = tag("Assets")
        out = a / a.shift(250) - 1
    elif name == "leverage":
        out = tag("Liabilities") / tag("Assets")
    elif name == "cash_to_assets":
        out = tag("CashAndCashEquivalentsAtCarryingValue") / tag("Assets")
    else:
        raise KeyError(f"unknown fundamental hypothesis: {name}")
    return winsorise(out.replace([float("inf"), float("-inf")], pd.NA).astype(float))


def composite(fun: PITFundamentals, dates, price, shares=None, leaky_period_join=False,
              names=None) -> pd.DataFrame:
    """Equal-weight composite of signed, cross-sectionally ranked hypotheses."""
    parts = []
    for h in HYPOTHESES:
        if names and h["name"] not in names:
            continue
        f = compute(h["name"], fun, dates, price, shares, leaky_period_join)
        if f.notna().to_numpy().sum() == 0:
            continue
        parts.append((f.rank(axis=1, pct=True) - 0.5).fillna(0.0) * h["sign"])
    if not parts:
        return pd.DataFrame(index=pd.DatetimeIndex(dates))
    return sum(parts) / len(parts)
