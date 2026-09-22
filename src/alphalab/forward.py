"""Forward pre-registration: the only clean out-of-sample evidence left once a
holdout is burned, and the only data guaranteed to post-date an LLM's
training cutoff.

`forward publish` scores the latest date with the chosen strategy and writes
signals + a manifest (git SHA, config hash, data date, file SHA-256). Commit
the manifest (or post its hash somewhere public) BEFORE the next session opens.
`forward evaluate` scores every published week whose horizon has elapsed."""
from __future__ import annotations

import datetime as dt
import hashlib
import json

import numpy as np
import pandas as pd

from . import data
from .config import Config
from .pipeline import model as M


def _git_sha() -> str:
    from .provenance import git_sha
    return git_sha() or "not-a-git-repo"


def publish(cfg: Config, log=print) -> dict:
    choice = json.loads((cfg.run_dir / "model_choice.json").read_text())["chosen"]
    I = M.build_inputs(cfg)
    last = I["cal"][-1]
    V = M.variants(cfg, I, lambda *_: None)
    if choice.startswith(("C_", "F_")):
        # retrain on the most recent window, ending purge_days before the latest label
        X = I["Hr"] if choice.startswith("C_") else I["Hr"].join(I["Lr"] * I["lib_signs"], rsuffix="_lib")
        import lightgbm as lgb
        labelled = I["y"].dropna().index.get_level_values(0).unique().sort_values()
        tr_end = labelled[-cfg.model.purge_days - 1]
        tr_start = tr_end - pd.DateOffset(years=cfg.model.train_years)
        Xtr, ytr = M._sl(X, tr_start, tr_end), M._sl(I["y"], tr_start, tr_end)
        m = ytr.notna()
        bst = lgb.train(cfg.model.lgbm_params, lgb.Dataset(Xtr[m].values, ytr[m].values), cfg.model.lgbm_early_stop + 10)
        Xl = M._sl(X, last, last)
        scores = pd.Series(bst.predict(Xl.values), index=Xl.index)
    else:
        scores = V[choice]([last.year])
        scores = M._sl(scores, last, last)
    s = scores.droplevel(0).sort_values(ascending=False)
    out = cfg.run_dir / "forward"
    out.mkdir(exist_ok=True)
    f = out / f"{last.date()}_{choice}.csv"
    pd.DataFrame({"instrument": s.index, "score": s.values,
                  "rank": np.arange(1, len(s) + 1)}).to_csv(f, index=False)
    # The engine trades at the NEXT close after the signal date, so that close is
    # the moment this prediction becomes untestable. A manifest written after it
    # is a record, not evidence - and the file-hash check alone cannot tell the
    # difference, because a backdated file hashes perfectly well.
    close_idx = data.price_panel(cfg)[0].index
    j = close_idx.searchsorted(last) + 1
    execution = close_idx[j] if j < len(close_idx) else None
    now = dt.datetime.now(dt.timezone.utc)
    clean = execution is not None and now.date() < execution.date()
    manifest = dict(signal_date=str(last.date()), strategy=choice, topk=cfg.trading.topk,
                    execution_date=str(execution.date()) if execution is not None else "",
                    clean=bool(clean),
                    file=f.name, file_sha256=hashlib.sha256(f.read_bytes()).hexdigest(),
                    config_sha=cfg.sha(), git_sha=_git_sha(),
                    published_utc=now.isoformat(timespec="seconds"))
    if not clean:
        when = manifest["execution_date"] or "beyond the end of the data"
        log(f"NOT CLEAN EVIDENCE: the execution close ({when}) is not in the future at "
            f"publication time. Recorded, and excluded from the forward tally. Refresh the "
            f"dataset (`alphalab download-cn`) and publish again before the next session opens.")
    (out / f"{last.date()}_{choice}.manifest.json").write_text(json.dumps(manifest, indent=2))
    with open(out / "published.jsonl", "a") as fh:
        fh.write(json.dumps(manifest) + "\n")
    if getattr(cfg.storage, "use_database", True):
        try:
            from .db import repo
            repo.record_forward(cfg.name, manifest, url=cfg.storage.database_url)
        except Exception:                            # noqa: BLE001
            pass
    log(json.dumps(manifest, indent=2))
    return manifest


def evaluate(cfg: Config, log=print) -> pd.DataFrame:
    out = cfg.run_dir / "forward"
    pub = [json.loads(x) for x in (out / "published.jsonl").read_text().splitlines()] \
        if (out / "published.jsonl").exists() else []
    close, _ = data.price_panel(cfg)
    bench = data.benchmark_close(cfg)
    rows, late = [], []
    for p in pub:
        f = out / p["file"]
        if hashlib.sha256(f.read_bytes()).hexdigest() != p["file_sha256"]:
            log(f"WARNING {f.name}: file changed after publication - excluded")
            continue
        if not p.get("clean", True):
            late.append(p["signal_date"])
            continue
        d0 = pd.Timestamp(p["signal_date"])
        idx = close.index
        i = idx.searchsorted(d0)
        if i + 1 + cfg.trading.horizon >= len(idx):
            continue                                   # horizon not elapsed yet
        t1, t2 = idx[i + 1], idx[i + 1 + cfg.trading.horizon]
        top = pd.read_csv(f).head(p["topk"])["instrument"]
        r = (close.loc[t2, top] / close.loc[t1, top] - 1).mean()
        b = bench.loc[t2] / bench.loc[t1] - 1
        rows.append(dict(signal_date=p["signal_date"], strategy=p["strategy"],
                         ret=float(r), bench=float(b), excess=float(r - b)))
    df = pd.DataFrame(rows, columns=["signal_date", "strategy", "ret", "bench", "excess"])
    df.to_csv(out / "evaluations.csv", index=False)     # header even when empty
    if late:
        log(f"{len(late)} publication(s) excluded as not clean (written on or after the "
            f"execution close): {', '.join(late)}")
    if df.empty:
        log(f"no clean forward weeks with an elapsed horizon yet ({len(pub)} published)")
    else:
        log(df.tail(20).to_string())
        log(f"\nclean forward weeks: {len(df)}  mean excess {df.excess.mean():+.4%}  "
            f"hit rate {(df.excess > 0).mean():.0%}")
    return df
