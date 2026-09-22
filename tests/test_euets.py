"""EU ETS carbon, and the time-series path a one-instrument market requires."""
import numpy as np
import pandas as pd
import pytest

from alphalab import timeseries as ts
from alphalab.markets import euets


# --------------------------------------------------------------------------
# time-series evaluation: the statistics the cross-sectional path gets free
# --------------------------------------------------------------------------
def test_overlapping_windows_inflate_the_naive_t_statistic():
    """A 20-day forward return sampled daily shares 19 days with its neighbour."""
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2015-01-01", periods=1500)
    px = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, len(dates)))), index=dates)
    fwd = ts.forward_return(px, horizon=20, lag=1)
    signal = pd.Series(rng.normal(0, 1, len(dates)), index=dates)     # pure noise

    out = ts.evaluate_ts(signal, fwd, horizon=20)
    assert out["t_newey_west"] == out["t_newey_west"]
    assert abs(out["t_newey_west"]) < abs(out["t_naive"]) * 1.05, (
        "Newey-West must not be larger than the naive statistic on overlapping data")
    assert out["overlap_inflation"] is not None


def test_a_real_signal_survives_the_correction_and_noise_does_not():
    rng = np.random.default_rng(3)
    n = 1500
    dates = pd.bdate_range("2015-01-01", periods=n)
    signal = pd.Series(rng.normal(0, 1, n), index=dates)
    # a genuine but modest relationship
    fwd = pd.Series(0.02 * signal.to_numpy() + rng.normal(0, 0.05, n), index=dates)
    real = ts.evaluate_ts(signal, fwd, horizon=20)
    noise = ts.evaluate_ts(pd.Series(rng.normal(0, 1, n), index=dates), fwd, horizon=20)
    assert real["t_newey_west"] > 3 > abs(noise["t_newey_west"])
    assert real["ic_spearman"] > noise["ic_spearman"]


def test_breadth_of_a_timing_signal_is_counted_and_small():
    dates = pd.bdate_range("2015-01-01", periods=1000)
    fast = pd.Series(np.random.default_rng(1).normal(0, 1, 1000), index=dates)
    out = ts.independent_decisions(fast, horizon=20, periods_per_year=252)
    assert out["naive_bets_per_year"] == pytest.approx(12.6, abs=0.1)
    assert out["bets_per_year"] <= out["naive_bets_per_year"]

    # a slow-moving signal makes fewer decisions than its sampling rate suggests
    slow = pd.Series(np.repeat(np.random.default_rng(2).normal(0, 1, 50), 20)[:1000], index=dates)
    assert ts.independent_decisions(slow, 20)["bets_per_year"] < out["bets_per_year"]


def test_forward_return_does_not_start_on_the_signal_day():
    px = pd.Series(np.arange(100, 200, dtype=float),
                   index=pd.bdate_range("2024-01-01", periods=100))
    fwd = ts.forward_return(px, horizon=5, lag=1)
    # the return from t+1 to t+6, never including the close the signal was computed from
    assert fwd.iloc[0] == pytest.approx(px.iloc[6] / px.iloc[1] - 1)


# --------------------------------------------------------------------------
# the auction parser refuses to guess
# --------------------------------------------------------------------------
def test_the_parser_fails_loudly_rather_than_mis_mapping_a_column():
    """The EEX schema was NOT verified when this was written (the proxy 403'd),
    so a near-match must be an error rather than a plausible wrong series."""
    junk = pd.DataFrame({"Something": [1, 2], "Else": [3, 4]})
    with pytest.raises(ValueError, match="could not map column"):
        euets.parse_auction_report(junk)
    assert euets.SCHEMA_UNVERIFIED is True, "the flag must stay until someone opens the file"


def test_the_parser_normalises_a_plausible_workbook():
    raw = pd.DataFrame({
        "Date": pd.bdate_range("2024-01-01", periods=5),
        "Auction Price": [70.1, 71.2, 69.8, 72.0, 70.5],
        "Auction Volume": [3_000_000] * 5,
        "Total Amount of Bids": [5_000_000, 6_000_000, 4_000_000, 7_000_000, 5_500_000],
        "Number of Bidders": [18, 20, 15, 22, 19]})
    out = euets.parse_auction_report(raw)
    assert list(out.columns) == ["clearing_price", "volume", "bids", "bidders"]
    assert out.index.name == "date" and len(out) == 5


# --------------------------------------------------------------------------
# auction signals
# --------------------------------------------------------------------------
def _auctions(n=250, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2023-01-02", periods=n)
    return pd.DataFrame({
        "clearing_price": 70 + np.cumsum(rng.normal(0, 0.5, n)),
        "volume": 3_000_000.0,
        "bids": 3_000_000 * (1.5 + rng.normal(0, 0.3, n)),
        "bidders": rng.integers(12, 25, n).astype(float)}, index=idx)


def test_cover_ratio_and_discount_are_computed_from_published_data_only():
    a = _auctions()
    secondary = a["clearing_price"] * 1.005          # auctions clear slightly below
    sig = euets.auction_signals(a, secondary)
    assert {"cover_ratio", "cover_ratio_z", "bidder_breadth_z",
            "auction_discount", "auction_discount_z"} <= set(sig.columns)
    assert sig["cover_ratio"].mean() == pytest.approx(1.5, abs=0.1)
    assert sig["auction_discount"].mean() < 0, "auctions clearing below secondary is a discount"


def test_the_rolling_z_score_never_looks_forward():
    a = _auctions()
    sig = euets.auction_signals(a)
    a2 = a.copy()
    a2.iloc[-1, a2.columns.get_loc("bids")] *= 10      # change only the LAST observation
    sig2 = euets.auction_signals(a2)
    pd.testing.assert_series_equal(sig["cover_ratio_z"].iloc[:-1], sig2["cover_ratio_z"].iloc[:-1])


# --------------------------------------------------------------------------
# policy mechanics
# --------------------------------------------------------------------------
@pytest.mark.parametrize("tnac,action", [
    (1_200_000_000, "intake"), (900_000_000, "tapered intake"),
    (600_000_000, "neutral"), (300_000_000, "release")])
def test_msr_reproduces_the_published_supply_rule(tnac, action):
    s = euets.msr_state(tnac)
    assert s["action"] == action
    assert "re-check them against the current Directive" in s["caution"]


def test_msr_intake_is_24_percent_above_the_threshold():
    s = euets.msr_state(1_500_000_000)
    assert s["net_withdrawal"] == pytest.approx(0.24 * 1_500_000_000)


def test_a_moving_publication_date_is_stored_not_assumed():
    """Verified emissions appear in early April - but on 1 April in 2019 and
    9 April in 2026. A fixed lag is itself a look-ahead bug."""
    rel = pd.DataFrame([
        dict(series="verified_emissions", period=2024, value=1_200.0, released="2025-04-02"),
        dict(series="verified_emissions", period=2025, value=1_150.0, released="2026-04-09"),
    ])
    cal = euets.PolicyCalendar(rel)
    assert cal.latest("verified_emissions", "2026-04-08")["period"] == 2024, (
        "on 8 April 2026 the CY2025 figure was not yet public")
    assert cal.latest("verified_emissions", "2026-04-09")["period"] == 2025
    assert cal.latest("verified_emissions", "2019-01-01") is None


def test_hypotheses_are_few_pre_specified_and_carry_mechanisms():
    assert len(euets.HYPOTHESES) <= 8, (
        "one instrument means a handful of independent bets a year; a wide search would "
        "inflate the trial count while the achievable IR stays capped")
    for h in euets.HYPOTHESES:
        assert h["sign"] in (-1, 1) and len(h["rationale"]) > 60
    assert "carry" in euets.UNAVAILABLE_ON_FREE_DATA, (
        "the best-evidenced commodity mechanism needs a curve, and no free licence-clean "
        "curve was found - that belongs on the record, not in a backlog")


def test_the_surrender_date_is_a_flagged_parameter_not_a_constant():
    d = euets.days_to_surrender(pd.to_datetime(["2026-01-15", "2026-09-29", "2026-10-01"]))
    assert d.iloc[0] > d.iloc[1] and d.iloc[2] > 300
    april = euets.days_to_surrender(pd.to_datetime(["2026-01-15"]), deadline_month=4)
    assert april.iloc[0] != d.iloc[0], "the deadline must be a parameter: it was not verified"
