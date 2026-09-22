"""Tests for the alpha-harvesting loop: families, bandit scheduler, memory."""
import json

import pytest

from alphalab.config import Config
from alphalab.families import classify, diagnostics, family_cap
from alphalab.ledger import Ledger
from alphalab.memory import build, to_prompt
from alphalab.scheduler import FamilyBandit


@pytest.mark.parametrize("expr,family", [
    ("Ref($close,20)/Ref($close,240)-1", "trend"),
    ("$close/Ref($close,5)-1", "reversal"),
    ("Std($close/Ref($close,1)-1,20)", "volatility"),
    ("Mean(($high-$low)/$close,20)", "range"),
    ("Corr($close,Log($volume+1),20)", "price_volume"),
    ("Mean($volume,20)/Mean($volume,120)", "liquidity"),
])
def test_family_classification_is_stable(expr, family):
    assert classify(expr) == family
    assert classify(expr) == classify(expr)          # deterministic


def test_family_cap_enforces_diversity():
    rows = [dict(name=f"f{i}", family="trend", ic_t=5 - i * 0.1) for i in range(10)]
    rows += [dict(name="v1", family="volatility", ic_t=3.5)]
    kept = family_cap(rows, per_family=2)
    assert sum(r["family"] == "trend" for r in kept) == 2
    assert sum(r["family"] == "volatility" for r in kept) == 1


def test_diagnostics_reports_survival_by_family():
    rows = [dict(family="trend", ic_t=4.0, ic_mean=0.03, later_ic_mean=0.01, status="probation"),
            dict(family="trend", ic_t=1.0, ic_mean=0.01, later_ic_mean=0.0, status="rejected")]
    d = diagnostics(rows)
    assert d["trend"]["evaluated"] == 2 and d["trend"]["t_ge_3"] == 1 and d["trend"]["kept"] == 1


def test_bandit_shifts_budget_to_productive_families(tmp_path):
    b = FamilyBandit(tmp_path / "b.json", families=("trend", "volatility"), seed=0)
    for _ in range(40):
        b.update("trend", True)
        b.update("volatility", False)
    alloc = b.allocate(40)
    assert alloc["trend"] > alloc["volatility"]
    assert sum(alloc.values()) == 40
    assert alloc["volatility"] >= 1                  # never starved completely
    b.save()
    assert json.loads((tmp_path / "b.json").read_text())["trend"]["wins"] == 40


def test_memory_summarises_wins_and_failures(tmp_path):
    cfg = Config(workdir=str(tmp_path))
    led = Ledger(cfg.run_dir / "ledger.csv")
    led.log(stage="discover-eval", name="a", source="llm", expr="Std($close,20)",
            status="probation", later_ic_mean=0.02, reason="passed")
    led.log(stage="discover-reject", name="b", source="random", expr="Mean($volume,20)",
            status="rejected", reason="zoo overlap 12>8")
    mem = build(led, cfg.run_dir / "memory.json")
    assert mem["good"]["volatility"]["count"] == 1
    assert mem["bad"]["liquidity"]["count"] == 1
    text = to_prompt(mem)
    assert "WHAT HAS WORKED" in text and "zoo overlap" in text
