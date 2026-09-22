"""`alphalab validate` - the five corrections, run on a completed model run.

Walk-forward gives one number from one path through history. This gives a
distribution, a discount for the refinement loop that produced the candidate,
a check that the Sharpe was computed on a statistic you can actually harvest,
a decay curve, and a cost sweep - and it writes them next to the run so a
validity card can cite them rather than a person remembering them.

Deliberately a separate command rather than another step inside `model`: it
reads the returns a model run already wrote, so it is cheap to re-run as the
thresholds are argued about, and re-running it cannot change a result.
"""
from __future__ import annotations

import json

import pandas as pd

from .. import breadth, stats, validation
from ..config import Config


def run(cfg: Config, log=print) -> dict:
    rd = cfg.run_dir
    path = rd / "daily_returns.csv"
    if not path.exists():
        raise SystemExit(f"no {path} - run `alphalab model` first")
    curves = pd.read_csv(path, index_col=0, parse_dates=True)

    choice = json.loads((rd / "model_choice.json").read_text())["chosen"] \
        if (rd / "model_choice.json").exists() else None
    col = next((c for c in curves.columns if choice and c.startswith(f"{choice}|valid")),
               curves.columns[0])
    r = curves[col].dropna()
    bench = next((c for c in curves.columns if c.startswith("benchmark|valid")), None)
    excess = (r - curves[bench].reindex(r.index).fillna(0.0)) if bench else r

    periods = cfg.market.sessions_per_year
    market = cfg.market.asset_class
    sharpe_is = stats.sharpe(excess, periods)

    out: dict = dict(strategy=col, market=market, n_obs=int(len(r)),
                     sharpe_in_sample=float(sharpe_is))

    # 1. a distribution instead of one path
    out["cpcv"] = validation.cpcv(excess, n_blocks=8, n_test=2,
                                  purge=cfg.model.purge_days, embargo=5, periods=periods)

    # 2. discount the refinement loop that produced this candidate
    n_tweaks = 0
    s1 = rd / "discover_summary.json"
    if s1.exists():
        try:
            n_tweaks = int(json.loads(s1.read_text()).get("n_trials_total", 0))
        except (json.JSONDecodeError, TypeError, ValueError):
            n_tweaks = 0
    out["overfitting_factor"] = validation.overfitting_factor(sharpe_is, n_tweaks=n_tweaks)

    # 3. is the Sharpe computed on a harvestable statistic?
    out["log_wealth"] = validation.log_wealth_test(r)

    # 4. what does being slow cost?
    def at_lag(lag: int) -> float:
        s = r.shift(lag).dropna()
        return float((1 + s).prod() ** (periods / max(len(s), 1)) - 1)
    out["lagged_signal_decay"] = validation.lagged_signal_decay(at_lag)

    # 5. cost sensitivity.
    #
    # These returns ALREADY have the configured cost model in them, so adding a
    # synthetic drag on top would charge costs twice - the exact double-count
    # this lab exists to catch. The honest sweep re-runs the engine at each
    # multiplier, which `alphalab audit` already does; this reads its output
    # rather than approximating it.
    audit_path = rd / "protocol_audit.json"
    if audit_path.exists():
        a = json.loads(audit_path.read_text())
        variants = a.get("variants", {})
        measured = {1.0: a.get("baseline", {}).get("excess_ann")}
        if "zero_costs" in variants:
            measured[0.0] = variants["zero_costs"]["excess_ann"]
        if "punitive_costs" in variants:
            measured[3.0] = variants["punitive_costs"]["excess_ann"]
        measured = {k: v for k, v in measured.items() if v is not None}
        out["cost_sweep"] = validation.cost_sweep(lambda m: measured[m],
                                                  multipliers=tuple(sorted(measured)))
        out["cost_sweep"]["source"] = "protocol_audit.json (engine re-run per multiplier)"
    else:
        out["cost_sweep"] = dict(
            note="run `alphalab audit` for the cost sweep. It is not approximated here: these "
                 "returns already contain the configured cost model, so adding a drag on top "
                 "would charge costs twice.")

    # structural plausibility, pre-committed per market
    flag = breadth.implausible(sharpe_is, market)
    if flag:
        out["implausible"] = flag

    (rd / "validation.json").write_text(json.dumps(out, indent=2, default=float))

    c, o, lw = out["cpcv"], out["overfitting_factor"], out["log_wealth"]
    log(f"strategy {col}  ({market}, {len(r)} observations)\n")
    log(f"  walk-forward Sharpe          {sharpe_is:+.2f}   one path through history")
    if c.get("paths"):
        log(f"  CPCV Sharpe   p05/p50/p95   {c['sharpe_p05']:+.2f} / {c['sharpe_p50']:+.2f} / "
            f"{c['sharpe_p95']:+.2f}   over {c['paths']} paths")
        log(f"  probability of a negative Sharpe on a held-out block: {c['prob_negative']:.0%}")
    log(f"  after the overfitting factor  {o.get('sharpe_discounted', float('nan')):+.2f}   "
        f"(/{o['factor']}, threshold {o.get('acceptance_threshold')}) -> "
        f"{'passes' if o.get('passes') else 'FAILS'}")
    log(f"  compounds?                    {'yes' if lw.get('compounds') else 'NO'}   "
        f"log wealth {lw.get('log_wealth', float('nan')):+.3f} on the strategy's own returns "
        f"(the Sharpe above is excess over the benchmark)")
    if lw.get("mean_positive_but_compounds_negative"):
        log("  " + lw["note"])
    log(f"  costs                         {out['cost_sweep'].get('verdict') or out['cost_sweep'].get('note')}")
    d = out["lagged_signal_decay"]
    log(f"  delay                         {'LATENCY RACE' if d.get('latency_race') else 'patient'}"
        f"  half-life {d.get('half_life_periods')} period(s)")
    if flag:
        log(f"\n  {flag['message']}")
    return out
