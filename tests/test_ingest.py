"""Bring-your-own-data: the CSV path must produce exactly what the engine reads."""
import numpy as np
import pandas as pd
import pytest

from alphalab.sources import ingest


def _csvs(d, syms=("aaa", "bbb"), n=40):
    dates = pd.bdate_range("2024-01-01", periods=n)
    for s in syms:
        px = np.linspace(10, 20, n)
        pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "open": px, "high": px * 1.01,
                      "low": px * 0.99, "close": px, "volume": np.arange(n) + 1000
                      }).to_csv(d / f"{s}.csv", index=False)
    return dates


def test_round_trip_matches_the_source_csv(tmp_path):
    src, dest = tmp_path / "csv", tmp_path / "prov"
    src.mkdir()
    dates = _csvs(src)
    meta = ingest.run(str(src), str(dest), universe="book", log=lambda *_: None)
    assert meta["instruments"] == 2 and meta["sessions"] == len(dates)

    cal = (dest / "calendars" / "day.txt").read_text().split()
    assert cal[0] == "2024-01-01" and len(cal) == len(dates)
    assert (dest / "instruments" / "book.txt").exists()

    raw = np.fromfile(dest / "features" / "aaa" / "close.day.bin", dtype="<f4")
    assert raw[0] == 0.0, "the header is the instrument's start index into the calendar"
    assert len(raw) == len(dates) + 1
    assert raw[1] == pytest.approx(10.0) and raw[-1] == pytest.approx(20.0)

    # amount and vwap are derived when absent
    amount = np.fromfile(dest / "features" / "aaa" / "amount.day.bin", dtype="<f4")
    assert amount[1] == pytest.approx(10.0 * 1000, rel=1e-5)


def test_bad_data_is_refused_rather_than_silently_ingested(tmp_path):
    src, dest = tmp_path / "csv", tmp_path / "prov"
    src.mkdir()
    _csvs(src, syms=("aaa",))
    df = pd.read_csv(src / "aaa.csv")
    df.loc[3, "close"] = -5.0                     # a negative price makes returns undefined
    df.loc[7, "date"] = df.loc[6, "date"]         # a duplicate date silently overwrites
    df.to_csv(src / "aaa.csv", index=False)

    with pytest.raises(SystemExit) as e:
        ingest.run(str(src), str(dest), log=lambda *_: None)
    assert "2 data problem" in str(e.value)
    assert ingest.run(str(src), str(dest), force=True, log=lambda *_: None)["instruments"] == 1


def test_a_single_long_csv_needs_a_symbol_column(tmp_path):
    src, dest = tmp_path / "all.csv", tmp_path / "prov"
    dates = pd.bdate_range("2024-01-01", periods=30)
    rows = [dict(date=d.strftime("%Y-%m-%d"), symbol=s, open=1.0, high=1.0, low=1.0,
                 close=1.0, volume=100) for s in ("x", "y") for d in dates]
    pd.DataFrame(rows).to_csv(src, index=False)
    assert ingest.run(str(src), str(dest), symbol_col="symbol",
                      log=lambda *_: None)["instruments"] == 2

    pd.DataFrame(rows).drop(columns=["symbol"]).to_csv(src, index=False)
    with pytest.raises(SystemExit, match="symbol column"):
        ingest.run(str(src), str(dest), log=lambda *_: None)


def test_generated_config_scales_topk_to_the_universe(tmp_path):
    """Picking 30 of 40 names is the market, not a portfolio: the engine's own
    sanity check fails on such a config, which is how this was found."""
    import yaml

    src, dest = tmp_path / "csv", tmp_path / "prov"
    src.mkdir()
    _csvs(src, syms=[f"s{i:02d}" for i in range(40)], n=60)
    cfg_path = tmp_path / "mine.yaml"
    ingest.run(str(src), str(dest), universe="mine", write_config_to=str(cfg_path),
               log=lambda *_: None)

    cfg = yaml.safe_load(cfg_path.read_text())
    assert cfg["trading"]["topk"] == 8                      # 40 // 5
    assert cfg["trading"]["keep_rank"] == 16
    assert cfg["market"]["point_in_time_universe"] is False, \
        "an ingested file has no membership history, so this can never be true"

    from alphalab.config import load
    loaded = load(cfg_path)                                  # must validate against the schema
    assert loaded.market.provider_uri == str(dest)
