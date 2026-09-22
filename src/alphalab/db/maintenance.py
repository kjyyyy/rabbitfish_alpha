"""`alphalab db ...` - migrations and CSV import, so the database never has to
be created by hand."""
from __future__ import annotations

import csv
from pathlib import Path

from sqlalchemy import func, inspect, select

from ..config import Config
from . import repo
from .models import ForwardSignal, Fundamental, LibraryFactor, Run, Trial
from .session import database_url, get_engine, session_scope

ROOT = Path(__file__).resolve().parents[3]


def _alembic_config(cfg: Config):
    from alembic.config import Config as AlembicConfig
    ini = ROOT / "alembic.ini"
    ac = AlembicConfig(str(ini))
    ac.set_main_option("script_location", str(ROOT / "migrations"))
    ac.set_main_option("sqlalchemy.url", cfg.storage.database_url or database_url())
    return ac


def upgrade(cfg: Config) -> None:
    from alembic import command
    command.upgrade(_alembic_config(cfg), "head")
    print(f"database up to date: {cfg.storage.database_url or database_url()}")


def status(cfg: Config) -> None:
    url = cfg.storage.database_url or database_url()
    eng = get_engine(url)
    tables = sorted(inspect(eng).get_table_names())
    print(f"url:    {url}")
    print(f"tables: {', '.join(tables) or '(none - run `alphalab db upgrade`)'}")
    if "trials" not in tables:
        return
    def n(model):
        with session_scope(url) as s:
            return int(s.scalar(select(func.count()).select_from(model)) or 0)
    print(f"runs:               {n(Run)}")
    print(f"trials:             {n(Trial)}")
    print(f"distinct formulas:  {repo.count_distinct_formulas(url=url)}")
    print(f"library factors:    {n(LibraryFactor)}")
    print(f"forward signals:    {n(ForwardSignal)}")
    print(f"fundamental rows:   {n(Fundamental)}")


def import_csv(cfg: Config) -> None:
    """Backfill the database from existing CSV mirrors (idempotent)."""
    url = cfg.storage.database_url or database_url()
    led = cfg.run_dir / "ledger.csv"
    n = 0
    if led.exists():
        with open(led) as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            run_id = r.get("run_id") or "imported"
            repo.ensure_run(run_id, cfg.name, cfg.sha(), url=url)
            n += int(repo.add_trial(dict(r, run_id=run_id), url=url))
    exc = cfg.run_dir / "exceptions.csv"
    m = 0
    if exc.exists():
        with open(exc) as f:
            for r in csv.DictReader(f):
                repo.add_exception(cfg.name, r["kind"], r["scope"], r["reason"],
                                   r.get("author", ""), url=url)
                m += 1
    print(f"imported {n} trials and {m} exceptions into {url}")


def verify(cfg: Config) -> dict:
    """Is the database still the same record as the CSV mirror?

    The ledger writes CSV first and the database second, and the database write
    is wrapped in `except Exception` so a storage fault can never lose a trial.
    The cost of that choice is silent divergence - and the database is what
    answers "how many trials have I run?", which is the denominator of every
    Deflated Sharpe in this repo. So the two records are reconciled explicitly
    rather than assumed equal.
    """
    url = cfg.storage.database_url or database_url()
    led = cfg.run_dir / "ledger.csv"
    if not led.exists():
        print(f"no CSV ledger at {led} - nothing to reconcile")
        return dict(ok=True, csv_rows=0)

    with open(led) as f:
        rows = list(csv.DictReader(f))
    csv_keys = {(r.get("run_id", ""), r.get("stage", ""), r.get("name", ""),
                 r.get("fingerprint", "")) for r in rows}
    run_ids = {r.get("run_id", "") for r in rows}

    with session_scope(url) as s:
        db_rows = s.execute(
            select(Trial.run_id, Trial.stage, Trial.name, Trial.fingerprint)
            .where(Trial.run_id.in_(run_ids))).all()
    db_keys = {tuple(r) for r in db_rows}

    missing = csv_keys - db_keys            # in the CSV, never reached the database
    extra = db_keys - csv_keys              # in the database, not in this CSV mirror
    csv_fps = {r.get("fingerprint", "") for r in rows
               if r.get("stage", "").startswith("discover") and r.get("fingerprint")}
    db_fp_count = repo.count_distinct_formulas(url=url)

    print(f"CSV rows:            {len(rows)} ({len(csv_keys)} unique keys, {len(run_ids)} runs)")
    print(f"database rows:       {len(db_keys)} for those runs")
    print(f"distinct formulas:   {len(csv_fps)} in this CSV, {db_fp_count} in the database "
          f"(all runs, all configs)")
    ok = not missing
    if missing:
        print(f"\n{len(missing)} CSV row(s) NEVER REACHED THE DATABASE - the trial count is wrong:")
        for k in sorted(missing)[:10]:
            print(f"  run={k[0]} stage={k[1]} name={k[2]}")
        if len(missing) > 10:
            print(f"  ... and {len(missing) - 10} more")
        print("\nfix: alphalab db import-csv   (idempotent)")
    if extra:
        print(f"\n{len(extra)} database row(s) are not in this CSV mirror. Usually fine - a "
              f"deleted or rotated CSV - but check if you did not expect it.")
    if ok:
        print("\nthe two records agree")
    return dict(ok=ok, csv_rows=len(rows), db_rows=len(db_keys),
                missing=len(missing), extra=len(extra), distinct_formulas=db_fp_count)
