"""Engine and session handling. SQLite by default, Postgres via DATABASE_URL."""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

_ENGINES: dict[str, Engine] = {}


def database_url(default_dir: str | Path = "runs") -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    p = Path(default_dir)
    p.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{p / 'alphalab.db'}"


def get_engine(url: str | None = None) -> Engine:
    url = url or database_url()
    if url not in _ENGINES:
        eng = create_engine(url, future=True)
        if url.startswith("sqlite"):
            @event.listens_for(eng, "connect")
            def _pragmas(conn, _):           # WAL + FK enforcement: concurrent reads, real constraints
                cur = conn.cursor()
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA foreign_keys=ON")
                cur.close()
        _ENGINES[url] = eng
    return _ENGINES[url]


@contextmanager
def session_scope(url: str | None = None):
    maker = sessionmaker(bind=get_engine(url), future=True, expire_on_commit=False)
    s = maker()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
