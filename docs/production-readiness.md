# Production readiness: an honest assessment

> Superseded in part by **`docs/fit-gap.md`** (v0.9), which scores the same ground section by
> section and carries the prioritised plan. This page remains the record of what v0.8 changed.

Scored against what "open source and production friendly" usually means. The gaps found in this
review were fixed in v0.8 where cheap; the rest are listed as gaps rather than glossed over.

| Dimension | Before v0.8 | Now |
|---|---|---|
| Packaging | `pyproject.toml`, src layout, pinned extras, console script | unchanged — fine |
| Licence | MIT, with third-party licence notes in the README | unchanged — fine |
| Tests | 74 offline tests, no data or network needed | **83**, including migrations and storage |
| CI | GitHub Actions on 3.10–3.12, ruff + pytest | unchanged — fine |
| **Persistence** | **CSV and JSON files only. No schema, no constraints, no concurrent writers** | **SQLAlchemy models + Alembic migrations; SQLite by default, Postgres via `DATABASE_URL`** |
| **Migrations** | **none** | **`migrations/`, two revisions, upgrade/downgrade both tested in CI** |
| Local run | worked, but undocumented setup order | `make setup`, `make db`, `make test`, `make offline` |
| **Local models** | Ollama reachable via config, undocumented and unverified | **`alphalab llm-check`, ready-made Ollama and vLLM configs, docker-compose services** |
| Fully offline | partial (needed an API key for the LLM arm) | **`make offline` runs the whole suite with a mock model and no network** |
| Secrets | `.env.example`, keys read from env, `detect-private-key` pre-commit hook | unchanged — fine |
| Config | YAML + pydantic validation, hashed into every run | unchanged — fine |
| Reproducibility | assumption register, append-only ledger, prompt-hash caching | now also queryable in SQL |
| Observability | logs to stdout, JSON artefacts per run | **gap**: no structured logging or metrics |
| Packaging for deploy | none | **gap**: no Dockerfile for the lab itself (only for its services) |
| Secrets management | env vars | **gap**: no vault integration; fine for a solo operator |

## Storage: what the database buys

The CSV ledger was the single weakest part of the repo. It is kept as a human-readable mirror,
but the record now also lives in a real schema:

- `runs`, `trials`, `library_factors`, `protocol_exceptions`, `forward_signals`, `fundamentals`
- `trials` is unique on `(run_id, stage, name, fingerprint)`, so double-logging a candidate is
  impossible — which is what keeps the Deflated-Sharpe trial count honest
- `fundamentals` carries `period` and `filed` with an index on `(cik, tag, filed)`, so the
  point-in-time read path is a fast query rather than a convention
- questions like "how many distinct formulas have ever been evaluated, across every run" are one
  query (`alphalab db status` shows 243 today, across 264 logged trials)

```bash
make db                    # alembic upgrade head + status
alphalab db import-csv     # backfill from existing CSV mirrors, idempotent
DATABASE_URL=postgresql+psycopg://user:pass@host/db make db     # same migrations on Postgres
```

Migrations use `render_as_batch=True`, so SQLite handles constraint changes the same way
Postgres does — verified by the round trip in `tests/test_db.py`.

## Local models: Ollama and vLLM

Both serve an OpenAI-compatible API, so the existing `openai` provider drives either with no
code change — only config. Ready-made profiles ship in `configs/`:

```bash
make up PROFILE=local-llm                   # postgres + ollama   (v0.9 profile names)
docker compose exec ollama ollama pull llama3.1:8b
alphalab llm-check -c configs/local_ollama.yaml

make up PROFILE=gpu                         # vLLM (needs an NVIDIA GPU)
alphalab llm-check -c configs/local_vllm.yaml
```

`llm-check` runs a real structured-output round trip against the endpoint and reports latency,
cached latency and the failure reason — so a broken endpoint is diagnosed in two seconds rather
than halfway through a discovery run.

The proposer and critic are configured as **different model families** by default (llama vs qwen),
because a critic from the same family as the proposer agrees with it too readily.

## Fully offline

`make offline` runs llm-check, sanity, discovery, models, the protocol audit and the journal with
`provider: mock` and no network access at all. That path is what CI-adjacent verification and
air-gapped work use, and it is the reason the LLM arm is optional rather than load-bearing.

## Remaining gaps

1. ~~**No Dockerfile for the lab itself.**~~ Closed in v0.9: `Dockerfile`, `docker/entrypoint.sh`,
   `.dockerignore`, and a profiled `docker-compose.yml` with an app service.
2. **No structured logging or metrics.** Runs print to stdout and write JSON. A long unattended
   run would want structured logs and a heartbeat.
3. **No retention policy for `runs/`.** The evaluation cache grows without bound.
4. **Single-writer assumption.** SQLite with WAL handles concurrent reads; concurrent *writers*
   (two discovery runs at once) want Postgres.
5. **The lab has never executed an order.** Nothing here is a trading system; it is a research
   record with a paper-trading path.
