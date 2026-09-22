# How alpha harvesting works here

*Research software. It places no orders and nothing here is financial advice.*

Most factor-research systems are built to **find** things. This one is built to **not be fooled**
by what it finds. That inversion explains every design decision below, and it is why the honest
headline after fourteen versions is that **no discovered factor has ever passed a Deflated Sharpe
test that counts every trial** — which is the system working, not failing.

This document explains the process end to end and names the research framework behind each stage,
so that any number the lab produces can be traced to the method that produced it and the paper
that argued for it.

---

## The shape of the problem

Three findings organise everything:

**1. Backtest overfitting is the dominant failure mode, and it is cheap.** López de Prado's
account of "research through backtesting" — repeatedly testing on the same data until something
favourable appears — notes it takes only about **20 iterations to manufacture a false strategy at
standard significance**. Testing *I* independent strategies on pure noise produces an expected
maximum Sharpe of roughly **√(2 log I)**: a hundred trials yields a best-of-set Sharpe near 2.1
from nothing at all.

**2. The trial count is unobservable to everyone except the researcher.** Every multiple-testing
correction is downstream of an honest count of how many things were tried. Institutions solve
this by instrumenting the research platform so that every run is logged automatically, turning a
cultural control into an infrastructural one.

**3. Most apparent alpha is evaluation convention.** This lab measured it on its own data:
assuming zero costs was worth **+6.6%/yr**, and trading the same close used to compute the signal
another **+4.5%/yr** — over eleven points a year of pure fiction before any signal existed.

So: **agents sit upstream, gates sit downstream, and everything is counted.**

---

## The pipeline, stage by stage

```
    hypothesis ─► screen ─► evaluate ─► gate ─► library ─► model ─► construct ─► forward
         ▲                                                                          │
         └──────────────── what we learned changes what we try next ◄────────────────┘
```

### 1. Hypothesis — an idea with a mechanism

A factor enters as a formula **plus a stated economic mechanism and an expected sign**. Three
sources compete on equal terms: hand-written hypotheses, LLM proposals, and a **random control
arm** of grammar-generated formulas with no reasoning behind them. The control arm exists so the
LLM has something to beat; if it cannot beat random, it is decoration.

Ideas can be **pre-registered** — hashed and timestamped before testing — so they cannot be
reworded afterwards to match whatever came out.

> **Framework.** Pre-registration from clinical-trial practice. The mechanism requirement follows
> the standard objection to data-mined factors: without a story about who is on the other side
> and why they lose, a pattern is not a hypothesis and cannot be disconfirmed.

### 2. Screen — cheap rejections first

Before any data is touched: an **AST whitelist** (no attribute access, no imports, no dunders, no
negative `Ref` shifts — which are look-ahead by construction), a **complexity cap**, and an
**originality cap** measured as the largest common subtree against a zoo of published factors.

> **Framework.** The AST whitelist is a security boundary as much as a research one — Qlib
> evaluates these strings. Complexity and originality limits follow AlphaAgent's approach:
> complexity buys in-sample fit almost for free, and rediscovering a known factor inflates the
> trial count with work someone else already did.

### 3. Evaluate — and prove it cannot see the future

Every candidate faces a **future-noise test**: scramble all data after a cut date and require
that every value before it is bit-identical. Anything that changes is reading the future.

This replaced a truncation test that did not work. Qlib computes expressions over the whole
stored series and *then* slices, so truncating the input proved nothing — a discovery that
invalidated the obvious approach and is documented because it will catch anyone else building on
the same engine. A regression test plants a centred rolling mean and requires the detector to
catch it.

> **Framework.** Perturbation testing. The principle: a causal function of past data is invariant
> to changes in the future, so make the future change and watch.

### 4. Gate — deterministic, and counted

| Gate | Value | Why this number |
|---|---|---|
| t-statistic | **≥ 3.0** | Harvey, Liu & Zhu: 2.0 is far too weak once you account for how much the literature has tried |
| Deflated Sharpe | **≥ 0.95** | Bailey & López de Prado, deflated against the **cumulative** count of distinct formulas ever evaluated — including rejects |
| PBO | reported | Probability of backtest overfitting via combinatorially symmetric cross-validation |
| Correlation to accepted | **< 0.7** | A library of near-duplicates is one bet in many costumes |
| Family quota | **≤ 4** per mechanism family | Diversity by construction rather than by hope |

The trial count is the load-bearing part. It accumulates across every run in a config, so the bar
**rises with every search** — which the lab reports as a hurdle: after 385 distinct trials, a new
candidate needs an annualised Sharpe of **1.78** to clear DSR 0.95. That is the treadmill, and it
is the strongest argument against searching harder on the same data.

### 5. Validate — five corrections, because one path is not evidence

| Check | What it catches | Framework |
|---|---|---|
| **CPCV** | A walk-forward Sharpe is one draw from a distribution. On this lab's own best strategy: walk-forward +0.64, but CPCV p05 **−0.42**, with a **21% chance** of a negative Sharpe on a held-out block | López de Prado, combinatorial purged cross-validation |
| **Overfitting Factor** | The tweak-until-it-passes loop, which a bandit is structurally most exposed to. Default **halve the Sharpe**; with the CFM acceptance threshold of 0.7, a candidate needs ~**1.4 backtest** to be a credible 0.7 live | Rej, Seager & Bouchaud (CFM), arXiv:1902.01802 |
| **Log-wealth test** | A strategy can have a *significantly positive mean* and still **compound to a loss** under fat tails. The Sharpe is then computed on a statistic nobody receives | Jensen's inequality; the crypto factor literature's own caveat |
| **Lagged-signal decay** | Whether the edge is a latency race you will lose, and how much slippage tolerance exists | Maven Securities' delay test |
| **Cost sweep** | Pre-committed rule: an edge that dies by 3× costs was a cost assumption. The engine is re-run per multiplier — **never** a synthetic drag added to already-costed returns, which double-charges | — |

### 6. Library — a lifecycle, not a trophy cabinet

Factors enter on **probation**. Two consecutive strong rechecks **on data they were not
discovered on** promote to active; two weak ones retire. Re-running a recheck on the same window
is **refused** — two "consecutive" checks of identical sessions is one piece of evidence counted
twice, which is a mistake this lab made and had to repair.

First recheck of 18 factors discovered at t = 3.0–6.9: median recheck t ≈ **1.2**, five negative.

> **Framework.** McLean & Pontiff on post-publication decay, made operational: measure it, then
> act on it.

### 7. Search allocation — rewarded on evidence it did not fit

A Thompson-sampling bandit allocates genetic-programming effort across mechanism families. It is
rewarded on a **purged inner holdout inside the discovery window** — deliberately not on the
validation years, which would spend the validation window on search.

This was a bug for six versions: the bandit was rewarded on **in-sample t ≥ 3**, so the thing
allocating research effort was trained on precisely the quantity the rest of the repo exists to
distrust. Fixing it changed the ranking materially — `liquidity` went from third to first,
`reversal` from second to sixth.

> **Framework.** R&D-Agent-Quant's bandit scheduler, with the reward signal corrected.

### 8. Construct — where the actual improvement came from

Portfolio construction beat signal research, twice:

- **No-trade bands** cut turnover from 99% to 79% per rebalance and lifted the information ratio
  from **0.18 to 0.30**.
- **62% of the best signal was style exposure** — low beta, small, low volatility. Neutralised,
  the remainder does not survive costs. That is factor beta, not alpha.

Market impact uses the square-root law calibrated to AQR's study of $1.7tn of live executions
(mean impact ~10bp, power-law exponent ≈ ½). At a small book's participation rate the impact term
is negligible — which means **cost modelling for a small book is more reliable than for an
institution**, and the residual failure mode is almost purely statistical self-deception.

Capacity for the best construction is roughly **£1–10m**.

### 9. Forward — the only clean evidence

`forward publish` scores the latest date, writes signals and a SHA-256 manifest, and you commit it
**before the market can resolve it**. `forward evaluate` scores every week whose horizon elapsed —
and **refuses any manifest written after its own execution close**, because a file hash proves the
file is unchanged, not that the prediction preceded the outcome.

Claim tiers: `research-aid` → `historical-backtest` → `forward-evidence`. **Nothing in this repo
has ever exceeded research-aid.**

---

## The frameworks, in one table

| Stage | Framework | Source |
|---|---|---|
| Multiple-testing bar | t ≥ 3.0 | Harvey, Liu & Zhu (2016) |
| Deflation | Deflated Sharpe Ratio | Bailey & López de Prado |
| Overfit probability | PBO via CSCV | Bailey et al. |
| Cross-validation | CPCV, purging, embargoing | López de Prado, *Advances in Financial ML* |
| Refinement discount | Overfitting Factor (~2×) | Rej, Seager & Bouchaud (CFM) |
| Decay | Post-publication decay; delay test | McLean & Pontiff; Maven Securities |
| Search allocation | Thompson-sampling bandit | R&D-Agent-Quant |
| Complexity & originality | AST caps, zoo subtree overlap | AlphaAgent |
| Factor lifecycle | probation → active → retired | AlphaCrafter-style, re-implemented |
| Dynamic combination | trailing-IC weights with shrinkage | AlphaForge, re-implemented |
| Market impact | square-root law | AQR (Frazzini, Israel & Moskowitz) |
| Risk model use | diagnostic only, never an optimiser input | Saxena & Stubbs, factor alignment problem |
| Breadth | IR = IC·√BR | Grinold's fundamental law |
| Turnover control | no-trade bands | Novy-Marx & Velikov |

Ideas from AlphaGen and AlphaForge are **re-implemented, not copied** — neither ships a licence
file. MiroFish (AGPL) is deliberately unused.

---

## Portability: what transfers to crypto and futures

The 2026 review's verdict: **the validation machinery ports; the search engine does not.**

**Ports unchanged.** Trial-counted deflation, purged holdouts, the leakage audit, pre-registration,
promotion and retirement on out-of-period rechecks. These are market-agnostic.

**Partly ports: breadth.** IR = IC·√BR. Measured on simulated universes at realistic
correlations (`scripts/breadth_experiment.py`, pure noise, 200 random factors per search, 30
repetitions):

| Universe | Instruments | Avg corr | Bets (long-only) | Bets (neutral) | IR from an IC of 0.03 |
|---|---|---|---|---|---|
| Equity cross-section | 300 | 0.14 | 43.0 | **190.0** | **2.98** |
| Crypto perps | 100 | 0.57 | 3.0 | 83.2 | 1.97 |
| Commodity futures | 25 | 0.35 | 6.4 | 23.1 | 1.04 |
| A thin book | 8 | 0.49 | 3.0 | 7.0 | 0.57 |

Two findings, one of them a correction to the claim this experiment was built to test.

**The hypothesis failed.** A thinner universe does *not* inflate the in-sample best of a fixed
search budget: the best-of-200 Sharpe is roughly 0.9–1.2 everywhere and out-of-sample is roughly
zero everywhere. Saying so is the point of running it.

**The breadth penalty depends on the kind of book.** A common factor collapses *long-only*
breadth — 25 futures really are about 6 bets, which is what the CTA literature's "4–8 independent
bets" refers to — but it **cancels** for a cross-sectional book, where the same 25 contracts are
about 23. Quoting one figure at the other misstates breadth by an order of magnitude. `breadth.py`
therefore reports both, and an earlier version of this lab's own diagnostic reported only the raw
figure and drew the wrong conclusion about its own equity universe.

The residual penalty is still real and still the argument for a narrow, pre-specified search in a
thin market: **identical skill earns an IR of 2.98 in the wide cross-section and 1.04 in commodity
futures, while the trial count that deflates the result is the same in both.** The risk of fooling
yourself is constant; the payoff is not.

Measured on the lab's own CSI-300 universe: 653 names, average correlation 0.38, **6.6 long-only
bets but 97.2 market-neutral bets** — so the equity search that has been running is in fact
proportionate (3.7 trials per bet). The disproportion appears in commodities, not here.

**What the new markets additionally require** (`docs/crypto-and-futures.md`): a roll engine with
timing, splicing and return-chaining kept separate; tick-denominated costs; funding as a holding
cash flow; and notional, margin and NAV tracked as three different numbers.

**EU ETS carbon** (`docs/eu-ets.md`) is the limiting case: one tradable instrument, so the
cross-sectional path is not weak but *undefined* — `evaluate.py` requires 30+ names per date.
`alphalab.timeseries` supplies the other geometry, with Newey-West standard errors because a
20-day forward return sampled daily shares 19 days with its neighbour and inflates a naive t-stat
by roughly √h. The market also demonstrates the trial-count argument better than any equity
example: a horizon sweep of four signals across five horizons is **twenty trials**, and the best
thing it found — a pure-noise calendar countdown at Sharpe 0.54 — scores **DSR 0.837 as a lone
hypothesis and 0.060 once the sweep is counted.**

---

## What it has actually found

Nothing tradeable. What it has established is worth more than a backtest would have been:

- Zero-cost assumptions and same-day execution were worth **11 points a year** of fiction.
- **62%** of the best signal was style exposure.
- No-trade bands lifted the IR from **0.18 to 0.30** — construction beat research.
- Factors discovered at **t = 3.0–6.9** came back with a median recheck **t ≈ 1.2**.
- Hierarchical testing raised a family composite to **DSR 0.999** — which then earned **−0.4%** in
  walk-forward. Better statistics, no performance.
- The chosen strategy's CPCV distribution has a **21% chance of a negative Sharpe**, and after the
  overfitting factor it scores **0.27 against a 0.7 threshold**.

A lab that had produced a Sharpe 2.5 equity curve after 385 trials with no cost model would be the
failure. This is the instrument working.

---

## Running it

```bash
alphalab init && make db && alphalab doctor    # keys, data, schema, endpoints
alphalab ingest --csv ~/prices --write-config configs/mine.yaml   # or your own data
alphalab discover      # screen → evaluate → GP with the bandit → gates
alphalab model         # walk-forward variants + validity cards
alphalab validate      # CPCV, overfitting factor, log-wealth, decay, cost sweep
alphalab audit         # how much "alpha" is evaluation convention?
alphalab revalidate    # recheck the library on data it was not discovered on
alphalab hierarchy     # family-level testing first (cuts effective N)
alphalab forward publish   # commit the manifest BEFORE the next session opens
alphalab serve         # read-only dashboard
```

The dashboard's **Gates** page states every rule with its live value; **Glossary** defines every
column; **Loop** shows what each factor is blocked by. See `README.md` for setup and
`docs/feedback-loop.md` for the audit of which return paths are actually closed.
