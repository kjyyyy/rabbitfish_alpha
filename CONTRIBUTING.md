# Contributing

The unusual thing about this repo is that **most contributions should make results worse.**
A change that increases reported performance is suspected of loosening a control until proven
otherwise; a change that reveals a leak, tightens a gate or lowers a number is the normal case.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[qlib,llm,web,dev]"
alphalab init && make db && pytest -q
pre-commit install
```

No data, network or model is needed for the test suite.

## The rules that are not negotiable

1. **No look-ahead.** A feature may only use information available at the decision time it claims.
   New operators need a `tests/test_leakage.py` case; `future_noise_test` must pass.
2. **Every trial is logged.** Including rejects. The trial count is the denominator of every
   Deflated Sharpe here, so an unlogged candidate is a silently inflated result.
3. **Gates are code, not judgement.** If a candidate passes because someone decided it should,
   that is an exception and belongs in the exception log (`alphalab exception`).
4. **Costs are always modelled.** A zero-cost number may be reported alongside, never alone.
5. **Nothing chosen after seeing the answer.** Families, composites and splits are fixed in code
   before results exist. If you need to change one, say so in the PR.

## Pull requests

- `ruff check src tests` and `pytest -q` pass; add tests for behaviour, not for coverage.
- Changed a model? `make migration M="what changed"`, and check `alembic check` is clean.
- Changed something that affects results? Re-run `alphalab discover` and `alphalab model`, and
  put the before/after in the PR. A results change with no explanation will be sent back.
- Commit messages say *what changed and what it cost*, not just what was added.

## What this repo will not accept

- A backtest result without a validity card and trial count.
- A factor with no stated economic mechanism.
- Vendored data, credentials, or a dependency that needs a paid API to run the tests.
- Anything that places an order. This is research software; it has never executed a trade.
