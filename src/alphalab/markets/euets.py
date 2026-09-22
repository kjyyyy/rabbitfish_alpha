"""EU ETS carbon: auctions, scarcity and the curve you cannot get for free.

The EU Emissions Trading System is the largest carbon market by value, and it is
a genuinely different research problem from equities: supply is set by
regulation rather than by issuers, demand is a compliance obligation with an
annual deadline, and the tradable universe is one allowance plus a futures
curve. Three consequences drive everything in this module.

**1. Cross-sectional evaluation does not apply.** One instrument means no
ranking, no quintile spread, no market-neutral escape. Use `alphalab.timeseries`,
which reports Newey-West t-statistics and the number of genuinely independent
bets - because a timing signal at a monthly horizon makes about twelve decisions
a year, and IR = IC*sqrt(BR) is unforgiving at that breadth.

**2. The futures curve is not free.** Verified in the 2026 review: no free,
licence-clean, machine-readable settlement curve for EUA futures was found. The
best free price backbone (the Zenodo EU ETS Data Package, CC-BY-4.0) carries
AUCTION CLEARING PRICES, not futures settlements - so there is no term structure
in it at all. Carry and calendar-spread signals, the best-evidenced mechanisms in
commodities, are therefore **not computable from free data here**. That is the
same wall as front-month-only CFDs, and it should be settled before any research
time is spent, not after.

**3. What IS free is the interesting part.** Auction results are published by
EEX as public XLSX files with no login. Cover ratio, clearing price against the
secondary market, and bidder counts are a direct read on compliance demand
versus speculative positioning - a flow signal with a real mechanism and no
equity analogue. Registry data gives installation-level verified emissions.

**Licence, stated because it constrains what you may build.** EEX's terms bar
"systematic republication or dissemination of a substantial amount of the Data".
Fetching for personal research is one thing; redistributing a derived dataset is
another. The Zenodo package is CC-BY-4.0 and may be redistributed with
attribution.

**Point-in-time discipline is unusually easy to get wrong here.** Verified
emissions for a calendar year appear in early April of the following year - but
the exact date MOVES (1 April 2019; 9 April 2026 for CY2025). A fixed lag is
therefore itself a look-ahead risk, so `PolicyCalendar` stores the actual
release date of each figure and refuses to answer as of a date before it.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import numpy as np
import pandas as pd

# ---------------------------------------------------------------- contract --
# ICE Endex EUA Futures (symbol "C"), mirrored by EEX. Verified against the
# exchanges' own contract specification pages, 2026.
EUA_FUTURE = dict(
    symbol="C", exchange="ICE Endex", allowances_per_lot=1000, currency="EUR",
    tick_size=0.01, tick_value=10.00,          # EUR 0.01/tonne x 1,000 = EUR 10/lot
    settlement="physical",                      # allowance transfer, NOT cash settled
    last_trading_day="last Monday of the contract month (pushed for GB bank holidays)",
    note="December is a market CONVENTION, not a contract constraint: monthlies, "
         "quarterlies, July and August contracts also list. A roll rule that assumes "
         "December-only will silently mis-handle the others.")

# Market Stability Reserve, as revised in 2023. This is the supply rule any
# scarcity model keys on.
MSR = dict(
    upper_threshold=1_096_000_000,      # TNAC above this -> intake
    lower_threshold=400_000_000,        # TNAC below this -> 100m released
    taper_floor=833_000_000,            # from 2024, intake tapers within the band
    intake_rate=0.24,                   # 24% of TNAC
    release=100_000_000,
    tnac_published_by="1 June",         # moved from 15 May by the 2023 revision
    cycle="September to August",
    note="Above 400m the reserve permanently invalidates allowances from 2024. The "
         "thresholds are policy and have been revised before - treat them as data, not "
         "constants, and re-check them against the Directive before trusting a result.")


@dataclass
class PolicyCalendar:
    """Point-in-time answers for figures whose publication date moves.

    Verified emissions for calendar year Y appear in early April of Y+1, but the
    day is not fixed - 1 April in 2019, 9 April in 2026. Assuming a constant lag
    is a look-ahead bug in exactly the way a period-end fundamentals join is, and
    this lab has already measured what that class of error is worth.
    """
    releases: pd.DataFrame          # columns: series, period, value, released

    def as_of(self, series: str, when) -> pd.DataFrame:
        when = pd.Timestamp(when)
        r = self.releases
        m = (r["series"] == series) & (pd.to_datetime(r["released"]) <= when)
        return r[m].sort_values("released")

    def latest(self, series: str, when):
        rows = self.as_of(series, when)
        return None if rows.empty else rows.iloc[-1].to_dict()


# ----------------------------------------------------------------- auctions --
# The report is a public, year-parameterised XLSX. There is no documented free
# API, so a pipeline downloads and parses the workbook.
AUCTION_REPORT_URL = ("https://public.eex-group.com/eex/eua-auction-report/"
                      "emission-spot-primary-market-auction-report-{year}-data.xlsx")

# The 2026 review could NOT open this file - the outbound proxy returned 403 -
# and no EEX page documents the schema. These are therefore CANDIDATE column
# names, and `parse_auction_report` fails loudly rather than guessing if none of
# them match. Enumerate the real columns once and pin them.
COLUMN_CANDIDATES = {
    "date": ["Date", "Auction Date", "date"],
    "clearing_price": ["Auction Price", "Clearing Price", "Auction Price [EUR/tCO2]", "Price"],
    "volume": ["Auction Volume", "Offer Volume", "Volume", "Auctioned Volume"],
    "bids": ["Total Amount of Bids", "Total Bid Volume", "Bid Volume", "Demand"],
    "bidders": ["Number of Bidders", "Successful Bidders", "Bidders"],
}
SCHEMA_UNVERIFIED = True


def parse_auction_report(df: pd.DataFrame, strict: bool = True) -> pd.DataFrame:
    """Normalise an EEX auction workbook into date, price, volume, bids, bidders.

    Refuses to guess. If a required column cannot be matched the error names
    what was found, because a silently mis-mapped column produces a plausible
    series that is wrong - the worst failure mode available.
    """
    cols = {str(c).strip(): c for c in df.columns}
    found, missing = {}, []
    for field, candidates in COLUMN_CANDIDATES.items():
        hit = next((cols[c] for c in candidates if c in cols), None)
        if hit is None:
            hit = next((orig for name, orig in cols.items()
                        if any(c.lower() in name.lower() for c in candidates)), None)
        if hit is None:
            missing.append(field)
        else:
            found[field] = hit
    if missing and strict:
        raise ValueError(
            f"could not map column(s) {missing} in the auction report. Columns present: "
            f"{list(cols)[:20]}. The EEX schema is not documented and was NOT verified when "
            f"this parser was written - enumerate the real columns once and pin them in "
            f"COLUMN_CANDIDATES rather than letting a near-match through.")

    out = pd.DataFrame({k: df[v] for k, v in found.items()})
    if "date" in out:
        out["date"] = pd.to_datetime(out["date"], errors="coerce")
        out = out.dropna(subset=["date"]).set_index("date").sort_index()
    for c in out.columns:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out


def auction_signals(auctions: pd.DataFrame, secondary: pd.Series | None = None,
                    window: int = 20) -> pd.DataFrame:
    """Flow and positioning measures from auction results.

    Each has a stated mechanism, because a carbon signal with no mechanism is
    just a policy-driven series being data-mined:

    * **cover_ratio** = bids / volume offered. Compliance buyers must acquire
      allowances regardless of price; speculators need not. A falling cover ratio
      is compliance demand thinning relative to supply.
    * **auction_discount** = clearing price / secondary price - 1. Auctions
      normally clear at a small discount to the secondary market. A widening
      discount says the primary market is absorbing supply poorly.
    * **bidder_breadth** = participant count against its own recent history -
      participation broadening or narrowing.

    All are computed from data published AFTER each auction settles, so a signal
    built from them can only be traded at the next session.
    """
    a = auctions.sort_index()
    out = pd.DataFrame(index=a.index)
    if {"bids", "volume"} <= set(a.columns):
        out["cover_ratio"] = a["bids"] / a["volume"].replace(0, np.nan)
        out["cover_ratio_z"] = _z(out["cover_ratio"], window)
    if "bidders" in a.columns:
        out["bidder_breadth_z"] = _z(a["bidders"], window)
    if secondary is not None and "clearing_price" in a.columns:
        s = pd.Series(secondary).reindex(a.index).ffill()
        out["auction_discount"] = a["clearing_price"] / s.replace(0, np.nan) - 1.0
        out["auction_discount_z"] = _z(out["auction_discount"], window)
    return out


def _z(s: pd.Series, window: int) -> pd.Series:
    """Rolling z-score, strictly backward-looking."""
    r = s.rolling(window, min_periods=max(5, window // 2))
    return ((s - r.mean()) / r.std()).replace([np.inf, -np.inf], np.nan)


def msr_state(tnac: float) -> dict:
    """What the Market Stability Reserve does at this TNAC, and why.

    The supply rule is mechanical and published, which makes it the one part of
    this market where the forward supply path is genuinely knowable - and
    therefore the one place a modelling edge is plausible without a data edge.
    """
    if tnac > MSR["upper_threshold"]:
        intake = MSR["intake_rate"] * tnac
        action = "intake"
        detail = (f"TNAC {tnac:,.0f} is above the {MSR['upper_threshold']:,.0f} threshold, so "
                  f"{intake:,.0f} allowances are withdrawn over the next cycle")
    elif tnac > MSR["taper_floor"]:
        intake = tnac - MSR["taper_floor"]
        action = "tapered intake"
        detail = (f"TNAC {tnac:,.0f} is inside the taper band, so intake is the excess over "
                  f"{MSR['taper_floor']:,.0f} rather than the full 24%")
    elif tnac < MSR["lower_threshold"]:
        intake = -MSR["release"]
        action = "release"
        detail = (f"TNAC {tnac:,.0f} is below {MSR['lower_threshold']:,.0f}, so "
                  f"{MSR['release']:,.0f} allowances are released back to auctions")
    else:
        intake, action, detail = 0.0, "neutral", f"TNAC {tnac:,.0f} is inside the neutral band"
    return dict(tnac=float(tnac), action=action, net_withdrawal=float(intake), detail=detail,
                published_by=MSR["tnac_published_by"],
                caution="thresholds are policy and have been revised; re-check them against "
                        "the current Directive before trusting any result built on them")


# ------------------------------------------------------- pre-specified ideas --
# Deliberately a SHORT list with stated mechanisms rather than an open search.
# The universe is one instrument: breadth is a handful of independent bets a
# year, so a wide expression search would inflate the trial count that deflates
# every result while the achievable information ratio stays capped.
HYPOTHESES = [
    dict(name="auction_cover_ratio", signal="cover_ratio_z", sign=1,
         horizon_days=20, needs=["auction"],
         rationale="Compliance buyers must acquire allowances whatever the price; speculators "
                   "need not. A high cover ratio relative to its own history is compliance "
                   "demand arriving, which should support price."),
    dict(name="auction_discount", signal="auction_discount_z", sign=-1,
         horizon_days=10, needs=["auction", "secondary"],
         rationale="Auctions normally clear slightly below the secondary market. A widening "
                   "discount means the primary market is absorbing supply poorly, which "
                   "typically precedes weakness."),
    dict(name="bidder_breadth", signal="bidder_breadth_z", sign=1,
         horizon_days=20, needs=["auction"],
         rationale="Participation broadening is demand from more distinct balance sheets, "
                   "which is harder to reverse than the same volume from fewer hands."),
    dict(name="compliance_seasonal", signal="days_to_surrender", sign=-1,
         horizon_days=20, needs=["calendar"],
         rationale="The annual surrender deadline forces buying from entities short of "
                   "allowances. NOTE: the 2026 review could not confirm whether the deadline "
                   "is 30 April or 30 September under the revised Directive. Verify before "
                   "trading this; the sign of a seasonal is meaningless if the date is wrong."),
    dict(name="msr_scarcity", signal="msr_net_withdrawal", sign=1, horizon_days=60,
         needs=["tnac"],
         rationale="The MSR mechanically withdraws supply when TNAC is high. The rule is "
                   "published, so the forward supply path is knowable - the rare case where "
                   "a modelling edge does not require a data edge."),
]

# What is NOT here, and why:
#   - carry / calendar spreads: the best-evidenced commodity mechanism, but it needs a
#     futures curve, and no free licence-clean curve was found. Not a signal problem.
#   - fuel-switching spreads (EUA vs power/gas/coal): needs energy price data, also paid.
#   - EUA vs UK ETS relative value: plausible, and UK auction data is public, but the
#     two markets' auction calendars differ and the pairing needs its own study.
UNAVAILABLE_ON_FREE_DATA = ["carry", "calendar_spread", "fuel_switching", "basis_momentum"]


def days_to_surrender(dates, deadline_month: int = 9, deadline_day: int = 30) -> pd.Series:
    """Days until the annual compliance surrender deadline.

    The default is 30 September. The 2026 review could NOT confirm whether the
    revised Directive uses 30 April or 30 September, so this is a parameter with
    a flagged default rather than a constant - and a seasonal signal built on an
    unverified date is measuring the wrong thing.
    """
    idx = pd.DatetimeIndex(dates)
    out = []
    for d in idx:
        deadline = dt.date(d.year, deadline_month, deadline_day)
        if d.date() > deadline:
            deadline = dt.date(d.year + 1, deadline_month, deadline_day)
        out.append((deadline - d.date()).days)
    return pd.Series(out, index=idx, name="days_to_surrender")
