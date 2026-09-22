"""Connectivity: market data in, target positions out. No order path.

The three-layer separation systematic shops use, and the reason for it:

    data layer        read-only credentials, or none at all
    research layer    ZERO exchange credentials; emits timestamped targets
    execution layer   holds every credential, contains no strategy logic

This package implements the first two and deliberately stops. `sources` fetches
market data with read-only or no credentials. `targets` writes what the research
says the book should hold, as a hash-stamped file any execution process can
reconcile against. Nothing here can place, cancel or amend an order, and no
function takes a key with trade permission.

That is a design decision, not an unfinished feature:

* **Nothing has earned an order yet.** No factor in this lab has passed a
  Deflated Sharpe that counts every trial, and there are zero clean forward
  weeks. An execution path would be plumbing for a decision the evidence has
  not supported.
* **A state interface is safer than an event interface.** "The book should hold
  X" is idempotent and self-healing: replay it twice and nothing happens twice,
  and a process that died mid-run leaves a reconcilable state rather than a
  half-sent order sequence. "Send order Y" is neither.
* **The blast radius of a leaked credential is set here.** A read-only key that
  leaks costs you data. A trade-enabled key that leaks can be drained by
  contra-trading illiquid pairs even without withdrawal permission. A hot
  private key that leaks is total, irreversible loss.

On MetaMask specifically, since it is the thing people reach for: it is a
browser extension that holds keys for a *human* to approve transactions one at
a time. There is no supported way for a headless research process to use it, and
the workaround - putting the private key in an environment variable so a script
can sign - removes every protection MetaMask exists to provide. A server-side
system that genuinely needs on-chain execution uses a scoped session or
delegated key that cannot withdraw, a hardware signer, or a custody service.
This lab needs none of them, because it does not trade.
"""
from .targets import TargetBook, read_targets, write_targets

__all__ = ["TargetBook", "write_targets", "read_targets"]
