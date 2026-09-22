"""Data access through Qlib (lazy import), with on-disk caching."""
from __future__ import annotations

import hashlib
import pickle
import warnings

import pandas as pd

from .config import Config

warnings.filterwarnings("ignore")
_INIT: str | None = None


def init(cfg: Config):
    global _INIT
    if _INIT != cfg.market.provider_uri:
        try:
            import qlib
        except ImportError as e:
            raise SystemExit("Qlib is not installed: pip install -e '.[qlib]'") from e
        qlib.init(provider_uri=cfg.market.provider_uri, region=cfg.market.qlib_region,
                  kernels=2, logging_level="WARNING")
        _INIT = cfg.market.provider_uri


def _cached(cfg: Config, key: str, fn):
    p = cfg.cache_dir / (hashlib.md5(key.encode()).hexdigest()[:16] + ".pkl")
    if p.exists():
        return pickle.loads(p.read_bytes())
    obj = fn()
    p.write_bytes(pickle.dumps(obj))
    return obj


def features(cfg: Config, exprs, names=None, start=None, end=None, instruments=None):
    """Evaluate (already-audited) Qlib expressions. Index: (datetime, instrument)."""
    init(cfg)
    from qlib.data import D
    start, end = start or cfg.splits.data_start, end or cfg.splits.data_end
    names = list(names or exprs)
    inst = instruments if instruments is not None else cfg.market.universe
    key = f"{cfg.market.provider_uri}|{inst}|{start}|{end}|" + "||".join(exprs)

    def load():
        pool = D.instruments(inst) if isinstance(inst, str) else inst
        df = D.features(pool, list(exprs), start_time=start, end_time=end)
        df.columns = names
        return df.swaplevel().sort_index().astype("float32")
    return _cached(cfg, key, load)


def label(cfg: Config, start=None, end=None) -> pd.Series:
    return features(cfg, [cfg.trading.label_expr], ["label"], start, end)["label"]


def universe_names(cfg: Config):
    init(cfg)
    from qlib.data import D
    return sorted(D.list_instruments(D.instruments(cfg.market.universe),
                                     start_time=cfg.splits.data_start,
                                     end_time=cfg.splits.data_end, as_list=True))


def price_panel(cfg: Config):
    df = features(cfg, ["$close", "$volume"], ["close", "volume"],
                  instruments=universe_names(cfg))
    return df["close"].unstack(), df["volume"].unstack()


def adv_panel(cfg: Config, win: int = 20) -> pd.DataFrame:
    """Average daily traded VALUE in local currency (date x instrument)."""
    df = features(cfg, [cfg.market.adv_expr], ["adv"], instruments=universe_names(cfg))
    return (df["adv"].unstack() * cfg.market.adv_scale).rolling(win).mean()


def benchmark_close(cfg: Config) -> pd.Series:
    df = features(cfg, ["$close"], ["close"], instruments=[cfg.market.benchmark])
    return df["close"].droplevel(1)


def last_date(cfg: Config) -> str:
    init(cfg)
    from qlib.data import D
    return str(D.calendar(end_time=cfg.splits.data_end)[-1].date())


def cs_rank(df: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional percentile rank per date, centred on 0 (NaN -> 0)."""
    return (df.groupby(level=0).rank(pct=True) - 0.5).fillna(0.0).astype("float32")
