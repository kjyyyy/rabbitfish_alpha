"""Offline tests for the free-data adapters (fixtures, no network)."""
import io
import zipfile

import pandas as pd

from alphalab.sources.delistings import delisting_calendar, parse_form_index
from alphalab.sources.sec_fsds import latest_known, parse_quarter

SUB = "adsh\tcik\tname\tform\tperiod\tfy\tfp\tfiled\n" \
      "0001-24-000001\t320193\tAPPLE INC\t10-Q\t20240630\t2024\tQ3\t20240802\n" \
      "0001-24-000002\t789019\tMICROSOFT CORP\t10-K\t20240630\t2024\tFY\t20240730\n"
NUM = "adsh\ttag\tddate\tqtrs\tuom\tvalue\n" \
      "0001-24-000001\tAssets\t20240630\t0\tUSD\t331612000000\n" \
      "0001-24-000001\tNetIncomeLoss\t20240630\t1\tUSD\t21448000000\n" \
      "0001-24-000001\tNotATrackedTag\t20240630\t1\tUSD\t1\n" \
      "0001-24-000002\tAssets\t20240630\t0\tUSD\t512163000000\n"


def _zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("sub.txt", SUB)
        z.writestr("num.txt", NUM)
    return buf.getvalue()


def test_parse_quarter_keeps_filing_date_and_filters_tags():
    df = parse_quarter(_zip())
    assert set(df.tag) == {"Assets", "NetIncomeLoss"}          # untracked tag dropped
    apple = df[df.cik == 320193].iloc[0]
    assert apple.filed == pd.Timestamp("2024-08-02")           # the date it became public
    assert apple.period == pd.Timestamp("2024-06-30")          # NOT the same thing
    assert apple.filed > apple.period


def test_latest_known_never_returns_unfiled_data():
    df = parse_quarter(_zip())
    # Microsoft filed 2024-07-30, Apple 2024-08-02
    before = latest_known(df, "2024-07-31")
    assert set(before.cik) == {789019}                         # Apple not public yet
    on_the_day = latest_known(df, "2024-07-29")
    assert on_the_day.empty                                    # nothing filed yet
    after = latest_known(df, "2024-08-05")
    assert set(after.cik) == {320193, 789019}


FORM_IDX = """Form Type   Company Name                                                  CIK         Date Filed  File Name
---------------------------------------------------------------------------------------------------
25          DEAD CORP                                                     1234567     2024-03-15  edgar/data/x.txt
25-NSE      EXPIRED INC                                                   7654321     2024-04-02  edgar/data/y.txt
10-K        ALIVE PLC                                                     1111111     2024-04-02  edgar/data/z.txt
"""


def test_parse_form_index_picks_only_delisting_forms():
    df = parse_form_index(FORM_IDX)
    assert list(df.form) == ["25", "25-NSE"]
    assert set(df.cik) == {1234567, 7654321}


def test_delisting_calendar_takes_the_first_filing():
    a = parse_form_index(FORM_IDX)
    b = a.copy()
    b["date"] = b["date"] + pd.Timedelta(days=200)
    cal = delisting_calendar([b, a])
    assert cal.loc[cal.cik == 1234567, "delisted_on"].iloc[0] == pd.Timestamp("2024-03-15")
