"""Portfolio-construction checks on synthetic data (no Qlib needed)."""
import numpy as np
import pandas as pd

from alphalab import risk
from alphalab.config import Config
from alphalab.portfolio import BookSpec, impact_bp, run_book, target_weights


def _panel(n_days=320, n_names=150, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2021-01-01", periods=n_days)
    names = [f"X{i:04d}" for i in range(n_names)]
    r = rng.normal(0.0002, 0.02, (n_days, n_names))
    close = pd.DataFrame(100 * np.cumprod(1 + r, axis=0), index=dates, columns=names)
    vol = pd.DataFrame(1e5, index=dates, columns=names)
    adv = pd.DataFrame(1e7, index=dates, columns=names)      # £10m ADV per name
    return close, vol, adv, close.mean(axis=1)


def _cfg():
    c = Config()
    c.market.price_limits = False
    return c


def _scores(close, seed=1):
    rng = np.random.default_rng(seed)
    s = pd.DataFrame(rng.normal(size=close.shape), index=close.index, columns=close.columns)
    return s.stack().rename("score")


def test_market_neutral_is_dollar_neutral_and_capped():
    a = pd.Series(np.linspace(-1, 1, 200), index=[f"X{i:04d}" for i in range(200)])
    w = target_weights(a, BookSpec(mode="market_neutral", max_weight=0.05))
    assert abs(w.sum()) < 1e-9                      # dollar neutral
    assert abs(w.abs().sum() - 1.0) < 1e-6          # gross = 1
    assert w.abs().max() <= 0.05 + 1e-9             # position cap respected


def test_impact_follows_square_root_law():
    adv = pd.Series([1e6])
    one_pct = impact_bp(pd.Series([1e4]), adv, 10.0).iloc[0]
    four_pct = impact_bp(pd.Series([4e4]), adv, 10.0).iloc[0]
    assert abs(one_pct - 10.0) < 1e-6
    assert abs(four_pct - 20.0) < 1e-6              # 4x size -> 2x cost


def test_bands_cut_turnover():
    cfg, (close, vol, adv, bench) = _cfg(), _panel()
    sc = _scores(close)
    _, _, d0 = run_book(cfg, sc, close, vol, bench, BookSpec(band=0.0), adv=adv)
    _, _, d1 = run_book(cfg, sc, close, vol, bench, BookSpec(band=0.25), adv=adv)
    assert d1["turnover_per_rebalance"] < d0["turnover_per_rebalance"]


def test_impact_grows_with_capital_until_caps_bind():
    """Uncapped, impact must grow with book size. With participation caps on, a
    huge book instead stops being able to trade - which is what makes the far
    end of a capacity curve meaningless rather than attractive."""
    cfg, (close, vol, adv, bench) = _cfg(), _panel()
    sc = _scores(close)
    loose = dict(max_adv_participation=1.0)
    small = run_book(cfg, sc, close, vol, bench, BookSpec(capital=1e5, **loose), adv=adv)[2]
    big = run_book(cfg, sc, close, vol, bench, BookSpec(capital=1e9, **loose), adv=adv)[2]
    assert big["impact_cost_ann"] > small["impact_cost_ann"] * 10
    capped = run_book(cfg, sc, close, vol, bench, BookSpec(capital=1e9), adv=adv)[2]
    assert capped["share_trades_capped"] > 0.5


def test_neutralisation_removes_style_exposure():
    close, vol, adv, bench = _panel()
    expos = risk.exposures(close, vol, bench)
    v = expos["vol"].stack().dropna()
    alpha = (-v).rename("alpha")                      # a pure low-volatility bet
    neutral = risk.neutralise(alpha, expos)
    corr_before = alpha.corr(v)
    corr_after = neutral.corr(v.reindex(neutral.index))
    assert abs(corr_after) < abs(corr_before) / 2
