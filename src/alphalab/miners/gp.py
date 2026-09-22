"""Genetic-programming refiner (RiskMiner/AlphaGen-inspired fitness, clean
implementation): children of the best seeds are scored on the DISCOVERY
window only with
    fitness = t(IC) - lambda * nodes - mu * max|corr(LS, pool)|
Every child is a trial and is written to the ledger by the caller."""
from __future__ import annotations

import random

from .. import expr as E


def next_generation(parents: list[dict], n_children: int, rng: random.Random,
                    seen: set[str]) -> list[dict]:
    parents = [p for p in parents if p.get("expr")]
    if not parents:
        return []
    kids, tries = [], 0
    while len(kids) < n_children and tries < n_children * 20:
        tries += 1
        a = rng.choice(parents)
        try:
            others = [p for p in parents if p is not a]
            if rng.random() < 0.5 and others:
                b = rng.choice(others)
                e = E.crossover(a["expr"], b["expr"], rng)
                pid = f"{a['name']}x{b['name']}"
            else:
                e = E.mutate(a["expr"], rng)
                pid = a["name"]
            fp = E.fingerprint(e)
        except E.ExprError:
            continue
        if fp in seen:
            continue
        seen.add(fp)
        kids.append(dict(name=f"gp_{len(seen):04d}", expr=e, sign=0, parent_id=pid,
                         source="gp", rationale=f"GP child of {pid}"))
    return kids


def fitness(row: dict, lam: float, mu: float) -> float:
    return abs(row["ic_t"]) - lam * row["nodes"] - mu * row.get("max_corr", 0.0)
