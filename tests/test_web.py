"""The dashboard: every route must render on an empty database and on a real one.

Read-only is a design constraint, not an accident, so it is tested: any route
that accepts a write is a bug.
"""
import json

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from alphalab.config import Config  # noqa: E402
from alphalab.db.models import Base  # noqa: E402
from alphalab.db.session import get_engine  # noqa: E402
from alphalab.web.app import create_app  # noqa: E402

PAGES = ["/", "/loop", "/search", "/library", "/decay", "/audit", "/hierarchy",
         "/forward", "/versions"]
APIS = ["/api/health", "/api/runs", "/api/stats/summary", "/api/stats/treadmill", "/api/loop",
        "/api/search/allocation", "/api/decay", "/api/library", "/api/audit", "/api/hierarchy",
        "/api/forward", "/api/cards", "/api/exceptions", "/api/versions", "/api/trials"]


@pytest.fixture
def client(tmp_path):
    cfg = Config(name="web", workdir=str(tmp_path))
    cfg.storage.database_url = f"sqlite:///{tmp_path}/web.db"
    Base.metadata.create_all(get_engine(cfg.storage.database_url))
    return TestClient(create_app(cfg)), cfg


@pytest.mark.parametrize("path", PAGES)
def test_pages_render_on_an_empty_lab(client, path):
    c, _ = client
    r = c.get(path)
    assert r.status_code == 200, r.text[:300]
    assert "Alpha Lab" in r.text
    # an empty page must say what to run, not show a blank table
    assert "Nothing to show yet" in r.text or "<table" in r.text


@pytest.mark.parametrize("path", APIS)
def test_api_returns_json_on_an_empty_lab(client, path):
    c, _ = client
    r = c.get(path)
    assert r.status_code == 200, r.text[:300]
    json.loads(r.text)


def test_health_reports_the_code_version(client):
    c, _ = client
    body = c.get("/api/health").json()
    assert body["status"] == "ok" and body["alphalab_version"]


def test_pages_and_api_agree_because_nothing_is_recomputed(client):
    c, cfg = client
    from alphalab.ledger import Ledger
    led = Ledger(cfg.run_dir / "ledger.csv", cfg=cfg)
    for i in range(3):
        led.log(stage="discover-eval", name=f"f{i}", source="test", fingerprint=f"fp{i}",
                ic_t=4.0 + i, dsr=0.5, n_trials_at_eval=99, status="rejected",
                reason="DSR too low")
    api = c.get("/api/runs").json()
    assert api and api[0]["trials"] == 3
    page = c.get("/").text
    assert api[0]["run_id"] in page and ">3<" in page.replace(" ", "")

    detail = c.get(f"/api/runs/{api[0]['run_id']}").json()
    assert detail["trial_count_at_eval"] == 99          # the DSR denominator, surfaced
    assert c.get(f"/runs/{api[0]['run_id']}").status_code == 200


def test_rejected_trials_are_shown_by_default(client):
    c, cfg = client
    from alphalab.ledger import Ledger
    led = Ledger(cfg.run_dir / "ledger.csv", cfg=cfg)
    led.log(stage="discover-eval", name="loser", source="test", fingerprint="x",
            ic_t=0.2, status="rejected", reason="t=0.20<3.0")
    run_id = c.get("/api/runs").json()[0]["run_id"]
    assert "loser" in c.get(f"/runs/{run_id}").text, \
        "hiding rejects hides the denominator, which is how a backtest flatters itself"


# The invariant is not "no writes". It is: the dashboard may never change the
# RULES and never change a RESULT. Exactly two writes pass that test, and both
# happen before evidence exists, so neither can flatter an outcome.
ALLOWED_WRITES = {"/hypotheses", "/api/hypotheses", "/data", "/api/data/sources"}


def test_only_the_two_safe_writes_exist(client):
    c, _ = client
    writes = {(m, r.path) for r in c.app.routes
              for m in getattr(r, "methods", set()) if m not in ("GET", "HEAD", "OPTIONS")}
    assert {m for m, _ in writes} <= {"POST"}, f"no PUT/PATCH/DELETE may exist: {writes}"
    paths = {p for _, p in writes}
    assert paths <= ALLOWED_WRITES, (
        f"a write outside the allowlist would make this a p-hacking console: "
        f"{paths - ALLOWED_WRITES}")


def test_no_route_can_change_a_gate_a_threshold_or_a_result(client):
    c, cfg = client
    before = (cfg.gates.dsr_min, cfg.gates.t_stat_min, cfg.gates.max_nodes)
    for path, body in [("/api/gates", {"dsr_min": 0.1}), ("/api/config", {"dsr_min": 0.1}),
                       ("/api/trials", {"status": "passed"}), ("/api/library", {"status": "active"}),
                       ("/api/runs", {}), ("/api/decay", {})]:
        r = c.post(path, json=body)
        assert r.status_code in (404, 405), f"{path} accepted a write: {r.status_code}"
    assert (cfg.gates.dsr_min, cfg.gates.t_stat_min, cfg.gates.max_nodes) == before


def test_gates_page_shows_every_rule_with_its_live_value(client):
    c, cfg = client
    body = c.get("/api/gates").json()
    names = {g["name"] for g in body["gates"]}
    assert {"Deflated Sharpe", "t-statistic", "AST whitelist", "Look-ahead (future-noise test)",
            "Promotion", "Forward evidence"} <= names
    dsr = next(g for g in body["gates"] if g["name"] == "Deflated Sharpe")
    assert dsr["value"] == str(cfg.gates.dsr_min) and dsr["key"] == "gates.dsr_min"
    assert dsr["rejects"] and dsr["rule"]
    html = c.get("/gates").text
    assert "gates.dsr_min" in html and "cannot change these here" in html


def test_every_table_header_can_explain_itself(client):
    from alphalab.web import glossary
    c, _ = client
    for key in ("dsr", "ic_t", "n_trials_at_eval", "inner_oos_t", "blocking_gate", "clean",
                "retained", "strikes", "reward_rate", "claim_tier"):
        assert glossary.tip(key), f"{key} has no tooltip"
        assert glossary.TERMS[key]["long"], f"{key} has no glossary entry"
    assert c.get("/glossary").status_code == 200
    assert "Deflated Sharpe" in c.get("/glossary").text


def test_a_hypothesis_is_recorded_before_it_is_tested_and_accepted_by_nothing(client):
    c, cfg = client
    why = ("Stocks whose volume is unusually high against their own history mean-revert, "
           "because the liquidity providers absorbing that flow are compensated.")
    form = dict(name="vol_revert_5_60", expr="Mean($volume, 5) / Mean($volume, 60)",
                rationale=why, sign=-1, author="tester")
    r = c.post("/api/hypotheses", data=form)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] is True and len(body["content_sha"]) == 64
    assert body["created_at"] and body["fingerprint"]

    # recording it changes no result: no trial, no library entry, no status
    assert c.get("/api/trials").json() == []
    assert c.get("/api/library").json() == []

    # idempotent on content: the same idea cannot be re-registered with a later timestamp
    again = c.post("/api/hypotheses", data=form).json()
    assert again["created"] is False and again["created_at"] == body["created_at"]


@pytest.mark.parametrize("expr,why", [
    ("$close.__class__", "attribute access is how you escape the sandbox"),
    ("__import__('os')", "imports are how you run code"),
    ("Ref($close, -5)", "a negative shift reads the future"),
])
def test_unsafe_expressions_never_reach_storage(client, expr, why):
    c, _ = client
    r = c.post("/api/hypotheses", data=dict(
        name="bad", expr=expr, sign=1,
        rationale="A long enough rationale to pass the mechanism check, but the formula is unsafe."))
    assert r.status_code == 400, why
    assert c.get("/api/hypotheses").json() == []


def test_a_hypothesis_without_a_mechanism_is_refused(client):
    c, _ = client
    r = c.post("/api/hypotheses", data=dict(name="x", expr="Mean($close, 5)", sign=1,
                                            rationale="looks good"))
    assert r.status_code == 400
    assert "mechanism" in r.json()["detail"]


def test_uploaded_data_is_audited_before_anything_is_written(client, tmp_path):
    c, _ = client
    good = "date,open,high,low,close,volume\n" + "\n".join(
        f"2024-01-{d:02d},10,11,9,10.5,1000" for d in range(1, 29))
    bad = good.replace("2024-01-05,10,11,9,10.5,1000", "2024-01-05,10,11,9,-1,1000")

    r = c.post("/data", data={"name": "probe"},
               files=[("files", ("aaa.csv", bad, "text/csv"))])
    assert r.status_code == 200
    assert "non-positive prices" in r.text and "Nothing was written" in r.text

    r = c.post("/api/data/sources", data={"name": "probe2"},
               files=[("files", ("aaa.csv", good, "text/csv"))])
    body = r.json()
    assert body["problems"] == [] and body["ingested"] is False   # audit-only by default


def test_a_non_csv_upload_is_refused(client):
    c, _ = client
    r = c.post("/api/data/sources", data={"name": "probe"},
               files=[("files", ("payload.py", "import os", "text/x-python"))])
    assert r.status_code == 400 and "csv" in r.json()["detail"].lower()


def test_unknown_run_is_404_not_a_traceback(client):
    c, _ = client
    assert c.get("/api/runs/nope").status_code == 404
    assert c.get("/runs/nope").status_code == 404


def test_decay_page_flags_stale_revalidation(client):
    c, cfg = client
    run_dir = cfg.run_dir
    lib = {"f1": dict(name="f1", status="probation", passes=1, strikes=0, expr="$close",
                      fingerprint="abc", history=[{"ic_t": 3.0}])}
    (run_dir / "library.json").write_text(json.dumps(lib))
    (run_dir / "revalidation.json").write_text(json.dumps(
        dict(promoted=["f1"] * 5, retired=[], library_sha="bad", factors=[
            dict(name="f1", discovery_ic_t=3, recheck_t=2.5, now="active")])) )
    text = c.get("/decay").text
    assert "Stale revalidation artefact" in text


def test_artefact_reads_cannot_escape_the_work_directory(client, tmp_path):
    from alphalab.web import artefacts
    _, cfg = client
    for bad in ("../../etc", "..", "a/b", "/etc/passwd", "x" * 100):
        with pytest.raises(ValueError):
            artefacts.run_dir(cfg, bad)
    with pytest.raises(ValueError):
        artefacts.read(cfg, "not_an_artefact")
