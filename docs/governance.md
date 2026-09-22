# Research governance

Two artefacts, both generated rather than written by hand, so they cannot drift from what the
code did.

## Assumption register (`runs/<name>/assumptions.json`)

Written automatically on every model run. It records the choices that change results and that a
sceptical reader would otherwise have to reverse-engineer: execution timing, the cost model and
its sensitivity, universe definition and point-in-time membership, data provenance and the
filing-date rule for fundamentals, gate thresholds, trial-counting policy, and whether the
holdout has been burned. Regenerate any time with `alphalab register`.

## Exception log (`runs/<name>/exceptions.csv`)

Append-only. Every deviation from the standard protocol goes in:

```bash
alphalab exception --kind exclusion --scope "2020-02..2020-04" --reason "CN calendar gap"
alphalab exception --kind filter --scope microcaps --reason "excluded below 100m ADV"
```

Validity cards report the count and kinds. An unexplained ad-hoc filter is how exploratory work
quietly becomes a confirmatory claim; logging it keeps the distinction visible.

## Why not "only count pre-registered tests"

A recurring suggestion is to deflate the Sharpe against pre-registered tests only. This lab
rejects that: **every candidate ever evaluated counts**, including every LLM proposal the
auditor rejected. Pre-registration is used for what it is good at — forcing an economic
rationale and separating confirmatory from exploratory work — not as a way to shrink N.
