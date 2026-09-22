"""A poor man's risk model, and alpha neutralisation.

Professional books run a vendor factor model (Barra/Axioma) between the signal
and the portfolio. Without one, this builds the same idea from price data only:
a market factor plus style factors (size proxy, volatility, momentum,
liquidity), estimated cross-sectionally, with optional statistical (PCA)
factors on the residuals.

Neutralisation = cross-sectional regression of the alpha on factor exposures,
keeping the residual, so the book does not unintentionally bet on "small,
volatile, high-momentum" as a style. Note the factor alignment problem
(MSCI): a residual alpha looks risk-free to the risk model, so an optimiser
will over-weight it. This lab therefore uses bounded, rank-based weights
rather than a mean-variance optimiser.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def exposures(close: pd.DataFrame, volume: pd.DataFrame, bench: pd.Series,
              win_vol: int = 60, win_mom: int = 120, win_beta: int = 120) -> dict[str, pd.DataFrame]:
    """Style exposures, each a date x instrument frame (raw, unstandardised)."""
    ret = close.pct_change(fill_method=None)
    br = bench.pct_change(fill_method=None).reindex(ret.index)
    cov = ret.rolling(win_beta).cov(br)
    beta = cov.div(br.rolling(win_beta).var(), axis=0)
    dollar_vol = (close * volume).rolling(20).mean()
    return {
        "beta": beta,
        "size": np.log(dollar_vol.replace(0, np.nan)),          # ADV proxy for size
        "vol": ret.rolling(win_vol).std(),
        "mom": close.shift(20) / close.shift(win_mom) - 1,
        "liq": volume.rolling(20).mean() / volume.rolling(120).mean(),
    }


def _z(x: pd.Series) -> pd.Series:
    x = x.astype(float)
    m = x.mean()
    s = x.std()
    return ((x - m) / s).clip(-3, 3).fillna(0.0) if s and np.isfinite(s) else pd.Series(0.0, index=x.index)


def neutralise_cross_section(alpha: pd.Series, expo: pd.DataFrame) -> pd.Series:
    """Residual of alpha after regressing on [1, exposures] for one date."""
    common = alpha.dropna().index.intersection(expo.dropna(how="all").index)
    if len(common) < 30:
        return alpha
    a = alpha.reindex(common).astype(float)
    X = expo.reindex(common).apply(_z).fillna(0.0)
    X.insert(0, "const", 1.0)
    coef, *_ = np.linalg.lstsq(X.values, a.values, rcond=None)
    resid = a.values - X.values @ coef
    return pd.Series(resid, index=common).reindex(alpha.index)


def neutralise(scores: pd.Series, expos: dict[str, pd.DataFrame],
               factors: tuple[str, ...] = ("beta", "size", "vol", "mom")) -> pd.Series:
    """Neutralise a (date, instrument) score series date by date."""
    out = []
    for date, s in scores.groupby(level=0):
        s = s.droplevel(0)
        expo = pd.DataFrame({f: expos[f].loc[date].reindex(s.index) for f in factors
                             if date in expos[f].index})
        r = neutralise_cross_section(s, expo) if not expo.empty else s
        out.append(pd.concat({date: r}, names=["datetime"]))
    res = pd.concat(out)
    res.index = res.index.set_names(scores.index.names)
    return res


def specific_vol(close: pd.DataFrame, bench: pd.Series, win: int = 60) -> pd.DataFrame:
    """Idiosyncratic volatility: rolling std of returns minus beta*market."""
    ret = close.pct_change(fill_method=None)
    br = bench.pct_change(fill_method=None).reindex(ret.index)
    beta = ret.rolling(win).cov(br).div(br.rolling(win).var(), axis=0)
    resid = ret.sub(beta.mul(br, axis=0))
    return resid.rolling(win).std()


def crowding_r2(close: pd.DataFrame, volume: pd.DataFrame, expos: dict[str, pd.DataFrame],
                win: int = 60) -> pd.Series:
    """Khandani & Lo (2007) crowding proxy: R^2 of a cross-sectional regression
    of stock turnover on factor exposures. They flagged >10% as the alarm level
    before the August 2007 quant quake. Price/volume data only."""
    turn = (volume / volume.rolling(win).mean()).replace([np.inf, -np.inf], np.nan)
    out = {}
    for date in turn.index[win:]:
        y = turn.loc[date].dropna()
        X = pd.DataFrame({f: expos[f].loc[date].reindex(y.index) for f in
                          ("beta", "size", "vol", "mom") if date in expos[f].index}).apply(_z)
        if len(y) < 50 or X.empty:
            continue
        X.insert(0, "const", 1.0)
        coef, *_ = np.linalg.lstsq(X.values, y.values, rcond=None)
        pred = X.values @ coef
        ss_res = float(((y.values - pred) ** 2).sum())
        ss_tot = float(((y.values - y.values.mean()) ** 2).sum())
        out[date] = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan
    return pd.Series(out).rolling(20).mean()
