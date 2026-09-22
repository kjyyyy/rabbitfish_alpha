# Data

## China A-shares (default, free)
`alphalab download-cn` fetches the Qlib community dataset (chenditc/investment_data, updated
daily): CSI 300/500/800/1000 point-in-time membership, 2000 to present. It is not official
exchange data. Spot-check it before relying on it.

## US
Qlib's collector (clone microsoft/qlib; the PyPI wheel does not ship `scripts/`):
```bash
python scripts/data_collector/yahoo/collector.py download_data --source_dir ~/.qlib/us_raw --region US --interval 1d
python scripts/data_collector/yahoo/collector.py normalize_data --source_dir ~/.qlib/us_raw --normalize_dir ~/.qlib/us_norm --region US
python scripts/dump_bin.py dump_all --data_path ~/.qlib/us_norm --qlib_dir data/us_data --include_fields open,close,high,low,volume,factor
python scripts/data_collector/us_index/collector.py --index_name SP500 --qlib_dir data/us_data --method parse_instruments
```
Yahoo data is **not survivorship-free**. The US config marks `point_in_time_universe: false`,
so its cards can never reach the backtest tier. Use a point-in-time vendor (such as Norgate) for real work.

## UK
Qlib has no UK collector. Export daily OHLCV CSVs (one file per symbol: date, open, high, low,
close, volume, factor) from your vendor, then run `python scripts/dump_bin.py dump_all
--data_path <csv_dir> --qlib_dir data/uk_data`. Write `data/uk_data/instruments/ftse350.txt`
as tab-separated `SYMBOL  start  end` rows, one per membership spell. Costs in
`configs/uk_ftse350.yaml` include 0.5% stamp duty on purchases (AIM shares are exempt).

## Qlib version
PyPI `pyqlib 0.9.7` (Aug 2025) works. Qlib `main` has about 30 later commits, including pickle
security fixes. To pin them: `pip install "pyqlib @ git+https://github.com/microsoft/qlib@be725493eb1a6bbb42bf11b37aa7669f59610ff1"`
(this builds Cython extensions; on Windows use WSL).
