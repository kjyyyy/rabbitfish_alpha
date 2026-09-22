"""Synthetic-panel engine checks (no Qlib needed)."""
import numpy as np
import pandas as pd

from alphalab import backtest
from alphalab.config import Config


def _panel(n_days=400, n_names=120, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2020-01-01", periods=n_days)
    names = [f"US{i:04d}" for i in range(n_names)]
    r = rng.normal(0.0003, 0.02, (n_days, n_names))
    close = pd.DataFrame(100 * np.cumprod(1 + r, axis=0), index=dates, columns=names)
    vol = pd.DataFrame(1e6, index=dates, columns=names)
    return close, vol, close.mean(axis=1)


def _cfg():
    c = Config()
    c.market.price_limits = False
    return c


def _label(close, h=5):
    fwd = close.shift(-(h + 1)) / close.shift(-1) - 1
    return fwd.stack().rename("y").swaplevel().swaplevel().sort_index()


def test_oracle_random_stale():
    cfg = _cfg()
    close, vol, bench = _panel()
    y = _label(close).dropna()
    y.index = y.index.set_names(["datetime", "instrument"])
    rng = np.random.default_rng(0)
    res = {}
    for k, sc in {"oracle": y,
                  "random": pd.Series(rng.normal(size=len(y)), index=y.index),
                  "stale": y.groupby(level=1).shift(6).dropna()}.items():
        d, b, _ = backtest.run(cfg, sc, close, vol, bench)
        res[k] = backtest.metrics(d, b)["info_ratio"]
    assert res["oracle"] > 3
    assert res["random"] < 0.5 and res["stale"] < 0.8


def test_uk_stamp_duty_costs_more():
    close, vol, bench = _panel()
    y = _label(close).dropna()
    rng = np.random.default_rng(1)
    sc = pd.Series(rng.normal(size=len(y)), index=y.index)
    a, b = _cfg(), _cfg()
    b.market.costs.stamp_buy = 0.005
    ra = backtest.metrics(*backtest.run(a, sc, close, vol, bench)[:2])["cagr"]
    rb = backtest.metrics(*backtest.run(b, sc, close, vol, bench)[:2])["cagr"]
    assert rb < ra
