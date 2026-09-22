"""Research memory (XAlpha's Cross Brain, simplified and deterministic).

Consolidates the ledger into GOOD and BAD summaries per mechanism family, so
the next proposal round starts from what has already been learned instead of
re-proposing known failures. The memory is derived from the ledger by plain
code - the LLM reads it, it does not write it, so it cannot launder a failure
into a success."""
from __future__ import annotations

import datetime as dt
import json
from collections import Counter
from pathlib import Path

from .families import classify
from .ledger import Ledger


def build(ledger: Ledger, path: Path) -> dict:
    rows = ledger.rows()
    good, bad, fails = {}, {}, Counter()
    for r in rows:
        if not r.get("expr"):
            continue
        try:
            fam = classify(r["expr"])
        except Exception:                     # noqa: BLE001 - unparseable rejects still count
            fam = "other"
        if r["status"] in ("active", "probation"):
            g = good.setdefault(fam, {"count": 0, "examples": [], "mean_later_ic": []})
            g["count"] += 1
            if len(g["examples"]) < 3:
                g["examples"].append({"expr": r["expr"], "why": r.get("rationale", "")[:160]})
            if r.get("later_ic_mean"):
                g["mean_later_ic"].append(float(r["later_ic_mean"]))
        elif r["status"] == "rejected":
            b = bad.setdefault(fam, {"count": 0, "reasons": Counter()})
            b["count"] += 1
            reason = (r.get("reason") or "").split(";")[0].split("=")[0].strip()[:60]
            b["reasons"][reason] += 1
            fails[reason] += 1
    for g in good.values():
        ic = g.pop("mean_later_ic")
        g["mean_later_ic"] = sum(ic) / len(ic) if ic else None
    mem = dict(updated=dt.date.today().isoformat(),
               good={k: v for k, v in sorted(good.items(), key=lambda kv: -kv[1]["count"])},
               bad={k: {"count": v["count"], "top_reasons": v["reasons"].most_common(3)}
                    for k, v in bad.items()},
               top_failure_modes=fails.most_common(8))
    Path(path).write_text(json.dumps(mem, indent=2))
    return mem


def to_prompt(mem: dict, max_len: int = 1800) -> str:
    """Render memory as prompt context for the proposer."""
    if not mem:
        return "  (no prior research memory)"
    lines = ["WHAT HAS WORKED (mechanism families with survivors):"]
    for fam, g in list(mem.get("good", {}).items())[:6]:
        ic = f", mean later IC {g['mean_later_ic']:.3f}" if g.get("mean_later_ic") else ""
        lines.append(f"  - {fam}: {g['count']} survivors{ic}")
        for ex in g["examples"][:2]:
            lines.append(f"      e.g. {ex['expr']}")
    lines.append("WHAT HAS FAILED (do not repeat):")
    for fam, b in list(mem.get("bad", {}).items())[:6]:
        reasons = ", ".join(f"{r} (x{n})" for r, n in b["top_reasons"])
        lines.append(f"  - {fam}: {b['count']} rejected - {reasons}")
    return "\n".join(lines)[:max_len]
