"""Portfolio construction and a weight-based backtest with market impact.

This is the layer between "signal" and "positions" that hobby projects skip and
professional books spend most of their effort on:

  * long-only top-k  OR  dollar-neutral long/short
  * bounded, rank-based weights (no mean-variance optimiser - see the factor
    alignment problem in risk.py)
  * per-name caps, and a cap on participation in daily volume
  * no-trade bands (Novy-Marx & Velikov: buy/hold bands cut turnover ~41% and
    costs ~42%, the best cost/effort ratio in the cost literature)
  * volatility targeting on the book
  * costs = commission + spread/slippage + stamp duty + MARKET IMPACT, where
    impact follows the square-root law, calibrated to AQR's live-trade estimate
    of ~10bp at 1% of daily volume (Frazzini, Israel & Moskowitz)
  * short financing and borrow costs for the long/short version

Capacity falls out of the same code: run the book at several capital levels
and watch impact eat the edge.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import Config


@dataclass
class BookSpec:
    mode: str = "long_only"          # "long_only" | "market_neutral"
    capital: float = 1e6             # book size in local currency
    gross: float = 1.0               # gross exposure / capital (1.0 = unlevered)
    topk: int = 30                   # long_only: number of names
    quantile: float = 0.2            # market_neutral: fraction long and short
    max_weight: float = 0.05         # cap per name (fraction of capital)
    max_adv_participation: float = 0.05   # cap a trade at 5% of that name's ADV
    band: float = 0.25               # no-trade band as a fraction of target weight
    neutralise: bool = False         # residualise alpha against style factors
    vol_target: float | None = None  # annualised vol target for the book, e.g. 0.10
    impact_bp_at_1pct: float = 10.0  # square-root impact coefficient
    short_financing_ann: float = 0.03  # UK CFD reality: ~3% of gross per year
    borrow_ann: float = 0.005
    extra: dict = field(default_factory=dict)


def target_weights(alpha: pd.Series, spec: BookSpec, spec_vol: pd.Series | None = None,
                   held: set | None = None) -> pd.Series:
    """Cross-sectional weights for one date from an alpha score.

    `held` enables rank banding: a name already held is kept while it stays
    inside a wider rank band, instead of being sold the moment it leaves the
    top-k. This is where most of the turnover saving comes from."""
    a = alpha.dropna()
    held = held or set()
    if len(a) < 20:
        return pd.Series(dtype=float)
    if spec.mode == "long_only":
        ranked = a.sort_values(ascending=False)
        chosen = list(ranked.index[:spec.topk])
        if spec.band > 0:
            keep_n = int(spec.topk * (1 + 2 * spec.band))
            keepers = [x for x in ranked.index[:keep_n] if x in held and x not in chosen]
            chosen = (chosen + keepers)[:max(spec.topk, len(chosen))]
            if keepers:                     # hold the band names instead of the weakest new ones
                chosen = list(dict.fromkeys(list(ranked.index[:spec.topk - len(keepers)]) + keepers))
        w = pd.Series(1.0 / len(chosen), index=chosen)
    else:
        r = a.rank(pct=True)
        q = spec.quantile
        band = spec.band * q
        longs = a[(r > 1 - q) | ((r > 1 - q - band) & pd.Series(a.index.isin(list(held)), index=a.index))]
        shorts = a[(r <= q) | ((r <= q + band) & pd.Series(a.index.isin(list(held)), index=a.index))]
        z = pd.concat([longs.rank() - longs.rank().mean(), shorts.rank() - shorts.rank().mean()])
        w = pd.Series(0.0, index=a.index)
        if len(longs) and len(shorts):
            wl = (z.reindex(longs.index) - z.reindex(longs.index).min() + 1)
            ws = (z.reindex(shorts.index).max() - z.reindex(shorts.index) + 1)
            w.loc[longs.index] = 0.5 * wl / wl.sum()
            w.loc[shorts.index] = -0.5 * ws / ws.sum()
        w = w[w != 0]
    if spec_vol is not None:                       # tilt away from very volatile names
        iv = spec_vol.reindex(w.index).clip(lower=spec_vol.median() * 0.5)
        w = w / iv
        w = w / w.abs().sum() * (1.0 if spec.mode == "long_only" else 1.0)
    w = w.clip(-spec.max_weight, spec.max_weight)
    if spec.mode == "long_only":
        w = w / w.sum()
    else:
        pos, neg = w[w > 0], w[w < 0]
        if len(pos) and len(neg):                  # dollar neutral
            w[w > 0] = pos / pos.sum() * 0.5
            w[w < 0] = -neg / neg.sum() * 0.5
    return w * spec.gross


def apply_bands(target: pd.Series, current: pd.Series, band: float) -> pd.Series:
    """Keep the current weight when it is within `band` of the target
    (Novy-Marx & Velikov buy/hold banding)."""
    if current.empty or band <= 0:
        return target
    out = target.copy()
    common = target.index.intersection(current.index)
    tol = band * target.abs().reindex(common).clip(lower=1e-6)
    keep = (target.reindex(common) - current.reindex(common)).abs() < tol
    out.loc[common[keep]] = current.reindex(common)[keep]
    return out


def impact_bp(trade_value: pd.Series, adv_value: pd.Series, coef: float) -> pd.Series:
    """Square-root law: bp = coef * sqrt(participation / 1%)."""
    part = (trade_value.abs() / adv_value.replace(0, np.nan)).clip(upper=1.0)
    return coef * np.sqrt((part * 100).clip(lower=0))


def run_book(cfg: Config, scores: pd.Series, close: pd.DataFrame, volume: pd.DataFrame,
             bench: pd.Series, spec: BookSpec, spec_vol: pd.DataFrame | None = None,
             adv: pd.DataFrame | None = None):
    """Weight-based backtest. Returns (daily net returns, benchmark, diagnostics)."""
    h = cfg.trading.horizon
    c = cfg.market.costs
    ret = close.pct_change(fill_method=None)
    if adv is None:                      # fallback: price x volume (units must match!)
        adv = (close * volume).rolling(20).mean()
    S = scores.unstack()
    dates = close.index
    sig_dates = S.index[::h]
    daily = pd.Series(0.0, index=dates)
    cur = pd.Series(dtype=float)
    turn, gross_hist, impact_hist, capped = [], [], [], []
    limits = 0.095 if cfg.market.price_limits else None

    for k, sd in enumerate(sig_dates):
        pos = dates.searchsorted(sd)
        if pos + 1 >= len(dates):
            break
        td = dates[pos + 1]
        nxt = sig_dates[k + 1] if k + 1 < len(sig_dates) else None
        end = (dates[min(dates.searchsorted(nxt) + 1, len(dates) - 1)] if nxt is not None
               else dates[min(pos + 1 + h, len(dates) - 1)])
        a = S.loc[sd].dropna()
        sv = spec_vol.loc[sd].reindex(a.index) if spec_vol is not None and sd in spec_vol.index else None
        tgt = target_weights(a, spec, sv, held=set(cur.index))
        if tgt.empty:
            continue
        if spec.vol_target:                       # scale the book to a vol target
            hist = daily.loc[:td].tail(60)
            realised = hist.std() * np.sqrt(244) if hist.std() > 0 else None
            if realised and realised > 0:
                tgt = tgt * float(np.clip(spec.vol_target / realised, 0.25, 2.0))
        # tradability
        r_td, v_td = ret.loc[td], volume.loc[td]
        tradable = ~(v_td.isna() | (v_td <= 0))
        if limits is not None:
            tradable &= (r_td.abs() < limits - 0.005) | r_td.isna()
        tgt = tgt[tgt.index.map(lambda x: bool(tradable.get(x, False)))]
        tgt = apply_bands(tgt, cur, spec.band)
        # participation cap: limit each trade to a share of that name's ADV
        names = tgt.index.union(cur.index)
        t_full = tgt.reindex(names).fillna(0.0)
        c_full = cur.reindex(names).fillna(0.0)
        dv = (t_full - c_full) * spec.capital
        adv_td = adv.loc[td].reindex(names) if td in adv.index else pd.Series(np.nan, index=names)
        cap = adv_td.fillna(0.0) * spec.max_adv_participation
        over = dv.abs() > cap
        capped.append(float(over.mean()))
        dv_capped = dv.where(~over, np.sign(dv) * cap)
        new = c_full + dv_capped / spec.capital
        # costs on the traded value
        one_way = c.commission + c.slippage
        stamp = np.where(dv_capped > 0, c.stamp_buy, c.stamp_sell)
        imp = impact_bp(dv_capped, adv_td, spec.impact_bp_at_1pct) / 1e4
        cost = float((dv_capped.abs() / spec.capital * (one_way + stamp + imp.fillna(0.0))).sum())
        daily.loc[td] -= cost
        impact_hist.append(float((dv_capped.abs() / spec.capital * imp.fillna(0.0)).sum()))
        turn.append(float(dv_capped.abs().sum() / spec.capital))
        cur = new[new.abs() > 1e-6]
        gross_hist.append(float(cur.abs().sum()))
        # holding-period returns + financing on the short side
        seg = ret.loc[(ret.index > td) & (ret.index <= end), cur.index].fillna(0.0)
        daily.loc[seg.index] += seg.mul(cur, axis=1).sum(axis=1).values
        short_notional = float(-cur[cur < 0].sum())
        if short_notional:
            fin = short_notional * (spec.short_financing_ann + spec.borrow_ann) / 244
            daily.loc[seg.index] -= fin
    first = dates[dates.searchsorted(sig_dates[0]) + 1]
    daily = daily.loc[first:end]
    b = bench.pct_change(fill_method=None).reindex(daily.index).fillna(0.0)
    diag = dict(turnover_per_rebalance=float(np.mean(turn)) if turn else 0.0,
                avg_gross=float(np.mean(gross_hist)) if gross_hist else 0.0,
                impact_cost_ann=float(np.mean(impact_hist) * (244 / cfg.trading.horizon)) if impact_hist else 0.0,
                share_trades_capped=float(np.mean(capped)) if capped else 0.0)
    return daily, b, diag


def capacity_curve(cfg: Config, scores, close, volume, bench, spec: BookSpec,
                   capitals, spec_vol=None, adv=None) -> pd.DataFrame:
    """Re-run the same book at several capital levels: the point where impact
    eats the edge is the strategy's capacity."""
    from . import backtest
    rows = []
    for cap in capitals:
        s = BookSpec(**{**spec.__dict__, "capital": cap})
        d, b, diag = run_book(cfg, scores, close, volume, bench, s, spec_vol, adv)
        m = backtest.metrics(d, b)
        rows.append(dict(capital=cap, excess_ann=m["excess_ann"], info_ratio=m["info_ratio"],
                         cagr=m["cagr"], **diag))
    return pd.DataFrame(rows)
