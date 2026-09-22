"""Read run artefacts safely.

The API serves JSON files written by the pipelines. Every name is checked
against a whitelist and every config name against a pattern, so a request can
never walk out of the work directory. Nothing outside `workdir` is readable,
and `.env`, `llm_calls.jsonl` and `llm_cache.sqlite` are never served at all.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..config import Config

SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

ARTEFACTS = {
    "discover_summary": "discover_summary.json",
    "model_results": "model_results.json",
    "cards": "cards.json",
    "hierarchy": "hierarchy.json",
    "audit": "protocol_audit.json",
    "revalidation": "revalidation.json",
    "assumptions": "assumptions.json",
    "library": "library.json",
    "bandit": "bandit.json",
    "memory": "memory.json",
    "portfolio_trial": "portfolio_trial.json",
    "model_choice": "model_choice.json",
}


def run_dir(cfg: Config, config_name: str | None = None) -> Path:
    name = config_name or cfg.name
    if not SAFE_NAME.match(name):
        raise ValueError(f"unsafe config name: {name!r}")
    base = Path(cfg.workdir).resolve()
    p = (base / name).resolve()
    if base not in p.parents and p != base:
        raise ValueError("path escapes the work directory")
    return p


def read(cfg: Config, key: str, config_name: str | None = None, default=None):
    if key not in ARTEFACTS:
        raise ValueError(f"unknown artefact {key!r}")
    p = run_dir(cfg, config_name) / ARTEFACTS[key]
    if not p.is_file():
        return default
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return default


def configs(cfg: Config) -> list[str]:
    base = Path(cfg.workdir)
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.iterdir()
                  if p.is_dir() and not p.name.startswith(".") and SAFE_NAME.match(p.name))
