"""Effective number of trials.

The Deflated Sharpe Ratio deflates by N, the number of strategies tried. Using
the raw count assumes every trial was an *independent* lottery ticket. In a
formulaic-alpha search most candidates are near-copies of each other - 200
variations on "recent returns" are not 200 independent chances to get lucky -
so the raw count over-penalises, and a genuine edge can be buried.

Two standard ways to count correlated tests:

* **Eigenvalue (participation ratio)**: N_eff = (sum λ)² / sum λ² on the
  correlation matrix of candidate return series. One perfectly correlated
  block counts as one trial; orthogonal series count in full.
* **Average-correlation**: N_eff = N / (1 + (N-1)·rho_bar), the classic
  effective-sample-size adjustment.

This module reports both. The lab keeps the **raw count as the default** for
gating, and shows the adjusted figures alongside: choosing whichever N makes a
strategy pass is exactly the researcher degree of freedom the DSR exists to
control.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _clean(M: pd.DataFrame, min_obs: int = 30) -> pd.DataFrame:
    M = M.dropna(axis=1, thresh=min_obs)
    return M.loc[:, M.std() > 0]


def eigenvalue_neff(M: pd.DataFrame) -> float:
    """Participation ratio of the correlation matrix's eigenvalues."""
    M = _clean(M)
    if M.shape[1] < 2:
        return float(M.shape[1])
    C = np.nan_to_num(M.corr().to_numpy(), nan=0.0)
    np.fill_diagonal(C, 1.0)
    lam = np.linalg.eigvalsh(C)
    lam = np.clip(lam, 0, None)
    if lam.sum() <= 0:
        return float(M.shape[1])
    return float(lam.sum() ** 2 / (lam ** 2).sum())


def avg_corr_neff(M: pd.DataFrame) -> tuple[float, float]:
    """(N_eff, mean absolute pairwise correlation)."""
    M = _clean(M)
    n = M.shape[1]
    if n < 2:
        return float(n), 0.0
    C = M.corr().to_numpy()
    iu = np.triu_indices(n, 1)
    rho = float(np.nanmean(np.abs(C[iu])))
    return float(n / (1 + (n - 1) * rho)), rho


def report(M: pd.DataFrame, n_raw: int) -> dict:
    """Trial-count diagnostics for a matrix of candidate return series."""
    eig = eigenvalue_neff(M)
    avg, rho = avg_corr_neff(M)
    return dict(n_raw=int(n_raw), n_eff_eigenvalue=round(eig, 1),
                n_eff_avg_corr=round(avg, 1), mean_abs_corr=round(rho, 3),
                note="raw N is used for gating; effective N is reported only")
