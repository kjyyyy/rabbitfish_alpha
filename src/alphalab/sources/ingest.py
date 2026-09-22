"""`alphalab ingest` - point the lab at your own OHLCV files.

Until now the only data path was the 570MB Qlib community CSI-300 download,
which UK retail investors cannot trade. This converts a directory of per-symbol
CSVs (or one long CSV with a symbol column) into the on-disk format the engine
reads, so anyone can run the lab on data they already have: a broker export,
Stooq, Yahoo, a vendor file, their own scraper.

The binary layout is Qlib's and is written directly rather than through its
`dump_bin` script, which does not ship in the wheel:

    <dest>/calendars/day.txt            every session, ascending
    <dest>/instruments/all.txt          SYMBOL<TAB>first_date<TAB>last_date
    <dest>/features/<symbol>/<f>.day.bin   float32: [start_index, v0, v1, ...]

Two warnings this module will not let you skip, because they are the two ways
a hobby backtest lies to itself:

* **Adjusted prices.** If your file is unadjusted, every split is a fake
  overnight return. Pass `--factor-col` or adjust before ingesting.
* **Survivorship.** A file containing only today's listed names has already
  deleted every company that failed. The lab reports this on the validity card,
  but it cannot detect it for you.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

FIELDS = ("open", "high", "low", "close", "volume", "amount", "vwap", "factor")
REQUIRED = ("open", "high", "low", "close", "volume")


def _read_one(path: Path, date_col: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    if date_col not in df.columns:
        raise SystemExit(f"{path.name}: no '{date_col}' column (found: {', '.join(df.columns)})")
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    return df.dropna(subset=[date_col]).sort_values(date_col)


def collect(src: Path, date_col: str = "date", symbol_col: str | None = None) -> dict[str, pd.DataFrame]:
    """Return {symbol: frame indexed by date}, from a directory or one long CSV."""
    frames: dict[str, pd.DataFrame] = {}
    if src.is_dir():
        files = sorted([*src.glob("*.csv"), *src.glob("*.CSV")])
        if not files:
            raise SystemExit(f"no .csv files in {src}")
        for f in files:
            frames[f.stem.strip().lower()] = _read_one(f, date_col).set_index(date_col)
    else:
        df = _read_one(src, date_col)
        col = (symbol_col or "symbol").lower()
        if col not in df.columns:
            raise SystemExit(f"{src.name} is one file, so it needs a symbol column "
                             f"(--symbol-col, default 'symbol'); found: {', '.join(df.columns)}")
        for sym, g in df.groupby(col):
            frames[str(sym).strip().lower()] = g.drop(columns=[col]).set_index(date_col)
    return frames


def audit(frames: dict[str, pd.DataFrame]) -> list[str]:
    """Problems worth stopping for, in the order they corrupt results."""
    problems = []
    for sym, df in frames.items():
        missing = [c for c in REQUIRED if c not in df.columns]
        if missing:
            problems.append(f"{sym}: missing column(s) {', '.join(missing)}")
            continue
        if df.index.has_duplicates:
            n = int(df.index.duplicated().sum())
            problems.append(f"{sym}: {n} duplicate date(s) - the last one would silently win")
        px = df[["open", "high", "low", "close"]]
        if (px <= 0).any().any():
            problems.append(f"{sym}: non-positive prices - returns would be undefined")
        if (df["high"] < df["low"]).any():
            problems.append(f"{sym}: high < low on some rows")
    return problems


def write_provider(frames: dict[str, pd.DataFrame], dest: Path, universe: str = "all",
                   log=print) -> dict:
    dest = Path(dest)
    (dest / "features").mkdir(parents=True, exist_ok=True)
    (dest / "calendars").mkdir(parents=True, exist_ok=True)
    (dest / "instruments").mkdir(parents=True, exist_ok=True)

    calendar = sorted({d for df in frames.values() for d in df.index})
    pos = {d: i for i, d in enumerate(calendar)}
    (dest / "calendars" / "day.txt").write_text(
        "\n".join(d.strftime("%Y-%m-%d") for d in calendar) + "\n")

    lines, written = [], 0
    for sym, df in frames.items():
        df = df[~df.index.duplicated(keep="last")].sort_index()
        d = pd.DataFrame(index=df.index)
        for f in REQUIRED:
            d[f] = pd.to_numeric(df[f], errors="coerce")
        # amount and vwap are derived when absent; factor defaults to 1 (see the warning)
        d["amount"] = pd.to_numeric(df["amount"], errors="coerce") if "amount" in df \
            else d["close"] * d["volume"]
        d["vwap"] = pd.to_numeric(df["vwap"], errors="coerce") if "vwap" in df \
            else (d["amount"] / d["volume"].replace(0, np.nan))
        d["factor"] = pd.to_numeric(df["factor"], errors="coerce") if "factor" in df else 1.0

        start = pos[d.index[0]]
        out = dest / "features" / sym
        out.mkdir(parents=True, exist_ok=True)
        for f in FIELDS:
            arr = np.empty(len(d) + 1, dtype="<f4")
            arr[0] = np.float32(start)                 # Qlib's header: calendar start index
            arr[1:] = d[f].to_numpy(dtype="float32")
            (out / f"{f}.day.bin").write_bytes(arr.tobytes())
        lines.append(f"{sym.upper()}\t{d.index[0]:%Y-%m-%d}\t{d.index[-1]:%Y-%m-%d}")
        written += 1

    (dest / "instruments" / "all.txt").write_text("\n".join(lines) + "\n")
    if universe != "all":
        (dest / "instruments" / f"{universe}.txt").write_text("\n".join(lines) + "\n")
    meta = dict(instruments=written, sessions=len(calendar),
                start=calendar[0].strftime("%Y-%m-%d"), end=calendar[-1].strftime("%Y-%m-%d"),
                universe=universe, fields=list(FIELDS))
    (dest / "ingest_meta.json").write_text(json.dumps(meta, indent=2))
    return meta


CONFIG_TEMPLATE = """# Written by `alphalab ingest`. Everything here is set BEFORE looking at
# results - that is the point of a config file in this repo.
name: {name}
market:
  name: {region}
  qlib_region: {region}
  provider_uri: {dest}
  universe: {universe}
  benchmark: ""                 # a symbol you ingested, or leave empty for an equal-weight proxy
  point_in_time_universe: false # your file has no membership history, so this cannot be true
  survivorship_note: "ingested from {src} - check whether delisted names are present"
  price_limits: false
  adv_expr: "$amount"
  adv_scale: 1.0
  costs:
    commission: 0.0005
    slippage: 0.0010
trading:
  # scaled to YOUR universe: picking 30 of 40 names is not a portfolio, it is the
  # market, and every cross-sectional signal looks flat through it
  topk: {topk}
  keep_rank: {keep_rank}
splits:
  data_start: "{start}"
  discover_start: "{start}"
  discover_end: "{disc_end}"
  valid_years: [{valid}]
  holdout_years: [{holdout}]
  data_end: "{end}"
llm:
  provider: mock                # no key needed; switch to anthropic/openai when ready
  critic_provider: mock
"""


def write_config(path: Path, meta: dict, dest: str, src: str, region: str) -> Path:
    """A ready-to-run config, so nobody has to hand-edit YAML to see their data work."""
    y0, y1 = int(meta["start"][:4]), int(meta["end"][:4])
    span = max(y1 - y0, 2)
    disc_end_year = y0 + max(int(span * 0.6), 1)
    valid = list(range(disc_end_year + 1, y1))
    holdout = [y1]
    n = int(meta["instruments"])
    topk = max(3, min(30, n // 5))
    # absolute: a relative provider_uri silently resolves against the current
    # directory, so the same config works from one folder and not another
    path.write_text(CONFIG_TEMPLATE.format(
        name=path.stem, region=region, dest=Path(dest).resolve(), universe=meta["universe"],
        src=src,
        topk=topk, keep_rank=min(n, topk * 2),
        start=meta["start"], end=meta["end"], disc_end=f"{disc_end_year}-12-31",
        valid=", ".join(str(y) for y in valid) or str(disc_end_year + 1),
        holdout=", ".join(str(y) for y in holdout)))
    return path


def run(src: str, dest: str = "data/my_market", universe: str = "all", date_col: str = "date",
        symbol_col: str | None = None, region: str = "us", force: bool = False,
        write_config_to: str | None = None, log=print) -> dict:
    frames = collect(Path(src), date_col, symbol_col)
    log(f"read {len(frames)} instrument(s) from {src}")
    problems = audit(frames)
    for p in problems:
        log(f"  PROBLEM  {p}")
    if problems and not force:
        raise SystemExit(f"{len(problems)} data problem(s); fix them, or pass --force to ingest "
                         f"anyway and let the numerical gates reject what they can")

    meta = write_provider(frames, Path(dest), universe, log)
    has_factor = any("factor" in df.columns for df in frames.values())
    log(f"\nwrote {meta['instruments']} instruments x {meta['sessions']} sessions "
        f"({meta['start']} .. {meta['end']}) to {dest}")
    if not has_factor:
        log("\nWARNING: no `factor` column, so prices are assumed ALREADY ADJUSTED for splits\n"
            "         and dividends. If they are not, every split is a fake overnight return\n"
            "         and every result from this data is fiction.")
    log("WARNING: if this file contains only names listed today, it is survivorship-biased.\n"
        "         The lab reports that on the validity card; it cannot detect it for you.")
    if write_config_to:
        cfgp = write_config(Path(write_config_to), meta, dest, src, region)
        log(f"\nwrote a ready-to-run config: {cfgp}")
        if meta["instruments"] < 50:
            log(f"\nNOTE: {meta['instruments']} instruments is thin for cross-sectional research. "
                f"topk was scaled down to match, but a long/short book over so few names is "
                f"dominated by single-stock risk - treat anything it finds as a smoke test.")
        log(f"\nnext:\n  alphalab doctor -c {cfgp}\n  alphalab sanity -c {cfgp}"
            f"\n  alphalab discover -c {cfgp}")
        return meta

    log(f"""
point a config at it (or re-run with --write-config <path> to have it written for you):

  market:
    name: {region}
    qlib_region: {region}
    provider_uri: {dest}
    universe: {universe}
    benchmark: ""              # set a benchmark symbol if you ingested one
    point_in_time_universe: false
    price_limits: false
  splits:
    data_start: "{meta['start']}"
    data_end: "{meta['end']}"

then:  alphalab doctor -c <your-config>  &&  alphalab sanity -c <your-config>""")
    return meta
