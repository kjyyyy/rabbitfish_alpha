"""Continuous futures construction, tested where it usually goes wrong.

Every test here corresponds to a documented failure mode: back-adjusted prices
crossing zero, look-ahead in a liquidity-based roll rule, fabricated P&L at the
roll boundary, and roll timing quietly dominating the result.
"""
import numpy as np
import pandas as pd
import pytest

from alphalab.futures import costs, roll


def panel(n_days=260, contango=True, seed=0, step=0.0):
    """A synthetic dated-contract panel with a known term structure.

    Quarterly contracts, each priced at the spot path plus a per-contract offset
    that is positive in contango. The offset is what a roll must remove.
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-02", periods=n_days)
    spot = 100 * np.exp(np.cumsum(rng.normal(step, 0.01, n_days)))
    rows = []
    for k in range(6):
        expiry = dates[0] + pd.Timedelta(days=60 * (k + 1))
        offset = (3.0 if contango else -3.0) * (k + 1)
        live = dates[dates <= expiry]
        for d in live:
            if d < expiry - pd.Timedelta(days=200):
                continue
            days_left = (expiry - d).days
            rows.append(dict(date=d, contract=f"C{k}", settle=spot[list(dates).index(d)] + offset,
                             volume=1e5 * max(1, 30 - abs(days_left - 30)),
                             open_interest=1e4 * max(1, 45 - abs(days_left - 25)),
                             expiry=expiry))
    return pd.DataFrame(rows).set_index(["date", "contract"]).sort_index()


# --------------------------------------------------------------------------
# the invariant: the two views of the same exposure must agree
# --------------------------------------------------------------------------
@pytest.mark.parametrize("method", ["calendar", "open_interest", "volume"])
def test_ratio_series_and_chained_returns_agree_up_to_a_constant(method):
    p = panel()
    s = roll.roll_schedule(p, method=method)
    out = roll.invariant_check(p, s)
    assert out["ok"], out
    assert out["relative_drift"] < 1e-3, (
        "the ratio-adjusted price series and the chained wealth curve describe the same "
        "exposure, so a drift between them means P&L is being fabricated at a roll")


def test_the_invariant_actually_fails_when_returns_cross_a_roll():
    """Guard the guard: differencing the raw held-contract price fabricates a jump."""
    p = panel()
    s = roll.roll_schedule(p)
    raw = roll.continuous(p, s, adjust="none").dropna()
    naive = raw.pct_change().fillna(0.0)                  # the classic mistake
    honest = roll.chained_returns(p, s).reindex(naive.index).fillna(0.0)
    assert not np.allclose(naive, honest), "this test is meaningless if the two agree"
    gap = float(abs((1 + naive).prod() - (1 + honest).prod()))
    assert gap > 0.01, (
        f"differencing across rolls should fabricate visible P&L; saw {gap:.4f}")


# --------------------------------------------------------------------------
# back-adjustment: the negative-price trap
# --------------------------------------------------------------------------
def test_back_adjusted_series_warns_when_it_crosses_zero():
    p = panel(n_days=400, contango=True)
    s = roll.roll_schedule(p)
    back = roll.continuous(p, s, adjust="back")
    ratio = roll.continuous(p, s, adjust="ratio")
    assert (ratio.dropna() > 0).all(), "ratio adjustment must keep the series positive"
    if (back.dropna() <= 0).any():
        assert "crosses zero" in back.attrs.get("warning", ""), \
            "a back-adjusted series that goes negative must say so: log returns, ratio "\
            "momentum and vol scaling are all invalid on it"


def test_ratio_adjustment_removes_the_roll_gap():
    p = panel(contango=True)
    s = roll.roll_schedule(p)
    ratio = roll.continuous(p, s, adjust="ratio").dropna()
    raw = roll.continuous(p, s, adjust="none").dropna()
    roll_days = s.index[s["is_roll"]]
    for d in roll_days[1:]:
        if d not in ratio.index or d not in raw.index:
            continue
        i = ratio.index.get_loc(d)
        if i == 0:
            continue
        jump_raw = abs(raw.iloc[i] / raw.iloc[i - 1] - 1)
        jump_adj = abs(ratio.iloc[i] / ratio.iloc[i - 1] - 1)
        assert jump_adj <= jump_raw + 1e-9


# --------------------------------------------------------------------------
# look-ahead in liquidity-based roll rules
# --------------------------------------------------------------------------
def test_liquidity_roll_decides_on_lagged_data():
    """A roll rule reading today's open interest uses a number published after
    the close it trades. The schedule must record the lag it used."""
    p = panel()
    s = roll.roll_schedule(p, method="open_interest", lag_days=1)
    assert s.attrs["lag_days"] == 1
    assert s.attrs["method"] == "open_interest"

    # with a longer lag the schedule may differ, but must never roll EARLIER
    slow = roll.roll_schedule(p, method="open_interest", lag_days=5)
    first_fast = s.index[s["is_roll"]][0] if s["is_roll"].any() else None
    first_slow = slow.index[slow["is_roll"]][0] if slow["is_roll"].any() else None
    if first_fast is not None and first_slow is not None:
        assert first_slow >= first_fast, "more lag cannot cause an earlier roll"


def test_calendar_roll_respects_first_notice_day_when_present():
    p = panel().copy()
    p["first_notice"] = pd.to_datetime(p["expiry"]) - pd.Timedelta(days=20)
    s = roll.roll_schedule(p, method="calendar", offset_days=5)
    days_to_fnd = [(pd.to_datetime(p.xs(d, level="date").loc[r["held"], "first_notice"]) - d).days
                   for d, r in s.iterrows()]
    assert min(days_to_fnd) > 0, (
        "a physically delivered contract must be exited before first notice day, not before "
        "expiry - holding past FND risks assignment of the physical commodity")

    # when nothing is holdable the schedule must emit NO row rather than quietly
    # holding a contract into delivery
    all_dates = p.index.get_level_values("date").unique()
    assert len(s) < len(all_dates), (
        "the tail of this panel has no contract left to roll into, so those dates must be "
        "absent from the schedule")


# --------------------------------------------------------------------------
# does the answer depend on an arbitrary choice?
# --------------------------------------------------------------------------
def test_roll_sensitivity_reports_a_spread_across_rules():
    p = panel(step=0.0004)
    df = roll.roll_sensitivity(p)
    assert len(df) >= 4 and "sharpe" in df
    assert "verdict" in df.attrs
    assert df["n_rolls"].max() >= 1


# --------------------------------------------------------------------------
# costs in ticks, and the three denominators
# --------------------------------------------------------------------------
def test_costs_are_denominated_in_ticks_not_basis_points():
    brent = costs.ContractSpec("BRN", multiplier=1000, tick_size=0.01, commission=2.5,
                               spread_ticks=1, initial_margin=6000)
    corn = costs.ContractSpec("ZC", multiplier=50, tick_size=0.25, commission=2.5,
                              spread_ticks=1, initial_margin=1800)
    assert brent.tick_value == pytest.approx(10.0)
    assert corn.tick_value == pytest.approx(12.5)
    # the same one-tick spread is a very different cost in bp of notional
    assert brent.cost_bp(70.0) < corn.cost_bp(450.0) * 10
    assert brent.cost_per_side() > 0 and corn.cost_per_side() > 0


def test_the_roll_is_charged_as_a_round_trip_even_with_no_signal_change():
    spec = costs.ContractSpec("BRN", multiplier=1000, tick_size=0.01, commission=2.5)
    held_flat = costs.roll_cost(spec, contracts=2, n_rolls=12)
    assert held_flat == pytest.approx(2 * 12 * costs.trade_cost(spec, 2))
    assert held_flat > 0, (
        "twelve monthly rolls cost twenty-four legs a year before any signal trades; a "
        "turnover model driven by signal changes alone misses all of it")


def test_funding_sign_convention_is_the_right_way_round():
    dates = pd.date_range("2024-01-01", periods=10)
    long = pd.Series(10_000.0, index=dates)
    positive_funding = pd.Series(0.0001, index=dates)     # longs pay shorts
    pnl = costs.funding_pnl(long, positive_funding)
    assert (pnl < 0).all(), "a long paying positive funding must lose money"
    assert costs.funding_pnl(-long, positive_funding).gt(0).all()
    apr = costs.annualised_funding(positive_funding, 8)
    assert apr.iloc[0] == pytest.approx(0.0001 * 3 * 365)


def test_notional_margin_and_nav_are_three_different_numbers():
    spec = costs.ContractSpec("BRN", multiplier=1000, tick_size=0.01, initial_margin=6000)
    book = costs.Book(nav=100_000, positions={"BRN": 4})
    state = book.check({"BRN": spec}, {"BRN": 70.0}, max_leverage=3.0, max_margin_use=0.5)
    assert state["notional"] == pytest.approx(280_000)
    assert state["margin"] == pytest.approx(24_000)
    assert state["leverage"] == pytest.approx(2.8)
    assert state["margin_utilisation"] == pytest.approx(0.24)
    assert state["ok"]
    over = costs.Book(nav=100_000, positions={"BRN": 10}).check({"BRN": spec}, {"BRN": 70.0})
    assert not over["ok"] and over["problems"]


def test_whole_contract_rounding_is_the_binding_constraint_for_a_small_book():
    spec = costs.ContractSpec("BRN", multiplier=1000, tick_size=0.01)
    want = costs.vol_target_contracts(nav=25_000, target_vol=0.15, price=70.0,
                                      spec=spec, instrument_vol=0.35)
    r = costs.round_lots(want)
    assert r["untradeable"] is True and r["holdable"] == 0
    assert "not reachable at this account size" in r["note"]

    big = costs.round_lots(costs.vol_target_contracts(1_000_000, 0.15, 70.0, spec, 0.35))
    assert big["holdable"] >= 1 and not big["untradeable"]
