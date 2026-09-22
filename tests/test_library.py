import numpy as np
import pandas as pd

from alphalab.library import Library, dynamic_weights


def test_dynamic_weights_use_only_past_ic():
    dates = pd.bdate_range("2021-01-01", periods=300)
    ic = pd.DataFrame({"a": 0.0, "b": 0.0}, index=dates)
    ic.iloc[200:, 0] = 1.0                       # factor a suddenly perfect from day 200
    w = dynamic_weights(ic, pd.Series({"a": 1, "b": 1}), horizon=5, lookback=20, shrink=0.0)
    # weight on 'a' must not react before the ICs could have been realised (lag 6)
    assert w["a"].iloc[200:206].abs().max() == 0 or np.isnan(w["a"].iloc[200:206]).all() or \
        (w["a"].iloc[200:206] == w["a"].iloc[199]).all()
    assert w["a"].iloc[240] > w["b"].iloc[240]


def test_library_lifecycle(tmp_path):
    lib = Library(tmp_path / "lib.json")
    lib.upsert("f1", "Mean($close,5)", 1, "hypothesis", "probation", {"ic_t": 3.1})
    lib.save()
    dates = pd.bdate_range("2025-01-01", periods=60)
    bad = pd.DataFrame({"f1": np.random.default_rng(0).normal(-0.01, 0.05, 60)}, index=dates)
    lib.revalidate(bad)
    lib.revalidate(bad)
    assert lib.items["f1"]["status"] == "retired"


def test_the_same_window_cannot_be_counted_as_two_rechecks():
    """Two consecutive checks promote or retire a factor, so re-running the
    recheck on identical sessions would move the whole library on no new data."""
    from alphalab.pipeline.revalidate import already_checked

    w = "2025-09-01..2026-09-10"
    members = [{"name": "a", "history": [{"recheck_t": 2.5, "window": w}]},
               {"name": "b", "history": [{"recheck_t": 0.1, "window": w}]}]
    assert already_checked(members, w) is True
    assert already_checked(members, "2025-12-01..2026-12-10") is False
    assert already_checked([], w) is False


def test_promotion_needs_two_consecutive_strong_rechecks(tmp_path):
    lib = Library(tmp_path / "lib.json")
    lib.upsert("f", "$close", 1, "hypothesis", "probation", {"ic_t": 4.0})
    strong = pd.DataFrame({"f": np.full(120, 0.05)})
    lib.revalidate(strong, promote_t=2.0, window="w1")
    assert lib.items["f"]["status"] == "probation", "one strong check is not enough"
    lib.revalidate(strong, promote_t=2.0, window="w2")
    assert lib.items["f"]["status"] == "active"
