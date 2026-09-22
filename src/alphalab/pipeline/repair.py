"""Reconcile run artefacts after schema or library repairs."""
from __future__ import annotations

import datetime as dt
import json
from collections import defaultdict

from .. import expr as E
from ..config import Config
from ..ledger import FIELDS, Ledger
from ..library import Library, item_fingerprint


def _merge_duplicate_factors(lib: Library, log=print) -> list[tuple[str, str]]:
    """Keep the earliest-added name per fingerprint; retire the rest."""
    by_fp: dict[str, list[str]] = defaultdict(list)
    for name, it in lib.items.items():
        fp = item_fingerprint(it)
        if fp:
            by_fp[fp].append(name)
    merged: list[tuple[str, str]] = []
    for fp, names in by_fp.items():
        if len(names) < 2:
            continue
        names.sort(key=lambda n: lib.items[n].get("added", ""))
        keep, drop = names[0], names[1:]
        for d in drop:
            it = lib.items[d]
            it["status"] = "retired"
            it.setdefault("history", []).append(
                dict(date=dt.date.today().isoformat(), status="retired",
                     reason=f"duplicate of {keep}", fingerprint=fp))
            merged.append((d, keep))
            log(f"  retire duplicate {d} -> same expression as {keep}")
    return merged


def run(cfg: Config, apply: bool = False, log=print) -> dict:
    run_dir = cfg.run_dir
    lib_path = run_dir / "library.json"
    lib = Library(lib_path)
    ledger_path = run_dir / "ledger.csv"
    ledger = Ledger(ledger_path, cfg=cfg)

    report: dict = dict(apply=apply, ledger_migrated=False, duplicates=[], revalidation_quarantined=False)

    if ledger_path.exists():
        if apply:
            report["ledger_migrated"] = ledger.migrate()
            if report["ledger_migrated"]:
                log(f"migrated {ledger_path} to {len(FIELDS)} columns")
        else:
            try:
                ledger.rows()
            except Exception as e:  # noqa: BLE001
                log(f"ledger needs migration: {e}")
                report["ledger_needs_migration"] = True

    backfilled = 0
    for _name, it in lib.items.items():
        if not it.get("fingerprint") and it.get("expr"):
            it["fingerprint"] = E.fingerprint(it["expr"])
            backfilled += 1
    if backfilled:
        log(f"  backfilled fingerprint on {backfilled} library member(s)")

    dups = _merge_duplicate_factors(lib, log=log)
    report["duplicates"] = dups

    reval_path = run_dir / "revalidation.json"
    if reval_path.exists():
        try:
            reval = json.loads(reval_path.read_text())
        except json.JSONDecodeError:
            reval = {}
        current_sha = lib.state_sha()
        if reval.get("library_sha") != current_sha:
            report["revalidation_stale"] = True
            if apply:
                ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                dest = run_dir / f"revalidation.stale-{ts}.json"
                reval_path.rename(dest)
                report["revalidation_quarantined"] = True
                log(f"  quarantined stale {reval_path.name} -> {dest.name}")
            else:
                log("  revalidation.json is stale (library changed since it was written)")

    if apply:
        lib.save()
        if getattr(cfg.storage, "use_database", True):
            from ..db import repo
            url = cfg.storage.database_url
            repo.sync_library(cfg.name, lib.items, url=url)
            db_n = repo.count_library(cfg.name, url=url)
            json_n = len(lib.items)
            db_trials = repo.count_distinct_formulas(url=url)
            try:
                csv_trials = ledger.n_trials("discover")
            except Exception:
                csv_trials = None
            report["library_json"] = json_n
            report["library_db"] = db_n
            report["distinct_formulas_db"] = db_trials
            report["distinct_formulas_csv"] = csv_trials
            log(f"  library: {json_n} in JSON, {db_n} in database")
            if csv_trials is not None:
                log(f"  distinct discovery formulas: {csv_trials} in CSV, {db_trials} in database")
    else:
        log("dry run only — pass --apply to write changes")

    return report
