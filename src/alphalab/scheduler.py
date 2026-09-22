"""Bandit scheduler for research effort (R&D-Agent-Quant, NeurIPS 2025).

That paper uses linear Thompson sampling over a two-armed action space
{factor, model}. Here the arms are mechanism families: each generation, the
scheduler decides how many children to spend on each family, based on the hit
rate that family has produced so far. Families that keep producing survivors
get more of the budget; exhausted ones get less but never zero, so the search
can recover if a regime changes.

Beta-Bernoulli Thompson sampling: each family has a Beta(successes+1,
failures+1) posterior over "a child from this family clears the t>=3 bar"."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .families import FAMILIES


class FamilyBandit:
    def __init__(self, path: Path | None = None, families=FAMILIES, seed: int = 0):
        self.path = Path(path) if path else None
        self.families = list(families)
        self.rng = np.random.default_rng(seed)
        # `wins` is the reward that drives allocation (inner-holdout evidence).
        # `in_sample_wins` is the OLD reward, kept only so the divergence between
        # "looked significant" and "held up" stays visible - see docs/feedback-loop.md.
        self.stats = {f: {"wins": 0, "trials": 0, "in_sample_wins": 0} for f in self.families}
        if self.path and self.path.exists():
            saved = json.loads(self.path.read_text())
            for f, v in saved.items():
                if f in self.stats:
                    self.stats[f] = {**self.stats[f], **v}

    def allocate(self, budget: int, min_per_family: int = 1) -> dict[str, int]:
        """Thompson-sample a budget split across families."""
        draws = {f: float(self.rng.beta(s["wins"] + 1, s["trials"] - s["wins"] + 1))
                 for f, s in self.stats.items()}
        floor = min_per_family * len(self.families)
        free = max(budget - floor, 0)
        total = sum(draws.values()) or 1.0
        alloc = {f: min_per_family + int(free * d / total) for f, d in draws.items()}
        short = budget - sum(alloc.values())
        if short > 0:                                  # hand the remainder to the best draw
            alloc[max(draws, key=draws.get)] += short
        return alloc

    def update(self, family: str, success: bool, in_sample: bool | None = None):
        """`success` is what allocates budget; `in_sample` is recorded for contrast."""
        s = self.stats.setdefault(family, {"wins": 0, "trials": 0, "in_sample_wins": 0})
        s["trials"] += 1
        s["wins"] += int(bool(success))
        if in_sample is not None:
            s["in_sample_wins"] = s.get("in_sample_wins", 0) + int(bool(in_sample))

    def rates(self) -> dict[str, float]:
        return {f: (s["wins"] / s["trials"] if s["trials"] else None) for f, s in self.stats.items()}

    def divergence(self) -> dict[str, dict]:
        """Per family: the rate that allocates budget vs the rate that used to.
        A large gap means in-sample significance was buying research effort."""
        out = {}
        for f, s in self.stats.items():
            n = s["trials"]
            out[f] = dict(trials=n,
                          reward_rate=(s["wins"] / n if n else None),
                          in_sample_rate=(s.get("in_sample_wins", 0) / n if n else None))
            if n:
                out[f]["gap"] = out[f]["in_sample_rate"] - out[f]["reward_rate"]
        return out

    def save(self):
        if self.path:
            self.path.write_text(json.dumps(self.stats, indent=2))
