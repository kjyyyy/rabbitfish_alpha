"""Effective-trials accounting and the leakage safety of the shrinkage combiner."""
import numpy as np
import pandas as pd

from alphalab.neff import avg_corr_neff, eigenvalue_neff, report


def _frame(cols):
    return pd.DataFrame({f"c{i}": c for i, c in enumerate(cols)})


def test_identical_candidates_count_as_one_trial():
    rng = np.random.default_rng(0)
    base = pd.Series(rng.normal(size=300))
    M = _frame([base] * 20)
    assert eigenvalue_neff(M) < 1.5
    assert avg_corr_neff(M)[0] < 1.5


def test_independent_candidates_count_in_full():
    rng = np.random.default_rng(1)
    M = pd.DataFrame(rng.normal(size=(600, 20)))
    assert eigenvalue_neff(M) > 15
    assert avg_corr_neff(M)[0] > 12


def test_report_never_lowers_the_gating_count():
    rng = np.random.default_rng(2)
    base = pd.Series(rng.normal(size=400))
    M = _frame([base + rng.normal(0, 0.3, 400) for _ in range(30)])
    rep = report(M, n_raw=30)
    assert rep["n_raw"] == 30                      # gating still uses the raw count
    assert rep["n_eff_eigenvalue"] < 30            # but the correlation is reported
    assert 0 <= rep["mean_abs_corr"] <= 1


def test_shrinkage_weights_use_only_realised_ic():
    from alphalab.pipeline.model import shrinkage_weights
    dates = pd.bdate_range("2021-01-01", periods=400)
    ic = pd.DataFrame({"a": 0.0, "b": 0.0}, index=dates)
    ic.iloc[300:, 0] = 0.5                          # factor a turns good at day 300
    w = shrinkage_weights(ic, horizon=5, lookback=100)
    early = w.loc[w.index < dates[306]]
    assert early.empty or float(early["a"].abs().max()) < 1e-9
