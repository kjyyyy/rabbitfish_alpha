"""Which code produced this run.

A research record that cannot say which version of the lab wrote it is not a
record. `runs.git_sha` existed from v0.8 but was never populated, so every run
in the database claimed to come from nowhere - which makes "did v0.5 actually
beat v0.4?" unanswerable except by reading committed markdown by hand.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from . import __version__


def git_sha(short: bool = False) -> str:
    """HEAD of the repo this package is installed from, '' outside a checkout."""
    try:
        out = subprocess.check_output(
            ["git", "-C", str(Path(__file__).resolve().parent), "rev-parse",
             "--short" if short else "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
        dirty = subprocess.call(
            ["git", "-C", str(Path(__file__).resolve().parent), "diff", "--quiet"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return out + ("-dirty" if dirty else "")
    except Exception:                                 # noqa: BLE001 - not a checkout
        return ""


def version() -> str:
    return __version__


def stamp() -> dict:
    return {"alphalab_version": version(), "git_sha": git_sha()}


def write_snapshot(cfg, headline: dict, kind: str = "model") -> Path:
    """Write results/v<version>-<date>/summary.json.

    `results/` held hand-written markdown with no v0.2, v0.8 or v0.9 entry, so
    no two versions could be compared by anything but reading. This writes the
    headline numbers next to the config hash and the commit that produced them,
    which is what makes "did v0.5 beat v0.4?" a query rather than an argument.
    """
    import datetime as dt
    import json

    d = Path("results") / f"v{version()}-{dt.date.today().isoformat()}"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "summary.json"
    prior = json.loads(p.read_text()) if p.exists() else {}
    prior[kind] = dict(headline, config_name=cfg.name, config_sha=cfg.sha(),
                       written_utc=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                       **stamp())
    p.write_text(json.dumps(prior, indent=2, default=float))
    return p
