"""The interface between research and execution: a target book, not an order.

Research says what the portfolio *should* hold, as of a timestamp, and signs it
with a content hash. Whatever executes reads that and works out the difference
itself. The research process never learns whether a fill happened, which is the
point: it cannot adapt to its own execution and quietly become a different
strategy from the one that was tested.

Why a state interface rather than an order stream:

* **Idempotent.** Replaying the same target book twice changes nothing the
  second time. Replaying an order stream doubles the position.
* **Self-healing.** A process that dies halfway leaves a stale target, not a
  half-executed sequence. The next reconciliation fixes it with no special case.
* **Auditable.** The hash ties a position back to the research run, the config
  and the commit that produced it - the same chain `forward publish` uses to
  make a prediction falsifiable.

A target book is also exactly what a paper broker consumes, which is how this
lab can run a full operational loop on live data with no credentials and no
custody at all.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class TargetBook:
    """What the book should hold, and everything needed to audit that claim."""
    as_of: str                                    # the data timestamp it was computed from
    weights: dict[str, float]                     # symbol -> fraction of NAV, shorts negative
    config_name: str = ""
    config_sha: str = ""
    git_sha: str = ""
    alphalab_version: str = ""
    strategy: str = ""
    note: str = ""
    generated_utc: str = field(default_factory=
                               lambda: dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))

    def gross(self) -> float:
        return float(sum(abs(w) for w in self.weights.values()))

    def net(self) -> float:
        return float(sum(self.weights.values()))

    def content_sha(self) -> str:
        payload = json.dumps(dict(as_of=self.as_of, strategy=self.strategy,
                                  weights={k: round(float(v), 8)
                                           for k, v in sorted(self.weights.items())}),
                             sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()

    def check(self, max_gross: float = 2.0, max_position: float = 0.25) -> list[str]:
        """Sanity limits that belong on the research side of the boundary.

        These are not risk management - the execution layer must re-check
        everything it is told, because a research bug is exactly the thing that
        produces a plausible-looking instruction to hold ten times the book.
        """
        problems = []
        if self.gross() > max_gross:
            problems.append(f"gross exposure {self.gross():.2f} exceeds {max_gross}")
        for s, w in self.weights.items():
            if abs(w) > max_position:
                problems.append(f"{s}: {w:+.1%} exceeds the {max_position:.0%} position limit")
        if any(w != w for w in self.weights.values()):
            problems.append("a weight is NaN")
        return problems


def write_targets(book: TargetBook, path: str | Path) -> dict:
    """Write the target book plus its manifest. Refuses to write a book that
    fails its own limits: an unreviewable instruction should not exist on disk."""
    problems = book.check()
    if problems:
        raise ValueError("target book fails its own limits: " + "; ".join(problems))
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    body = asdict(book)
    body["content_sha"] = book.content_sha()
    body["gross"] = book.gross()
    body["net"] = book.net()
    body["interface"] = ("state, not events: this is what the book SHOULD hold. Whatever "
                         "executes computes the difference and is responsible for its own "
                         "risk checks. Nothing in this repo places orders.")
    p.write_text(json.dumps(body, indent=2))
    return body


def read_targets(path: str | Path) -> dict:
    """Read a target book and verify it has not been altered since it was written."""
    body = json.loads(Path(path).read_text())
    book = TargetBook(as_of=body["as_of"], weights=body["weights"],
                      strategy=body.get("strategy", ""))
    recomputed = book.content_sha()
    body["verified"] = bool(recomputed == body.get("content_sha"))
    if not body["verified"]:
        body["warning"] = ("content hash does not match the weights in this file: it has been "
                           "edited since it was written. Do not act on it.")
    return body
