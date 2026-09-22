# Raising a Deflated Sharpe of 0.9: what worked, what didn't

A Deflated Sharpe Ratio (DSR) of ~0.9 means: *after* correcting for how many strategies were
tried and for non-normal returns, there is roughly a 90% probability the true Sharpe is above
zero. Convention treats 0.95 as "strong evidence", so 0.9 is a promising hypothesis, not an
edge. The lab's best candidate sat at 0.90 after v0.4.

Three levers were implemented and tested.

## 1. Hierarchical testing — works statistically

Testing 194 formulas flat means deflating against 194 trials. Testing 7 **mechanism-family
composites** first means deflating against 7; only families that clear that bar earn a
within-family search (`alphalab hierarchy`).

Apples-to-apples, on the same factor:

| Test | N | DSR |
|---|---|---|
| Flat search | 194 | 0.288 |
| Within its family | 40 | **0.707** |
| The family composite itself | 7 | **0.999** ← first thing in this project to clear 0.95 |

This is legitimate **only** because the family definitions and the composite rule are fixed
before results are seen: families come from the AST (`families.classify`), and the composite is
an equal-weight blend of every evaluated member, signed. Nothing is re-picked on performance.

The honest caveat: the members were mined from the same discovery window, so N=7 understates the
real search. The flat count is too conservative, the family count too generous, and the truth is
in between.

## 2. Effective trial count — the raw count was far too harsh

194 formulaic candidates are not 194 independent lottery tickets. Their mean absolute pairwise
correlation is **0.485**, so:

| Measure | Value |
|---|---|
| Raw trials | 194 |
| Effective trials (eigenvalue participation ratio) | **2.8** |
| Effective trials (average-correlation adjustment) | 1.8 |

The lab reports both and **still gates on the raw count**. Picking whichever N makes a strategy
pass is exactly the degree of freedom the DSR exists to remove.

## 3. Better combination — did not work here

| Variant | Validation excess/yr | IR | Holdout (descriptive) |
|---|---|---|---|
| A hypothesis composite (baseline) | +7.1% | 0.63 | −14.9% |
| **I horizon ensemble** (1/5/10-day models, rank-averaged) | **+7.4%** | **0.76** | −3.5% |
| E library, dynamic IC weights | −2.3% | −0.20 | −8.7% |
| G library, Ledoit-Wolf shrinkage | −5.0% | −0.53 | −13.3% |
| H **family composite** (the DSR 0.999 one) | **−0.4%** | **−0.04** | −8.3% |

The horizon ensemble is the one modest win: the best validation IR in the project (0.76) at lower
volatility, though it still fails at doubled costs.

## The finding that matters

**The composite that passed the statistical bar at 0.999 earned −0.4% in walk-forward validation.**

Raising a DSR by reducing the effective number of trials makes the *statistic* more accurate —
it corrects a real over-penalty — but it creates no performance. Three separate factor-combination
methods from the literature (dynamic IC weighting, Ledoit-Wolf shrinkage, family composites) all
underperformed the twelve hand-written hypotheses. The lab's binding constraint is not its
statistics; it is that price-only daily signals on this universe do not contain a durable edge
after costs.

Worth noting against the source material: the advice to "only count pre-registered tests toward N"
is dangerous unless the pre-registration genuinely preceded the data work. This lab does the
opposite — every candidate, including every LLM reject, lands in the ledger and counts.
