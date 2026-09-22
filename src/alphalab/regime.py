"""Rule-based market regimes. Used for REPORTING breakdowns only - never for
allocation (LLM regime gating a la Alpha-R1 is not built; see docs)."""
import numpy as np
import pandas as pd


def label_regimes(bench_close: pd.Series) -> pd.DataFrame:
    r = bench_close.pct_change()
    trend = np.where(bench_close > bench_close.rolling(200).mean(), "up-trend", "down-trend")
    vol = r.rolling(60).std()
    vol_hi = vol > vol.expanding(250).median()
    return pd.DataFrame({"trend": trend, "vol": np.where(vol_hi, "high-vol", "low-vol")},
                        index=bench_close.index)


def breakdown(excess: pd.Series, regimes: pd.DataFrame, periods=244) -> dict:
    out = {}
    reg = regimes.reindex(excess.index)
    for col in reg.columns:
        for val, sub in excess.groupby(reg[col]):
            out[f"{col}={val}"] = dict(days=int(len(sub)),
                                       excess_ann=float(sub.mean() * periods),
                                       ir=float(sub.mean() / sub.std() * np.sqrt(periods)) if sub.std() > 0 else None)
    return out
