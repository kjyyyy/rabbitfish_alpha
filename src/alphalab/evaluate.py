"""Vectorised factor evaluation (all candidates at once)."""
import numpy as np
import pandas as pd


def _per_col(F: pd.DataFrame, y: pd.Series):
    yv = y.reindex(F.index)
    out_ic, out_ls, out_pic = {}, {}, {}
    for c in F.columns:
        f = F[c]
        m = f.notna() & yv.notna() & np.isfinite(f)
        d = pd.DataFrame({"f": f[m], "y": yv[m]})
        g = d.groupby(level=0)
        rf = g["f"].rank(pct=True)
        ry = g["y"].rank(pct=True)
        n = g["f"].transform("size")
        d = d.assign(rf=rf, ry=ry, n=n)
        d = d[d.n > 30]
        gg = d.groupby(level=0)
        mf, my = gg.rf.transform("mean"), gg.ry.transform("mean")
        cov = ((d.rf - mf) * (d.ry - my)).groupby(level=0).mean()
        sf = ((d.rf - mf) ** 2).groupby(level=0).mean() ** 0.5
        sy = ((d.ry - my) ** 2).groupby(level=0).mean() ** 0.5
        out_ic[c] = cov / (sf * sy)
        # Pearson IC on winsorised raw values (Hubble reports rank IC and Pearson IC).
        # Winsorise globally, not per date: cheaper, and it only trims fat tails.
        lo, hi = d.f.quantile(0.01), d.f.quantile(0.99)
        d = d.assign(w=d.f.clip(lo, hi).to_numpy())
        gw = d.groupby(level=0)
        mw, my2 = gw.w.transform("mean"), gw.y.transform("mean")
        cov_p = ((d.w - mw) * (d.y - my2)).groupby(level=0).mean()
        sw = ((d.w - mw) ** 2).groupby(level=0).mean() ** 0.5
        sy2 = ((d.y - my2) ** 2).groupby(level=0).mean() ** 0.5
        out_pic[c] = cov_p / (sw * sy2)
        top = d.y.where(d.rf > 0.8).groupby(level=0).mean()
        bot = d.y.where(d.rf <= 0.2).groupby(level=0).mean()
        out_ls[c] = top - bot
    return pd.DataFrame(out_ic), pd.DataFrame(out_ls), pd.DataFrame(out_pic)


def evaluate(F: pd.DataFrame, y: pd.Series):
    """Returns (daily rank-IC frame, daily quintile long-short frame, daily Pearson-IC frame)."""
    return _per_col(F, y)
