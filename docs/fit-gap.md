# Fit–gap analysis and enhancement plan (v0.8 → v0.9)

Scored against one question: **can a stranger clone this repo and have it running on a laptop in
ten minutes, with or without a GPU, without a cloud account?** Verdict: *almost*. The research
core is in better shape than the packaging around it. Two of the gaps below were breaking a fresh
clone outright.

Legend: ✅ works · ⚠️ works but thin · ❌ missing

---

## A. Open-source friendliness

| Item | Status | Notes |
|---|---|---|
| Licence | ✅ | MIT at the root; third-party licence notes in the README (Qlib MIT; AlphaGen/AlphaForge re-implemented, not copied; MiroFish AGPL deliberately unused) |
| README | ✅ | Purpose, quick start, layout, honest results. Better than most research repos |
| Changelog | ✅ | `CHANGELOG.md`, one entry per version |
| Package layout | ✅ | `src/` layout, `pyproject.toml`, console script, extras (`qlib`, `llm`, `postgres`, `dev`) |
| Tests | ✅ | 83 offline tests, no data/network/model needed — the single best property of this repo |
| CI | ⚠️ | ruff + migrations + pytest on 3.10–3.12. Does **not** build the image, does not run the `qlib` extra, does not run pre-commit, no `alembic check` |
| **Version discipline** | ❌→✅ | `pyproject.toml` and `__init__.py` said **0.2.0** while the README and results said v0.8. Fixed: both now `0.9.0`. Still no git tags or GitHub releases |
| **Fresh-clone integrity** | ❌→✅ | **`data` was a committed symlink to `/home/claude/data`.** Every clone got a dangling link into someone else's home directory, and `.gitignore`'s `data/` never applied because the path was already tracked. Untracked; `/data` added to `.gitignore` |
| **Repo cleanliness** | ❌→✅ | Ten `runs_*.log` transcripts were committed at the root. Untracked and ignored |
| Reproducible installs | ❌ | Dependencies are open ranges (`pandas>=2.2`). No lock/constraints file, so two clones a month apart get different scientific libraries — unacceptable in a repo whose output is a statistic |
| Contribution docs | ❌ | No `CONTRIBUTING.md`, `SECURITY.md`, issue/PR templates, or code of conduct |
| Typing | ⚠️ | Type hints throughout, but no `py.typed` marker and no mypy in CI |
| Distribution | ❌ | Not on PyPI, no published image. Install is `git clone` + `pip install -e .` |

**Verdict:** genuinely open-source in licence and in spirit. The defects were mechanical rather
than architectural, which is the good kind. The remaining one that matters is the lock file.

## B. Docker and containerisation

| Item | Status | Notes |
|---|---|---|
| Dockerfile for the lab | ❌→✅ | Did not exist; only the *services* were containerised. Drafted — see `Dockerfile` |
| `.dockerignore` | ❌→✅ | Absent, so `docker build` would have shipped `runs/`, `data/` (570MB) and `.env` into the context. Drafted |
| Compose services | ⚠️→✅ | Postgres/Ollama/vLLM existed but with `:latest` tags, no app service, no profiles separating dev from prod-like, ports on `0.0.0.0`, no restart policies, no health check on Ollama or vLLM |
| Image provenance | ⚠️ | Base pinned to `python:3.11.9-slim-bookworm`, service images pinned to exact tags. Digest pinning documented but not applied (cannot be verified offline in this container) |
| Non-root | ✅ (drafted) | uid/gid 10001, fixed so bind-mounted `runs/` keeps predictable host ownership |
| Migrations on boot | ✅ (drafted) | `ALPHALAB_AUTO_MIGRATE=1` in the entrypoint, explicitly documented as single-writer-only |
| Image build in CI | ❌ | Nothing verifies the Dockerfile still builds |

**Blocker discovered by writing the draft:** `LLM.critic_base_url` defaults to
`http://localhost:11434/v1`. Inside compose, `localhost` is the *lab* container, not Ollama.
The compose file passes `ALPHALAB_LLM_BASE_URL=http://ollama:11434/v1`, but **nothing reads that
variable yet** — `config.py` has no env override. Task 7 closes this; until then the containerised
LLM arm only works with `network_mode: host`.

## C. Database and migrations

| Item | Status | Notes |
|---|---|---|
| ORM models | ✅ | SQLAlchemy 2.0 declarative, six tables, sensible uniqueness (`run_id, stage, name, fingerprint`) and the `(cik, tag, filed)` index the point-in-time read path needs |
| Alembic | ✅ | `migrations/`, two revisions, `render_as_batch=True` so SQLite handles constraint changes like Postgres |
| Both engines | ✅ | SQLite default (`runs/alphalab.db`, WAL + foreign keys), Postgres via `DATABASE_URL`, same migrations |
| CI coverage | ✅ | `upgrade head` → `downgrade base` on every push |
| Model/migration drift | ❌ | No `alembic check`. Edit a model, forget the revision, and CI stays green |
| **Write-path integrity** | ⚠️ | `Ledger._to_db` swallows every exception (`except Exception: ...`) to protect the CSV write. Correct priority, wrong consequence: the DB can silently diverge from the CSV, and the DB is what answers "how many trials have I run?" — the denominator of every Deflated Sharpe in the repo |
| Connection tuning | ⚠️ | No pool sizing or `pool_pre_ping` for Postgres; a dropped connection kills a long run |
| Backup / retention | ❌ | No policy for `runs/`; the evaluation cache and `llm_cache.sqlite` grow without bound |
| Concurrency | ⚠️ | SQLite is single-writer. Two discovery runs at once need Postgres — documented, not enforced |

**Verdict:** the strongest section. This was v0.8's job and it was done properly. The gap that
carries scientific weight is the silent dual-write, not the schema.

## D. Local LLM integration

| Item | Status | Notes |
|---|---|---|
| Provider abstraction | ✅ | Anthropic / any OpenAI-compatible endpoint / deterministic `mock`. Ollama and vLLM need config only, no code |
| Ready-made configs | ✅ | `local_offline.yaml`, `local_ollama.yaml`, `local_vllm.yaml` |
| Endpoint verification | ✅ | `alphalab llm-check` does a real structured-output round trip and reports latency, cached latency and the failure reason |
| Fully offline path | ✅ | `make offline` runs the whole suite with `provider: mock`, no network, no key — verified end to end |
| Caching | ✅ | SQLite prompt-hash cache + JSONL call log; re-runs are free and byte-identical |
| Different-family critic | ✅ | Proposer and critic default to different families, which is the point |
| **Timeouts** | ❌ | No `timeout=` on either client. A wedged Ollama hangs a discovery run indefinitely, with no heartbeat to notice |
| **Retries** | ❌ | No backoff on 429/5xx/connection reset. One transient failure aborts the run |
| **Spend cap** | ❌ | Nothing bounds tokens or cost per run. `alphalab cycle -n 200` against a paid API is unbounded |
| Env override for `base_url` | ❌ | See section B — hardcoded `localhost` breaks inside containers |
| Cache retention | ❌ | `llm_cache.sqlite` is per run dir and never pruned |

**Verdict:** the design is right (provider-agnostic, local-first, cache-reproducible). The
robustness layer is missing, and that is what turns an unattended overnight run into a hang.

## E. Frontend / UI

Nothing exists. Full design in **`docs/frontend.md`**; the recommendation, since you asked for it
explicitly: **CLI-first, with a small read-only server-rendered dashboard.** FastAPI + Jinja2 +
HTMX + Pico.css — no Node, no build step, no second language, ships inside the same image, works
offline. Not React, not a SPA: a single-developer research lab does not need a build toolchain to
render six tables, and every hour spent on a frontend is an hour not spent on the science.

One design constraint, which is a research constraint rather than a UI one: **the dashboard is
read-only and shows every trial by default, never only the survivors.** A UI that lets you sort
by Deflated Sharpe and re-run until something clears is a p-hacking console. The trial count must
be on screen beside any statistic that depends on it.

## F. Production-readiness checklist

| Dimension | Status | Notes |
|---|---|---|
| Packaging | ✅ | src layout, extras, console script |
| Licence & provenance | ✅ | MIT, third-party notes |
| Tests | ✅ | 83, offline, fast |
| CI | ⚠️ | No image build, no `alembic check`, no coverage gate |
| Reproducible builds | ❌ | No lock file (task 5) |
| Containerisation | ✅ (drafted) | Dockerfile, entrypoint, `.dockerignore`, profiled compose |
| Schema & migrations | ✅ | Both engines, round-tripped in CI |
| Config | ✅ | YAML + pydantic, SHA-stamped into every run |
| Secrets | ✅ | Env/`.env` only, gitignored, `detect-private-key` hook, `.dockerignore` excludes `.env` |
| Local-first | ✅ | `make offline` needs no network, no key, no GPU |
| Structured logging | ❌ | `print()` to stdout. An unattended run is unreadable after the fact (task 6) |
| Metrics / heartbeat | ❌ | No way to tell a slow run from a hung one (task 6) |
| Error handling | ⚠️ | Dual-write swallows DB errors silently (task 8) |
| Timeouts & retries | ❌ | LLM calls have neither (task 7) |
| Resource limits | ❌ | No spend cap, no memory limit in compose |
| Retention | ❌ | `runs/`, eval cache and LLM cache grow forever (task 8) |
| Concurrency | ⚠️ | Single-writer on SQLite; Postgres path exists |
| Observability of the *research* | ✅ | Assumption register, append-only ledger, exception log, validity cards, forward manifests — better than the engineering observability |
| Release process | ❌ | No tags, no published artefacts (task 10) |
| **Order execution** | n/a | The lab has never placed an order and is not meant to. Research record with a paper-trading path |

---

## Prioritised enhancement plan

Effort: **S** ≤ half a day · **M** 1–2 days · **L** 3–5 days.

| # | Task | Files | Effort | Depends on |
|---|---|---|---|---|
| 1 | **Repo hygiene** — untrack the `data` symlink and the ten `runs_*.log` files, align versions | `.gitignore`, `pyproject.toml`, `src/alphalab/__init__.py` | S | — |
| 2 ✅ | **Dependency lock** — `pip-compile` the full tree into `constraints.txt`; use it in the Docker build and CI | `constraints.txt`, `Makefile`, `Dockerfile`, `ci.yml` | S | 1 |
| 3 | **Dockerfile + entrypoint** | `Dockerfile`, `docker/entrypoint.sh`, `.dockerignore` | M | 2 |
| 4 | **Compose rewrite** — app service, profiles, pinned tags, health checks, loopback ports | `docker-compose.yml`, `Makefile`, `.env.example` | S | 3 |
| 5 ✅ | **CI hardening** — build the image, run `make offline` inside it, add `alembic check`, run pre-commit | `.github/workflows/ci.yml` | S | 3, 4 |
| 6 ✅ | **LLM robustness** — timeouts, bounded retry with backoff, per-run token/spend cap, `ALPHALAB_LLM_BASE_URL` env override (unblocks the containerised LLM arm) | `agents/harness.py`, `config.py`, `llm_check.py`, `tests/test_agents.py` | M | — |
| 7 ✅ | **Structured logging + heartbeat** — stdlib `logging` with a JSON formatter, `--log-format json`, a progress line every N candidates carrying run id, stage, elapsed, count | new `logging_setup.py`, `cli.py`, `pipeline/*.py` | M | — |
| 8 ✅ | **Storage integrity + retention** — `alphalab db verify` reconciling CSV ↔ DB and failing loudly on divergence; stop swallowing DB errors silently (log at ERROR, count them, surface in `journal`); `alphalab clean --older-than` for caches | `ledger.py`, `db/maintenance.py`, `cli.py`, `tests/test_db.py` | M | — |
| 9 ✅ | **Read-only API + dashboard** — see `docs/frontend.md` | new `web/` package, `cli.py` (`serve`), `pyproject.toml` (`web` extra) | L | 3, 4 (to ship in the image), 8 (clean data) |
| 10 ✅ | **Release plumbing** — `CONTRIBUTING.md`, `SECURITY.md`, issue/PR templates, git tags, GHCR image publish on tag | `.github/`, `CONTRIBUTING.md`, `SECURITY.md` | S | 5 |

### Order of work

**1 → 2 → 3 → 4 → 5** first: this is the "a stranger can run it" block, it is mostly mechanical,
and everything else is easier to verify once CI builds and runs the image. Tasks 1, 3 and 4 are
already done in this commit; 2 and 5 are the remainder.

**6 → 7** next. These are what make an unattended overnight `alphalab cycle` trustworthy, and
task 6 also unblocks the local-LLM path inside containers, which is currently broken.

**8** before **9**, deliberately: the dashboard reads the database, so the database should be
known-consistent with the CSV mirror before anything renders numbers from it. Shipping a UI on
top of a silently-diverging write path would put a wrong trial count on a screen, and the trial
count is the denominator of every Deflated Sharpe in the repo.

**9** last among the engineering tasks, and **10** alongside it.

### Loop-closing tasks (added after the v0.9 loop audit — `docs/feedback-loop.md`)

The ten tasks above make the repo runnable by a stranger. These six make it *learn*. The audit
found that most of the harvesting loop's return paths are open: the bandit is rewarded on
in-sample significance, revalidation is dead code, and no forward week has ever been published.

| # | Task | Files | Effort | Depends on |
|---|---|---|---|---|
| 11 ✅ | **Publish forward week 1.** One command, committed before Monday's open, then weekly. Nine versions of machinery and zero out-of-sample evidence is the biggest gap in the repo, and it is the only task here that produces *evidence* rather than infrastructure | `runs/<cfg>/forward/` (no code change) | S | — |
| 12 ✅ | **Fix the bandit reward.** Add an inner purged split inside the discovery window; reward families on the inner holdout, not on in-sample `t ≥ 3`. Record both rates so the divergence stays visible. Do **not** reward on `later_ic_mean` — that spends the validation window on search | `pipeline/discover.py`, `scheduler.py`, `config.py`, `tests/test_harvesting.py` | M | — |
| 13 ✅ | **Wire up revalidation.** `alphalab revalidate` calling the existing, tested `Library.revalidate`; promote probation → active on sustained out-of-period IC, retire on two strikes. Record every recheck | `library.py`, `cli.py`, `db/models.py` (+migration), `tests/test_library.py` | M | — |
| 14 | **Close the forward → priors arrow.** Feed `forward.evaluate` results into the library status, the bandit posterior and research memory, so realised evidence changes what gets proposed next | `forward.py`, `memory.py`, `scheduler.py` | M | 11, 12, 13 |
| 15 ✅ | **Machine-readable version snapshots.** Write `results/<version>/summary.json` on every model run (headline metrics + config SHA + git SHA) so two versions can be diffed by code rather than by reading markdown | `pipeline/model.py`, `provenance.py` | S | done: runs now record provenance |
| 16 ✅ | **A stopping rule.** Per config: a trial budget, the DSR hurdle it implies, and a loud warning when the marginal candidate cannot clear the bar the search itself created | `stats.py`, `pipeline/discover.py`, `card.py` | S | — |

**Status (v0.12): every task on this plan is done except 14.** Tasks 1–13 and 15–19 have
shipped. **14** (forward evidence feeding back into the library, the bandit and research memory)
is not startable yet: it needs clean forward weeks, and the first one cannot exist until the
dataset is refreshed and a signal is published before its own execution close. That is a calendar
dependency, not an engineering one.

Three tasks were added in v0.11 that were not on the original list, because the review asked
whether a user can *start* — and the answer was no:

| # | Task | Status |
|---|---|---|
| 17 | **`.env` was never loaded.** `.env.example` had told users to put keys there since v0.2 and nothing read the file; every documented LLM path silently required a manual `export` | ✅ `env.py`, with the real environment winning over the file |
| 18 | **`alphalab init` + `alphalab doctor`** — scaffold a `.env` and a stack, then check data, keys, database, migrations and endpoints in one command, each failure printing the command that fixes it | ✅ |
| 19 | **`alphalab ingest`** — bring your own OHLCV CSVs instead of the 570MB CN download, with an audit that refuses duplicate dates, non-positive prices and `high < low` | ✅ |

**Original order:** **11 first, today** (it costs one command and starts a clock that cannot be
started retroactively), then 12 → 13 → 15 → 16, then the engineering block 2 → 5, then 14, then
the dashboard (9) with its loop pages, then 6 → 7 → 8 → 10.

The dashboard moves *after* 12, 13 and 15 deliberately: `/search`, `/decay` and `/versions`
render state those tasks create. Building the pages first produces four honest but empty tables.

### What this plan deliberately does not do

- **No cloud services, no managed anything.** Every task above runs on a laptop with pip or Docker.
- **No auth, no multi-tenancy, no job queue in the UI.** A read-only dashboard bound to loopback
  needs none of it. If the dashboard ever needs to *launch* runs, that is a job-queue problem
  (Celery/RQ + a worker) and a different decision, not a feature to bolt on.
- **No new science.** None of this makes a factor work. The honest summary of `results/` is
  unchanged: nothing has yet passed a Deflated Sharpe test that counts every trial.
