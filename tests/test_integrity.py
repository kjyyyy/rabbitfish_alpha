"""Artefact integrity: ledger schema, stale revalidation, library dedup and DB sync."""
import csv
import json

import pandas as pd

from alphalab.config import Config
from alphalab.db import repo
from alphalab.db.models import Base
from alphalab.db.session import get_engine
from alphalab.ledger import LEGACY_FIELDS, Ledger
from alphalab.library import Library
from alphalab.miners.gp import next_generation
from alphalab.pipeline import repair
from alphalab.web import queries as Q


def test_library_state_sha_tracks_lifecycle(tmp_path):
    lib = Library(tmp_path / "lib.json")
    lib.upsert("a", "$close", 1, "gp", "probation", {"ic_t": 3.0}, fingerprint="fp1")
    sha1 = lib.state_sha()
    lib.items["a"]["passes"] = 2
    assert lib.state_sha() != sha1


def test_ledger_migrates_legacy_rows(tmp_path):
    path = tmp_path / "ledger.csv"
    row = [""] * len(LEGACY_FIELDS)
    row[0], row[2], row[3], row[8], row[9], row[21], row[22] = (
        "ts", "discover-eval", "f0", "fp", "Mean($close,5)", "ok", "")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(LEGACY_FIELDS)
        w.writerow(row)
    led = Ledger(path)
    assert led.migrate() is True
    pd.read_csv(path)
    out = led.rows()
    assert out[0]["fingerprint"] == "fp"
    assert out[0]["inner_oos_ic"] == ""


def test_stale_revalidation_filters_phantom_promotions(tmp_path):
    cfg = Config(name="web", workdir=str(tmp_path))
    run_dir = cfg.run_dir
    lib = {"f1": dict(name="f1", status="probation", passes=1, strikes=0, expr="$close",
                      fingerprint="abc", history=[{"ic_t": 3.0}])}
    (run_dir / "library.json").write_text(json.dumps(lib))
    (run_dir / "revalidation.json").write_text(json.dumps(
        dict(promoted=["f1", "f2", "f3"], retired=["r1"], library_sha="deadbeef", factors=[])))
    body = Q.decay(cfg)
    assert body["stale"] is True
    assert body["promoted"] == []
    assert body["retired"] == []


def test_sync_library_matches_json(tmp_path):
    url = f"sqlite:///{tmp_path/'t.db'}"
    Base.metadata.create_all(get_engine(url))
    cfg = Config(name="lab", workdir=str(tmp_path))
    cfg.storage.database_url = url
    run_dir = cfg.run_dir
    lib = Library(run_dir / "library.json")
    lib.upsert("f1", "$close", 1, "gp", "probation", {"ic_t": 3.0}, fingerprint="fp1")
    lib.upsert("f2", "Mean($close,5)", 1, "gp", "probation", {"ic_t": 2.5}, fingerprint="fp2")
    lib.save()
    repo.sync_library("lab", lib.items, url=url)
    assert repo.count_library("lab", url=url) == 2
    lib.items.pop("f2")
    lib.save()
    repo.sync_library("lab", lib.items, url=url)
    assert repo.count_library("lab", url=url) == 1


def test_repair_retires_duplicate_expressions(tmp_path):
    cfg = Config(name="lab", workdir=str(tmp_path))
    cfg.storage.use_database = False
    run_dir = cfg.run_dir
    expr = "Corr($close, $volume, 20)"
    lib = Library(run_dir / "library.json")
    lib.items["gp_0161"] = dict(name="gp_0161", expr=expr, sign=-1, source="gp", status="probation",
                                added="2024-01-01", history=[])
    lib.items["gp_0190"] = dict(name="gp_0190", expr=expr, sign=-1, source="gp", status="probation",
                                added="2024-02-01", history=[])
    lib.save()
    repair.run(cfg, apply=True, log=lambda *_: None)
    lib = Library(run_dir / "library.json")
    assert lib.items["gp_0161"]["status"] == "probation"
    assert lib.items["gp_0190"]["status"] == "retired"


def test_gp_names_include_run_id():
    import random
    parents = [dict(name="p", expr="Mean($close, 5)")]
    kids = next_generation(parents, 2, random.Random(0), set(), "ab12cd34")
    assert all(k["name"].startswith("gp_ab12cd34_") for k in kids)
