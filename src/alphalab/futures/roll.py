"""Continuous futures series: three independent decisions, kept independent.

A "continuous contract" is not a thing that exists. It is a construction, and
most futures research errors live in it rather than in the signal. The three
decisions are separable and this module keeps them separate, because conflating
them is what makes the errors invisible:

1. **Roll timing** - when to stop looking at the front contract and start
   looking at the next. Calendar (N days before expiry or first notice day),
   open interest crossover, or volume crossover.
2. **Splicing** - how to join the two price series into one. Back-adjusted
   ("Panama"), ratio-adjusted, or unadjusted.
3. **Return computation** - how P&L is actually calculated.

The rule that matters most, and the one most often broken: **returns are chained
WITHIN a contract and never across a roll.** A roll is a change of instrument,
not a price move. Differencing across the boundary of an unadjusted series
fabricates a jump equal to the spread between contracts; and because that spread
is the roll return, adding a separate "roll yield" term to a correctly chained
series double-counts it.

Two traps this module refuses to let you walk into:

* **Back-adjusted prices can go negative.** In persistent contango, each roll
  subtracts a positive gap, and enough rolls drive an old price through zero.
  Then log returns are undefined, ratio-based momentum is nonsense, and
  volatility scaling silently inverts near the crossing. `continuous(...,
  adjust="back")` is provided because the literature uses it, and it returns a
  loud warning when the series crosses zero.
* **Open-interest and volume roll rules look ahead** unless the decision is made
  on data available *before* the decision date. `lag_days` defaults to 1 and the
  schedule records it, because a roll rule that peeks is a leak the gates
  downstream cannot see.

The invariant that catches most mistakes: a ratio-adjusted price series and the
wealth curve built by chaining per-contract returns must agree up to a single
constant multiplier. `invariant_check` asserts exactly that.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

METHODS = ("calendar", "open_interest", "volume")
ADJUSTMENTS = ("ratio", "back", "none")


def _require(panel: pd.DataFrame, cols) -> None:
    missing = [c for c in cols if c not in panel.columns]
    if missing:
        raise ValueError(f"panel is missing column(s): {', '.join(missing)}")


def roll_schedule(panel: pd.DataFrame, method: str = "calendar", offset_days: int = 5,
                  lag_days: int = 1, price_col: str = "settle") -> pd.DataFrame:
    """Which contract is held on each date.

    `panel` is indexed by (date, contract) with at least `expiry` and, for the
    liquidity-based methods, `open_interest` or `volume`.

    Returns a frame indexed by date with `held`, `next`, `is_roll` and the
    parameters used, so the schedule is a stored artefact rather than an
    implicit consequence of whichever code path ran.
    """
    if method not in METHODS:
        raise ValueError(f"unknown roll method {method!r}; choose from {METHODS}")
    _require(panel, ["expiry"])
    p = panel.copy()
    p.index = p.index.set_names(["date", "contract"])
    dates = p.index.get_level_values("date").unique().sort_values()

    rows = []
    for d in dates:
        day = p.xs(d, level="date")
        # A contract is only holdable while its DEADLINE is in the future. For a
        # physically delivered contract that deadline is first notice day, not
        # expiry: hold past FND and you can be assigned delivery of the physical
        # commodity. When the panel supplies `first_notice` it governs.
        deadline_col = "first_notice" if "first_notice" in day.columns else "expiry"
        day = day[pd.to_datetime(day[deadline_col]) > d]
        if price_col in day:
            day = day[day[price_col].notna()]
        if day.empty:
            # Nothing holdable today. Emitting no row is the honest answer - it
            # is how a panel that has run out of contracts announces itself,
            # rather than quietly holding something into delivery.
            continue
        day = day.sort_values("expiry")

        if method == "calendar":
            # roll `offset_days` before the deadline of the front contract
            deadline = pd.to_datetime(day.iloc[0][deadline_col])
            held = day.index[0] if (deadline - d).days > offset_days else (
                day.index[1] if len(day) > 1 else day.index[0])
        else:
            col = "open_interest" if method == "open_interest" else "volume"
            _require(panel, [col])
            # THE LOOK-AHEAD GUARD: decide on data from `lag_days` ago. Deciding
            # on today's open interest uses a number not published until after
            # the close you are trading.
            past = dates[dates <= d]
            ref_date = past[-(lag_days + 1)] if len(past) > lag_days else past[0]
            ref = p.xs(ref_date, level="date")
            ref = ref[ref.index.isin(day.index)].sort_values("expiry")
            if ref.empty or len(ref) < 2:
                held = day.index[0]
            else:
                front, second = ref.index[0], ref.index[1]
                # switch once the next contract carries more liquidity than the front
                held = second if ref.loc[second, col] > ref.loc[front, col] else front
                if held not in day.index:
                    held = day.index[0]

        pos = list(day.index).index(held) if held in list(day.index) else 0
        nxt = day.index[pos + 1] if pos + 1 < len(day) else None
        rows.append(dict(date=d, held=held, next=nxt))

    sched = pd.DataFrame(rows).set_index("date")
    sched["is_roll"] = sched["held"] != sched["held"].shift(1)
    sched.loc[sched.index[0], "is_roll"] = False
    sched.attrs.update(method=method, offset_days=offset_days, lag_days=lag_days,
                       price_col=price_col)
    return sched


def chained_returns(panel: pd.DataFrame, sched: pd.DataFrame,
                    price_col: str = "settle") -> pd.Series:
    """Per-period returns, computed WITHIN a contract and never across a roll.

    This is the P&L truth. On a roll date the return is the held contract's own
    move from its previous close to today's - the old contract's price never
    enters, because you no longer own it. The roll return is captured
    automatically by the fact that the new contract is a different instrument at
    a different price; adding a separate roll-yield term would count it twice.
    """
    _require(panel, [price_col])
    px = panel[price_col].unstack()                     # date x contract
    out = {}
    prev_held, prev_px = None, None
    for d, row in sched.iterrows():
        held = row["held"]
        cur = px.at[d, held] if held in px.columns and d in px.index else np.nan
        if prev_held == held and prev_px == prev_px and prev_px not in (None, 0):
            out[d] = cur / prev_px - 1.0
        else:
            out[d] = 0.0 if prev_held is None else np.nan
            if prev_held is not None and prev_held != held:
                # a roll: the day's return is the NEW contract's own move, if it
                # traded yesterday too. Otherwise there is no return to report.
                i = px.index.get_loc(d)
                if i > 0 and held in px.columns:
                    y = px.iloc[i - 1][held]
                    if y == y and y != 0:
                        out[d] = cur / y - 1.0
        prev_held, prev_px = held, cur
    return pd.Series(out).astype(float).rename("return")


def continuous(panel: pd.DataFrame, sched: pd.DataFrame, adjust: str = "ratio",
               price_col: str = "settle") -> pd.Series:
    """A single price series for signal computation.

    `ratio` multiplies away each roll gap and is the default: the series stays
    strictly positive, so log returns, ratio momentum and volatility scaling all
    remain meaningful. `back` reproduces the Panama convention used in the
    literature and can go negative - it warns when it does. `none` returns the
    raw held-contract price, which is correct for nothing except inspection,
    because it contains the roll jumps.
    """
    if adjust not in ADJUSTMENTS:
        raise ValueError(f"unknown adjustment {adjust!r}; choose from {ADJUSTMENTS}")
    _require(panel, [price_col])
    px = panel[price_col].unstack()
    raw = pd.Series({d: (px.at[d, r["held"]] if r["held"] in px.columns else np.nan)
                     for d, r in sched.iterrows()}).astype(float)
    if adjust == "none":
        return raw.rename("price")

    # gap at each roll, measured on the overlap day where BOTH contracts traded
    gaps = []
    for d, r in sched[sched["is_roll"]].iterrows():
        i = px.index.get_loc(d)
        if i == 0:
            continue
        prev_held = sched["held"].iloc[sched.index.get_loc(d) - 1]
        y = px.index[i - 1]
        new_prev = px.at[y, r["held"]] if r["held"] in px.columns else np.nan
        old_prev = px.at[y, prev_held] if prev_held in px.columns else np.nan
        if new_prev == new_prev and old_prev == old_prev and old_prev != 0:
            gaps.append((d, new_prev - old_prev, new_prev / old_prev))

    adj = raw.copy()
    if adjust == "back":
        # subtract each gap from everything BEFORE it, oldest applied last
        for d, diff, _ in gaps:
            adj.loc[adj.index < d] -= diff
        if (adj <= 0).any():
            first = adj[adj <= 0].index[0]
            adj.attrs["warning"] = (
                f"back-adjusted series crosses zero at {first.date()}: in persistent contango "
                f"each roll subtracts a positive gap and old prices are driven through zero. "
                f"Log returns, ratio momentum and volatility scaling are all invalid on this "
                f"series. Use adjust='ratio' for signals.")
    else:
        for d, _, ratio in gaps:
            if ratio and ratio == ratio and ratio > 0:
                adj.loc[adj.index < d] *= ratio
    adj.attrs.update(adjust=adjust, rolls=len(gaps))
    return adj.rename("price")


def invariant_check(panel: pd.DataFrame, sched: pd.DataFrame, price_col: str = "settle",
                    tol: float = 1e-6) -> dict:
    """The ratio-adjusted price series and the chained wealth curve must agree.

    Both describe the same thing - what one unit of this exposure did - so they
    can differ only by a constant multiplier. If the ratio of the two is not
    flat, the roll logic and the return logic disagree, and one of them is
    fabricating P&L at the roll boundaries. This is the single cheapest test
    that catches most continuous-contract errors, and it runs on any panel.
    """
    ratio_px = continuous(panel, sched, "ratio", price_col).dropna()
    rets = chained_returns(panel, sched, price_col).reindex(ratio_px.index).fillna(0.0)
    wealth = (1.0 + rets).cumprod()
    both = pd.concat([ratio_px, wealth.rename("wealth")], axis=1).dropna()
    if len(both) < 3:
        return dict(ok=False, note="not enough overlapping observations")
    k = both.iloc[:, 0] / both["wealth"]
    drift = float(k.max() / k.min() - 1.0) if k.min() > 0 else float("inf")
    ok = bool(drift < max(tol, 1e-9) * 1e3 or drift < 1e-3)
    return dict(ok=ok, constant_ratio=float(k.iloc[0]), relative_drift=drift,
                n=len(both),
                note=("ratio-adjusted prices and chained returns agree up to a constant, as "
                      "they must" if ok else
                      "MISMATCH: the roll logic and the return logic disagree, so one of them "
                      "is fabricating P&L at a roll boundary. Do not trust any backtest on "
                      "this panel until it passes."))


def roll_sensitivity(panel: pd.DataFrame, price_col: str = "settle",
                     methods=METHODS, offsets=(1, 3, 5, 10)) -> pd.DataFrame:
    """How much does the result depend on an arbitrary choice?

    Roll timing is a free parameter nobody has a prior over. If the annualised
    return swings materially across these settings, the finding is about the
    roll rule rather than the market - and reporting only the best setting is
    the same error as reporting only the best factor.
    """
    rows = []
    for m in methods:
        for off in (offsets if m == "calendar" else (0,)):
            try:
                s = roll_schedule(panel, m, offset_days=off, price_col=price_col)
                r = chained_returns(panel, s, price_col).dropna()
                rows.append(dict(method=m, offset_days=off, n_rolls=int(s["is_roll"].sum()),
                                 ann_return=float((1 + r).prod() ** (252 / max(len(r), 1)) - 1),
                                 ann_vol=float(r.std() * np.sqrt(252)),
                                 sharpe=float(r.mean() / r.std() * np.sqrt(252))
                                 if r.std() > 0 else float("nan")))
            except Exception as e:                    # noqa: BLE001 - a rule may not apply
                rows.append(dict(method=m, offset_days=off, error=str(e)[:60]))
    df = pd.DataFrame(rows)
    if "sharpe" in df and df["sharpe"].notna().any():
        spread = float(df["sharpe"].max() - df["sharpe"].min())
        df.attrs["sharpe_spread"] = spread
        df.attrs["verdict"] = (
            "roll choice dominates the result - this is a finding about the roll rule, not "
            "the market" if spread > 0.5 else "result is robust to the roll rule")
    return df
