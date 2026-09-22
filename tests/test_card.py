import numpy as np
import pandas as pd

from alphalab import card
from alphalab.config import Config
from alphalab.regime import label_regimes


def _series(mu, seed):
    idx = pd.bdate_range("2021-01-01", periods=900)
    return pd.Series(np.random.default_rng(seed).normal(mu, 0.01, len(idx)), index=idx)


def test_burned_holdout_caps_tier():
    cfg = Config()
    cfg.splits.holdout_burned = True
    d, b = _series(0.002, 1), _series(0.0, 2)
    reg = label_regimes((1 + b).cumprod())
    c = card.build(cfg, "x", d, b, 3, 1e-4, {}, reg, lambda m: 0.1 - 0.02 * m)
    assert c["tier"] == "research-aid"
    cfg.splits.holdout_burned = False
    c2 = card.build(cfg, "x", d, b, 3, 1e-4, {}, reg, lambda m: 0.1 - 0.02 * m)
    assert c2["tier"] == "historical-backtest"
    assert c2["stats"]["break_even_one_way_bp"] is not None
