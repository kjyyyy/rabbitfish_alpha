"""An independent evaluator for the factor language.

Two jobs:

1. **Dynamic leakage testing.** Qlib computes an expression over the whole
   stored series and only then slices, so truncating the end date does NOT
   reveal look-ahead (verified experimentally). To test for leakage we need to
   control the data, which means evaluating expressions ourselves.
2. **Cross-checking Qlib.** Two independent implementations that agree are
   much stronger evidence than one. `tests/test_evalexpr.py` compares them.

Panel convention: a dict of {field: DataFrame(date x instrument)}.
Rolling windows are backward-looking and inclusive of the current bar, which
is what Qlib's operators do.
"""
from __future__ import annotations

import ast

import numpy as np
import pandas as pd

from .expr import parse


def _roll(x: pd.DataFrame, w: int):
    return x.rolling(int(w), min_periods=max(2, int(w) // 2))


OPS = {
    "Ref": lambda x, n: x.shift(int(n)),
    "Mean": lambda x, w: _roll(x, w).mean(),
    "Std": lambda x, w: _roll(x, w).std(),
    "Var": lambda x, w: _roll(x, w).var(),
    "Max": lambda x, w: _roll(x, w).max(),
    "Min": lambda x, w: _roll(x, w).min(),
    "Sum": lambda x, w: _roll(x, w).sum(),
    "Med": lambda x, w: _roll(x, w).median(),
    "Skew": lambda x, w: _roll(x, w).skew(),
    "Kurt": lambda x, w: _roll(x, w).kurt(),
    "Mad": lambda x, w: _roll(x, w).apply(lambda v: np.nanmean(np.abs(v - np.nanmean(v))), raw=True),
    "Delta": lambda x, w: x - x.shift(int(w)),
    "EMA": lambda x, w: x.ewm(span=int(w), min_periods=max(2, int(w) // 2)).mean(),
    "WMA": lambda x, w: _roll(x, w).apply(
        lambda v: np.nansum(v * np.arange(1, len(v) + 1)) / np.arange(1, len(v) + 1).sum(), raw=True),
    "Rank": lambda x, w: _roll(x, w).apply(lambda v: pd.Series(v).rank(pct=True).iloc[-1], raw=True),
    "IdxMax": lambda x, w: _roll(x, w).apply(lambda v: float(np.nanargmax(v)), raw=True),
    "IdxMin": lambda x, w: _roll(x, w).apply(lambda v: float(np.nanargmin(v)), raw=True),
    "Slope": lambda x, w: _roll(x, w).apply(_slope, raw=True),
    "Rsquare": lambda x, w: _roll(x, w).apply(_rsq, raw=True),
    "Resi": lambda x, w: _roll(x, w).apply(_resid, raw=True),
    "Quantile": lambda x, w, q: _roll(x, w).quantile(float(q)),
    "Corr": lambda a, b, w: _roll(a, w).corr(b),
    "Cov": lambda a, b, w: _roll(a, w).cov(b),
    "Abs": lambda x: x.abs(),
    "Log": lambda x: np.log(x.where(x > 0)),
    "Sign": lambda x: np.sign(x),
    "Greater": lambda a, b: _bin(a, b, np.maximum),
    "Less": lambda a, b: _bin(a, b, np.minimum),
    "Power": lambda a, b: _bin(a, b, np.power),
    "If": lambda c, a, b: _where(c, a, b),
}


def _fit(v):
    y = np.asarray(v, dtype=float)
    ok = ~np.isnan(y)
    if ok.sum() < 2:
        return None
    x = np.arange(len(y))[ok]
    return np.polyfit(x, y[ok], 1), y, ok, x


def _slope(v):
    f = _fit(v)
    return np.nan if f is None else f[0][0]


def _rsq(v):
    f = _fit(v)
    if f is None:
        return np.nan
    coef, y, ok, x = f
    pred = np.polyval(coef, x)
    ss_t = float(((y[ok] - y[ok].mean()) ** 2).sum())
    return np.nan if ss_t == 0 else 1 - float(((y[ok] - pred) ** 2).sum()) / ss_t


def _resid(v):
    f = _fit(v)
    if f is None:
        return np.nan
    coef, y, ok, x = f
    return float(y[ok][-1] - np.polyval(coef, x[-1]))


def _bin(a, b, fn):
    if isinstance(a, pd.DataFrame) or isinstance(b, pd.DataFrame):
        a_, b_ = (a, b) if isinstance(a, pd.DataFrame) else (b, a)
        return pd.DataFrame(fn(np.asarray(a), np.asarray(b)) if isinstance(b, pd.DataFrame)
                            else fn(a_.values, b_), index=a_.index, columns=a_.columns)
    return fn(a, b)


def _where(c, a, b):
    return pd.DataFrame(np.where(np.asarray(c) > 0, np.asarray(a), np.asarray(b)),
                        index=c.index, columns=c.columns)


def evaluate(expr: str, panel: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Evaluate an audited expression against a panel of field frames."""
    tree = parse(expr)                      # re-uses the AST whitelist

    def walk(node):
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant):
            return float(node.value)
        if isinstance(node, ast.Name):
            if node.id.startswith("F_"):
                f = node.id[2:]
                if f not in panel:
                    raise KeyError(f"field ${f} missing from panel")
                return panel[f]
            raise ValueError(f"unexpected name {node.id}")
        if isinstance(node, ast.UnaryOp):
            v = walk(node.operand)
            return -v if isinstance(node.op, ast.USub) else v
        if isinstance(node, ast.BinOp):
            a, b = walk(node.left), walk(node.right)
            op = {ast.Add: "add", ast.Sub: "sub", ast.Mult: "mul", ast.Div: "truediv"}[type(node.op)]
            if isinstance(a, pd.DataFrame):
                return getattr(a, op)(b)
            if isinstance(b, pd.DataFrame):
                return getattr(b, {"add": "radd", "sub": "rsub", "mul": "rmul",
                                   "truediv": "rtruediv"}[op])(a)
            return getattr(float(a), f"__{op}__")(float(b))
        if isinstance(node, ast.Call):
            return OPS[node.func.id](*[walk(x) for x in node.args])
        raise ValueError(f"unexpected node {type(node).__name__}")

    out = walk(tree)
    if not isinstance(out, pd.DataFrame):
        raise ValueError("expression does not depend on any field")
    return out.replace([np.inf, -np.inf], np.nan)


def synthetic_panel(n_days=260, n_names=40, seed=0, start="2020-01-01"):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start, periods=n_days)
    names = [f"S{i:03d}" for i in range(n_names)]
    r = rng.normal(0.0004, 0.02, (n_days, n_names))
    close = pd.DataFrame(50 * np.cumprod(1 + r, axis=0), index=dates, columns=names)
    high = close * (1 + np.abs(rng.normal(0, 0.01, close.shape)))
    low = close * (1 - np.abs(rng.normal(0, 0.01, close.shape)))
    open_ = low + (high - low) * rng.random(close.shape)
    volume = pd.DataFrame(rng.lognormal(12, 0.4, close.shape), index=dates, columns=names)
    return {"close": close, "high": high, "low": low, "open": open_,
            "vwap": (high + low + close) / 3, "volume": volume,
            "amount": close * volume}
