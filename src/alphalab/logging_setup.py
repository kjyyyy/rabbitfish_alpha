"""Structured logging and a heartbeat.

Runs printed to stdout with no timestamps, no run id and no progress, which is
fine while you watch them and useless afterwards - and it left no way to tell a
slow discovery run from a hung one. This adds:

* `configure(fmt="json")` - one JSON object per line, for an unattended run whose
  output will be read by `jq` or shipped somewhere, with the run id and config
  attached to every line.
* `configure(fmt="text")` - the default, still readable by a human.
* `progress()` - a heartbeat every N items carrying elapsed time and rate, so a
  stalled loop is obvious at a glance.

Nothing here logs a secret: the LLM layer records prompt hashes and token counts,
never prompts or keys, and that is unchanged.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time

LOGGER = "alphalab"
_CONTEXT: dict[str, str] = {}
_RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + "Z",
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
            **_CONTEXT,
        }
        for k, v in record.__dict__.items():          # extra={...} passes through
            if k not in _RESERVED and not k.startswith("_"):
                out[k] = v
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str)


def configure(fmt: str | None = None, level: str = "INFO") -> logging.Logger:
    fmt = (fmt or os.environ.get("ALPHALAB_LOG_FORMAT") or "text").lower()
    log = logging.getLogger(LOGGER)
    log.setLevel(level.upper())
    log.handlers.clear()
    log.propagate = False
    h = logging.StreamHandler(sys.stderr if fmt == "json" else sys.stdout)
    h.setFormatter(JsonFormatter() if fmt == "json"
                   else logging.Formatter("%(asctime)s %(levelname)-5s %(message)s", "%H:%M:%S"))
    log.addHandler(h)
    return log


def bind(**kv) -> None:
    """Attach run-level context (run id, config, version) to every later line."""
    _CONTEXT.update({k: str(v) for k, v in kv.items() if v is not None})


def context() -> dict:
    return dict(_CONTEXT)


def get(name: str = "") -> logging.Logger:
    return logging.getLogger(f"{LOGGER}.{name}" if name else LOGGER)


class progress:
    """Heartbeat for a long loop.

    with progress("evaluate", total=400) as p:
        for c in candidates:
            ...
            p.tick()
    """

    def __init__(self, stage: str, total: int = 0, every: int = 25, log=None):
        self.stage, self.total, self.every = stage, total, max(1, every)
        self.log = log or get(stage)
        self.n = 0
        self.t0 = time.time()

    def __enter__(self):
        self.log.info(f"{self.stage}: starting"
                      + (f" ({self.total} items)" if self.total else ""),
                      extra=dict(stage=self.stage, event="start", total=self.total))
        return self

    def tick(self, n: int = 1, **extra):
        self.n += n
        if self.n % self.every == 0 or (self.total and self.n == self.total):
            el = time.time() - self.t0
            rate = self.n / el if el > 0 else 0.0
            eta = (self.total - self.n) / rate if self.total and rate > 0 else None
            self.log.info(
                f"{self.stage}: {self.n}"
                + (f"/{self.total}" if self.total else "")
                + f"  {el:.0f}s elapsed, {rate:.1f}/s"
                + (f", ~{eta:.0f}s left" if eta is not None else ""),
                extra=dict(stage=self.stage, event="progress", done=self.n, total=self.total,
                           elapsed_s=round(el, 1), rate_per_s=round(rate, 2),
                           eta_s=round(eta, 1) if eta is not None else None, **extra))

    def __exit__(self, exc_type, exc, tb):
        el = time.time() - self.t0
        if exc_type:
            self.log.error(f"{self.stage}: failed after {el:.0f}s ({exc_type.__name__}: {exc})",
                           extra=dict(stage=self.stage, event="error", elapsed_s=round(el, 1)))
        else:
            self.log.info(f"{self.stage}: done, {self.n} items in {el:.0f}s",
                          extra=dict(stage=self.stage, event="done", done=self.n,
                                     elapsed_s=round(el, 1)))
        return False
