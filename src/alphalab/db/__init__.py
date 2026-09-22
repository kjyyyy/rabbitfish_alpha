"""Relational storage for the research record.

CSV files are fine for a laptop and terrible for anything else: no schema, no
constraints, no concurrent writers, and no way to ask "every trial that used
this data vintage". This package puts the research record - trials, library,
exceptions, forward signals, point-in-time fundamentals - in a real database
with Alembic migrations, while keeping the CSV mirrors for git-friendly diffs.

Default is SQLite (zero setup, `runs/alphalab.db`); set `DATABASE_URL` to point
at Postgres in production. The models avoid anything SQLite-specific so the same
migrations run on both.
"""
from .models import Base, ExceptionRecord, ForwardSignal, Fundamental, LibraryFactor, Run, Trial
from .session import get_engine, session_scope

__all__ = ["Base", "Run", "Trial", "LibraryFactor", "ExceptionRecord", "ForwardSignal",
           "Fundamental", "get_engine", "session_scope"]
