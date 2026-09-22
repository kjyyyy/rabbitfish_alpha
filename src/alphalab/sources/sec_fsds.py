"""SEC Financial Statement Data Sets -> point-in-time fundamentals.

Why this source: it is free, published by the regulator, and **as filed** -
the SEC states the data is "presented without change from the 'as filed'
financial reports". Each row carries the filing's acceptance date, so a factor
can use only what was public at the time. Quarterly ZIPs, 2009Q2 to present.
    https://www.sec.gov/data-research/sec-markets-data/financial-statement-data-sets

That makes it the free substitute for Compustat point-in-time, and the single
biggest data upgrade available to this lab (see docs/data-sources.md).

Caveats worth keeping in mind: the SEC does not guarantee accuracy; tags are
filer-chosen so the same concept appears under different tags; amended filings
(10-K/A) appear as separate rows and must be handled as new information, not as
corrections to the past; and there are no share prices or tickers here - map
CIK to ticker with the free company_tickers.json.

Network access is required to download; this module is written so the parsing
half can be unit-tested offline from a small fixture.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pandas as pd

BASE = "https://www.sec.gov/files/dera/data/financial-statement-data-sets"
# The SEC requires a descriptive User-Agent with contact details on every request.
USER_AGENT = "alphalab research (contact: set SEC_CONTACT env var)"

# a deliberately small, interpretable starting set
DEFAULT_TAGS = (
    "Assets", "Liabilities", "StockholdersEquity", "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax", "NetIncomeLoss",
    "OperatingIncomeLoss", "CashAndCashEquivalentsAtCarryingValue",
    "NetCashProvidedByUsedInOperatingActivities", "CommonStockSharesOutstanding",
)


def quarter_url(year: int, quarter: int) -> str:
    return f"{BASE}/{year}q{quarter}.zip"


def parse_quarter(zip_bytes: bytes, tags=DEFAULT_TAGS) -> pd.DataFrame:
    """Parse one quarterly ZIP into tidy point-in-time rows.

    Returns columns: cik, adsh, filed (the date the market could see it),
    period, fy, fp, tag, value. `filed` is what makes this point-in-time -
    join fundamentals to prices on `filed`, never on `period`.
    """
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        sub = pd.read_csv(z.open("sub.txt"), sep="\t", dtype=str,
                          usecols=["adsh", "cik", "name", "form", "period", "fy", "fp", "filed"])
        num = pd.read_csv(z.open("num.txt"), sep="\t", dtype={"adsh": str, "tag": str, "value": float},
                          usecols=["adsh", "tag", "ddate", "qtrs", "uom", "value"])
    num = num[(num.tag.isin(tags)) & (num.uom.isin(["USD", "shares"]))]
    num = num[num.value.notna()]
    df = num.merge(sub, on="adsh", how="inner")
    df["filed"] = pd.to_datetime(df["filed"], format="%Y%m%d", errors="coerce")
    df["period"] = pd.to_datetime(df["period"], format="%Y%m%d", errors="coerce")
    df["cik"] = pd.to_numeric(df["cik"], errors="coerce").astype("Int64")
    df = df.dropna(subset=["filed", "cik"])
    return df[["cik", "adsh", "name", "form", "filed", "period", "fy", "fp", "tag", "value"]]


def latest_known(df: pd.DataFrame, asof: pd.Timestamp) -> pd.DataFrame:
    """The most recent value of each (cik, tag) that was already FILED by `asof`.
    This is the join that keeps a fundamental factor honest."""
    known = df[df["filed"] <= pd.Timestamp(asof)]
    known = known.sort_values("filed")
    return (known.groupby(["cik", "tag"], as_index=False).last()
            [["cik", "tag", "value", "filed", "period"]])


def download_quarter(year: int, quarter: int, out_dir: Path, contact: str | None = None) -> Path:
    """Fetch one quarterly ZIP. Requires network access and a contact string."""
    import urllib.request
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{year}q{quarter}.zip"
    if dest.exists():
        return dest
    req = urllib.request.Request(quarter_url(year, quarter),
                                 headers={"User-Agent": contact or USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as r:      # noqa: S310 - fixed SEC host
        dest.write_bytes(r.read())
    return dest
