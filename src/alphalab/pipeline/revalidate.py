"""Re-check the factor library against evidence it was not discovered on.

`Library.revalidate` existed from v0.3 and was called only from its own unit
test, so 18 factors sat in `probation` forever: none promoted, none retired,
no recheck ever recorded. The decay this lab measures (roughly two-thirds of
IC lost after discovery) was never acted on.

This closes that arrow. It scores every library member over a recent window
that starts AFTER the discovery window ends, then:

  probation -> active   two consecutive rechecks at t >= gates.promote_t_min
  any       -> retired  two consecutive rechecks below `min_t` (existing rule)

Both directions need two consecutive checks, so one quiet quarter neither
promotes nor kills a factor. Every recheck is appended to the factor's history
and to the research ledger, because a promotion that leaves no record is
indistinguishable from a decision made after seeing the result.
"""
from __future__ import annotations

import datetime as dt
import json

import numpy as np
import pandas as pd

from .. import data
from ..config import Config
from ..evaluate import evaluate
from ..ledger import Ledger
from ..library import Library


def already_checked(members: list[dict], window: str) -> bool:
    """True when every member's most recent recheck used this exact window.

    Two "consecutive" rechecks of the same sessions are one piece of evidence
    counted twice - and since two consecutive checks are what promote or retire
    a factor, that is enough to move the whole library on no new information.
    """
    return bool(members) and all(m["history"][-1].get("window") == window for m in members)


def run(cfg: Config, log=print) -> dict:
    lib = Library(cfg.run_dir / "library.json")
    members = [v for v in lib.items.values() if v["status"] != "retired"]
    if not members:
        raise SystemExit("library is empty - run `alphalab discover` first")

    start = f"{int(cfg.splits.discover_end[:4]) + 1}-01-01"
    end = cfg.splits.data_end
    names = [m["name"] for m in members]
    F = data.features(cfg, [m["expr"] for m in members], names, start, end)
    F = F.replace([np.inf, -np.inf], np.nan)
    y = data.label(cfg, start, end)
    IC, _, _ = evaluate(F, y)

    # only the most recent stretch counts as "live"
    look = cfg.model.combiner_lookback_days
    recent = IC.tail(look)
    # Guard: two "consecutive" rechecks of the same window are one piece of
    # evidence counted twice. A streak may only advance on new data.
    window = f"{recent.index[0].date()}..{recent.index[-1].date()}"
    if already_checked(members, window):
        log(f"already rechecked on {window} - no new sessions since the last recheck, so "
            f"nothing is counted. Refresh the data and run again.")
        return dict(window=window, skipped=True, promoted=[], retired=[],
                    unchanged=len(members), factors=[])

    before = {m["name"]: m["status"] for m in members}
    lib.revalidate(recent, min_t=1.0, promote_t=cfg.gates.promote_t_min, window=window)
    lib.save()

    led = Ledger(cfg.run_dir / "ledger.csv", cfg=cfg)
    rows = []
    for name in names:
        it = lib.items[name]
        last = it["history"][-1]
        t = last.get("recheck_t")
        rows.append(dict(name=name, family=it.get("family", ""), source=it["source"],
                         was=before[name], now=it["status"], recheck_t=t,
                         strikes=it.get("strikes", 0), passes=it.get("passes", 0),
                         discovery_ic_t=it["history"][0].get("ic_t")))
        led.log(stage="revalidate", name=name, source=it["source"], expr=it["expr"],
                sign=it["sign"], ic_t=round(t, 2) if t == t and t is not None else "",
                status=it["status"],
                reason=f"recheck over the last {look} sessions after {cfg.splits.discover_end}; "
                       f"{before[name]} -> {it['status']}")
        if getattr(cfg.storage, "use_database", True):
            try:
                from ..db import repo
                repo.upsert_library(cfg.name, it, url=cfg.storage.database_url)
            except Exception as e:                    # noqa: BLE001
                log(f"  (library not written to the database: {type(e).__name__})")

    df = pd.DataFrame(rows).sort_values("recheck_t", ascending=False, na_position="last")
    out = dict(window=window, window_start=start, window_end=end, sessions=int(len(recent)),
               promoted=[r["name"] for r in rows if r["was"] != r["now"] == "active"],
               retired=[r["name"] for r in rows if r["was"] != r["now"] == "retired"],
               unchanged=sum(1 for r in rows if r["was"] == r["now"]),
               factors=rows,
               library_sha=lib.state_sha(),
               generated_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
    (cfg.run_dir / "revalidation.json").write_text(json.dumps(out, indent=2, default=float))
    log(df.to_string(index=False, float_format=lambda v: f"{v:.2f}"))
    log(f"\n{len(rows)} factors rechecked over {len(recent)} sessions from {start}: "
        f"{len(out['promoted'])} promoted, {len(out['retired'])} retired, "
        f"{out['unchanged']} unchanged")
    if not out["promoted"] and not out["retired"]:
        log("nothing moved - which is itself the finding: discovery-window significance "
            "is not reproducing out of period.")
    return out
