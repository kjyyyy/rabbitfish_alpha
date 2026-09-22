"""Connectivity: what it does, and - more importantly - what it cannot do."""
import datetime as dt
import json

import pytest

from alphalab.connect import sources, targets


def test_nothing_in_the_package_can_place_an_order():
    """The research layer holds no credential that could move money.

    Checked against the parsed syntax tree rather than the source text, so that
    discussing withdrawal permission in a docstring does not trip it while an
    actual `exchange.withdraw(...)` call would.
    """
    import ast
    import inspect

    from alphalab import connect
    banned = {"create_order", "place_order", "cancel_order", "withdraw", "transfer",
              "create_market_buy_order", "create_limit_order", "send_transaction",
              "sign_transaction", "send_raw_transaction"}
    for mod in (connect, sources, targets):
        tree = ast.parse(inspect.getsource(mod))
        used = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        used |= {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        assert not (used & banned), f"{mod.__name__} calls {used & banned}"

    for mod in (sources, targets):
        for fname, fn in inspect.getmembers(mod, inspect.isfunction):
            params = inspect.signature(fn).parameters
            assert not any(p in params for p in ("api_key", "secret", "private_key", "mnemonic")), \
                f"{mod.__name__}.{fname} accepts a credential"


# --------------------------------------------------------------------------
# the target book
# --------------------------------------------------------------------------
def test_a_target_book_is_state_and_verifies_its_own_contents(tmp_path):
    book = targets.TargetBook(as_of="2026-09-18", strategy="carry",
                              weights={"BTC": 0.10, "ETH": -0.08})
    assert book.gross() == pytest.approx(0.18)
    assert book.net() == pytest.approx(0.02)

    p = tmp_path / "targets.json"
    body = targets.write_targets(book, p)
    assert body["content_sha"] and "state, not events" in body["interface"]

    back = targets.read_targets(p)
    assert back["verified"] is True

    # editing the file must be detectable: an instruction nobody can verify is
    # an instruction nobody should act on
    tampered = json.loads(p.read_text())
    tampered["weights"]["BTC"] = 0.90
    p.write_text(json.dumps(tampered))
    assert targets.read_targets(p)["verified"] is False
    assert "edited since it was written" in targets.read_targets(p)["warning"]


def test_a_book_that_breaks_its_own_limits_is_never_written(tmp_path):
    huge = targets.TargetBook(as_of="2026-09-18", weights={"BTC": 3.0})
    with pytest.raises(ValueError, match="fails its own limits"):
        targets.write_targets(huge, tmp_path / "x.json")
    assert not (tmp_path / "x.json").exists(), (
        "an unreviewable instruction should not exist on disk at all")

    nan_book = targets.TargetBook(as_of="2026-09-18", weights={"BTC": float("nan")})
    assert "NaN" in " ".join(nan_book.check())


def test_replaying_a_target_book_is_idempotent(tmp_path):
    """The reason for a state interface rather than an order stream."""
    book = targets.TargetBook(as_of="2026-09-18", weights={"BTC": 0.1})
    a = targets.write_targets(book, tmp_path / "t.json")["content_sha"]
    b = targets.write_targets(book, tmp_path / "t.json")["content_sha"]
    assert a == b, "the same state written twice is the same state, not twice the position"


# --------------------------------------------------------------------------
# free data sources
# --------------------------------------------------------------------------
def test_the_archive_timestamp_unit_changes_mid_history():
    """A silent unit change that mangles half a series if assumed constant."""
    assert sources.timestamp_unit("spot", dt.date(2024, 12, 31)) == "ms"
    assert sources.timestamp_unit("spot", dt.date(2025, 1, 1)) == "us"
    assert sources.timestamp_unit("um", dt.date(2025, 6, 1)) == "ms", \
        "the cutover documented for the spot archive should not be assumed for futures"


def test_bulk_urls_cover_dated_contracts_and_funding():
    coinm = sources.binance_bulk_urls("BTCUSD_240628", "1d", market="cm", months=["2024-03"])
    assert "futures/cm" in coinm[0]["url"] and coinm[0]["checksum"].endswith(".CHECKSUM")

    funding = sources.binance_bulk_urls("BTCUSDT", market="um", kind="fundingRate",
                                        months=["2024-03"])
    assert "fundingRate" in funding[0]["url"]

    with pytest.raises(ValueError):
        sources.binance_bulk_urls("X", market="nope", months=["2024-01"])


def test_survivorship_diff_finds_what_a_live_symbol_list_deleted():
    out = sources.survivorship_diff(
        archive_symbols=["BTCUSDT", "ETHUSDT", "LUNAUSDT", "FTTUSDT"],
        live_symbols=["BTCUSDT", "ETHUSDT"])
    assert out["n_delisted"] == 2 and "LUNAUSDT" in out["delisted"]
    assert "went to zero" in out["survivorship_warning"]

    clean = sources.survivorship_diff(["BTCUSDT"], ["BTCUSDT"])
    assert clean["n_delisted"] == 0


def test_ccxt_is_optional_and_says_so_when_absent(monkeypatch):
    import builtins
    real = builtins.__import__

    def no_ccxt(name, *a, **k):
        if name == "ccxt":
            raise ImportError("no ccxt")
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_ccxt)
    with pytest.raises(SystemExit, match="ccxt is not installed"):
        sources.fetch_ohlcv("binance", "BTC/USDT")
