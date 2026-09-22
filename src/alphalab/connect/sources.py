"""Read-only market data for crypto and futures, from free sources.

Everything here fetches. Nothing here trades, and no function accepts a key
with trade permission - the research layer holds no credential that could move
money, which is the whole reason the layers are separate.

Two routes, and the choice between them matters more than it looks:

* **Bulk archive** (`binance_bulk_urls`) - Binance publishes zipped CSVs per
  symbol per day/month at data.binance.vision, including funding rates and
  metrics, with `.CHECKSUM` files. This is the only route that gives deep
  history without thousands of paginated calls, and it is the one to build on.
  Two documented traps are handled here: spot archive timestamps switched to
  MICROSECONDS from 1 January 2025 (a silent mid-series unit change), and the
  archive retains symbols that have since been delisted - which, by diffing it
  against the live symbol list, is the only free way found to recover a
  survivorship-honest universe.
* **REST via ccxt** (`fetch_ohlcv`) - convenient, unified across venues, and
  rate-limited per exchange. Good for recent data and for funding rates; poor
  for deep backfill, because venues cap candles per request.

Known venue limits worth respecting rather than discovering: Kraken's REST
returns only the most recent ~720 candles and older data cannot be retrieved
through it (their bulk CSVs exist instead); Hyperliquid's candle snapshot
returns only the most recent ~5,000, so its fine-grained history must be
captured going forward rather than backfilled.

Commodity futures are deliberately not wrapped here. The free per-contract
sources that once existed have gone - Nasdaq Data Link's CHRIS continuous
futures is deprecated with no replacement, and Stooq began requiring a key in
March 2026 - so the honest path for dated commodity contracts is a licensed
feed. `alphalab ingest` takes whatever panel you obtain; see
`docs/crypto-and-futures.md`.
"""
from __future__ import annotations

import datetime as dt
from typing import Iterable

BULK = "https://data.binance.vision/data"
# The archive switched spot timestamps from milliseconds to microseconds here.
# Parsing a whole history with one assumed unit silently mangles everything on
# one side of this date.
SPOT_MICROSECOND_CUTOVER = dt.date(2025, 1, 1)


def timestamp_unit(market: str, day: dt.date) -> str:
    """Which unit the archive uses for this market and date."""
    if market == "spot" and day >= SPOT_MICROSECOND_CUTOVER:
        return "us"
    return "ms"


def binance_bulk_urls(symbol: str, interval: str = "1d", market: str = "um",
                      kind: str = "klines", months: Iterable[str] = ()) -> list[dict]:
    """Archive URLs plus their checksums, for the months given as 'YYYY-MM'.

    `market` is 'spot', 'um' (USD-margined perpetuals) or 'cm' (coin-margined,
    which is where the dated quarterly contracts live - the free per-contract
    history that makes it possible to build and test a roll engine without
    paying for a commodity feed).
    """
    if market not in ("spot", "um", "cm"):
        raise ValueError("market must be 'spot', 'um' or 'cm'")
    if kind not in ("klines", "fundingRate", "metrics"):
        raise ValueError("kind must be 'klines', 'fundingRate' or 'metrics'")
    seg = "spot" if market == "spot" else f"futures/{market}"
    out = []
    for m in months:
        if kind == "klines":
            path = f"{BULK}/{seg}/monthly/klines/{symbol}/{interval}/{symbol}-{interval}-{m}.zip"
        else:
            path = f"{BULK}/{seg}/monthly/{kind}/{symbol}/{symbol}-{kind}-{m}.zip"
        day = dt.date(int(m[:4]), int(m[5:7]), 1)
        out.append(dict(url=path, checksum=path + ".CHECKSUM", month=m,
                        timestamp_unit=timestamp_unit(market, day)))
    return out


def survivorship_diff(archive_symbols: Iterable[str], live_symbols: Iterable[str]) -> dict:
    """Symbols the archive still holds that the venue no longer lists.

    This is the closest thing to a free delisting register that exists. Price
    APIs serve only what is currently listed - CoinGecko states plainly that
    historical data for inactive or delisted coins is not available through it -
    so a universe built from a live symbol list has already deleted everything
    that died. In crypto that is not a small correction: it removes the entire
    left tail of the return distribution.
    """
    arch, live = set(archive_symbols), set(live_symbols)
    dead = sorted(arch - live)
    return dict(archive=len(arch), live=len(live), delisted=dead, n_delisted=len(dead),
                survivorship_warning=(
                    f"{len(dead)} symbol(s) exist in the archive but not in the live listing. "
                    f"A universe built from the live list alone silently excludes them, and "
                    f"they are disproportionately the ones that went to zero."
                    if dead else "no delisted symbols detected in this comparison"))


def fetch_ohlcv(exchange: str, symbol: str, timeframe: str = "1d", since=None,
                limit: int = 1000, sandbox: bool = False):
    """Candles via ccxt. Read-only: no credentials are accepted or used.

    ccxt is MIT-licensed and covers 100+ venues behind one interface. Rate
    limiting is left enabled deliberately - disabling it is how an IP gets
    banned mid-backfill.
    """
    try:
        import ccxt
    except ImportError as e:                          # pragma: no cover - optional dependency
        raise SystemExit("ccxt is not installed: pip install ccxt\n"
                         "It is optional: the lab runs on ingested CSVs without it.") from e
    if not hasattr(ccxt, exchange):
        raise ValueError(f"ccxt has no exchange {exchange!r}")
    ex = getattr(ccxt, exchange)({"enableRateLimit": True})
    if sandbox:
        ex.set_sandbox_mode(True)                     # must precede every other call
    return ex.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit)


def fetch_funding(exchange: str, symbol: str, since=None, limit: int = 1000):
    """Historical funding rates, where the venue exposes them through ccxt.

    Funding is both a cost and a signal, and it is the one series a price-only
    crypto backtest silently omits - which flatters every long-perp strategy by
    exactly the amount it would have paid.
    """
    try:
        import ccxt
    except ImportError as e:                          # pragma: no cover
        raise SystemExit("ccxt is not installed: pip install ccxt") from e
    ex = getattr(ccxt, exchange)({"enableRateLimit": True})
    if not getattr(ex, "has", {}).get("fetchFundingRateHistory"):
        raise SystemExit(f"{exchange} does not expose funding history through ccxt; use the "
                         f"bulk archive (see binance_bulk_urls(kind='fundingRate'))")
    return ex.fetch_funding_rate_history(symbol, since=since, limit=limit)
