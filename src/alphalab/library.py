"""Factor library with a lifecycle (AlphaCrafter-style gates, re-implemented):
  probation -> active -> retired.
and a combiner that weights factors by their TRAILING information coefficient
(dynamic weighting in the spirit of AlphaForge; clean re-implementation)."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd


class Library:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.items: dict[str, dict] = json.loads(self.path.read_text()) if self.path.exists() else {}

    def save(self):
        self.path.write_text(json.dumps(self.items, indent=2, default=float))

    def upsert(self, name, expr, sign, source, status, metrics):
        now = dt.date.today().isoformat()
        it = self.items.get(name, {"added": now, "history": []})
        it.update(name=name, expr=expr, sign=int(sign), source=source, status=status)
        it["history"].append({"date": now, "status": status, **metrics})
        self.items[name] = it

    def members(self, statuses=("probation", "active")):
        return [v for v in self.items.values() if v["status"] in statuses]

    def revalidate(self, recent_ic: pd.DataFrame, min_t: float = 1.0,
                   promote_t: float | None = None, window: str = ""):
        """Retire factors whose recent (signed) IC t-stat falls below min_t on
        two consecutive checks, and - when `promote_t` is given - promote a
        factor out of probation after two consecutive checks at or above it.
        recent_ic: date x factor daily rank IC, measured on data the factor was
        not discovered on."""
        for name, it in self.items.items():
            if it["status"] == "retired" or name not in recent_ic:
                continue
            x = recent_ic[name].dropna() * it["sign"]
            t = float(x.mean() / (x.std() / np.sqrt(len(x)))) if len(x) > 20 else np.nan
            weak = not (t >= min_t)
            strikes = it.get("strikes", 0) + 1 if weak else 0
            it["strikes"] = strikes
            if strikes >= 2:
                it["status"] = "retired"
            elif promote_t is not None:
                strong = t >= promote_t if t == t else False
                it["passes"] = it.get("passes", 0) + 1 if strong else 0
                if it["passes"] >= 2 and it["status"] == "probation":
                    it["status"] = "active"
            it["history"].append({"date": dt.date.today().isoformat(), "recheck_t": t,
                                  "window": window, "status": it["status"]})


def dynamic_weights(ic: pd.DataFrame, signs: pd.Series, horizon: int, lookback: int,
                    shrink: float) -> pd.DataFrame:
    """Per-date factor weights using only ICs whose labels were REALISED before
    that date (shift by horizon+1). Weights = shrink * prior sign / n
    + (1-shrink) * trailing mean IC / sum|trailing mean IC|."""
    lagged = ic.shift(horizon + 1)
    trail = lagged.rolling(lookback, min_periods=lookback // 2).mean()
    dyn = trail.div(trail.abs().sum(axis=1), axis=0)
    prior = pd.DataFrame(np.tile(signs.reindex(ic.columns).values / len(ic.columns), (len(ic), 1)),
                         index=ic.index, columns=ic.columns)
    w = shrink * prior + (1 - shrink) * dyn.fillna(0.0)
    return w.fillna(prior)


def combine(ranked: pd.DataFrame, weights: pd.DataFrame) -> pd.Series:
    """Score = sum_i w_i(t) * rank_i(t). ranked: (date, inst) x factor."""
    w = weights[list(ranked.columns)].sort_index()
    dates = ranked.index.get_level_values(0)
    w = w.reindex(w.index.union(dates.unique())).ffill().reindex(dates).fillna(0.0).values
    return pd.Series((ranked.values * w).sum(axis=1), index=ranked.index)
