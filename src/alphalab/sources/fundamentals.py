"""Point-in-time fundamentals table and the as-of join.

One rule governs this whole module: **a fundamental value may only be used on
dates after it was filed.** SEC rows carry both `period` (what the numbers
describe) and `filed` (when the market could see them). Joining on `period` is
the fundamental-data equivalent of trading at the close you used to compute the
signal - it silently grants foresight over the reporting lag, which for annual
filings can be two months or more.

`PITFundamentals.as_of(date)` is the only supported way to read values, and it
filters on `filed <= date`. Everything downstream (factor library, QA) builds
on it, so the bias cannot be reintroduced by accident.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

REQUIRED = ("cik", "tag", "period", "filed", "value")


class PITFundamentals:
    def __init__(self, rows: pd.DataFrame):
        missing = [c for c in REQUIRED if c not in rows.columns]
        if missing:
            raise ValueError(f"missing columns: {missing}")
        df = rows.copy()
        df["filed"] = pd.to_datetime(df["filed"])
        df["period"] = pd.to_datetime(df["period"])
        df = df.dropna(subset=["filed", "period", "value"])
        # a later filing of the same (cik, tag, period) is a restatement: keep both,
        # ordered, so as_of() naturally serves whatever was current at the time
        self.rows = df.sort_values(["cik", "tag", "period", "filed"]).reset_index(drop=True)

    # ---- queries ------------------------------------------------------------
    @property
    def reporting_lag(self) -> pd.Series:
        return (self.rows["filed"] - self.rows["period"]).dt.days

    def as_of(self, date) -> pd.DataFrame:
        """Latest filed value of each (cik, tag) that was public on `date`."""
        d = pd.Timestamp(date)
        known = self.rows[self.rows["filed"] <= d]
        if known.empty:
            return known.assign(asof=d)
        latest = known.groupby(["cik", "tag"], as_index=False).last()
        return latest.assign(asof=d)

    def panel(self, tag: str, dates, ciks=None, leaky_period_join: bool = False) -> pd.DataFrame:
        """date x cik frame of one tag, forward-filled from filing dates.

        `leaky_period_join=True` deliberately joins on `period` instead of
        `filed`. It exists only so the protocol audit can measure how much
        apparent alpha that mistake creates - never use it in research.
        """
        sub = self.rows[self.rows["tag"] == tag]
        if ciks is not None:
            sub = sub[sub["cik"].isin(list(ciks))]
        if sub.empty:
            return pd.DataFrame(index=pd.DatetimeIndex(dates))
        key = "period" if leaky_period_join else "filed"
        wide = (sub.pivot_table(index=key, columns="cik", values="value", aggfunc="last")
                .sort_index())
        idx = pd.DatetimeIndex(dates)
        return wide.reindex(wide.index.union(idx)).ffill().reindex(idx)

    def coverage(self, dates, tag: str, ciks=None) -> pd.Series:
        p = self.panel(tag, dates, ciks)
        return p.notna().mean(axis=1) if not p.empty else pd.Series(0.0, index=pd.DatetimeIndex(dates))


def market_cap(price: pd.DataFrame, shares: pd.DataFrame) -> pd.DataFrame:
    """Price (date x id) times shares outstanding (date x id, PIT)."""
    return price * shares.reindex(index=price.index, columns=price.columns)


def winsorise(df: pd.DataFrame, lo: float = 0.01, hi: float = 0.99) -> pd.DataFrame:
    """Trim per-date tails: fundamental ratios have brutal outliers (tiny
    denominators), and a single one can dominate a cross-sectional rank."""
    q_lo = df.quantile(lo, axis=1)
    q_hi = df.quantile(hi, axis=1)
    return df.clip(q_lo, q_hi, axis=0).replace([np.inf, -np.inf], np.nan)
