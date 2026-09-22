# Is the harvesting loop actually a loop?

An audit of what v0.1–v0.9 built, asking one question of each stage: **does what we learn at
this stage change what we do next, automatically?** Not "is it logged" — logged is not learned.

Measured on the real record in `runs/cn_csi300/` (194 evaluated candidates, 259 distinct formulas
across 356 trials in 12 runs), not on intuition.

## The loop as designed

```
   propose ──► screen ──► evaluate ──► gate ──► library ──► model ──► portfolio ──► forward
      ▲            (AST, complexity,   (t, DSR,  (probation/   (walk-   (bands,      (pre-register,
      │             originality)        PBO)      active)       forward) capacity)    then wait)
      │                                                                                    │
      └──────────────────────── what we learned changes what we try next ◄──────────────────┘
```

## Which return arrows actually exist

| Return path | Status | Evidence |
|---|---|---|
| ledger → research memory → proposer prompt | ✅ **closed** | `memory.build()` runs from the ledger, `roles.py:86` injects GOOD/BAD and top failure modes into the proposal prompt |
| ledger → cumulative trial count → DSR hurdle | ✅ **closed** | `discover.py:205` `prior = ledger.n_trials("discover-eval")`; N accumulates across every run in a config, so the bar genuinely rises as you search |
| discovery → factor library | ⚠️ **one-way** | `lib.upsert()` inserts. Nothing ever removes or promotes |
| GP/bandit reward → next generation's budget | ⚠️→✅ **fixed in v0.10** | rewarded on a purged inner holdout inside the discovery window; both rates recorded. See below |
| library → revalidation → retirement | ❌→✅ **closed in v0.10** | `alphalab revalidate` scores the library on post-discovery data; two consecutive strong rechecks promote, two weak ones retire, and re-running on the same window is refused |
| forward evidence → anything | ⚠️ **armed in v0.10** | Week 1 published. `evaluate` now excludes any manifest written after its own execution close. Still zero *clean* weeks: the dataset must be refreshed weekly for the clock to run |
| protocol audit / portfolio / risk findings → gates | ❌ **human-only** | `audit.py` proves zero-cost + same-day = ~11%/yr of fiction; `risk.py` proves 62% of the signal is style; neither constrains the next discovery round automatically |
| run → code version | ❌→✅ **fixed in this commit** | `runs.git_sha` was empty on all 12 runs and 3 runs had `config_name="unknown"`. `provenance.py` now stamps git SHA + version; migration `803d3db11492` adds `alphalab_version` |

## The one that matters: the bandit learns the wrong lesson

`discover.py:198` rewards a mechanism family when a child clears **in-sample t ≥ 3** on the
discovery window. So the thing that allocates research effort is trained on exactly the quantity
the rest of the repo exists to distrust. The GP fitness function (`t(IC) − λ·nodes − μ·max|corr|`)
has the same property.

Does it matter in practice? Measured on the 194 evaluated candidates, comparing what the bandit
rewards against `later_ic_mean` (the same factor's IC *after* the discovery window):

| family | n | bandit hit rate (in-sample t≥3) | mean later IC | later IC > 0 |
|---|---|---|---|---|
| price_volume | 40 | **0.550** | +0.0061 | 70% |
| liquidity | 16 | 0.375 | +0.0049 | 44% |
| reversal | 18 | 0.333 | **−0.0048** | 50% |
| trend | 10 | **0.200** | **+0.0081** | 70% |
| range | 56 | 0.179 | +0.0066 | 70% |
| volatility | 38 | 0.132 | +0.0055 | 63% |
| other | 16 | 0.063 | −0.0048 | 38% |

- At the **candidate** level the reward is weakly informative: `corr(|t|, later IC) = +0.235`, and
  candidates the bandit calls winners average +0.0110 later IC against +0.0017 for the rest.
  So it is not noise.
- At the **family** level — which is the level the bandit actually allocates over — it is close to
  noise: Spearman rank correlation between hit rate and later IC is **0.21** across 7 families.
- Concretely, it **starves the best family**. `trend` has the *lowest* hit rate (0.20) and the
  *highest* later IC (+0.0081). `reversal` gets middling budget and has *negative* later IC.
- And it pours the most budget into `price_volume` (15 wins / 27 trials on disk, the largest
  allocation) — the family that reached DSR 0.999 in the v0.5 hierarchy test and then earned
  **−0.4%** in walk-forward. The loop concentrates effort on the family most reliably producing
  statistically impressive, economically worthless results.

### What v0.10 changed

`splits.inner_holdout_years` (default 2) reserves the last two years of the **discovery** window
from the allocator. Candidates are still gated on the full discovery window — gate behaviour is
unchanged — but the bandit is rewarded only on the purged inner holdout, and the reward sign is
taken from the inner *training* slice so the holdout cannot choose its own direction.

Measured on a fresh run (385 distinct trials):

| family | n | reward rate (inner holdout, t ≥ 1) | old in-sample rate (t ≥ 3) |
|---|---|---|---|
| liquidity | 29 | **0.76** | 0.21 |
| price_volume | 54 | 0.69 | 0.33 |
| range | 42 | 0.40 | 0.19 |
| volatility | 26 | 0.31 | 0.15 |
| trend | 12 | 0.25 | **0.00** |
| reversal | 22 | 0.23 | 0.27 |
| other | 19 | 0.00 | 0.00 |

The two columns use **different bars (t ≥ 1 out of sample vs t ≥ 3 in sample), so their levels are
not comparable — only their ordering is.** The ordering changes materially: `liquidity` goes from
third to first, `reversal` from second to sixth, and `trend` from zero wins to fifth. Budget that
used to follow in-sample significance now follows evidence the allocator did not fit.

**The fix is not "reward on `later_ic_mean` instead."** `later_ic_mean` is measured in the
*validation* years; using it to steer the search would spend the validation window on search and
leave nothing clean to validate against. The correct fix is an **inner split inside the discovery
window**: search on `discover_start … discover_end − k years`, reward on the purged inner
holdout, and leave `valid_years` untouched. That is the difference between a loop that learns and
a loop that launders.

## The one that was simply missing: no forward evidence existed

`forward.py` was built in v0.2. The claim tiers in every validity card distinguish
`research-aid` from `forward-evidence`. **No week had ever been published** before v0.10: there was no
`forward/` directory in any run.

Nine versions have added machinery *upstream* of the only clean test in the repo, and the test
has never been started. Thirteen weeks of pre-registration begun at v0.2 would have finished
before v0.7. This is the single biggest thing missed on the way, and it costs nothing but
patience — one command a week, committed before Monday's open.

## The library was a one-way door

18 factors, **all 18 stuck in `probation`**, zero promoted to `active`, zero retired, zero
rechecks ever recorded. `alphalab revalidate` (v0.10) closes it. The first recheck, over 250
sessions from 2021 onward:

| | discovery t | recheck t |
|---|---|---|
| best | 5.2–6.9 | 4.78, 3.83, 3.81 |
| median | ~5.2 | **~1.2** |
| worst | 3.0–3.6 | −0.16, −0.47, −0.47, −0.90 |

Nothing moved on one check, by design: promotion and retirement each need two consecutive
rechecks, so one quiet quarter neither kills nor crowns a factor. Five factors are one strong
recheck from `active`; seven are one weak recheck from retirement.

**A hole found by using it:** running the recheck twice on the same window counts one piece of
evidence twice, and since two consecutive checks are what move a factor, that alone would have
promoted five and retired seven on no new data. It did, on the first attempt here. The library
was repaired to its true single-recheck state, the window is now recorded on every recheck, and
`already_checked()` refuses a repeat — with a regression test. Promotion to `active` requires DSR ≥ 0.95 at insert, which has never
happened; demotion requires `revalidate()`, which never runs. The decay this repo *measured*
(two-thirds of IC lost after discovery) is never *acted on*.

## Other gaps found

1. **No stopping rule.** N rises monotonically, so every future candidate faces a higher DSR bar
   than the last, forever. Nothing says "this mechanism is exhausted, stop or change the data".
2. **Regime labels are reporting-only.** `regime.py` labels regimes; nothing conditions search or
   weighting on them.
3. **Result snapshots have holes.** `results/` has v0.1, v0.3–v0.7 — no v0.2, v0.8 or v0.9 — and
   they are hand-written markdown, so no machine can diff two versions.
4. **Cross-config trial counts are separate.** Each config's N is its own; defensible (different
   universes), but nothing on screen says so.
5. **Still unrun:** SEC adapters against live endpoints, the 8 pre-registered fundamental
   hypotheses, the crypto pilot.

## So: does the dashboard close the loop?

**No — as designed in the first draft it was a viewer, not a loop.** It showed runs, trials,
library, audit, hierarchy and forward: everything that *happened*, nothing about *what happens
next*. You asked for something a user can monitor to reach the next stage, which needs four
things the first draft did not have:

1. **A stage/gate state machine per candidate** — where it is, which gate blocks it, what
   evidence would promote it, how many forward weeks remain.
2. **A search-allocation page showing in-sample hit rate beside out-of-period hit rate** — the
   page that would have made the bandit defect visible in v0.4 instead of v0.9.
3. **A decay and retirement queue** — the revalidation output, once revalidation runs.
4. **Version-to-version comparison** — now possible, because runs finally record the code that
   produced them.

Those four are added to `docs/frontend.md` as pages 7–10 with their endpoints, and to the plan in
`docs/fit-gap.md` as tasks 11–16.

## Order, honestly

The dashboard is task 9 of 16 and it should stay there. Publishing **forward week 1** (task 11)
costs one command and is worth more than every remaining engineering task combined, because it is
the only item on the list that can produce evidence rather than infrastructure.
