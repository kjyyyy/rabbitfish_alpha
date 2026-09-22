"""What every column means, defined once.

A dashboard full of numbers nobody can define is a dashboard that gets
misread, and misreading "DSR 0.72" as "72% chance this works" is exactly the
kind of error this lab exists to prevent. Every term here carries its
definition, the reason it is on screen, and where the number comes from -
a config key, a formula, or a file the pipeline wrote.

`short` is the tooltip. `long` is the glossary entry. `source` says who
produced the number, so a disputed figure can be traced rather than argued
about.
"""
from __future__ import annotations

TERMS: dict[str, dict] = {
    # ---- identity -------------------------------------------------------
    "run": dict(label="Run", short="One invocation of a pipeline stage, with its own id.",
                long="Every `alphalab discover`, `model`, `hierarchy` or `revalidate` "
                     "invocation opens a run and stamps it with the config hash and the "
                     "commit that produced it. Runs are how you tell two results apart.",
                source="runs table"),
    "config_sha": dict(label="Config sha", short="Hash of every setting used, taken before the run.",
                       long="A SHA-256 of the entire config, computed at run start. If this "
                            "differs between two runs, they are not comparable, however similar "
                            "the numbers look.",
                       source="Config.sha()"),
    "commit": dict(label="Commit", short="The git revision of the lab that produced this run.",
                   long="Empty for runs before v0.9, when the field existed but was never "
                        "populated. `-dirty` means there were uncommitted changes, so the code "
                        "that ran cannot be recovered exactly.",
                   source="provenance.git_sha()"),

    # ---- the statistics -------------------------------------------------
    "ic_mean": dict(label="IC mean", short="Average cross-sectional rank correlation with the forward return.",
                    long="Per date, the Spearman correlation between the factor's ranking of "
                         "stocks and their subsequent return, averaged over the discovery "
                         "window. 0.02 is a respectable equity factor; 0.10 usually means a leak.",
                    source="evaluate.evaluate()"),
    "ic_t": dict(label="IC t", short="t-statistic of the IC series, sampled at the holding horizon.",
                 long="The IC series is sampled every `trading.horizon` days so overlapping "
                      "windows do not inflate it. The gate is t >= 3 (Harvey, Liu & Zhu 2016), "
                      "not the usual 2, because thousands of factors have been tried in "
                      "published literature and the bar must account for that.",
                 source="stats.tstat()", config_key="gates.t_stat_min"),
    "inner_oos_t": dict(label="Inner OOS t", short="Same t-statistic, on a purged holdout INSIDE the discovery window.",
                        long="The last `splits.inner_holdout_years` of the discovery window are "
                             "withheld from the search allocator. This column is measured there, "
                             "with a purge gap, and the sign is taken from the inner training "
                             "slice so the holdout cannot choose its own direction. It is what "
                             "the bandit is rewarded on - deliberately not the validation years, "
                             "which would spend the validation window on search.",
                        source="pipeline/discover.py", config_key="splits.inner_holdout_years"),
    "dsr": dict(label="DSR", short="Deflated Sharpe: P(true Sharpe > best expected from N trials of noise).",
                long="Bailey & Lopez de Prado's Deflated Sharpe Ratio. It is NOT the probability "
                     "the strategy makes money. It is the probability the observed Sharpe beats "
                     "what the luckiest of N pure-noise trials would have produced, adjusting for "
                     "skew and kurtosis. It falls as N rises, which is why the trial count sits "
                     "next to it in every table.",
                source="stats.deflated_sharpe()", config_key="gates.dsr_min"),
    "n_trials_at_eval": dict(label="N at eval", short="How many distinct formulas had been tried when this DSR was computed.",
                             long="The cumulative count of distinct formulas ever evaluated for "
                                  "this config, including rejects, at the moment this row was "
                                  "scored. It is the denominator that deflates the Sharpe. A DSR "
                                  "quoted without it means nothing.",
                             source="ledger.n_trials()"),
    "later_ic_mean": dict(label="Later IC", short="The same factor's IC AFTER the discovery window.",
                          long="Reported, never gated on - it is measured in the validation "
                               "years, so using it to select anything would burn the validation "
                               "window. It is the honest preview of decay: factors discovered at "
                               "t = 3-7 here typically retain a fraction of it.",
                          source="pipeline/discover.py"),
    "pbo": dict(label="PBO", short="Probability of Backtest Overfitting, by combinatorially symmetric cross-validation.",
                long="Split the return matrix many ways; how often does the in-sample best "
                     "candidate land below median out of sample? 0.5 is coin-flipping. Computed "
                     "over both the + and - sign of every candidate, so the sign choice cannot "
                     "leak.",
                source="stats.pbo_cscv()"),
    "hurdle": dict(label="Sharpe needed", short="The annualised Sharpe a NEW candidate must reach to clear the DSR gate now.",
                   long="Inverts the Deflated Sharpe at the current trial count. It rises with "
                        "every trial whether or not anything was learned - the treadmill. When it "
                        "exceeds what the asset class plausibly offers, more search on the same "
                        "data cannot win, and the answer is different data.",
                   source="stats.hurdle_sharpe()", config_key="mining.trial_budget"),
    "sharpe_ann": dict(label="Sharpe", short="Annualised Sharpe of the long/short book, after costs.",
                       long="Computed on the rebalance frequency and annualised by sqrt(52). "
                            "Always after the configured cost model; a zero-cost figure may be "
                            "shown beside it but never instead of it.",
                       source="stats.sharpe()"),
    "info_ratio": dict(label="IR", short="Excess return over the benchmark, divided by tracking error.",
                       long="The benchmark is the configured index, so this is the part of the "
                            "return that is not just owning the market.",
                       source="backtest.metrics()"),
    "excess_ann": dict(label="Excess/yr", short="Annualised return above the benchmark, after costs.",
                       source="backtest.metrics()",
                       long="Negative is common and is not a bug: most candidates do not beat "
                            "the index after realistic costs."),
    "effective_trials": dict(label="Effective trials", short="How many INDEPENDENT bets the trial count really represents.",
                             long="Correlation-adjusted count (eigenvalue participation ratio). "
                                  "194 highly correlated formulas may be only ~3 independent "
                                  "bets. Reported for insight, never used to soften the gate: "
                                  "the raw count still deflates the Sharpe.",
                             source="neff.report()"),

    # ---- the loop -------------------------------------------------------
    "stage": dict(label="Stage", short="How far a factor has got: probation, active, retired, forward-evidenced.",
                  long="probation = entered on discovery evidence. active = confirmed by two "
                       "consecutive rechecks on data it was not discovered on. retired = failed "
                       "two consecutive rechecks. forward-evidenced = 13 clean pre-registered "
                       "weeks, the only state that supports a performance claim.",
                  source="library.json"),
    "blocking_gate": dict(label="Blocking gate", short="The single check standing between this factor and its next stage.",
                          long="One gate, not a list, because a factor is only ever blocked by "
                               "the first bar it fails. Clear it and this column changes to the "
                               "next one.",
                          source="web/queries.loop()"),
    "have_need": dict(label="Has / Needs", short="The factor's current value against the threshold it must reach.",
                      long="Read them together: 0.72 of 0.95 on the Deflated Sharpe is a "
                           "different situation from 1 of 2 consecutive rechecks, even though "
                           "both are 'blocked'.",
                      source="web/queries.loop()"),
    "strikes": dict(label="Strikes", short="Consecutive weak rechecks. Two retires the factor.",
                    long="Reset to zero by any strong recheck, so one bad quarter does not kill "
                         "a factor. The same window can never be counted twice.",
                    source="library.revalidate()"),
    "passes": dict(label="Passes", short="Consecutive strong rechecks. Two promotes probation to active.",
                   source="library.revalidate()", config_key="gates.promote_t_min",
                   long="Symmetric with strikes, and for the same reason: promotion should need "
                        "evidence repeated on new data, not one lucky window."),
    "recheck_t": dict(label="Recheck t", short="The factor's t-statistic on recent data it was NOT discovered on.",
                      long="Measured after the discovery window ends. Compare it with the "
                           "discovery t in the same row: the gap is decay, and it is usually "
                           "large.",
                      source="pipeline/revalidate.py"),
    "retained": dict(label="Retained", short="Recheck t divided by discovery t - the fraction of the edge that survived.",
                     long="1.0 means it held up entirely; 0.2 means four fifths of the apparent "
                          "edge was selection. Negative means it reversed.",
                     source="web/queries.decay()"),
    "reward_rate": dict(label="Reward rate", short="Share of a family's children that held up on the purged inner holdout.",
                        long="What the search allocator is rewarded on since v0.10. Measured at "
                             "t >= gates.bandit_reward_t_min on data the allocator never fit.",
                        source="scheduler.divergence()", config_key="gates.bandit_reward_t_min"),
    "in_sample_rate": dict(label="In-sample rate", short="The OLD reward: share clearing t >= 3 in sample. Kept only for contrast.",
                           long="Shown beside the reward rate so a family buying research effort "
                                "with significance it cannot reproduce is visible. The two use "
                                "different bars, so compare the ORDERING of families, not the "
                                "levels.",
                           source="scheduler.divergence()"),

    # ---- forward --------------------------------------------------------
    "clean": dict(label="Clean", short="Was this signal published BEFORE the close that resolves it?",
                  long="A file hash proves the file has not changed; it does not prove the "
                       "prediction preceded the outcome. A manifest written on or after its own "
                       "execution close is recorded and permanently excluded from the tally.",
                  source="forward.publish()"),
    "execution_date": dict(label="Execution", short="The close at which the signal would have been traded.",
                           long="The engine trades at the next close after the signal date. That "
                            "close is the moment the prediction becomes untestable.",
                           source="forward.publish()"),

    # ---- claims ---------------------------------------------------------
    "claim_tier": dict(label="Tier", short="The strongest claim the evidence supports: research-aid, historical-backtest, forward-evidence.",
                       long="research-aid = an idea worth further work, no performance claim. "
                            "historical-backtest = survived the gates in-sample with costs and "
                            "multiple-testing accounting. forward-evidence = supported by "
                            "pre-registered weeks. Nothing in this repo has ever exceeded "
                            "research-aid.",
                       source="card.build()"),
    "status": dict(label="Status", short="Whether this candidate passed the gates, went to probation, or was rejected.",
                   long="Rejected rows are shown by default everywhere in this dashboard. They "
                        "are the denominator, and hiding them is precisely how a backtest "
                        "flatters itself.",
                   source="trials table"),
    "source_col": dict(label="Source", short="Where the candidate came from: hypothesis, llm, random, gp.",
                       long="'random' is a control arm: random grammar with no prior reasoning. "
                            "If the LLM arm cannot beat it, the LLM is decoration.",
                       source="trials table"),
    "family": dict(label="Family", short="Mechanism family, assigned by reading the formula's AST.",
                   long="trend, reversal, volatility, range, price_volume, liquidity, other. "
                        "Assigned deterministically by code, never by hand and never after "
                        "seeing performance - which is what makes family-level testing "
                        "legitimate.",
                   source="families.classify()", config_key="gates.max_per_family"),
}


def tip(key: str) -> str:
    t = TERMS.get(key)
    return t["short"] if t else ""


def entries() -> list[dict]:
    return [dict(key=k, **v) for k, v in TERMS.items()]
