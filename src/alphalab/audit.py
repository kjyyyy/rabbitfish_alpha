"""Decision-time protocol audit.

Most "alpha" in hobby backtests is manufactured by evaluation conventions, not
by signals. This module holds the data, the factors, the portfolio rule and the
costs fixed, and toggles **one convention at a time** against a strictly causal
reference. Whatever performance appears when a convention is loosened is
protocol-induced, not edge.

Conventions tested:

| variant | what changes | why it is (or isn't) legitimate |
|---|---|---|
| `baseline` | strictly causal: backward windows, per-date cross-sectional ranks, trade at the next close, point-in-time universe | the reference |
| `same_day_execution` | trade at the close of the signal day | you cannot trade a close you need to compute the signal |
| `centered_features` | rolling windows centred (half the window in the future) | classic silent leak |
| `global_normalisation` | z-score each factor over the whole sample | uses future means and standard deviations |
| `survivors_only` | universe restricted to names still in the index at the end | the classic survivorship bias |

Every variant is computed with the lab's own evaluator (`evalexpr`), so the
comparison is internally consistent and does not depend on Qlib's semantics.
"""
from __future__ import annotations

import json
from contextlib import contextmanager

import numpy as np
import pandas as pd

from . import backtest, data, evalexpr
from .config import Config
from .factors.hypotheses import HYPOTHESES

FIELDS = ("close", "high", "low", "open", "vwap", "volume", "amount")


def build_panel(cfg: Config, start: str, end: str) -> dict[str, pd.DataFrame]:
    names = data.universe_names(cfg)
    df = data.features(cfg, [f"${f}" for f in FIELDS], list(FIELDS), start, end, instruments=names)
    return {f: df[f].unstack() for f in FIELDS}


@contextmanager
def centred_windows():
    """Temporarily make every rolling operator centred - a deliberate leak."""
    original = dict(evalexpr.OPS)
    orig_roll = evalexpr._roll
    evalexpr._roll = lambda x, w: x.rolling(int(w), center=True, min_periods=max(2, int(w) // 2))
    for name in ("Mean", "Std", "Var", "Max", "Min", "Sum", "Med", "Skew", "Kurt"):
        fn = {"Mean": "mean", "Std": "std", "Var": "var", "Max": "max", "Min": "min",
              "Sum": "sum", "Med": "median", "Skew": "skew", "Kurt": "kurt"}[name]
        evalexpr.OPS[name] = (lambda f: (lambda x, w: getattr(evalexpr._roll(x, w), f)()))(fn)
    try:
        yield
    finally:
        evalexpr.OPS.clear()
        evalexpr.OPS.update(original)
        evalexpr._roll = orig_roll


def composite(panel: dict[str, pd.DataFrame], normalisation: str = "cross_sectional_rank") -> pd.Series:
    """Equal-weight composite of the written hypotheses, computed locally."""
    parts = []
    for h in HYPOTHESES:
        try:
            f = evalexpr.evaluate(h["expr"], panel) * h["sign"]
        except Exception:                       # noqa: BLE001 - a field may be missing
            continue
        if normalisation == "global_zscore":     # LEAKY: whole-sample statistics
            z = (f - np.nanmean(f.to_numpy())) / (np.nanstd(f.to_numpy()) + 1e-12)
        else:                                    # causal: rank within each date
            z = f.rank(axis=1, pct=True) - 0.5
        parts.append(z.fillna(0.0))
    comp = sum(parts) / max(len(parts), 1)
    return comp.stack().rename("score").sort_index()


def fundamentals_timing_bias(seed: int = 0, lag_days: int = 45) -> dict:
    """How much apparent alpha comes from joining fundamentals on the period end
    instead of the filing date? Measured on synthetic data where the answer is
    known by construction: the "fundamental" is built to predict returns, so a
    join that sees it `lag_days` early captures returns it could not have.

    Runs offline - no SEC download needed - so the bias is quantified before
    any real fundamental factor is trusted."""
    from .sources.fundamentals import PITFundamentals
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2020-01-01", periods=500)
    ids = list(range(1, 41))
    # future returns driven by a quarterly "quality" number
    quality = pd.DataFrame(rng.normal(size=(8, len(ids))), columns=ids,
                           index=pd.date_range("2020-03-31", periods=8, freq="QE"))
    rows = []
    for period, row in quality.iterrows():
        for cik, v in row.items():
            rows.append(dict(cik=cik, tag="NetIncomeLoss", period=period,
                             filed=period + pd.Timedelta(days=lag_days), value=float(v)))
    fun = PITFundamentals(pd.DataFrame(rows))
    honest_panel = fun.panel("NetIncomeLoss", dates, ciks=ids)          # known on filing
    early_panel = fun.panel("NetIncomeLoss", dates, ciks=ids, leaky_period_join=True)
    # Prices drift toward the true number from PERIOD END onwards - pre-announcements,
    # informed trading, the quarter's business performance being visible. That drift is
    # exactly what a period-end join captures and an honest researcher cannot.
    ret = pd.DataFrame(rng.normal(0, 0.01, (len(dates), len(ids))), index=dates, columns=ids)
    ret = ret + 0.002 * early_panel.shift(1).fillna(0.0)
    fwd = ret.shift(-1)

    def ic(panel):
        r = panel.rank(axis=1).corrwith(fwd.rank(axis=1), axis=1)
        return float(r.mean())

    honest = ic(honest_panel)
    leaky = ic(early_panel)
    return dict(reporting_lag_days=lag_days, ic_filing_date_join=honest,
                ic_period_end_join=leaky, inflation=leaky - honest)


def run(cfg: Config, log=print) -> dict:
    y0, y1 = cfg.splits.valid_years[0], cfg.splits.valid_years[-1]
    start = f"{y0 - 2}-01-01"
    end = f"{y1}-12-31"
    panel = build_panel(cfg, start, end)
    close, vol = data.price_panel(cfg)
    bench = data.benchmark_close(cfg)

    def score_to_metrics(scores, shift_execution=0):
        s = scores
        if shift_execution:                      # +1 day => the engine trades one day earlier
            s = s.unstack().shift(shift_execution).stack()
        s = s[s.index.get_level_values(0) >= pd.Timestamp(f"{y0}-01-01")]
        d, b, _ = backtest.run(cfg, s, close, vol, bench)
        return backtest.metrics(d, b)

    results = {}
    base_scores = composite(panel)
    results["baseline"] = score_to_metrics(base_scores)

    results["same_day_execution"] = score_to_metrics(base_scores, shift_execution=-1)

    with centred_windows():
        results["centered_features"] = score_to_metrics(composite(panel))

    results["global_normalisation"] = score_to_metrics(composite(panel, "global_zscore"))

    # cost model: zero (the classic flattering assumption) and punitive
    for mult, label in ((0.0, "zero_costs"), (3.0, "punitive_costs")):
        d, b, _ = backtest.run(cfg, base_scores[base_scores.index.get_level_values(0)
                                                >= pd.Timestamp(f"{y0}-01-01")],
                               close, vol, bench, cost_mult=mult)
        results[label] = backtest.metrics(d, b)

    # survivors only: keep names still in the index in the final year
    last_year = close.loc[f"{y1}"].dropna(axis=1, how="all").columns
    surv_panel = {f: df.reindex(columns=last_year) for f, df in panel.items()}
    results["survivors_only"] = score_to_metrics(composite(surv_panel))

    base = results["baseline"]
    out = {"baseline": base, "variants": {},
           "fundamentals_timing_bias_synthetic": fundamentals_timing_bias()}
    for k, v in results.items():
        if k == "baseline":
            continue
        out["variants"][k] = dict(
            excess_ann=v["excess_ann"], info_ratio=v["info_ratio"],
            excess_uplift_vs_baseline=v["excess_ann"] - base["excess_ann"],
            ir_uplift_vs_baseline=v["info_ratio"] - base["info_ratio"])
    (cfg.run_dir / "protocol_audit.json").write_text(json.dumps(out, indent=2, default=float))

    fb = out["fundamentals_timing_bias_synthetic"]
    log(f"{'protocol':24s} {'excess/yr':>10s} {'IR':>7s} {'uplift vs causal baseline':>26s}")
    log(f"{'baseline (causal)':24s} {base['excess_ann']:+10.2%} {base['info_ratio']:+7.2f} {'-':>26s}")
    for k, v in out["variants"].items():
        log(f"{k:24s} {v['excess_ann']:+10.2%} {v['info_ratio']:+7.2f} "
            f"{v['excess_uplift_vs_baseline']:+13.2%} / IR {v['ir_uplift_vs_baseline']:+.2f}")
    log(f"\nfundamentals timing (synthetic, {fb['reporting_lag_days']}-day reporting lag): "
        f"IC {fb['ic_filing_date_join']:.4f} joining on filing date vs "
        f"{fb['ic_period_end_join']:.4f} joining on period end "
        f"(+{fb['inflation']:.4f} of pure foresight)")
    return out
