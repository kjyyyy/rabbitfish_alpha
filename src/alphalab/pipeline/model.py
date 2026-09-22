"""STAGE 2 - pre-registered strategy variants, walk-forward on the validation
years, then the holdout. If `splits.holdout_burned` is true, holdout numbers
are reported as descriptive only and can never raise a strategy's claim tier."""
from __future__ import annotations

import json

import lightgbm as lgb
import numpy as np
import pandas as pd

from .. import backtest, card, data
from ..config import Config
from ..evaluate import evaluate
from ..factors.hypotheses import HYPOTHESES
from ..families import classify
from ..ledger import Ledger
from ..ledger import Ledger as _Ledger
from ..library import Library, combine, dynamic_weights
from ..regime import label_regimes


def _sl(df, a, b):
    d = df.index.get_level_values(0)
    return df[(d >= pd.Timestamp(a)) & (d <= pd.Timestamp(b))]


def fold_dates(cfg: Config, cal: pd.DatetimeIndex, year: int):
    t0 = pd.Timestamp(f"{year}-01-01")
    v0, v1 = pd.Timestamp(f"{year - 1}-01-01"), pd.Timestamp(f"{year - 1}-12-31")
    tr0 = pd.Timestamp(f"{year - 1 - cfg.model.train_years}-01-01")
    p = cfg.model.purge_days
    return (tr0, cal[cal < v0][-p - 1]), (v0, min(v1, cal[cal < t0][-p - 1])), (t0, pd.Timestamp(f"{year}-12-31"))


def lgbm_walk_forward(cfg: Config, X, y, years, cal, log):
    out, rounds = [], []
    for Y in years:
        (a, b), (c, d), (e, f) = fold_dates(cfg, cal, Y)
        Xtr, ytr, Xv, yv, Xte = _sl(X, a, b), _sl(y, a, b), _sl(X, c, d), _sl(y, c, d), _sl(X, e, f)
        m, mv = ytr.notna(), yv.notna()
        dtr = lgb.Dataset(Xtr[m].values, ytr[m].values)
        dv = lgb.Dataset(Xv[mv].values, yv[mv].values, reference=dtr)
        bst = lgb.train(cfg.model.lgbm_params, dtr, cfg.model.lgbm_rounds, valid_sets=[dv],
                        callbacks=[lgb.early_stopping(cfg.model.lgbm_early_stop, verbose=False)])
        rounds.append(bst.best_iteration)
        out.append(pd.Series(bst.predict(Xte.values), index=Xte.index))
        log(f"    fold {Y}: train {a.date()}..{b.date()} valid {c.date()}..{d.date()} rounds={bst.best_iteration}")
    return pd.concat(out), rounds


def horizon_label(cfg: Config, h: int, start: str):
    expr = f"Ref($close, -{h + 1}) / Ref($close, -1) - 1"
    y = data.features(cfg, [expr], ["label"], start, cfg.splits.data_end)["label"]
    return data.cs_rank(y.to_frame())["label"].where(y.notna())


def family_composites(cfg: Config, start: str, families: list[str]):
    """Equal-weight composite of every evaluated member of a family (the same
    rule the hierarchical test used - nothing is re-picked on performance)."""
    rows = [r for r in _Ledger(cfg.run_dir / "ledger.csv", cfg=cfg).rows()
            if r["stage"] == "discover-eval" and r.get("expr")]
    out = {}
    for fam in families:
        mem = [r for r in rows if (r.get("family") or classify(r["expr"])) == fam]
        if len(mem) < 3:
            continue
        names = [f"{fam}__{i}" for i in range(len(mem))]
        signs = pd.Series({n: float(m["sign"] or 1) for n, m in zip(names, mem, strict=True)})
        F = data.features(cfg, [m["expr"] for m in mem], names, start, cfg.splits.data_end)
        out[fam] = (data.cs_rank(F.replace([np.inf, -np.inf], np.nan)) * signs).sum(axis=1) / len(names)
    return out


def shrinkage_weights(ic: pd.DataFrame, horizon: int, lookback: int):
    """Ledoit-Wolf shrunk covariance of factor ICs -> weights ~ Sigma^-1 * mean IC,
    computed only from ICs whose labels were already realised."""
    from sklearn.covariance import LedoitWolf
    lagged = ic.shift(horizon + 1)
    w = {}
    for i in range(lookback, len(lagged), 20):          # refit monthly
        win = lagged.iloc[i - lookback:i].dropna(axis=1, how="all").dropna()
        if len(win) < 40 or win.shape[1] < 2:
            continue
        lw = LedoitWolf().fit(win.values)
        mu = win.mean().values
        try:
            raw = np.linalg.solve(lw.covariance_ + np.eye(len(mu)) * 1e-10, mu)
        except np.linalg.LinAlgError:
            continue
        v = pd.Series(raw, index=win.columns)
        v = v.clip(-v.abs().quantile(0.9) * 3, v.abs().quantile(0.9) * 3)
        w[lagged.index[i]] = v / v.abs().sum()
    return pd.DataFrame(w).T.reindex(columns=ic.columns).fillna(0.0)


def build_inputs(cfg: Config):
    years = list(cfg.splits.valid_years) + list(cfg.splits.holdout_years)
    start = f"{min(years) - 2 - cfg.model.train_years}-01-01"
    y_raw = data.label(cfg, start, cfg.splits.data_end)
    y = data.cs_rank(y_raw.to_frame())["label"].where(y_raw.notna())
    H = data.features(cfg, [h["expr"] for h in HYPOTHESES], [h["name"] for h in HYPOTHESES],
                      start, cfg.splits.data_end).replace([np.inf, -np.inf], np.nan)
    Hr = data.cs_rank(H)
    lib = Library(cfg.run_dir / "library.json")
    members = lib.members()
    if members:
        L = data.features(cfg, [m["expr"] for m in members], [m["name"] for m in members],
                          start, cfg.splits.data_end).replace([np.inf, -np.inf], np.nan)
        Lr = data.cs_rank(L)
        signs = pd.Series({m["name"]: m["sign"] for m in members})
        L_ic, _, _ = evaluate(L, y_raw)
    else:
        Lr, signs, L_ic = None, None, None
    hier = cfg.run_dir / "hierarchy.json"
    survivors = json.loads(hier.read_text())["survivors"] if hier.exists() else []
    comps = family_composites(cfg, start, survivors) if survivors else {}
    return dict(start=start, y_raw=y_raw, y=y, H=H, Hr=Hr, Lr=Lr, lib_signs=signs, L_ic=L_ic,
                family_comps=comps, survivors=survivors,
                cal=y_raw.index.get_level_values(0).unique().sort_values())


def variants(cfg: Config, I: dict, log):
    hsign = pd.Series({h["name"]: h["sign"] for h in HYPOTHESES})
    V = {}
    V["A_hypothesis_composite"] = lambda yrs: _sl(
        (I["Hr"] * hsign).sum(axis=1) / len(hsign), f"{yrs[0]}-01-01", f"{yrs[-1]}-12-31")
    V["C_lgbm_hypotheses"] = lambda yrs: lgbm_walk_forward(cfg, I["Hr"], I["y"], yrs, I["cal"], log)[0]
    if I["Lr"] is not None:
        def dyn(yrs):
            w = dynamic_weights(I["L_ic"], I["lib_signs"], cfg.trading.horizon,
                                cfg.model.combiner_lookback_days, cfg.model.combiner_shrink)
            sc = combine(I["Lr"], w)
            return _sl(sc, f"{yrs[0]}-01-01", f"{yrs[-1]}-12-31")
        V["E_library_dynamic_ic"] = dyn
        HL = I["Hr"].join(I["Lr"] * I["lib_signs"], rsuffix="_lib")
        V["F_lgbm_hypotheses_plus_library"] = lambda yrs: lgbm_walk_forward(cfg, HL, I["y"], yrs, I["cal"], log)[0]

        def shrunk(yrs):
            w = shrinkage_weights(I["L_ic"], cfg.trading.horizon, cfg.model.combiner_lookback_days)
            return _sl(combine(I["Lr"], w), f"{yrs[0]}-01-01", f"{yrs[-1]}-12-31")
        V["G_library_ledoit_wolf"] = shrunk
    if I["family_comps"]:
        comp = sum(I["family_comps"].values()) / len(I["family_comps"])
        V["H_family_composite"] = lambda yrs: _sl(comp, f"{yrs[0]}-01-01", f"{yrs[-1]}-12-31")

    def horizons(yrs):
        preds = []
        for h in (1, 5, 10):
            yh = horizon_label(cfg, h, I["start"])
            p = lgbm_walk_forward(cfg, I["Hr"], yh, yrs, I["cal"], lambda *_: None)[0]
            preds.append(p.groupby(level=0).rank(pct=True))
        return sum(preds) / len(preds)
    V["I_horizon_ensemble"] = horizons
    return V


def run(cfg: Config, log=print) -> dict:
    from .. import governance
    governance.write_register(cfg)          # assumptions are recorded with every run
    ledger = Ledger(cfg.run_dir / "ledger.csv", cfg=cfg)
    I = build_inputs(cfg)
    V = variants(cfg, I, log)
    close, vol = data.price_panel(cfg)
    bench = data.benchmark_close(cfg)
    regimes = label_regimes(bench)
    s1 = json.loads((cfg.run_dir / "discover_summary.json").read_text()) \
        if (cfg.run_dir / "discover_summary.json").exists() else {}
    llm_n = sum(1 for m in Library(cfg.run_dir / "library.json").members() if m["source"] == "llm")

    def evaluate_scores(sc, mult=1.0):
        d, b, to = backtest.run(cfg, sc, close, vol, bench, cost_mult=mult)
        m = backtest.metrics(d, b)
        ic = sc.groupby(level=0).apply(lambda s: s.rank().corr(I["y_raw"].reindex(s.index).rank())).mean()
        m.update(rank_ic=float(ic), weekly_turnover=to)
        return m, d, b

    results, curves, scores_valid = {}, {}, {}
    for name, fn in V.items():
        log(f"[validation] {name}")
        sc = fn(list(cfg.splits.valid_years))
        scores_valid[name] = sc
        m, d, b = evaluate_scores(sc)
        m2, _, _ = evaluate_scores(sc, 2.0)
        m["info_ratio_2x_costs"], m["excess_ann_2x_costs"] = m2["info_ratio"], m2["excess_ann"]
        results[name] = {"validation": m}
        curves[f"{name}|valid"], curves["benchmark|valid"] = d, b
        ledger.log(stage="model-valid", name=name, source="model", status="evaluated",
                   ls_sharpe_ann=round(m["info_ratio"], 3), reason=json.dumps(
                       {k: round(v, 4) for k, v in m.items() if isinstance(v, float)}))
        log("    " + json.dumps({k: round(v, 3) for k, v in m.items() if isinstance(v, float)}))

    chosen = max(results, key=lambda k: results[k]["validation"]["info_ratio_2x_costs"])
    (cfg.run_dir / "model_choice.json").write_text(json.dumps(
        {"chosen": chosen, "rule": "max validation information ratio at 2x costs",
         "holdout_burned": cfg.splits.holdout_burned}, indent=2))
    log(f"CHOSEN by pre-registered rule: {chosen}")

    for name, fn in V.items():
        log(f"[holdout{' - DESCRIPTIVE ONLY (burned)' if cfg.splits.holdout_burned else ''}] {name}")
        m, d, b = evaluate_scores(fn(list(cfg.splits.holdout_years)))
        results[name]["holdout"] = m
        curves[f"{name}|holdout"], curves["benchmark|holdout"] = d, b
        log("    " + json.dumps({k: round(v, 3) for k, v in m.items() if isinstance(v, float)}))

    # ---- validity cards --------------------------------------------------------
    n_model_trials = len({r["name"] for r in ledger.rows() if r["stage"] == "model-valid"})
    ex_srs = [(curves[f"{n}|valid"] - curves["benchmark|valid"].reindex(curves[f"{n}|valid"].index))
              for n in V]
    sr_var = float(np.var([e.mean() / e.std() for e in ex_srs]))
    fwd = _forward_stats(cfg)
    cards = {}
    for name in V:
        sc = scores_valid[name]
        run_fn = (lambda mult, sc=sc: backtest.metrics(*backtest.run(cfg, sc, close, vol, bench, mult)[:2])["excess_ann"])
        c = card.build(cfg, name, curves[f"{name}|valid"],
                       curves["benchmark|valid"].reindex(curves[f"{name}|valid"].index),
                       n_model_trials, sr_var, s1, regimes, run_fn,
                       forward_weeks=fwd.get("weeks", 0) if name == chosen else 0,
                       forward_ir=fwd.get("ir") if name == chosen else None,
                       llm_sources=llm_n if "library" in name else 0)
        c["holdout"] = dict(descriptive_only=cfg.splits.holdout_burned,
                            **{k: round(v, 4) if isinstance(v, float) else v
                               for k, v in results[name]["holdout"].items()})
        cards[name] = c
    (cfg.run_dir / "cards.json").write_text(json.dumps(cards, indent=2, default=float))
    (cfg.run_dir / "CARDS.md").write_text("# Validity cards\n\n" + "\n".join(
        card.to_markdown(c) for c in cards.values()))
    (cfg.run_dir / "model_results.json").write_text(json.dumps(results, indent=2))
    pd.DataFrame(curves).to_csv(cfg.run_dir / "daily_returns.csv")

    from ..provenance import write_snapshot
    ch = results.get(chosen, {})
    cc = cards.get(chosen, {})
    snap = write_snapshot(cfg, dict(
        chosen=chosen,
        validation=ch.get("validation", {}),
        holdout=ch.get("holdout", {}),
        claim_tier=cc.get("tier"),
        checks_failed=[k for k, v in cc.get("checks", {}).items() if not v.get("ok")],
        forward_weeks=fwd.get("weeks", 0),
        n_model_trials=n_model_trials,
        discovery_trials=s1.get("n_trials_total"),
        hurdle_sharpe_ann=s1.get("hurdle_sharpe_ann")))
    print(f"snapshot written: {snap}")
    return results


def _forward_stats(cfg: Config) -> dict:
    p = cfg.run_dir / "forward" / "evaluations.csv"
    if not p.exists() or p.stat().st_size == 0:
        return {}
    try:
        e = pd.read_csv(p)
    except pd.errors.EmptyDataError:                  # written before any clean week
        return {}
    if e.empty or "excess" not in e:
        return {}
    ex = e["excess"]
    return dict(weeks=int(len(e)), ir=float(ex.mean() / ex.std() * np.sqrt(52)) if len(e) > 2 else None)
