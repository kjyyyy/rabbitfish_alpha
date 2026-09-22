"""Storage layer: schema, idempotency, the trial count, and a real migration run."""
import datetime as dt
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import inspect

from alphalab.config import Config
from alphalab.db import repo
from alphalab.db.models import Base
from alphalab.db.session import get_engine, session_scope

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def url(tmp_path):
    u = f"sqlite:///{tmp_path/'t.db'}"
    Base.metadata.create_all(get_engine(u))
    return u


def _trial(**kw):
    base = dict(run_id="r1", stage="discover-eval", name="f1", source="random",
                fingerprint="abc123", expr="Mean($close,5)", status="probation",
                ic_t="3.4", nodes="4", sign="1")
    base.update(kw)
    return base


def test_trials_are_idempotent(url):
    repo.ensure_run("r1", "cfg", url=url)
    assert repo.add_trial(_trial(), url=url) is True
    assert repo.add_trial(_trial(), url=url) is False          # same formula, same run+stage
    assert repo.add_trial(_trial(name="f2", fingerprint="def456"), url=url) is True


def test_rows_without_fingerprint_do_not_collide(url):
    """Family-level tests have no formula fingerprint - they must still insert."""
    repo.ensure_run("r1", "cfg", url=url)
    assert repo.add_trial(_trial(stage="hierarchy-family", name="family::trend",
                                 fingerprint=""), url=url)
    assert repo.add_trial(_trial(stage="hierarchy-family", name="family::reversal",
                                 fingerprint=""), url=url)


def test_distinct_formula_count_spans_runs(url):
    for run in ("r1", "r2"):
        repo.ensure_run(run, "cfg", url=url)
        repo.add_trial(_trial(run_id=run, fingerprint="shared"), url=url)
        repo.add_trial(_trial(run_id=run, name="x", fingerprint=f"only-{run}"), url=url)
    assert repo.count_distinct_formulas(url=url) == 3          # shared + two run-specific


def test_string_numbers_from_csv_are_coerced(url):
    repo.ensure_run("r1", "cfg", url=url)
    repo.add_trial(_trial(ic_t="", dsr="0.91", n_trials_at_eval="194"), url=url)
    with session_scope(url) as s:
        from alphalab.db.models import Trial
        t = s.query(Trial).one()
    assert t.ic_t is None and t.dsr == pytest.approx(0.91) and t.n_trials_at_eval == 194


def test_fundamentals_respect_the_filing_date(url):
    rows = [dict(cik=1, tag="Assets", period="2024-06-30", filed="2024-08-02", value=1.0, adsh="a"),
            dict(cik=2, tag="Assets", period="2024-06-30", filed="2024-07-30", value=2.0, adsh="b")]
    assert repo.bulk_fundamentals(rows, url=url) == 2
    assert repo.bulk_fundamentals(rows, url=url) == 0          # idempotent
    early = repo.fundamentals_as_of(dt.date(2024, 7, 31), url=url)
    assert {r["cik"] for r in early} == {2}


def test_alembic_migrations_run_on_a_fresh_database(tmp_path):
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "DATABASE_URL": f"sqlite:///{tmp_path/'m.db'}"}
    r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                       cwd=ROOT, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    tables = set(inspect(get_engine(env["DATABASE_URL"])).get_table_names())
    assert {"trials", "runs", "fundamentals", "forward_signals"} <= tables
    down = subprocess.run([sys.executable, "-m", "alembic", "downgrade", "base"],
                          cwd=ROOT, env=env, capture_output=True, text=True)
    assert down.returncode == 0, down.stderr


def test_ledger_dual_writes_csv_and_database(tmp_path, monkeypatch):
    from alphalab.ledger import Ledger
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path/'l.db'}")
    Base.metadata.create_all(get_engine(f"sqlite:///{tmp_path/'l.db'}"))
    cfg = Config(workdir=str(tmp_path))
    led = Ledger(cfg.run_dir / "ledger.csv", cfg=cfg)
    led.log(**_trial(run_id=led.run_id))
    assert (cfg.run_dir / "ledger.csv").exists() and len(led.rows()) == 1
    assert repo.count_distinct_formulas(url=f"sqlite:///{tmp_path/'l.db'}") == 1


def test_run_records_the_code_version_that_produced_it(tmp_path):
    """A research record that cannot say which version wrote it is not a record."""
    from sqlalchemy import select

    from alphalab.config import Config
    from alphalab.db.models import Base, Run
    from alphalab.db.session import get_engine, session_scope
    from alphalab.ledger import Ledger
    from alphalab.provenance import version

    url = f"sqlite:///{tmp_path}/lineage.db"
    Base.metadata.create_all(get_engine(url))

    cfg = Config(name="lineage", workdir=str(tmp_path))
    cfg.storage.database_url = url
    led = Ledger(tmp_path / "ledger.csv", cfg=cfg)
    led.log(stage="discover-eval", name="x", source="test", fingerprint="abc", status="rejected")

    with session_scope(url) as s:
        run = s.scalar(select(Run).where(Run.run_id == led.run_id))
        assert run is not None
        assert run.alphalab_version == version()
        assert run.config_name == "lineage"


def test_verify_detects_a_csv_row_that_never_reached_the_database(tmp_path, capsys):
    """The DB write is best-effort by design; divergence must be findable."""
    from alphalab.config import Config
    from alphalab.db import maintenance
    from alphalab.db.models import Base
    from alphalab.db.session import get_engine
    from alphalab.ledger import Ledger

    url = f"sqlite:///{tmp_path}/v.db"
    Base.metadata.create_all(get_engine(url))
    cfg = Config(name="verify", workdir=str(tmp_path))
    cfg.storage.database_url = url

    led = Ledger(cfg.run_dir / "ledger.csv", cfg=cfg)
    led.log(stage="discover-eval", name="a", source="t", fingerprint="f1", status="passed")
    maintenance.verify(cfg)
    assert "the two records agree" in capsys.readouterr().out

    # a row that reached the CSV only - exactly what a storage fault leaves behind
    with open(cfg.run_dir / "ledger.csv", "a") as f:
        f.write(f"2026-01-01T00:00:00+00:00,{led.run_id},discover-eval,ghost,t,,,,f2,"
                + "," * 13 + "passed,\n")
    out = maintenance.verify(cfg)
    assert out["ok"] is False and out["missing"] == 1
    assert "NEVER REACHED THE DATABASE" in capsys.readouterr().out
