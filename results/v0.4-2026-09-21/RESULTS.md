# v0.4 results — the alpha-harvesting loop (CSI 300, data to 18 Sep 2026)

*Research output, not advice. The 2025–26 holdout was viewed in v0.1, so it stays descriptive only.*

## Did the 2026 "alpha harvesting" methods improve the lab?

Partly. They improved **research hygiene and search efficiency**. They did not produce alpha.

| Metric | v0.3 | v0.4 | Reading |
|---|---|---|---|
| Formulas evaluated | 212 | 194 | Similar budget |
| Reaching t ≥ 3 | 72 | 52 | Fewer, because degenerate factors are now rejected before scoring |
| Entering the library | 33 | **18** | Family caps stop one mechanism dominating |
| Best Deflated Sharpe | 0.81 | **0.90** | Survivors are stronger, still short of the 0.95 bar |
| PBO (overfitting probability) | 0.30 | **0.04** | Ranking is far more stable |
| Rejected by numerical checks | — | **30** | v0.3 scored these degenerate factors |
| Rejected by dynamic leakage test | — | 0 | The static gate already catches user-written leaks; this guards the operators |
| Evaluation speed | 3.5 s/candidate | **0.36 s** | Fixing the alignment bug also fixed the speed |

Still **zero factors pass every gate**, and the strategy variants did not improve: the
library-based ones (E, F) remain worse than the 12 written hypotheses alone.

## The single most valuable addition: a real look-ahead test

The papers propose testing for leakage by truncating the data. **That does not work with
Qlib**: it computes an expression over the whole stored series and slices afterwards. I
verified this — a deliberately leaky formula (`Ref($close,-5)/$close-1`) gave byte-identical
values computed to 2023 or to 2024.

So the lab now carries `evalexpr.py`, an independent evaluator for the operator language, and
tests every candidate by scrambling all data after a cut date and checking nothing before the
cut moves. The static AST gate already blocks user-written leaks; this guards **the operator
library itself**. `tests/test_leakage.py` implements a rolling mean as *centred* — half the
window in the future — and asserts the test catches it. No other check in the pipeline can see
that class of bug.

## Mechanism families: what the lab is actually finding

New in v0.4: every factor is classified by mechanism from its AST, and results are reported per
family.

| Family | Evaluated | t ≥ 3 | In library | Mean later IC of the strong ones |
|---|---|---|---|---|
| price_volume | 40 | 22 | 4 | 0.012 |
| range | 56 | 10 | 4 | **0.016** |
| liquidity | 16 | 6 | 3 | 0.012 |
| reversal | 18 | 6 | 3 | 0.007 |
| volatility | 38 | 5 | 2 | −0.001 |
| trend | 10 | 2 | 1 | **0.025** |
| other | 16 | 1 | 1 | −0.008 |

Price-volume factors are the easiest to *find* (22 of 40 clear t ≥ 3) but decay hard.
Trend factors are the hardest to find and hold up best. Volatility factors look strong
in discovery and are worthless afterwards. This is exactly the diagnostic the family layer
was added to produce, and it matches Hubble's finding that range and volatility families
dominate their top set while the weakest trend factor decays.

## The bandit scheduler learned the same thing

Research effort is now allocated across families by Thompson sampling, with the reward being
"a child from this family clears t ≥ 3" (R&D-Agent-Quant's idea, simplified).

Hit rates learned over three generations: price_volume 0.56, liquidity 0.44, reversal 0.36,
volatility 0.23, range 0.23, trend 0.14, other 0.00.

Note the trap this reveals: the bandit optimises for *finding* factors, and the most findable
family (price_volume) is not the most durable (trend). A future version should reward
out-of-period survival instead — but that reward arrives years late, which is the fundamental
problem with automating this loop.

## Strategy variants (unchanged conclusion)

| Variant | Valid excess/yr | IR | IR @2× costs | Holdout (descriptive) |
|---|---|---|---|---|
| A hypothesis composite | +7.1% | 0.63 | **0.24** ← chosen | −14.9% |
| C LightGBM on hypotheses | +6.1% | 0.65 | 0.01 | +3.7% |
| E library, dynamic IC weights | −2.3% | −0.20 | −0.69 | −8.7% |
| F LightGBM on hypotheses + library | +4.5% | 0.49 | −0.21 | +2.6% |

## Honesty log

Building v0.4 surfaced five bugs, four of them mine, and all found by tests or sanity checks
rather than by reading the code:

1. The truncation-based leakage test silently passed a leaky formula (Qlib's evaluation order).
2. Numerical checks rejected 96 of 103 good candidates, because a rectangular unstack of an
   index-membership panel is ~60% structurally empty — that is not a defective factor.
3. The genetic step crashed when a family had one parent, then produced zero children when the
   evaluation stage had rejected everything upstream.
4. The Pearson IC used a per-group transform that misaligned indexes; fixing it also made
   evaluation 10× faster.
5. PBO crashed when one candidate had a short history; it now drops short-history columns.

An earlier patch to `evaluate.py` silently failed to apply and I did not notice until the error
recurred — worth remembering when reading any "fixed" claim in this log.
