"""The only two things the dashboard is allowed to write.

The rule is not "no writes". It is: **the dashboard may never change the rules,
and may never change a result.** Two actions pass that test, and both make the
research stronger rather than weaker:

1. **Pre-registering a hypothesis.** Writing an idea down, hashed and
   timestamped, before it has been tested is the opposite of p-hacking. It
   cannot be reworded later to match whatever came out, and it is accepted by
   nothing: it faces the same AST whitelist, complexity, originality, t, DSR
   and correlation gates as every other candidate when `discover` runs.

2. **Adding a data source.** Ingesting price files happens before any evidence
   exists, so it cannot be used to select a result. It is also audited on the
   way in and refuses to overwrite a source that already exists.

Everything else - thresholds, gate values, a factor's status, the trial count,
anything in the ledger - is read-only from here, permanently. A slider that
loosens a gate after you have seen what it rejects would undo the entire repo.
"""
from __future__ import annotations

import datetime as dt
import hashlib
from pathlib import Path

from .. import expr as E
from ..config import Config
from ..db import repo
from ..db.session import database_url
from ..factors.zoo import alpha158_exprs


class Rejected(ValueError):
    """The submission never reaches storage; the reason is shown to the user."""


def _url(cfg: Config) -> str:
    return cfg.storage.database_url or database_url()


def validate_expression(cfg: Config, expression: str) -> dict:
    """The same screen `discover` applies, run here so feedback is immediate."""
    g = cfg.gates
    expression = (expression or "").strip()
    try:
        canonical = E.canonical(expression)           # parses; raises on anything unsafe
        cx = E.complexity(expression)
        fp = E.fingerprint(expression)
    except Exception as e:                            # noqa: BLE001 - parser raises its own
        raise Rejected(f"not a valid factor expression: {e}") from None

    if cx.nodes > g.max_nodes:
        raise Rejected(f"too complex: {cx.nodes} nodes, the cap is {g.max_nodes} "
                       f"(gates.max_nodes). Complexity buys in-sample fit almost for free.")
    if cx.raw_fields > g.max_raw_fields:
        raise Rejected(f"uses {cx.raw_fields} raw fields, the cap is {g.max_raw_fields} "
                       f"(gates.max_raw_fields).")
    if cx.constants > g.max_constants:
        raise Rejected(f"uses {cx.constants} constants, the cap is {g.max_constants} "
                       f"(gates.max_constants). Tuned constants are fitted parameters.")
    overlap = E.Zoo(alpha158_exprs()).overlap(expression)
    if overlap > g.max_zoo_overlap:
        raise Rejected(f"too close to a published factor: largest common subtree is {overlap} "
                       f"nodes, the cap is {g.max_zoo_overlap} (gates.max_zoo_overlap). "
                       f"Rediscovering a known factor is not a discovery.")
    return dict(canonical=canonical, nodes=cx.nodes, raw_fields=cx.raw_fields, constants=cx.constants,
                zoo_overlap=overlap, fingerprint=fp)


def preregister_hypothesis(cfg: Config, name: str, expression: str, rationale: str,
                           sign: int = 1, author: str = "") -> dict:
    name = (name or "").strip()
    rationale = (rationale or "").strip()
    if not name or len(name) > 64:
        raise Rejected("a hypothesis needs a short name (1-64 characters)")
    if len(rationale) < 20:
        raise Rejected("state the economic mechanism you expect, in at least a sentence. "
                       "A factor with no stated mechanism is a pattern, not a hypothesis - "
                       "and there is no way to tell later whether it did what you expected.")
    if sign not in (-1, 1):
        raise Rejected("sign must be +1 or -1: say which direction you expect BEFORE testing")

    checked = validate_expression(cfg, expression)
    payload = f"{name}|{checked['canonical']}|{sign}|{rationale}"
    content_sha = hashlib.sha256(payload.encode()).hexdigest()
    item = dict(name=name, expr=expression.strip(), fingerprint=checked["fingerprint"],
                sign=int(sign), rationale=rationale, author=(author or "").strip()[:64],
                origin="ui", content_sha=content_sha, status="pre-registered")
    out = repo.preregister(cfg.name, item, url=_url(cfg))
    return dict(**out, **checked, name=name,
                receipt=f"{content_sha[:16]} at {out['created_at']}",
                note="Recorded, not accepted. It faces every gate when `alphalab discover` "
                     "next runs, and it counts toward the trial count that deflates every "
                     "Sharpe in this config.")


def add_data_source(cfg: Config, files: list[tuple[str, bytes]], name: str,
                    audit_only: bool = True) -> dict:
    """Stage uploaded OHLCV CSVs, audit them, and optionally ingest.

    Audit first, always: duplicate dates, non-positive prices and high < low are
    refused here rather than discovered halfway through a backtest.
    """
    from ..sources import ingest
    safe = "".join(c for c in (name or "").strip() if c.isalnum() or c in "-_")
    if not safe:
        raise Rejected("give the data source a name (letters, digits, - and _)")
    if not files:
        raise Rejected("no files uploaded")

    stage = Path(cfg.workdir) / "uploads" / safe
    dest = Path("data") / safe
    if dest.exists() and not audit_only:
        raise Rejected(f"{dest} already exists. Ingesting would overwrite a data source other "
                       f"runs may depend on; remove it deliberately from a shell first.")
    stage.mkdir(parents=True, exist_ok=True)
    for fname, blob in files:
        leaf = Path(fname).name
        if not leaf.lower().endswith(".csv"):
            raise Rejected(f"{leaf}: only .csv files are accepted")
        (stage / leaf).write_bytes(blob)

    frames = ingest.collect(stage)
    problems = ingest.audit(frames)
    out = dict(name=safe, staged=str(stage), instruments=len(frames), problems=problems,
               audit_only=audit_only, ingested=False)
    if problems:
        out["verdict"] = (f"{len(problems)} problem(s). Nothing was ingested: these corrupt "
                          f"results silently rather than loudly.")
        return out
    out["verdict"] = "no problems found"
    if not audit_only:
        cfg_path = Path("configs") / f"{safe}.yaml"
        meta = ingest.run(str(stage), str(dest), universe=safe,
                          write_config_to=str(cfg_path), log=lambda *_: None)
        out.update(ingested=True, dest=str(dest), config=str(cfg_path), meta=meta,
                   verdict=f"ingested {meta['instruments']} instruments x {meta['sessions']} "
                           f"sessions; config written to {cfg_path}",
                   warning="Prices are assumed already adjusted for splits and dividends, and "
                           "a file containing only names listed today is survivorship-biased. "
                           "Neither can be detected for you.")
    out["at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    return out


def list_hypotheses(cfg: Config) -> list[dict]:
    return repo.hypotheses(cfg.name, url=_url(cfg))
