"""Point-in-time fundamentals: the as-of rule, and what breaks without it."""
import numpy as np
import pandas as pd

from alphalab.factors.fundamental import HYPOTHESES, composite, compute
from alphalab.sources.fundamentals import PITFundamentals, winsorise
from alphalab.sources.qa import problems, report


def _rows():
    """Two firms, quarterly filings with a realistic ~45-day reporting lag."""
    rows = []
    for cik, base in ((1, 100.0), (2, 50.0)):
        for i, period in enumerate(pd.date_range("2020-03-31", periods=8, freq="QE")):
            filed = period + pd.Timedelta(days=45)
            for tag, mult in (("NetIncomeLoss", 1.0), ("StockholdersEquity", 8.0),
                              ("Assets", 20.0), ("Liabilities", 12.0)):
                rows.append(dict(cik=cik, tag=tag, period=period, filed=filed,
                                 value=base * mult * (1 + 0.05 * i)))
    return pd.DataFrame(rows)


def _prices(dates):
    return pd.DataFrame({1: np.linspace(10, 20, len(dates)), 2: np.linspace(20, 10, len(dates))},
                        index=dates)


def test_as_of_never_returns_unfiled_values():
    fun = PITFundamentals(_rows())
    first_period_end = pd.Timestamp("2020-03-31")
    assert fun.as_of(first_period_end).empty            # period over, not yet filed
    assert not fun.as_of(first_period_end + pd.Timedelta(days=46)).empty


def test_reporting_lag_is_positive_and_realistic():
    fun = PITFundamentals(_rows())
    assert fun.reporting_lag.min() >= 0
    rep = report(fun)
    assert rep["reporting_lag_days"]["median"] == 45
    assert not any("impossible" in m for m in problems(rep))


def test_period_join_leaks_information_the_filing_join_does_not():
    """The whole point of the module: joining on period grants foresight."""
    fun = PITFundamentals(_rows())
    dates = pd.bdate_range("2020-01-01", "2022-01-01")
    price = _prices(dates)
    honest = fun.panel("NetIncomeLoss", dates, ciks=price.columns)
    leaky = fun.panel("NetIncomeLoss", dates, ciks=price.columns, leaky_period_join=True)
    # on the day a period ends, the leaky panel already knows the number
    day = pd.Timestamp("2020-06-30")
    assert np.isnan(honest.loc[day, 1]) or honest.loc[day, 1] != leaky.loc[day, 1]
    assert not np.isnan(leaky.loc[day, 1])
    # and it knows it ~45 days early, every quarter
    lead = (leaky.notna() & honest.isna()).sum().sum()
    assert lead > 0


def test_every_hypothesis_computes_and_is_pre_registered():
    fun = PITFundamentals(_rows())
    dates = pd.bdate_range("2020-01-01", "2022-01-01")
    price = _prices(dates)
    for h in HYPOTHESES:
        assert h["rationale"] and h["sign"] in (1, -1)
    for name in ("earnings_yield", "book_to_market", "return_on_equity", "accruals",
                 "asset_growth", "leverage", "cash_to_assets"):
        out = compute(name, fun, dates, price)
        assert out.shape[0] == len(dates)
    comp = composite(fun, dates, price)
    assert comp.shape[0] == len(dates)


def test_winsorise_tames_denominator_blowups():
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [1e9, 2.0, 3.0], "c": [1.0, 2.0, 3.0]})
    w = winsorise(df)
    assert w.to_numpy().max() < 1e9
