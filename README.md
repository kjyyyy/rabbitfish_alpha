# Alpha Lab

**An LLM-assisted formulaic alpha research lab, built on Microsoft Qlib, with deterministic gates.**
LLM agents propose and critique factor ideas. Plain code decides what survives:
an AST whitelist, complexity and originality limits, multiple-testing hurdles (t ≥ 3, Deflated
Sharpe, PBO), walk-forward validation with realistic costs, validity cards, and hash-stamped
forward signals.

> Research software. It does not place orders and nothing here is financial advice.
>
> **New here? Read [`HARVESTING.md`](HARVESTING.md)** — how the alpha-harvesting process works
> stage by stage, and the research framework behind each gate.
> The default dataset is China A-shares, which UK retail investors cannot easily trade.
> It is a free, survivorship-safe test bed. See `docs/data.md` to port to US or UK data.

## About

A quantitative research lab built to not fool itself. LLM agents propose
factors; Deflated Sharpe, leakage audits and hash-stamped forward pre-registration
decide what survives. Equities, crypto, futures and EU ETS carbon.

Topics: quantitative-finance, algorithmic-trading, factor-investing, backtesting,
qlib, llm-agents, carbon-markets, research-reproducibility

## Why this design

A review of the 2024–26 alpha-mining literature (`docs/research/03-llm-alpha-mining-papers.md`) found:

- LLMs are useful as **researchers that write factor code** (reproducible) and unreliable as
  **traders** (they contradict their own earlier decisions on most steps).
- Most reported "LLM alpha" fails basic validity checks: temporal leakage, no costs, and no
  count of how many ideas were tried (*The Alpha Illusion*, 2026).
- The mechanisms that hold up are cheap: originality and complexity limits, correlation
  de-duplication, factor libraries with re-validation, and strict statistics.

So agents sit upstream and gates sit downstream. See `docs/architecture.md`.

## CLI first, dashboard second

**Harvesting runs in the terminal.** `alphalab discover`, `model`, `cycle`, `forward publish`, and
the rest are CLI commands. They write the research record under `runs/<config-name>/` and into
`runs/alphalab.db`.

**The dashboard is a read-mostly viewer** on that record (`pip install -e ".[web]"` then
`alphalab serve`). It does **not** start discovery or change gates — that is deliberate: a UI that
could re-run until something clears Deflated Sharpe would be a p-hacking console. From the browser
you can **pre-register a hypothesis** and **upload CSVs** (audit, or ingest); everything that
advances the pipeline stays a CLI decision you make and the ledger records.

Product walk and gaps (empty pages, config traps): [`docs/ux-product-fit-gap.md`](docs/ux-product-fit-gap.md).
Stage-by-stage science: [`HARVESTING.md`](HARVESTING.md).

## Quick start

### 1. Install and init

```bash
git clone <your-repo-url> alpha-lab && cd alpha-lab
python -m venv .venv && source .venv/bin/activate      # Windows: use WSL, or .venv\Scripts\activate
pip install -e ".[qlib,llm,dev,web]"                   # add web for the dashboard; or: make setup
alphalab init --stack mock                             # or ollama|vllm|anthropic — writes .env + picks a config
make db                                                # alembic upgrade + status
alphalab doctor -c configs/local_offline.yaml          # data, keys, database, migrations, model endpoints
pytest -q                                              # 206 unit tests, no data, network or model needed
```

Pick one config for the whole session and pass **`-c`** on every command (and on `serve`). Examples:
`configs/cn_csi300.yaml` (default CN), `configs/local_offline.yaml` (mock LLM), or a file from
`alphalab ingest --write-config`.

### 2. Market data (required before discover)

```bash
# Option A — free CSI-300 test bed (~570 MB download)
alphalab download-cn -c configs/cn_csi300.yaml

# Option B — your own OHLCV CSVs (no download; see "Your own data" below)
alphalab ingest --csv ~/prices --write-config configs/mine.yaml
alphalab doctor -c configs/mine.yaml
```

`make offline` uses mock LLMs but **still needs** market data (usually `data/cn_data` from
`download-cn`). Mock is not a substitute for prices.

### 3. Harvest (CLI)

Use the **same `-c`** as your data config throughout.

```bash
export CFG=configs/local_offline.yaml   # or cn_csi300.yaml, configs/mine.yaml, …

alphalab sanity -c $CFG
alphalab discover -c $CFG               # stage 1: screen → evaluate → GP refine → gate
alphalab model -c $CFG                  # stage 2: walk-forward variants + validity cards
alphalab audit -c $CFG                  # how much "alpha" is evaluation convention?
alphalab hierarchy -c $CFG              # family-level testing (cuts effective N)
alphalab revalidate -c $CFG             # recheck library on data it was not discovered on
alphalab validate -c $CFG               # CPCV, overfitting factor, log-wealth, decay, costs
alphalab portfolio-trial -c $CFG --capital 1000000
alphalab forward publish -c $CFG      # pre-register signals before the horizon elapses
alphalab journal -c $CFG
```

One closed loop (optional LLM proposals): `alphalab cycle -c $CFG -n 15` (use `-n 0` to skip the
LLM arm). Shorthand for a mock CN pass: `make offline` (after `download-cn` and with
`local_offline` config).

### 4. View results (dashboard)

Start the server **with the same config name** you harvested — artefacts live in
`runs/<config.name>/`.

```bash
alphalab serve -c $CFG                  # http://127.0.0.1:8000, read-only
```

If Loop, Search, or Library look empty while Runs shows trials, you are usually on the wrong
`-c`, or nothing has passed the gates yet (rejects appear on the run detail page). See
[`docs/ux-product-fit-gap.md`](docs/ux-product-fit-gap.md).

### Your own data

The CN dataset is a free, survivorship-safe test bed, not a recommendation. To run the lab on
data you already have — a broker export, Stooq, Yahoo, a vendor file:

```bash
alphalab ingest --csv ~/prices --write-config configs/mine.yaml    # a directory of SYMBOL.csv
alphalab ingest --csv all.csv --symbol-col ticker --write-config configs/mine.yaml   # one file
alphalab doctor -c configs/mine.yaml && alphalab sanity -c configs/mine.yaml
```

Required columns: `date, open, high, low, close, volume`. `amount` and `vwap` are derived when
absent; `factor` defaults to 1.0. The ingester **refuses** duplicate dates, non-positive prices
and `high < low` rather than ingesting them quietly, and warns about the two things it cannot
detect for you: unadjusted prices and a survivorship-biased file.

`--write-config` emits a ready-to-run config with `topk` scaled to your universe — picking 30 of
40 names is the market, not a portfolio, and the engine's own sanity check fails on it. Verified
end to end from a fresh clone: 43 ingested instruments, no download and no API key, `sanity`
gives oracle +173.6% / random +2.9% / stale oracle −6.8%.

### Your API keys

`alphalab init` writes a git-ignored `.env`; paste keys into it and every command picks them up.
Anything already exported wins over the file, so `docker run -e ...` and CI secrets work
unchanged. No key is ever written to a config, the ledger, the database or a run artefact.

```bash
ANTHROPIC_API_KEY=sk-ant-...        # only if a role uses the anthropic provider
OPENAI_API_KEY=ollama               # any non-empty value for Ollama or vLLM
ALPHALAB_LLM_BASE_URL=...           # optional: override the endpoint without editing YAML
```

`alphalab doctor` reports each of these as set or not set — never the value — along with what is
missing and the command that fixes it.

### Running it entirely locally

```bash
alphalab download-cn -c configs/local_offline.yaml   # required once; mock does not supply prices
make offline          # mock LLM, no API key: sanity → discover → model → audit → journal
make up               # optional: postgres + ollama containers
alphalab llm-check -c configs/local_ollama.yaml   # or configs/local_vllm.yaml (GPU)
```

Storage is SQLite by default (`runs/alphalab.db`) and Postgres by setting `DATABASE_URL`; the
same Alembic migrations run on both. See `docs/production-readiness.md` and `docs/local-models.md`.

### In containers

```bash
make image                                   # build alphalab:0.15.0 (non-root, ~400MB)
docker compose up -d                         # postgres
docker compose --profile local-llm up -d     # + ollama (CPU)
docker compose --profile gpu up -d           # + vllm (NVIDIA GPU)
docker compose run --rm lab discover -c configs/cn_csi300.yaml
```

`runs/` and `data/` are bind-mounted, so the research record stays on the host and readable
without the container. `docs/fit-gap.md` has the full open-source/production assessment and the
prioritised plan; `docs/frontend.md` designs the read-only dashboard (not built yet).

### Adding the AI agents

```bash
cp .env.example .env            # add ANTHROPIC_API_KEY
alphalab propose -n 20          # Claude proposes factors with hypotheses (AST-audited, all logged)
alphalab critique               # a different model family (default: local Ollama) checks hypothesis <-> formula
alphalab discover               # LLM candidates face exactly the same gates as everything else
alphalab journal                # the per-source table shows whether the LLM arm is earning its keep
```

The critic defaults to a local Ollama model (`ollama pull llama3.1:8b`), so the reviewer comes
from a different model family than the proposer. Every call is cached by prompt hash and logged
to `runs/<name>/llm_calls.jsonl`.

### Forward evidence (the only clean test once a holdout has been seen)

```bash
alphalab forward publish        # weekly: score the latest date, write signals + SHA-256 manifest
git add runs/*/forward/*.manifest.json && git commit -m "forward: week N"   # commit BEFORE Monday's open
alphalab forward evaluate       # score every week whose horizon has elapsed
```

## Repository layout

```
src/alphalab/
  expr.py            AST parser/whitelist, canonical form, complexity, zoo overlap, GP operators
  evaluate.py        vectorised rank IC and quintile long-short
  stats.py           t-stats, Deflated Sharpe, PBO (CSCV)
  backtest.py        weekly top-k engine with CN/US/UK cost models
  library.py         factor lifecycle + dynamic-IC combiner
  card.py            validity cards and claim tiers
  evalexpr.py        independent evaluator for the operator language (leakage tests, Qlib cross-check)
  leakage.py         future-noise look-ahead test + numerical validation gates
  families.py        mechanism families, diagnostics, diversity caps
  scheduler.py       Thompson-sampling bandit allocating search effort
  memory.py          GOOD/BAD research memory from the ledger
  neff.py            effective trial count (correlation-adjusted), reported not gated
  audit.py           decision-time protocol audit (execution timing, leaks, survivorship)
  sources/           free data adapters: SEC filings, EDGAR delistings, PIT fundamentals, data QA,
                     ingest.py (your own OHLCV CSVs -> the engine's format)
  governance.py      assumption register + append-only exception log
  db/                SQLAlchemy models, repository, migrations helper
  llm_check.py       verify Ollama / vLLM / Anthropic endpoints
  provenance.py      git SHA + version stamped onto every run
  doctor.py          one-command check: data, keys, database, migrations, endpoints
  init_lab.py        `alphalab init`: .env + a model stack
  env.py             loads .env (the real environment wins)
  retention.py       cache pruning that cannot touch the research record
  logging_setup.py   JSON logs + a heartbeat, so a slow run is not a hung one
  validation.py      CPCV, overfitting factor, log-wealth, delay decay, cost sweep
  breadth.py         IR = IC*sqrt(BR): is this search proportionate to the universe?
  futures/           dated contracts: roll engine, tick costs, margin vs notional vs NAV
  timeseries.py      one-instrument evaluation: Newey-West, breadth of a timing signal
  markets/euets.py   EU ETS carbon: auctions, MSR scarcity, point-in-time policy calendar
  connect/           read-only data in, target positions out. No order path, by design
  web/               read-only dashboard: FastAPI + Jinja2, no Node, no CDN
migrations/          Alembic revisions (SQLite and Postgres)
  risk.py            price-only risk model, style neutralisation, crowding proxy
  portfolio.py       position sizing: bands, caps, impact, long/short, capacity curves
  regime.py          rule-based regime labels (reporting only)
  forward.py         forward pre-registration
  ledger.py          append-only research ledger
  pipeline/          discover.py (stage 1), model.py (stage 2), hierarchy.py, revalidate.py,
                     portfolio_trial.py
  miners/gp.py       genetic-programming refiner
  factors/           written hypotheses, Alpha158 zoo
  agents/            harness.py (LLM client), roles.py (proposer, critic, journal), prompts/
configs/             cn_csi300.yaml (default), us_sp500.yaml, uk_ftse350.yaml, local_* (offline/ollama/vllm)
Dockerfile           two-stage, non-root; docker/entrypoint.sh, docker-compose.yml (profiles)
docs/                architecture, validity card, data, roadmap, research reports
results/             committed result snapshots (runs/ itself is git-ignored)
tests/               unit tests on synthetic data (CI runs these)
```

## Results so far

See `results/`. No discovered factor has ever passed a Deflated-Sharpe test that accounts for
every trial; the strongest in-sample factors lose about two-thirds of their IC after discovery;
and no strategy has earned more than the "research-aid" tier.

The v0.3 portfolio layer produced the two most useful findings so far:

- **No-trade bands** cut turnover from 99% to 79% per rebalance and lifted the information ratio
  from 0.18 to 0.30 — construction beat signal research.
- **62% of the signal was style exposure** (low beta, small, low volatility). Neutralised, the
  remainder does not survive costs. That is factor beta, not alpha.

v0.4 added the harvesting loop (`docs/alpha-harvesting.md`): mechanism families, a bandit
scheduler, research memory, numerical gates and a **dynamic look-ahead test**. It cut the
overfitting probability from 0.30 to 0.04 and rejected 30 degenerate factors that v0.3 scored —
but produced no new alpha.

v0.5 attacked the Deflated Sharpe directly (`docs/deflated-sharpe.md`). Hierarchical testing
works statistically — the price-volume family composite reached DSR 0.999 against 7 family
trials, where the same factor scored 0.29 against 194 flat trials, and the 194 candidates are
effectively only ~3 independent bets. But that composite then earned **−0.4%** in walk-forward
validation. Better statistics, no new performance.

v0.6 measured how much apparent alpha comes from evaluation conventions rather than signal
(`docs/data-sources.md`, `results/v0.6-*`): **assuming zero costs is worth +6.6%/yr and trading
the same close used to compute the signal another +4.5%/yr — over 11 points a year of pure
fiction.** At 3x costs the same strategy makes −5.4%, so the edge lives in a narrow cost band. It also added free, licence-clean
point-in-time fundamentals (SEC as-filed data) and delisting dates (EDGAR Form 25) — the data
upgrade that matters more than any further modelling.

v0.7 added point-in-time fundamentals, data QA and the governance layer (assumption register,
append-only exception log). v0.8 replaced CSV-only storage with SQLAlchemy models and Alembic
migrations, added `alphalab llm-check` and a fully offline `make offline` path. v0.9 containerised
the lab and audited it as an open-source project (`docs/fit-gap.md`).

v0.10 audited the research loop itself (`docs/feedback-loop.md`) and closed three of its open
return paths:

- **The search allocator was rewarded on in-sample significance.** It now learns from a purged
  inner holdout *inside* the discovery window, and records both rates so the gap stays visible.
  They disagree: `liquidity` ranks 1st on held-out evidence and 3rd on in-sample, `reversal`
  falls from 2nd to 6th.
- **`Library.revalidate` had never run outside its own unit test.** `alphalab revalidate` now
  rechecks the library on data it was not discovered on. First run: of 18 factors discovered at
  t = 3.0–6.9, the median recheck t is ~1.2 and five are negative.
- **No forward week had ever been published**, nine versions after the machinery was built. Week 1
  is published, and `forward` now refuses to count any manifest written after its own execution
  close — a file hash proves the file is unchanged, not that the prediction preceded the outcome.

The trial count is now reported as a **hurdle**: after 385 distinct trials, a new candidate needs
an annualised Sharpe of **1.78** to clear DSR 0.95. That bar was raised by searching, not by
learning.

Capacity for the best construction is roughly **£1–10m**; below that, market impact is almost
free, which is the one structural advantage a small book has (`docs/institutional-gap.md`).

## The dashboard

```bash
pip install -e ".[web]" && alphalab serve -c configs/cn_csi300.yaml   # same -c as your harvest
```

**It does not replace the CLI.** Opening `http://127.0.0.1:8000` without running discover/model
first shows empty harvest pages; that is normal. Run the pipeline in section 3, then serve with
matching `-c`.

Ten pages over the same data the CLI uses — nothing is recomputed, so the screen cannot disagree
with the ledger. Four of them exist to close the loop rather than report it:

- **Loop** — every library factor, the one gate blocking it, and what it has against what it needs
- **Search** — where the GP budget went, with the held-out reward rate beside the old in-sample
  rate, so a family buying effort with significance it cannot reproduce is visible
- **Decay** — the retirement queue: discovery t against recheck t, strikes and passes
- **Versions** — runs grouped by the commit that produced them, joined to committed snapshots

Three more explain the machinery rather than the results: **Gates** states all 15 rules in the
order they apply, each with its live value and the config key that sets it; **Glossary** defines
every column, because "DSR 0.72" read as "72% chance this works" is a serious misreading;
**Hypotheses** and **Data** are the only two things the dashboard can write.

**The invariant is not "no writes" — it is that no write may change a rule or a result.**
Pre-registering a hypothesis and adding a data source both happen *before* any evidence exists,
so neither can flatter an outcome; a pre-registered idea is hashed, timestamped and accepted by
nothing, facing every gate when `discover` next runs. Thresholds, statuses and the ledger are
read-only from here, permanently, and tests enforce it: no `PUT`/`PATCH`/`DELETE` may exist,
`POST` paths must sit inside a four-entry allowlist, and posting to `/api/gates` must fail.

Gates are deliberately not editable in the UI. A slider that relaxes a threshold after you have
seen what it rejected is the most efficient way to manufacture a false discovery. Changing a gate
is a config edit, which changes the config hash, which marks every later run as a different
experiment — that trail is the control. It binds to localhost and has no auth — see
`SECURITY.md` before exposing it.

## Licence

MIT. Third-party attribution, dependency licences and data-licence constraints
are in [`NOTICE.md`](NOTICE.md).
