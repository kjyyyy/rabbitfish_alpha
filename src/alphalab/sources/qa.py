"""Data QA for a fundamentals table: the checks to run before trusting a factor.

Reporting-lag distribution, tag coverage, missing data, outliers and
restatement frequency. These are the "data hardening" checks - cheap, and they
catch the failures that quietly invalidate months of research."""
from __future__ import annotations

import numpy as np

from .fundamentals import PITFundamentals


def report(fun: PITFundamentals, dates=None) -> dict:
    rows = fun.rows
    lag = fun.reporting_lag
    dup = rows.duplicated(subset=["cik", "tag", "period"], keep=False)
    per_tag = rows.groupby("tag").agg(rows=("value", "size"), ciks=("cik", "nunique"))
    out = dict(
        n_rows=int(len(rows)), n_ciks=int(rows["cik"].nunique()), n_tags=int(rows["tag"].nunique()),
        date_range=[str(rows["filed"].min().date()), str(rows["filed"].max().date())],
        reporting_lag_days=dict(median=float(lag.median()), p90=float(lag.quantile(0.9)),
                                max=float(lag.max()), negative=int((lag < 0).sum())),
        restatements=int(dup.sum()),
        tags={t: dict(rows=int(r.rows), ciks=int(r.ciks)) for t, r in per_tag.iterrows()},
        outliers={t: int((np.abs(s - s.median()) > 20 * (s.quantile(0.75) - s.quantile(0.25) + 1e-9)).sum())
                  for t, s in rows.groupby("tag")["value"]},
    )
    if dates is not None:
        cov = {t: float(fun.coverage(dates, t).mean()) for t in rows["tag"].unique()}
        out["mean_daily_coverage"] = cov
    return out


def problems(rep: dict) -> list[str]:
    """Human-readable warnings worth blocking research on."""
    msgs = []
    if rep["reporting_lag_days"]["negative"]:
        msgs.append(f"{rep['reporting_lag_days']['negative']} rows filed BEFORE their period end "
                    "- impossible; check the parser")
    if rep["reporting_lag_days"]["median"] < 5:
        msgs.append("median reporting lag under 5 days is implausible for SEC filings")
    if rep["restatements"]:
        msgs.append(f"{rep['restatements']} rows share (cik, tag, period) - restatements present; "
                    "as_of() serves whichever was current, which is correct, but factor "
                    "definitions should not assume one row per period")
    for tag, n in rep.get("outliers", {}).items():
        if n:
            msgs.append(f"{tag}: {n} extreme values - winsorise before ranking")
    return msgs
