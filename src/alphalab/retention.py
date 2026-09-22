"""`alphalab clean` - the caches that otherwise grow without bound.

Three caches make re-runs cheap and reproducible: the Qlib feature cache, the
per-candidate evaluation cache, and the LLM prompt-hash cache. None of them had
a retention policy, so a laptop running a weekly cycle fills up quietly.

What is never touched: `ledger.csv`, the database, `library.json`, forward
manifests and anything under `results/`. Those are the research record, and a
retention policy that can delete evidence is not a retention policy.
"""
from __future__ import annotations

import time
from pathlib import Path

from .config import Config

PROTECTED = ("ledger.csv", "library.json", "memory.json", "bandit.json", "alphalab.db")


def _sweep(paths, cutoff: float, dry_run: bool) -> tuple[int, int]:
    n = freed = 0
    for p in paths:
        try:
            st = p.stat()
        except FileNotFoundError:
            continue
        if p.name in PROTECTED or "forward" in p.parts or "results" in p.parts:
            continue
        if cutoff and st.st_mtime > cutoff:
            continue
        freed += st.st_size
        n += 1
        if not dry_run:
            p.unlink(missing_ok=True)
    return n, freed


def run(cfg: Config, older_than_days: int = 30, dry_run: bool = False, log=print) -> dict:
    cutoff = time.time() - older_than_days * 86400 if older_than_days else 0
    work = Path(cfg.workdir)
    groups = {
        "evaluation cache": list((work / ".cache").glob("eval_*.pkl")),
        "feature cache": [p for p in (work / ".cache").glob("*.pkl")
                          if not p.name.startswith("eval_")],
        "llm prompt cache": list(work.glob("*/llm_cache.sqlite")),
        "llm call logs": list(work.glob("*/llm_calls.jsonl")),
    }
    total_n = total_b = 0
    for label, paths in groups.items():
        n, b = _sweep(paths, cutoff, dry_run)
        total_n += n
        total_b += b
        log(f"  {label:18s} {n:5d} file(s), {b / 1e6:8.1f} MB"
            + (" (dry run)" if dry_run and n else ""))
    log(f"{'would free' if dry_run else 'freed'} {total_b / 1e6:.1f} MB across {total_n} files"
        + (f", keeping anything newer than {older_than_days} days" if older_than_days else ""))
    log("the research record (ledger, database, library, forward manifests, results/) is "
        "never touched")
    return dict(files=total_n, bytes=total_b, dry_run=dry_run)
