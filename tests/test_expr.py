import random

import pytest

from alphalab import expr as E

ATTACKS = ["$close.__class__", "$close.real", "__import__('os').system('x')",
           "(lambda: 1)()", "Ref($close,-1)", "Mean(Ref($close,-5),10)", "Foo($close,5)",
           "$earnings", "Mean($close,$volume)", "Mean($close,1000)", "open('x')",
           "Mean($close, window=5)", "[1,2]", "'abc'", "$close if 1 else 2"]


@pytest.mark.parametrize("e", ATTACKS)
def test_auditor_rejects(e):
    assert not E.is_valid(e)[0]


@pytest.mark.parametrize("e", ["Ref($close,20)/Ref($close,240)-1", "Corr($close,Log($volume+1),20)",
                               "Std($close/Ref($close,1)-1,20)", "-Mean($close,5)"])
def test_auditor_accepts(e):
    assert E.is_valid(e)[0]


def test_canonical_commutative():
    assert E.canonical("Corr($close,$volume,20)") == E.canonical("Corr($volume,$close,20)")
    assert E.canonical("$close+$open") == E.canonical("$open+$close")
    assert E.canonical("$close-$open") != E.canonical("$open-$close")


def test_complexity_and_zoo():
    c = E.complexity("Corr($close,Log($volume+1),20)")
    assert c.raw_fields == 2 and c.nodes >= 5
    z = E.Zoo(["Mean($close/Ref($close,1)-1,20)"])
    assert z.overlap("Mean($close/Ref($close,1)-1,5)") == z.overlap("Mean($close/Ref($close,1)-1,20)")
    assert z.overlap("Std($volume,10)") <= 1


def test_gp_operators_stay_valid():
    rng = random.Random(0)
    for _ in range(500):
        a = E.random_expr(rng)
        try:
            b = E.mutate(a, rng)
            c = E.crossover(a, b, rng)
        except E.ExprError:
            continue
        assert E.is_valid(b)[0] and E.is_valid(c)[0]
