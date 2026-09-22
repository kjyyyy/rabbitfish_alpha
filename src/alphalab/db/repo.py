"""Repository functions: the only place the rest of the lab touches the database."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select

from .models import ExceptionRecord, ForwardSignal, Fundamental, LibraryFactor, Run, Trial
from .session import session_scope

_NUM = {"sign", "nodes", "zoo_overlap", "ic_mean", "ic_t", "ls_sharpe_ann", "dsr",
        "later_ic_mean", "n_trials_at_eval"}
_COLS = {c.name for c in Trial.__table__.columns}


def _coerce(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if k not in _COLS or k in ("id", "created_at"):
            continue
        if k in _NUM:
            try:
                out[k] = None if v in (None, "") else float(v) if k not in (
                    "sign", "nodes", "zoo_overlap", "n_trials_at_eval") else int(float(v))
            except (TypeError, ValueError):
                out[k] = None
        else:
            out[k] = "" if v is None else str(v)
    return out


def ensure_run(run_id: str, config_name: str, config_sha: str = "", git_sha: str = "",
               alphalab_version: str = "", url: str | None = None) -> None:
    with session_scope(url) as s:
        if s.scalar(select(Run).where(Run.run_id == run_id)) is None:
            s.add(Run(run_id=run_id, config_name=config_name, config_sha=config_sha,
                      git_sha=git_sha, alphalab_version=alphalab_version))


def add_trial(row: dict, url: str | None = None) -> bool:
    """Insert one trial. Returns False if it was already recorded (idempotent)."""
    data = _coerce(row)
    if not data.get("run_id"):
        return False
    with session_scope(url) as s:
        dup = s.scalar(select(Trial).where(Trial.run_id == data["run_id"],
                                           Trial.stage == data.get("stage", ""),
                                           Trial.name == data.get("name", ""),
                                           Trial.fingerprint == data.get("fingerprint", "")))
        if dup is not None:
            return False
        s.add(Trial(**data))
        return True


def count_distinct_formulas(stage_prefix: str = "discover", url: str | None = None) -> int:
    """The trial count the Deflated Sharpe deflates against, across all runs."""
    with session_scope(url) as s:
        return int(s.scalar(
            select(func.count(func.distinct(Trial.fingerprint)))
            .where(Trial.stage.like(f"{stage_prefix}%"), Trial.fingerprint != "")) or 0)


def upsert_library(config_name: str, item: dict, url: str | None = None) -> None:
    with session_scope(url) as s:
        row = s.scalar(select(LibraryFactor).where(LibraryFactor.config_name == config_name,
                                                   LibraryFactor.name == item["name"]))
        if row is None:
            row = LibraryFactor(config_name=config_name, name=item["name"])
            s.add(row)
        for k in ("expr", "family", "sign", "source", "status", "strikes", "passes",
                  "fingerprint", "ic_t", "dsr"):
            if k in item and item[k] is not None:
                setattr(row, k, item[k] if k not in ("sign", "strikes", "passes")
                        else int(item[k]))


def sync_library(config_name: str, items: dict, url: str | None = None) -> tuple[int, int]:
    """Upsert every JSON library member and remove DB rows not in the JSON."""
    names = set(items.keys())
    with session_scope(url) as s:
        existing = {r.name: r for r in s.scalars(
            select(LibraryFactor).where(LibraryFactor.config_name == config_name)).all()}
        for name, item in items.items():
            row = existing.get(name)
            if row is None:
                row = LibraryFactor(config_name=config_name, name=name)
                s.add(row)
            for k in ("expr", "family", "sign", "source", "status", "strikes", "passes",
                      "fingerprint", "ic_t", "dsr"):
                if k in item and item[k] is not None:
                    setattr(row, k, item[k] if k not in ("sign", "strikes", "passes")
                            else int(item[k]))
        for name, row in list(existing.items()):
            if name not in names:
                s.delete(row)
    return len(items), len(names)


def count_library(config_name: str, url: str | None = None) -> int:
    with session_scope(url) as s:
        return int(s.scalar(
            select(func.count()).select_from(LibraryFactor)
            .where(LibraryFactor.config_name == config_name)) or 0)


def library(config_name: str, statuses=("probation", "active"), url: str | None = None) -> list[dict]:
    with session_scope(url) as s:
        rows = s.scalars(select(LibraryFactor).where(LibraryFactor.config_name == config_name,
                                                     LibraryFactor.status.in_(list(statuses)))).all()
        return [dict(name=r.name, expr=r.expr, sign=r.sign, family=r.family, source=r.source,
                     status=r.status) for r in rows]


def add_exception(config_name: str, kind: str, scope: str, reason: str, author: str = "",
                  url: str | None = None) -> None:
    with session_scope(url) as s:
        s.add(ExceptionRecord(config_name=config_name, kind=kind, scope=scope,
                              reason=reason, author=author))


def record_forward(config_name: str, manifest: dict, url: str | None = None) -> None:
    with session_scope(url) as s:
        existing = s.scalar(select(ForwardSignal).where(
            ForwardSignal.config_name == config_name,
            ForwardSignal.signal_date == dt.date.fromisoformat(manifest["signal_date"]),
            ForwardSignal.strategy == manifest["strategy"]))
        if existing is not None:
            return
        s.add(ForwardSignal(config_name=config_name,
                            signal_date=dt.date.fromisoformat(manifest["signal_date"]),
                            strategy=manifest["strategy"], file_sha256=manifest["file_sha256"],
                            git_sha=manifest.get("git_sha", ""),
                            config_sha=manifest.get("config_sha", ""),
                            topk=int(manifest.get("topk", 0))))


def bulk_fundamentals(rows, url: str | None = None) -> int:
    """Insert parsed SEC rows, skipping duplicates. Returns rows written."""
    written = 0
    with session_scope(url) as s:
        for r in rows:
            key = dict(cik=int(r["cik"]), tag=str(r["tag"]),
                       period=_as_date(r["period"]), filed=_as_date(r["filed"]),
                       adsh=str(r.get("adsh", "")))
            if s.scalar(select(Fundamental).filter_by(**key)) is not None:
                continue
            s.add(Fundamental(**key, value=float(r["value"]), form=str(r.get("form", ""))))
            written += 1
    return written


def fundamentals_as_of(asof, url: str | None = None) -> list[dict]:
    """Rows the market could already see on `asof` - the point-in-time read path."""
    d = _as_date(asof)
    with session_scope(url) as s:
        rows = s.scalars(select(Fundamental).where(Fundamental.filed <= d)).all()
        return [dict(cik=r.cik, tag=r.tag, period=r.period, filed=r.filed, value=r.value)
                for r in rows]


def _as_date(v):
    if isinstance(v, dt.date) and not isinstance(v, dt.datetime):
        return v
    if isinstance(v, dt.datetime):
        return v.date()
    return dt.date.fromisoformat(str(v)[:10])


def _iso_utc(v) -> str:
    """SQLite drops the timezone, so a value read back is naive while a value
    just flushed is aware. Normalise, or the same row reports two timestamps."""
    if v is None:
        return ""
    if v.tzinfo is None:
        v = v.replace(tzinfo=dt.timezone.utc)
    return v.astimezone(dt.timezone.utc).isoformat()


def preregister(config_name: str, item: dict, url: str | None = None) -> dict:
    """Record a hypothesis before it is tested. Idempotent on content."""
    from .models import Hypothesis
    with session_scope(url) as s:
        existing = s.scalar(select(Hypothesis).where(
            Hypothesis.config_name == config_name,
            Hypothesis.content_sha == item["content_sha"]))
        if existing is not None:
            return dict(created=False, id=existing.id,
                        created_at=_iso_utc(existing.created_at),
                        content_sha=existing.content_sha)
        h = Hypothesis(config_name=config_name, **item)
        s.add(h)
        s.flush()
        return dict(created=True, id=h.id, created_at=_iso_utc(h.created_at),
                    content_sha=h.content_sha)


def hypotheses(config_name: str, url: str | None = None) -> list[dict]:
    from .models import Hypothesis
    with session_scope(url) as s:
        rows = s.scalars(select(Hypothesis)
                         .where(Hypothesis.config_name == config_name)
                         .order_by(Hypothesis.created_at.desc())).all()
        return [dict(id=h.id, name=h.name, expr=h.expr, sign=h.sign, rationale=h.rationale,
                     author=h.author, origin=h.origin, fingerprint=h.fingerprint,
                     content_sha=h.content_sha, status=h.status,
                     created_at=_iso_utc(h.created_at))
                for h in rows]
