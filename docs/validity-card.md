# Validity card

Every strategy variant gets a card (`runs/<name>/CARDS.md`, `cards.json`). The card sets the
**strongest claim you are allowed to make**, following the claim levels in *The Alpha Illusion*
(Ye et al., arXiv:2605.16895):

| Tier | Requires | Allowed wording |
|---|---|---|
| research-aid | default | "an idea worth further research" |
| historical-backtest | P1 temporal integrity (purge > horizon; no LLM factors whose model saw the window), P2 point-in-time universe, P5 costs, Deflated Sharpe ≥ 0.95, **unseen** holdout | "survived a rigorous backtest; not live evidence" |
| forward-evidence | the above + ≥ 13 weeks of hash-stamped forward signals with positive IR | "supports a small, risk-limited live trial" |

Fields reported: excess return, IR, Sharpe with 95% CI (Lo 2002), max drawdown, DSR vs the
number of model variants tried, the one-way cost that wipes out the edge (break-even), excess after
a 58% post-publication decay haircut (McLean & Pontiff 2016), a regime breakdown, and the
discovery-stage trial count and PBO.

Not yet computed (roadmap): the LLM flip test (reverse the evidence and check whether the model
changes direction), calibration (ECE), run-to-run variance across seeds, and a probe of how much
the model recalls about the test period.
