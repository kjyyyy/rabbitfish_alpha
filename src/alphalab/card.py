"""Validity card: an automatic, per-strategy evidence summary mapped to the
claim levels of 'The Alpha Illusion' (Ye et al., arXiv:2605.16895, 2026).

Claim levels (what you are allowed to say):
  research-aid          - an idea worth more research; no performance claim
  historical-backtest   - P1 temporal integrity + P2 point-in-time universe + P5 costs,
                          and it survives multiple-testing and an unseen holdout
  forward-evidence      - the above, plus >= 13 weeks of pre-registered forward signals
The card never upgrades a claim on its own judgement; every rule is below."""
from __future__ import annotations

import math

import pandas as pd

from . import backtest, stats
from .regime import breakdown

MCLEAN_PONTIFF_POST_PUB_DECAY = 0.58   # returns 58% lower post-publication (JF 2016)
MIN_FORWARD_WEEKS = 13


def sharpe_se(daily: pd.Series, periods=244) -> float:
    sr = daily.mean() / daily.std()
    return float(math.sqrt((1 + 0.5 * sr ** 2) / len(daily)) * math.sqrt(periods))


def break_even_cost_bp(run_fn, one_way_bp: float) -> float | None:
    """One-way cost (bp) at which annual excess return hits zero (bisection)."""
    lo, hi = 0.0, 20.0
    if run_fn(lo) <= 0:
        return 0.0
    if run_fn(hi) > 0:
        return None
    for _ in range(12):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if run_fn(mid) > 0 else (lo, mid)
    return round(lo * one_way_bp, 1)


def build(cfg, name, valid_daily, valid_bench, n_model_trials, sr_var_models,
          stage1_summary, regimes, run_fn, forward_weeks=0, forward_ir=None,
          llm_sources=0) -> dict:
    ex = valid_daily - valid_bench
    m = backtest.metrics(valid_daily, valid_bench)
    dsr, sr, sr0 = stats.deflated_sharpe(ex, max(n_model_trials, 2), sr_var_models)
    c = cfg.market.costs
    one_way_bp = (c.commission + c.slippage + (c.stamp_buy + c.stamp_sell) / 2) * 1e4

    p1 = cfg.model.purge_days > cfg.trading.horizon and not (
        llm_sources and (cfg.llm.training_cutoff or "9999") >= cfg.splits.discover_start)
    p2 = cfg.market.point_in_time_universe
    p5 = True
    holdout_clean = not cfg.splits.holdout_burned
    checks = {
        "P1_temporal_integrity": dict(ok=p1, detail=(
            f"purge {cfg.model.purge_days}d > horizon {cfg.trading.horizon}d; "
            + ("LLM-proposed factors present and the model's training cutoff overlaps the "
               "discovery window -> only post-cutoff/forward data is clean" if llm_sources else
               "no LLM-proposed factors"))),
        "P2_point_in_time_universe": dict(ok=p2, detail=cfg.market.survivorship_note or
                                          "point-in-time index membership"),
        "P5_costs_modelled": dict(ok=p5, detail=f"~{one_way_bp:.0f}bp one-way incl. stamp; "
                                                 f"2x-cost run reported"),
        "multiple_testing_DSR": dict(ok=dsr >= cfg.gates.dsr_min, value=round(dsr, 3),
                                     detail=f"{n_model_trials} model variants tried"),
        "holdout_clean": dict(ok=holdout_clean, detail="holdout already seen -> descriptive only"
                              if not holdout_clean else "holdout unseen"),
        "forward_evidence": dict(ok=forward_weeks >= MIN_FORWARD_WEEKS and (forward_ir or 0) > 0,
                                 detail=f"{forward_weeks} pre-registered weeks"),
    }
    if checks["forward_evidence"]["ok"] and p1 and p2 and checks["multiple_testing_DSR"]["ok"]:
        tier = "forward-evidence"
    elif p1 and p2 and p5 and checks["multiple_testing_DSR"]["ok"] and holdout_clean:
        tier = "historical-backtest"
    else:
        tier = "research-aid"
    allowed = {
        "research-aid": "An idea worth further research. No performance claim is supported.",
        "historical-backtest": "Survived point-in-time, cost-aware, multiple-testing-adjusted "
                               "backtesting and an unseen holdout. Not evidence of live performance.",
        "forward-evidence": "Backtest plus pre-registered forward signals support a small, "
                            "risk-limited live trial.",
    }[tier]
    from . import governance
    exc = governance.exceptions(cfg)
    checks["protocol_exceptions"] = dict(
        ok=len(exc) == 0,
        detail=("no logged deviations from the standard protocol" if not exc else
                f"{len(exc)} logged deviation(s): " + "; ".join(e["kind"] for e in exc[:3])))
    return dict(
        strategy=name, tier=tier, allowed_claim=allowed, checks=checks,
        stats=dict(**{k: round(v, 4) if isinstance(v, float) else v for k, v in m.items()},
                   sharpe_se=round(sharpe_se(valid_daily), 3),
                   sharpe_95ci=[round(m["sharpe"] - 1.96 * sharpe_se(valid_daily), 2),
                                round(m["sharpe"] + 1.96 * sharpe_se(valid_daily), 2)],
                   dsr=round(dsr, 3),
                   break_even_one_way_bp=break_even_cost_bp(run_fn, one_way_bp),
                   excess_after_decay_haircut=round(m["excess_ann"] * (1 - MCLEAN_PONTIFF_POST_PUB_DECAY), 4)),
        regimes=breakdown(ex, regimes),
        discovery=dict(n_trials=stage1_summary.get("n_trials_total"),
                       pbo=stage1_summary.get("pbo")),
    )


def to_markdown(card: dict) -> str:
    s = card["stats"]
    lines = [f"### {card['strategy']}  -  tier: **{card['tier']}**", "",
             f"> {card['allowed_claim']}", "",
             "| Check | OK | Detail |", "|---|---|---|"]
    for k, v in card["checks"].items():
        lines.append(f"| {k} | {'yes' if v['ok'] else 'NO'} | {v.get('detail', '')} "
                     f"{'(' + str(v['value']) + ')' if 'value' in v else ''}|")
    lines += ["", f"Validation: excess {s['excess_ann']:+.1%}/yr, IR {s['info_ratio']:.2f}, "
              f"Sharpe {s['sharpe']:.2f} (95% CI {s['sharpe_95ci'][0]} to {s['sharpe_95ci'][1]}), "
              f"max DD {s['max_dd']:.1%}, DSR {s['dsr']}, break-even cost "
              f"{s['break_even_one_way_bp']} bp one-way, excess after 58% decay haircut "
              f"{s['excess_after_decay_haircut']:+.1%}/yr.", ""]
    if card["regimes"]:
        lines.append("Regime breakdown (excess/yr): " + ", ".join(
            f"{k} {v['excess_ann']:+.1%}" for k, v in card["regimes"].items()))
    return "\n".join(lines) + "\n"
