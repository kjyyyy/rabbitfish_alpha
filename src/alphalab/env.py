"""Load `.env` into the process environment.

`.env.example` has told users to "copy to .env and add your key" since v0.2 -
and nothing ever read the file. Keys only worked if the user happened to
`export` them by hand, which is not what the docs said. This closes that gap
with no new dependency.

Semantics match the usual dotenv convention, and the direction matters:
**a variable already set in the real environment wins.** That is what lets one
image run with `docker run -e ALPHALAB_LLM_BASE_URL=...` while the same `.env`
sits in the working directory.
"""
from __future__ import annotations

import os
from pathlib import Path


def load(path: str | Path | None = None, override: bool = False) -> dict[str, str]:
    """Read KEY=VALUE lines into os.environ. Returns the names loaded (never values)."""
    p = Path(path or os.environ.get("ALPHALAB_ENV_FILE") or ".env")
    if not p.is_file():
        return {}
    loaded = {}
    for raw in p.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key.startswith("export "):
            key = key[7:].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if not key or (key in os.environ and not override):
            continue                                  # the real environment wins
        os.environ[key] = value
        loaded[key] = "set"                           # names only: never log a secret
    return loaded
