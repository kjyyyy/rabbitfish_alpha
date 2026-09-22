# Minimal frontend design

> **Built in v0.12.** This page is the design; the deviations from it are recorded in
> "What was actually built" at the end, because a design doc that quietly matches whatever
> shipped is worth nothing.


**Recommendation: CLI-first, with a small read-only web dashboard.** The CLI stays the way work
is done. The dashboard exists because three questions are genuinely painful in a terminal —
*what has this run actually tried?*, *how does this factor's Deflated Sharpe move as the trial
count grows?*, and *which protocol exceptions were logged against the numbers I'm looking at?* —
and painless in a table you can sort.

Nothing about the research changes. If the dashboard is deleted, every number is still reachable
with `alphalab journal`, `alphalab db status` and the JSON artefacts in `runs/`.

## Stack

| Layer | Choice | Why |
|---|---|---|
| Server | **FastAPI** + **uvicorn** | Already a Pydantic codebase, so request/response models are free. Gives a JSON API and HTML from one app, and `TestClient` tests run offline like the rest of the suite |
| Templates | **Jinja2** | Server-rendered. No build step, no bundler, no Node |
| Interactivity | **HTMX** (~14KB, vendored) | Sorting, filtering and pagination as `hx-get` attribute swaps. No client-side state to keep in sync with the server |
| Styling | **Pico.css** (~10KB, vendored) | Class-less CSS: semantic HTML looks like a dashboard with no design work |
| Charts | **matplotlib → PNG endpoints** | Already a dependency (`MPLBACKEND=Agg` is set in the image). The chart code in `scripts/make_charts.py` is reused rather than reimplemented in JS |
| Packaging | `pip install -e ".[web]"` | New optional extra: `fastapi`, `uvicorn[standard]`, `jinja2`. HTMX and Pico are **vendored into `web/static/`**, not loaded from a CDN, so the dashboard works air-gapped |

Total new runtime dependencies: three. No Node, no npm, no `package.json`, no build step, no
second language, and the whole thing runs inside the existing image on the port the Dockerfile
already exposes.

### Alternatives considered

- **Streamlit** — fastest to a first screen, and a fair choice if you never want a JSON API. Rejected
  because it owns the process, duplicates the data-access layer in script form, is awkward to test,
  and cannot serve machine-readable output to a script or a notebook.
- **React / Next.js** — a Node toolchain, a build step, a second language and a bundle to keep
  current, in exchange for interactivity this dashboard does not need.
- **Grafana / Superset** — built for time-series metrics and BI, not for "show me the 194 formulas
  this run tried and why each was rejected". Would need a metrics store that does not exist.
- **Jupyter** — already available and better for ad-hoc analysis. Not a substitute for a page you
  can leave open during a two-hour run.

## Design constraints

1. **Read-only.** No endpoint mutates anything. No `POST`, no run launching, no gate editing. A UI
   that can re-run discovery until something clears is a p-hacking console; the whole repo exists
   to prevent that. Launching runs stays a CLI/cron decision.
2. **Every statistic appears beside its trial count.** Deflated Sharpe is meaningless without N.
   The trials table shows `n_trials_at_eval` in the row, and the run header shows the run's total.
   `/api/stats/treadmill` plots N over time, because a bar that rises with every search is a fact
   the operator needs in front of them, not a footnote.
3. **Rejects are first-class.** The default trial view is *all* trials, not survivors. The
   rejection reason is a column, not a detail page.
4. **Loopback only, no auth.** Bound to `127.0.0.1:8000`. If it ever needs to leave the laptop,
   that is a reverse proxy plus a decision about auth, not a code change here.
5. **No secrets in responses.** The API serves the DB and whitelisted JSON artefacts by name.
   `run_id` and artefact names are validated against a pattern — never joined into a path
   unchecked — and `.env`, `llm_calls.jsonl` and anything outside `workdir` are never served.

## Pages

| Page | Route | Contents |
|---|---|---|
| **Runs** | `/` | Every run: id, config name, config SHA, git SHA, started, trial count, distinct formulas, status. Newest first. Links into each run |
| **Run detail** | `/runs/{run_id}` | Header: config, SHAs, date range, **total trials (the DSR denominator)**, effective N. Tabs: **Trials** (sortable/filterable table — name, family, source, stage, IC mean, t, DSR, N at eval, status, reason), **Validity cards** (claim tier, P1/P2/P5, Sharpe CI, break-even cost, decay haircut, regime breakdown), **Assumptions** (the register for this config), **Exceptions** (append-only protocol deviations) |
| **Factor library** | `/library` | Lifecycle view: probation / active / retired, fingerprint, expression, family, first seen, last re-validated, live IC vs discovery IC. The decay column is the point |
| **Leakage & protocol audit** | `/audit` | The audit league table: each convention's excess/yr and IR against the causal baseline, with uplift. Plus the synthetic fundamentals-timing bias. This is the page to show anyone who asks whether the backtest is honest |
| **Hierarchy** | `/hierarchy` | Family composites tested against N=families, survivors, best within-family, and the same factor's DSR against the flat N — the v0.5 result, on a screen |
| **Forward evidence** | `/forward` | Pre-registered weeks: publish date, manifest SHA, horizon, whether it has elapsed, realised IC. The only clean evidence in the repo, so it gets its own page |

### Loop pages (added after the v0.9 loop audit — see `docs/feedback-loop.md`)

The six pages above answer *what happened*. These four answer *what happens next*, which is what
makes the dashboard a feedback loop rather than a log viewer.

| Page | Route | Contents | Why it exists |
|---|---|---|---|
| **Loop status** | `/loop` | Every candidate in the library and every family, as a state machine: current stage (screened → evaluated → probation → active → forward-registered → forward-evidenced), the **one gate currently blocking it**, the value it needs vs the value it has (`DSR 0.72 / 0.95`), and for forward-registered names the weeks elapsed of the weeks required | The "reach the next stage" view. Today nothing in the repo can answer "what would promote this factor?" |
| **Search allocation** | `/search` | Per family: GP budget spent, in-sample hit rate (what the bandit rewards), **out-of-period hit rate side by side**, and the divergence between them. Plus the bandit's Beta posteriors | This page would have surfaced the bandit defect at v0.4. A reward signal you cannot see is a reward signal you cannot audit |
| **Decay & retirement** | `/decay` | Library factors: discovery IC vs trailing live IC, strikes against them, the retirement queue, and time since last recheck | Makes the one-way door visible: 18 factors, all in probation, none rechecked |
| **Versions** | `/versions` | Runs grouped by `alphalab_version` + `git_sha`: headline metrics per version, deltas against the previous one, and which config SHA each used. Diff two versions' assumption registers and exception logs | Answers "did v0.5 beat v0.4?" without reading six hand-written `RESULTS.md` files. Only possible since runs record their provenance (v0.9) |

Ten pages. Each is one Jinja template plus one route.

## API

Every page is HTML over the same data the JSON API serves, so scripts and notebooks get the
identical view. Read-only throughout.

| Method | Path | Params | Returns |
|---|---|---|---|
| GET | `/api/health` | — | `{status, version, db, migration_head, runs_dir}` — backs the container health check |
| GET | `/api/runs` | `limit`, `offset` | Run rows with trial counts |
| GET | `/api/runs/{run_id}` | — | One run + summary counts (trials, distinct formulas, passed, rejected, exceptions) |
| GET | `/api/runs/{run_id}/trials` | `stage`, `status`, `family`, `source`, `min_dsr`, `sort`, `limit`, `offset` | Trial rows, always with `n_trials_at_eval` |
| GET | `/api/runs/{run_id}/cards` | — | Validity cards (`runs/<name>/cards/*.json`) |
| GET | `/api/runs/{run_id}/assumptions` | — | The assumption register written by `governance.write_register` |
| GET | `/api/runs/{run_id}/exceptions` | — | `protocol_exceptions` rows for this config |
| GET | `/api/runs/{run_id}/hierarchy` | — | `hierarchy.json`: family results, survivors, effective-trials report |
| GET | `/api/runs/{run_id}/audit` | — | `protocol_audit.json`: baseline + variant uplifts |
| GET | `/api/library` | `config`, `status` | Library factors with lifecycle state |
| GET | `/api/library/{fingerprint}` | — | One factor: expression, family, history, every trial that ever evaluated it |
| GET | `/api/forward` | `config` | Forward manifests and realised outcomes |
| GET | `/api/stats/summary` | — | Repo-wide: runs, trials, distinct formulas ever evaluated, library size. The honest global trial count |
| GET | `/api/loop` | `config` | Per candidate: stage, blocking gate, `have` vs `need`, forward weeks elapsed/required |
| GET | `/api/search/allocation` | `config` | Per family: budget spent, in-sample hit rate, out-of-period hit rate, Beta posterior, divergence |
| GET | `/api/decay` | `config` | Library factors with discovery IC, trailing live IC, strikes, last recheck |
| GET | `/api/versions` | — | Runs grouped by `alphalab_version`/`git_sha` with headline metrics |
| GET | `/api/versions/{a}/compare/{b}` | — | Metric deltas, assumption-register diff, exception diff between two versions |
| GET | `/api/stats/treadmill` | `config` | Cumulative distinct trials over time and the DSR hurdle each implies |
| GET | `/charts/{run_id}/{name}.png` | — | Server-rendered matplotlib figure, name whitelisted |

Data sources: the database for `runs`, `trials`, `library_factors`, `protocol_exceptions` and
`forward_signals`; whitelisted JSON artefacts under `cfg.workdir` for cards, `hierarchy.json`,
`protocol_audit.json` and the assumption register. Nothing is recomputed in the web layer — the
dashboard must never be able to disagree with the CLI.

## Shape

```
src/alphalab/web/
  __init__.py
  app.py            create_app(cfg) -> FastAPI; mounts /api, /static, pages
  api.py            the JSON routes above (SQLAlchemy queries via db/repo.py)
  artefacts.py      whitelisted, traversal-safe reads of runs/<name>/*.json
  charts.py         matplotlib -> PNG, reusing scripts/make_charts.py
  templates/        base.html, runs.html, run_detail.html, library.html,
                    audit.html, hierarchy.html, forward.html
  static/           pico.min.css, htmx.min.js (vendored, no CDN)
tests/test_web.py   TestClient: every route 200s on an empty DB and on a seeded one
```

New CLI verb, consistent with the rest:

```bash
alphalab serve --host 127.0.0.1 --port 8000 -c configs/cn_csi300.yaml
```

and in compose, the already-drafted `api` service (`--profile app`) runs exactly that.

## Effort

**L (5–7 days)** for all ten pages. Roughly: 1 day for the app skeleton, health route, runs list
and run detail; 1 day for the trials table with HTMX sorting/filtering plus the library page;
1 day for audit, hierarchy and forward; 1.5 days for the four loop pages; half a day for charts;
1 day for tests and docs. The API is the larger half, and it is the half worth building first —
it is useful from `curl` and a notebook before a single template exists.

Build order within the task: `/api/health` → runs → run detail → **`/loop` and `/search`** →
library and decay → audit/hierarchy/forward → versions. The two loop pages come early because
they are the ones that change behaviour; the rest are reporting.

**One dependency worth stating:** `/loop`, `/search` and `/decay` render state that does not exist
yet. `/search` needs the out-of-period hit rate the bandit does not currently record (task 12),
`/decay` needs revalidation to run (task 13), and `/loop`'s forward column needs at least one
published forward week (task 11). Build those first or the pages render honest but empty tables —
which is itself better than a page that implies evidence that was never gathered.


---

## What was actually built (v0.12)

Ten pages, twenty JSON endpoints, `alphalab serve`, 30 tests. Three deviations from the design
above, all deliberate:

1. **No Pico.css, no HTMX.** The design said vendor both. The lab has to run air-gapped, and
   pulling third-party assets into the repo to get table sorting was a poor trade: `static/style.css`
   is ~70 hand-written lines with light and dark themes, `static/app.js` ~35 lines of vanilla
   JavaScript for filtering and sorting. Total third-party frontend code: none.
2. **`/versions` replaced the separate compare endpoint.** Grouping runs by `alphalab_version`
   and `git_sha` and joining the committed `results/*/summary.json` answers "did v0.5 beat v0.4?"
   directly; a pairwise diff endpoint would have added a route to answer the same question worse.
3. **Charts are deferred.** The treadmill renders as a table with CSS bars. A matplotlib PNG
   endpoint is still the right way to do the curves, and it is not worth blocking the release.

Two bugs that only a real run could find, both now regression-tested:

- **Every page 422'd** because `from __future__ import annotations` turned `request: Request`
  into a string that FastAPI resolves against *module* scope, where the lazily-imported name does
  not exist — so it silently reclassified the parameter as a query field. The future import is
  now absent from `web/app.py`, with a comment saying why.
- **Three pages 500'd against the real record while passing on an empty database**: Jinja's
  `min`/`max` are iterable filters, not clamps, and `float(Undefined)` raises for a run that
  predates a field. Both replaced with a `width` filter and a total-catch `num` filter.

### Security posture

Read-only is enforced by a test that asserts the app exposes no verb but `GET`/`HEAD`. Artefact
names are whitelisted and config names pattern-matched, with a test that path traversal raises.
It binds to `127.0.0.1` and has no authentication, which is stated in `SECURITY.md` rather than
assumed.


## Explaining itself, and the two permitted writes (v0.13)

The first release answered *what happened* but never said what a column meant, never showed what
a gate actually was, and wrote nothing at all. Three additions:

**Every column defines itself.** `web/glossary.py` holds 30 terms — definition, why it is on
screen, and the function or config key that produced the number. Each is the tooltip on its own
column header (59 headers annotated) and a row on `/glossary`. The point is not decoration: "DSR
0.72" read as "72% chance this works" is a serious misreading, and the tooltip says plainly that
it is the probability of beating the luckiest of N noise trials.

**Every gate states its rule, its live value and its source.** `/gates` lists all 15 in the order
they apply — screen, evaluate, gate, search, library, claim — each with the rule in plain words,
the value read from the live config object, the config key or source file that sets it, and what
it rejects. It reads the same `Config` the pipeline does, so it cannot drift from what is
enforced.

**Gates are still not editable here, and that is the design.** A slider that relaxes a threshold
after you have seen which candidates it rejected is the most efficient way to manufacture a false
discovery. Changing a gate is a config edit; a config edit changes the config hash; the hash
marks every later run as a different experiment. That trail is the control. If a single run must
deviate, `alphalab exception` records it append-only and it surfaces on the validity card.

### The invariant, restated

Not "no writes" — **no write may change a rule or a result.** Two actions pass that test and both
strengthen the discipline rather than weakening it:

| Write | Why it is safe | Guard |
|---|---|---|
| Pre-register a hypothesis (`POST /hypotheses`) | It precedes the evidence, so it cannot be reworded to match a result | AST whitelist, complexity, originality and a mechanism of at least a sentence, all before storage; hashed and timestamped; idempotent on content; accepted by nothing — it faces every gate when `discover` runs |
| Add a data source (`POST /data`) | Ingestion happens before any evidence exists | Audited on upload (duplicate dates, non-positive prices, `high < low`); audit-only by default; refuses to overwrite an existing source; non-CSV refused |

Enforced by tests: no `PUT`/`PATCH`/`DELETE` may exist, `POST` paths must be inside a four-entry
allowlist, posting to `/api/gates`, `/api/config`, `/api/trials` or `/api/library` must 404 or
405, and an unsafe expression must never reach storage.
