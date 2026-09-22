"""Hierarchical testing: families first, then factors inside the survivors.

Testing 194 formulas at once means deflating against 194 trials. Testing 7
mechanism-family composites first means deflating against 7, and only the
families that clear that bar earn the right to a within-family search. Same
data, far less multiple-testing penalty - this is the most direct lever on a
Deflated Sharpe of ~0.9, and it costs nothing in compute.

The catch, stated plainly: this is only legitimate when the family definitions
and the composite rule are fixed **before** looking at the results. They are:
`families.classify` reads the AST, and the composite is an equal-weight blend
of the signed members. Nothing here is chosen after seeing performance.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .. import data, neff, stats
from ..config import Config
from ..evaluate import evaluate
from ..families import FAMILIES
from ..ledger import Ledger


def run(cfg: Config, log=print) -> dict:
    led = Ledger(cfg.run_dir / "ledger.csv", cfg=cfg)
    rows = [r for r in led.rows() if r["stage"] == "discover-eval" and r.get("expr")]
    if not rows:
        raise SystemExit("no evaluated candidates in the ledger - run `alphalab discover` first")
    end_valid = f"{cfg.splits.valid_years[-1]}-12-31"
    y = data.label(cfg, cfg.splits.discover_start, end_valid)
    disc_end = pd.Timestamp(cfg.splits.discover_end)
    step = cfg.trading.horizon

    # ---- stage A: one composite per mechanism family -------------------------
    members: dict[str, list] = {}
    for r in rows:
        fam = r.get("family") or "other"
        members.setdefault(fam, []).append(r)
    members = {f: m for f, m in members.items() if f in FAMILIES and len(m) >= 3}

    comps, per_family = {}, {}
    for fam, mem in members.items():
        exprs = [m["expr"] for m in mem]
        names = [f"{fam}__{i}" for i in range(len(mem))]
        signs = pd.Series({n: float(m["sign"] or 1) for n, m in zip(names, mem, strict=True)})
        F = data.features(cfg, exprs, names, cfg.splits.discover_start, end_valid)
        F = F.replace([np.inf, -np.inf], np.nan)
        comp = (data.cs_rank(F) * signs).sum(axis=1) / len(names)
        comps[fam] = comp
        per_family[fam] = dict(members=len(mem))

    C = pd.DataFrame(comps)
    IC, LS, _ = evaluate(C, y)
    n_families = len(members)
    ls_d = LS[LS.index <= disc_end].iloc[::step]
    sr_var = float(np.var([ls_d[f].mean() / ls_d[f].std() for f in ls_d if ls_d[f].std() > 0]))
    family_results = {}
    for fam in members:
        ic_d = IC[fam][IC.index <= disc_end]
        ic_l = IC[fam][IC.index > disc_end]
        t = stats.tstat(ic_d.iloc[::step])
        dsr, _, _ = stats.deflated_sharpe(ls_d[fam], n_families, sr_var)
        family_results[fam] = dict(
            **per_family[fam], ic_mean=float(ic_d.mean()), ic_t=float(t),
            ls_sharpe_ann=stats.sharpe(ls_d[fam], 52), dsr_family_level=float(dsr),
            later_ic=float(ic_l.mean()),
            passes=bool(t >= cfg.gates.t_stat_min and dsr >= cfg.gates.dsr_min))
        led.log(stage="hierarchy-family", name=f"family::{fam}", source="hierarchy",
                expr=f"equal-weight composite of {per_family[fam]['members']} members",
                ic_mean=round(float(ic_d.mean()), 5), ic_t=round(float(t), 2),
                dsr=round(float(dsr), 3), later_ic_mean=round(float(ic_l.mean()), 5),
                n_trials_at_eval=n_families,
                status="passed" if family_results[fam]["passes"] else "rejected",
                reason=f"family-level test against N={n_families}")

    survivors = [f for f, v in family_results.items() if v["passes"]]
    log(f"stage A: {n_families} family composites tested against N={n_families}; "
        f"{len(survivors)} passed ({', '.join(survivors) or 'none'})")

    # ---- stage B: within-family search, deflated against that family only ----
    stage_b = {}
    for fam in survivors:
        mem = members[fam]
        n_in_family = len(mem)
        exprs = [m["expr"] for m in mem]
        names = [f"{fam}__{i}" for i in range(len(mem))]
        F = data.features(cfg, exprs, names, cfg.splits.discover_start, end_valid)
        _, LSf, _ = evaluate(F.replace([np.inf, -np.inf], np.nan), y)
        lsf = LSf[LSf.index <= disc_end].iloc[::step]
        srv = float(np.var([lsf[n].mean() / lsf[n].std() for n in lsf if lsf[n].std() > 0]))
        best = None
        for n, m in zip(names, mem, strict=True):
            if n not in lsf:
                continue
            sgn = float(m["sign"] or 1)
            dsr, _, _ = stats.deflated_sharpe(lsf[n] * sgn, n_in_family, srv)
            dsr_flat, _, _ = stats.deflated_sharpe(lsf[n] * sgn, len(rows), srv)
            if best is None or dsr > best["dsr_within_family"]:
                best = dict(name=m["name"], expr=m["expr"], dsr_within_family=float(dsr),
                            dsr_same_factor_flat_N=float(dsr_flat),
                            ic_t=float(m["ic_t"]), n_in_family=n_in_family)
        stage_b[fam] = best
        if best:
            log(f"stage B [{fam}]: best is {best['name']} - same factor scores DSR "
                f"{best['dsr_within_family']:.3f} against N={n_in_family} vs "
                f"{best['dsr_same_factor_flat_N']:.3f} against the flat N={len(rows)}")

    # ---- effective-trials diagnostics ---------------------------------------
    trials_report = neff.report(C, n_raw=len(rows))
    out = dict(n_flat_trials=len(rows), n_family_trials=n_families,
               families=family_results, survivors=survivors, best_within_family=stage_b,
               effective_trials=trials_report)
    (cfg.run_dir / "hierarchy.json").write_text(json.dumps(out, indent=2, default=float))
    log(json.dumps(trials_report, indent=2))
    return out
