"""Transparent weekly top-k long-only backtest with market-specific frictions.
Signal at close t -> trade at close t+1 -> hold one horizon.
CN: cannot buy limit-up or suspended names; cannot sell limit-down or suspended.
UK: stamp duty on purchases. Costs are charged on names traded (equal weight)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import Config


def _limit(code: str) -> float:
    c = code.upper()
    return 0.195 if c.startswith(("SZ300", "SH688")) else 0.095


def _stamp_sell(cfg: Config, day) -> float:
    c = cfg.market.costs
    if c.stamp_change_date and c.stamp_sell_before is not None and day < pd.Timestamp(c.stamp_change_date):
        return c.stamp_sell_before
    return c.stamp_sell


def run(cfg: Config, scores: pd.Series, close: pd.DataFrame, volume: pd.DataFrame,
        bench: pd.Series, cost_mult: float = 1.0):
    t = cfg.trading
    c = cfg.market.costs
    S = scores.unstack()
    dates = close.index
    ret = close.pct_change(fill_method=None)
    sig_dates = S.index[::t.horizon]
    limits = pd.Series({k: _limit(k) for k in close.columns}) if cfg.market.price_limits else None

    holdings, turnover, last_end = [], [], None
    daily = pd.Series(0.0, index=dates)
    for k, sd in enumerate(sig_dates):
        pos = dates.searchsorted(sd)
        if pos + 1 >= len(dates):
            break
        td = dates[pos + 1]
        nxt = sig_dates[k + 1] if k + 1 < len(sig_dates) else None
        end = (dates[min(dates.searchsorted(nxt) + 1, len(dates) - 1)] if nxt is not None
               else dates[min(pos + 1 + t.horizon, len(dates) - 1)])
        s = S.loc[sd].dropna().sort_values(ascending=False)
        r_td, v_td = ret.loc[td], volume.loc[td]
        susp = v_td.isna() | (v_td <= 0)
        if limits is not None:
            up, dn = r_td >= (limits - 0.005), r_td <= -(limits - 0.005)
        else:
            up = dn = pd.Series(False, index=r_td.index)
        rank = pd.Series(np.arange(len(s)), index=s.index)
        keep = [h for h in holdings if (h in rank.index and rank[h] < t.keep_rank)
                or susp.get(h, True) or dn.get(h, False)]
        buys = [x for x in s.index if x not in keep and not susp.get(x, True)
                and not up.get(x, False)][: max(t.topk - len(keep), 0)]
        new = keep + buys
        sold = [h for h in holdings if h not in new]
        n = max(len(new), 1)
        buy_cost = c.commission + c.slippage + c.stamp_buy
        sell_cost = c.commission + c.slippage + _stamp_sell(cfg, td)
        cost = (len(buys) / n) * buy_cost + ((len(sold) / len(holdings)) * sell_cost if holdings else 0.0)
        daily.loc[td] -= cost * cost_mult
        turnover.append(len(buys) / n)
        holdings = new
        seg = ret.loc[(ret.index > td) & (ret.index <= end), holdings].fillna(0.0).mean(axis=1)
        daily.loc[seg.index] += seg.values
        last_end = end
    first = dates[dates.searchsorted(sig_dates[0]) + 1]
    daily = daily.loc[first:last_end]
    b = bench.pct_change(fill_method=None).reindex(daily.index).fillna(0.0)
    return daily, b, float(np.mean(turnover)) if turnover else 0.0


def metrics(daily: pd.Series, bench: pd.Series, periods: int = 244) -> dict:
    eq = (1 + daily).cumprod()
    ex = daily - bench
    yrs = len(daily) / periods
    sd = daily.std()
    return dict(
        cagr=float(eq.iloc[-1] ** (1 / yrs) - 1), vol=float(sd * np.sqrt(periods)),
        sharpe=float(daily.mean() / sd * np.sqrt(periods)) if sd > 0 else float("nan"),
        max_dd=float((eq / eq.cummax() - 1).min()),
        bench_cagr=float((1 + bench).prod() ** (1 / yrs) - 1),
        excess_ann=float(ex.mean() * periods),
        info_ratio=float(ex.mean() / ex.std() * np.sqrt(periods)) if ex.std() > 0 else float("nan"),
        n_days=int(len(daily)))
