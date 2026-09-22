"""Delisting dates from SEC EDGAR, free.

An exchange files **Form 25** (or 25-NSE) to delist a security; those filings
are in EDGAR's quarterly full index, which is free and needs no key. That gives
a delisting DATE per CIK - enough to keep dead names in a universe instead of
silently dropping them, which is the bias that flatters backtests most.

What it does not give is the delisting RETURN. Shumway (1997) found omitted
delisting returns average about -30% for performance-related delistings, so a
universe built this way should apply a documented assumption (e.g. -30% on the
delisting date for exchange-initiated removals) and report it on the validity
card rather than pretending the number is known.
"""
from __future__ import annotations

import pandas as pd

FORM_INDEX = "https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{q}/form.idx"
DELISTING_FORMS = ("25", "25-NSE")


def parse_form_index(text: str, forms=DELISTING_FORMS) -> pd.DataFrame:
    """Parse an EDGAR form.idx into delisting rows (form, company, cik, date)."""
    rows = []
    started = False
    for line in text.splitlines():
        if line.startswith("-----"):
            started = True
            continue
        if not started or not line.strip():
            continue
        form = line[:12].strip()
        if form not in forms:
            continue
        company = line[12:74].strip()
        cik = line[74:86].strip()
        date = line[86:98].strip()
        if not cik.isdigit():
            continue
        rows.append(dict(form=form, company=company, cik=int(cik),
                         date=pd.to_datetime(date, errors="coerce")))
    return pd.DataFrame(rows).dropna(subset=["date"])


def delisting_calendar(frames) -> pd.DataFrame:
    """First delisting filing per CIK across many quarters."""
    df = pd.concat(list(frames), ignore_index=True)
    return (df.sort_values("date").groupby("cik", as_index=False).first()
            .rename(columns={"date": "delisted_on"}))
