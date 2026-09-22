import numpy as np
import pandas as pd
import pytest

from alphalab import evalexpr
from alphalab.leakage import future_noise_test, numerical_checks


def test_clean_expressions_pass():
    for e in ["Ref($close,5)/$close-1", "Mean($close,20)/$close-1",
              "Corr($close,Log($volume+1),20)", "Std($close/Ref($close,1)-1,20)"]:
        ok, why = future_noise_test(e)
        assert ok, f"{e}: {why}"


def test_detects_a_leaky_operator_implementation(monkeypatch):
    """The static AST gate cannot see inside an operator. If someone implements
    a rolling mean as CENTERED (half the window in the future), only the
    future-noise test catches it - this is the regression guard for that."""
    monkeypatch.setitem(evalexpr.OPS, "Mean",
                        lambda x, w: x.rolling(int(w), center=True, min_periods=2).mean())
    ok, why = future_noise_test("Mean($close,20)/$close-1")
    assert not ok and "LOOK-AHEAD" in why


def test_static_gate_still_blocks_obvious_leaks():
    ok, why = future_noise_test("Ref($close,-5)/$close-1")
    assert not ok


def test_numerical_checks_reject_degenerate_factors():
    dates = pd.bdate_range("2021-01-01", periods=120)
    names = [f"S{i}" for i in range(50)]
    rng = np.random.default_rng(0)
    good = pd.DataFrame(rng.normal(size=(120, 50)), index=dates, columns=names)
    assert numerical_checks(good)[0]
    constant = pd.DataFrame(1.0, index=dates, columns=names)
    assert not numerical_checks(constant)[0]
    mostly_nan = good.mask(rng.random(good.shape) < 0.9)
    assert not numerical_checks(mostly_nan)[0]


@pytest.mark.parametrize("expr", ["Mean($close,10)", "Std($close,20)", "Ref($close,3)",
                                  "Delta($close,5)", "Corr($close,$volume,20)"])
def test_evaluator_matches_pandas_reference(expr):
    panel = evalexpr.synthetic_panel(seed=3)
    out = evalexpr.evaluate(expr, panel)
    c, v = panel["close"], panel["volume"]
    ref = {"Mean($close,10)": c.rolling(10, min_periods=5).mean(),
           "Std($close,20)": c.rolling(20, min_periods=10).std(),
           "Ref($close,3)": c.shift(3),
           "Delta($close,5)": c - c.shift(5),
           "Corr($close,$volume,20)": c.rolling(20, min_periods=10).corr(v)}[expr]
    pd.testing.assert_frame_equal(out, ref.replace([np.inf, -np.inf], np.nan), atol=1e-9)
