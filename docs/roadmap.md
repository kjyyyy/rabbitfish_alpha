# Roadmap

Priorities are from `docs/research/03-llm-alpha-mining-papers.md`.

- [x] P0 AST parser and whitelist; ledger v2; LLM harness; validity card; forward pre-registration
- [x] P1 complexity and originality gates; consistency critic; per-source ablation table
- [x] P2 GP refiner; factor library and dynamic IC combiner; regime breakdown
- [x] P3 institutional portfolio layer: risk model, neutralisation, bands, caps, impact, capacity, crowding
- [x] P4 harvesting loop: families, bandit scheduler, memory, numerical gates, dynamic leakage test, `alphalab cycle`
- [x] P5 DSR work: hierarchical testing, effective-N reporting, shrinkage/horizon/family combiners
- [x] P6 protocol audit + free-data registry (SEC PIT fundamentals, EDGAR delistings)
- [x] P7 PIT fundamentals table, fundamental hypothesis library, data QA, governance register
- [x] P8 production hardening: relational storage + Alembic migrations, local model stack (Ollama/vLLM), offline mode, Makefile
- [ ] Run the SEC adapters against live endpoints locally; build a US delisting-aware universe
- [ ] Re-test the best mechanism families on the clean US universe (fundamentals overlay)
- [ ] Crypto pilot (3-5 majors, daily bars) once the US fundamental block is done - same gates, same audit, 10bp+ cost sweeps
- [ ] Reward the bandit on out-of-period survival rather than in-sample t-stats
- [ ] Run the LLM arm for real (`alphalab propose` with a key), then decide whether to keep it using the ablation table
- [ ] 13 weeks of `alphalab forward publish` every weekend; commit each manifest before Monday's open
- [ ] US point-in-time data (Norgate) and UK data; port and re-run the sanity tests
- [ ] QuantaAlpha-style trajectory mutation: the critic names the failing step, the proposer rewrites only that step
- [ ] Validity-card additions: LLM flip test, run-to-run variance, recall probe for LLM-derived features
- [ ] IBKR paper mirror via `ib_async`: reconcile fills to signals; hard risk limits and a kill switch in plain code
- [ ] (maybe) RD-Agent(Q) as an external baseline (Linux + Docker)
