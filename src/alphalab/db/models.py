"""Schema for the research record.

Design rules:
* every row that could ever be selected on is a column, not JSON;
* `trials` is append-only by convention and by unique constraint - the same
  formula in the same run cannot be logged twice, which is what keeps the
  Deflated-Sharpe trial count honest;
* `fundamentals` carries both `period` and `filed`, and every read path filters
  on `filed` (see sources/fundamentals.py).
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    config_name: Mapped[str] = mapped_column(String(128))
    config_sha: Mapped[str] = mapped_column(String(32))
    git_sha: Mapped[str] = mapped_column(String(64), default="")
    alphalab_version: Mapped[str] = mapped_column(String(32), default="")
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    note: Mapped[str] = mapped_column(Text, default="")
    trials: Mapped[list["Trial"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class Trial(Base):
    """One evaluated or rejected candidate - the unit the DSR deflates against."""
    __tablename__ = "trials"
    __table_args__ = (
        # a named candidate is logged once per run and stage; rows without a
        # formula fingerprint (family-level tests) are distinguished by name
        UniqueConstraint("run_id", "stage", "name", "fingerprint", name="uq_trial_run_stage_name"),
        Index("ix_trials_stage_status", "stage", "status"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(32), ForeignKey("runs.run_id"), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    stage: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(128))
    source: Mapped[str] = mapped_column(String(32), index=True)
    source_model: Mapped[str] = mapped_column(String(64), default="")
    prompt_sha: Mapped[str] = mapped_column(String(32), default="")
    parent_id: Mapped[str] = mapped_column(String(128), default="")
    fingerprint: Mapped[str] = mapped_column(String(32), default="", index=True)
    family: Mapped[str] = mapped_column(String(32), default="", index=True)
    expr: Mapped[str] = mapped_column(Text, default="")
    rationale: Mapped[str] = mapped_column(Text, default="")
    sign: Mapped[int | None] = mapped_column(Integer, nullable=True)
    nodes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    zoo_overlap: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ic_mean: Mapped[float | None] = mapped_column(Float, nullable=True)
    ic_t: Mapped[float | None] = mapped_column(Float, nullable=True)
    ls_sharpe_ann: Mapped[float | None] = mapped_column(Float, nullable=True)
    dsr: Mapped[float | None] = mapped_column(Float, nullable=True)
    later_ic_mean: Mapped[float | None] = mapped_column(Float, nullable=True)
    # inner-holdout evidence: what the search allocator is rewarded on (v0.10)
    inner_oos_ic: Mapped[float | None] = mapped_column(Float, nullable=True)
    inner_oos_t: Mapped[float | None] = mapped_column(Float, nullable=True)
    n_trials_at_eval: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="", index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    run: Mapped["Run"] = relationship(back_populates="trials")


class LibraryFactor(Base):
    """Lifecycle state of a factor: probation -> active -> retired."""
    __tablename__ = "library_factors"
    __table_args__ = (UniqueConstraint("config_name", "name", name="uq_library_config_name"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    config_name: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(128))
    expr: Mapped[str] = mapped_column(Text)
    family: Mapped[str] = mapped_column(String(32), default="")
    sign: Mapped[int] = mapped_column(Integer, default=1)
    source: Mapped[str] = mapped_column(String(32), default="")
    status: Mapped[str] = mapped_column(String(24), default="probation", index=True)
    strikes: Mapped[int] = mapped_column(Integer, default=0)
    passes: Mapped[int] = mapped_column(Integer, default=0)
    fingerprint: Mapped[str] = mapped_column(String(32), default="", index=True)
    added_on: Mapped[dt.date] = mapped_column(Date, default=lambda: dt.date.today())
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    ic_t: Mapped[float | None] = mapped_column(Float, nullable=True)
    dsr: Mapped[float | None] = mapped_column(Float, nullable=True)


class ExceptionRecord(Base):
    """Append-only log of deviations from the standard protocol."""
    __tablename__ = "protocol_exceptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    config_name: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    kind: Mapped[str] = mapped_column(String(48))
    scope: Mapped[str] = mapped_column(String(128))
    reason: Mapped[str] = mapped_column(Text)
    author: Mapped[str] = mapped_column(String(64), default="")


class ForwardSignal(Base):
    """Hash-stamped pre-registered signals - the only clean out-of-sample record."""
    __tablename__ = "forward_signals"
    __table_args__ = (UniqueConstraint("config_name", "signal_date", "strategy",
                                       name="uq_forward_date_strategy"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    config_name: Mapped[str] = mapped_column(String(128), index=True)
    signal_date: Mapped[dt.date] = mapped_column(Date, index=True)
    strategy: Mapped[str] = mapped_column(String(64))
    published_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    file_sha256: Mapped[str] = mapped_column(String(64))
    git_sha: Mapped[str] = mapped_column(String(64), default="")
    config_sha: Mapped[str] = mapped_column(String(32), default="")
    topk: Mapped[int] = mapped_column(Integer, default=0)
    realised_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    benchmark_return: Mapped[float | None] = mapped_column(Float, nullable=True)


class Hypothesis(Base):
    """A factor idea recorded BEFORE it is evaluated.

    Pre-registration is the whole value: an idea timestamped and hashed before
    anyone has seen how it performs cannot be quietly reworded afterwards to
    match the result. Nothing here is accepted by being written down - it faces
    exactly the same gates as every other candidate when `discover` runs.
    """
    __tablename__ = "hypotheses"
    __table_args__ = (
        UniqueConstraint("config_name", "content_sha", name="uq_hypothesis_content"),
        Index("ix_hypotheses_config_created", "config_name", "created_at"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    config_name: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(128))
    expr: Mapped[str] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(32), default="", index=True)
    sign: Mapped[int] = mapped_column(Integer, default=1)
    rationale: Mapped[str] = mapped_column(Text, default="")
    author: Mapped[str] = mapped_column(String(64), default="")
    origin: Mapped[str] = mapped_column(String(32), default="ui")
    content_sha: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    status: Mapped[str] = mapped_column(String(24), default="pre-registered", index=True)


class Fundamental(Base):
    """Point-in-time fundamentals. `filed` is what every read path filters on."""
    __tablename__ = "fundamentals"
    __table_args__ = (
        UniqueConstraint("cik", "tag", "period", "filed", "adsh", name="uq_fundamental_row"),
        Index("ix_fundamentals_cik_tag_filed", "cik", "tag", "filed"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    cik: Mapped[int] = mapped_column(Integer, index=True)
    adsh: Mapped[str] = mapped_column(String(32), default="")
    tag: Mapped[str] = mapped_column(String(96), index=True)
    period: Mapped[dt.date] = mapped_column(Date)
    filed: Mapped[dt.date] = mapped_column(Date, index=True)
    value: Mapped[float] = mapped_column(Float)
    form: Mapped[str] = mapped_column(String(16), default="")
