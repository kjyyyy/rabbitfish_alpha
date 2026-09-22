"""Engine sanity checks on real data: an oracle must win massively (timing is
aligned), random scores must lose roughly the cost drag, and a stale oracle
(information 6 days late) must not look like foresight. Run after ANY change
to the backtest or data layer."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import backtest, data
from .config import Config


def run(cfg: Config, log=print) -> dict:
    y0, y1 = cfg.splits.valid_years[0], cfg.splits.valid_years[-1]
    y = data.label(cfg, f"{y0}-01-01", f"{y1}-12-31")
    close, vol = data.price_panel(cfg)
    bench = data.benchmark_close(cfg)
    rng = np.random.default_rng(0)
    tests = {"oracle": y, "random": pd.Series(rng.normal(size=len(y)), index=y.index),
             "stale_oracle": y.groupby(level=1).shift(cfg.trading.horizon + 1)}
    out = {}
    for k, sc in tests.items():
        d, b, to = backtest.run(cfg, sc.dropna(), close, vol, bench)
        m = backtest.metrics(d, b)
        out[k] = dict(excess_ann=m["excess_ann"], ir=m["info_ratio"], turnover=to)
        log(f"{k:14s} excess/yr={m['excess_ann']:+.1%}  IR={m['info_ratio']:+.2f}  turnover={to:.0%}")
    ok = out["oracle"]["ir"] > 3 and out["random"]["ir"] < 0.3 and out["stale_oracle"]["ir"] < 0.5
    log("SANITY " + ("PASSED" if ok else "FAILED - do not trust any backtest until fixed"))
    out["passed"] = ok
    return out
