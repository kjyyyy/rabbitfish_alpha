"""The read-only dashboard: JSON API + server-rendered pages, one app.

Read-only on purpose. A UI that can launch discovery runs and sort by Deflated
Sharpe until something clears is a p-hacking console, and this repo exists to
prevent exactly that. There is no POST here, and there is no button that starts
a run: that stays a CLI decision a human makes and the ledger records.

No build step, no Node, no CDN: the CSS is ~150 hand-written lines served from
`static/`, and the little interactivity there is (client-side table filtering)
is a few lines of vanilla JavaScript. That deviates from the original design,
which vendored Pico.css and HTMX - dropped because a research tool that must
run air-gapped should not carry third-party assets it does not need.
"""
# NOTE: no `from __future__ import annotations` here on purpose. FastAPI resolves
# a route's annotations against the MODULE namespace; with postponed evaluation the
# lazily-imported `Request` is only a string that module scope cannot resolve, so
# FastAPI silently reclassifies it as a query parameter and every page 422s.
from pathlib import Path
from urllib.parse import quote

from ..config import Config
from ..provenance import stamp
from . import artefacts
from . import gates as G
from . import glossary as GL
from . import queries as Q
from . import writes as W

HERE = Path(__file__).resolve().parent

PAGES = [("/", "Runs"), ("/loop", "Loop"), ("/search", "Search"), ("/library", "Library"),
         ("/decay", "Decay"), ("/audit", "Audit"), ("/hierarchy", "Hierarchy"),
         ("/forward", "Forward"), ("/versions", "Versions"),
         ("/gates", "Gates"), ("/hypotheses", "Hypotheses"), ("/data", "Data"),
         ("/glossary", "Glossary")]


def create_app(cfg: Config):
    try:
        from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
        from fastapi.responses import HTMLResponse, RedirectResponse
        from fastapi.staticfiles import StaticFiles
        from fastapi.templating import Jinja2Templates
    except ImportError as e:                     # pragma: no cover
        raise SystemExit("the web extra is not installed: pip install -e '.[web]'") from e

    app = FastAPI(title="Alpha Lab", docs_url="/api/docs", redoc_url=None)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    tpl = Jinja2Templates(directory=str(HERE / "templates"))
    tpl.env.filters["num"] = _num
    tpl.env.filters["width"] = _width
    tpl.env.globals["tip"] = GL.tip                 # every column header explains itself

    def page(request, template, **ctx):
        return tpl.TemplateResponse(request, template,
                                    dict(pages=PAGES, cfg=cfg, path=request.url.path, **ctx))

    # ------------------------------------------------------------ api ------
    @app.get("/api/health")
    def health():
        s = Q.summary(cfg)
        return dict(status="ok", config=cfg.name, runs=s["runs"], trials=s["trials"], **stamp())

    @app.get("/api/runs")
    def api_runs(limit: int = 50, offset: int = 0):
        return Q.runs(cfg, limit, offset)

    @app.get("/api/runs/{run_id}")
    def api_run(run_id: str):
        r = Q.run_detail(cfg, run_id)
        if r is None:
            raise HTTPException(404, "no such run")
        return r

    @app.get("/api/runs/{run_id}/trials")
    def api_trials(run_id: str, stage: str | None = None, status: str | None = None,
                   family: str | None = None, source: str | None = None,
                   min_dsr: float | None = None, sort: str = "-ic_t",
                   limit: int = Query(200, le=2000), offset: int = 0):
        return Q.trials(cfg, run_id, stage, status, family, source, min_dsr, sort, limit, offset)

    @app.get("/api/trials")
    def api_all_trials(stage: str | None = None, status: str | None = None,
                       family: str | None = None, source: str | None = None,
                       min_dsr: float | None = None, sort: str = "-ic_t",
                       limit: int = Query(200, le=2000), offset: int = 0):
        return Q.trials(cfg, None, stage, status, family, source, min_dsr, sort, limit, offset)

    @app.get("/api/stats/summary")
    def api_summary():
        return Q.summary(cfg)

    @app.get("/api/stats/treadmill")
    def api_treadmill():
        return Q.treadmill(cfg)

    @app.get("/api/loop")
    def api_loop(config: str | None = None):
        return Q.loop(cfg, config)

    @app.get("/api/search/allocation")
    def api_search(config: str | None = None):
        return Q.search_allocation(cfg, config)

    @app.get("/api/decay")
    def api_decay(config: str | None = None):
        return Q.decay(cfg, config)

    @app.get("/api/library")
    def api_library(config: str | None = None, status: str | None = None):
        rows = Q.library(cfg, config)
        return [r for r in rows if not status or r["status"] == status]

    @app.get("/api/audit")
    def api_audit(config: str | None = None):
        return Q.audit(cfg, config)

    @app.get("/api/hierarchy")
    def api_hierarchy(config: str | None = None):
        return Q.hierarchy(cfg, config)

    @app.get("/api/forward")
    def api_forward(config: str | None = None):
        return Q.forward(cfg, config)

    @app.get("/api/cards")
    def api_cards(config: str | None = None):
        return Q.cards(cfg, config)

    @app.get("/api/exceptions")
    def api_exceptions(config: str | None = None):
        return Q.exceptions(cfg, config)

    @app.get("/api/versions")
    def api_versions():
        return Q.versions(cfg)

    @app.get("/api/glossary")
    def api_glossary():
        return GL.entries()

    @app.get("/api/gates")
    def api_gates():
        return dict(gates=G.describe(cfg), config=G.config_file_hint(cfg))

    @app.get("/api/hypotheses")
    def api_hypotheses():
        return W.list_hypotheses(cfg)

    @app.post("/api/hypotheses")
    def api_preregister(name: str = Form(...), expr: str = Form(...),
                        rationale: str = Form(...), sign: int = Form(1),
                        author: str = Form("")):
        """Permitted write #1: recording an idea BEFORE it is tested.

        This cannot flatter a result - it precedes one - and it is accepted by
        nothing: the hypothesis faces every gate when `discover` next runs.
        """
        try:
            return W.preregister_hypothesis(cfg, name, expr, rationale, sign, author)
        except W.Rejected as e:
            raise HTTPException(400, str(e)) from None

    @app.get("/api/data/sources")
    def api_sources():
        return _sources(cfg)

    @app.post("/api/data/sources")
    async def api_add_source(name: str = Form(...), ingest: bool = Form(False),
                             files: list[UploadFile] = File(...)):
        """Permitted write #2: adding data, which happens before any evidence exists."""
        blobs = [(f.filename or "x.csv", await f.read()) for f in files]
        try:
            return W.add_data_source(cfg, blobs, name, audit_only=not ingest)
        except W.Rejected as e:
            raise HTTPException(400, str(e)) from None

    # ---------------------------------------------------------- pages ------
    @app.get("/", response_class=HTMLResponse)
    def p_runs(request: Request):
        return page(request, "runs.html", runs=Q.runs(cfg), summary=Q.summary(cfg),
                    treadmill=Q.treadmill(cfg))

    @app.get("/runs/{run_id}", response_class=HTMLResponse)
    def p_run(request: Request, run_id: str, status: str | None = None):
        d = Q.run_detail(cfg, run_id)
        if d is None:
            raise HTTPException(404, "no such run")
        return page(request, "run.html", run=d,
                    trials=Q.trials(cfg, run_id, status=status, limit=500),
                    cards=Q.cards(cfg), exceptions=Q.exceptions(cfg), status=status)

    @app.get("/loop", response_class=HTMLResponse)
    def p_loop(request: Request):
        lib = artefacts.read(cfg, "library", default={}) or {}
        reval = artefacts.read(cfg, "revalidation", default={}) or {}
        return page(request, "loop.html", rows=Q.loop(cfg), forward=Q.forward(cfg),
                    revalidation=Q._revalidation_stale(cfg, None, lib, reval))

    @app.get("/search", response_class=HTMLResponse)
    def p_search(request: Request):
        return page(request, "search.html", data=Q.search_allocation(cfg))

    @app.get("/library", response_class=HTMLResponse)
    def p_library(request: Request):
        return page(request, "library.html", rows=Q.library(cfg))

    @app.get("/decay", response_class=HTMLResponse)
    def p_decay(request: Request):
        return page(request, "decay.html", data=Q.decay(cfg))

    @app.get("/audit", response_class=HTMLResponse)
    def p_audit(request: Request):
        return page(request, "audit.html", data=Q.audit(cfg))

    @app.get("/hierarchy", response_class=HTMLResponse)
    def p_hierarchy(request: Request):
        return page(request, "hierarchy.html", data=Q.hierarchy(cfg))

    @app.get("/forward", response_class=HTMLResponse)
    def p_forward(request: Request):
        return page(request, "forward.html", data=Q.forward(cfg))

    @app.get("/versions", response_class=HTMLResponse)
    def p_versions(request: Request):
        return page(request, "versions.html", rows=Q.versions(cfg))

    @app.get("/glossary", response_class=HTMLResponse)
    def p_glossary(request: Request):
        return page(request, "glossary.html", terms=GL.entries())

    @app.get("/gates", response_class=HTMLResponse)
    def p_gates(request: Request):
        return page(request, "gates.html", gates=G.describe(cfg),
                    conf=G.config_file_hint(cfg))

    @app.get("/hypotheses", response_class=HTMLResponse)
    def p_hypotheses(request: Request, ok: str | None = None, err: str | None = None):
        return page(request, "hypotheses.html", rows=W.list_hypotheses(cfg), ok=ok, err=err)

    @app.post("/hypotheses", response_class=HTMLResponse)
    def p_preregister(request: Request, name: str = Form(...), expr: str = Form(...),
                      rationale: str = Form(...), sign: int = Form(1), author: str = Form("")):
        try:
            res = W.preregister_hypothesis(cfg, name, expr, rationale, sign, author)
            msg = (f"Recorded as {res['receipt']}" if res["created"]
                   else f"Already recorded at {res['created_at']} ({res['content_sha'][:16]}) "
                        f"- pre-registration is idempotent on content")
            return RedirectResponse(f"/hypotheses?ok={quote(msg)}", status_code=303)
        except W.Rejected as e:
            return RedirectResponse(f"/hypotheses?err={quote(str(e))}", status_code=303)

    @app.get("/data", response_class=HTMLResponse)
    def p_data(request: Request):
        return page(request, "data.html", sources=_sources(cfg), result=None)

    @app.post("/data", response_class=HTMLResponse)
    async def p_add_data(request: Request, name: str = Form(...), ingest: str = Form(""),
                         files: list[UploadFile] = File(...)):
        blobs = [(f.filename or "x.csv", await f.read()) for f in files]
        try:
            result = W.add_data_source(cfg, blobs, name, audit_only=(ingest != "on"))
        except W.Rejected as e:
            result = dict(error=str(e))
        return page(request, "data.html", sources=_sources(cfg), result=result)

    return app


def _sources(cfg: Config) -> list[dict]:
    """Every provider directory the lab can see, with what it contains."""
    import json
    out = []
    for base in (Path("data"), Path(cfg.market.provider_uri).parent):
        if not base.is_dir():
            continue
        for d in sorted(base.iterdir()):
            cal = d / "calendars" / "day.txt"
            if not cal.is_file():
                continue
            days = cal.read_text().split()
            meta = {}
            if (d / "ingest_meta.json").is_file():
                try:
                    meta = json.loads((d / "ingest_meta.json").read_text())
                except json.JSONDecodeError:
                    meta = {}
            row = dict(path=str(d), name=d.name, sessions=len(days),
                       start=days[0] if days else "", end=days[-1] if days else "",
                       instruments=meta.get("instruments"),
                       ingested=bool(meta),
                       in_use=str(d) == str(Path(cfg.market.provider_uri)))
            if row["path"] not in {r["path"] for r in out}:
                out.append(row)
    return out


def _num(v, digits: int = 3, pct: bool = False):
    """Format a number, or '-' for anything that is not one.

    Deliberately catch-all: Jinja hands this `Undefined` for a key a dict does
    not have, and `float(Undefined)` raises. A dashboard must not 500 because
    one run predates a field.
    """
    try:
        if v is None or v == "":
            return "-"
        f = float(v)
    except Exception:                             # noqa: BLE001 - Undefined, str, anything
        return "-"
    if f != f:                                    # NaN
        return "-"
    return f"{f:+.2%}" if pct else f"{f:,.{digits}f}"


def _width(v, of=1.0):
    """Clamp a fraction to a 0-100 bar width. Jinja's min/max are iterable
    filters, not clamps, so doing this in the template silently raises."""
    try:
        pct = 100.0 * float(v or 0) / float(of or 1)
    except Exception:                             # noqa: BLE001
        return 0
    return max(0, min(100, round(pct)))


def serve(cfg: Config, host: str = "127.0.0.1", port: int = 8000, reload: bool = False):
    import uvicorn
    print(f"alphalab dashboard on http://{host}:{port}  (read-only; config '{cfg.name}')")
    uvicorn.run(create_app(cfg), host=host, port=port, log_level="info")
