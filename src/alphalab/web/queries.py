"""Every number the dashboard shows, computed once here.

The pages and the JSON API call the same functions, so the screen and `curl`
can never disagree - and neither can disagree with the CLI, because nothing is
recomputed: this module reads the database and the artefacts the pipelines
wrote, and does arithmetic on nothing.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from sqlalchemy import func, select

from ..config import Config
from ..db.models import ExceptionRecord, ForwardSignal, LibraryFactor, Run, Trial
from ..db.session import database_url, session_scope
from . import artefacts

# ---------------------------------------------------------------- runs ------


def _url(cfg: Config) -> str:
    return cfg.storage.database_url or database_url()


def runs(cfg: Config, limit: int = 50, offset: int = 0) -> list[dict]:
    with session_scope(_url(cfg)) as s:
        counts = dict(s.execute(select(Trial.run_id, func.count(Trial.id))
                                .group_by(Trial.run_id)).all())
        rows = s.scalars(select(Run).order_by(Run.started_at.desc())
                         .limit(limit).offset(offset)).all()
        return [dict(run_id=r.run_id, config=r.config_name, config_sha=r.config_sha,
                     git_sha=r.git_sha, version=r.alphalab_version,
                     started=r.started_at.isoformat() if r.started_at else "",
                     trials=counts.get(r.run_id, 0)) for r in rows]


def run_detail(cfg: Config, run_id: str) -> dict | None:
    with session_scope(_url(cfg)) as s:
        r = s.scalar(select(Run).where(Run.run_id == run_id))
        if r is None:
            return None
        by_status = dict(s.execute(select(Trial.status, func.count(Trial.id))
                                   .where(Trial.run_id == run_id)
                                   .group_by(Trial.status)).all())
        n_fp = s.scalar(select(func.count(func.distinct(Trial.fingerprint)))
                        .where(Trial.run_id == run_id, Trial.fingerprint != "")) or 0
        max_n = s.scalar(select(func.max(Trial.n_trials_at_eval))
                         .where(Trial.run_id == run_id))
        return dict(run_id=r.run_id, config=r.config_name, config_sha=r.config_sha,
                    git_sha=r.git_sha, version=r.alphalab_version,
                    started=r.started_at.isoformat() if r.started_at else "",
                    by_status=by_status, trials=sum(by_status.values()),
                    distinct_formulas=n_fp,
                    # the DSR denominator, on screen beside anything it deflates
                    trial_count_at_eval=int(max_n) if max_n else None)


def trials(cfg: Config, run_id: str | None = None, stage: str | None = None,
           status: str | None = None, family: str | None = None, source: str | None = None,
           min_dsr: float | None = None, sort: str = "-ic_t",
           limit: int = 200, offset: int = 0) -> list[dict]:
    cols = {"ic_t": Trial.ic_t, "dsr": Trial.dsr, "ic_mean": Trial.ic_mean,
            "later_ic_mean": Trial.later_ic_mean, "inner_oos_t": Trial.inner_oos_t,
            "name": Trial.name, "created_at": Trial.created_at}
    key = sort.lstrip("-")
    col = cols.get(key, Trial.ic_t)
    order = col.desc() if sort.startswith("-") else col.asc()
    q = select(Trial)
    for val, c in ((run_id, Trial.run_id), (stage, Trial.stage), (status, Trial.status),
                   (family, Trial.family), (source, Trial.source)):
        if val:
            q = q.where(c == val)
    if min_dsr is not None:
        q = q.where(Trial.dsr >= min_dsr)
    with session_scope(_url(cfg)) as s:
        rows = s.scalars(q.order_by(order).limit(limit).offset(offset)).all()
        return [dict(run_id=t.run_id, stage=t.stage, name=t.name, source=t.source,
                     family=t.family, expr=t.expr, sign=t.sign, ic_mean=t.ic_mean,
                     ic_t=t.ic_t, dsr=t.dsr, inner_oos_t=t.inner_oos_t,
                     later_ic_mean=t.later_ic_mean, n_trials_at_eval=t.n_trials_at_eval,
                     status=t.status, reason=t.reason) for t in rows]


def summary(cfg: Config) -> dict:
    with session_scope(_url(cfg)) as s:
        return dict(
            runs=s.scalar(select(func.count(Run.id))) or 0,
            trials=s.scalar(select(func.count(Trial.id))) or 0,
            distinct_formulas=s.scalar(
                select(func.count(func.distinct(Trial.fingerprint)))
                .where(Trial.stage.like("discover%"), Trial.fingerprint != "")) or 0,
            library=s.scalar(select(func.count(LibraryFactor.id))) or 0,
            exceptions=s.scalar(select(func.count(ExceptionRecord.id))) or 0,
            forward_signals=s.scalar(select(func.count(ForwardSignal.id))) or 0,
            configs=artefacts.configs(cfg))


def treadmill(cfg: Config) -> dict:
    """Cumulative distinct trials over time, and the DSR hurdle each implies."""
    from .. import stats
    with session_scope(_url(cfg)) as s:
        rows = s.execute(select(Trial.created_at, Trial.fingerprint)
                         .where(Trial.stage.like("discover%"), Trial.fingerprint != "")
                         .order_by(Trial.created_at)).all()
    seen, points = set(), []
    for ts, fp in rows:
        seen.add(fp)
        points.append(dict(ts=ts.isoformat() if ts else "", n=len(seen)))
    step = max(1, len(points) // 60)
    thinned = points[::step] + (points[-1:] if points else [])
    sr_var = 0.02
    for p in thinned:
        p["hurdle_sharpe_ann"] = round(stats.hurdle_sharpe(p["n"], sr_var, 400), 3)
    return dict(points=thinned, sr_var_assumed=sr_var,
                note="hurdle uses a representative trial-Sharpe variance; the exact value "
                     "for a run is in its discover_summary.json")


# ------------------------------------------------------------- the loop -----

GATES = ("t_stat_min", "dsr_min", "revalidation", "forward")


def _library_state_sha(lib: dict) -> str:
    import hashlib

    from ..library import item_fingerprint
    parts = []
    for name in sorted(lib):
        it = lib[name]
        parts.append("|".join([name, it.get("status", ""), str(it.get("passes", 0)),
                               str(it.get("strikes", 0)), item_fingerprint(it)]))
    return hashlib.sha1("\n".join(parts).encode()).hexdigest()


def _revalidation_stale(cfg: Config, config_name: str | None, lib: dict, reval: dict) -> dict:
    if not reval:
        return dict(stale=False, reason="")
    current = _library_state_sha(lib)
    file_sha = reval.get("library_sha")
    if not file_sha or file_sha != current:
        return dict(stale=True, reason="library state changed since revalidation was recorded",
                    current_library_sha=current, file_library_sha=file_sha or "")
    return dict(stale=False, reason="", current_library_sha=current, file_library_sha=file_sha)


def _revalidation_moves(reval: dict, lib: dict) -> tuple[list[str], list[str]]:
    """Promotions/retirements only when the current library backs the claim."""
    promoted = [n for n in reval.get("promoted", [])
              if lib.get(n, {}).get("status") == "active"]
    retired = [n for n in reval.get("retired", [])
               if lib.get(n, {}).get("status") == "retired"]
    return promoted, retired


def loop(cfg: Config, config_name: str | None = None) -> list[dict]:
    """Per library factor: the stage it is at and the ONE gate blocking it."""
    name = config_name or cfg.name
    lib = artefacts.read(cfg, "library", name, default={}) or {}
    reval = artefacts.read(cfg, "revalidation", name, default={}) or {}
    stale_info = _revalidation_stale(cfg, name, lib, reval)
    reval_fresh = not stale_info.get("stale")
    reval_by = {r["name"]: r for r in reval.get("factors", [])} if reval_fresh else {}
    fwd = forward(cfg, name)
    clean_weeks = sum(1 for p in fwd["published"] if p.get("clean"))
    out = []
    for n, it in lib.items():
        hist = it.get("history", [])
        first, last = (hist[0] if hist else {}), (hist[-1] if hist else {})
        dsr = first.get("dsr")
        rv = reval_by.get(n, {})
        if it["status"] == "retired":
            stage, gate, have, need = "retired", "-", rv.get("recheck_t") if reval_fresh else last.get("recheck_t"), None
        elif it["status"] == "probation":
            stage = "probation"
            if dsr is not None and dsr < cfg.gates.dsr_min:
                gate, have, need = "deflated sharpe", dsr, cfg.gates.dsr_min
            else:
                gate, have, need = ("revalidation (2 consecutive)",
                                    it.get("passes", 0), 2)
        elif clean_weeks < 13:
            stage, gate, have, need = "active", "forward weeks", clean_weeks, 13
        else:
            stage, gate, have, need = "forward-evidenced", "-", clean_weeks, None
        out.append(dict(name=n, expr=it.get("expr", ""), source=it.get("source", ""),
                        status=it["status"], stage=stage, blocking_gate=gate,
                        have=have, need=need,
                        discovery_ic_t=first.get("ic_t"), discovery_dsr=dsr,
                        recheck_t=(rv.get("recheck_t") if reval_fresh and rv else last.get("recheck_t")),
                        strikes=it.get("strikes", 0), passes=it.get("passes", 0)))
    if stale_info.get("stale"):
        for row in out:
            row["revalidation_stale"] = True
    return sorted(out, key=lambda r: (r["status"] != "active", r["status"] != "probation",
                                      -(r["discovery_ic_t"] or 0)))


def search_allocation(cfg: Config, config_name: str | None = None) -> dict:
    """Where the search budget went, and whether the reward predicted anything."""
    d = artefacts.read(cfg, "discover_summary", config_name, default={}) or {}
    div = d.get("bandit_reward_vs_in_sample", {})
    rows = [dict(family=f, **v) for f, v in div.items() if v.get("trials")]
    rows.sort(key=lambda r: -(r.get("reward_rate") or 0))
    return dict(families=rows,
                hurdle_sharpe_ann=d.get("hurdle_sharpe_ann"),
                n_trials_total=d.get("n_trials_total"),
                trial_budget=d.get("trial_budget"),
                pbo=d.get("pbo"),
                note="reward_rate is measured on the purged inner holdout (t >= "
                     f"{cfg.gates.bandit_reward_t_min}); in_sample_rate is the old rule "
                     f"(t >= {cfg.gates.t_stat_min}). The bars differ, so compare the "
                     "ORDERING of families, not the levels.")


def decay(cfg: Config, config_name: str | None = None) -> dict:
    lib = artefacts.read(cfg, "library", config_name, default={}) or {}
    r = artefacts.read(cfg, "revalidation", config_name, default={}) or {}
    stale_info = _revalidation_stale(cfg, config_name, lib, r)
    promoted, retired = _revalidation_moves(r, lib) if r else ([], [])
    rows = list(r.get("factors", [])) if not stale_info.get("stale") else []
    for row in rows:
        d, t = row.get("discovery_ic_t"), row.get("recheck_t")
        row["retained"] = (t / d) if (d and t is not None and d != 0) else None
    rows.sort(key=lambda x: -(x.get("recheck_t") or -99))
    return dict(window=r.get("window"), sessions=r.get("sessions"),
                promoted=promoted, retired=retired, factors=rows, **stale_info)


def versions(cfg: Config) -> list[dict]:
    """Runs grouped by the code that produced them, plus committed snapshots."""
    with session_scope(_url(cfg)) as s:
        rows = s.execute(
            select(Run.alphalab_version, Run.git_sha, func.count(Run.id),
                   func.min(Run.started_at), func.max(Run.started_at))
            .group_by(Run.alphalab_version, Run.git_sha)).all()
    out = [dict(version=v or "(not recorded)", git_sha=g or "", runs=n,
                first=str(a or ""), last=str(b or "")) for v, g, n, a, b in rows]
    snaps = {}
    for p in sorted(Path("results").glob("v*/summary.json")) if Path("results").is_dir() else []:
        try:
            snaps[p.parent.name] = json.loads(p.read_text())
        except json.JSONDecodeError:
            continue
    for o in out:
        for label, snap in snaps.items():
            if o["version"] and label.startswith(f"v{o['version']}"):
                m = snap.get("model", {})
                o["snapshot"] = label
                o["chosen"] = m.get("chosen")
                o["claim_tier"] = m.get("claim_tier")
                o["validation_ir"] = (m.get("validation") or {}).get("info_ratio")
                o["holdout_ir"] = (m.get("holdout") or {}).get("info_ratio")
                o["discovery_trials"] = m.get("discovery_trials")
    out.sort(key=lambda r: r["last"], reverse=True)
    return out


def forward(cfg: Config, config_name: str | None = None) -> dict:
    d = artefacts.run_dir(cfg, config_name) / "forward"
    pub, ev = [], []
    if (d / "published.jsonl").is_file():
        for line in (d / "published.jsonl").read_text().splitlines():
            try:
                pub.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if (d / "evaluations.csv").is_file() and (d / "evaluations.csv").stat().st_size:
        with open(d / "evaluations.csv") as f:
            ev = list(csv.DictReader(f))
    clean = [p for p in pub if p.get("clean")]
    return dict(published=pub, evaluated=ev, n_published=len(pub), n_clean=len(clean),
                n_evaluated=len(ev),
                note="a manifest written after its own execution close is recorded but never "
                     "counted: a file hash proves the file is unchanged, not that the "
                     "prediction preceded the outcome")


def library(cfg: Config, config_name: str | None = None) -> list[dict]:
    lib = artefacts.read(cfg, "library", config_name, default={}) or {}
    out = []
    for n, it in lib.items():
        hist = it.get("history", [])
        out.append(dict(name=n, expr=it.get("expr", ""), sign=it.get("sign"),
                        source=it.get("source", ""), status=it["status"],
                        added=it.get("added", ""), checks=len(hist),
                        discovery_ic_t=(hist[0] if hist else {}).get("ic_t"),
                        discovery_dsr=(hist[0] if hist else {}).get("dsr"),
                        later_ic=(hist[0] if hist else {}).get("later_ic"),
                        recheck_t=(hist[-1] if hist else {}).get("recheck_t"),
                        strikes=it.get("strikes", 0), passes=it.get("passes", 0)))
    return sorted(out, key=lambda r: -(r["discovery_ic_t"] or 0))


def audit(cfg: Config, config_name: str | None = None) -> dict:
    return artefacts.read(cfg, "audit", config_name, default={}) or {}


def hierarchy(cfg: Config, config_name: str | None = None) -> dict:
    return artefacts.read(cfg, "hierarchy", config_name, default={}) or {}


def cards(cfg: Config, config_name: str | None = None) -> dict:
    return artefacts.read(cfg, "cards", config_name, default={}) or {}


def exceptions(cfg: Config, config_name: str | None = None) -> list[dict]:
    with session_scope(_url(cfg)) as s:
        rows = s.scalars(select(ExceptionRecord)
                         .where(ExceptionRecord.config_name == (config_name or cfg.name))
                         .order_by(ExceptionRecord.id.desc())).all()
        return [dict(kind=r.kind, scope=r.scope, reason=r.reason, author=r.author,
                     at=str(getattr(r, "created_at", ""))) for r in rows]
