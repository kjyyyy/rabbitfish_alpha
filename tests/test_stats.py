import numpy as np
import pandas as pd

from alphalab.stats import deflated_sharpe, hurdle_sharpe, pbo_cscv


def test_pbo_on_noise_is_about_half():
    rng = np.random.default_rng(1)
    M = pd.DataFrame(rng.normal(0, 0.02, (400, 200)))
    pbo, _ = pbo_cscv(M, max_combos=300)
    assert 0.35 < pbo < 0.65


def test_dsr_penalises_best_of_many_noise():
    rng = np.random.default_rng(2)
    M = pd.DataFrame(rng.normal(0, 0.02, (460, 500)))
    sr = M.mean() / M.std()
    best = M[sr.idxmax()]
    dsr, _, _ = deflated_sharpe(best, 500, sr.var())
    assert dsr < 0.95                       # a lucky winner must not pass
    # note: a true annual Sharpe of ~1.4 (0.004/0.02 weekly) gives DSR ~0.91 after 500 trials
    real = pd.Series(rng.normal(0.006, 0.02, 460))
    assert deflated_sharpe(real, 500, sr.var())[0] > 0.95


def test_hurdle_rises_with_every_trial():
    """The bar a candidate must clear is set by how much you searched, not by
    what you learned - the reason a trial budget is a research decision."""
    h = [hurdle_sharpe(n, 0.02, 400) for n in (1, 10, 100, 1000)]
    assert all(b > a for a, b in zip(h, h[1:], strict=False)), h
    assert h[0] > 0
    # a candidate that clears the hurdle really does clear the target DSR
    x = np.random.default_rng(0).standard_normal(400)
    x = (x - x.mean()) / x.std(ddof=1) + h[2] / np.sqrt(52) * 1.02
    dsr, _, _ = deflated_sharpe(x, 100, 0.02)
    assert dsr >= 0.95
