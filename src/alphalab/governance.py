"""Assumption register and exception log (SR 11-7 style, minimal).

Two files per run:

* `assumptions.json` - every choice a reader would need in order to reproduce
  or challenge a result: execution timing, cost model, universe, data source
  and its point-in-time treatment, gates. Generated from the config, so it
  cannot drift from what the code actually did.
* `exceptions.csv` - an append-only log of deviations: an ad-hoc filter, an
  excluded period, special handling for a name. Recording them is what keeps
  "exploratory" from quietly becoming "confirmatory".
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import subprocess
from pathlib import Path

from .config import Config


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except Exception:                                  # noqa: BLE001
        return "not-a-git-repo"


def assumption_register(cfg: Config) -> dict:
    c = cfg.market.costs
    return {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "git_sha": _git_sha(), "config_sha": cfg.sha(), "config_name": cfg.name,
        "execution": {
            "signal_time": "close of day t",
            "trade_time": "close of day t+1 (never the close used to build the signal)",
            "holding_period_days": cfg.trading.horizon,
            "rebalance": f"every {cfg.trading.horizon} trading days",
        },
        "universe": {
            "definition": cfg.market.universe,
            "point_in_time_membership": cfg.market.point_in_time_universe,
            "survivorship_note": cfg.market.survivorship_note or "point-in-time index membership",
            "price_limits_modelled": cfg.market.price_limits,
        },
        "costs_one_way": {
            "commission": c.commission, "slippage": c.slippage,
            "stamp_buy": c.stamp_buy, "stamp_sell": c.stamp_sell,
            "market_impact": "square-root law, ~10bp at 1% of ADV (AQR live-trade estimate)",
            "sensitivity_reported": "2x costs on every variant; break-even cost on every card",
        },
        "data": {
            "prices": cfg.market.provider_uri,
            "fundamentals": "SEC Financial Statement Data Sets (as filed) when configured",
            "pit_rule": "fundamentals are joined on filing date, never on period end",
            "delistings": "EDGAR Form 25 / 25-NSE when configured",
        },
        "statistics": {
            "trial_counting": "every candidate ever evaluated, including LLM rejects",
            "t_stat_min": cfg.gates.t_stat_min, "dsr_min": cfg.gates.dsr_min,
            "effective_n": "reported (eigenvalue and average-correlation) but never used for gating",
            "holdout_burned": cfg.splits.holdout_burned,
        },
    }


def write_register(cfg: Config) -> Path:
    p = cfg.run_dir / "assumptions.json"
    p.write_text(json.dumps(assumption_register(cfg), indent=2))
    return p


FIELDS = ("timestamp", "kind", "scope", "reason", "author")


def log_exception(cfg: Config, kind: str, scope: str, reason: str, author: str = "") -> Path:
    """Record a deviation from the standard protocol. Append-only."""
    p = cfg.run_dir / "exceptions.csv"
    new = not p.exists()
    with open(p, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(dict(timestamp=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                        kind=kind, scope=scope, reason=reason, author=author))
    if getattr(cfg.storage, "use_database", True):
        try:
            from .db import repo
            repo.add_exception(cfg.name, kind, scope, reason, author, url=cfg.storage.database_url)
        except Exception:                            # noqa: BLE001 - CSV is the fallback
            pass
    return p


def exceptions(cfg: Config) -> list[dict]:
    p = cfg.run_dir / "exceptions.csv"
    if not p.exists():
        return []
    with open(p) as f:
        return list(csv.DictReader(f))
