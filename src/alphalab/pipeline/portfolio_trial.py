"""TRIAL - what the institutional portfolio-construction layer adds.

Same alpha, six books, one validation window. Each step is a practice that
professional equity books take for granted and hobby backtests skip:
banding, style neutralisation, volatility-scaled weights, dollar-neutral
long/short, participation caps and market impact. Then a capacity curve."""
from __future__ import annotations

import json

import pandas as pd

from .. import backtest, data, risk
from ..config import Config
from ..portfolio import BookSpec, capacity_curve, run_book
from . import model as M

CONFIGS = {
    "1_naive_topk_equal": dict(mode="long_only", band=0.0, neutralise=False),
    "2_plus_bands": dict(mode="long_only", band=0.25, neutralise=False),
    "3_plus_neutralised_alpha": dict(mode="long_only", band=0.25, neutralise=True),
    "4_plus_vol_scaled_weights": dict(mode="long_only", band=0.25, neutralise=True, vol_scale=True),
    "5_market_neutral_long_short": dict(mode="market_neutral", band=0.25, neutralise=False),
    "6_market_neutral_full": dict(mode="market_neutral", band=0.25, neutralise=True, vol_scale=True),
}


def run(cfg: Config, capital: float = 1e6, log=print) -> dict:
    choice_file = cfg.run_dir / "model_choice.json"
    chosen = json.loads(choice_file.read_text())["chosen"] if choice_file.exists() else "A_hypothesis_composite"
    I = M.build_inputs(cfg)
    V = M.variants(cfg, I, lambda *_: None)
    if chosen not in V:
        chosen = next(iter(V))
    log(f"alpha source: {chosen}")
    scores = V[chosen](list(cfg.splits.valid_years))

    close, vol = data.price_panel(cfg)
    bench = data.benchmark_close(cfg)
    adv = data.adv_panel(cfg)
    expos = risk.exposures(close, vol, bench)
    sv = risk.specific_vol(close, bench)
    neutral_scores = risk.neutralise(scores, expos)

    # --- diagnostic: how much of the "alpha" is just style exposure? -----------
    def _ic(sig):
        d = pd.concat([sig.rename("s"), I["y_raw"].reindex(sig.index).rename("y")], axis=1).dropna()
        return float(d.groupby(level=0).apply(lambda g: g.s.rank().corr(g.y.rank())).mean())
    style = {f: float(scores.corr(expos[f].stack().reindex(scores.index)))
             for f in ("beta", "size", "vol", "mom")}
    ic_raw, ic_neutral = _ic(scores), _ic(neutral_scores)
    log(f"raw IC {ic_raw:.4f} -> style-neutral IC {ic_neutral:.4f} "
        f"({1 - ic_neutral / ic_raw:.0%} of the signal was style exposure)")
    log("  alpha vs style: " + ", ".join(f"{k}={v:+.2f}" for k, v in style.items()))

    rows, curves = [], {}
    for name, opts in CONFIGS.items():
        spec = BookSpec(capital=capital, mode=opts["mode"], band=opts["band"])
        sc = neutral_scores if opts["neutralise"] else scores
        d, b, diag = run_book(cfg, sc, close, vol, bench, spec,
                              spec_vol=sv if opts.get("vol_scale") else None, adv=adv)
        m = backtest.metrics(d, b)
        rows.append(dict(config=name, **{k: round(v, 4) for k, v in m.items() if isinstance(v, float)},
                         **{k: round(v, 4) for k, v in diag.items()}))
        curves[name] = d
        # a market-neutral book's benchmark is cash, not the index: judge it on
        # absolute return/Sharpe. Judging it on "excess vs a falling index" flatters it.
        head = (f"return/yr={m['cagr']:+.2%} Sharpe={m['sharpe']:+.2f} (vs cash)"
                if opts["mode"] == "market_neutral"
                else f"excess/yr={m['excess_ann']:+.2%} IR={m['info_ratio']:+.2f} (vs index)")
        log(f"  {name:28s} {head:42s} maxDD={m['max_dd']:.1%} "
            f"turnover/rebal={diag['turnover_per_rebalance']:.0%} impact={diag['impact_cost_ann']:.2%}/yr")
    table = pd.DataFrame(rows)
    # score each book against its own benchmark: index for long-only, cash for neutral
    table["headline_ratio"] = [r["info_ratio"] if CONFIGS[r["config"]]["mode"] == "long_only"
                               else r["sharpe"] for r in rows]
    best = table.sort_values("headline_ratio", ascending=False).iloc[0]["config"]
    log(f"best by IR: {best}")

    caps = [1e5, 1e6, 1e7, 1e8, 1e9, 1e10]
    spec = BookSpec(capital=capital, mode=CONFIGS[best]["mode"], band=CONFIGS[best]["band"])
    cap_df = capacity_curve(cfg, neutral_scores if CONFIGS[best]["neutralise"] else scores,
                            close, vol, bench, spec, caps,
                            spec_vol=sv if CONFIGS[best].get("vol_scale") else None, adv=adv)
    cap_df["faithful"] = cap_df["share_trades_capped"] < 0.2   # above this the caps
    # change the strategy itself, so those rows are not the same book any more
    log("\ncapacity curve (" + best + ")")
    log(cap_df.assign(capital=lambda d: d.capital.map(lambda x: f"{x:,.0f}"))[
        ["capital", "excess_ann", "info_ratio", "impact_cost_ann", "share_trades_capped", "faithful"]]
        .round(4).to_string(index=False))

    crowd = risk.crowding_r2(close.loc["2020":], vol.loc["2020":], expos)
    out = dict(alpha_source=chosen, capital=capital, configs=rows, best=best,
               style_diagnostic=dict(ic_raw=ic_raw, ic_style_neutral=ic_neutral,
                                     share_of_signal_from_style=1 - ic_neutral / ic_raw,
                                     alpha_vs_style=style),
               capacity=cap_df.to_dict("records"),
               crowding_r2_last=float(crowd.dropna().iloc[-1]) if not crowd.dropna().empty else None,
               crowding_r2_max=float(crowd.max()) if not crowd.dropna().empty else None)
    (cfg.run_dir / "portfolio_trial.json").write_text(json.dumps(out, indent=2, default=float))
    table.to_csv(cfg.run_dir / "portfolio_trial.csv", index=False)
    pd.DataFrame(curves).to_csv(cfg.run_dir / "portfolio_trial_returns.csv")
    cap_df.to_csv(cfg.run_dir / "capacity_curve.csv", index=False)
    crowd.to_csv(cfg.run_dir / "crowding_r2.csv")
    return out
