"""STAGE 1 - discover, refine and gate candidate factors on the DISCOVERY window.

Sources: written hypotheses, LLM proposals (runs/<name>/llm_candidates.jsonl),
a random grammar, and a GP refiner seeded with the best of those. Every
candidate is parsed (AST whitelist), capped for complexity, checked for
originality against the zoo, evaluated, and logged. Later-period IC is
reported for decay analysis but never used for selection."""
from __future__ import annotations

import hashlib
import json
import pickle
import random

import numpy as np
import pandas as pd

from .. import data, stats
from .. import expr as E
from .. import memory as mem_mod
from ..config import Config
from ..evaluate import evaluate
from ..factors.hypotheses import HYPOTHESES
from ..factors.zoo import alpha158_exprs
from ..families import classify, diagnostics
from ..leakage import future_noise_test, numerical_checks
from ..ledger import Ledger
from ..library import Library
from ..logging_setup import progress
from ..miners.gp import fitness, next_generation
from ..scheduler import FamilyBandit


def _load_llm(cfg: Config):
    p = cfg.run_dir / "llm_candidates.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        c = json.loads(line)
        if c.get("status", "ok") == "ok":
            out.append(dict(c, source="llm"))
    return out


def _screen(cfg: Config, cands, zoo, ledger, seen):
    ok = []
    g = cfg.gates
    for c in cands:
        try:
            fp = E.fingerprint(c["expr"])
            cx = E.complexity(c["expr"])
        except E.ExprError as e:
            ledger.log(stage="discover-reject", name=c["name"], source=c["source"], expr=c["expr"],
                       rationale=c.get("rationale", ""), status="rejected", reason=f"parse: {e}",
                       source_model=c.get("source_model", ""), prompt_sha=c.get("prompt_sha", ""))
            continue
        if fp in seen:
            continue
        seen.add(fp)
        reason = []
        if cx.nodes > g.max_nodes:
            reason.append(f"nodes {cx.nodes}>{g.max_nodes}")
        if cx.raw_fields > g.max_raw_fields:
            reason.append(f"fields {cx.raw_fields}>{g.max_raw_fields}")
        if cx.constants > g.max_constants:
            reason.append(f"constants {cx.constants}>{g.max_constants}")
        ok_leak, why_leak = future_noise_test(c["expr"])
        if not ok_leak:
            ledger.log(stage="discover-reject", name=c["name"], source=c["source"], expr=c["expr"],
                       fingerprint=fp, nodes=cx.nodes, rationale=c.get("rationale", ""),
                       status="rejected", reason=f"dynamic leakage: {why_leak}",
                       parent_id=c.get("parent_id", ""), source_model=c.get("source_model", ""))
            continue
        overlap = zoo.overlap(c["expr"])
        if c["source"] != "hypothesis" and overlap > g.max_zoo_overlap:
            reason.append(f"zoo overlap {overlap}>{g.max_zoo_overlap}")
        if reason:
            ledger.log(stage="discover-reject", name=c["name"], source=c["source"], expr=c["expr"],
                       fingerprint=fp, nodes=cx.nodes, zoo_overlap=overlap, family=classify(c["expr"]),
                       rationale=c.get("rationale", ""), status="rejected", reason="; ".join(reason),
                       parent_id=c.get("parent_id", ""), source_model=c.get("source_model", ""),
                       prompt_sha=c.get("prompt_sha", ""))
            continue
        ok.append(dict(c, fingerprint=fp, nodes=cx.nodes, zoo_overlap=overlap,
                       family=classify(c["expr"])))
    return ok


def _eval_cache_path(cfg: Config, fp: str, end_valid: str):
    # v2: rows carry inner-holdout metrics, so v1 entries must be recomputed
    key = f"v2|{cfg.market.universe}|{cfg.splits.discover_start}|{end_valid}|{fp}"
    return cfg.cache_dir / ("eval_" + hashlib.md5(key.encode()).hexdigest()[:16] + ".pkl")


def _evaluate(cfg: Config, cands, y, end_valid):
    step = cfg.trading.horizon
    disc_end = pd.Timestamp(cfg.splits.discover_end)
    inner_end = pd.Timestamp(cfg.splits.inner_end)
    purge = pd.Timedelta(days=cfg.model.purge_days)
    rows, LS_all, rejected_numeric = [], {}, []
    todo = []
    for c in cands:                      # serve what has already been evaluated
        p = _eval_cache_path(cfg, c["fingerprint"], end_valid)
        if p.exists():
            cached = pickle.loads(p.read_bytes())
            if cached.get("rejected"):
                rejected_numeric.append((c, cached["rejected"]))
            else:
                rows.append(dict(c, **cached["row"]))
                LS_all[c["name"]] = cached["ls_raw"]
        else:
            todo.append(c)
    if len(cands) - len(todo):
        print(f"  {len(cands) - len(todo)}/{len(cands)} served from the evaluation cache")
    hb = progress("evaluate", total=len(todo), every=40)
    hb.__enter__() if todo else None
    for i in range(0, len(todo), 40):
        chunk = todo[i:i + 40]
        F = data.features(cfg, [c["expr"] for c in chunk], [c["name"] for c in chunk],
                          cfg.splits.discover_start, end_valid)
        F = F.replace([np.inf, -np.inf], np.nan)
        IC, LS, PIC = evaluate(F, y)
        for c in chunk:
            n = c["name"]
            if n not in IC or IC[n].dropna().empty or len(LS[n].dropna()) < 100:
                continue     # not enough history to evaluate honestly
            ok_num, why_num = numerical_checks(F[n])   # Series: structural NaNs excluded
            if not ok_num:
                rejected_numeric.append((c, why_num))
                _eval_cache_path(cfg, c["fingerprint"], end_valid).write_bytes(
                    pickle.dumps({"rejected": why_num}))
                continue
            ic_d = IC[n][IC.index <= disc_end]
            ic_l = IC[n][IC.index > disc_end]
            # inner split, entirely inside the discovery window:
            #   train slice  -> what the allocator is allowed to learn from
            #   holdout slice -> what it is rewarded on (purged)
            ic_in = IC[n][IC.index <= inner_end]
            ic_io = IC[n][(IC.index > inner_end + purge) & (IC.index <= disc_end)]
            ls = LS[n][LS.index <= disc_end].iloc[::step]
            raw_mean = ic_d.mean()
            sign = c["sign"] if c.get("sign") in (1, -1) else (1 if raw_mean >= 0 else -1)
            # the reward sign must not be chosen using the inner holdout
            sign_r = c["sign"] if c.get("sign") in (1, -1) else (1 if ic_in.mean() >= 0 else -1)
            io = ic_io.iloc[::step]
            LS_all[n] = ls
            row = dict(sign=sign, ic_mean=float(raw_mean * sign),
                             ic_t=float(stats.tstat(ic_d.iloc[::step]) * sign),
                             ls=ls * sign, ls_sharpe_ann=stats.sharpe(ls * sign, 52),
                             later_ic_mean=float(ic_l.mean() * sign),
                             inner_oos_ic=float(ic_io.mean() * sign_r) if len(ic_io) else float("nan"),
                             inner_oos_t=float(stats.tstat(io) * sign_r) if len(io) > 5 else float("nan"),
                             pearson_ic=float(PIC[n][PIC.index <= disc_end].mean() * sign),
                       wrong_sign=(c.get("sign") in (1, -1) and raw_mean * c["sign"] < 0))
            rows.append(dict(c, **row))
            _eval_cache_path(cfg, c["fingerprint"], end_valid).write_bytes(
                pickle.dumps({"row": row, "ls_raw": ls}))
        hb.tick(len(chunk), rejected=len(rejected_numeric))
    if todo:
        hb.__exit__(None, None, None)
    return rows, LS_all, rejected_numeric


def run(cfg: Config, gp: bool = True) -> dict:
    ledger = Ledger(cfg.run_dir / "ledger.csv", cfg=cfg)
    lib = Library(cfg.run_dir / "library.json")
    zoo = E.Zoo(alpha158_exprs() + [v["expr"] for v in lib.items.values()])
    rng = random.Random(cfg.mining.seed)
    end_valid = f"{cfg.splits.valid_years[-1]}-12-31"
    y = data.label(cfg, cfg.splits.discover_start, end_valid)

    cands = [dict(h, source="hypothesis") for h in HYPOTHESES] + _load_llm(cfg)
    k = 0
    while k < cfg.mining.n_random:
        e = E.random_expr(rng)
        cands.append(dict(name=f"rnd_{k:03d}", expr=e, sign=0, source="random",
                          rationale="random grammar (no prior hypothesis)"))
        k += 1
    seen: set[str] = set()
    screened = _screen(cfg, cands, zoo, ledger, seen)
    print(f"{len(cands)} candidates -> {len(screened)} after AST/complexity/originality screen")
    rows, LS_all, num_rejects = _evaluate(cfg, screened, y, end_valid)
    for c, why in num_rejects:
        ledger.log(stage="discover-reject", name=c["name"], source=c["source"], expr=c["expr"],
                   fingerprint=c["fingerprint"], status="rejected", reason=f"numerical: {why}")

    # ---- GP refinement of the best non-hypothesis seeds -----------------
    bandit = FamilyBandit(cfg.run_dir / "bandit.json", seed=cfg.mining.seed)
    if gp and cfg.mining.gp_generations > 0:
        for gen in range(cfg.mining.gp_generations):
            pool = sorted(rows, key=lambda r: -abs(r["ic_t"]))[:10]
            pool_ls = [r["ls"] for r in pool]
            for r in rows:
                r["max_corr"] = max((abs(r["ls"].corr(p)) for p in pool_ls
                                     if not p.equals(r["ls"])), default=0.0)
            alloc = bandit.allocate(cfg.mining.gp_population)
            kids = []
            for fam, n_kids in alloc.items():
                if n_kids <= 0:
                    continue
                pool_f = [r for r in rows if r.get("family") == fam] or rows
                parents = sorted(pool_f, key=lambda r: -fitness(r, cfg.mining.gp_lambda_nodes,
                                                                cfg.mining.gp_mu_corr))[:8]
                kids += next_generation(parents, n_kids, rng, seen)
            raw_kids = len(kids)
            kids = _screen(cfg, kids, zoo, ledger, set())
            if not kids:
                print(f"  (generation {gen + 1}: {raw_kids} children generated, all screened out)")
            print(f"GP generation {gen + 1}: {len(kids)} children; budget "
                  + ", ".join(f"{k}:{v}" for k, v in alloc.items() if v))
            new_rows, new_ls, num_rej = _evaluate(cfg, kids, y, end_valid)
            for c, why in num_rej:
                ledger.log(stage="discover-reject", name=c["name"], source=c["source"],
                           expr=c["expr"], status="rejected", reason=f"numerical: {why}")
            for r in new_rows:
                # Reward on evidence the allocator did not fit (inner holdout),
                # NOT on in-sample significance. `in_sample` is recorded only so
                # the gap between the two stays measurable.
                t_io = r.get("inner_oos_t", float("nan"))
                held_up = bool(t_io == t_io and t_io >= cfg.gates.bandit_reward_t_min)
                bandit.update(r.get("family", "other"), held_up,
                              in_sample=abs(r["ic_t"]) >= cfg.gates.t_stat_min)
            rows += new_rows
            LS_all.update(new_ls)
        bandit.save()

    # ---- gates ---------------------------------------------------------------
    prior = ledger.n_trials("discover-eval")
    n_trials = prior + len(rows)

    # Is this search proportionate to the universe it is searching? IR = IC*sqrt(BR),
    # so a thin universe caps the achievable information ratio while every trial
    # still raises the bar all of them must clear. Diagnostic, never a gate.
    try:
        from .. import breadth as _breadth
        # The breadth that matters is of the INSTRUMENT universe, not of the
        # candidate strategies. Candidate independence is a different quantity -
        # the effective trial count - and `neff` already reports that.
        _close, _ = data.price_panel(cfg)
        _inst = _close.loc[cfg.splits.discover_start:cfg.splits.discover_end].pct_change()
        _inst = _inst.dropna(axis=1, thresh=int(0.5 * len(_inst)))
        breadth_report = _breadth.assess(_inst, n_trials_planned=n_trials,
                                         market=cfg.market.asset_class,
                                         rebalances_per_year=cfg.market.rebalances_per_year)
        if breadth_report.get("warning"):
            print("\nBREADTH: " + breadth_report["warning"] + "\n")
    except Exception as e:                            # noqa: BLE001 - a diagnostic must never stop a run
        breadth_report = dict(error=f"{type(e).__name__}: {str(e)[:80]}")
    sr_pp = [r["ls"].mean() / r["ls"].std() for r in rows if r["ls"].std() > 0]
    sr_var = float(np.var(sr_pp))
    T_typ = int(np.median([len(r["ls"].dropna()) for r in rows])) if rows else 0
    hurdle = stats.hurdle_sharpe(n_trials, sr_var, T_typ, cfg.gates.dsr_min, 52)
    print(f"after {n_trials} distinct trials, a new candidate needs an annualised Sharpe of "
          f"{hurdle:.2f} to clear DSR {cfg.gates.dsr_min:.2f}")
    budget = cfg.mining.trial_budget
    if budget and n_trials >= budget:
        print(f"TRIAL BUDGET SPENT: {n_trials} >= {budget}. Every further candidate faces a bar "
              f"this search raised. Change the data, the horizon or the universe - or stop; "
              f"more search on the same data cannot clear a bar that search itself creates.")
    g = cfg.gates
    kept_series, fam_counts = [], {}
    for r in sorted(rows, key=lambda r: -r["ic_t"]):
        dsr, _, _ = stats.deflated_sharpe(r["ls"], n_trials, sr_var)
        r["dsr"] = dsr
        reason = []
        if r["wrong_sign"]:
            reason.append("wrong sign vs stated hypothesis")
        if r["ic_t"] < g.t_stat_min:
            reason.append(f"t={r['ic_t']:.2f}<{g.t_stat_min}")
        redundant = any(abs(r["ls"].corr(s)) > g.max_corr_to_accepted for s in kept_series)
        if redundant:
            reason.append(f"redundant (corr>{g.max_corr_to_accepted})")
        if not reason and dsr >= g.dsr_min:
            status = "active"
        elif not reason and r["ic_t"] >= g.probation_t_min:
            status = "probation"
            reason.append(f"DSR={dsr:.2f}<{g.dsr_min}")
        else:
            status = "rejected"
            if dsr < g.dsr_min:
                reason.append(f"DSR={dsr:.2f}")
        r["status"] = status
        if status in ("active", "probation") and fam_counts.get(r.get("family", "other"), 0) >= cfg.gates.max_per_family:
            status, r["status"] = "rejected", "rejected"
            reason.append(f"family quota ({cfg.gates.max_per_family} per mechanism family)")
        if status in ("active", "probation"):
            fam_counts[r.get("family", "other")] = fam_counts.get(r.get("family", "other"), 0) + 1
            kept_series.append(r["ls"])
            lib.upsert(r["name"], r["expr"], r["sign"], r["source"], status,
                       dict(ic_t=r["ic_t"], dsr=dsr, later_ic=r["later_ic_mean"]))
        ledger.log(stage="discover-eval", name=r["name"], source=r["source"], expr=r["expr"],
                   fingerprint=r["fingerprint"], parent_id=r.get("parent_id", ""),
                   source_model=r.get("source_model", ""), prompt_sha=r.get("prompt_sha", ""),
                   rationale=r.get("rationale", ""), family=r.get("family", ""),
                   sign=r["sign"], nodes=r["nodes"],
                   zoo_overlap=r["zoo_overlap"], ic_mean=round(r["ic_mean"], 5),
                   ic_t=round(r["ic_t"], 2), ls_sharpe_ann=round(r["ls_sharpe_ann"], 2),
                   dsr=round(dsr, 3), later_ic_mean=round(r["later_ic_mean"], 5),
                   inner_oos_ic=round(r.get("inner_oos_ic", float("nan")), 5),
                   inner_oos_t=round(r.get("inner_oos_t", float("nan")), 2),
                   n_trials_at_eval=n_trials, status=status, reason="; ".join(reason) or "passed")
    lib.save()

    raw = pd.DataFrame({n: s for n, s in LS_all.items()})
    M = pd.concat([raw.add_suffix("+"), (-raw).add_suffix("-")], axis=1)
    pbo, _ = stats.pbo_cscv(M)

    ablation = {}
    for src in ("hypothesis", "llm", "random", "gp"):
        sub = [r for r in rows if r["source"] == src]
        strong = [r for r in sub if r["ic_t"] >= g.t_stat_min]
        ablation[src] = dict(evaluated=len(sub), t_ge_3=len(strong),
                             probation=sum(r["status"] == "probation" for r in sub),
                             active=sum(r["status"] == "active" for r in sub),
                             mean_disc_ic_of_t3=float(np.mean([r["ic_mean"] for r in strong])) if strong else None,
                             mean_later_ic_of_t3=float(np.mean([r["later_ic_mean"] for r in strong])) if strong else None)
    top = sorted(rows, key=lambda r: -r["ic_t"])[:20]
    summary = dict(
        n_candidates=len(cands), n_evaluated=len(rows), n_trials_total=n_trials,
        naive_t2=sum(r["ic_t"] >= 2 for r in rows), t3=sum(r["ic_t"] >= 3 for r in rows),
        active=[r["name"] for r in rows if r["status"] == "active"],
        probation=[r["name"] for r in rows if r["status"] == "probation"],
        pbo=pbo, best_dsr=max(r["dsr"] for r in rows),
        decay_top20=dict(discovery_ic=float(np.mean([r["ic_mean"] for r in top])),
                         later_ic=float(np.mean([r["later_ic_mean"] for r in top]))),
        ic_corr_discovery_vs_later=float(pd.Series([r["ic_mean"] for r in rows]).corr(
            pd.Series([r["later_ic_mean"] for r in rows]))),
        ablation_by_source=ablation,
        family_diagnostics=diagnostics(rows),
        hurdle_sharpe_ann=hurdle, trial_budget=cfg.mining.trial_budget,
        breadth=breadth_report,
        bandit_hit_rates=bandit.rates(),
        bandit_reward_vs_in_sample=bandit.divergence(),
        rejected_by_leakage=sum(1 for r in ledger.rows()
                                if r["stage"] == "discover-reject" and "leakage" in (r["reason"] or "")),
        rejected_by_numerical=sum(1 for r in ledger.rows()
                                  if r["stage"] == "discover-reject" and "numerical" in (r["reason"] or "")))
    mem_mod.build(ledger, cfg.run_dir / "memory.json")
    pd.DataFrame([{k: r[k] for k in ("name", "source", "family", "expr", "sign", "nodes",
                   "zoo_overlap", "ic_mean", "pearson_ic", "ic_t", "ls_sharpe_ann", "dsr",
                   "later_ic_mean", "status")}
                  for r in rows]).to_csv(cfg.run_dir / "discover_candidates.csv", index=False)
    (cfg.run_dir / "discover_summary.json").write_text(json.dumps(summary, indent=2, default=float))
    print(json.dumps({k: v for k, v in summary.items() if k not in ("probation",)},
                     indent=2, default=float))
    return summary
