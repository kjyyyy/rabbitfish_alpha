"""The validation corrections, each tested against the failure it exists to catch."""
import numpy as np
import pandas as pd
import pytest

from alphalab import breadth, validation


# --------------------------------------------------------------------------
# CPCV
# --------------------------------------------------------------------------
def test_cpcv_purges_and_embargoes_around_every_test_block():
    splits = validation.cpcv_splits(400, n_blocks=8, n_test=2, purge=10, embargo=5)
    assert splits, "a 400-observation series should yield paths"
    for train, test in splits:
        assert not set(train) & set(test), "train and test must be disjoint"
        gap = min(abs(int(t) - int(tr)) for t in test[:5] for tr in train)
        assert gap >= 1
        # nothing within the purge window before a test block survives in train
        lo = int(test.min())
        assert not any(lo - 10 <= int(i) < lo for i in train), "purge window leaked"


def test_cpcv_returns_a_distribution_not_a_point_estimate():
    rng = np.random.default_rng(0)
    r = pd.Series(rng.normal(0.002, 0.02, 400))
    out = validation.cpcv(r, n_blocks=8, n_test=2)
    assert out["paths"] > 10
    assert out["sharpe_p05"] < out["sharpe_p50"] < out["sharpe_p95"]
    assert 0.0 <= out["prob_negative"] <= 1.0


def test_cpcv_on_pure_noise_straddles_zero():
    rng = np.random.default_rng(3)
    out = validation.cpcv(pd.Series(rng.normal(0, 0.02, 500)), n_blocks=8, n_test=2)
    assert out["prob_negative"] > 0.2, (
        "a noise strategy must show a real chance of a negative Sharpe; if it does not, the "
        "paths are not independent enough to be informative")


def test_cpcv_declines_rather_than_guesses_on_a_short_series():
    assert validation.cpcv(pd.Series(np.zeros(10)))["paths"] == 0


# --------------------------------------------------------------------------
# the overfitting factor
# --------------------------------------------------------------------------
def test_overfitting_factor_halves_a_backtest_sharpe():
    out = validation.overfitting_factor(1.4, n_tweaks=0)
    assert out["factor"] == pytest.approx(2.0, abs=0.01)
    assert out["sharpe_discounted"] == pytest.approx(0.7, abs=0.01)
    assert out["passes"] is True, "1.4 backtest is exactly the CFM threshold for 0.7 live"


def test_more_tweaking_means_a_harsher_discount():
    light = validation.overfitting_factor(1.5, n_tweaks=1)["factor"]
    heavy = validation.overfitting_factor(1.5, n_tweaks=200)["factor"]
    assert heavy > light >= 2.0
    assert validation.overfitting_factor(0.9, n_tweaks=20)["passes"] is False


def test_the_discount_can_never_flatter_a_result():
    for s in (0.1, 0.5, 1.0, 3.0):
        out = validation.overfitting_factor(s)
        assert out["factor"] >= 1.0 and out["sharpe_discounted"] <= s


# --------------------------------------------------------------------------
# log wealth: the statistic crypto breaks
# --------------------------------------------------------------------------
def test_a_strategy_can_average_up_and_compound_down():
    """The fat-tail failure a t-test cannot see: many small gains, rare huge losses.

    95% of periods make 5%, 5% lose 75%. Arithmetic mean +1.0% per period at
    t = 2.6 — comfortably "significant" — while wealth compounds to roughly
    e^-46 of its starting value. This is the shape crypto actually produces,
    and a Sharpe built on the arithmetic mean describes a return nobody receives.
    """
    r = pd.Series([0.05] * 1900 + [-0.75] * 100)
    out = validation.log_wealth_test(r)
    assert out["mean_return"] > 0 and out["mean_t"] > 2, "the mean is significantly positive"
    assert out["log_wealth"] < 0, "yet wealth compounds to a loss"
    assert out["mean_positive_but_compounds_negative"] is True
    assert "not harvestable" in out["note"]


def test_a_healthy_series_passes_the_log_wealth_test():
    rng = np.random.default_rng(1)
    out = validation.log_wealth_test(pd.Series(rng.normal(0.004, 0.02, 300)))
    assert out["compounds"] is True
    assert out["mean_positive_but_compounds_negative"] is False
    assert out["variance_drag"] > 0, "the arithmetic mean always exceeds the geometric mean"


def test_total_loss_is_reported_rather_than_producing_a_number():
    out = validation.log_wealth_test(pd.Series([0.01] * 50 + [-1.0]))
    assert out["total_loss"] is True and "meaningless" in out["note"]


# --------------------------------------------------------------------------
# lagged-signal decay
# --------------------------------------------------------------------------
def test_a_latency_race_is_identified_as_one():
    out = validation.lagged_signal_decay(lambda lag: 0.20 * (0.25 ** lag))
    assert out["half_life_periods"] == 1 and out["latency_race"] is True


def test_a_patient_signal_is_not_flagged():
    out = validation.lagged_signal_decay(lambda lag: 0.10 - 0.002 * lag)
    assert out["latency_race"] is False
    assert out["cost_per_period_of_delay"] == pytest.approx(0.002, abs=1e-6)


def test_a_failing_lag_does_not_abort_the_sweep():
    def flaky(lag):
        if lag == 2:
            raise RuntimeError("no data at this lag")
        return 0.1
    out = validation.lagged_signal_decay(flaky, lags=(0, 1, 2, 3))
    assert out["errors"][2] and out["curve"][0] == 0.1


# --------------------------------------------------------------------------
# cost sensitivity, with the rule pre-committed
# --------------------------------------------------------------------------
def test_an_edge_that_dies_at_three_times_costs_is_named_as_a_cost_artefact():
    out = validation.cost_sweep(lambda m: 0.12 - 0.05 * m)
    assert out["breaks_at_multiple"] == 3.0
    assert out["survives_3x"] is False
    assert "cost assumption, not an edge" in out["verdict"]
    assert out["zero_cost_uplift"] == pytest.approx(0.05)


def test_a_robust_edge_survives_the_sweep():
    out = validation.cost_sweep(lambda m: 0.30 - 0.02 * m)
    assert out["survives_3x"] is True and out["breaks_at_multiple"] is None


# --------------------------------------------------------------------------
# breadth: the arithmetic that does not port to a thin universe
# --------------------------------------------------------------------------
def _correlated(n_inst, rho, n=500, seed=0):
    rng = np.random.default_rng(seed)
    common = rng.normal(0, 1, n)
    return pd.DataFrame({f"i{j}": np.sqrt(rho) * common + np.sqrt(1 - rho) * rng.normal(0, 1, n)
                         for j in range(n_inst)})


def test_a_common_factor_collapses_raw_breadth_but_not_neutral_breadth():
    """The distinction that decides which number to use.

    Forty instruments sharing one dominant factor are a handful of bets to a
    LONG-ONLY book - that is the market, held forty ways. To a dollar-neutral
    book the common factor cancels and the bets are the idiosyncratic residuals,
    so breadth survives. Reporting only the raw figure would tell a market-
    neutral strategy it has three bets when it has forty.
    """
    wide = breadth.effective_breadth(_correlated(40, 0.05))
    tight = breadth.effective_breadth(_correlated(40, 0.75))

    assert wide["independent_bets"] > 20
    assert tight["independent_bets"] < 5, "raw breadth collapses under a dominant factor"
    assert tight["independent_bets_neutral"] > 20, (
        "after removing the cross-sectional mean the common factor is gone, so a neutral book "
        "still has plenty of independent bets")
    assert abs(tight["avg_correlation_neutral"]) < abs(tight["avg_correlation"])


def test_genuinely_few_instruments_cannot_be_rescued_by_neutralising():
    """A commodity book is thin in both senses: there is nothing to cancel."""
    few = breadth.effective_breadth(_correlated(6, 0.35))
    assert few["independent_bets_neutral"] <= 6
    assert breadth.required_ic(0.7, few["breadth_per_year"]) > \
        breadth.required_ic(0.7, breadth.effective_breadth(_correlated(300, 0.1))["breadth_per_year"])


def test_the_ic_a_thin_universe_needs_is_much_higher():
    thin = breadth.required_ic(0.7, breadth_per_year=6 * 52)
    wide = breadth.required_ic(0.7, breadth_per_year=300 * 52)
    assert thin > wide * 5, "IR = IC*sqrt(BR): less breadth demands far more skill per bet"


def test_a_wide_search_over_a_narrow_universe_is_called_out():
    """Six contracts and four hundred trials: 67 trials per independent bet."""
    out = breadth.assess(_correlated(6, 0.4), n_trials_planned=400, market="futures")
    assert out["verdict"] == "wide search, narrow universe"
    assert "pre-specified" in out["warning"] and "market-neutral" in out["warning"]
    assert out["trials_per_independent_bet"] > 25
    assert out["sanity_ceiling_sharpe"] == 1.0, "the futures ceiling, pre-committed"


def test_a_proportionate_search_is_not_warned_about():
    out = breadth.assess(_correlated(200, 0.05), n_trials_planned=200, market="equity")
    assert "warning" not in out


def test_an_implausible_futures_sharpe_demands_an_explanation():
    flag = breadth.implausible(2.5, "futures")
    assert flag and "back-adjusted" in flag["message"] and "roll rule" in flag["message"]
    assert breadth.implausible(0.8, "futures") is None
    assert breadth.implausible(1.2, "equity") is None, "the ceiling is market-specific"
