"""Charts for the results snapshot (static PNGs, light surface)."""
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

SURF, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e0"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
plt.rcParams.update({"font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "figure.facecolor": SURF,
                     "axes.facecolor": SURF})


def tidy(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)


def main(run_dir: Path, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    R = pd.read_csv(run_dir / "portfolio_trial_returns.csv", index_col=0, parse_dates=True)
    bench = pd.read_csv(run_dir / "daily_returns.csv", index_col=0, parse_dates=True)["benchmark|valid"]
    show = {"1_naive_topk_equal": "Naive top-30 equal weight",
            "2_plus_bands": "+ no-trade bands",
            "5_market_neutral_long_short": "Dollar-neutral long/short"}
    fig, ax = plt.subplots(figsize=(9, 4.4))
    idx = R[list(show)[0]].dropna().index
    cum_b = ((1 + bench.reindex(idx).fillna(0)).cumprod() - 1) * 100
    ax.plot(idx, cum_b, color=INK2, lw=1.5, ls=(0, (4, 3)), label="CSI 300 (the market)")
    ax.annotate(f"{cum_b.iloc[-1]:+.0f}%", (idx[-1], cum_b.iloc[-1]), xytext=(6, 0),
                textcoords="offset points", va="center", color=INK2, fontsize=9)
    for (k, lab), col in zip(show.items(), SERIES, strict=False):
        d = R[k].dropna()
        cum = ((1 + d).cumprod() - 1) * 100
        ax.plot(cum.index, cum, color=col, lw=2, label=lab)
        ax.annotate(f"{cum.iloc[-1]:+.0f}%", (cum.index[-1], cum.iloc[-1]),
                    xytext=(6, 0), textcoords="offset points", va="center", color=INK, fontsize=9)
    ax.axhline(0, color=INK2, lw=1)
    ax.set_ylabel("Cumulative net return (%), after costs and impact")
    ax.set_title("Same signal, three portfolio constructions (validation 2021-24, net)",
                 loc="left", color=INK, fontsize=12)
    ax.legend(frameon=False, loc="lower left", fontsize=9, labelcolor=INK)
    tidy(ax)
    fig.tight_layout()
    fig.savefig(out_dir / "chart_portfolio_ladder.png", dpi=160)

    C = pd.read_csv(run_dir / "capacity_curve.csv")
    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    f = C[C.faithful]
    ax.plot(f.capital, f.excess_ann * 100, color=SERIES[0], lw=2, marker="o", ms=7,
            label="excess return vs index")
    nf = C[~C.faithful]
    if len(nf):
        ax.plot(pd.concat([f.capital.tail(1), nf.capital]), pd.concat([f.excess_ann.tail(1), nf.excess_ann]) * 100,
                color=INK2, lw=1.5, ls=(0, (4, 3)), marker="o", ms=6,
                label="caps bind: no longer the same strategy")
    ax.axhline(0, color=INK2, lw=1)
    ax.set_xscale("log")
    ax.set_xlabel("Book size (CNY)")
    ax.set_ylabel("Excess return vs CSI 300 (%/yr)")
    ax.set_title("Capacity: where market impact eats the edge", loc="left", color=INK, fontsize=12)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK)
    tidy(ax)
    fig.tight_layout()
    fig.savefig(out_dir / "chart_capacity.png", dpi=160)

    D = pd.read_csv(run_dir / "discover_candidates.csv")
    fig, ax = plt.subplots(figsize=(6.6, 5))
    ax.scatter(D.ic_mean, D.later_ic_mean, s=26, color=SERIES[0], alpha=0.75,
               edgecolor=SURF, linewidth=1)
    lim = [min(D.ic_mean.min(), D.later_ic_mean.min()) - 0.005,
           max(D.ic_mean.max(), D.later_ic_mean.max()) + 0.005]
    ax.plot(lim, lim, color=INK2, lw=1, ls=(0, (4, 3)))
    ax.text(lim[1], lim[1], " no decay", color=INK2, fontsize=9, ha="right", va="bottom")
    ax.axhline(0, color=GRID, lw=1)
    ax.axvline(0, color=GRID, lw=1)
    ax.set_xlabel("Mean rank IC, discovery 2012-2020 (sign chosen in-sample)")
    ax.set_ylabel("Mean rank IC, 2021-2024")
    ax.set_title(f"All {len(D)} candidates: in-sample vs later", loc="left", color=INK, fontsize=12)
    tidy(ax)
    ax.grid(False)
    fig.tight_layout()
    fig.savefig(out_dir / "chart_alpha_decay.png", dpi=160)
    print("charts written to", out_dir)


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "runs/cn_csi300"),
         Path(sys.argv[2] if len(sys.argv) > 2 else "results/v0.3-2026-09-20"))
