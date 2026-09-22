# Changelog

## v0.15 - EU ETS carbon, and the geometry a one-instrument market needs

Research: `docs/research/06-eu-ets-data-and-specs.md`. Engineering: `docs/eu-ets.md`.

- **`timeseries.py`** - the lab's cross-sectional path requires more than 30 instruments per date
  and silently produces nothing below that, so it is *undefined* on a one-instrument market.
  This is the other geometry: Newey-West t-statistics (a 20-day forward return sampled daily
  shares 19 days with its neighbour and inflates a naive t by roughly sqrt(h)), a non-overlapping
  cross-check, the number of genuinely independent bets a timing signal makes per year, and a
  comparison against simply holding the thing.
- **`markets/euets.py`** - ICE/EEX contract mechanics (1,000 allowances per lot, EUR 0.01 tick =
  EUR 10/lot, physically delivered, last Monday LTD); the MSR supply rule; auction cover ratio,
  discount-to-secondary and bidder breadth as signals with stated mechanisms; and a
  `PolicyCalendar` that stores the ACTUAL release date of each figure, because verified emissions
  appear in early April but on a date that moves year to year - so a fixed lag is itself a
  look-ahead bug.
- **The auction parser refuses to guess.** The EEX schema could not be verified (the proxy
  returned 403 and no EEX page documents the columns), so a near-match raises rather than passing
  a plausible-but-wrong series. `SCHEMA_UNVERIFIED` stays True until someone opens the file.
- **Recorded, not backlogged:** carry, calendar spreads, basis momentum and fuel switching are
  **not computable on free data** for EU ETS - no free licence-clean futures settlement curve was
  found, and the best free price source carries auction clearing prices with no term structure.
  Those are the best-evidenced mechanisms, so this is a real constraint.
- **`scripts/euets_demo.py`** runs the whole path on synthetic data. Two findings, neither
  expected: a signal only works at a horizon matching its own memory (the planted effect peaks at
  a 10-day horizon against an 11-day signal memory and is gone by 20); and a horizon sweep is a
  search - four signals across five horizons is **20 trials**, and its best result, a pure-noise
  calendar countdown at Sharpe 0.54, scores **DSR 0.837 as a lone hypothesis and 0.060 counting
  the sweep**.

206 tests (was 190).


## v0.14 - crypto and futures: the methodology, and a claim that failed its own test

Research report in `docs/research/05-crypto-and-futures-alpha-fit.md`; engineering consequences
in `docs/crypto-and-futures.md`; the whole approach is now documented in `HARVESTING.md`.

**Validation corrections** (`validation.py`, `alphalab validate`) - all five apply to every market:
- **CPCV**: a walk-forward Sharpe is one draw from a distribution. On this lab's own best
  strategy: walk-forward +0.64, CPCV p05 **-0.42**, and a **21% chance of a negative Sharpe** on a
  held-out block.
- **Overfitting Factor** (CFM arXiv:1902.01802): halve the backtest Sharpe. That strategy scores
  **0.27 against the 0.7 threshold** and FAILS.
- **Log-wealth test**: a strategy can have a significantly positive mean and still compound to a
  loss under fat tails. The chosen strategy does not compound.
- **Lagged-signal decay** (Maven) and a **cost sweep** that reads the engine's own per-multiplier
  runs rather than adding a synthetic drag to already-costed returns - which would double-charge.

**Futures and perpetuals** (`futures/`): a roll engine keeping timing, splicing and return
chaining separate, with the invariant that a ratio-adjusted series and the chained wealth curve
must agree to a constant; look-ahead guards on liquidity-based roll rules; a warning when a
back-adjusted series crosses zero; refusal to hold past first notice day; tick-denominated costs;
the roll charged as the round trip it is; funding as a holding cash flow with the sign convention
stated; and notional, margin and NAV tracked separately.

**Connectivity** (`connect/`): read-only data sources and a hash-stamped target-position
interface. **No order path, and a test asserts it against the parsed syntax tree.** MetaMask is
documented as the wrong tool for automated trading, with the custody hierarchy and blast radii.

**Breadth** (`breadth.py`) - and a correction to my own first version of it:
- The claim that a thin universe inflates in-sample false positives was **tested and not
  supported**: best-of-200 Sharpe is ~0.9-1.2 at every universe width, out-of-sample ~0 at all.
- What the experiment does establish: the breadth penalty depends on the kind of book. A common
  factor collapses LONG-ONLY breadth (25 futures -> ~6 bets, matching the CTA literature) but
  cancels for a CROSS-SECTIONAL one (~23 bets). The first version of this diagnostic reported only
  the raw figure and concluded the lab's equity search was disproportionate. Corrected: 653
  CSI-300 names are 6.6 long-only bets but **97.2 market-neutral bets**, so that search is in fact
  proportionate at 3.7 trials per bet.
- Residual penalty, which is the real argument: identical skill (IC 0.03) earns an IR of **2.98**
  in the wide cross-section, **1.04** in commodity futures, **0.57** in a thin book - while the
  trial count deflating the result is the same in each.

**Market profiles**: `asset_class` (equity/crypto/futures) now drives the calendar, the cost model
and a pre-committed structural sanity ceiling on gross Sharpe.

190 tests (was 147).


## v0.13 - the dashboard explains itself, and writes exactly two things

- **Every column defines itself.** `web/glossary.py`: 30 terms with a definition, why the number
  is on screen, and the function or config key that produced it. Attached as a tooltip to 59
  table headers and listed on `/glossary`. "DSR 0.72" now says what it is - the probability of
  beating the luckiest of N noise trials - rather than inviting the reading "72% chance this
  works".
- **`/gates`**: all 15 gates in the order they apply (screen, evaluate, gate, search, library,
  claim), each with its rule in plain words, the value read from the live config object, the
  config key or source file that sets it, and what it rejects. It reads the same `Config` the
  pipeline does, so it cannot drift from what is enforced.
- **The read-only invariant is now precise, and stricter where it matters.** Not "no writes" but
  "no write may change a rule or a result". Two writes pass that test:
  - **`POST /hypotheses`** - pre-register an idea before testing it. Screened through the AST
    whitelist, complexity, originality and a required economic mechanism *before* storage, then
    hashed and timestamped, idempotent on content, and accepted by nothing: it faces every gate
    when `discover` next runs and counts toward the trial count that deflates every Sharpe.
  - **`POST /data`** - upload OHLCV CSVs, audited on the way in (duplicate dates, non-positive
    prices, `high < low`), audit-only by default, refusing to overwrite an existing source.
  Gates remain uneditable from the UI on purpose: relaxing a threshold after seeing what it
  rejected is how a false discovery is manufactured. `alphalab exception` remains the way to
  record a deliberate deviation.
- Tests enforce it: no `PUT`/`PATCH`/`DELETE` may exist, `POST` paths must be inside a four-entry
  allowlist, posting to `/api/gates`, `/api/config`, `/api/trials` or `/api/library` must 404 or
  405, and unsafe expressions (`$close.__class__`, `__import__`, `Ref($close, -5)`) must never
  reach storage.
- Migration `9d011d75fa42`: a `hypotheses` table, unique on content per config.
- 147 tests (was 137).


## v0.12 - the dashboard, structured logs, and a release process

Every task in `docs/fit-gap.md` is now done except 14, which is waiting on a calendar, not code.

- **`alphalab serve`**: a read-only dashboard and JSON API - FastAPI + Jinja2, ten pages, twenty
  endpoints, no Node, no build step and no CDN (70 lines of hand-written CSS, 35 of vanilla JS).
  Four pages close the loop rather than report it: **Loop** (the one gate blocking each factor,
  have vs need), **Search** (held-out reward rate beside the old in-sample rate), **Decay** (the
  retirement queue) and **Versions** (runs grouped by the commit that produced them). Read-only
  is enforced by a test asserting the app exposes no verb but GET/HEAD, and artefact reads are
  whitelisted with a path-traversal test.
- Two bugs only a real run could find: every page 422'd because `from __future__ import
  annotations` made FastAPI reclassify `request: Request` as a query field; three pages 500'd
  against the real record while passing on an empty database, because Jinja's `min`/`max` are
  iterable filters rather than clamps and `float(Undefined)` raises.
- **Structured logging** (task 7): `--log-format json`, one object per line carrying run id,
  config, version and commit, plus a `progress` heartbeat with elapsed time, rate and ETA - so a
  slow discovery run is distinguishable from a hung one.
- **`-c` before the subcommand never worked.** The shared parent-parser idiom let the subparser
  write its default over the value, so `alphalab -c mine.yaml discover` silently ran the default
  config - a documented feature since v0.8. Fixed with `default=argparse.SUPPRESS` and a
  regression test that reproduces the bug and then the fix.
- `ingest --write-config` now writes an absolute `provider_uri`: a relative one resolves against
  the current directory, so the same config worked from one folder and not another.
- **Release plumbing** (task 10): `CONTRIBUTING.md` (including the rule that most contributions
  should make results worse), `SECURITY.md`, issue and PR templates, and a tagged release
  workflow that refuses to publish unless the tag matches the package version and the suite,
  ruff and `alembic check` all pass.
- 137 tests (was 98).


## v0.11 - start in one command, on your own data

**`.env` was never loaded.** `.env.example` has told users to copy it and add a key since v0.2,
and nothing ever read the file: keys only worked if the user happened to `export` them by hand.
`env.py` closes that, with the usual precedence - a variable already in the environment beats the
file, so `docker run -e ...` and CI secrets still win.

- **`alphalab init`** writes a git-ignored `.env` and picks a stack (`mock`, `ollama`, `vllm`,
  `anthropic`), then prints the next commands. It is dispatched before the config is loaded,
  because it exists for the case where no config exists yet.
- **`alphalab doctor`** checks python, extras, data (and freshness), `.env`, keys, database,
  migration head, disk and both model endpoints - each failure printing the command that fixes
  it. Keys are reported as set or not set, never echoed.
- **`alphalab ingest`** takes a directory of `SYMBOL.csv` files or one long CSV and writes the
  engine's on-disk format directly (Qlib's `dump_bin` is not in the wheel). Verified by reading
  the result back through Qlib: values match the source CSV to float32. It refuses duplicate
  dates, non-positive prices and `high < low`, and warns about unadjusted prices and
  survivorship - the two things it cannot detect for you.
- **LLM harness hardened** (task 6): request timeouts, bounded exponential backoff that retries
  only what is retryable (a 401 is not), per-run call and token budgets that cached calls never
  consume, a clear "pip install -e '.[llm]'" when an SDK is missing, and
  `ALPHALAB_LLM_BASE_URL` / `ALPHALAB_CRITIC_BASE_URL` overrides - which unblocks the
  containerised LLM arm, where `localhost` is the lab container rather than Ollama.
- **`alphalab db verify`** (task 8) reconciles the CSV ledger against the database and fails
  loudly on divergence, because the database holds the trial count that every Deflated Sharpe
  deflates against. Ledger DB failures are now counted and named rather than mentioned once.
- **`alphalab clean`** (task 8): retention for the evaluation, feature and LLM caches - 4.7 GB
  had accumulated here with no policy. It cannot touch the ledger, database, library, forward
  manifests or `results/`.
- **`constraints.txt`** (task 2): 208 packages pinned by `make lock`, used by the Docker build.
  The CI matrix stays unpinned on 3.10-3.12 to catch upstream breakage early.
- **CI** (task 5): `alembic check` for model/migration drift, a Docker build job that runs the
  entrypoint and migrations in the image, a pre-commit job, and a `byod` job that generates
  CSVs, ingests them and reads them back through Qlib - the new-user path, with no download.
- `alphalab ingest --write-config` writes a ready-to-run config with `topk` scaled to the
  universe. Found by running it: the first generated config kept `topk: 30` for a 43-name
  universe, so the book was most of the market and the engine's sanity check failed (oracle
  +1.0% vs random +4.1%). Scaled, it passes: oracle +173.6%, random +2.9%, stale oracle -6.8%.
- 98 tests (was 87).


## v0.10 - closing the research loop

Audit in `docs/feedback-loop.md`; five planned tasks implemented.

- **Search allocator rewarded on evidence it did not fit.** `splits.inner_holdout_years`
  (default 2) reserves the last two years of the discovery window; the bandit is rewarded on that
  purged inner holdout instead of in-sample `t >= 3`, with the reward sign taken from the inner
  training slice. Both rates are recorded (`bandit.divergence()`), and they disagree: `liquidity`
  ranks 1st on held-out evidence vs 3rd in-sample, `reversal` falls 2nd -> 6th, `trend` rises from
  zero wins to 5th. Gate behaviour is unchanged - only allocation moved.
- **`alphalab revalidate`**: the library is rechecked on post-discovery data. Two consecutive
  strong rechecks promote probation -> active, two weak ones retire. First run on 18 factors
  discovered at t = 3.0-6.9: median recheck t ~1.2, five negative, nothing moved on one check.
  Re-running on the same window is refused (`already_checked`), because two "consecutive" checks
  of identical sessions is one piece of evidence counted twice - which happened here on the first
  attempt and moved twelve factors before the guard existed.
- **Forward week 1 published**, and `forward evaluate` now refuses any manifest written after its
  own execution close. A file hash proves the file is unchanged, not that the prediction preceded
  the outcome. Week 1 is honestly marked `clean: false`: the dataset ends on the signal date.
- **Trial budget and hurdle** (`stats.hurdle_sharpe`, `mining.trial_budget`): after 385 distinct
  trials a new candidate needs an annualised Sharpe of **1.78** to clear DSR 0.95. Reported on
  every discovery run.
- **Machine-readable snapshots**: `results/v<version>-<date>/summary.json` with headline metrics,
  failed checks, config SHA and commit, written on every model run.
- Fixes: `forward evaluate` wrote a headerless empty CSV that crashed the next model run;
  `_forward_stats` now tolerates it. Leftover `_alembic_tmp_trials` table dropped.
- Migrations `803d3db11492` (run provenance) and `4002058acc4e` (inner-holdout metrics on trials).
- 87 tests (was 83).


## v0.9 - containerisation, repo hygiene, and the fit-gap assessment

- **Fixed a broken fresh clone**: `data` was a committed symlink to an absolute path in the
  author's home directory, and ten `runs_*.log` transcripts were tracked at the root. Both
  untracked and ignored.
- **Version drift fixed**: `pyproject.toml` and `__init__.py` said 0.2.0 while the repo was v0.8.
  Both now 0.9.0.
- **`Dockerfile`**: two-stage build, venv copied from builder, non-root uid 10001, `libgomp1` for
  LightGBM, tini, health check, optional `ALPHALAB_AUTO_MIGRATE`, plus `.dockerignore`.
- **`docker-compose.yml` rewritten**: app (`cli`/`app`) services, `local-llm` and `gpu` profiles,
  exact image tags instead of `:latest`, health checks on every service, ports bound to loopback,
  optional `.env`.
- **`make lock` / `make image`**, and `up` reworked for the new profiles.
- **`docs/fit-gap.md`**: section-by-section assessment (open-source, Docker, DB, local LLM, UI,
  production checklist) and a prioritised 10-task plan with effort and dependencies.
- **`docs/frontend.md`**: design for a read-only FastAPI + HTMX dashboard - stack justification,
  six pages, thirteen endpoints. Deliberately not built yet; the CLI remains the interface.
- Known gap documented rather than fixed: `critic_base_url` defaults to `localhost`, which is the
  lab container inside compose. `ALPHALAB_LLM_BASE_URL` is passed but not yet read by `config.py`.


## 0.8.0 - 2026-09-21
- **Storage**: SQLAlchemy models + Alembic migrations (`runs`, `trials`, `library_factors`, `protocol_exceptions`, `forward_signals`, `fundamentals`). SQLite by default, Postgres via `DATABASE_URL`; CSV kept as a human-readable mirror. `alphalab db upgrade|status|import-csv`.
- Trials are unique on `(run_id, stage, name, fingerprint)` - double-logging a candidate is now impossible, which is what keeps the DSR trial count honest.
- **Local models**: `alphalab llm-check` (real structured-output round trip, latency, cache), ready-made Ollama and vLLM configs, docker-compose services for postgres/ollama/vllm.
- **Fully offline**: `configs/local_offline.yaml` + `make offline` run the whole suite with a mock model and no network.
- `Makefile` (setup, db, test, data, offline, cycle, up/down), `-c/--config` now works before or after the subcommand.
- CI applies and reverts migrations on a clean database.
- 83 tests.

## 0.7.0 - 2026-09-21
- `sources/fundamentals.py`: point-in-time fundamentals table with `as_of()` (filters on filing date), reporting lag, restatement-aware ordering, winsorising.
- `factors/fundamental.py`: 8 pre-registered fundamental hypotheses with rationales and expected signs.
- `sources/qa.py`: data-hardening report (reporting-lag distribution, coverage, restatements, outliers) with a `problems()` warning list.
- `governance.py` + `alphalab register` / `alphalab exception`: assumption register written on every model run, append-only exception log, both surfaced on validity cards.
- Audit extended: zero-cost and punitive-cost toggles, plus an offline measurement of the fundamentals period-end join.
- Findings: zero costs manufacture +6.6%/yr (IR +0.48), same-day execution +4.5%/yr; a period-end fundamentals join steals +0.08 IC at a 45-day lag and +0.17 at 90 days.
- 74 tests.

## 0.6.0 - 2026-09-21
- `audit.py` + `alphalab audit`: decision-time protocol audit. Toggles execution timing, centred windows, global normalisation and survivors-only universe against a strictly causal baseline.
- `sources/sec_fsds.py`: SEC Financial Statement Data Sets adapter - free, as-filed (point-in-time) US fundamentals keyed on filing date.
- `sources/delistings.py`: Form 25 / 25-NSE parser from EDGAR's free full index - delisting dates so dead names stay in the universe.
- `docs/data-sources.md`: registry of free, licence-clean data with what each buys and what it is not.
- Finding: same-day execution manufactures +4.5%/yr and +0.32 IR. Survivorship bias is near-zero on CN A-shares (they rarely delist) - not a clean bill of health for a US port.
- 63 tests.

## 0.5.0 - 2026-09-21
- `neff.py`: effective-trial estimates (eigenvalue participation ratio, average-correlation adjustment). Reported alongside the raw count; gating still uses the raw count.
- `alphalab hierarchy`: family-level testing first, then within-family search, with same-factor DSR under both trial counts.
- New strategy variants: G Ledoit-Wolf shrinkage combiner, H family composite, I multi-horizon ensemble (1/5/10-day).
- `family` recorded in the ledger.
- Finding: the family composite passes DSR 0.999 at family level and earns -0.4% in walk-forward validation. See `docs/deflated-sharpe.md`.
- 59 tests.

## 0.4.0 - 2026-09-21
- `evalexpr.py`: an independent evaluator for the operator language (also cross-checks Qlib).
- `leakage.py`: future-noise perturbation test (dynamic look-ahead detection) + numerical validation gates (invalid/extreme ratio, coverage, near-constant cross-sections).
- `families.py`: deterministic mechanism-family classification, per-family diagnostics and a diversity cap at library admission.
- `scheduler.py`: Beta-Bernoulli Thompson sampling allocating GP effort across families.
- `memory.py`: GOOD/BAD research memory derived from the ledger by code, injected into the proposer prompt.
- `alphalab cycle`: one closed research loop (propose -> critique -> discover -> model -> memory -> journal).
- Dual IC reporting (rank and Pearson); evaluation cache keyed by formula fingerprint.
- Fixed: Pearson IC index misalignment (10x speedup), numerical checks on membership panels, GP crash with a single parent, PBO with short-history candidates.
- 55 tests (24 new).

## 0.3.0 - 2026-09-20
- `risk.py`: price-only factor model (beta, size, volatility, momentum, liquidity), cross-sectional alpha neutralisation, specific volatility, Khandani-Lo crowding proxy.
- `portfolio.py`: bounded rank weights, dollar-neutral long/short, no-trade bands, per-name and participation caps, square-root market impact (AQR calibration), short financing, volatility targeting, capacity curves.
- `alphalab portfolio-trial`: six-rung construction ladder + capacity curve + style diagnostic.
- Market-neutral books are now scored against cash, not the index.
- Fixed: ADV units (CN volume is in 100-share lots; `$amount` is now the source), rank-based banding, deflated Sharpe crash on short series.
- 36 tests (5 new for portfolio construction and neutralisation).

## 0.2.0 - 2026-09-20
- Restructured into an installable package (`src/alphalab`) with the `alphalab` CLI, YAML configs, CI and an MIT licence.
- AST expression parser with whitelist, canonical form, complexity and zoo originality (replaces the regex auditor).
- GP refiner; factor library lifecycle; dynamic-IC combiner; regime breakdown.
- LLM harness (Anthropic, OpenAI-compatible/Ollama, mock), plus proposer, critic and journal agents.
- Validity cards with claim tiers; forward pre-registration with SHA-256 manifests.
- Holdout 2025–26 marked `holdout_burned: true` (viewed in v0.1).

## 0.1.0 - 2026-09-20
- First prototype (see `results/v0.1-2026-09-20/`).
