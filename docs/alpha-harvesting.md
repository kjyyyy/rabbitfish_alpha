# The alpha-harvesting loop (v0.4)

Alpha harvesting means running discovery as a *closed loop* — propose, gate, evaluate,
remember, repeat — rather than as a one-off backtest. v0.4 adds the loop, taking the
mechanisms from four 2026 papers that survived a claims check, and leaving out the rest.

```
              ┌──────────── one cycle: `alphalab cycle -n 15` ────────────┐
  memory.json │  proposer (LLM) ──► critic (other model family)           │
   (GOOD/BAD) │        ▲                     │                            │
      ▲       │        │ prompt context      ▼                            │
      │       │        └────────── AST gate ─► complexity ─► originality  │
      │       │                                    │                      │
      │       │        ┌── bandit allocates GP children per family ◄──────┤
      │       │        ▼                                                  │
      │       │   DYNAMIC LEAKAGE TEST ─► numerical checks ─► evaluation  │
      │       │                                    │                      │
      │       │        t ≥ 3 · Deflated Sharpe · correlation · FAMILY CAP │
      │       │                                    ▼                      │
      └───────┴──── library ─► strategy variants ─► validity cards ───────┘
```

## What was adopted, and from where

| Mechanism | Source | How it is implemented here |
|---|---|---|
| Operator-tree factors in an AST sandbox | [Hubble](https://arxiv.org/abs/2604.09601) | `expr.py` (already in v0.2) |
| Dual IC reporting (rank **and** Pearson) | Hubble | `evaluate.py` returns both |
| Mechanism families + diversity penalty | Hubble, XAlpha B-layer | `families.py`, `gates.max_per_family` |
| Numerical validation (invalid/extreme ratio, low-information dates, near-constant cross-sections) | [XAlpha](https://arxiv.org/abs/2607.08332) | `leakage.numerical_checks` (XAlpha discards above a 30% invalid/extreme ratio) |
| **Future-noise perturbation test** | XAlpha | `leakage.future_noise_test` + `evalexpr.py` |
| GOOD/BAD memory feeding the next round | XAlpha Cross Brain | `memory.py`, injected into the proposer prompt |
| Bandit allocation of research effort | [R&D-Agent-Quant](https://arxiv.org/abs/2505.15155) (NeurIPS 2025) | `scheduler.py`, Beta-Bernoulli Thompson sampling over families |
| Trajectory/parent lineage | QuantaAlpha, AlphaSeek | `parent_id` in the ledger (v0.2) |

## The one that mattered most: the dynamic leakage test

Qlib computes an expression over the whole stored series and slices afterwards, so
**truncating the end date does not reveal look-ahead** — I verified this: a deliberately
leaky formula (`Ref($close,-5)/$close-1`) produced byte-identical values whether computed
to 2023 or to 2024.

So the lab now carries its own evaluator (`evalexpr.py`) for the operator language, and
every candidate is tested by replacing all data after a cut date with noise and checking
that nothing before the cut moves. The static AST gate already blocks user-written leaks;
the real value of this test is that it guards **the operator library itself**. `tests/test_leakage.py`
implements a rolling mean as *centred* (half the window in the future) and asserts the test
catches it. That class of bug is invisible to every other check in the pipeline.

The second evaluator pays a bonus: `tests/test_leakage.py` cross-checks it against pandas
references, and the same machinery could cross-check Qlib itself on real data.

## What was deliberately not adopted

| Mechanism | Why not |
|---|---|
| ATLAS-style adaptive prompt optimisation for a trading agent | The agent decides trades. The evidence against LLM traders is consistent (see `docs/research/02`, `03`) |
| Alpha-R1 semantic gating (LLM picks factors for the current regime) | Trained and tested inside the model's own pretraining window; regime labels stay reporting-only here |
| FactorEngine parallel Bayesian parameter search | Multiplies the trial count enormously. It would need every tuned variant logged and deflated, or the Deflated Sharpe becomes meaningless |
| XAlpha's 48 archetypes / 8-agent bundles | Structure without evidence at this scale; the memory file covers the same purpose in a few hundred lines |

## Cost of the loop

The new gates are not free: the leakage test costs about 0.7s per candidate and the
numerical checks about 0.35s. On a 220-candidate cycle that is roughly four minutes —
cheap next to the cost of trading a leaked factor.
