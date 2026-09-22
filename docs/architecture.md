# Architecture

The design principle comes from the paper review (`docs/research/03-llm-alpha-mining-papers.md`):
**LLMs work upstream as researchers; deterministic code makes every decision.**
Agents that write factor code produce reproducible results (AlphaForgeBench). Agents that emit
trades do not: across repeated runs they disagree with themselves on 54–96% of decisions.

```
                 ┌────────────────────────── RESEARCH (LLM allowed) ──────────────────────────┐
  hypotheses ──┐ │  proposer agent ──► critic agent (other model family) ──► one repair try   │
  (humans)     │ └───────────────────────────────┬────────────────────────────────────────────┘
               ▼                                 ▼
          ┌──────────────── GATES (deterministic, src/alphalab) ─────────────────┐
          │ 1 AST whitelist parse (expr.py)  - blocks eval() attacks & look-ahead │
          │ 2 complexity caps  - nodes / raw fields / constants                   │
          │ 3 originality      - largest common subtree vs Alpha158 zoo + library │
          │ 4 evaluation on DISCOVERY window only - rank IC, t (non-overlapping)  │
          │ 5 GP refiner       - fitness = t - λ·nodes - μ·max|corr|, all logged  │
          │ 6 multiple testing - t ≥ 3, Deflated Sharpe vs ALL trials, PBO        │
          └───────────────┬──────────────────────────────────────────────────────┘
                          ▼
          library.json  probation ─► active ─► retired  (periodic re-validation)
                          ▼
          pre-registered strategy variants (walk-forward, purged folds, costs)
          A composite · C LightGBM(hypotheses) · E dynamic-IC library · F LightGBM(+library)
                          ▼
          validity card per strategy  ─►  claim tier (research-aid / backtest / forward-evidence)
                          ▼
          forward pre-registration (hash-stamped weekly signals)  ─►  forward evaluate
                          ▼
          [not built] execution. Paper trading via IBKR/ib_async is the next step; sizing and
          risk limits stay in plain code, never in an LLM.
```

## Build status

| Component | Status | Why |
|---|---|---|
| AST parser, whitelist, canonical form | built | Qlib `eval()`s expression strings; regex auditing is unsafe |
| Complexity caps + zoo originality | built | AlphaAgent ablation: hit ratio 0.16 → 0.29 |
| Ledger v2 (every candidate, rejects included) | built | Trial count drives Deflated Sharpe/PBO |
| LLM harness (cache, call log, schema, repair) | built | Reproducibility without temperature |
| Proposer / critic / journal agents | built | Researchers, not traders |
| GP refiner | built | RiskMiner/AlphaGen-style fitness; cheap |
| Factor library + dynamic IC combiner | built | AlphaCrafter lifecycle; AlphaForge-style weighting (re-implemented; originals unlicensed) |
| Rule-based regime breakdown | built (reporting only) | New Quant survey stress-breakdown |
| Validity card + claim tiers | built | The Alpha Illusion protocols P1/P2/P5 |
| Forward pre-registration | built | Holdout burned; only clean OOS left |
| QuantaAlpha trajectory mutation | later | Critic already names failures; add parent-linked rewrite |
| IBKR paper mirror (ib_async) | later | Needs a funded IBKR account |
| LLM regime gating (Alpha-R1 GRPO) | not built | 6-month test, likely in pre-training data, GPU cost |
| LLM trader / sizer, debate swarms | not built | Evidence negative (Alpha Arena, StockBench, Alpha Illusion) |
