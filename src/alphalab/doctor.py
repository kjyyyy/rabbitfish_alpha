"""`alphalab doctor` - can this machine run the lab right now, and if not, why?

Every check answers one question a new user would otherwise answer by reading a
traceback: is the package installed with the extras it needs, is there data, is
the database migrated, are the keys present, do the model endpoints answer.
Each failure prints the exact command that fixes it.

Nothing here prints a secret. A key is reported as set or not set, never echoed,
and never written to the ledger, the database or a run artefact.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from pathlib import Path

from . import __version__
from .config import Config

OK, WARN, BAD = "ok", "warn", "fail"


def _check(name, state, detail, fix=""):
    return dict(name=name, state=state, detail=detail, fix=fix)


def _python() -> dict:
    v = sys.version_info
    good = (3, 10) <= (v.major, v.minor) < (3, 13)
    return _check("python", OK if good else BAD, f"{v.major}.{v.minor}.{v.micro}",
                  "" if good else "the lab supports 3.10-3.12 (Qlib pins the upper bound)")


def _package() -> dict:
    return _check("alphalab", OK, f"v{__version__} from {Path(__file__).resolve().parents[1]}")


def _extras() -> list[dict]:
    out = []
    for mod, extra, why in (("qlib", "qlib", "the data engine: no data access without it"),
                            ("anthropic", "llm", "only needed for the Anthropic proposer"),
                            ("openai", "llm", "needed for Ollama, vLLM and OpenAI"),
                            ("lightgbm", "", "model stage"),
                            ("fastapi", "web", "only needed for `alphalab serve`")):
        have = importlib.util.find_spec(mod) is not None
        state = OK if have else (WARN if extra in ("llm", "web") else BAD)
        out.append(_check(f"import {mod}", state, "installed" if have else "missing",
                          "" if have else (f"pip install -e '.[{extra}]'" if extra else
                                           "pip install -e .") + f"  ({why})"))
    return out


def _data(cfg: Config) -> list[dict]:
    p = Path(cfg.market.provider_uri)
    if not p.exists():
        return [_check("market data", BAD, f"{p} does not exist",
                       "alphalab download-cn   (free CSI-300 set, ~570MB)  or"
                       "  alphalab ingest --csv <dir>   to use your own OHLCV files")]
    cal = p / "calendars" / "day.txt"
    if not cal.exists():
        return [_check("market data", BAD, f"{p} has no calendars/day.txt",
                       "the directory is not a Qlib provider: re-run `alphalab download-cn` "
                       "or `alphalab ingest`")]
    days = cal.read_text().split()
    rows = [_check("market data", OK, f"{len(days)} sessions, {days[0]} .. {days[-1]}, at {p}")]
    # is the data recent enough for the config's own end date?
    if days[-1] < cfg.splits.data_end:
        rows.append(_check("data freshness", WARN,
                           f"data ends {days[-1]}, config expects {cfg.splits.data_end}",
                           "alphalab download-cn   (forward pre-registration needs fresh data "
                           "every week, or no week is ever clean)"))
    return rows


def _keys(cfg: Config) -> list[dict]:
    rows = []
    dotenv = Path(os.environ.get("ALPHALAB_ENV_FILE") or ".env")
    if dotenv.is_file():
        names = [ln.split("=")[0].strip() for ln in dotenv.read_text().splitlines()
                 if ln.strip() and not ln.strip().startswith("#") and "=" in ln]
        rows.append(_check(".env", OK, f"loaded {dotenv} ({len(names)} entries: "
                                       f"{', '.join(names[:4])}{'...' if len(names) > 4 else ''})"))
    else:
        rows.append(_check(".env", WARN, "missing",
                           "alphalab init   (writes a git-ignored .env you can paste keys into)"))
    needed = set()
    for provider, key in ((cfg.llm.provider, "ANTHROPIC_API_KEY"),
                          (cfg.llm.critic_provider, "ANTHROPIC_API_KEY")):
        if provider == "anthropic":
            needed.add(key)
    for provider in (cfg.llm.provider, cfg.llm.critic_provider):
        if provider == "openai":
            needed.add("OPENAI_API_KEY")
    for key in sorted(needed):
        have = bool(os.environ.get(key))
        local = key == "OPENAI_API_KEY"
        rows.append(_check(key, OK if have else (WARN if local else BAD),
                           "set" if have else "not set",          # never echo the value
                           "" if have else (f"put {key}=... in .env" + (
                               "  (for Ollama or vLLM any non-empty value works)" if local else ""))))
    if not needed:
        rows.append(_check("api keys", OK, f"none needed for provider '{cfg.llm.provider}'"))
    return rows


def _database(cfg: Config) -> list[dict]:
    from .db.session import database_url
    url = cfg.storage.database_url or database_url()
    shown = url.split("@")[-1] if "@" in url else url        # never print a password
    try:
        from sqlalchemy import inspect

        from .db.session import get_engine
        eng = get_engine(url)
        names = set(inspect(eng).get_table_names())
    except Exception as e:                                   # noqa: BLE001
        return [_check("database", BAD, f"{type(e).__name__}: {str(e)[:80]}",
                       "make db   (alembic upgrade head)")]
    if "trials" not in names:
        return [_check("database", BAD, f"reachable at {shown} but not migrated",
                       "make db   (alembic upgrade head)")]
    rows = [_check("database", OK, f"{shown}, {len(names)} tables")]
    try:
        from alembic.runtime.migration import MigrationContext
        from alembic.script import ScriptDirectory
        with eng.connect() as c:
            current = MigrationContext.configure(c).get_current_revision()
        head = ScriptDirectory.from_config(_alembic_cfg()).get_current_head()
        rows.append(_check("migrations", OK if current == head else WARN,
                           f"at {current}" + ("" if current == head else f", head is {head}"),
                           "" if current == head else "make db"))
    except Exception:                                        # noqa: BLE001 - not a checkout
        pass
    return rows


def _alembic_cfg():
    from alembic.config import Config as AConfig
    return AConfig("alembic.ini")


def _disk() -> dict:
    free = shutil.disk_usage(".").free / 1e9
    return _check("disk free", OK if free > 2 else WARN, f"{free:.1f} GB",
                  "" if free > 2 else "the CN dataset needs ~1.5GB unpacked")


def run(cfg: Config, check_models: bool = True, log=print) -> dict:
    rows = [_python(), _package(), *_extras(), *_data(cfg), *_keys(cfg),
            *_database(cfg), _disk()]
    if check_models:
        from .llm_check import check_one
        for role in ("proposer", "critic"):
            r = check_one(cfg, role, log=lambda *_: None)
            rows.append(_check(f"model: {role}", OK if r.get("ok") else WARN,
                               f"{r['provider']}:{r['model']} @ {r['base_url']}"
                               + (f" ({r['latency_s']}s)" if r.get("ok") else
                                  f" - {r.get('error', '')[:60]}"),
                               "" if r.get("ok") else
                               "ollama serve && ollama pull llama3.1:8b, or use "
                               "configs/local_offline.yaml (provider: mock, no network)"))

    mark = {OK: "ok  ", WARN: "warn", BAD: "FAIL"}
    log(f"alphalab doctor - config '{cfg.name}'\n")
    for r in rows:
        log(f"  [{mark[r['state']]}] {r['name']:18s} {r['detail']}")
        if r["fix"]:
            log(f"         -> {r['fix']}")
    bad = [r for r in rows if r["state"] == BAD]
    warn = [r for r in rows if r["state"] == WARN]
    log(f"\n{len(rows) - len(bad) - len(warn)} ok, {len(warn)} warning(s), {len(bad)} blocking")
    if not bad:
        log("ready: try `alphalab sanity` then `alphalab discover`")
    return dict(rows=rows, ok=not bad, blocking=[r["name"] for r in bad])
