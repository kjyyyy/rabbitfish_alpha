"""Append-only research ledger (CSV). Every candidate ever generated is a row,
including rejects, because the trial count sets the Deflated-Sharpe bar."""
from __future__ import annotations

import csv
import datetime as dt
import uuid
from pathlib import Path

FIELDS = ["timestamp", "run_id", "stage", "name", "source", "source_model", "prompt_sha",
          "parent_id", "fingerprint", "expr", "rationale", "family", "sign", "nodes", "zoo_overlap",
          "ic_mean", "ic_t", "ls_sharpe_ann", "dsr", "inner_oos_ic", "inner_oos_t",
          "later_ic_mean", "n_trials_at_eval",
          "status", "reason"]


class Ledger:
    """Append-only research record. Writes the CSV mirror always, and the
    database too when one is configured - the DB is what makes "every trial that
    used this data vintage" answerable, the CSV is what makes a diff readable."""

    def __init__(self, path: Path, run_id: str | None = None, cfg=None):
        self.path = Path(path)
        self.run_id = run_id or uuid.uuid4().hex[:8]
        self.cfg = cfg
        self._db_ok = None
        self.db_failures = 0          # counted, surfaced, and reconcilable with `db verify`

    def _db_url(self):
        if self.cfg is None or not getattr(self.cfg, "storage", None):
            return None
        if not self.cfg.storage.use_database:
            return None
        return self.cfg.storage.database_url

    def _to_db(self, row: dict):
        if self.cfg is not None and not getattr(self.cfg.storage, "use_database", True):
            return
        try:
            from .db import repo
            if self._db_ok is None:
                from .provenance import git_sha, version
                repo.ensure_run(self.run_id,
                                getattr(self.cfg, "name", "unknown") if self.cfg else "unknown",
                                self.cfg.sha() if self.cfg else "",
                                git_sha=git_sha(), alphalab_version=version(),
                                url=self._db_url())
                self._db_ok = True
            repo.add_trial(row, url=self._db_url())
        except Exception as e:                       # noqa: BLE001 - never lose a CSV write
            self.db_failures += 1
            if self._db_ok is not False:
                print(f"ledger: database unavailable ({type(e).__name__}: {str(e)[:120]}), "
                      f"CSV only. The trial count in the database will be WRONG until you run "
                      f"`alphalab db import-csv`; check with `alphalab db verify`.")
            self._db_ok = False

    def log(self, **row):
        new = not self.path.exists()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        row.setdefault("timestamp", dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
        row.setdefault("run_id", self.run_id)
        with open(self.path, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
            if new:
                w.writeheader()
            w.writerow(row)
        self._to_db(row)

    def rows(self):
        if not self.path.exists():
            return []
        with open(self.path) as f:
            return list(csv.DictReader(f))

    def n_trials(self, stage_prefix: str = "discover") -> int:
        """Distinct formulas ever evaluated or rejected in discovery (all runs)."""
        fps = {r["fingerprint"] or r["expr"] for r in self.rows()
               if r["stage"].startswith(stage_prefix)}
        return len(fps)
