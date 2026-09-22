"""The research agents. They propose and critique; they never size, trade or
decide what gets promoted. Everything they emit is logged to the ledger.

  proposer : LLM writes factor hypotheses + Qlib expressions
  critic   : a (preferably different-family) LLM checks hypothesis <-> formula
             consistency; pass/fail, one repair attempt (logged as a new trial)
  journal  : weekly plain-English summary of the ledger and library
"""
from __future__ import annotations

import json
from importlib import resources

from pydantic import BaseModel, Field

from .. import expr as E
from ..config import Config
from ..factors.hypotheses import HYPOTHESES
from ..ledger import Ledger
from ..library import Library
from ..memory import build as build_memory
from ..memory import to_prompt
from .harness import LLMClient, LLMError


class Proposal(BaseModel):
    name: str
    hypothesis: str
    expr: str
    sign: int = Field(..., description="+1 or -1")


class Verdict(BaseModel):
    consistent: bool
    reason: str
    suggested_fix: str = ""


def _prompt(name: str) -> str:
    return resources.files("alphalab.agents").joinpath(f"prompts/{name}.md").read_text()


# ---------------------------------------------------------------------------
# deterministic mock responses (tests / CI / demo without API keys)
# ---------------------------------------------------------------------------
MOCK_PROPOSALS = [
    dict(name="overnight_gap_reversal", sign=-1,
         hypothesis="Large overnight gaps are driven by retail order imbalance at the open and partially reverse.",
         expr="Mean($open/Ref($close,1)-1,5)"),
    dict(name="volume_shock_drift", sign=1,
         hypothesis="High-volume up-days reflect informed buying that is incorporated slowly.",
         expr="Mean(($close/Ref($close,1)-1)*($volume/Mean($volume,20)),10)"),
    dict(name="lookahead_attempt", sign=1, hypothesis="(deliberately invalid - uses future data)",
         expr="Ref($close,-5)/$close-1"),
    dict(name="close_location", sign=-1,
         hypothesis="Closing near the daily high after a run-up signals late momentum chasing that fades.",
         expr="Mean(($close-$low)/($high-$low+1e-12),10)"),
]


def mock_fn(system: str, user: str) -> str:
    if "model_note" in user:                       # llm-check ping
        return json.dumps({"ok": True, "model_note": "mock provider"})
    if "sceptical reviewer" in user:
        return json.dumps({"consistent": "invalid" not in user, "reason": "mock review",
                           "suggested_fix": ""})
    if "journal" in user.lower():
        return "Mock journal: see deterministic summary above."
    return json.dumps(MOCK_PROPOSALS)


def client(cfg: Config, role: str = "proposer") -> LLMClient:
    L = cfg.llm
    critic = role == "critic"
    return LLMClient(L.critic_provider if critic else L.provider,
                     L.critic_model if critic else L.model,
                     cfg.run_dir,
                     L.critic_base_url if critic else L.base_url,
                     L.max_tokens, mock_fn=mock_fn,
                     timeout_s=L.timeout_s, max_retries=L.max_retries,
                     max_calls=L.max_calls_per_run, max_run_tokens=L.max_tokens_per_run,
                     role=role)


# ---------------------------------------------------------------------------
def propose(cfg: Config, n: int = 20, log=print) -> list[dict]:
    ledger = Ledger(cfg.run_dir / "ledger.csv", cfg=cfg)
    lib = Library(cfg.run_dir / "library.json")
    existing = [h["expr"] for h in HYPOTHESES] + [v["expr"] for v in lib.items.values()]
    rejects = [r for r in ledger.rows() if r["status"] == "rejected"][-15:]
    memory = to_prompt(build_memory(ledger, cfg.run_dir / "memory.json"))
    ops = sorted(E.OPS)
    user = _prompt("proposer").format(
        market=cfg.market.universe, horizon=cfg.trading.horizon, n=n,
        fields=[f"${f}" for f in E.FIELDS], ops=ops, max_nodes=cfg.gates.max_nodes,
        max_fields=cfg.gates.max_raw_fields, max_constants=cfg.gates.max_constants,
        existing="\n".join(f"  - {e}" for e in existing[:40]),
        rejections="\n".join(f"  - {r['expr']} [{r['reason'][:80]}]" for r in rejects) or "  (none yet)",
        memory=memory)
    c = client(cfg)
    try:
        props, sha = c.structured("Return only JSON.", user, Proposal, tag="propose", many=True)
    except LLMError as e:
        raise SystemExit(f"proposer failed: {e}") from None
    out = cfg.run_dir / "llm_candidates.jsonl"
    kept = []
    with open(out, "a") as fh:
        for p in props:
            name = f"llm_{p.name}"[:60]
            ok, why = E.is_valid(p.expr)
            if ok and p.sign not in (1, -1):
                ok, why = False, "sign must be +1 or -1"
            row = dict(name=name, expr=p.expr, sign=p.sign, rationale=p.hypothesis,
                       source_model=f"{c.provider}:{c.model}", prompt_sha=sha,
                       status="ok" if ok else "rejected", reason=why)
            if not ok:
                ledger.log(stage="discover-reject", name=name, source="llm", expr=p.expr,
                           rationale=p.hypothesis, source_model=row["source_model"],
                           prompt_sha=sha, status="rejected", reason=f"auditor: {why}")
                log(f"  rejected {name}: {why}")
            else:
                kept.append(row)
            fh.write(json.dumps(row) + "\n")
    log(f"proposer: {len(props)} proposals, {len(kept)} passed the AST auditor -> {out}")
    return kept


def critique(cfg: Config, log=print) -> None:
    """Consistency-check every pending LLM candidate; rewrites the candidates file."""
    path = cfg.run_dir / "llm_candidates.jsonl"
    if not path.exists():
        log("no LLM candidates to critique")
        return
    ledger = Ledger(cfg.run_dir / "ledger.csv", cfg=cfg)
    rows = [json.loads(x) for x in path.read_text().splitlines()]
    c = client(cfg, "critic")
    tmpl = _prompt("critic")
    for r in rows:
        if r.get("status") != "ok" or r.get("critic"):
            continue
        try:
            v, sha = c.structured("Return only JSON.", tmpl.format(
                hypothesis=r["rationale"], expr=r["expr"], sign=r["sign"]), Verdict, tag="critic")
        except LLMError as e:
            log(f"  critic unavailable for {r['name']}: {e} (left as-is)")
            continue
        r["critic"] = dict(consistent=v.consistent, reason=v.reason, model=f"{c.provider}:{c.model}")
        if not v.consistent:
            r["status"] = "rejected"
            ledger.log(stage="discover-reject", name=r["name"], source="llm", expr=r["expr"],
                       rationale=r["rationale"], source_model=r.get("source_model", ""),
                       status="rejected", reason=f"critic: {v.reason[:150]}")
            fix = v.suggested_fix.strip()
            if fix and E.is_valid(fix)[0] and not r["name"].endswith("_fix"):
                rows.append(dict(r, name=r["name"] + "_fix", expr=fix, status="ok", critic=None,
                                 parent_id=r["name"], reason="critic repair"))
        log(f"  {r['name']}: {'consistent' if v.consistent else 'INCONSISTENT'} - {v.reason[:90]}")
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def journal(cfg: Config, log=print) -> str:
    """Deterministic weekly summary (+ optional LLM narrative)."""
    ledger = Ledger(cfg.run_dir / "ledger.csv", cfg=cfg)
    lib = Library(cfg.run_dir / "library.json")
    rows = ledger.rows()
    ev = [r for r in rows if r["stage"] == "discover-eval"]
    by = {}
    for r in ev:
        s = by.setdefault(r["source"], dict(evaluated=0, probation=0, active=0))
        s["evaluated"] += 1
        s[r["status"]] = s.get(r["status"], 0) + 1
    lines = [f"# Research journal - {cfg.name}", "",
             f"- Distinct formulas evaluated (all runs): {ledger.n_trials('discover-eval')}",
             f"- Rejected before evaluation: {sum(r['stage'] == 'discover-reject' for r in rows)}",
             "- Library: " + ", ".join(f"{k}={sum(v['status'] == k for v in lib.items.values())}"
                                        for k in ("active", "probation", "retired")), "",
             "| Source | Evaluated | Probation | Active |", "|---|---|---|---|"]
    lines += [f"| {k} | {v['evaluated']} | {v.get('probation', 0)} | {v.get('active', 0)} |"
              for k, v in by.items()]
    text = "\n".join(lines) + "\n"
    (cfg.run_dir / "JOURNAL.md").write_text(text)
    log(text)
    return text
